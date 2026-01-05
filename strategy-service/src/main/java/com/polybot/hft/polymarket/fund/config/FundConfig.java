package com.polybot.hft.polymarket.fund.config;

import com.polybot.hft.config.HftProperties;

import java.math.BigDecimal;

/**
 * Fund configuration wrapper for AWARE Fund products.
 *
 * Wraps HftProperties.Fund into a more convenient form.
 */
public record FundConfig(
        boolean enabled,
        String indexType,
        BigDecimal capitalUsd,
        double maxPositionPct,
        BigDecimal minTradeUsd,
        int signalDelaySeconds,
        double maxSlippagePct,
        HftProperties.FundExecutionMode executionMode,
        RiskLimits riskLimits
) {

    public static FundConfig from(HftProperties.Fund fund) {
        return new FundConfig(
                fund.enabled(),
                fund.indexType(),
                fund.capitalUsd(),
                fund.maxPositionPct(),
                fund.minTradeUsd(),
                fund.signalDelaySeconds(),
                fund.maxSlippagePct(),
                fund.executionMode(),
                RiskLimits.from(fund.riskLimits())
        );
    }

    public static FundConfig defaults() {
        return new FundConfig(
                false,
                "PSI-10",
                BigDecimal.valueOf(10000),
                0.10,
                BigDecimal.valueOf(5),
                5,
                0.02,
                HftProperties.FundExecutionMode.LIMIT_THEN_MARKET,
                RiskLimits.defaults()
        );
    }

    /**
     * Check if this is a passive index fund (mirrors traders).
     */
    public boolean isMirrorFund() {
        return indexType != null && indexType.startsWith("PSI-");
    }

    /**
     * Check if this is an active alpha fund (runs strategy directly).
     */
    public boolean isAlphaFund() {
        return indexType != null && indexType.startsWith("ALPHA-");
    }

    /**
     * Risk limits sub-configuration.
     */
    public record RiskLimits(
            BigDecimal maxDailyLossUsd,
            double maxDrawdownPct,
            int maxOpenPositions,
            BigDecimal maxSingleMarketExposureUsd,
            boolean killSwitchActive
    ) {
        public static RiskLimits from(HftProperties.FundRiskLimits limits) {
            return new RiskLimits(
                    limits.maxDailyLossUsd(),
                    limits.maxDrawdownPct(),
                    limits.maxOpenPositions(),
                    limits.maxSingleMarketExposureUsd(),
                    limits.killSwitchActive()
            );
        }

        public static RiskLimits defaults() {
            return new RiskLimits(
                    BigDecimal.valueOf(500),
                    0.10,
                    50,
                    BigDecimal.valueOf(1000),
                    false
            );
        }
    }
}
