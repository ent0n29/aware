package com.polybot.hft.polymarket.fund.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.util.HashMap;
import java.util.Map;

/**
 * Multi-fund configuration properties.
 *
 * Allows running ALL fund strategies simultaneously with individual
 * enable/disable and capital allocation per fund.
 *
 * YAML Configuration:
 * <pre>
 * hft:
 *   multi-fund:
 *     enabled: true
 *     total-capital-usd: 50000
 *     funds:
 *       PSI-10:
 *         enabled: true
 *         capital-pct: 30
 *       PSI-SPORTS:
 *         enabled: true
 *         capital-pct: 10
 *       ALPHA-INSIDER:
 *         enabled: true
 *         capital-pct: 20
 *       ALPHA-EDGE:
 *         enabled: true
 *         capital-pct: 20
 *       ALPHA-ARB:
 *         enabled: true
 *         capital-pct: 20
 * </pre>
 */
@Data
@Component
@ConfigurationProperties(prefix = "hft.multi-fund")
public class MultiFundProperties {

    /**
     * Master switch to enable multi-fund mode.
     * When true, ALL configured funds run simultaneously.
     */
    private boolean enabled = false;

    /**
     * Total capital pool in USD.
     * Individual fund allocations are percentages of this.
     */
    private BigDecimal totalCapitalUsd = BigDecimal.valueOf(10000);

    /**
     * Per-fund configurations.
     * Key = fund type ID (e.g., "PSI-10", "ALPHA-ARB")
     */
    private Map<String, FundAllocation> funds = new HashMap<>();

    /**
     * Individual fund allocation configuration.
     */
    @Data
    public static class FundAllocation {
        /**
         * Whether this fund is enabled.
         */
        private boolean enabled = true;

        /**
         * Percentage of total capital allocated to this fund (0-100).
         */
        private double capitalPct = 10.0;

        /**
         * Override: specific capital amount in USD.
         * If set, overrides capitalPct.
         */
        private BigDecimal capitalUsd;

        /**
         * Max position size as percentage of fund capital.
         */
        private double maxPositionPct = 0.10;

        /**
         * Minimum trade size in USD.
         */
        private BigDecimal minTradeUsd = BigDecimal.valueOf(5);

        /**
         * Calculate actual capital allocation.
         */
        public BigDecimal getEffectiveCapital(BigDecimal totalCapital) {
            if (capitalUsd != null && capitalUsd.compareTo(BigDecimal.ZERO) > 0) {
                return capitalUsd;
            }
            return totalCapital.multiply(BigDecimal.valueOf(capitalPct / 100.0));
        }
    }

    /**
     * Get effective capital for a specific fund.
     */
    public BigDecimal getFundCapital(String fundType) {
        FundAllocation allocation = funds.get(fundType);
        if (allocation == null) {
            // Default: equal split
            int numFunds = Math.max(1, funds.size());
            return totalCapitalUsd.divide(BigDecimal.valueOf(numFunds), 2, java.math.RoundingMode.HALF_UP);
        }
        return allocation.getEffectiveCapital(totalCapitalUsd);
    }

    /**
     * Check if a specific fund is enabled.
     */
    public boolean isFundEnabled(String fundType) {
        if (!enabled) {
            return false;
        }
        FundAllocation allocation = funds.get(fundType);
        return allocation != null && allocation.isEnabled();
    }

    /**
     * Create default configuration with all funds enabled at equal allocation.
     */
    public static MultiFundProperties defaults() {
        MultiFundProperties props = new MultiFundProperties();
        props.setEnabled(true);
        props.setTotalCapitalUsd(BigDecimal.valueOf(10000));

        // Default allocations (20% each for 5 fund types)
        String[] fundTypes = {"PSI-10", "ALPHA-INSIDER", "ALPHA-EDGE", "ALPHA-ARB"};
        for (String fundType : fundTypes) {
            FundAllocation alloc = new FundAllocation();
            alloc.setEnabled(true);
            alloc.setCapitalPct(25.0);  // 25% each for 4 funds
            props.getFunds().put(fundType, alloc);
        }

        return props;
    }
}
