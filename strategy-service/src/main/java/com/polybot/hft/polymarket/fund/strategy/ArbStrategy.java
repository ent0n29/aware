package com.polybot.hft.polymarket.fund.strategy;

import com.polybot.hft.polymarket.fund.config.ActiveFundConfig;
import com.polybot.hft.polymarket.fund.model.AlphaSignal;
import com.polybot.hft.polymarket.ws.ClobMarketWebSocketClient;
import com.polybot.hft.polymarket.ws.TopOfBook;
import com.polybot.hft.strategy.executor.ExecutorApiClient;
import io.micrometer.core.instrument.MeterRegistry;
import lombok.extern.slf4j.Slf4j;
import org.springframework.jdbc.core.JdbcTemplate;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * ALPHA-ARB Fund Strategy.
 *
 * Complete-set arbitrage strategy that exploits pricing inefficiencies
 * in binary YES/NO markets on Polymarket.
 *
 * Core Concept:
 * In a binary market, YES + NO must sum to $1.00 at resolution.
 * If the current cost to buy both is less than $1.00, there's guaranteed profit.
 *
 * Edge Calculation:
 *   edge = 1.0 - (yesAskPrice + noAskPrice)
 *
 * Example:
 *   YES ask = $0.48, NO ask = $0.50
 *   Cost = $0.98, Edge = $0.02 (2%)
 *   Buy both -> guaranteed $1.00 at resolution -> 2% profit
 *
 * Risk Controls:
 * - Minimum edge threshold (covers fees + slippage)
 * - Maximum concurrent arb positions
 * - Maximum notional per arb trade
 * - Market validation (active, liquid, not near expiry)
 */
@Slf4j
public class ArbStrategy extends ActiveFundExecutor {

    private static final String FUND_TYPE = "ALPHA-ARB";

    // Arb thresholds (in decimal, e.g., 0.02 = 2%)
    private static final double MIN_ARB_EDGE = 0.02;  // 2% minimum edge
    private static final double IDEAL_ARB_EDGE = 0.03;  // 3% for high confidence
    private static final double MIN_LIQUIDITY_USD = 50.0;  // Minimum liquidity per side

    // Position limits
    private static final int MAX_CONCURRENT_ARB_POSITIONS = 5;
    private static final double MAX_ARB_NOTIONAL_USD = 100.0;  // Max per arb trade

    // Track active arb positions (marketSlug -> entry time)
    private final Map<String, ArbPosition> activeArbPositions = new ConcurrentHashMap<>();

    // Track detected opportunities for deduplication
    private final Set<String> recentOpportunities = ConcurrentHashMap.newKeySet();

    // Metrics
    private long opportunitiesDetected = 0;
    private long arbsExecuted = 0;
    private long arbsSkipped = 0;
    private double totalEdgeCaptured = 0.0;

    // WebSocket client for real-time prices
    private final ClobMarketWebSocketClient marketWs;

    public ArbStrategy(
            ActiveFundConfig config,
            ExecutorApiClient executorApi,
            JdbcTemplate jdbcTemplate,
            Clock clock,
            MeterRegistry meterRegistry,
            ClobMarketWebSocketClient marketWs
    ) {
        super(config, executorApi, jdbcTemplate, clock, meterRegistry);
        this.marketWs = marketWs;
    }

    @Override
    public String getFundType() {
        return FUND_TYPE;
    }

    @Override
    protected void onStart() {
        super.onStart();
        log.info("ArbStrategy starting - minEdge: {}%, maxPositions: {}, maxNotional: ${}",
                MIN_ARB_EDGE * 100, MAX_CONCURRENT_ARB_POSITIONS, MAX_ARB_NOTIONAL_USD);
    }

    /**
     * Poll for arbitrage opportunities.
     *
     * Called periodically by scheduled task.
     */
    @Override
    public void pollForSignals() {
        if (!isEnabled()) {
            return;
        }

        try {
            // Check if we can take more positions
            if (activeArbPositions.size() >= MAX_CONCURRENT_ARB_POSITIONS) {
                log.debug("Max arb positions reached ({}), skipping scan", MAX_CONCURRENT_ARB_POSITIONS);
                return;
            }

            // Scan for opportunities
            List<ArbOpportunity> opportunities = scanForArbOpportunities();

            for (ArbOpportunity opp : opportunities) {
                try {
                    executeArbitrage(opp);
                } catch (Exception e) {
                    log.warn("Error executing arb on {}: {}", opp.marketSlug, e.getMessage());
                }
            }

        } catch (Exception e) {
            log.warn("Error scanning for arb opportunities: {}", e.getMessage());
        }
    }

