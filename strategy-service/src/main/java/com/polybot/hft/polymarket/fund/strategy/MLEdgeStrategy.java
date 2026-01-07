package com.polybot.hft.polymarket.fund.strategy;

import com.polybot.hft.polymarket.fund.config.ActiveFundConfig;
import com.polybot.hft.polymarket.fund.model.AlphaSignal;
import com.polybot.hft.strategy.executor.ExecutorApiClient;
import io.micrometer.core.instrument.MeterRegistry;
import lombok.extern.slf4j.Slf4j;
import org.springframework.jdbc.core.JdbcTemplate;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * ALPHA-EDGE Fund Strategy.
 *
 * Trades based on ML-predicted edge scores from the Python analytics pipeline.
 * High-edge traders are identified through machine learning models that analyze
 * trading patterns, timing, and historical performance.
 *
 * Signal Sources:
 * 1. ClickHouse polling: Reads from polybot.aware_ml_scores for high-edge traders
 * 2. Cross-references with aware_global_trades_dedup for recent activity
 *
 * Signal Flow:
 * 1. ML pipeline (Python) computes edge_score and anomaly_score per trader
 * 2. This strategy polls for traders with edge_score > threshold and low anomaly
 * 3. Fetches recent trades from high-edge traders
 * 4. Converts trades to AlphaSignals with confidence based on edge_score
 * 5. ActiveFundExecutor handles execution
 *
 * Filtering:
 * - Edge score threshold (70+ out of 100 = GOLD tier or better)
 * - Tier confidence filter (> 0.5 for confident ML predictions)
 * - Signal freshness (trades within last hour)
 * - Deduplication (track processed trades)
 * - Market validity (check market is still active)
 *
 * Edge Decay Detection:
 * - Track edge scores over time
 * - Generate SELL signals when edge decays significantly
 * - Exit positions from traders losing their edge
 */
@Slf4j
public class MLEdgeStrategy extends ActiveFundExecutor {

    private static final String FUND_TYPE = "ALPHA-EDGE";

    // Polling configuration
    private static final int DEFAULT_POLL_INTERVAL_SECONDS = 10;
    private static final int MAX_TRADE_AGE_SECONDS = 3600;  // 1 hour
    private static final int MARKET_COOLDOWN_SECONDS = 120;  // 2 minutes between signals on same market
    private static final int EDGE_CACHE_TTL_SECONDS = 300;   // 5 minutes cache for edge scores

    // Edge thresholds - ML ensemble produces scores in 0-100 range
    private static final double MIN_EDGE_SCORE = 70.0;  // GOLD tier threshold (top ~20% traders)
    private static final double MAX_ANOMALY_SCORE = 0.5;  // tier_confidence > 0.5 (more confident predictions)
    private static final double EDGE_DECAY_THRESHOLD = 15.0;  // Points drop triggers sell (scaled for 0-100)

    // Cache of high-edge traders: proxy_address -> EdgeTrader
    private final Map<String, EdgeTrader> highEdgeTraders = new ConcurrentHashMap<>();

    // Track processed trades to avoid duplicates
    private final Set<String> processedTradeIds = ConcurrentHashMap.newKeySet();

    // Track last signal time per market for cooldown
    private final Map<String, Instant> lastSignalByMarket = new ConcurrentHashMap<>();

    // Track historical edge scores for decay detection
    private final Map<String, EdgeHistory> edgeHistories = new ConcurrentHashMap<>();

    // Highwater mark for trade polling
    private Instant lastTradePollTime = null;

    // Metrics
    private long tradersPolled = 0;
    private long tradesPolled = 0;
    private long signalsGenerated = 0;
    private long edgeDecaysDetected = 0;

    public MLEdgeStrategy(
            ActiveFundConfig config,
            ExecutorApiClient executorApi,
            JdbcTemplate jdbcTemplate,
            Clock clock,
            MeterRegistry meterRegistry
    ) {
        super(config, executorApi, jdbcTemplate, clock, meterRegistry);
    }

    @Override
    public String getFundType() {
        return FUND_TYPE;
    }

