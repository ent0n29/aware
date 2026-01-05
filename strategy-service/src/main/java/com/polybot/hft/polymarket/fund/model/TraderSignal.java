package com.polybot.hft.polymarket.fund.model;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;

/**
 * A trading signal detected from a tracked trader.
 *
 * When a trader in the index executes a trade, this signal is generated
 * and queued for the fund to process.
 */
public record TraderSignal(
        String signalId,
        String username,           // Trader who made the trade
        String marketSlug,         // Market identifier (e.g., "btc-100k-2025")
        String tokenId,            // Specific outcome token
        String outcome,            // "Yes" or "No"
        SignalType type,           // BUY, SELL, or CLOSE
        BigDecimal shares,         // Size of trader's trade
        BigDecimal price,          // Execution price
        BigDecimal notionalUsd,    // USD value of trade
        Instant detectedAt,        // When we detected this trade
        Instant traderExecutedAt,  // When trader actually executed
        double traderWeight        // Trader's weight in the index at signal time
) {

    public enum SignalType {
        BUY,    // Trader opened or increased position
        SELL,   // Trader reduced position (partial)
        CLOSE   // Trader closed position entirely
    }

    /**
     * Calculate the fund's target trade size based on this signal.
     */
    public BigDecimal fundTargetShares(BigDecimal fundCapitalUsd, BigDecimal traderCapitalUsd) {
        if (traderCapitalUsd == null || traderCapitalUsd.compareTo(BigDecimal.ZERO) <= 0) {
            // If we don't know trader's capital, use weight-based sizing
            return shares.multiply(BigDecimal.valueOf(traderWeight));
        }

        // Scale by capital ratio: (fundCapital / traderCapital) * shares * weight
        BigDecimal capitalRatio = fundCapitalUsd.divide(traderCapitalUsd, 4, RoundingMode.HALF_UP);
        return shares.multiply(capitalRatio).multiply(BigDecimal.valueOf(traderWeight));
    }
}
