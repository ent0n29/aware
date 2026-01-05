package com.polybot.hft.polymarket.fund.config;

import com.polybot.hft.config.HftProperties;

import java.math.BigDecimal;

/**
 * Configuration specific to active alpha funds (ALPHA-*).
 *
 * Extends base FundConfig with alpha-specific parameters:
 * - Signal filtering thresholds
 * - Position sizing for active strategies
 * - Risk parameters for alpha generation
 */
public record ActiveFundConfig(
        // Base fund config
        boolean enabled,
        String fundType,                     // "ALPHA-INSIDER", "ALPHA-ARB", etc.
        BigDecimal capitalUsd,
        double maxPositionPct,
        BigDecimal minTradeUsd,
        double maxSlippagePct,
        HftProperties.FundExecutionMode executionMode,
        FundConfig.RiskLimits riskLimits,

        // Alpha-specific: Signal filtering
        double minConfidence,                // Minimum signal confidence (0-1)
        double minStrength,                  // Minimum signal strength
        int signalExpirySeconds,             // How long signals remain valid

        // Alpha-specific: Position sizing
        double basePositionPct,              // Base position size as % of capital
        double maxSinglePositionPct,         // Max for single position
        double confidenceScaling,            // Scale size by confidence (0=disabled)

        // Alpha-specific: Execution
        int executionDelayMillis,            // Delay before executing (anti-front-run)
        int maxConcurrentOrders,             // Max pending orders at once
        boolean useAggressiveExecution,      // Cross spread when urgency is HIGH

        // Alpha-specific: Risk
        int maxDailyTrades,                  // Max trades per day
        BigDecimal maxDailyNotionalUsd,      // Max daily notional traded
        double maxCorrelatedExposurePct      // Max exposure to correlated positions
) {

    /**
     * Create ActiveFundConfig from base FundConfig with alpha defaults.
     */
    public static ActiveFundConfig from(FundConfig base) {
        return new ActiveFundConfig(
                base.enabled(),
                base.indexType(),
                base.capitalUsd(),
                base.maxPositionPct(),
                base.minTradeUsd(),
                base.maxSlippagePct(),
                base.executionMode(),
                base.riskLimits(),
                // Alpha defaults
                0.6,              // minConfidence: 60%+
                0.5,              // minStrength
                300,              // signalExpirySeconds: 5 minutes
                0.02,             // basePositionPct: 2%
                0.10,             // maxSinglePositionPct: 10%
                0.5,              // confidenceScaling: moderate scaling
                100,              // executionDelayMillis: 100ms
                5,                // maxConcurrentOrders
                true,             // useAggressiveExecution
                100,              // maxDailyTrades
                base.capitalUsd().multiply(BigDecimal.valueOf(2)), // maxDailyNotionalUsd: 2x capital
                0.30              // maxCorrelatedExposurePct: 30%
        );
    }

    /**
     * Create default configuration for a given fund type.
     */
    public static ActiveFundConfig defaults(String fundType) {
        return new ActiveFundConfig(
                false,
                fundType,
                BigDecimal.valueOf(10000),
                0.10,
                BigDecimal.valueOf(5),
                0.02,
                HftProperties.FundExecutionMode.LIMIT_THEN_MARKET,
                FundConfig.RiskLimits.defaults(),
                // Alpha defaults
                0.6,
                0.5,
                300,
                0.02,
                0.10,
                0.5,
                100,
                5,
                true,
                100,
                BigDecimal.valueOf(20000),
                0.30
        );
    }

    /**
     * Create insider-optimized configuration.
     */
    public static ActiveFundConfig forInsiderStrategy(FundConfig base) {
        return new ActiveFundConfig(
                base.enabled(),
                "ALPHA-INSIDER",
                base.capitalUsd(),
                base.maxPositionPct(),
                base.minTradeUsd(),
                base.maxSlippagePct(),
                base.executionMode(),
                base.riskLimits(),
                // Insider-optimized: higher thresholds, faster execution
                0.70,             // minConfidence: 70%+ (more selective)
                0.6,              // minStrength: higher bar
                180,              // signalExpirySeconds: 3 minutes (faster decay)
                0.03,             // basePositionPct: 3% (slightly larger bets)
                0.15,             // maxSinglePositionPct: 15% (allow conviction plays)
                0.7,              // confidenceScaling: aggressive scaling by confidence
                50,               // executionDelayMillis: 50ms (faster)
                3,                // maxConcurrentOrders: fewer parallel
                true,             // useAggressiveExecution: cross spread on high confidence
                50,               // maxDailyTrades: fewer, higher quality
                base.capitalUsd().multiply(BigDecimal.valueOf(1.5)),
                0.25              // maxCorrelatedExposurePct: 25%
        );
    }

    /**
     * Create ML-edge-optimized configuration for ALPHA-EDGE fund.
     *
     * Tuned for following high-edge traders identified by ML models:
     * - Moderate confidence threshold (70%) based on edge_score/100
     * - Longer signal expiry (5 min) since ML scores update less frequently
     * - Conservative position sizing (2%) as we follow multiple traders
     * - Moderate execution delay (100ms) to avoid front-running detection
     */
    public static ActiveFundConfig forEdgeStrategy(FundConfig base) {
        return new ActiveFundConfig(
                base.enabled(),
                "ALPHA-EDGE",
                base.capitalUsd(),
                base.maxPositionPct(),
                base.minTradeUsd(),
                base.maxSlippagePct(),
                base.executionMode(),
                base.riskLimits(),
                // Edge-optimized: balanced thresholds, moderate execution
                0.70,             // minConfidence: 70%+ (based on edge_score >= 70)
                0.5,              // minStrength: moderate bar
                300,              // signalExpirySeconds: 5 minutes (longer for ML signals)
                0.02,             // basePositionPct: 2% (spread across traders)
                0.10,             // maxSinglePositionPct: 10% (diversified)
                0.5,              // confidenceScaling: moderate scaling
                100,              // executionDelayMillis: 100ms (balanced)
                5,                // maxConcurrentOrders: allow parallel
                true,             // useAggressiveExecution: cross spread on high edge
                75,               // maxDailyTrades: higher volume, more traders
                base.capitalUsd().multiply(BigDecimal.valueOf(2.0)),
                0.30              // maxCorrelatedExposurePct: 30% (more diversified)
        );
    }

    /**
     * Calculate position size for a given signal.
     *
     * @param confidence Signal confidence (0-1)
     * @param strength Signal strength
     * @return Position size in USD
     */
    public BigDecimal calculatePositionSize(double confidence, double strength) {
        // Base size
        BigDecimal baseSize = capitalUsd.multiply(BigDecimal.valueOf(basePositionPct));

        // Apply confidence scaling
        double scaleFactor = 1.0;
        if (confidenceScaling > 0) {
            // Scale between 0.5x and 2x based on confidence
            scaleFactor = 0.5 + (confidence * confidenceScaling * 3);
            scaleFactor = Math.min(2.0, Math.max(0.5, scaleFactor));
        }

        // Apply strength multiplier (0.5 to 1.5)
        double strengthMultiplier = 0.5 + (strength * 1.0);

        BigDecimal finalSize = baseSize
                .multiply(BigDecimal.valueOf(scaleFactor))
                .multiply(BigDecimal.valueOf(strengthMultiplier));

        // Cap at max single position
        BigDecimal maxPosition = capitalUsd.multiply(BigDecimal.valueOf(maxSinglePositionPct));
        if (finalSize.compareTo(maxPosition) > 0) {
            finalSize = maxPosition;
        }

        // Ensure minimum
        if (finalSize.compareTo(minTradeUsd) < 0) {
            return BigDecimal.ZERO;
        }

        return finalSize.setScale(2, java.math.RoundingMode.DOWN);
    }

    /**
     * Check if a signal passes the filtering thresholds.
     */
    public boolean passesFilter(double confidence, double strength) {
        return confidence >= minConfidence && strength >= minStrength;
    }
}
