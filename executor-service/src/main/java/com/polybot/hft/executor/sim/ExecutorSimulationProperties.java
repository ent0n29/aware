package com.polybot.hft.executor.sim;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "executor.sim")
public record ExecutorSimulationProperties(
    @NotNull Boolean enabled,
    /**
     * Username to attribute simulated fills to (written as polymarket.user.trade events).
     */
    String username,
    /**
     * Proxy address to attribute simulated fills to. Does not need to be a real Polygon address.
     */
    String proxyAddress,
    /**
     * When enabled, simulate fills and publish polymarket.user.trade events.
     */
    @NotNull Boolean fillsEnabled,
    /**
     * Fill simulation poll interval.
     */
    @NotNull @Min(50) Long fillPollMillis,
    /**
     * Maximum allowed age (ms) for WS top-of-book data when simulating fills.
     * Older snapshots are skipped to avoid using stale prices.
     */
    @NotNull @Min(0) Long tobMaxAgeMillis,
    /**
     * Minimum age (ms) before a maker-like order is eligible to fill.
     */
    @NotNull @Min(0) Long makerFillMinAgeMillis,
    /**
     * Minimum lag (ms) between fills on opposite outcomes for the same condition.
     * Helps enforce lead→lag timing in the simulator.
     */
    @NotNull @Min(0) Long leadLagMinMillis,
    /**
     * Probability (0..1) of a maker-like partial fill per poll when our bid is competitive.
     */
    @NotNull @DecimalMin("0.0") @DecimalMax("1.0") Double makerFillProbabilityPerPoll,
    /**
     * Multiplier applied per tick when our price improves above the current best bid (queue priority proxy).
     * For example, with base p=0.02 and multiplier=1.5:
     * - 0 ticks above best bid: p=0.02
     * - 1 tick above best bid: p=0.03
     * - 2 ticks above best bid: p=0.045
     *
     * Set to 1.0 to disable tick-based scaling.
     */
    @NotNull @DecimalMin("0.0") @DecimalMax("10.0") Double makerFillProbabilityMultiplierPerTick,
    /**
     * Upper bound cap (0..1) on the per-poll maker fill probability after scaling.
     */
    @NotNull @DecimalMin("0.0") @DecimalMax("1.0") Double makerFillProbabilityMaxPerPoll,
    /**
     * Fraction (0..1) of remaining size to fill when a maker-like fill triggers.
     */
    @NotNull @DecimalMin("0.0") @DecimalMax("1.0") Double makerFillFractionOfRemaining,
    /**
     * Queue priority multiplier range for maker orders (introduces fill-time variance).
     */
    @NotNull @DecimalMin("0.1") @DecimalMax("5.0") Double makerQueueFactorMin,
    @NotNull @DecimalMin("0.1") @DecimalMax("5.0") Double makerQueueFactorMax,
    /**
     * When enabled, drive maker fills from the real market trade tape (data-api market trades),
     * instead of using a per-poll Bernoulli fill probability.
     */
    @NotNull Boolean tradeTapeEnabled,
    /**
     * Source for trade-tape prints used to drive maker fills.
     * <p>
     * - {@code WS}: Use the market websocket last-trade events (real-time, but no size; we synthesize size)
     * - {@code WS_BID_DELTA}: Use WS top-of-book best-bid size deltas as a proxy for sell volume at the bid
     * - {@code DATA_API}: Poll data-api /trades (has size, but can be delayed and avg-priced)
     */
    @NotNull String tradeTapeSource,
    /**
     * Poll interval (ms) for fetching new trade tape prints per condition.
     */
    @NotNull @Min(100) Long tradeTapePollMillis,
    /**
     * Number of recent trades to fetch per condition per poll.
     */
    @NotNull @Min(1) Integer tradeTapeLimit,
    /**
     * When enabled, stamp simulated fills with the triggering trade's timestamp (seconds-resolution),
     * rather than the local clock time. This improves strict match comparability vs target prints.
     */
    @NotNull Boolean tradeTapeUseTradeTimestamp,
    /**
     * When enabled, allow a trade-tape-gated probabilistic fallback for maker-like fills.
     * <p>
     * Rationale: the public trade tape does not fully reveal our queue priority/order lifecycle at a
     * given price level, so strict print matching alone can under-fill in PAPER. The fallback keeps
     * trade activity as the timing driver while still producing realistic maker fills.
     */
    @NotNull Boolean tradeTapeFallbackEnabled,
    /**
     * Only allow fallback fills if we've observed a trade tape print for this token within the last N ms.
     */
    @NotNull @Min(0) Long tradeTapeFallbackMaxIdleMillis,
    /**
     * Scale factor applied to {@link #makerFillProbabilityPerPoll} when using the trade-tape fallback.
     */
    @NotNull @DecimalMin("0.0") @DecimalMax("10.0") Double tradeTapeFallbackProbabilityScale,
    /**
     * WS_BID_DELTA only: when best-bid size decreases without a corresponding last-trade signal,
     * treat it as partially-cancel-driven by scaling the inferred "print size" by this factor.
     * <p>
     * 0.0 = ignore cancel-like deltas entirely, 1.0 = treat all size decreases as prints.
     */
    @NotNull @DecimalMin("0.0") @DecimalMax("1.0") Double tradeTapeBidDeltaCancelScale,
    /**
     * WS_BID_DELTA only: maximum allowed lag (ms) between tob.updatedAt and lastTradeAt to consider
     * a size-delta as "trade-confirmed".
     */
    @NotNull @Min(0) Long tradeTapeBidDeltaMaxTradeLagMillis,
    /**
     * CLICKHOUSE_MARKET_TRADES only: ClickHouse HTTP URL (e.g., http://127.0.0.1:8123).
     */
    String tradeTapeClickhouseUrl,
    /**
     * CLICKHOUSE_MARKET_TRADES only: ClickHouse database (default: polybot).
     */
    String tradeTapeClickhouseDatabase,
    /**
     * CLICKHOUSE_MARKET_TRADES only: ClickHouse user (optional).
     */
    String tradeTapeClickhouseUser,
    /**
     * CLICKHOUSE_MARKET_TRADES only: ClickHouse password (optional).
     */
    String tradeTapeClickhousePassword,
    /**
     * CLICKHOUSE_MARKET_TRADES only: how far back to query per poll (seconds).
     * Keep this small; we dedupe by event_key.
     */
    @NotNull @Min(1) Integer tradeTapeClickhouseLookbackSeconds
) {
  public ExecutorSimulationProperties {
    if (enabled == null) {
      enabled = false;
    }
    if (username == null || username.isBlank()) {
      username = "polybot-sim";
    }
    if (proxyAddress == null || proxyAddress.isBlank()) {
      proxyAddress = "sim";
    }
    if (fillsEnabled == null) {
      fillsEnabled = true;
    }
    if (fillPollMillis == null) {
      fillPollMillis = 250L;
    }
    if (tobMaxAgeMillis == null) {
      tobMaxAgeMillis = 5_000L;
    }
    if (makerFillMinAgeMillis == null) {
      makerFillMinAgeMillis = 0L;
    }
    if (leadLagMinMillis == null) {
      leadLagMinMillis = 0L;
    }
    if (makerFillProbabilityPerPoll == null) {
      makerFillProbabilityPerPoll = 0.03;
    }
    if (makerFillProbabilityMultiplierPerTick == null) {
      makerFillProbabilityMultiplierPerTick = 1.0;
    }
    if (makerFillProbabilityMaxPerPoll == null) {
      makerFillProbabilityMaxPerPoll = 0.50;
    }
    if (makerFillFractionOfRemaining == null) {
      makerFillFractionOfRemaining = 0.25;
    }
    if (makerQueueFactorMin == null) {
      makerQueueFactorMin = 0.5;
    }
    if (makerQueueFactorMax == null) {
      makerQueueFactorMax = 1.5;
    }
    if (tradeTapeEnabled == null) {
      tradeTapeEnabled = false;
    }
    if (tradeTapeSource == null || tradeTapeSource.isBlank()) {
      tradeTapeSource = "WS";
    }
    if (tradeTapePollMillis == null) {
      tradeTapePollMillis = 500L;
    }
    if (tradeTapeLimit == null) {
      tradeTapeLimit = 200;
    }
    if (tradeTapeUseTradeTimestamp == null) {
      tradeTapeUseTradeTimestamp = true;
    }
    if (tradeTapeFallbackEnabled == null) {
      tradeTapeFallbackEnabled = true;
    }
    if (tradeTapeFallbackMaxIdleMillis == null) {
      tradeTapeFallbackMaxIdleMillis = 2_000L;
    }
    if (tradeTapeFallbackProbabilityScale == null) {
      tradeTapeFallbackProbabilityScale = 0.35;
    }
    if (tradeTapeBidDeltaCancelScale == null) {
      tradeTapeBidDeltaCancelScale = 0.15;
    }
    if (tradeTapeBidDeltaMaxTradeLagMillis == null) {
      tradeTapeBidDeltaMaxTradeLagMillis = 300L;
    }
    if (tradeTapeClickhouseUrl == null || tradeTapeClickhouseUrl.isBlank()) {
      tradeTapeClickhouseUrl = "http://127.0.0.1:8123";
    }
    if (tradeTapeClickhouseDatabase == null || tradeTapeClickhouseDatabase.isBlank()) {
      tradeTapeClickhouseDatabase = "polybot";
    }
    if (tradeTapeClickhouseUser == null) {
      tradeTapeClickhouseUser = "";
    }
    if (tradeTapeClickhousePassword == null) {
      tradeTapeClickhousePassword = "";
    }
    if (tradeTapeClickhouseLookbackSeconds == null) {
      tradeTapeClickhouseLookbackSeconds = 20;
    }
  }
}
