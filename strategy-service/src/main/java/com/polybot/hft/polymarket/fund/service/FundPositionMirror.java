package com.polybot.hft.polymarket.fund.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.polybot.hft.domain.OrderSide;
import com.polybot.hft.polymarket.api.LimitOrderRequest;
import com.polybot.hft.polymarket.api.OrderSubmissionResult;
import com.polybot.hft.polymarket.fund.config.FundConfig;
import com.polybot.hft.polymarket.fund.model.FundPosition;
import com.polybot.hft.polymarket.fund.model.IndexConstituent;
import com.polybot.hft.polymarket.fund.model.TraderSignal;
import com.polybot.hft.strategy.executor.ExecutorApiClient;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import lombok.extern.slf4j.Slf4j;
import org.springframework.jdbc.core.JdbcTemplate;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentLinkedQueue;

/**
 * Core fund mirroring engine.
 *
 * When a tracked trader executes a trade:
 * 1. Signal is queued with anti-front-running delay
 * 2. After delay, position is sized based on fund capital / trader capital
 * 3. Order is submitted to executor with slippage protection
 * 4. Position is tracked for P&L attribution
 */
@Slf4j
public class FundPositionMirror {

    private final FundConfig config;
    private final IndexWeightProvider weightProvider;
    private final ExecutorApiClient executorApi;
    private final Clock clock;
    private final JdbcTemplate jdbcTemplate;

    // Pending signals waiting for delay to expire
    private final Queue<PendingSignal> pendingSignals = new ConcurrentLinkedQueue<>();

    // Active positions by tokenId
    private final Map<String, FundPosition> positions = new ConcurrentHashMap<>();

    // Metrics
    private int signalsProcessed = 0;
    private int ordersSubmitted = 0;
    private int ordersFailed = 0;

    // Prometheus metrics
    private final Counter signalsProcessedCounter;
    private final Counter ordersSubmittedCounter;
    private final Counter ordersFailedCounter;

    public FundPositionMirror(
            FundConfig config,
            IndexWeightProvider weightProvider,
            ExecutorApiClient executorApi,
            Clock clock,
            JdbcTemplate jdbcTemplate,
            MeterRegistry meterRegistry
    ) {
        this.config = config;
        this.weightProvider = weightProvider;
        this.executorApi = executorApi;
        this.clock = clock;
        this.jdbcTemplate = jdbcTemplate;

        // Initialize Prometheus metrics
        this.signalsProcessedCounter = Counter.builder("fund.signals.processed")
                .description("Total signals processed by position mirror")
                .tag("fund", config.indexType())
                .register(meterRegistry);

        this.ordersSubmittedCounter = Counter.builder("fund.orders.submitted")
                .description("Total orders submitted to executor")
                .tag("fund", config.indexType())
                .register(meterRegistry);

        this.ordersFailedCounter = Counter.builder("fund.orders.failed")
                .description("Total orders that failed submission")
                .tag("fund", config.indexType())
                .register(meterRegistry);

        // Register gauges for open positions and pending signals
        io.micrometer.core.instrument.Gauge.builder("fund.positions.open", positions, Map::size)
                .description("Number of open positions")
                .tag("fund", config.indexType())
                .register(meterRegistry);

        io.micrometer.core.instrument.Gauge.builder("fund.pending.signals", pendingSignals, Queue::size)
                .description("Number of pending signals in queue")
                .tag("fund", config.indexType())
                .register(meterRegistry);
    }

    /**
     * Queue a signal for processing after the anti-front-running delay.
     */
    public void queueSignal(TraderSignal signal) {
        Instant executeAt = clock.instant().plusSeconds(config.signalDelaySeconds());
        pendingSignals.add(new PendingSignal(signal, executeAt));
        log.info("Queued signal {} for {} at {} (delay {}s)",
                signal.signalId(), signal.username(), executeAt, config.signalDelaySeconds());
    }

    /**
     * Process any signals whose delay has expired.
     * Called by scheduled task every 100ms.
     */
    public void processPendingSignals() {
        Instant now = clock.instant();
        PendingSignal pending;

        while ((pending = pendingSignals.peek()) != null && pending.executeAt.isBefore(now)) {
            pendingSignals.poll();
            try {
                processSignal(pending.signal);
                signalsProcessed++;
                signalsProcessedCounter.increment();
            } catch (Exception e) {
                log.error("Failed to process signal {}: {}", pending.signal.signalId(), e.getMessage());
                ordersFailed++;
                ordersFailedCounter.increment();
            }
        }
    }

