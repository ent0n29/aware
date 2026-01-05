package com.polybot.hft.polymarket.fund.model;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * A trader who is part of a PSI index (e.g., PSI-10).
 *
 * Contains the trader's weight and capital for position sizing.
 */
public record IndexConstituent(
        String username,           // Trader's pseudonym on Polymarket
        String proxyAddress,       // Trader's wallet address
        double weight,             // Weight in index (0.0 - 1.0, sums to 1.0)
        int rank,                  // Rank in index (1 = top)
        BigDecimal estimatedCapitalUsd,  // Estimated trader capital for sizing
        double smartMoneyScore,    // SMS from scoring pipeline
        String strategyType,       // DIRECTIONAL, ARBITRAGEUR, etc.
        Instant lastTradeAt,       // Last trade timestamp
        Instant indexedAt          // When added to index
) {

    /**
     * Create constituent from PSI index query result.
     */
    public static IndexConstituent fromIndexQuery(
            String username,
            String proxyAddress,
            double weight,
            int rank,
            BigDecimal estimatedCapital,
            double smartMoneyScore,
            String strategyType,
            Instant lastTradeAt
    ) {
        return new IndexConstituent(
                username,
                proxyAddress,
                weight,
                rank,
                estimatedCapital,
                smartMoneyScore,
                strategyType,
                lastTradeAt,
                Instant.now()
        );
    }

    /**
     * Check if this trader should be tracked for signal generation.
     */
    public boolean isActive() {
        // Consider trader active if they traded in last 7 days
        return lastTradeAt != null &&
               lastTradeAt.isAfter(Instant.now().minusSeconds(7 * 24 * 60 * 60));
    }

    /**
     * Calculate the fund's target position size for a given trade.
     *
     * @param traderShares Shares the trader bought/sold
     * @param fundCapitalUsd Total fund capital
     * @return Target shares for fund to trade
     */
    public BigDecimal calculateFundShares(BigDecimal traderShares, BigDecimal fundCapitalUsd) {
        if (estimatedCapitalUsd == null || estimatedCapitalUsd.compareTo(BigDecimal.ZERO) <= 0) {
            // Unknown capital: use weight-based sizing
            return traderShares.multiply(BigDecimal.valueOf(weight));
        }

        // Capital-proportional sizing: (fundCapital / traderCapital) * shares * weight
        BigDecimal capitalRatio = fundCapitalUsd.divide(
                estimatedCapitalUsd, 4, java.math.RoundingMode.HALF_UP);
        return traderShares
                .multiply(capitalRatio)
                .multiply(BigDecimal.valueOf(weight));
    }
}
