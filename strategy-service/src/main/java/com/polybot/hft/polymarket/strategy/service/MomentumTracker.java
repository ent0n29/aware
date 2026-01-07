package com.polybot.hft.polymarket.strategy.service;

import com.polybot.hft.polymarket.ws.TopOfBook;
import lombok.extern.slf4j.Slf4j;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedList;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Tracks intra-market price momentum for 15-minute binary options.
 *
 * Based on analysis of gabagool22's 292,896 trades:
 * - When UP price RISES during market: UP wins 88% of the time
 * - When UP price FALLS during market: DOWN wins 85% of the time
 * - Strategy: Follow momentum within each market window
 *
 * This tracker monitors bid prices over time and signals momentum direction.
 */
@Slf4j
public class MomentumTracker {

    private static final Duration PRICE_HISTORY_WINDOW = Duration.ofMinutes(10);
    private static final int MIN_SAMPLES_FOR_SIGNAL = 3;
    private static final BigDecimal MOMENTUM_THRESHOLD = BigDecimal.valueOf(0.02); // 2 cents

    private final Clock clock;
    private final Map<String, PriceHistory> historyByMarket = new ConcurrentHashMap<>();

    public MomentumTracker(Clock clock) {
        this.clock = clock;
    }

    /**
     * Record current prices for a market.
     */
    public void recordPrices(String marketSlug, TopOfBook upBook, TopOfBook downBook) {
        if (marketSlug == null || upBook == null || downBook == null) return;

        BigDecimal upBid = upBook.bestBid();
        BigDecimal downBid = downBook.bestBid();
        if (upBid == null || downBid == null) return;

        Instant now = clock.instant();
        historyByMarket.compute(marketSlug, (k, prev) -> {
            PriceHistory history = prev != null ? prev : new PriceHistory();
            history.addSample(now, upBid, downBid);
            history.pruneOldSamples(now.minus(PRICE_HISTORY_WINDOW));
            return history;
        });
    }

    /**
     * Get the momentum signal for a market.
     *
     * @return MomentumSignal indicating price trend direction
     */
    public MomentumSignal getSignal(String marketSlug) {
        PriceHistory history = historyByMarket.get(marketSlug);
        if (history == null || history.samples.size() < MIN_SAMPLES_FOR_SIGNAL) {
            return MomentumSignal.NEUTRAL;
        }

        BigDecimal earlyUpPrice = history.getEarlyUpPrice();
        BigDecimal lateUpPrice = history.getLateUpPrice();

        if (earlyUpPrice == null || lateUpPrice == null) {
            return MomentumSignal.NEUTRAL;
        }

        BigDecimal priceChange = lateUpPrice.subtract(earlyUpPrice);

        if (priceChange.compareTo(MOMENTUM_THRESHOLD) > 0) {
            return MomentumSignal.UP_RISING;
        } else if (priceChange.compareTo(MOMENTUM_THRESHOLD.negate()) < 0) {
            return MomentumSignal.UP_FALLING;
        } else {
            return MomentumSignal.NEUTRAL;
        }
    }

    /**
     * Get detailed momentum metrics for a market.
     */
    public MomentumMetrics getMetrics(String marketSlug) {
        PriceHistory history = historyByMarket.get(marketSlug);
        if (history == null || history.samples.isEmpty()) {
            return new MomentumMetrics(
                    MomentumSignal.NEUTRAL,
                    BigDecimal.ZERO,
                    BigDecimal.ZERO,
                    BigDecimal.ZERO,
                    BigDecimal.ZERO,
                    0
            );
        }

        BigDecimal earlyUpPrice = history.getEarlyUpPrice();
        BigDecimal lateUpPrice = history.getLateUpPrice();
        BigDecimal priceChange = (earlyUpPrice != null && lateUpPrice != null)
                ? lateUpPrice.subtract(earlyUpPrice)
                : BigDecimal.ZERO;

        return new MomentumMetrics(
                getSignal(marketSlug),
                earlyUpPrice != null ? earlyUpPrice : BigDecimal.ZERO,
                lateUpPrice != null ? lateUpPrice : BigDecimal.ZERO,
                priceChange,
                history.getAvgUpPrice(),
                history.samples.size()
        );
    }

