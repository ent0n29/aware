package com.polybot.hft.polymarket.fund.strategy;

import com.fasterxml.jackson.databind.JsonNode;
import com.polybot.hft.domain.OrderSide;
import com.polybot.hft.polymarket.api.LimitOrderRequest;
import com.polybot.hft.polymarket.api.OrderSubmissionResult;
import com.polybot.hft.polymarket.fund.config.ActiveFundConfig;
import com.polybot.hft.polymarket.fund.model.AlphaSignal;
import com.polybot.hft.polymarket.fund.model.FundPosition;
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
import java.time.LocalDate;
import java.util.*;
import java.util.concurrent.*;

/**
 * Base executor for active alpha fund strategies.
 *
 * Provides core execution infrastructure for ALPHA-* funds:
 * - Signal-to-order translation with configurable sizing
 * - Position management with risk limits
 * - Order lifecycle tracking
 * - ClickHouse persistence for analytics
 *
 * Subclasses (strategies) override signal generation methods while
 * this class handles all execution mechanics.
 *
 * Flow:
 * 1. Strategy generates AlphaSignal via processSignal()
 * 2. Signal is validated against filters and risk limits
 * 3. Position size is calculated based on config + signal confidence
 * 4. Order is submitted to executor-service
 * 5. Position is tracked and persisted
 */
@Slf4j
public abstract class ActiveFundExecutor {

    protected final ActiveFundConfig config;
    protected final ExecutorApiClient executorApi;
    protected final JdbcTemplate jdbcTemplate;
    protected final Clock clock;
    protected final MeterRegistry meterRegistry;

    // Active positions by tokenId
    protected final Map<String, FundPosition> positions = new ConcurrentHashMap<>();

    // Pending orders awaiting confirmation
    protected final Map<String, PendingOrder> pendingOrders = new ConcurrentHashMap<>();

    // Signals queued for execution (with optional delay)
    protected final Queue<QueuedSignal> signalQueue = new ConcurrentLinkedQueue<>();

    // Daily metrics tracking
    private volatile LocalDate currentDay;
    private volatile int dailyTradeCount = 0;
    private volatile BigDecimal dailyNotionalTraded = BigDecimal.ZERO;

    // Metrics
    private int signalsReceived = 0;
    private int signalsFiltered = 0;
    private int signalsExecuted = 0;
    private int ordersSubmitted = 0;
    private int ordersFailed = 0;

    // Prometheus metrics
    private final Counter signalsReceivedCounter;
    private final Counter signalsFilteredCounter;
    private final Counter signalsExecutedCounter;

    protected ActiveFundExecutor(
            ActiveFundConfig config,
            ExecutorApiClient executorApi,
            JdbcTemplate jdbcTemplate,
            Clock clock,
            MeterRegistry meterRegistry
    ) {
        this.config = config;
        this.executorApi = executorApi;
        this.jdbcTemplate = jdbcTemplate;
        this.clock = clock;
        this.meterRegistry = meterRegistry;
        this.currentDay = LocalDate.now(clock);

        // Initialize Prometheus metrics
        String fundType = config.fundType() != null ? config.fundType() : "ALPHA";

        this.signalsReceivedCounter = Counter.builder("alpha.signals.received")
                .description("Total alpha signals received")
                .tag("fund", fundType)
                .register(meterRegistry);

        this.signalsFilteredCounter = Counter.builder("alpha.signals.filtered")
                .description("Total alpha signals filtered out")
                .tag("fund", fundType)
                .register(meterRegistry);

        this.signalsExecutedCounter = Counter.builder("alpha.signals.executed")
                .description("Total alpha signals executed")
                .tag("fund", fundType)
                .register(meterRegistry);

        // Register gauges for daily metrics - using AtomicReference for thread safety
        io.micrometer.core.instrument.Gauge.builder("alpha.daily.trades", this, e -> e.dailyTradeCount)
                .description("Daily trade count")
                .tag("fund", fundType)
                .register(meterRegistry);

        io.micrometer.core.instrument.Gauge.builder("alpha.daily.notional", this, e -> e.dailyNotionalTraded.doubleValue())
                .description("Daily notional traded in USD")
                .tag("fund", fundType)
                .register(meterRegistry);
    }

    // ========== Abstract Methods for Subclasses ==========

    /**
     * Get the fund type identifier (e.g., "ALPHA-INSIDER").
     */
    public abstract String getFundType();

    /**
     * Strategy-specific signal polling/generation.
     * Called periodically by the scheduled task.
     */
    public abstract void pollForSignals();