    /**
     * Scan ClickHouse for binary markets and check for arb opportunities.
     */
    private List<ArbOpportunity> scanForArbOpportunities() {
        List<ArbOpportunity> opportunities = new ArrayList<>();

        // Query for active binary markets with their token pairs
        // Uses gamma_markets_latest which has: slug, token_ids (array), end_date, active, volume_num
        String sql = """
            SELECT DISTINCT
                m.slug as market_slug,
                m.slug as question,
                m.token_ids[1] as yes_token_id,
                m.token_ids[2] as no_token_id,
                m.end_date
            FROM polybot.gamma_markets_latest m
            WHERE m.active = 1
              AND length(m.token_ids) >= 2
              AND m.end_date > now()
              AND m.end_date < now() + INTERVAL 7 DAY
            ORDER BY m.volume_num DESC
            LIMIT 50
            """;

        try {
            List<MarketInfo> markets = jdbcTemplate.query(sql, (rs, rowNum) -> new MarketInfo(
                    rs.getString("market_slug"),
                    rs.getString("question"),
                    rs.getString("yes_token_id"),
                    rs.getString("no_token_id"),
                    rs.getTimestamp("end_date").toInstant()
            ));

            for (MarketInfo market : markets) {
                // Skip if already have position in this market
                if (activeArbPositions.containsKey(market.marketSlug)) {
                    continue;
                }

                // Skip if recently processed
                if (recentOpportunities.contains(market.marketSlug)) {
                    continue;
                }

                // Get current prices from WebSocket
                Optional<TopOfBook> yesBook = marketWs.getTopOfBook(market.yesTokenId);
                Optional<TopOfBook> noBook = marketWs.getTopOfBook(market.noTokenId);

                if (yesBook.isEmpty() || noBook.isEmpty()) {
                    continue;
                }

                TopOfBook yes = yesBook.get();
                TopOfBook no = noBook.get();

                // Check liquidity
                BigDecimal minLiquidity = BigDecimal.valueOf(MIN_LIQUIDITY_USD);
                if (yes.bestAskSize().compareTo(minLiquidity) < 0 ||
                    no.bestAskSize().compareTo(minLiquidity) < 0) {
                    continue;
                }

                // Calculate edge: edge = 1.0 - (yesAsk + noAsk)
                BigDecimal yesAsk = yes.bestAsk();
                BigDecimal noAsk = no.bestAsk();
                BigDecimal totalCost = yesAsk.add(noAsk);
                BigDecimal edge = BigDecimal.ONE.subtract(totalCost);

                if (edge.compareTo(BigDecimal.valueOf(MIN_ARB_EDGE)) >= 0) {
                    opportunitiesDetected++;
                    BigDecimal availableLiquidity = yes.bestAskSize().min(no.bestAskSize());
                    opportunities.add(new ArbOpportunity(
                            market.marketSlug,
                            market.question,
                            market.yesTokenId,
                            market.noTokenId,
                            yesAsk.doubleValue(),
                            noAsk.doubleValue(),
                            edge.doubleValue(),
                            availableLiquidity.doubleValue(),
                            market.endDate
                    ));

                    log.info("ARB OPPORTUNITY: {} - Edge: {}%, YES: ${}, NO: ${}",
                            market.marketSlug,
                            String.format("%.2f", edge.doubleValue() * 100),
                            yesAsk, noAsk);
                }
            }

        } catch (Exception e) {
            log.warn("Error querying markets for arb scan: {}", e.getMessage());
        }

        return opportunities;
    }

