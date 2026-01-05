package com.polybot.hft.polymarket.fund.service;

import com.polybot.hft.polymarket.fund.config.FundConfig;
import com.polybot.hft.polymarket.fund.model.IndexConstituent;
import com.polybot.hft.polymarket.fund.model.TraderSignal;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
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

    // Prometheus metrics
    private final Counter tradesPolledCounter;
    private final Counter signalsGeneratedCounter;
    private final Timer pollDurationTimer;
    private final MeterRegistry meterRegistry;

    public FundTradeListener(
            FundConfig config,
            IndexWeightProvider weightProvider,
            FundPositionMirror positionMirror,
            JdbcTemplate jdbcTemplate,
            Clock clock,
            MeterRegistry meterRegistry
    ) {
        this.config = config;
        this.weightProvider = weightProvider;
        this.positionMirror = positionMirror;
        this.jdbcTemplate = jdbcTemplate;
        this.clock = clock;
        this.meterRegistry = meterRegistry;

        // Initialize Prometheus metrics
        this.tradesPolledCounter = Counter.builder("fund.trades.polled")
                .description("Total trades polled from ClickHouse")
                .tag("fund", config.indexType())
                .register(meterRegistry);

        this.signalsGeneratedCounter = Counter.builder("fund.signals.generated")
                .description("Total signals generated from trader activity")
                .tag("fund", config.indexType())
                .register(meterRegistry);

        this.pollDurationTimer = Timer.builder("fund.poll.duration")
                .description("Time to poll for trades from ClickHouse")
                .tag("fund", config.indexType())
                .register(meterRegistry);

        // Register gauge for tracked traders count
        io.micrometer.core.instrument.Gauge.builder("fund.traders.tracked", lastTradeByTrader, Map::size)
                .description("Number of tracked traders")
                .tag("fund", config.indexType())
                .register(meterRegistry);
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
            List<TraderSignal> signals = pollDurationTimer.record(() -> fetchNewTrades());
            for (TraderSignal signal : signals) {
                positionMirror.queueSignal(signal);
                signalsGenerated++;
                signalsGeneratedCounter.increment();
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
            log.warn("No constituents found for index: {}. Check aware_psi_index table.", config.indexType());
            return List.of();
        }
        log.debug("Fetching trades for {} constituents in index {}", constituents.size(), config.indexType());

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
        tradesPolledCounter.increment(trades.size());

        if (!trades.isEmpty()) {
            log.info("Found {} new trades from PSI-10 traders (window: {} to {})",
                    trades.size(), lastPollTime, now);
        }

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

        // Build query with quoted address list and formatted timestamps
        // ClickHouse JDBC doesn't handle IN clause placeholders well
        String addressList = addresses.stream()
                .map(addr -> "'" + addr + "'")
                .collect(java.util.stream.Collectors.joining(","));

        // Format timestamps for ClickHouse DateTime64
        java.time.format.DateTimeFormatter fmt = java.time.format.DateTimeFormatter
                .ofPattern("yyyy-MM-dd HH:mm:ss")
                .withZone(java.time.ZoneOffset.UTC);
        String fromStr = fmt.format(from);
        String toStr = fmt.format(to);

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
              AND ts > toDateTime('%s')
              AND ts <= toDateTime('%s')
            ORDER BY ts
            LIMIT 100
            """.formatted(addressList, fromStr, toStr);

        log.debug("Querying trades: {} addresses, from={}, to={}", addresses.size(), from, to);
        try {
            List<RawTrade> result = jdbcTemplate.query(sql, (rs, rowNum) -> new RawTrade(
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
            ));
            if (!result.isEmpty()) {
                log.info("Found {} trades from PSI traders", result.size());
            }
            return result;
        } catch (Exception e) {
            log.warn("Trade query error: {}", e.getMessage());
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