    /**
     * Strategy-specific initialization.
     * Called once when the executor starts.
     */
    protected void onStart() {
        log.info("Starting {} executor with capital ${}", getFundType(), config.capitalUsd());
    }

    /**
     * Strategy-specific shutdown.
     * Called when the executor stops.
     */
    protected void onStop() {
        log.info("Stopping {} executor", getFundType());
    }

    // ========== Signal Processing ==========

    /**
     * Process an alpha signal from the strategy.
     *
     * This is the main entry point for strategies to submit signals.
     * The signal will be validated, sized, and executed.
     */
    public void processSignal(AlphaSignal signal) {
        signalsReceived++;
        signalsReceivedCounter.increment();

        // Reset daily counters if new day
        checkDayRollover();

        // Validate signal
        if (!validateSignal(signal)) {
            signalsFiltered++;
            signalsFilteredCounter.increment();
            return;
        }

        // Check risk limits
        if (!checkRiskLimits(signal)) {
            signalsFiltered++;
            signalsFilteredCounter.increment();
            log.info("Signal {} rejected by risk limits", signal.signalId());
            return;
        }

        // Queue for execution (with optional delay)
        queueSignal(signal);
    }

    /**
     * Validate a signal against configuration thresholds.
     */
    protected boolean validateSignal(AlphaSignal signal) {
        Instant now = clock.instant();

        // Check expiry
        if (!signal.isValid(now)) {
            log.debug("Signal {} expired at {}", signal.signalId(), signal.expiresAt());
            return false;
        }

        // Check confidence threshold
        if (!signal.meetsConfidenceThreshold(config.minConfidence())) {
            log.debug("Signal {} confidence {} below threshold {}",
                    signal.signalId(), signal.confidence(), config.minConfidence());
            return false;
        }

        // Check strength threshold
        if (signal.strength() < config.minStrength()) {
            log.debug("Signal {} strength {} below threshold {}",
                    signal.signalId(), signal.strength(), config.minStrength());
            return false;
        }

        // Check HOLD signals (informational only)
        if (signal.action() == AlphaSignal.SignalAction.HOLD) {
            log.debug("Signal {} is HOLD - no action needed", signal.signalId());
            return false;
        }

        return true;
    }

    /**
     * Check risk limits before executing.
     */
    protected boolean checkRiskLimits(AlphaSignal signal) {
        // Kill switch
        if (config.riskLimits().killSwitchActive()) {
            log.warn("Kill switch active - rejecting signal {}", signal.signalId());
            return false;
        }

        // Daily trade limit
        if (dailyTradeCount >= config.maxDailyTrades()) {
            log.warn("Daily trade limit ({}) reached", config.maxDailyTrades());
            return false;
        }

        // Daily notional limit
        BigDecimal signalSize = calculatePositionSize(signal);
        if (dailyNotionalTraded.add(signalSize).compareTo(config.maxDailyNotionalUsd()) > 0) {
            log.warn("Daily notional limit ${} would be exceeded", config.maxDailyNotionalUsd());
            return false;
        }

        // Max open positions (for new positions only)
        if (signal.action() == AlphaSignal.SignalAction.BUY &&
            !positions.containsKey(signal.tokenId()) &&
            positions.size() >= config.riskLimits().maxOpenPositions()) {
            log.warn("Max open positions ({}) reached", config.riskLimits().maxOpenPositions());
            return false;
        }

        // Max concurrent orders
        if (pendingOrders.size() >= config.maxConcurrentOrders()) {
            log.warn("Max concurrent orders ({}) reached", config.maxConcurrentOrders());
            return false;
        }

        return true;
    }

    /**
     * Queue a signal for execution.
     */
    protected void queueSignal(AlphaSignal signal) {
        Instant executeAt = clock.instant().plusMillis(config.executionDelayMillis());
        signalQueue.add(new QueuedSignal(signal, executeAt));
        log.info("Queued signal {} for {} at {} (delay {}ms)",
                signal.signalId(), signal.action(), executeAt, config.executionDelayMillis());
    }

    /**
     * Process queued signals whose delay has expired.
     * Called periodically by scheduled task.
     */
    public void processQueuedSignals() {
        Instant now = clock.instant();
        QueuedSignal queued;

        while ((queued = signalQueue.peek()) != null && queued.executeAt.isBefore(now)) {
            signalQueue.poll();
            try {
                executeSignal(queued.signal);
                signalsExecuted++;
                signalsExecutedCounter.increment();
            } catch (Exception e) {
                log.error("Failed to execute signal {}: {}", queued.signal.signalId(), e.getMessage());
                ordersFailed++;
            }
        }
    }

