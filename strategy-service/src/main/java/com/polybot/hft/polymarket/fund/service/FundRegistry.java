package com.polybot.hft.polymarket.fund.service;

import com.polybot.hft.polymarket.fund.model.FundType;
import lombok.extern.slf4j.Slf4j;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Registry for managing active fund instances.
 *
 * Tracks:
 * - Active funds and their types
 * - Capital allocation
 * - Performance metrics
 */
@Slf4j
public class FundRegistry {

    private final Map<String, FundInstance> activeFunds = new ConcurrentHashMap<>();

    /**
     * Register a new fund instance.
     */
    public void registerFund(String fundId, FundType type, BigDecimal capitalUsd) {
        if (activeFunds.containsKey(fundId)) {
            throw new IllegalStateException("Fund already registered: " + fundId);
        }

        FundInstance instance = new FundInstance(
                fundId,
                type,
                capitalUsd,
                BigDecimal.ZERO,
                BigDecimal.ZERO,
                0,
                Instant.now()
        );

        activeFunds.put(fundId, instance);
        log.info("Registered fund: {} ({}) with ${} capital",
                fundId, type.getId(), capitalUsd);
    }

    /**
     * Get a fund instance by ID.
     */
    public Optional<FundInstance> getFund(String fundId) {
        return Optional.ofNullable(activeFunds.get(fundId));
    }

    /**
     * Get all active funds.
     */
    public Collection<FundInstance> getAllFunds() {
        return Collections.unmodifiableCollection(activeFunds.values());
    }

    /**
     * Get all mirror funds (PSI index funds).
     */
    public List<FundInstance> getMirrorFunds() {
        return activeFunds.values().stream()
                .filter(f -> f.type().isMirrorFund())
                .toList();
    }

    /**
     * Get all active strategy funds (ALPHA funds).
     */
    public List<FundInstance> getActiveFunds() {
        return activeFunds.values().stream()
                .filter(f -> f.type().isActiveFund())
                .toList();
    }

    /**
     * Update fund performance metrics.
     */
    public void updatePerformance(String fundId, BigDecimal realizedPnl,
                                  BigDecimal unrealizedPnl, int openPositions) {
        FundInstance existing = activeFunds.get(fundId);
        if (existing == null) {
            log.warn("Cannot update unknown fund: {}", fundId);
            return;
        }

        FundInstance updated = new FundInstance(
                existing.fundId(),
                existing.type(),
                existing.capitalUsd(),
                realizedPnl,
                unrealizedPnl,
                openPositions,
                existing.startedAt()
        );

        activeFunds.put(fundId, updated);
    }

    /**
     * Check if a fund is active.
     */
    public boolean isActive(String fundId) {
        return activeFunds.containsKey(fundId);
    }

    /**
     * Deactivate a fund.
     */
    public void deactivateFund(String fundId) {
        FundInstance removed = activeFunds.remove(fundId);
        if (removed != null) {
            log.info("Deactivated fund: {}", fundId);
        }
    }

    /**
     * Get aggregate metrics across all funds.
     */
    public AggregateMetrics getAggregateMetrics() {
        BigDecimal totalCapital = BigDecimal.ZERO;
        BigDecimal totalRealizedPnl = BigDecimal.ZERO;
        BigDecimal totalUnrealizedPnl = BigDecimal.ZERO;
        int totalOpenPositions = 0;

        for (FundInstance fund : activeFunds.values()) {
            totalCapital = totalCapital.add(fund.capitalUsd());
            totalRealizedPnl = totalRealizedPnl.add(fund.realizedPnl());
            totalUnrealizedPnl = totalUnrealizedPnl.add(fund.unrealizedPnl());
            totalOpenPositions += fund.openPositions();
        }

        return new AggregateMetrics(
                activeFunds.size(),
                totalCapital,
                totalRealizedPnl,
                totalUnrealizedPnl,
                totalOpenPositions
        );
    }

    /**
     * A registered fund instance.
     */
    public record FundInstance(
            String fundId,
            FundType type,
            BigDecimal capitalUsd,
            BigDecimal realizedPnl,
            BigDecimal unrealizedPnl,
            int openPositions,
            Instant startedAt
    ) {
        /**
         * Calculate total P&L (realized + unrealized).
         */
        public BigDecimal totalPnl() {
            return realizedPnl.add(unrealizedPnl);
        }

        /**
         * Calculate return percentage.
         */
        public double returnPct() {
            if (capitalUsd.compareTo(BigDecimal.ZERO) == 0) {
                return 0.0;
            }
            return totalPnl()
                    .divide(capitalUsd, 4, java.math.RoundingMode.HALF_UP)
                    .multiply(BigDecimal.valueOf(100))
                    .doubleValue();
        }

        /**
         * Calculate current NAV.
         */
        public BigDecimal nav() {
            return capitalUsd.add(totalPnl());
        }
    }

    /**
     * Aggregate metrics across all funds.
     */
    public record AggregateMetrics(
            int activeFunds,
            BigDecimal totalCapital,
            BigDecimal totalRealizedPnl,
            BigDecimal totalUnrealizedPnl,
            int totalOpenPositions
    ) {
        public BigDecimal totalPnl() {
            return totalRealizedPnl.add(totalUnrealizedPnl);
        }

        public BigDecimal totalNav() {
            return totalCapital.add(totalPnl());
        }
    }
}