    /**
     * Process a single trader signal.
     */
    private void processSignal(TraderSignal signal) {
        // Check risk limits
        if (config.riskLimits().killSwitchActive()) {
            log.warn("Kill switch active - skipping signal {}", signal.signalId());
            return;
        }

        // Get trader's weight in the index
        Optional<IndexConstituent> constituentOpt = weightProvider.getConstituent(
                config.indexType(), signal.username());

        if (constituentOpt.isEmpty()) {
            log.debug("Trader {} not in index {}, skipping signal",
                    signal.username(), config.indexType());
            return;
        }

        IndexConstituent constituent = constituentOpt.get();

        // Calculate fund target size
        BigDecimal targetShares = calculateTargetShares(signal, constituent);

        if (targetShares.compareTo(BigDecimal.ZERO) <= 0) {
            log.debug("Target shares {} too small for signal {}", targetShares, signal.signalId());
            return;
        }

        // Check position limits
        if (!checkPositionLimits(signal, targetShares)) {
            log.warn("Position limits exceeded for signal {}", signal.signalId());
            return;
        }

        // Submit order
        submitOrder(signal, targetShares);
    }

    /**
     * Calculate target shares based on signal and trader weight.
     */
    private BigDecimal calculateTargetShares(TraderSignal signal, IndexConstituent constituent) {
        BigDecimal rawTarget = constituent.calculateFundShares(signal.shares(), config.capitalUsd());

        // Apply max position limit
        BigDecimal maxPositionUsd = config.capitalUsd()
                .multiply(BigDecimal.valueOf(config.maxPositionPct()));
        BigDecimal targetNotional = rawTarget.multiply(signal.price());

        if (targetNotional.compareTo(maxPositionUsd) > 0) {
            // Scale down to max position
            rawTarget = maxPositionUsd.divide(signal.price(), 2, RoundingMode.DOWN);
        }

        // Check min trade size
        BigDecimal notional = rawTarget.multiply(signal.price());
        if (notional.compareTo(config.minTradeUsd()) < 0) {
            return BigDecimal.ZERO;
        }

        return rawTarget.setScale(2, RoundingMode.DOWN);
    }

    /**
     * Check position limits before trading.
     */
    private boolean checkPositionLimits(TraderSignal signal, BigDecimal targetShares) {
        // Check max open positions
        if (positions.size() >= config.riskLimits().maxOpenPositions()) {
            if (!positions.containsKey(signal.tokenId())) {
                log.warn("Max open positions ({}) reached", config.riskLimits().maxOpenPositions());
                return false;
            }
        }

        // Check single market exposure
        BigDecimal newExposure = targetShares.multiply(signal.price());
        FundPosition existing = positions.get(signal.tokenId());
        if (existing != null) {
            newExposure = newExposure.add(existing.notionalValue(signal.price()));
        }

        if (newExposure.compareTo(config.riskLimits().maxSingleMarketExposureUsd()) > 0) {
            log.warn("Single market exposure ${} exceeds limit ${}",
                    newExposure, config.riskLimits().maxSingleMarketExposureUsd());
            return false;
        }

        return true;
    }

    /**
     * Submit order to executor.
     */
    private void submitOrder(TraderSignal signal, BigDecimal shares) {
        OrderSide side = signal.type() == TraderSignal.SignalType.BUY
                ? OrderSide.BUY
                : OrderSide.SELL;

        // Calculate limit price with slippage
        BigDecimal limitPrice = calculateLimitPrice(signal.price(), side);

        LimitOrderRequest request = new LimitOrderRequest(
                signal.tokenId(),
                side,
                limitPrice,
                shares,
                null,  // orderType - default
                null,  // tickSize - let executor fetch
                null,  // negRisk
                null,  // feeRateBps
                null,  // nonce
                null,  // expirationSeconds
                null,  // taker
                null   // deferExec
        );

        log.info("Submitting {} {} shares of {} at ${} (signal: {}, trader: {})",
                side, shares, signal.tokenId(), limitPrice, signal.signalId(), signal.username());

        try {
            OrderSubmissionResult result = executorApi.placeLimitOrder(request);
            ordersSubmitted++;
            ordersSubmittedCounter.increment();

            String orderId = resolveOrderId(result);
            String status = resolveStatus(result);
            log.info("Order submitted: {} (status: {})", orderId, status);

            // Update position tracking
            updatePosition(signal, shares, limitPrice);

            // Persist to ClickHouse
            persistSignalExecution(signal, shares, limitPrice, orderId);

        } catch (Exception e) {
            ordersFailed++;
            ordersFailedCounter.increment();
            log.error("Order submission failed: {}", e.getMessage());
            throw e;
        }
    }