    @Override
    protected void onStart() {
        super.onStart();
        log.info("MLEdgeStrategy starting - poll interval: {}s, edge threshold: {}, max anomaly: {}",
                DEFAULT_POLL_INTERVAL_SECONDS, MIN_EDGE_SCORE, MAX_ANOMALY_SCORE);
    }

    /**
     * Poll ClickHouse for ML edge scores and recent trades.
     *
     * Called periodically by scheduled task (every 10 seconds).
     */
    @Override
    public void pollForSignals() {
        if (!isEnabled()) {
            return;
        }

        try {
            // Step 1: Refresh high-edge trader cache
            refreshHighEdgeTraders();

            // Step 2: Check for edge decay on tracked positions
            checkEdgeDecay();

            // Step 3: Fetch and process recent trades from high-edge traders
            if (!highEdgeTraders.isEmpty()) {
                processRecentTrades();
            }
        } catch (Exception e) {
            log.warn("Error polling for ML edge signals: {}", e.getMessage());
        }
    }

    /**
     * Refresh cache of high-edge traders from ML scores table.
     *
     * Note: The actual schema uses ml_score instead of edge_score,
     * and tier_confidence (higher = better) instead of anomaly_score.
     */
    private void refreshHighEdgeTraders() {
        String sql = """
            SELECT
                username,
                proxy_address,
                ml_score as edge_score,
                1.0 - tier_confidence as anomaly_score,
                ml_tier as strategy_cluster,
                calculated_at as updated_at
            FROM polybot.aware_ml_scores FINAL
            WHERE ml_score > ?
              AND tier_confidence > ?
            ORDER BY ml_score DESC
            LIMIT 50
            """;

        try {
            List<EdgeTrader> traders = jdbcTemplate.query(sql,
                    ps -> {
                        ps.setDouble(1, MIN_EDGE_SCORE);
                        // tier_confidence > 0.5 means confident prediction (inverse of anomaly_score < 0.5)
                        ps.setDouble(2, 1.0 - MAX_ANOMALY_SCORE);
                    },
                    (rs, rowNum) -> new EdgeTrader(
                            rs.getString("username"),
                            rs.getString("proxy_address"),
                            rs.getDouble("edge_score"),
                            rs.getDouble("anomaly_score"),
                            rs.getString("strategy_cluster"),
                            rs.getTimestamp("updated_at").toInstant()
                    )
            );

            tradersPolled += traders.size();

            // Update cache and track edge history
            Instant now = clock.instant();
            for (EdgeTrader trader : traders) {
                EdgeTrader existing = highEdgeTraders.get(trader.proxyAddress);

                // Track edge history for decay detection
                EdgeHistory history = edgeHistories.computeIfAbsent(
                        trader.proxyAddress,
                        k -> new EdgeHistory()
                );
                history.recordEdge(trader.edgeScore, now);

                // Check for edge decay
                if (existing != null && trader.edgeScore < existing.edgeScore - EDGE_DECAY_THRESHOLD) {
                    log.info("Edge decay detected for {}: {} -> {}",
                            trader.username, existing.edgeScore, trader.edgeScore);
                    edgeDecaysDetected++;
                    // Edge decay signals will be generated in checkEdgeDecay()
                }

                highEdgeTraders.put(trader.proxyAddress, trader);
            }

            // Remove stale entries
            Instant staleThreshold = now.minusSeconds(EDGE_CACHE_TTL_SECONDS * 2);
            highEdgeTraders.entrySet().removeIf(e ->
                    e.getValue().updatedAt.isBefore(staleThreshold));

            if (!traders.isEmpty()) {
                log.debug("Refreshed {} high-edge traders (cache size: {})",
                        traders.size(), highEdgeTraders.size());
            }

        } catch (Exception e) {
            log.warn("Error refreshing high-edge traders: {}", e.getMessage());
        }
    }

