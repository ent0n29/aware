package com.polybot.hft.polymarket.fund.service;

import com.polybot.hft.polymarket.fund.config.FundConfig;
import com.polybot.hft.polymarket.fund.model.IndexConstituent;
import com.polybot.hft.polymarket.fund.model.TraderSignal;
import lombok.extern.slf4j.Slf4j;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;

import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Listens for trades from PSI index traders and generates signals.
 *
 * Uses polling from ClickHouse rather than Kafka direct consumption
 * to leverage existing infrastructure and deduplication.
 *
 * Flow:
 * 1. Every second, polls ClickHouse for new trades from indexed traders
 * 2. Converts trades to TraderSignals
 * 3. Queues signals in FundPositionMirror (with delay)
 */
@Slf4j
public class FundTradeListener {

    private final FundConfig config;
    private final IndexWeightProvider weightProvider;
    private final FundPositionMirror positionMirror;
    private final JdbcTemplate jdbcTemplate;
    private final Clock clock;

    // Track last processed trade per trader to avoid duplicates
    private final Map<String, Instant> lastTradeByTrader = new ConcurrentHashMap<>();

    // Highwater mark for polling
    private Instant lastPollTime = null;

    // Metrics
    private long tradesProcessed = 0;
    private long signalsGenerated = 0;

    public FundTradeListener(
            FundConfig config,
            IndexWeightProvider weightProvider,
            FundPositionMirror positionMirror,
            JdbcTemplate jdbcTemplate,
            Clock clock
    ) {
        this.config = config;
        this.weightProvider = weightProvider;
        this.positionMirror = positionMirror;
        this.jdbcTemplate = jdbcTemplate;
        this.clock = clock;
    }

    /**
     * Poll for new trades from indexed traders.
     * Runs every second to catch trades quickly.
     */
    @Scheduled(fixedRate = 1000)
    public void pollForTrades() {
        if (!config.enabled()) {
            return;
        }

        try {
            List<TraderSignal> signals = fetchNewTrades();
            for (TraderSignal signal : signals) {
                positionMirror.queueSignal(signal);
                signalsGenerated++;
            }
        } catch (Exception e) {
            log.warn("Error polling for trades: {}", e.getMessage());
        }
    }

    /**
     * Fetch new trades from ClickHouse for indexed traders.
     */
    private List<TraderSignal> fetchNewTrades() {
        // Get current index constituents
        List<IndexConstituent> constituents = weightProvider.getConstituents(config.indexType());
        if (constituents.isEmpty()) {
            return List.of();
        }

        // Build proxy address list
        List<String> addresses = constituents.stream()
                .map(IndexConstituent::proxyAddress)
                .toList();

        // Initialize polling window
        Instant now = clock.instant();
        if (lastPollTime == null) {
            // Start from 10 seconds ago on first poll
            lastPollTime = now.minusSeconds(10);
        }

        // Query for new trades
        List<RawTrade> trades = queryTrades(addresses, lastPollTime, now);
        tradesProcessed += trades.size();

        // Update highwater mark
        lastPollTime = now;

        // Convert to signals, filtering duplicates
        List<TraderSignal> signals = new ArrayList<>();
        for (RawTrade trade : trades) {
            // Check for duplicate
            Instant lastSeen = lastTradeByTrader.get(trade.proxyAddress);
            if (lastSeen != null && !trade.ts.isAfter(lastSeen)) {
                continue;
            }
            lastTradeByTrader.put(trade.proxyAddress, trade.ts);

            // Get trader's weight
            Optional<IndexConstituent> constituent = constituents.stream()
                    .filter(c -> c.proxyAddress().equalsIgnoreCase(trade.proxyAddress))
                    .findFirst();

            if (constituent.isEmpty()) {
                continue;
            }

            TraderSignal signal = convertToSignal(trade, constituent.get());
            signals.add(signal);

            log.info("New signal: {} {} {} shares of {} at ${} (trader: {})",
                    signal.type(), signal.outcome(), signal.shares(),
                    signal.marketSlug(), signal.price(), signal.username());
        }

        return signals;
    }

    /**
     * Query ClickHouse for trades from indexed traders.
     */
    private List<RawTrade> queryTrades(List<String> addresses, Instant from, Instant to) {
        if (addresses.isEmpty()) {
            return List.of();
        }

        // Build parameterized query with proper IN clause
        String placeholders = String.join(",", Collections.nCopies(addresses.size(), "?"));
        String sql = """
            SELECT
                ts,
                trade_id,
                username,
                proxy_address,
                market_slug,
                token_id,
                side,
                outcome,
                price,
                size,
                notional
            FROM polybot.aware_global_trades_dedup
            WHERE proxy_address IN (%s)
              AND ts > ?
              AND ts <= ?
            ORDER BY ts
            LIMIT 100
            """.formatted(placeholders);

        // Build params array
        Object[] params = new Object[addresses.size() + 2];
        for (int i = 0; i < addresses.size(); i++) {
            params[i] = addresses.get(i);
        }
        params[addresses.size()] = Timestamp.from(from);
        params[addresses.size() + 1] = Timestamp.from(to);

        try {
            return jdbcTemplate.query(sql, (rs, rowNum) -> new RawTrade(
                    rs.getTimestamp("ts").toInstant(),
                    rs.getString("trade_id"),
                    rs.getString("username"),
                    rs.getString("proxy_address"),
                    rs.getString("market_slug"),
                    rs.getString("token_id"),
                    rs.getString("side"),
                    rs.getString("outcome"),
                    rs.getDouble("price"),
                    rs.getDouble("size"),
                    rs.getDouble("notional")
            ), params);
        } catch (Exception e) {
            log.debug("Trade query error: {}", e.getMessage());
            return List.of();
        }
    }

    private TraderSignal convertToSignal(RawTrade trade, IndexConstituent constituent) {
        TraderSignal.SignalType type = trade.side.equalsIgnoreCase("BUY")
                ? TraderSignal.SignalType.BUY
                : TraderSignal.SignalType.SELL;

        return new TraderSignal(
                UUID.randomUUID().toString(),
                trade.username,
                trade.marketSlug,
                trade.tokenId,
                trade.outcome,
                type,
                BigDecimal.valueOf(trade.size),
                BigDecimal.valueOf(trade.price),
                BigDecimal.valueOf(trade.notional),
                clock.instant(),
                trade.ts,
                constituent.weight()
        );
    }

    public Map<String, Object> getMetrics() {
        return Map.of(
                "tradesProcessed", tradesProcessed,
                "signalsGenerated", signalsGenerated,
                "trackedTraders", lastTradeByTrader.size(),
                "lastPollTime", lastPollTime != null ? lastPollTime.toString() : "never"
        );
    }

    /**
     * Internal record for raw trade data from ClickHouse.
     */
    private record RawTrade(
            Instant ts,
            String tradeId,
            String username,
            String proxyAddress,
            String marketSlug,
            String tokenId,
            String side,
            String outcome,
            double price,
            double size,
            double notional
    ) {}
}