    // ========== Order Execution ==========

    /**
     * Execute a validated signal.
     */
    protected void executeSignal(AlphaSignal signal) {
        BigDecimal positionSize = calculatePositionSize(signal);

        if (positionSize.compareTo(BigDecimal.ZERO) <= 0) {
            log.debug("Position size {} too small for signal {}", positionSize, signal.signalId());
            return;
        }

        // Determine order side
        OrderSide side = signal.action() == AlphaSignal.SignalAction.BUY
                ? OrderSide.BUY
                : OrderSide.SELL;

        // Get current market price (use suggested or fetch from executor)
        BigDecimal marketPrice = estimateMarketPrice(signal);

        // Calculate shares from notional
        BigDecimal shares = positionSize.divide(marketPrice, 2, RoundingMode.DOWN);

        // Calculate limit price with slippage
        BigDecimal limitPrice = calculateLimitPrice(marketPrice, side, signal.urgency());

        // Submit order
        submitOrder(signal, side, shares, limitPrice);
    }

    /**
     * Calculate position size based on signal and config.
     */
    protected BigDecimal calculatePositionSize(AlphaSignal signal) {
        // Use suggested size if provided
        if (signal.suggestedSizeUsd() != null &&
            signal.suggestedSizeUsd().compareTo(BigDecimal.ZERO) > 0) {
            return capPositionSize(signal.suggestedSizeUsd());
        }

        // Calculate from config
        BigDecimal size = config.calculatePositionSize(signal.confidence(), signal.strength());
        return capPositionSize(size);
    }

    /**
     * Cap position size to risk limits.
     */
    protected BigDecimal capPositionSize(BigDecimal size) {
        // Cap to max single position
        BigDecimal maxPosition = config.capitalUsd()
                .multiply(BigDecimal.valueOf(config.maxSinglePositionPct()));
        if (size.compareTo(maxPosition) > 0) {
            size = maxPosition;
        }

        // Cap to max single market exposure
        if (size.compareTo(config.riskLimits().maxSingleMarketExposureUsd()) > 0) {
            size = config.riskLimits().maxSingleMarketExposureUsd();
        }

        return size;
    }

    /**
     * Estimate market price for a signal.
     */
    protected BigDecimal estimateMarketPrice(AlphaSignal signal) {
        // Use metadata if available
        if (signal.metadata() != null && signal.metadata().containsKey("currentPrice")) {
            Object price = signal.metadata().get("currentPrice");
            if (price instanceof Number) {
                return BigDecimal.valueOf(((Number) price).doubleValue());
            }
        }

        // Default to 0.50 for binary markets
        return BigDecimal.valueOf(0.50);
    }

    /**
     * Calculate limit price with slippage based on urgency.
     */
    protected BigDecimal calculateLimitPrice(BigDecimal marketPrice, OrderSide side,
                                             AlphaSignal.SignalUrgency urgency) {
        // Urgency affects slippage tolerance
        double slippageMult = switch (urgency) {
            case LOW -> 0.5;
            case MEDIUM -> 1.0;
            case HIGH -> 1.5;
            case CRITICAL -> 2.0;
        };

        BigDecimal slippage = BigDecimal.valueOf(config.maxSlippagePct() * slippageMult);

        if (side == OrderSide.BUY) {
            return marketPrice.multiply(BigDecimal.ONE.add(slippage))
                    .setScale(4, RoundingMode.UP);
        } else {
            return marketPrice.multiply(BigDecimal.ONE.subtract(slippage))
                    .setScale(4, RoundingMode.DOWN);
        }
    }

    /**
     * Submit order to executor-service.
     */
    protected void submitOrder(AlphaSignal signal, OrderSide side,
                               BigDecimal shares, BigDecimal limitPrice) {
        LimitOrderRequest request = new LimitOrderRequest(
                signal.tokenId(),
                side,
                limitPrice,
                shares,
                null,  // orderType
                null,  // tickSize - let executor fetch
                null,  // negRisk
                null,  // feeRateBps
                null,  // nonce
                null,  // expirationSeconds
                null,  // taker
                null   // deferExec
        );

        log.info("Submitting {} {} shares of {} at ${} (signal: {}, confidence: {:.2f})",
                side, shares, signal.tokenId(), limitPrice,
                signal.signalId(), signal.confidence());

        try {
            OrderSubmissionResult result = executorApi.placeLimitOrder(request);
            ordersSubmitted++;

            String orderId = resolveOrderId(result);
            String status = resolveStatus(result);

            log.info("Order submitted: {} (status: {})", orderId, status);

            // Track pending order
            if (orderId != null) {
                pendingOrders.put(orderId, new PendingOrder(
                        orderId, signal, side, shares, limitPrice, clock.instant()
                ));
            }

            // Update daily metrics
            dailyTradeCount++;
            dailyNotionalTraded = dailyNotionalTraded.add(shares.multiply(limitPrice));

            // Update position tracking
            updatePosition(signal, side, shares, limitPrice);

            // Persist to ClickHouse
            persistExecution(signal, side, shares, limitPrice, orderId);

        } catch (Exception e) {
            ordersFailed++;
            log.error("Order submission failed: {}", e.getMessage());
            throw e;
        }
    }