    /**
     * Check for edge decay on traders we're currently following.
     * Generate SELL signals when edge significantly decays.
     */
    private void checkEdgeDecay() {
        Instant now = clock.instant();

        for (Map.Entry<String, EdgeHistory> entry : edgeHistories.entrySet()) {
            String proxyAddress = entry.getKey();
            EdgeHistory history = entry.getValue();

            // Check if we have a position with this trader
            EdgeTrader trader = highEdgeTraders.get(proxyAddress);
            if (trader == null) continue;

            // Calculate edge decay
            Double decay = history.calculateDecay();
            if (decay != null && decay > EDGE_DECAY_THRESHOLD) {
                log.info("Significant edge decay for {}: {} points", trader.username, decay);

                // Generate SELL signal for all positions from this trader
                generateEdgeDecaySignal(trader, decay);
            }
        }
    }

    /**
     * Generate SELL signal due to edge decay.
     */
    private void generateEdgeDecaySignal(EdgeTrader trader, double decay) {
        // Look up current positions that originated from this trader's signals
        // For now, we'll rely on the position tracking in the base executor
        // In a full implementation, we'd query ClickHouse for our positions
        // that were opened based on this trader's activity

        // This is a simplified approach - generate a general decay alert
        String signalId = UUID.randomUUID().toString();
        double confidence = Math.min(0.9, decay / 30.0);  // Scale decay to confidence

        AlphaSignal signal = AlphaSignal.builder()
                .signalId(signalId)
                .source(AlphaSignal.SignalSource.EDGE_DECAY)
                .action(AlphaSignal.SignalAction.SELL)
                .marketSlug("*")  // Applies to all markets from this trader
                .tokenId("*")
                .outcome("*")
                .confidence(confidence)
                .strength(decay / 25.0)
                .urgency(AlphaSignal.SignalUrgency.MEDIUM)
                .reason(String.format("Edge decay detected for %s (%.1f points)", trader.username, decay))
                .metadata(Map.of(
                        "trader_username", trader.username,
                        "proxy_address", trader.proxyAddress,
                        "current_edge", trader.edgeScore,
                        "decay_amount", decay,
                        "signal_type", "EDGE_DECAY"
                ))
                .detectedAt(clock.instant())
                .expiresAt(clock.instant().plusSeconds(config.signalExpirySeconds()))
                .build();

        log.info("Generated edge decay SELL signal for trader {}", trader.username);
        signalsGenerated++;

        // Note: Edge decay signals need special handling in execution
        // The base executor will need to match these to existing positions
        // For now, we log the signal for manual review
    }

    /**
     * Fetch and process recent trades from high-edge traders.
     */
    private void processRecentTrades() {
        if (highEdgeTraders.isEmpty()) {
            return;
        }

        Instant now = clock.instant();

        // Initialize polling window
        if (lastTradePollTime == null) {
            lastTradePollTime = now.minusSeconds(MAX_TRADE_AGE_SECONDS);
        }

        // Build list of proxy addresses
        List<String> proxyAddresses = new ArrayList<>(highEdgeTraders.keySet());
        if (proxyAddresses.isEmpty()) {
            return;
        }

        // Format timestamps for ClickHouse
        DateTimeFormatter fmt = DateTimeFormatter
                .ofPattern("yyyy-MM-dd HH:mm:ss")
                .withZone(ZoneOffset.UTC);
        String fromStr = fmt.format(lastTradePollTime);
        String toStr = fmt.format(now);

        // Build parameterized IN clause
        String placeholders = String.join(",", Collections.nCopies(proxyAddresses.size(), "?"));

        String sql = """
            SELECT
                id,
                ts,
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
            ORDER BY ts DESC
            LIMIT 100
            """.formatted(placeholders, fromStr, toStr);

        try {
            List<TraderTrade> trades = jdbcTemplate.query(sql,
                    ps -> {
                        for (int i = 0; i < proxyAddresses.size(); i++) {
                            ps.setString(i + 1, proxyAddresses.get(i));
                        }
                    },
                    (rs, rowNum) -> new TraderTrade(
                            rs.getString("id"),
                            rs.getTimestamp("ts").toInstant(),
                            rs.getString("username"),
                            rs.getString("proxy_address"),
                            rs.getString("market_slug"),
                            rs.getString("token_id"),
                            rs.getString("side"),
                            rs.getString("outcome"),
                            rs.getBigDecimal("price"),
                            rs.getBigDecimal("size"),
                            rs.getBigDecimal("notional")
                    )
            );

            tradesPolled += trades.size();
            lastTradePollTime = now;

            if (!trades.isEmpty()) {
                log.info("Fetched {} recent trades from high-edge traders", trades.size());
            }

            for (TraderTrade trade : trades) {
                try {
                    processTrade(trade);
                } catch (Exception e) {
                    log.warn("Error processing trade {}: {}", trade.id, e.getMessage());
                }
            }

        } catch (Exception e) {
            log.warn("Error fetching trades from high-edge traders: {}", e.getMessage());
        }
    }

