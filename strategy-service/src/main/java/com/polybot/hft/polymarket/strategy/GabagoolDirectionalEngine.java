package com.polybot.hft.polymarket.strategy;

import com.polybot.hft.config.HftProperties;
import com.polybot.hft.events.HftEventPublisher;
import com.polybot.hft.polymarket.strategy.config.GabagoolConfig;
import com.polybot.hft.polymarket.strategy.model.Direction;
import com.polybot.hft.polymarket.strategy.model.GabagoolMarket;
import com.polybot.hft.polymarket.strategy.model.MarketInventory;
import com.polybot.hft.polymarket.strategy.model.OrderState;
import com.polybot.hft.polymarket.strategy.service.BankrollService;
import com.polybot.hft.polymarket.strategy.service.MomentumTracker;
import com.polybot.hft.polymarket.strategy.service.MomentumTracker.MomentumSignal;
import com.polybot.hft.polymarket.strategy.service.OrderManager;
import com.polybot.hft.polymarket.strategy.service.OrderManager.CancelReason;
import com.polybot.hft.polymarket.strategy.service.OrderManager.PlaceReason;
import com.polybot.hft.polymarket.strategy.service.PositionTracker;
import com.polybot.hft.polymarket.strategy.service.QuoteCalculator;
import com.polybot.hft.polymarket.ws.ClobMarketWebSocketClient;
import com.polybot.hft.polymarket.ws.TopOfBook;
import com.polybot.hft.strategy.executor.ExecutorApiClient;
import com.polybot.hft.strategy.metrics.StrategyMetricsService;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import lombok.NonNull;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import java.util.stream.Stream;

/**
 * Gabagool22-style strategy for Up/Down binary markets (replica-oriented).
 */
@Component
@Slf4j
@RequiredArgsConstructor
public class GabagoolDirectionalEngine {

    private static final Duration TICK_SIZE_CACHE_TTL = Duration.ofMinutes(10);

    private final @NonNull HftProperties properties;
    private final @NonNull ClobMarketWebSocketClient marketWs;
    private final @NonNull ExecutorApiClient executorApi;
    private final @NonNull HftEventPublisher events;
    private final @NonNull GabagoolMarketDiscovery marketDiscovery;
    private final @NonNull Clock clock;
    private final @NonNull StrategyMetricsService metricsService;