    /**
     * Update position tracking after order.
     */
    protected void updatePosition(AlphaSignal signal, OrderSide side,
                                  BigDecimal shares, BigDecimal price) {
        Instant now = clock.instant();
        String tokenId = signal.tokenId();

        if (side == OrderSide.BUY) {
            FundPosition existing = positions.get(tokenId);
            if (existing != null) {
                positions.put(tokenId, existing.add(shares, price, now));
            } else {
                String positionId = UUID.randomUUID().toString();
                // Create position using TraderSignal-compatible constructor
                positions.put(tokenId, new FundPosition(
                        positionId,
                        signal.marketSlug(),
                        signal.tokenId(),
                        signal.outcome(),
                        shares,
                        price,
                        BigDecimal.ZERO,
                        now,
                        now,
                        signal.signalId()
                ));
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
     * Persist execution to ClickHouse for analytics.
     */
    protected void persistExecution(AlphaSignal signal, OrderSide side,
                                    BigDecimal shares, BigDecimal price, String orderId) {
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
                    getFundType(),
                    signal.source().name(),  // Use source as "trader" for alpha funds
                    signal.marketSlug(),
                    signal.tokenId(),
                    signal.outcome(),
                    side.name(),
                    shares,  // For alpha funds, trader_shares = fund_shares
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

    // ========== Helper Methods ==========

    private void checkDayRollover() {
        LocalDate today = LocalDate.now(clock);
        if (!today.equals(currentDay)) {
            log.info("Day rollover: resetting daily counters");
            currentDay = today;
            dailyTradeCount = 0;
            dailyNotionalTraded = BigDecimal.ZERO;
        }
    }

    private static String resolveOrderId(OrderSubmissionResult result) {
        if (result == null) return null;
        JsonNode resp = result.clobResponse();
        if (resp != null) {
            if (resp.hasNonNull("orderID")) return resp.get("orderID").asText();
            if (resp.hasNonNull("orderId")) return resp.get("orderId").asText();
        }
        return null;
    }

    private static String resolveStatus(OrderSubmissionResult result) {
        if (result == null) return "UNKNOWN";
        JsonNode resp = result.clobResponse();
        if (resp != null && resp.hasNonNull("status")) {
            return resp.get("status").asText();
        }
        return "UNKNOWN";
    }

    // ========== Status Methods ==========

    public boolean isEnabled() {
        return config.enabled();
    }

    public Map<String, FundPosition> getPositions() {
        return Map.copyOf(positions);
    }

    public int getPendingSignalCount() {
        return signalQueue.size();
    }

    public int getPendingOrderCount() {
        return pendingOrders.size();
    }

    public Map<String, Object> getMetrics() {
        Map<String, Object> metrics = new HashMap<>();
        metrics.put("fundType", getFundType());
        metrics.put("enabled", config.enabled());
        metrics.put("capitalUsd", config.capitalUsd());
        metrics.put("signalsReceived", signalsReceived);
        metrics.put("signalsFiltered", signalsFiltered);
        metrics.put("signalsExecuted", signalsExecuted);
        metrics.put("ordersSubmitted", ordersSubmitted);
        metrics.put("ordersFailed", ordersFailed);
        metrics.put("pendingSignals", signalQueue.size());
        metrics.put("pendingOrders", pendingOrders.size());
        metrics.put("openPositions", positions.size());
        metrics.put("dailyTradeCount", dailyTradeCount);
        metrics.put("dailyNotionalTraded", dailyNotionalTraded);
        return metrics;
    }

    public ActiveFundConfig getConfig() {
        return config;
    }

    // ========== Internal Records ==========

    protected record QueuedSignal(AlphaSignal signal, Instant executeAt) {}

    protected record PendingOrder(
            String orderId,
            AlphaSignal signal,
            OrderSide side,
            BigDecimal shares,
            BigDecimal price,
            Instant submittedAt
    ) {}
}