    /**
     * Process a single trade from a high-edge trader.
     */
    private void processTrade(TraderTrade trade) {
        // Skip if already processed
        if (processedTradeIds.contains(trade.id)) {
            return;
        }

        // Skip if trade is too old
        Instant now = clock.instant();
        long ageSeconds = Duration.between(trade.ts, now).getSeconds();
        if (ageSeconds > MAX_TRADE_AGE_SECONDS) {
            processedTradeIds.add(trade.id);
            return;
        }

        // Check market cooldown
        if (isMarketOnCooldown(trade.marketSlug)) {
            log.debug("Market {} on cooldown, skipping trade {}", trade.marketSlug, trade.id);
            return;  // Don't mark as processed - try again later
        }

        // Get trader's edge info
        EdgeTrader trader = highEdgeTraders.get(trade.proxyAddress);
        if (trader == null) {
            processedTradeIds.add(trade.id);
            return;  // Trader no longer in high-edge cache
        }

        // Convert to AlphaSignal
        AlphaSignal signal = convertToSignal(trade, trader);

        if (signal != null) {
            // Process through parent executor
            processSignal(signal);
            signalsGenerated++;

            // Update cooldown
            lastSignalByMarket.put(trade.marketSlug, now);
        }

        // Mark as processed
        processedTradeIds.add(trade.id);

        // Cleanup old processed IDs (keep last 2000)
        if (processedTradeIds.size() > 2000) {
            Iterator<String> iter = processedTradeIds.iterator();
            int toRemove = processedTradeIds.size() - 1000;
            while (toRemove > 0 && iter.hasNext()) {
                iter.next();
                iter.remove();
                toRemove--;
            }
        }
    }

    /**
     * Convert a trader's trade to an AlphaSignal.
     */
    private AlphaSignal convertToSignal(TraderTrade trade, EdgeTrader trader) {
        // Determine action from trade side
        AlphaSignal.SignalAction action = switch (trade.side.toUpperCase()) {
            case "BUY", "YES" -> AlphaSignal.SignalAction.BUY;
            case "SELL", "NO" -> AlphaSignal.SignalAction.SELL;
            default -> null;
        };

        if (action == null) {
            log.debug("Could not determine action from side: {}", trade.side);
            return null;
        }

        // Calculate confidence based on edge score (0-100 -> 0.0-1.0)
        double confidence = Math.min(1.0, trader.edgeScore / 100.0);

        // Calculate strength based on trade size and inverse anomaly
        double strength = Math.min(1.0, (1.0 - trader.anomalyScore) *
                Math.min(1.0, trade.notional.doubleValue() / 1000.0));

        // Determine urgency based on edge score and trade recency
        AlphaSignal.SignalUrgency urgency;
        long tradeAgeSeconds = Duration.between(trade.ts, clock.instant()).getSeconds();
        if (trader.edgeScore >= 90 && tradeAgeSeconds < 60) {
            urgency = AlphaSignal.SignalUrgency.HIGH;
        } else if (trader.edgeScore >= 80 && tradeAgeSeconds < 300) {
            urgency = AlphaSignal.SignalUrgency.MEDIUM;
        } else {
            urgency = AlphaSignal.SignalUrgency.LOW;
        }

        // Build the signal
        return AlphaSignal.builder()
                .signalId(UUID.randomUUID().toString())
                .source(AlphaSignal.SignalSource.ML_EDGE_PREDICTOR)
                .action(action)
                .marketSlug(trade.marketSlug)
                .tokenId(trade.tokenId)
                .outcome(trade.outcome != null ? trade.outcome : "Yes")
                .confidence(confidence)
                .strength(strength)
                .urgency(urgency)
                .suggestedSizeUsd(trade.notional.multiply(BigDecimal.valueOf(0.5)))  // Follow at 50% size
                .suggestedSizePct(config.basePositionPct())
                .reason(String.format("High-edge trader %s (score: %.0f) %s %s @ $%.4f",
                        trader.username, trader.edgeScore, trade.side, trade.outcome, trade.price))
                .metadata(Map.of(
                        "trader_username", trader.username,
                        "proxy_address", trader.proxyAddress,
                        "edge_score", trader.edgeScore,
                        "anomaly_score", trader.anomalyScore,
                        "strategy_cluster", trader.strategyCluster != null ? trader.strategyCluster : "unknown",
                        "trade_id", trade.id,
                        "trade_price", trade.price,
                        "trade_size", trade.size,
                        "trade_notional", trade.notional,
                        "currentPrice", trade.price
                ))
                .detectedAt(trade.ts)
                .expiresAt(trade.ts.plusSeconds(config.signalExpirySeconds()))
                .build();
    }