    /**
     * Calculate the recommended position bias based on momentum.
     *
     * Returns a value between -1.0 (strong LONG_DOWN) and 1.0 (strong LONG_UP).
     * - Positive: favor UP position
     * - Negative: favor DOWN position
     * - Near zero: balanced
     */
    public double getPositionBias(String marketSlug) {
        MomentumSignal signal = getSignal(marketSlug);

        return switch (signal) {
            case UP_RISING -> 0.65;   // Strong bias toward LONG_UP (matches gab's 65.8% accuracy when LONG_UP)
            case UP_FALLING -> -0.57; // Strong bias toward LONG_DOWN (matches gab's 57% accuracy)
            case NEUTRAL -> 0.0;      // Balanced - use random or slight bias
        };
    }

    /**
     * Check if momentum has flipped since last check.
     */
    public boolean hasMomentumFlipped(String marketSlug, MomentumSignal previousSignal) {
        MomentumSignal current = getSignal(marketSlug);
        if (previousSignal == null || previousSignal == MomentumSignal.NEUTRAL) {
            return false;
        }
        if (current == MomentumSignal.NEUTRAL) {
            return false;
        }
        // Flip is when we go from UP_RISING to UP_FALLING or vice versa
        return (previousSignal == MomentumSignal.UP_RISING && current == MomentumSignal.UP_FALLING)
                || (previousSignal == MomentumSignal.UP_FALLING && current == MomentumSignal.UP_RISING);
    }

    /**
     * Clean up expired markets.
     */
    public void pruneExpiredMarkets(Instant cutoff) {
        historyByMarket.entrySet().removeIf(entry ->
                entry.getValue().getLastSampleTime() != null
                        && entry.getValue().getLastSampleTime().isBefore(cutoff)
        );
    }

    public void removeMarket(String marketSlug) {
        historyByMarket.remove(marketSlug);
    }

    // ========== Inner Classes ==========

    public enum MomentumSignal {
        UP_RISING,   // UP price is rising -> 88% chance UP wins
        UP_FALLING,  // UP price is falling -> 85% chance DOWN wins
        NEUTRAL      // No clear trend
    }

    public record MomentumMetrics(
            MomentumSignal signal,
            BigDecimal earlyUpPrice,
            BigDecimal lateUpPrice,
            BigDecimal priceChange,
            BigDecimal avgUpPrice,
            int sampleCount
    ) {}

    private static class PriceHistory {
        private final LinkedList<PriceSample> samples = new LinkedList<>();

        void addSample(Instant time, BigDecimal upBid, BigDecimal downBid) {
            samples.addLast(new PriceSample(time, upBid, downBid));
        }

        void pruneOldSamples(Instant cutoff) {
            while (!samples.isEmpty() && samples.peekFirst().time.isBefore(cutoff)) {
                samples.removeFirst();
            }
        }

        BigDecimal getEarlyUpPrice() {
            if (samples.size() < 2) return null;
            // Average of first 1/3 of samples
            int earlyCount = Math.max(1, samples.size() / 3);
            BigDecimal sum = BigDecimal.ZERO;
            int count = 0;
            for (PriceSample sample : samples) {
                if (count >= earlyCount) break;
                sum = sum.add(sample.upBid);
                count++;
            }
            return count > 0 ? sum.divide(BigDecimal.valueOf(count), 4, RoundingMode.HALF_UP) : null;
        }

        BigDecimal getLateUpPrice() {
            if (samples.size() < 2) return null;
            // Average of last 1/3 of samples
            int lateCount = Math.max(1, samples.size() / 3);
            int skipCount = samples.size() - lateCount;
            BigDecimal sum = BigDecimal.ZERO;
            int count = 0;
            int idx = 0;
            for (PriceSample sample : samples) {
                if (idx >= skipCount) {
                    sum = sum.add(sample.upBid);
                    count++;
                }
                idx++;
            }
            return count > 0 ? sum.divide(BigDecimal.valueOf(count), 4, RoundingMode.HALF_UP) : null;
        }

        BigDecimal getAvgUpPrice() {
            if (samples.isEmpty()) return BigDecimal.ZERO;
            BigDecimal sum = BigDecimal.ZERO;
            for (PriceSample sample : samples) {
                sum = sum.add(sample.upBid);
            }
            return sum.divide(BigDecimal.valueOf(samples.size()), 4, RoundingMode.HALF_UP);
        }

        Instant getLastSampleTime() {
            return samples.isEmpty() ? null : samples.peekLast().time;
        }
    }

    private record PriceSample(Instant time, BigDecimal upBid, BigDecimal downBid) {}
}
