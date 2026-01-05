package com.polybot.hft.polymarket.fund.model;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * Represents a position held by the fund in a specific market/outcome.
 *
 * Tracks:
 * - Original signal that triggered the position
 * - Current shares held and average cost
 * - Realized and unrealized P&L
 */
public record FundPosition(
        String positionId,
        String marketSlug,
        String tokenId,
        String outcome,            // "Yes" or "No"
        BigDecimal shares,         // Current shares held
        BigDecimal avgCostBasis,   // Average price paid
        BigDecimal realizedPnl,    // P&L from closed portions
        Instant openedAt,
        Instant lastUpdatedAt,
        String originSignalId      // TraderSignal that opened this
) {

    /**
     * Open a new position from a trader signal.
     */
    public static FundPosition open(
            String positionId,
            TraderSignal signal,
            BigDecimal executedShares,
            BigDecimal executedPrice,
            Instant now
    ) {
        return new FundPosition(
                positionId,
                signal.marketSlug(),
                signal.tokenId(),
                signal.outcome(),
                executedShares,
                executedPrice,
                BigDecimal.ZERO,
                now,
                now,
                signal.signalId()
        );
    }

    /**
     * Add to an existing position.
     */
    public FundPosition add(BigDecimal addedShares, BigDecimal addedPrice, Instant now) {
        // Calculate new average cost basis
        BigDecimal totalCost = shares.multiply(avgCostBasis)
                .add(addedShares.multiply(addedPrice));
        BigDecimal newShares = shares.add(addedShares);
        BigDecimal newAvgCost = totalCost.divide(newShares, 6, java.math.RoundingMode.HALF_UP);

        return new FundPosition(
                positionId,
                marketSlug,
                tokenId,
                outcome,
                newShares,
                newAvgCost,
                realizedPnl,
                openedAt,
                now,
                originSignalId
        );
    }

    /**
     * Reduce position and realize P&L.
     */
    public FundPosition reduce(BigDecimal reducedShares, BigDecimal sellPrice, Instant now) {
        BigDecimal pnl = reducedShares.multiply(sellPrice.subtract(avgCostBasis));
        BigDecimal newShares = shares.subtract(reducedShares);

        return new FundPosition(
                positionId,
                marketSlug,
                tokenId,
                outcome,
                newShares,
                avgCostBasis,  // Average cost doesn't change on reduction
                realizedPnl.add(pnl),
                openedAt,
                now,
                originSignalId
        );
    }

    /**
     * Calculate unrealized P&L at a given mark price.
     */
    public BigDecimal unrealizedPnl(BigDecimal markPrice) {
        return shares.multiply(markPrice.subtract(avgCostBasis));
    }

    /**
     * Total P&L (realized + unrealized at mark).
     */
    public BigDecimal totalPnl(BigDecimal markPrice) {
        return realizedPnl.add(unrealizedPnl(markPrice));
    }

    /**
     * Check if position is closed.
     */
    public boolean isClosed() {
        return shares.compareTo(BigDecimal.ZERO) <= 0;
    }

    /**
     * Current notional value at mark price.
     */
    public BigDecimal notionalValue(BigDecimal markPrice) {
        return shares.multiply(markPrice);
    }
}