    private final ScheduledExecutorService executor = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "gabagool-directional");
        t.setDaemon(true);
        return t;
    });

    private final String runId = UUID.randomUUID().toString();
    private final AtomicReference<List<GabagoolMarket>> activeMarkets = new AtomicReference<>(List.of());
    private final Map<String, TickSizeEntry> tickSizeCache = new ConcurrentHashMap<>();
    private final Map<String, double[]> marketSizeSkew = new ConcurrentHashMap<>();
    private final Map<String, Instant> hedgeHoldUntil = new ConcurrentHashMap<>();
    private final Map<String, MakerImprovePair> makerImproveByMarket = new ConcurrentHashMap<>();
    private final Map<String, FastTopUpDecision> fastTopUpDecisionByMarket = new ConcurrentHashMap<>();
    private final Map<String, Instant> edgeBelowCancelSince = new ConcurrentHashMap<>();
    private final Map<String, MomentumSignal> lastMomentumSignal = new ConcurrentHashMap<>();

    private record FastTopUpDecision(Instant leadFillAt, boolean allowFastTopUp) {}

    // Services (initialized in startIfEnabled)
    private BankrollService bankrollService;
    private PositionTracker positionTracker;
    private QuoteCalculator quoteCalculator;
    private OrderManager orderManager;
    private MomentumTracker momentumTracker;

    @PostConstruct
    void startIfEnabled() {
        GabagoolConfig cfg = getConfig();
        logStartupConfig(cfg);

        if (!cfg.enabled()) {
            log.info("gabagool-directional strategy is disabled");
            return;
        }

        if (!properties.polymarket().marketWsEnabled()) {
            log.warn("gabagool-directional enabled, but market WS disabled");
            return;
        }

        // Initialize services
        bankrollService = new BankrollService(executorApi, metricsService, clock);
        positionTracker = new PositionTracker(executorApi, clock);
        quoteCalculator = new QuoteCalculator(bankrollService, properties, metricsService);
        orderManager = new OrderManager(executorApi, events, clock, runId);
        momentumTracker = new MomentumTracker(clock);

        long periodMs = Math.max(100, cfg.refreshMillis());
        executor.scheduleAtFixedRate(() -> safeTick(cfg), 1000, periodMs, TimeUnit.MILLISECONDS);
        executor.scheduleAtFixedRate(this::discoverMarkets, 0, 10, TimeUnit.SECONDS);

        log.info("gabagool-directional started (refreshMillis={})", periodMs);
    }

    public int activeMarketCount() {
        return activeMarkets.get().size();
    }

    public boolean isRunning() {
        return !executor.isShutdown() && getConfig().enabled();
    }

    @PreDestroy
    void shutdown() {
        log.info("gabagool-directional shutting down");
        if (orderManager != null) {
            orderManager.cancelAll(CancelReason.SHUTDOWN);
        }
        executor.shutdownNow();
    }

    private void tick(GabagoolConfig cfg) {
        positionTracker.refreshIfStale();
        bankrollService.refreshIfStale(cfg);
        positionTracker.syncInventory(activeMarkets.get());

        if (bankrollService.isBelowThreshold(cfg)) {
            log.warn("CIRCUIT BREAKER: Effective bankroll below threshold ({}), skipping market evaluation",
                    cfg.bankrollMinThreshold());
            orderManager.checkPendingOrders(this::handleFill);
            return;
        }

        Instant now = clock.instant();
        for (GabagoolMarket market : activeMarkets.get()) {
            try {
                evaluateMarket(market, cfg, now);
            } catch (Exception e) {
                log.error("Error evaluating market {}: {}", market.slug(), e.getMessage());
            }
        }

        orderManager.checkPendingOrders(this::handleFill);
    }

    private void safeTick(GabagoolConfig cfg) {
        try {
            tick(cfg);
        } catch (Exception e) {
            log.error("GABAGOOL: Tick failed, continuing scheduler loop", e);
        }
    }

    private void handleFill(OrderState state, BigDecimal filledShares) {
        if (state.market() == null || state.direction() == null) return;
        positionTracker.recordFill(state.market().slug(),
                state.direction() == Direction.UP, filledShares, state.price());
        log.debug("GABAGOOL: Updated inventory for {} after fill: {} +{} shares",
                state.market().slug(), state.direction(), filledShares);
        GabagoolConfig cfg = getConfig();
        maybeMarkHedgeDelay(state.market(), state.direction(), cfg);
        maybeCancelLaggingOnFill(state, cfg);
    }

    private void evaluateMarket(GabagoolMarket market, GabagoolConfig cfg, Instant now) {
        long secondsToEnd = Duration.between(now, market.endTime()).getSeconds();
        long maxLifetimeSeconds = "updown-15m".equals(market.marketType()) ? 900L : 3600L;

        if (secondsToEnd < 0 || secondsToEnd > maxLifetimeSeconds) {
            orderManager.cancelMarketOrders(market, CancelReason.OUTSIDE_LIFETIME, secondsToEnd);
            // Rolling 15m/1h instances create many unique slugs; keep per-market caches bounded.
            makerImproveByMarket.remove(market.slug());
            marketSizeSkew.remove(market.slug());
            fastTopUpDecisionByMarket.remove(market.slug());
            edgeBelowCancelSince.remove(market.slug());
            hedgeHoldUntil.remove(hedgeKey(market, Direction.UP));
            hedgeHoldUntil.remove(hedgeKey(market, Direction.DOWN));
            lastMomentumSignal.remove(market.slug());
            if (momentumTracker != null) {
                momentumTracker.removeMarket(market.slug());
            }
            return;
        }

        long minSecondsToEnd = Math.max(0L, cfg.minSecondsToEnd());
        long maxSecondsToEnd = Math.min(maxLifetimeSeconds, Math.max(minSecondsToEnd, cfg.maxSecondsToEnd()));
        if (secondsToEnd < minSecondsToEnd || secondsToEnd > maxSecondsToEnd) {
            orderManager.cancelMarketOrders(market, CancelReason.OUTSIDE_TIME_WINDOW, secondsToEnd);
            return;
        }

        TopOfBook upBook = marketWs.getTopOfBook(market.upTokenId()).orElse(null);
        TopOfBook downBook = marketWs.getTopOfBook(market.downTokenId()).orElse(null);

	        if (upBook == null || downBook == null || isStale(upBook) || isStale(downBook)) {
	            if (upBook == null || isStale(upBook)) {
	                orderManager.cancelOrder(market.upTokenId(), CancelReason.BOOK_STALE, secondsToEnd, upBook, downBook);
	            }
	            if (downBook == null || isStale(downBook)) {
	                orderManager.cancelOrder(market.downTokenId(), CancelReason.BOOK_STALE, secondsToEnd, downBook, upBook);
	            }
	            return;
	        }

	        // Record prices for momentum tracking
	        if (momentumTracker != null) {
	            momentumTracker.recordPrices(market.slug(), upBook, downBook);
	        }

	        // Target user very rarely trades when one leg is extremely cheap/expensive (liquidity + queue dynamics differ a lot).
	        // Keep the replica inside a mid-range price band to avoid over-trading extreme-probability states.
	        BigDecimal upBid = upBook.bestBid();
	        BigDecimal downBid = downBook.bestBid();
	        if (upBid == null || downBid == null) {
	            orderManager.cancelMarketOrders(market, CancelReason.BOOK_STALE, secondsToEnd);
	            return;
	        }
	        BigDecimal minBid = upBid.min(downBid);
	        BigDecimal maxBid = upBid.max(downBid);
	        // Widened from 0.10-0.90 to 0.05-0.95 to match gab's trading range
	        // Gab trades at prices as low as 0.09, so 0.10 filter was too restrictive
	        if (minBid.compareTo(BigDecimal.valueOf(0.05)) < 0 || maxBid.compareTo(BigDecimal.valueOf(0.95)) > 0) {
	            orderManager.cancelMarketOrders(market, CancelReason.BOOK_OUT_OF_BAND, secondsToEnd);
	            return;
	        }

	        MarketInventory inv = positionTracker.getInventory(market.slug());
	        int[] skew = quoteCalculator.calculateSkewTicks(inv, cfg);
	        int skewTicksUp = skew[0];
        int skewTicksDown = skew[1];
        double[] sizeSkew = computeSizeSkewFactors(market, upBid, downBid);
        double upSizeFactor = sizeSkew[0];
        double downSizeFactor = sizeSkew[1];

        // Fast top-up after recent fill
        maybeFastTopUp(market, inv, upBook, downBook, cfg, secondsToEnd);

        // Near-end taker top-up
        if (cfg.completeSetTopUpEnabled() && secondsToEnd <= cfg.completeSetTopUpSecondsToEnd()) {
            BigDecimal absImbalance = inv.imbalance().abs();
            if (absImbalance.compareTo(cfg.completeSetTopUpMinShares()) >= 0) {
                Direction laggingLeg = inv.imbalance().compareTo(BigDecimal.ZERO) > 0 ? Direction.DOWN : Direction.UP;
                TopOfBook laggingBook = laggingLeg == Direction.UP ? upBook : downBook;
                String laggingTokenId = laggingLeg == Direction.UP ? market.upTokenId() : market.downTokenId();
                maybeTopUpLaggingLeg(market, laggingTokenId, laggingLeg, laggingBook,
                        laggingLeg == Direction.UP ? downBook : upBook, cfg, secondsToEnd, absImbalance, PlaceReason.TOP_UP);
            }
        }

        // Check planned edge
        BigDecimal upTickSize = getTickSize(market.upTokenId());
        BigDecimal downTickSize = getTickSize(market.downTokenId());
        if (upTickSize == null || downTickSize == null) {
            orderManager.cancelMarketOrders(market, CancelReason.BOOK_STALE, secondsToEnd);
            return;
        }

        BigDecimal upEntryPrice = quoteCalculator.calculateEntryPrice(upBook, upTickSize, cfg, skewTicksUp);
        BigDecimal downEntryPrice = quoteCalculator.calculateEntryPrice(downBook, downTickSize, cfg, skewTicksDown);
        if (upEntryPrice == null || downEntryPrice == null) {
            orderManager.cancelMarketOrders(market, CancelReason.BOOK_STALE, secondsToEnd);
            return;
        }

        BigDecimal plannedEdge = BigDecimal.ONE.subtract(upEntryPrice.add(downEntryPrice));
        BigDecimal entryEdge = BigDecimal.valueOf(cfg.completeSetMinEdge());
        BigDecimal cancelEdge = BigDecimal.valueOf(cfg.completeSetCancelEdge());
        if (cancelEdge.compareTo(entryEdge) > 0) {
            cancelEdge = entryEdge;
        }
        BigDecimal edgeEps = BigDecimal.valueOf(0.000001);

        // Check momentum signal - relax edge requirements when momentum is strong
        // Based on gabagool22 analysis: He often pays >$1.00 combined but wins 60%+ on direction
        MomentumSignal momentumSignal = momentumTracker != null
                ? momentumTracker.getSignal(market.slug())
                : MomentumSignal.NEUTRAL;
        boolean hasMomentum = momentumSignal != MomentumSignal.NEUTRAL;

        // When momentum is strong, relax edge requirements but stay near break-even.
        // RECALIBRATED: Previous -3%/-5% was too aggressive - SIM was placing orders at -9% edge!
        // Gab may use momentum but likely stays closer to break-even.
        BigDecimal momentumRelaxedCancelEdge = hasMomentum
                ? BigDecimal.valueOf(-0.01)  // Allow -1% edge when momentum is strong (was -5%)
                : cancelEdge;
        BigDecimal momentumRelaxedEntryEdge = hasMomentum
                ? BigDecimal.valueOf(0.0)    // Allow 0% edge for entry when momentum is strong (was -3%)
                : entryEdge;

        if (plannedEdge.add(edgeEps).compareTo(momentumRelaxedCancelEdge) < 0) {
            // Time hysteresis: avoid cancel-churn on brief edge dips.
            Instant since = edgeBelowCancelSince.computeIfAbsent(market.slug(), s -> now);
            long graceMillis = Math.max(750L, cfg.refreshMillis());
            long belowMillis = Math.max(0L, Duration.between(since, now).toMillis());
            if (belowMillis < graceMillis) {
                log.debug("GABAGOOL: Hold {} - edge {} < cancelEdge {} (momentum={}, {}ms < grace {}ms)",
                        market.slug(), plannedEdge, momentumRelaxedCancelEdge, momentumSignal, belowMillis, graceMillis);
                return;
            }
            edgeBelowCancelSince.remove(market.slug());
            log.debug("GABAGOOL: Cancel {} - edge {} < cancelEdge {} (momentum={}, {}ms >= grace {}ms)",
                    market.slug(), plannedEdge, momentumRelaxedCancelEdge, momentumSignal, belowMillis, graceMillis);
            orderManager.cancelMarketOrders(market, CancelReason.INSUFFICIENT_EDGE, secondsToEnd);
            return;
        } else {
            edgeBelowCancelSince.remove(market.slug());
        }

        if (plannedEdge.add(edgeEps).compareTo(momentumRelaxedEntryEdge) < 0) {
            log.debug("GABAGOOL: Holding {} - edge {} below entry {} (momentum={})",
                    market.slug(), plannedEdge, momentumRelaxedEntryEdge, momentumSignal);
            return;
        }

        boolean holdUp = isHedgeDelayActive(market, Direction.UP, cfg);
        boolean holdDown = isHedgeDelayActive(market, Direction.DOWN, cfg);

        // Optional taker mode
        if (shouldTake(plannedEdge, upBook, downBook, cfg, market)) {
            Direction takeLeg = decideTakerLeg(inv, upBook, downBook, cfg, upSizeFactor, downSizeFactor);
            if (takeLeg == Direction.UP) {
                if (!holdUp) {
                    maybeTakeToken(market, market.upTokenId(), Direction.UP, upBook, downBook, cfg, secondsToEnd, upSizeFactor);
                }
                if (!holdDown && !shouldSkipLaggingLeg(downSizeFactor)) {
                    maybeQuoteToken(market, market.downTokenId(), Direction.DOWN, downBook, upBook, cfg, secondsToEnd, plannedEdge, skewTicksDown, downTickSize, downSizeFactor, 0);
                }
                return;
            } else if (takeLeg == Direction.DOWN) {
                if (!holdDown) {
                    maybeTakeToken(market, market.downTokenId(), Direction.DOWN, downBook, upBook, cfg, secondsToEnd, downSizeFactor);
                }
                if (!holdUp && !shouldSkipLaggingLeg(upSizeFactor)) {
                    maybeQuoteToken(market, market.upTokenId(), Direction.UP, upBook, downBook, cfg, secondsToEnd, plannedEdge, skewTicksUp, upTickSize, upSizeFactor, 0);
                }
                return;
            }
        }

        // Maker mode
        boolean quoteUp = !holdUp && !shouldSkipLaggingLeg(upSizeFactor);
        boolean quoteDown = !holdDown && !shouldSkipLaggingLeg(downSizeFactor);

        // Spend edge slack down to the ENTRY threshold when improving inside the spread.
        // This matches the observed behavior: inside-spread fills cluster when the complete-set
        // edge has at least ~1 tick of slack above the entry edge (e.g., 2% edge can spend 1 tick
        // and still keep ~1% edge).
        int budgetTicks = computeImproveBudgetTicks(plannedEdge, entryEdge, upTickSize.min(downTickSize));
        String seriesKey = seriesKeyForMarket(market);

        int spreadUpTicks = spreadTicks(upBook, upTickSize);
        int spreadDownTicks = spreadTicks(downBook, downTickSize);
        int[] improves = getOrSampleMakerImprovePair(
                market, seriesKey, spreadUpTicks, spreadDownTicks, budgetTicks, cfg, now, quoteUp, quoteDown
        );
        int improveUp = improves[0];
        int improveDown = improves[1];

        if (quoteUp) {
            maybeQuoteToken(market, market.upTokenId(), Direction.UP, upBook, downBook, cfg, secondsToEnd, plannedEdge, skewTicksUp, upTickSize, upSizeFactor, improveUp);
        }
        if (quoteDown) {
            maybeQuoteToken(market, market.downTokenId(), Direction.DOWN, downBook, upBook, cfg, secondsToEnd, plannedEdge, skewTicksDown, downTickSize, downSizeFactor, improveDown);
        }
    }

    private void maybeQuoteToken(GabagoolMarket market, String tokenId, Direction direction,
                                  TopOfBook book, TopOfBook otherBook, GabagoolConfig cfg,
                                  long secondsToEnd, BigDecimal plannedEdge, int skewTicks, BigDecimal tickSize, double sizeFactor, int improveTicks) {
        if (tokenId == null || book == null) return;

        int priceTicks = skewTicks + Math.max(0, improveTicks);
        BigDecimal entryPrice = quoteCalculator.calculateEntryPrice(book, tickSize, cfg, priceTicks);
        if (entryPrice == null) return;

        BigDecimal exposure = quoteCalculator.calculateExposure(orderManager.getOpenOrders(), positionTracker.getAllInventories());
        BigDecimal shares = quoteCalculator.calculateShares(market, entryPrice, cfg, secondsToEnd, exposure, sizeFactor);
        if (shares == null) return;

        OrderState existing = orderManager.getOrder(tokenId);
        OrderManager.ReplaceDecision decision = orderManager.maybeReplaceOrder(
                tokenId, entryPrice, shares, cfg, CancelReason.REPLACE_PRICE, secondsToEnd, book, otherBook);
        if (decision == OrderManager.ReplaceDecision.SKIP) {
            return;
        }

        PlaceReason reason = decision == OrderManager.ReplaceDecision.REPLACE ? PlaceReason.REPLACE : PlaceReason.QUOTE;
        orderManager.placeOrder(market, tokenId, direction, entryPrice, shares, secondsToEnd, tickSize, book, otherBook, existing, reason);
    }

    private static String seriesKeyForMarket(GabagoolMarket market) {
        if (market == null || market.slug() == null) {
            return "other";
        }
        String slug = market.slug();
        if (slug.startsWith("btc-updown-15m-")) return "btc-15m";
        if (slug.startsWith("eth-updown-15m-")) return "eth-15m";
        if (slug.startsWith("bitcoin-up-or-down-")) return "btc-1h";
        if (slug.startsWith("ethereum-up-or-down-")) return "eth-1h";
        return "other";
    }

    private static int spreadTicks(TopOfBook book, BigDecimal tickSize) {
        if (book == null || book.bestBid() == null || book.bestAsk() == null) {
            return 1;
        }
        BigDecimal spread = book.bestAsk().subtract(book.bestBid());
        if (spread.compareTo(BigDecimal.ZERO) <= 0) {
            return 1;
        }
        BigDecimal denom = (tickSize == null || tickSize.compareTo(BigDecimal.ZERO) <= 0)
                ? BigDecimal.valueOf(0.01)
                : tickSize;
        try {
            int ticks = spread.divide(denom, 0, RoundingMode.HALF_UP).intValue();
            return Math.max(1, ticks);
        } catch (Exception e) {
            return 1;
        }
    }

    private record MakerImprovePair(int spreadUpTicks, int spreadDownTicks, int improveUp, int improveDown, Instant sampledAt) {}

    /**
     * Maker improve ticks are intentionally "sticky" per market instance to avoid excessive
     * cancel/replace churn (which destroys queue position and makes replication calibration noisy).
     *
     * We re-sample only when the spread regime changes or the cached selection gets old.
     */
    private int[] getOrSampleMakerImprovePair(GabagoolMarket market,
                                              String seriesKey,
                                              int spreadUpTicks,
                                              int spreadDownTicks,
                                              int budgetTicks,
                                              GabagoolConfig cfg,
                                              Instant now,
                                              boolean quoteUp,
                                              boolean quoteDown) {
        if (market == null || market.slug() == null) {
            return new int[]{0, 0};
        }
        if (budgetTicks <= 0) {
            return new int[]{0, 0};
        }

        long ttlMillis = Math.max(3_000L, Math.min(30_000L, cfg.forceReplaceMillis()));
        MakerImprovePair cached = makerImproveByMarket.get(market.slug());
        if (cached != null
                && cached.spreadUpTicks() == spreadUpTicks
                && cached.spreadDownTicks() == spreadDownTicks
                && cached.sampledAt() != null
                && Duration.between(cached.sampledAt(), now).toMillis() <= ttlMillis) {
            return new int[]{
                    quoteUp ? cached.improveUp() : 0,
                    quoteDown ? cached.improveDown() : 0
            };
        }

        int improveUp = quoteUp ? sampleMakerImproveTicks(seriesKey, spreadUpTicks) : 0;
        int improveDown = quoteDown ? sampleMakerImproveTicks(seriesKey, spreadDownTicks) : 0;
        int[] adjusted = enforceImproveBudget(improveUp, improveDown, budgetTicks);
        improveUp = adjusted[0];
        improveDown = adjusted[1];

        makerImproveByMarket.put(market.slug(), new MakerImprovePair(spreadUpTicks, spreadDownTicks, improveUp, improveDown, now));
        return new int[]{improveUp, improveDown};
    }

    /**
     * Sample maker price improvement (ticks above best bid) conditioned on spread and series.
     *
     * Empirical from clean gabagool22 trades:
     * - When spread is 1 tick, there is no room to improve.
     * - When spread is 2–3 ticks, bids frequently land at bid+1 (queue priority / inside-spread),
     *   with occasional deeper improvement when there is enough edge slack.
     *
     * Keep improvements bounded; taker mode and fast top-up handle the "need fill now" cases.
     */
    private int sampleMakerImproveTicks(String seriesKey, int spreadTicks) {
        int maxImprove = Math.max(0, spreadTicks - 1);
        if (maxImprove <= 0) {
            return 0;
        }

        int s = Math.min(spreadTicks, 5); // clamp to small buckets
        double r = ThreadLocalRandom.current().nextDouble();

        // Index = ticks above best bid (0..s-1).
        // Calibrated to match gabagool22's actual behavior: p50_above_bid = 0 (quotes AT the bid).
        // Data shows sim avg price 0.512 vs gab 0.506 - we're 1 cent too high. Increased at-bid weight to 95%.
        double[] weights = switch (s) {
            case 2 -> new double[]{0.95, 0.05};
            case 3 -> new double[]{0.90, 0.08, 0.02};
            case 4 -> new double[]{0.90, 0.06, 0.03, 0.01};
            default -> new double[]{0.90, 0.05, 0.03, 0.01, 0.01};
        };

        int sampled = sampleFromWeights(s, r, weights);
        return Math.min(sampled, maxImprove);
    }

    private static int sampleFromWeights(int spreadTicks, double r, double[] weights) {
        if (weights == null || weights.length == 0) {
            return 0;
        }
        double cum = 0.0;
        for (int i = 0; i < weights.length; i++) {
            cum += weights[i];
            if (r <= cum) {
                return i;
            }
        }
        return Math.min(weights.length - 1, Math.max(0, spreadTicks - 1));
    }

    /**
     * Max total maker improvement (in ticks) allowed across both legs while preserving entry edge.
     * If we spend too many ticks improving BOTH legs, net complete-set edge can go negative.
     */
    private static int computeImproveBudgetTicks(BigDecimal plannedEdge, BigDecimal entryEdge, BigDecimal tickSize) {
        if (plannedEdge == null || entryEdge == null || tickSize == null) {
            return 0;
        }
        if (tickSize.compareTo(BigDecimal.ZERO) <= 0) {
            return 0;
        }
        BigDecimal budget = plannedEdge.subtract(entryEdge);
        if (budget.compareTo(BigDecimal.ZERO) <= 0) {
            return 0;
        }
        try {
            return Math.max(0, budget.divide(tickSize, 0, RoundingMode.DOWN).intValue());
        } catch (Exception e) {
            return 0;
        }
    }

    private static int[] enforceImproveBudget(int improveUp, int improveDown, int budgetTicks) {
        int up = Math.max(0, improveUp);
        int down = Math.max(0, improveDown);
        int budget = Math.max(0, budgetTicks);

        while (up + down > budget) {
            if (up > down && up > 0) {
                up--;
                continue;
            }
            if (down > up && down > 0) {
                down--;
                continue;
            }
            if (up == down) {
                if (up <= 0) {
                    break;
                }
                if (ThreadLocalRandom.current().nextBoolean()) {
                    up--;
                } else {
                    down--;
                }
                continue;
            }
            if (up > 0) {
                up--;
            } else if (down > 0) {
                down--;
            } else {
                break;
            }
        }
        return new int[]{up, down};
    }

    private void maybeTakeToken(GabagoolMarket market, String tokenId, Direction direction,
                                 TopOfBook book, TopOfBook otherBook, GabagoolConfig cfg, long secondsToEnd, double sizeFactor) {
        if (tokenId == null || book == null) return;

        BigDecimal bestAsk = book.bestAsk();
        BigDecimal tickSize = getTickSize(tokenId);
        BigDecimal maxPrice = tickSize == null || tickSize.compareTo(BigDecimal.ZERO) <= 0
                ? BigDecimal.valueOf(0.99)
                : BigDecimal.ONE.subtract(tickSize);
        if (bestAsk == null || bestAsk.compareTo(maxPrice) > 0) return;

        BigDecimal exposure = quoteCalculator.calculateExposure(orderManager.getOpenOrders(), positionTracker.getAllInventories());
        BigDecimal shares = quoteCalculator.calculateShares(market, bestAsk, cfg, secondsToEnd, exposure, sizeFactor);
        if (shares == null) return;

        OrderState existing = orderManager.getOrder(tokenId);
        if (existing != null) {
            long ageMillis = Duration.between(existing.placedAt(), clock.instant()).toMillis();
            if (ageMillis < cfg.minReplaceMillis()) return;
            orderManager.cancelOrder(tokenId, CancelReason.REPLACE_PRICE, secondsToEnd, book, otherBook);
        }

        log.info("GABAGOOL: TAKER {} order on {} at ask {} (size={}, secondsToEnd={})",
                direction, market.slug(), bestAsk, shares, secondsToEnd);
        orderManager.placeOrder(market, tokenId, direction, bestAsk, shares, secondsToEnd, null, book, otherBook, existing, PlaceReason.TAKER);
    }

    private void maybeFastTopUp(GabagoolMarket market, MarketInventory inv, TopOfBook upBook,
                                TopOfBook downBook, GabagoolConfig cfg, long secondsToEnd) {
        if (!cfg.completeSetFastTopUpEnabled()) return;

        BigDecimal imbalance = inv.imbalance();
        BigDecimal absImbalance = imbalance.abs();
        if (absImbalance.compareTo(cfg.completeSetFastTopUpMinShares()) < 0) return;

        Instant now = clock.instant();
        if (inv.lastTopUpAt() != null &&
                Duration.between(inv.lastTopUpAt(), now).toMillis() < cfg.completeSetFastTopUpCooldownMillis()) {
            return;
        }

        Direction laggingLeg = imbalance.compareTo(BigDecimal.ZERO) > 0 ? Direction.DOWN : Direction.UP;
        Instant leadFillAt = laggingLeg == Direction.DOWN ? inv.lastUpFillAt() : inv.lastDownFillAt();
        if (leadFillAt == null) return;

        FastTopUpDecision decision = fastTopUpDecisionByMarket.get(market.slug());
        if (decision != null && leadFillAt.equals(decision.leadFillAt()) && !decision.allowFastTopUp()) {
            return;
        }

        long sinceLeadFillSeconds = Duration.between(leadFillAt, now).getSeconds();
        if (sinceLeadFillSeconds < cfg.completeSetFastTopUpMinSecondsAfterFill() ||
                sinceLeadFillSeconds > cfg.completeSetFastTopUpMaxSecondsAfterFill()) {
            return;
        }

        Instant lagFillAt = laggingLeg == Direction.DOWN ? inv.lastDownFillAt() : inv.lastUpFillAt();
        if (lagFillAt != null && !lagFillAt.isBefore(leadFillAt)) return;

        TopOfBook laggingBook = laggingLeg == Direction.UP ? upBook : downBook;
        TopOfBook otherBook = laggingLeg == Direction.UP ? downBook : upBook;
        String laggingTokenId = laggingLeg == Direction.UP ? market.upTokenId() : market.downTokenId();

        if (laggingBook.bestBid() == null || laggingBook.bestAsk() == null) return;
        BigDecimal spread = laggingBook.bestAsk().subtract(laggingBook.bestBid());
        if (spread.compareTo(takerMaxSpreadForMarket(cfg, market)) > 0) return;

        BigDecimal leadFillPrice = laggingLeg == Direction.DOWN ? inv.lastUpFillPrice() : inv.lastDownFillPrice();
        if (leadFillPrice == null) {
            leadFillPrice = laggingLeg == Direction.DOWN ? upBook.bestBid() : downBook.bestBid();
        }
        if (leadFillPrice != null) {
            BigDecimal hedgedEdge = BigDecimal.ONE.subtract(leadFillPrice.add(laggingBook.bestAsk()));
            if (hedgedEdge.compareTo(BigDecimal.valueOf(cfg.completeSetFastTopUpMinEdge())) < 0) return;
        }

        // Leave residual imbalance (fractional hedge) to match target user's per-market imbalance distribution.
        BigDecimal requestedShares = absImbalance.multiply(BigDecimal.valueOf(cfg.completeSetFastTopUpFraction()))
                .setScale(2, RoundingMode.DOWN);
        if (requestedShares.compareTo(BigDecimal.valueOf(0.01)) < 0) return;

        positionTracker.markTopUp(market.slug());
        maybeTopUpLaggingLeg(market, laggingTokenId, laggingLeg, laggingBook, otherBook, cfg, secondsToEnd, requestedShares, PlaceReason.FAST_TOP_UP);
    }

    private void maybeTopUpLaggingLeg(GabagoolMarket market, String tokenId, Direction direction,
                                      TopOfBook book, TopOfBook otherBook, GabagoolConfig cfg,
                                      long secondsToEnd, BigDecimal imbalanceShares, PlaceReason reason) {
        if (tokenId == null || book == null) return;
        if (imbalanceShares == null || imbalanceShares.compareTo(BigDecimal.valueOf(0.01)) < 0) return;

        BigDecimal bestAsk = book.bestAsk();
        BigDecimal tickSize = getTickSize(tokenId);
        BigDecimal maxPrice = tickSize == null || tickSize.compareTo(BigDecimal.ZERO) <= 0
                ? BigDecimal.valueOf(0.99)
                : BigDecimal.ONE.subtract(tickSize);
        if (bestAsk == null || bestAsk.compareTo(maxPrice) > 0) return;

        BigDecimal bestBid = book.bestBid();
        if (bestBid != null) {
            BigDecimal spread = bestAsk.subtract(bestBid);
            if (spread.compareTo(takerMaxSpreadForMarket(cfg, market)) > 0) return;
        }

        BigDecimal topUpShares = imbalanceShares;
        BigDecimal bankrollUsd = bankrollService.resolveEffective(cfg);

        if (bankrollUsd != null && bankrollUsd.compareTo(BigDecimal.ZERO) > 0) {
            if (cfg.maxOrderBankrollFraction() > 0) {
                BigDecimal perOrderCap = bankrollUsd.multiply(BigDecimal.valueOf(cfg.maxOrderBankrollFraction()));
                BigDecimal capShares = perOrderCap.divide(bestAsk, 2, RoundingMode.DOWN);
                topUpShares = topUpShares.min(capShares);
            }
            if (cfg.maxTotalBankrollFraction() > 0) {
                BigDecimal totalCap = bankrollUsd.multiply(BigDecimal.valueOf(cfg.maxTotalBankrollFraction()));
                BigDecimal exposure = quoteCalculator.calculateExposure(orderManager.getOpenOrders(), positionTracker.getAllInventories());
                BigDecimal remaining = totalCap.subtract(exposure);
                if (remaining.compareTo(BigDecimal.ZERO) <= 0) return;
                BigDecimal capShares = remaining.divide(bestAsk, 2, RoundingMode.DOWN);
                topUpShares = topUpShares.min(capShares);
            }
        }

        BigDecimal maxNotionalUsd = properties.risk().maxOrderNotionalUsd();
        if (maxNotionalUsd != null && maxNotionalUsd.compareTo(BigDecimal.ZERO) > 0) {
            BigDecimal capShares = maxNotionalUsd.divide(bestAsk, 2, RoundingMode.DOWN);
            topUpShares = topUpShares.min(capShares);
        }

        BigDecimal maxOrderSize = properties.risk().maxOrderSize();
        if (maxOrderSize != null && maxOrderSize.compareTo(BigDecimal.ZERO) > 0) {
            topUpShares = topUpShares.min(maxOrderSize);
        }

        topUpShares = topUpShares.setScale(2, RoundingMode.DOWN);
        if (topUpShares.compareTo(BigDecimal.valueOf(0.01)) < 0) return;

        OrderState existing = orderManager.getOrder(tokenId);
        if (existing != null) {
            long ageMillis = Duration.between(existing.placedAt(), clock.instant()).toMillis();
            if (ageMillis < cfg.minReplaceMillis()) return;
            orderManager.cancelOrder(tokenId, CancelReason.REPLACE_PRICE, secondsToEnd, book, otherBook);
        }

        log.info("GABAGOOL: TOP-UP {} on {} at ask {} (imbalance={}, topUpShares={}, secondsToEnd={})",
                direction, market.slug(), bestAsk, imbalanceShares, topUpShares, secondsToEnd);
        orderManager.placeOrder(market, tokenId, direction, bestAsk, topUpShares, secondsToEnd, null, book, otherBook, existing, reason);
    }

    private boolean shouldTake(BigDecimal edge, TopOfBook upBook, TopOfBook downBook, GabagoolConfig cfg, GabagoolMarket market) {
        if (!cfg.takerModeEnabled()) return false;
        if (edge.doubleValue() > cfg.takerModeMaxEdge()) return false;

        BigDecimal maxSpread = takerMaxSpreadForMarket(cfg, market);
        BigDecimal upSpread = upBook.bestAsk().subtract(upBook.bestBid());
        BigDecimal downSpread = downBook.bestAsk().subtract(downBook.bestBid());

        if (upSpread.compareTo(maxSpread) > 0 || downSpread.compareTo(maxSpread) > 0) return false;

        double p = takerProbabilityForMarket(cfg, market);
        if (p < 1.0 && ThreadLocalRandom.current().nextDouble() > p) {
            return false;
        }

        log.debug("GABAGOOL: Taker mode triggered - edge={}, upSpread={}, downSpread={}", edge, upSpread, downSpread);
        return true;
    }

    private BigDecimal takerMaxSpreadForMarket(GabagoolConfig cfg, GabagoolMarket market) {
        return cfg.takerModeMaxSpread();
    }

    /**
     * Compute size skew factors based on PRICE LEVEL and momentum signal.
     *
     * KEY INSIGHT from gabagool22 analysis:
     * - Gab buys EXPENSIVE sides (75% of DOWN buys at >50c, only 2% at <30c)
     * - SIM was buying CHEAP sides (44% at <30c) - this is WRONG
     *
     * Price-Level Logic (PRIMARY):
     * - When a side is CHEAP (<40c): SUPPRESS buying (skew factor 0.1-0.3)
     * - When a side is MID (40c-60c): Normal buying (skew factor 0.7-1.0)
     * - When a side is EXPENSIVE (>60c): FAVOR buying (skew factor 1.0)
     *
     * Momentum Logic (SECONDARY):
     * - When UP price is RISING: bias toward LONG_UP
     * - When UP price is FALLING: bias toward LONG_DOWN
     * - When NEUTRAL: Use price-level skew
     *
     * The skew factor reduces size on the non-preferred leg.
     */
    private double[] computeSizeSkewFactors(GabagoolMarket market, BigDecimal upBid, BigDecimal downBid) {
        if (market == null || market.slug() == null) {
            return new double[]{1.0, 1.0};
        }

        // PRIMARY: Price-level based sizing (matches gab's 75% at >50c behavior)
        double upPriceSkew = computePriceLevelSkew(upBid);
        double downPriceSkew = computePriceLevelSkew(downBid);

        // Get momentum signal
        MomentumSignal signal = momentumTracker != null
                ? momentumTracker.getSignal(market.slug())
                : MomentumSignal.NEUTRAL;

        // Check for momentum flip and log it
        MomentumSignal lastSignal = lastMomentumSignal.get(market.slug());
        if (lastSignal != null && signal != lastSignal && signal != MomentumSignal.NEUTRAL) {
            log.info("GABAGOOL: Momentum FLIP on {} from {} to {}", market.slug(), lastSignal, signal);
            marketSizeSkew.remove(market.slug());
        }
        if (signal != MomentumSignal.NEUTRAL) {
            lastMomentumSignal.put(market.slug(), signal);
        }

        // SECONDARY: Momentum-based adjustment
        double[] momentumSkew = switch (signal) {
            case UP_RISING -> {
                // Strong momentum up: favor UP position
                double downMomentumSkew = 0.55 + ThreadLocalRandom.current().nextDouble(0.10);
                yield new double[]{1.0, downMomentumSkew};
            }
            case UP_FALLING -> {
                // Strong momentum down: favor DOWN position
                double upMomentumSkew = 0.55 + ThreadLocalRandom.current().nextDouble(0.10);
                yield new double[]{upMomentumSkew, 1.0};
            }
            case NEUTRAL -> new double[]{1.0, 1.0};
        };

        // Combine price-level and momentum skews (multiply them)
        double finalUpSkew = upPriceSkew * momentumSkew[0];
        double finalDownSkew = downPriceSkew * momentumSkew[1];

        // Log when we suppress a cheap side
        if (upPriceSkew < 0.5 || downPriceSkew < 0.5) {
            log.debug("GABAGOOL: Price-level skew on {} - UP bid={} (skew={}), DOWN bid={} (skew={}), momentum={}",
                    market.slug(), upBid, String.format("%.2f", upPriceSkew),
                    downBid, String.format("%.2f", downPriceSkew), signal);
        }

        return new double[]{finalUpSkew, finalDownSkew};
    }

    /**
     * Compute size skew factor based on price level.
     *
     * RECALIBRATED based on actual gabagool22 Dec 26-27 data:
     * - <30c: 15.2% of trades
     * - 30-40c: 15.4% of trades
     * - 40-50c: 16.7% of trades
     * - 50-60c: 17.6% of trades
     * - >60c: 35.1% of trades (1.75x baseline)
     *
     * Previous values were too aggressive at suppressing cheap prices.
     */
    private double computePriceLevelSkew(BigDecimal bid) {
        if (bid == null) {
            return 0.8;
        }

        double price = bid.doubleValue();

        if (price < 0.30) {
            // Very cheap (<30c): Slight suppression (gab 15.2% vs baseline ~20%)
            // skew = 15.2/20 = 0.76
            return 0.70 + ThreadLocalRandom.current().nextDouble(0.10);
        } else if (price < 0.40) {
            // Cheap (30-40c): Slight suppression (gab 15.4% vs baseline ~20%)
            // skew = 15.4/20 = 0.77
            return 0.72 + ThreadLocalRandom.current().nextDouble(0.10);
        } else if (price < 0.50) {
            // Lower-mid (40-50c): Near baseline (gab 16.7% vs baseline ~20%)
            // skew = 16.7/20 = 0.84
            return 0.80 + ThreadLocalRandom.current().nextDouble(0.10);
        } else if (price < 0.60) {
            // Upper-mid (50-60c): Near baseline (gab 17.6% vs baseline ~20%)
            // skew = 17.6/20 = 0.88
            return 0.85 + ThreadLocalRandom.current().nextDouble(0.10);
        } else {
            // Expensive (>60c): BOOST (gab 35.1% vs baseline ~20%)
            // skew = 35.1/20 = 1.76, but cap at 1.2 to avoid over-concentration
            return 1.0 + ThreadLocalRandom.current().nextDouble(0.20);
        }
    }

	    private boolean shouldSkipLaggingLeg(double sizeFactor) {
	        if (sizeFactor >= 0.999) {
	            return false;
	        }
	        // RECALIBRATED: Gab trades both sides nearly equally (47% Up, 53% Down).
	        // Previous value 0.60 caused cheap UP to be skipped too often.
	        // Increase to 0.95 to ensure both sides are quoted consistently.
	        double quoteProb = 0.95;
	        return ThreadLocalRandom.current().nextDouble() > quoteProb;
	    }

    private void maybeCancelLaggingOnFill(OrderState state, GabagoolConfig cfg) {
        if (state == null || state.market() == null || state.direction() == null) {
            return;
        }
        if (cfg == null || !cfg.completeSetHedgeDelayEnabled()) {
            return;
        }

        String slug = state.market().slug();
        MarketInventory inv = positionTracker.getInventory(slug);
        Instant leadFillAt = state.direction() == Direction.UP ? inv.lastUpFillAt() : inv.lastDownFillAt();
        if (leadFillAt == null) {
            return;
        }

        boolean allowFastTopUp = ThreadLocalRandom.current().nextDouble() <= cfg.completeSetFastTopUpProbability();
        fastTopUpDecisionByMarket.put(slug, new FastTopUpDecision(leadFillAt, allowFastTopUp));
        if (allowFastTopUp) {
            return;
        }

        // Slow-hedge path: cancel lagging order and extend the hedge hold window. Uses the full
        // lead→lag delay distribution from sampleHedgeDelaySeconds() - including [2-5s] bucket with
        // 36% weight to match gabagool22's hedge timing (47% in [2-5s]).
        Direction laggingLeg = state.direction() == Direction.UP ? Direction.DOWN : Direction.UP;
        String laggingTokenId = laggingLeg == Direction.UP ? state.market().upTokenId() : state.market().downTokenId();
        long secondsToEnd = Duration.between(clock.instant(), state.market().endTime()).getSeconds();
        orderManager.cancelOrder(laggingTokenId, CancelReason.HEDGE_DELAY, secondsToEnd, null, null);

        long slowMin = Math.max(0L, cfg.completeSetHedgeDelayMinSeconds());  // Allow [2-5s] bucket
        long slowMax = Math.max(slowMin, cfg.completeSetHedgeDelayMaxSeconds());
        long delaySeconds = sampleHedgeDelaySeconds(slowMin, slowMax);
        hedgeHoldUntil.put(hedgeKey(state.market(), laggingLeg), clock.instant().plusSeconds(delaySeconds));
    }

    private void maybeMarkHedgeDelay(GabagoolMarket market, Direction leadLeg, GabagoolConfig cfg) {
        if (market == null || market.slug() == null || leadLeg == null) {
            return;
        }
        if (cfg == null || !cfg.completeSetHedgeDelayEnabled()) {
            return;
        }
        long minSeconds = Math.max(0L, cfg.completeSetHedgeDelayMinSeconds());
        long maxSeconds = Math.max(minSeconds, cfg.completeSetHedgeDelayMaxSeconds());
        if (maxSeconds <= 0) {
            return;
        }
        long delaySeconds = minSeconds == maxSeconds
                ? minSeconds
                : sampleHedgeDelaySeconds(minSeconds, maxSeconds);
        Direction laggingLeg = leadLeg == Direction.UP ? Direction.DOWN : Direction.UP;
        Instant until = clock.instant().plusSeconds(delaySeconds);
        hedgeHoldUntil.put(hedgeKey(market, laggingLeg), until);
    }

    private long sampleHedgeDelaySeconds(long minSeconds, long maxSeconds) {
        long min = Math.max(0L, minSeconds);
        long max = Math.max(min, maxSeconds);
        if (max <= min) {
            return min;
        }

        long[][] buckets = new long[][]{
                {2, 5},
                {5, 10},
                {10, 30},
                {30, 60},
                {60, 120},
                {120, 300}   // Extended to 300s to match gab's actual distribution (avg 211s for >120s bucket)
        };
        // RECALIBRATED: Actual gabagool22 hedge delay distribution (Dec 26-27 data):
        // GAB: 2-5s=4.8%, 5-10s=4.4%, 10-30s=10%, 30-60s=3.7%, 60-120s=29.5%, >120s=45.9%
        // Previous weights were 7x too fast (36% at 2-5s vs gab's 4.8%)
        double[] weights = new double[]{0.05, 0.05, 0.10, 0.04, 0.30, 0.46};

        double totalWeight = 0.0;
        long[] lower = new long[buckets.length];
        long[] upper = new long[buckets.length];
        for (int i = 0; i < buckets.length; i++) {
            long lo = Math.max(min, buckets[i][0]);
            long hi = Math.min(max, buckets[i][1]);
            if (lo <= hi) {
                lower[i] = lo;
                upper[i] = hi;
                totalWeight += weights[i];
            } else {
                lower[i] = 1;
                upper[i] = 0;
            }
        }

        if (totalWeight <= 0.0) {
            return ThreadLocalRandom.current().nextLong(min, max + 1);
        }

        double r = ThreadLocalRandom.current().nextDouble() * totalWeight;
        for (int i = 0; i < weights.length; i++) {
            if (lower[i] > upper[i]) {
                continue;
            }
            r -= weights[i];
            if (r <= 0.0) {
                return ThreadLocalRandom.current().nextLong(lower[i], upper[i] + 1);
            }
        }
        return ThreadLocalRandom.current().nextLong(min, max + 1);
    }

    private boolean isHedgeDelayActive(GabagoolMarket market, Direction leg, GabagoolConfig cfg) {
        if (market == null || market.slug() == null || leg == null) {
            return false;
        }
        if (cfg == null || !cfg.completeSetHedgeDelayEnabled()) {
            return false;
        }
        String key = hedgeKey(market, leg);
        Instant until = hedgeHoldUntil.get(key);
        if (until == null) {
            return false;
        }
        Instant now = clock.instant();
        if (now.isBefore(until)) {
            return true;
        }
        hedgeHoldUntil.remove(key, until);
        return false;
    }

    private String hedgeKey(GabagoolMarket market, Direction leg) {
        return market.slug() + ":" + leg.name();
    }

	    private double takerProbabilityForMarket(GabagoolConfig cfg, GabagoolMarket market) {
	        double p = cfg.takerModeProbability();
	        if (market == null || market.slug() == null) {
	            return p;
	        }
	        String slug = market.slug();
	        if (slug.startsWith("btc-updown-15m-")) {
	            p *= 1.10;
	        } else if (slug.startsWith("eth-updown-15m-")) {
	            p *= 1.00;
	        } else if (slug.startsWith("bitcoin-up-or-down-")) {
	            p *= 0.85;
	        } else if (slug.startsWith("ethereum-up-or-down-")) {
	            p *= 1.10;
	        }
	        if (p < 0.0) return 0.0;
	        if (p > 1.0) return 1.0;
	        return p;
	    }

    private Direction decideTakerLeg(MarketInventory inv, TopOfBook upBook, TopOfBook downBook, GabagoolConfig cfg,
                                     double upSizeFactor, double downSizeFactor) {
	        BigDecimal bidUp = upBook.bestBid(), askUp = upBook.bestAsk();
	        BigDecimal bidDown = downBook.bestBid(), askDown = downBook.bestAsk();
	        if (bidUp == null || askUp == null || bidDown == null || askDown == null) return null;

	        BigDecimal edgeTakeUp = BigDecimal.ONE.subtract(askUp.add(bidDown));
	        BigDecimal edgeTakeDown = BigDecimal.ONE.subtract(bidUp.add(askDown));
	        // For entry takers, require non-negative hedged edge (allow breakeven; avoid meaningfully negative crossings).
	        // Note: baseline taker trades cluster tightly around 0 due to TOB snapshot noise + spread cost.
	        boolean upOk = edgeTakeUp.compareTo(BigDecimal.ZERO) >= 0;
	        boolean downOk = edgeTakeDown.compareTo(BigDecimal.ZERO) >= 0;

        if (!upOk && !downOk) return null;
        if (upOk && !downOk) return Direction.UP;
        if (downOk && !upOk) return Direction.DOWN;

        double skewDelta = Math.abs(upSizeFactor - downSizeFactor);
        if (skewDelta >= 0.05) {
            return upSizeFactor >= downSizeFactor ? Direction.UP : Direction.DOWN;
        }

        int cmp = edgeTakeUp.compareTo(edgeTakeDown);
        if (cmp > 0) return Direction.UP;
        if (cmp < 0) return Direction.DOWN;

        BigDecimal imbalance = inv.imbalance();
        if (imbalance.compareTo(BigDecimal.ZERO) > 0) return Direction.DOWN;
        if (imbalance.compareTo(BigDecimal.ZERO) < 0) return Direction.UP;
        return Direction.UP;
    }

    private void discoverMarkets() {
        try {
            List<GabagoolMarket> markets = new ArrayList<>();

            List<GabagoolMarketDiscovery.DiscoveredMarket> discovered = marketDiscovery.getActiveMarkets();
            for (GabagoolMarketDiscovery.DiscoveredMarket d : discovered) {
                markets.add(new GabagoolMarket(d.slug(), d.upTokenId(), d.downTokenId(), d.endTime(), d.marketType()));
            }

            GabagoolConfig cfg = getConfig();
            if (cfg.markets() != null) {
                for (GabagoolConfig.GabagoolMarketConfig m : cfg.markets()) {
                    if (m.upTokenId() != null && m.downTokenId() != null) {
                        Instant endTime = m.endTime() != null ? m.endTime() : clock.instant().plus(Duration.ofMinutes(15));
                        String upToken = m.upTokenId();
                        boolean exists = markets.stream().anyMatch(existing -> existing.upTokenId().equals(upToken));
                        if (!exists) {
                            markets.add(new GabagoolMarket(
                                    m.slug() != null ? m.slug() : "configured",
                                    m.upTokenId(), m.downTokenId(), endTime, "unknown"
                            ));
                        }
                    }
                }
            }

            activeMarkets.set(markets);
            metricsService.updateActiveMarketsCount(markets.size());
            if (cfg.bankrollUsd() != null) metricsService.updateBankroll(cfg.bankrollUsd());

            List<String> assetIds = markets.stream()
                    .flatMap(m -> Stream.of(m.upTokenId(), m.downTokenId()))
                    .filter(Objects::nonNull)
                    .filter(s -> !s.isBlank())
                    .distinct()
                    .toList();
            if (!assetIds.isEmpty()) marketWs.setSubscribedAssets(assetIds);

            if (!markets.isEmpty()) {
                log.debug("GABAGOOL: Tracking {} markets ({} discovered, {} configured)",
                        markets.size(), discovered.size(), cfg.markets() != null ? cfg.markets().size() : 0);
            }
        } catch (Exception e) {
            log.error("GABAGOOL: Error discovering markets: {}", e.getMessage());
        }
    }

    private GabagoolConfig getConfig() {
        return GabagoolConfig.from(properties.strategy().gabagool());
    }

    private BigDecimal getTickSize(String tokenId) {
        TickSizeEntry cached = tickSizeCache.get(tokenId);
        if (cached != null && Duration.between(cached.fetchedAt(), clock.instant()).compareTo(TICK_SIZE_CACHE_TTL) < 0) {
            return cached.tickSize();
        }
        try {
            BigDecimal tickSize = executorApi.getTickSize(tokenId);
            tickSizeCache.put(tokenId, new TickSizeEntry(tickSize, clock.instant()));
            return tickSize;
        } catch (Exception e) {
            log.warn("Failed to get tick size for {}: {}", tokenId, e.getMessage());
            return BigDecimal.valueOf(0.01);
        }
    }

    private boolean isStale(TopOfBook tob) {
        if (tob == null || tob.updatedAt() == null) return true;
        // Widened from 5s to 15s to allow more tolerance during WS reconnects
        return Duration.between(tob.updatedAt(), clock.instant()).toMillis() > 15_000;
    }

    private void logStartupConfig(GabagoolConfig cfg) {
        log.info("gabagool strategy config loaded (enabled={}, refreshMillis={}, quoteSizeUsd={}, bankrollUsd={})",
                cfg.enabled(), cfg.refreshMillis(), cfg.quoteSize(), cfg.bankrollUsd());
        log.info("gabagool complete-set config (minEdge={}, cancelEdge={}, maxSkewTicks={}, topUpEnabled={}, fastTopUpEnabled={})",
                cfg.completeSetMinEdge(), cfg.completeSetCancelEdge(), cfg.completeSetMaxSkewTicks(),
                cfg.completeSetTopUpEnabled(), cfg.completeSetFastTopUpEnabled());
        log.info("gabagool taker-mode config (enabled={}, maxEdge={}, maxSpread={}, probability={})",
                cfg.takerModeEnabled(), cfg.takerModeMaxEdge(), cfg.takerModeMaxSpread(), cfg.takerModeProbability());
    }

    public record TickSizeEntry(BigDecimal tickSize, Instant fetchedAt) {}
}