    /**
     * Calculate limit price with slippage tolerance.
     */
    private BigDecimal calculateLimitPrice(BigDecimal marketPrice, OrderSide side) {
        BigDecimal slippage = BigDecimal.valueOf(config.maxSlippagePct());

        if (side == OrderSide.BUY) {
            // For buys, go higher
            return marketPrice.multiply(BigDecimal.ONE.add(slippage))
                    .setScale(4, RoundingMode.UP);
        } else {
            // For sells, go lower
            return marketPrice.multiply(BigDecimal.ONE.subtract(slippage))
                    .setScale(4, RoundingMode.DOWN);
        }
    }

    /**
     * Update position tracking after order.
     */
    private void updatePosition(TraderSignal signal, BigDecimal shares, BigDecimal price) {
        Instant now = clock.instant();
        String tokenId = signal.tokenId();

        if (signal.type() == TraderSignal.SignalType.BUY) {
            FundPosition existing = positions.get(tokenId);
            if (existing != null) {
                positions.put(tokenId, existing.add(shares, price, now));
            } else {
                String positionId = UUID.randomUUID().toString();
                positions.put(tokenId, FundPosition.open(positionId, signal, shares, price, now));
            }
        } else {
            FundPosition existing = positions.get(tokenId);
            if (existing != null) {
                FundPosition updated = existing.reduce(shares, price, now);
                if (updated.isClosed()) {
                    positions.remove(tokenId);
                } else {
                    positions.put(tokenId, updated);
                }
            }
        }
    }

    /**
     * Persist signal execution to ClickHouse for analytics.
     */
    private void persistSignalExecution(TraderSignal signal, BigDecimal shares,
                                        BigDecimal price, String orderId) {
        try {
            String sql = """
                INSERT INTO polybot.aware_fund_executions
                (signal_id, fund_id, trader_username, market_slug, token_id, outcome,
                 signal_type, trader_shares, fund_shares, execution_price, order_id,
                 detected_at, executed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """;

            jdbcTemplate.update(sql,
                    signal.signalId(),
                    config.indexType(),
                    signal.username(),
                    signal.marketSlug(),
                    signal.tokenId(),
                    signal.outcome(),
                    signal.type().name(),
                    signal.shares(),
                    shares,
                    price,
                    orderId,
                    signal.detectedAt(),
                    clock.instant()
            );
        } catch (Exception e) {
            log.warn("Failed to persist execution: {}", e.getMessage());
        }
    }

    /**
     * Extract orderId from clobResponse.
     */
    private static String resolveOrderId(OrderSubmissionResult result) {
        if (result == null) return null;
        JsonNode resp = result.clobResponse();
        if (resp != null) {
            if (resp.hasNonNull("orderID")) return resp.get("orderID").asText();
            if (resp.hasNonNull("orderId")) return resp.get("orderId").asText();
        }
        return null;
    }

    /**
     * Extract status from clobResponse.
     */
    private static String resolveStatus(OrderSubmissionResult result) {
        if (result == null) return "UNKNOWN";
        JsonNode resp = result.clobResponse();
        if (resp != null && resp.hasNonNull("status")) {
            return resp.get("status").asText();
        }
        return "UNKNOWN";
    }

    // ========== Status Methods ==========

    public Map<String, FundPosition> getPositions() {
        return Map.copyOf(positions);
    }

    public int getPendingSignalCount() {
        return pendingSignals.size();
    }

    public Map<String, Object> getMetrics() {
        return Map.of(
                "signalsProcessed", signalsProcessed,
                "ordersSubmitted", ordersSubmitted,
                "ordersFailed", ordersFailed,
                "pendingSignals", pendingSignals.size(),
                "openPositions", positions.size()
        );
    }

    private record PendingSignal(TraderSignal signal, Instant executeAt) {}
}