    /**
     * Execute an arbitrage opportunity by buying both YES and NO tokens.
     */
    private void executeArbitrage(ArbOpportunity opp) {
        // Validate opportunity is still valid
        if (opp.edge < MIN_ARB_EDGE) {
            log.debug("Edge dropped below threshold for {}", opp.marketSlug);
            arbsSkipped++;
            return;
        }

        // Calculate position size (limited by liquidity and max notional)
        double maxByLiquidity = opp.availableLiquidity * 0.5;  // Take 50% of available
        double positionSizePerSide = Math.min(MAX_ARB_NOTIONAL_USD / 2, maxByLiquidity);

        if (positionSizePerSide < 10.0) {
            log.debug("Position too small for {}: ${}", opp.marketSlug, positionSizePerSide);
            arbsSkipped++;
            return;
        }

        // Calculate confidence based on edge size
        double confidence = Math.min(0.95, 0.5 + (opp.edge / IDEAL_ARB_EDGE) * 0.45);

        // Create signals for both sides
        String arbId = UUID.randomUUID().toString();

        AlphaSignal yesSignal = AlphaSignal.builder()
                .signalId(arbId + "-YES")
                .source(AlphaSignal.SignalSource.ARBITRAGE)
                .action(AlphaSignal.SignalAction.BUY)
                .marketSlug(opp.marketSlug)
                .tokenId(opp.yesTokenId)
                .outcome("Yes")
                .confidence(confidence)
                .strength(opp.edge / MIN_ARB_EDGE)  // Strength = edge ratio
                .urgency(AlphaSignal.SignalUrgency.HIGH)  // Arb opportunities are time-sensitive
                .suggestedSizeUsd(BigDecimal.valueOf(positionSizePerSide))
                .reason(String.format("ARB: Edge %.2f%% - YES@$%.2f + NO@$%.2f",
                        opp.edge * 100, opp.yesAsk, opp.noAsk))
                .metadata(Map.of(
                        "arb_id", arbId,
                        "arb_side", "YES",
                        "edge", opp.edge,
                        "counterpart_token", opp.noTokenId
                ))
                .detectedAt(clock.instant())
                .expiresAt(clock.instant().plusSeconds(60))  // 1 minute expiry
                .build();

        AlphaSignal noSignal = AlphaSignal.builder()
                .signalId(arbId + "-NO")
                .source(AlphaSignal.SignalSource.ARBITRAGE)
                .action(AlphaSignal.SignalAction.BUY)
                .marketSlug(opp.marketSlug)
                .tokenId(opp.noTokenId)
                .outcome("No")
                .confidence(confidence)
                .strength(opp.edge / MIN_ARB_EDGE)
                .urgency(AlphaSignal.SignalUrgency.HIGH)
                .suggestedSizeUsd(BigDecimal.valueOf(positionSizePerSide))
                .reason(String.format("ARB: Edge %.2f%% - YES@$%.2f + NO@$%.2f",
                        opp.edge * 100, opp.yesAsk, opp.noAsk))
                .metadata(Map.of(
                        "arb_id", arbId,
                        "arb_side", "NO",
                        "edge", opp.edge,
                        "counterpart_token", opp.yesTokenId
                ))
                .detectedAt(clock.instant())
                .expiresAt(clock.instant().plusSeconds(60))
                .build();

        // Process both signals
        processSignal(yesSignal);
        processSignal(noSignal);

        // Track the position
        activeArbPositions.put(opp.marketSlug, new ArbPosition(
                arbId,
                opp.marketSlug,
                opp.edge,
                positionSizePerSide * 2,  // Total notional both sides
                clock.instant(),
                opp.endDate
        ));

        // Mark as recently processed (prevent duplicate signals)
        recentOpportunities.add(opp.marketSlug);

        // Cleanup old entries periodically
        if (recentOpportunities.size() > 100) {
            recentOpportunities.clear();
        }

        arbsExecuted++;
        totalEdgeCaptured += opp.edge * positionSizePerSide * 2;

        log.info("ARB EXECUTED: {} - Edge: {}%, Size: ${}, Expected Profit: ${}",
                opp.marketSlug,
                String.format("%.2f", opp.edge * 100),
                String.format("%.0f", positionSizePerSide * 2),
                String.format("%.2f", opp.edge * positionSizePerSide * 2));
    }

    /**
     * Check for completed/resolved arb positions.
     * Called periodically to update metrics.
     */
    public void checkResolvedPositions() {
        Instant now = clock.instant();
        Iterator<Map.Entry<String, ArbPosition>> iter = activeArbPositions.entrySet().iterator();

        while (iter.hasNext()) {
            Map.Entry<String, ArbPosition> entry = iter.next();
            ArbPosition pos = entry.getValue();

            // Check if market has resolved (past end date)
            if (pos.endDate.isBefore(now)) {
                log.info("ARB RESOLVED: {} - Expected profit: ${}",
                        pos.marketSlug, String.format("%.2f", pos.edge * pos.notional));
                iter.remove();
            }
        }
    }

    // ========== Status Methods ==========

    @Override
    public Map<String, Object> getMetrics() {
        Map<String, Object> baseMetrics = super.getMetrics();
        Map<String, Object> metrics = new HashMap<>(baseMetrics);

        // Add strategy-specific metrics
        metrics.put("opportunitiesDetected", opportunitiesDetected);
        metrics.put("arbsExecuted", arbsExecuted);
        metrics.put("arbsSkipped", arbsSkipped);
        metrics.put("activeArbPositions", activeArbPositions.size());
        metrics.put("totalEdgeCaptured", String.format("$%.2f", totalEdgeCaptured));
        metrics.put("minEdgeThreshold", MIN_ARB_EDGE * 100 + "%");

        return metrics;
    }

    // ========== Internal Records ==========

    private record MarketInfo(
            String marketSlug,
            String question,
            String yesTokenId,
            String noTokenId,
            Instant endDate
    ) {}

    private record ArbOpportunity(
            String marketSlug,
            String question,
            String yesTokenId,
            String noTokenId,
            double yesAsk,
            double noAsk,
            double edge,
            double availableLiquidity,
            Instant endDate
    ) {}

    private record ArbPosition(
            String arbId,
            String marketSlug,
            double edge,
            double notional,
            Instant entryTime,
            Instant endDate
    ) {}
}