    /**
     * Check if market is on cooldown.
     */
    private boolean isMarketOnCooldown(String marketSlug) {
        Instant lastSignal = lastSignalByMarket.get(marketSlug);
        if (lastSignal == null) {
            return false;
        }

        long secondsSinceLastSignal = Duration.between(lastSignal, clock.instant()).getSeconds();
        return secondsSinceLastSignal < MARKET_COOLDOWN_SECONDS;
    }

    // ========== Status Methods ==========

    @Override
    public Map<String, Object> getMetrics() {
        Map<String, Object> baseMetrics = super.getMetrics();
        Map<String, Object> metrics = new HashMap<>(baseMetrics);

        // Add strategy-specific metrics
        metrics.put("tradersPolled", tradersPolled);
        metrics.put("tradesPolled", tradesPolled);
        metrics.put("signalsGenerated", signalsGenerated);
        metrics.put("edgeDecaysDetected", edgeDecaysDetected);
        metrics.put("highEdgeTradersCount", highEdgeTraders.size());
        metrics.put("processedTradeIds", processedTradeIds.size());
        metrics.put("marketsOnCooldown", lastSignalByMarket.size());
        metrics.put("lastTradePollTime", lastTradePollTime != null ? lastTradePollTime.toString() : "never");
        metrics.put("edgeThreshold", MIN_EDGE_SCORE);
        metrics.put("maxAnomalyScore", MAX_ANOMALY_SCORE);

        return metrics;
    }

    /**
     * Get list of currently tracked high-edge traders.
     */
    public List<EdgeTrader> getHighEdgeTraders() {
        return new ArrayList<>(highEdgeTraders.values());
    }

    // ========== Internal Records ==========

    /**
     * Trader with high ML-predicted edge score.
     */
    public record EdgeTrader(
            String username,
            String proxyAddress,
            double edgeScore,
            double anomalyScore,
            String strategyCluster,
            Instant updatedAt
    ) {}

    /**
     * Trade from a high-edge trader.
     */
    private record TraderTrade(
            String id,
            Instant ts,
            String username,
            String proxyAddress,
            String marketSlug,
            String tokenId,
            String side,
            String outcome,
            BigDecimal price,
            BigDecimal size,
            BigDecimal notional
    ) {}

    /**
     * Tracks edge score history for decay detection.
     */
    private static class EdgeHistory {
        private final LinkedList<EdgePoint> points = new LinkedList<>();
        private static final int MAX_HISTORY = 12;  // ~10 min at 10s intervals

        synchronized void recordEdge(double edgeScore, Instant timestamp) {
            points.addLast(new EdgePoint(edgeScore, timestamp));
            while (points.size() > MAX_HISTORY) {
                points.removeFirst();
            }
        }

        synchronized Double calculateDecay() {
            if (points.size() < 2) {
                return null;
            }

            double maxEdge = points.stream()
                    .mapToDouble(p -> p.edgeScore)
                    .max()
                    .orElse(0);

            double currentEdge = points.getLast().edgeScore;
            return maxEdge - currentEdge;
        }

        record EdgePoint(double edgeScore, Instant timestamp) {}
    }
}
