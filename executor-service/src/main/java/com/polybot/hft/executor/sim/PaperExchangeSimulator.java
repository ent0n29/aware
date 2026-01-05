package com.polybot.hft.executor.sim;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.polybot.hft.config.HftProperties;
import com.polybot.hft.domain.OrderSide;
import com.polybot.hft.events.HftEventPublisher;
import com.polybot.hft.events.HftEventTypes;
import com.polybot.hft.executor.events.ExecutorOrderStatusEvent;
import com.polybot.hft.polymarket.api.LimitOrderRequest;
import com.polybot.hft.polymarket.api.MarketOrderRequest;
import com.polybot.hft.polymarket.api.OrderSubmissionResult;
import com.polybot.hft.polymarket.data.PolymarketPosition;
import com.polybot.hft.polymarket.gamma.PolymarketGammaClient;
import com.polybot.hft.polymarket.clob.PolymarketClobClient;
import com.polybot.hft.polymarket.data.PolymarketDataApiClient;
import com.polybot.hft.polymarket.ws.ClobMarketWebSocketClient;
import com.polybot.hft.polymarket.ws.TopOfBook;
import lombok.NonNull;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import jakarta.annotation.PostConstruct;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.ThreadLocalRandom;
import java.util.concurrent.atomic.AtomicLong;

/**
 * A lightweight "paper exchange" simulator for local testing.
 *
 * Goals:
 * - Exercise the full strategy/executor lifecycle without touching real funds
 * - Provide realistic-ish order status transitions (OPEN -> PARTIAL -> FILLED/CANCELED)
 * - Optionally publish simulated polymarket.user.trade events so ClickHouse views/analysis can run
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class PaperExchangeSimulator {

  private static final String USER_TRADE_EVENT_TYPE = "polymarket.user.trade";
  private static final int DEFAULT_SEEN_TRADE_TAPE_KEYS_CAPACITY = 500_000;
  private static final HttpClient CLICKHOUSE_HTTP =
      HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build();

  private final @NonNull HftProperties hft;
  private final @NonNull ExecutorSimulationProperties sim;
  private final @NonNull ObjectMapper objectMapper;
  private final @NonNull Clock clock;
  private final @NonNull HftEventPublisher events;
  private final @NonNull ClobMarketWebSocketClient marketWs;
  private final @NonNull PolymarketGammaClient gammaClient;
  private final @NonNull PolymarketDataApiClient dataApi;
  private final @NonNull PolymarketClobClient clobClient;

  private final ConcurrentMap<String, SimOrder> ordersById = new ConcurrentHashMap<>();
  private final ConcurrentMap<String, Position> positionsByTokenId = new ConcurrentHashMap<>();
  private final ConcurrentMap<String, TokenMeta> metaByTokenId = new ConcurrentHashMap<>();
  private final ConcurrentMap<String, BigDecimal> tickSizeByTokenId = new ConcurrentHashMap<>();
  private final ConcurrentMap<String, LastFill> lastFillByConditionId = new ConcurrentHashMap<>();
  private final EvictingKeySet seenTradeTapeKeys = new EvictingKeySet(DEFAULT_SEEN_TRADE_TAPE_KEYS_CAPACITY);
  private final ConcurrentMap<String, Instant> lastTradeTapePrintAtByTokenId = new ConcurrentHashMap<>();
  private final ConcurrentMap<String, LastTradeTapePrint> lastEligibleTradeTapePrintByTokenId = new ConcurrentHashMap<>();
  private final ConcurrentMap<String, BidSnapshot> lastBestBidSnapshotByTokenId = new ConcurrentHashMap<>();

  private final AtomicLong tradeTapePolls = new AtomicLong();
  private final AtomicLong tradeTapePrints = new AtomicLong();
  private final AtomicLong tradeTapeMatchedPrints = new AtomicLong();
  private final AtomicLong tradeTapePriceMatches = new AtomicLong();
  private final AtomicLong tradeTapeLeadLagBlocks = new AtomicLong();
  private final AtomicLong tradeTapePreOrderSkips = new AtomicLong();
  private final AtomicLong tradeTapeQueueBlocks = new AtomicLong();
  private final AtomicLong tradeTapeFills = new AtomicLong();
  private volatile long lastTradeTapeStatsLoggedAtMillis;

  private volatile long lastTradeTapePollAtMillis;

  @PostConstruct
  void logSimConfig() {
    if (!enabled()) {
      log.info("paper-exchange simulator disabled");
      return;
    }
    log.info(
        "paper-exchange simulator enabled (fillsEnabled={}, fillPollMillis={}, tobMaxAgeMs={}, makerMinAgeMs={}, leadLagMinMs={}, makerP0={}, makerMultPerTick={}, makerPMax={}, makerFillFrac={}, queueFactor=[{},{}], tradeTapeEnabled={}, tradeTapeSource={}, tradeTapePollMs={}, tradeTapeLimit={}, tradeTapeUseTs={}, tradeTapeFallbackEnabled={}, tradeTapeFallbackMaxIdleMs={}, tradeTapeFallbackPScale={}, bidDeltaCancelScale={}, bidDeltaMaxTradeLagMs={}, chUrl={}, chDb={}, chLookbackSec={})",
        sim.fillsEnabled(),
        sim.fillPollMillis(),
        sim.tobMaxAgeMillis(),
        sim.makerFillMinAgeMillis(),
        sim.leadLagMinMillis(),
        sim.makerFillProbabilityPerPoll(),
        sim.makerFillProbabilityMultiplierPerTick(),
        sim.makerFillProbabilityMaxPerPoll(),
        sim.makerFillFractionOfRemaining(),
        sim.makerQueueFactorMin(),
        sim.makerQueueFactorMax(),
        sim.tradeTapeEnabled(),
        sim.tradeTapeSource(),
        sim.tradeTapePollMillis(),
        sim.tradeTapeLimit(),
        sim.tradeTapeUseTradeTimestamp(),
        sim.tradeTapeFallbackEnabled(),
        sim.tradeTapeFallbackMaxIdleMillis(),
        sim.tradeTapeFallbackProbabilityScale(),
        sim.tradeTapeBidDeltaCancelScale(),
        sim.tradeTapeBidDeltaMaxTradeLagMillis(),
        sim.tradeTapeClickhouseUrl(),
        sim.tradeTapeClickhouseDatabase(),
        sim.tradeTapeClickhouseLookbackSeconds()
    );
  }

  public boolean enabled() {
    return Boolean.TRUE.equals(sim.enabled());
  }

  public OrderSubmissionResult placeLimitOrder(LimitOrderRequest request) {
    Objects.requireNonNull(request, "request");
    marketWs.subscribeAssets(List.of(request.tokenId()));
    String orderId = "sim-" + UUID.randomUUID();
    BigDecimal size = request.size() == null ? BigDecimal.ZERO : request.size();
    BigDecimal matched = BigDecimal.ZERO;
    BigDecimal remaining = size.max(BigDecimal.ZERO);
    TopOfBook placedTob = marketWs.getTopOfBook(request.tokenId()).orElse(null);
    BigDecimal placedBestAsk = placedTob == null ? null : placedTob.bestAsk();
    BigDecimal placedBestBid = placedTob == null ? null : placedTob.bestBid();
    BigDecimal placedBestBidSize = placedTob == null ? null : placedTob.bestBidSize();
    BigDecimal price = request.price();
    boolean makerAtPlacement = false;
    boolean takerAtPlacement = false;
    if (price != null) {
      if (request.side() == OrderSide.SELL) {
        makerAtPlacement = placedBestBid != null && price.compareTo(placedBestBid) > 0;
        takerAtPlacement = placedBestBid != null && price.compareTo(placedBestBid) <= 0;
      } else {
        makerAtPlacement = placedBestAsk != null && price.compareTo(placedBestAsk) < 0;
        takerAtPlacement = placedBestAsk != null && price.compareTo(placedBestAsk) >= 0;
      }
    }
    double queueFactor = request.side() == OrderSide.BUY
        ? ThreadLocalRandom.current().nextDouble(sim.makerQueueFactorMin(), sim.makerQueueFactorMax())
        : 1.0;

    BigDecimal queueAheadShares = null;
    if (request.side() == OrderSide.BUY) {
      // Queue-ahead proxy for maker BUY orders:
      // initialize "shares ahead of us at this price level" from TOB size, scaled by a random factor.
      //
      // When we improve above the best bid (bid+1, bid+2, ...), we likely have less queue ahead.
      if (placedBestBidSize != null && placedBestBidSize.compareTo(BigDecimal.ZERO) > 0 && placedBestBid != null && price != null) {
        int ticksAboveBestBid = 0;
        try {
          BigDecimal diff = price.subtract(placedBestBid);
          if (diff.compareTo(BigDecimal.ZERO) > 0) {
            BigDecimal tick = tickSize(request.tokenId());
            if (tick.compareTo(BigDecimal.ZERO) > 0) {
              ticksAboveBestBid = diff.divide(tick, 0, RoundingMode.DOWN).intValue();
            }
          }
        } catch (Exception ignored) {
        }
        BigDecimal base = ticksAboveBestBid > 0 ? BigDecimal.ZERO : placedBestBidSize;
        queueAheadShares = base.multiply(BigDecimal.valueOf(queueFactor)).setScale(2, RoundingMode.DOWN);
      }
    }

    SimOrder order = new SimOrder(
        orderId,
        request.tokenId(),
        request.side(),
        request.price(),
        size,
        Instant.now(clock),
        "OPEN",
        matched,
        remaining,
        makerAtPlacement,
        queueFactor,
        queueAheadShares
    );
    ordersById.put(orderId, order);
    publishOrderStatus(order, null);
    if (Boolean.TRUE.equals(sim.fillsEnabled()) && takerAtPlacement) {
      BigDecimal fillPrice = request.side() == OrderSide.SELL ? placedBestBid : placedBestAsk;
      if (fillPrice != null) {
        // Respect lead→lag floor even for taker-at-placement fills, otherwise we can create
        // unrealistically fast (<2s) opposite-leg fills compared to the baseline data.
        boolean allowImmediateFill = true;
        if (sim.leadLagMinMillis() > 0) {
          TokenMeta meta = resolveTokenMeta(order.tokenId).orElse(null);
          if (meta == null || meta.conditionId == null || meta.conditionId.isBlank() || meta.outcome == null || meta.outcome.isBlank()) {
            allowImmediateFill = false;
          } else {
            LastFill last = lastFillByConditionId.get(meta.conditionId);
            if (last != null && last.outcome() != null && !last.outcome().equals(meta.outcome)) {
              long lagMs = Duration.between(last.ts(), clock.instant()).toMillis();
              if (lagMs >= 0 && lagMs < sim.leadLagMinMillis()) {
                allowImmediateFill = false;
              }
            }
          }
        }
        if (allowImmediateFill) {
          fill(order, order.remainingSize, fillPrice, "TAKER");
        }
      }
    }

    ObjectNode resp = objectMapper.createObjectNode()
        .put("mode", "SIM")
        .put("orderID", orderId)
        .put("orderId", orderId)
        .put("status", "OPEN");
    return new OrderSubmissionResult(hft.mode(), null, resp);
  }

  public OrderSubmissionResult placeMarketOrder(MarketOrderRequest request) {
    Objects.requireNonNull(request, "request");
    marketWs.subscribeAssets(List.of(request.tokenId()));

    String orderId = "sim-" + UUID.randomUUID();
    TopOfBook tob = marketWs.getTopOfBook(request.tokenId()).orElse(null);
    if (tob == null || tob.bestBid() == null || tob.bestAsk() == null) {
      ObjectNode resp = objectMapper.createObjectNode()
          .put("mode", "SIM")
          .put("orderID", orderId)
          .put("orderId", orderId)
          .put("status", "REJECTED")
          .put("reason", "no_tob");
      return new OrderSubmissionResult(hft.mode(), null, resp);
    }

    BigDecimal limitPrice = request.price();
    if (limitPrice == null) {
      limitPrice = BigDecimal.ONE;
    }

    if (request.side() == OrderSide.BUY) {
      BigDecimal bestAsk = tob.bestAsk();
      if (bestAsk.compareTo(limitPrice) > 0) {
        ObjectNode resp = objectMapper.createObjectNode()
            .put("mode", "SIM")
            .put("orderID", orderId)
            .put("orderId", orderId)
            .put("status", "REJECTED")
            .put("reason", "ask_above_limit");
        return new OrderSubmissionResult(hft.mode(), null, resp);
      }

      BigDecimal notionalUsd = request.amount();
      if (notionalUsd == null || notionalUsd.compareTo(BigDecimal.ZERO) <= 0) {
        ObjectNode resp = objectMapper.createObjectNode()
            .put("mode", "SIM")
            .put("orderID", orderId)
            .put("orderId", orderId)
            .put("status", "REJECTED")
            .put("reason", "amount_invalid");
        return new OrderSubmissionResult(hft.mode(), null, resp);
      }

      BigDecimal shares = notionalUsd.divide(bestAsk, 2, RoundingMode.DOWN);
      if (shares.compareTo(BigDecimal.valueOf(0.01)) < 0) {
        ObjectNode resp = objectMapper.createObjectNode()
            .put("mode", "SIM")
            .put("orderID", orderId)
            .put("orderId", orderId)
            .put("status", "REJECTED")
            .put("reason", "shares_too_small");
        return new OrderSubmissionResult(hft.mode(), null, resp);
      }

      SimOrder order = new SimOrder(
          orderId,
          request.tokenId(),
          request.side(),
          bestAsk,
          shares,
          Instant.now(clock),
          "FILLED",
          shares,
          BigDecimal.ZERO,
          false,
          1.0,
          BigDecimal.ZERO
      );
      ordersById.put(orderId, order);

      positionsByTokenId.compute(order.tokenId, (k, prev) -> {
        Position cur = prev == null ? new Position(BigDecimal.ZERO, BigDecimal.ZERO) : prev;
        BigDecimal nextShares = cur.shares.add(shares);
        BigDecimal nextCost = cur.costUsd.add(bestAsk.multiply(shares));
        return new Position(nextShares, nextCost);
      });

      publishOrderStatus(order, null);
      publishUserTrade(order, shares, bestAsk, "TAKER");

      ObjectNode resp = objectMapper.createObjectNode()
          .put("mode", "SIM")
          .put("orderID", orderId)
          .put("orderId", orderId)
          .put("status", "FILLED");
      return new OrderSubmissionResult(hft.mode(), null, resp);
    }

    if (request.side() == OrderSide.SELL) {
      BigDecimal bestBid = tob.bestBid();
      if (bestBid.compareTo(limitPrice) < 0) {
        ObjectNode resp = objectMapper.createObjectNode()
            .put("mode", "SIM")
            .put("orderID", orderId)
            .put("orderId", orderId)
            .put("status", "REJECTED")
            .put("reason", "bid_below_limit");
        return new OrderSubmissionResult(hft.mode(), null, resp);
      }

      BigDecimal shares = request.amount();
      if (shares == null || shares.compareTo(BigDecimal.valueOf(0.01)) < 0) {
        ObjectNode resp = objectMapper.createObjectNode()
            .put("mode", "SIM")
            .put("orderID", orderId)
            .put("orderId", orderId)
            .put("status", "REJECTED")
            .put("reason", "amount_invalid");
        return new OrderSubmissionResult(hft.mode(), null, resp);
      }

      SimOrder order = new SimOrder(
          orderId,
          request.tokenId(),
          request.side(),
          bestBid,
          shares,
          Instant.now(clock),
          "FILLED",
          shares,
          BigDecimal.ZERO,
          false,
          1.0,
          BigDecimal.ZERO
      );
      ordersById.put(orderId, order);

      positionsByTokenId.compute(order.tokenId, (k, prev) -> {
        Position cur = prev == null ? new Position(BigDecimal.ZERO, BigDecimal.ZERO) : prev;
        BigDecimal nextShares = cur.shares.subtract(shares);
        BigDecimal nextCost = cur.costUsd.subtract(bestBid.multiply(shares));
        return new Position(nextShares, nextCost);
      });

      publishOrderStatus(order, null);
      publishUserTrade(order, shares, bestBid, "TAKER");

      ObjectNode resp = objectMapper.createObjectNode()
          .put("mode", "SIM")
          .put("orderID", orderId)
          .put("orderId", orderId)
          .put("status", "FILLED");
      return new OrderSubmissionResult(hft.mode(), null, resp);
    }

    ObjectNode resp = objectMapper.createObjectNode()
        .put("mode", "SIM")
        .put("orderID", orderId)
        .put("orderId", orderId)
        .put("status", "REJECTED")
        .put("reason", "unsupported_side");
    return new OrderSubmissionResult(hft.mode(), null, resp);
  }

  public JsonNode cancelOrder(String orderId) {
    if (orderId == null || orderId.isBlank()) {
      return objectMapper.createObjectNode().put("canceled", false);
    }
    SimOrder order = ordersById.get(orderId);
    if (order == null) {
      return objectMapper.createObjectNode()
          .put("mode", "SIM")
          .put("canceled", false)
          .put("orderId", orderId);
    }
    synchronized (order) {
      if (isTerminal(order.status)) {
        return objectMapper.createObjectNode()
            .put("mode", "SIM")
            .put("canceled", false)
            .put("orderId", orderId)
            .put("status", order.status);
      }
      order.status = "CANCELED";
    }
    publishOrderStatus(order, null);
    return objectMapper.createObjectNode()
        .put("mode", "SIM")
        .put("canceled", true)
        .put("orderId", orderId)
        .put("status", "CANCELED");
  }

  public JsonNode getOrder(String orderId) {
    if (orderId == null || orderId.isBlank()) {
      return objectMapper.createObjectNode().put("error", "orderId blank");
    }
    SimOrder order = ordersById.get(orderId);
    if (order == null) {
      return objectMapper.createObjectNode()
          .put("mode", "SIM")
          .put("orderId", orderId)
          .put("status", "UNKNOWN");
    }
    synchronized (order) {
      return objectMapper.createObjectNode()
          .put("mode", "SIM")
          .put("orderId", order.orderId)
          .put("tokenId", order.tokenId)
          .put("side", order.side == null ? null : order.side.name())
          .put("status", order.status)
          .put("matched_size", order.matchedSize == null ? 0.0 : order.matchedSize.doubleValue())
          .put("remaining_size", order.remainingSize == null ? 0.0 : order.remainingSize.doubleValue())
          .put("requestedPrice", order.requestedPrice == null ? null : order.requestedPrice.doubleValue())
          .put("requestedSize", order.requestedSize == null ? null : order.requestedSize.doubleValue());
    }
  }

  public PolymarketPosition[] getPositions(int limit, int offset) {
    if (limit <= 0) {
      limit = 200;
    }
    if (offset < 0) {
      offset = 0;
    }

    List<Map.Entry<String, Position>> snapshot = new ArrayList<>(positionsByTokenId.entrySet());
    snapshot.sort(Comparator.comparing(Map.Entry::getKey));

    int from = Math.min(offset, snapshot.size());
    int to = Math.min(snapshot.size(), from + limit);
    List<PolymarketPosition> out = new ArrayList<>();
    for (int i = from; i < to; i++) {
      Map.Entry<String, Position> e = snapshot.get(i);
      if (e == null) {
        continue;
      }
      String tokenId = e.getKey();
      Position p = e.getValue();
      if (tokenId == null || p == null) {
        continue;
      }
      BigDecimal shares = p.shares();
      if (shares == null || shares.compareTo(BigDecimal.ZERO) == 0) {
        continue;
      }
      TokenMeta meta = resolveTokenMeta(tokenId).orElse(null);
      out.add(new PolymarketPosition(
          sim.proxyAddress(),
          tokenId,
          meta == null ? null : meta.conditionId(),
          shares,
          p.avgPrice(),
          p.costUsd(),
          null,
          null,
          null,
          meta == null ? null : bestEffortCurPrice(tokenId),
          false,
          null,
          meta == null ? null : meta.title(),
          meta == null ? null : meta.marketSlug(),
          meta == null ? null : meta.outcome(),
          meta == null ? null : meta.outcomeIndex(),
          null,
          null,
          null
      ));
    }
    return out.toArray(PolymarketPosition[]::new);
  }

  @Scheduled(
      initialDelayString = "5000",
      fixedDelayString = "${executor.sim.fill-poll-millis:250}"
  )
  void simulateFills() {
    if (!enabled()) {
      return;
    }
    if (!Boolean.TRUE.equals(sim.fillsEnabled())) {
      return;
    }

    if (Boolean.TRUE.equals(sim.tradeTapeEnabled())) {
      maybePollTradeTapeAndFill();
    }

    for (SimOrder order : ordersById.values()) {
      if (order == null) {
        continue;
      }
      simulateOne(order);
    }
  }

  private record TradePrint(
      String conditionId,
      String tokenId,
      String side,
      BigDecimal price,
      BigDecimal size,
      Instant ts,
      String transactionHash
  ) {
  }

  private BigDecimal tickSize(String tokenId) {
    if (tokenId == null || tokenId.isBlank()) {
      return BigDecimal.valueOf(0.001);
    }
    BigDecimal cached = tickSizeByTokenId.get(tokenId);
    if (cached != null && cached.compareTo(BigDecimal.ZERO) > 0) {
      return cached;
    }
    try {
      BigDecimal ts = clobClient.getMinimumTickSize(tokenId.trim());
      if (ts == null || ts.compareTo(BigDecimal.ZERO) <= 0) {
        ts = BigDecimal.valueOf(0.001);
      }
      tickSizeByTokenId.put(tokenId, ts);
      return ts;
    } catch (Exception e) {
      BigDecimal fallback = BigDecimal.valueOf(0.001);
      tickSizeByTokenId.put(tokenId, fallback);
      return fallback;
    }
  }

  private static int tickScale(BigDecimal tickSize) {
    if (tickSize == null) {
      return 3;
    }
    try {
      return Math.max(0, tickSize.stripTrailingZeros().scale());
    } catch (Exception ignored) {
      return 3;
    }
  }

  private static BigDecimal quantizeToTick(BigDecimal price, BigDecimal tickSize, RoundingMode roundingMode) {
    if (price == null) {
      return null;
    }
    if (tickSize == null || tickSize.compareTo(BigDecimal.ZERO) <= 0) {
      return price;
    }
    BigDecimal q = price.divide(tickSize, 0, roundingMode).multiply(tickSize);
    return q.setScale(tickScale(tickSize), roundingMode);
  }

  private boolean isMakerLikeBuyOrder(SimOrder order) {
    if (order == null || order.side != OrderSide.BUY) {
      return false;
    }
    if (order.requestedPrice == null) {
      return false;
    }
    TopOfBook tob = marketWs.getTopOfBook(order.tokenId).orElse(null);
    if (tob == null || tob.bestAsk() == null) {
      // If we don't have a book snapshot, assume maker-like so that we don't incorrectly fall back to
      // the probabilistic fill model while trade tape mode is enabled.
      return true;
    }
    return order.requestedPrice.compareTo(tob.bestAsk()) < 0;
  }

  private void maybeInitQueueAheadShares(SimOrder order) {
    if (order == null || order.side != OrderSide.BUY) {
      return;
    }
    if (order.queueAheadShares != null) {
      return;
    }
    if (order.requestedPrice == null) {
      return;
    }

    TopOfBook tob = marketWs.getTopOfBook(order.tokenId).orElse(null);
    if (tob == null || tob.bestBid() == null || tob.bestBidSize() == null) {
      return;
    }

    BigDecimal bestBid = tob.bestBid();
    BigDecimal bestBidSize = tob.bestBidSize();
    if (bestBidSize.compareTo(BigDecimal.ZERO) <= 0) {
      return;
    }

    BigDecimal queueAhead;
    if (order.requestedPrice.compareTo(bestBid) > 0) {
      // We improved above the best bid (and did not cross the ask), so we likely have little to no queue ahead.
      queueAhead = BigDecimal.ZERO;
    } else {
      double factor = order.queueFactor > 0 ? order.queueFactor : 1.0;
      queueAhead = bestBidSize.multiply(BigDecimal.valueOf(factor)).setScale(2, RoundingMode.DOWN);
    }

    synchronized (order) {
      if (order.queueAheadShares == null) {
        order.queueAheadShares = queueAhead.max(BigDecimal.ZERO);
      }
    }
  }

  private void maybePollTradeTapeAndFill() {
    long pollMillis = sim.tradeTapePollMillis();
    long nowMillis = Instant.now(clock).toEpochMilli();
    if (pollMillis > 0 && nowMillis - lastTradeTapePollAtMillis < pollMillis) {
      return;
    }
    lastTradeTapePollAtMillis = nowMillis;

    int limit = Math.max(1, sim.tradeTapeLimit());
    tradeTapePolls.incrementAndGet();

    // Only poll conditions/tokens that have at least one active maker-like BUY order.
    java.util.Set<String> tokenIds = new java.util.HashSet<>();
    for (SimOrder order : ordersById.values()) {
      if (order == null || isTerminal(order.status)) {
        continue;
      }
      if (order.side != OrderSide.BUY) {
        continue;
      }
      if (!isMakerLikeBuyOrder(order)) {
        continue;
      }
      if (order.tokenId == null || order.tokenId.isBlank()) {
        continue;
      }
      tokenIds.add(order.tokenId);
    }
    if (tokenIds.isEmpty()) {
      return;
    }

    java.util.Set<String> conditionIds = new java.util.HashSet<>();
    for (String tokenId : tokenIds) {
      TokenMeta meta = resolveTokenMeta(tokenId).orElse(null);
      if (meta == null || meta.conditionId == null || meta.conditionId.isBlank()) {
        continue;
      }
      conditionIds.add(meta.conditionId);
    }

    List<TradePrint> newTrades = new ArrayList<>();
    String source = sim.tradeTapeSource() == null ? "" : sim.tradeTapeSource().trim().toUpperCase(Locale.ROOT);
    boolean useClickhouseWsTrades = "CLICKHOUSE_MARKET_WS_TRADES".equals(source)
        || "CLICKHOUSE_WS_TRADES".equals(source)
        || "CH_WS_TRADES".equals(source);
    boolean useClickhouseMarketTrades = "CLICKHOUSE_MARKET_TRADES".equals(source) || "CLICKHOUSE".equals(source) || "CH_MARKET_TRADES".equals(source);
    boolean useDataApi = "DATA_API".equals(source);
    boolean useBidDelta = "WS_BID_DELTA".equals(source);

    if (useClickhouseWsTrades) {
      newTrades.addAll(fetchClickhouseMarketWsTrades(tokenIds, limit));
    } else if (useClickhouseMarketTrades) {
      newTrades.addAll(fetchClickhouseMarketTrades(tokenIds, limit));
    } else if (useDataApi) {
      if (conditionIds.isEmpty()) {
        return;
      }
      for (String conditionId : conditionIds) {
        JsonNode node;
        try {
          node = dataApi.getMarketTrades(conditionId, limit, 0);
        } catch (Exception e) {
          continue;
        }
        if (node == null || !node.isArray()) {
          continue;
        }

        // Data API returns newest first; iterate backwards to process oldest→newest.
        for (int i = node.size() - 1; i >= 0; i--) {
          JsonNode trade = node.get(i);
          if (trade == null || trade.isNull()) {
            continue;
          }
          String tx = trade.path("transactionHash").asText(null);
          String tokenId = trade.path("asset").asText(null);
          String side = trade.path("side").asText(null);
          long tsRaw = trade.path("timestamp").asLong(0);
          if (tx == null || tx.isBlank() || tokenId == null || tokenId.isBlank() || side == null || side.isBlank() || tsRaw <= 0) {
            continue;
          }
          String sideNorm = side.trim().toUpperCase(java.util.Locale.ROOT);
          if (!"SELL".equals(sideNorm)) {
            // For maker-like BUY orders, only SELL prints (taker sells into bids) can hit our resting bid.
            continue;
          }

          String key = conditionId + ":" + tx.trim() + ":" + tokenId.trim() + ":" + sideNorm + ":" + tsRaw;
          if (!seenTradeTapeKeys.add(key)) {
            continue;
          }

          BigDecimal price = null;
          BigDecimal size = null;
          try {
            if (trade.hasNonNull("price")) {
              price = new BigDecimal(trade.get("price").asText());
            }
            if (trade.hasNonNull("size")) {
              size = new BigDecimal(trade.get("size").asText());
            }
          } catch (Exception ignored) {
          }
          if (price == null || size == null || size.compareTo(BigDecimal.valueOf(0.01)) < 0) {
            continue;
          }

          String reportedConditionId = trade.path("conditionId").asText(null);
          if (reportedConditionId != null && !reportedConditionId.isBlank() && !reportedConditionId.equals(conditionId)) {
            continue;
          }

          Instant ts = tsRaw > 1_000_000_000_000L ? Instant.ofEpochMilli(tsRaw) : Instant.ofEpochSecond(tsRaw);

          newTrades.add(new TradePrint(
              conditionId,
              tokenId,
              sideNorm,
              price,
              size,
              ts,
              tx.trim()
          ));
        }
      }
    } else if (useBidDelta) {
      // WS top-of-book prints: infer "sell volume at bid" from best-bid size decreases while the best bid
      // price is unchanged. This captures repeated prints at the same price level (which last_trade_price
      // events can miss) and provides a size signal without polling data-api.
      for (String tokenId : tokenIds) {
        if (tokenId == null || tokenId.isBlank()) {
          continue;
        }
        TopOfBook tob = marketWs.getTopOfBook(tokenId).orElse(null);
        if (tob == null || tob.bestBid() == null || tob.bestBidSize() == null || tob.updatedAt() == null) {
          continue;
        }

        BigDecimal tick = tickSize(tokenId);
        BigDecimal bestBidQ = quantizeToTick(tob.bestBid(), tick, RoundingMode.HALF_UP);
        BigDecimal bestBidSize = tob.bestBidSize();
        if (bestBidQ == null || bestBidSize.compareTo(BigDecimal.ZERO) <= 0) {
          continue;
        }

        BidSnapshot prev = lastBestBidSnapshotByTokenId.put(
            tokenId,
            new BidSnapshot(bestBidQ, bestBidSize, tob.updatedAt(), tob.lastTradeAt(), tob.lastTradePrice())
        );
        if (prev == null) {
          continue;
        }
        if (prev.bestBid() == null || prev.bestBidSize() == null) {
          continue;
        }
        if (prev.bestBid().compareTo(bestBidQ) != 0) {
          continue; // price moved -> no reliable size delta
        }
        BigDecimal delta = prev.bestBidSize().subtract(bestBidSize);
        if (delta.compareTo(BigDecimal.valueOf(0.01)) < 0) {
          continue;
        }

        // Cap extreme spikes (cancellations can also reduce visible size).
        BigDecimal maxDelta = BigDecimal.valueOf(500);
        if (delta.compareTo(maxDelta) > 0) {
          delta = maxDelta;
        }

        // If lastTradeAt advanced since the previous snapshot, treat the delta as trade-confirmed.
        // Otherwise, scale down because cancellations can also reduce visible size.
        boolean tradeConfirmed = false;
        if (tob.lastTradeAt() != null && tob.updatedAt() != null) {
          Instant prevTradeAt = prev.lastTradeAt();
          Instant currTradeAt = tob.lastTradeAt();
          if (prevTradeAt == null || (currTradeAt != null && currTradeAt.isAfter(prevTradeAt))) {
            long lagMs = Math.abs(Duration.between(currTradeAt, tob.updatedAt()).toMillis());
            if (lagMs <= sim.tradeTapeBidDeltaMaxTradeLagMillis()) {
              BigDecimal lastPx = tob.lastTradePrice();
              BigDecimal lastPxQ = lastPx == null ? null : quantizeToTick(lastPx, tick, RoundingMode.HALF_UP);
              // Only treat as "sell-like at bid" when last trade prints at/below the bid.
              if (lastPxQ == null || lastPxQ.compareTo(bestBidQ) <= 0) {
                tradeConfirmed = true;
              }
            }
          }
        }
        if (!tradeConfirmed) {
          double scale = sim.tradeTapeBidDeltaCancelScale();
          if (scale <= 0) {
            continue;
          }
          delta = delta.multiply(BigDecimal.valueOf(scale));
        }

        delta = delta.setScale(2, RoundingMode.DOWN);
        if (delta.compareTo(BigDecimal.valueOf(0.01)) < 0) {
          continue;
        }

        // Prefer the WS last-trade timestamp when available (closer to the actual print time than the book update time).
        Instant printAt = (tradeConfirmed && tob.lastTradeAt() != null) ? tob.lastTradeAt() : tob.updatedAt();
        if (printAt == null) {
          continue;
        }
        long tsRaw = printAt.toEpochMilli();
        String key = "WS_BID_DELTA:" + tokenId.trim() + ":" + tsRaw + ":" + bestBidQ + ":" + delta;
        if (!seenTradeTapeKeys.add(key)) {
          continue;
        }

        TokenMeta meta = resolveTokenMeta(tokenId).orElse(null);
        String conditionId = meta == null ? null : meta.conditionId();

        newTrades.add(new TradePrint(
            conditionId,
            tokenId,
            "SELL",
            bestBidQ,
            delta,
            printAt,
            key
        ));
      }
    } else {
      // WS tape is real-time but does not include size. We synthesize a size and only emit SELL-like prints
      // (i.e., trades at/near the bid) that can plausibly hit resting BUY orders.
      for (String tokenId : tokenIds) {
        if (tokenId == null || tokenId.isBlank()) {
          continue;
        }
        TopOfBook tob = marketWs.getTopOfBook(tokenId).orElse(null);
        if (tob == null || tob.bestBid() == null || tob.bestAsk() == null || tob.lastTradePrice() == null || tob.lastTradeAt() == null) {
          continue;
        }

        BigDecimal tick = tickSize(tokenId);
        BigDecimal bestBidQ = quantizeToTick(tob.bestBid(), tick, RoundingMode.HALF_UP);
        BigDecimal bestAskQ = quantizeToTick(tob.bestAsk(), tick, RoundingMode.HALF_UP);
        BigDecimal lastPriceQ = quantizeToTick(tob.lastTradePrice(), tick, RoundingMode.HALF_UP);
        if (bestBidQ == null || bestAskQ == null || lastPriceQ == null) {
          continue;
        }

        boolean sellLike;
        if (lastPriceQ.compareTo(bestBidQ) <= 0) {
          sellLike = true;
        } else if (lastPriceQ.compareTo(bestAskQ) >= 0) {
          sellLike = false;
        } else {
          BigDecimal mid = bestBidQ.add(bestAskQ).divide(BigDecimal.valueOf(2), tickScale(tick), RoundingMode.HALF_UP);
          sellLike = lastPriceQ.compareTo(mid) <= 0;
        }
        if (!sellLike) {
          continue;
        }

        long tsRaw = tob.lastTradeAt().toEpochMilli();
        String key = "WS:" + tokenId.trim() + ":" + tsRaw + ":" + lastPriceQ;
        if (!seenTradeTapeKeys.add(key)) {
          continue;
        }

        BigDecimal size = synthesizeWsTradeSize(tob.bestBidSize());
        if (size == null || size.compareTo(BigDecimal.valueOf(0.01)) < 0) {
          continue;
        }

        TokenMeta meta = resolveTokenMeta(tokenId).orElse(null);
        String conditionId = meta == null ? null : meta.conditionId();

        newTrades.add(new TradePrint(
            conditionId,
            tokenId,
            "SELL",
            lastPriceQ,
            size,
            tob.lastTradeAt(),
            key
        ));
      }
    }

    if (newTrades.isEmpty()) {
      return;
    }

    tradeTapePrints.addAndGet(newTrades.size());

    // Process prints in timestamp order (best-effort).
    newTrades.sort(java.util.Comparator.comparing(TradePrint::ts));
    for (TradePrint t : newTrades) {
      applyTradePrintToOrders(t);
    }

    // Periodic stats log (helps validate that trade-tape polling is working).
    long statsIntervalMs = 30_000L;
    if (nowMillis - lastTradeTapeStatsLoggedAtMillis > statsIntervalMs) {
      lastTradeTapeStatsLoggedAtMillis = nowMillis;
      log.info(
          "SIM trade-tape stats: polledConditions={} polls={} prints={} matchedPrints={} priceMatches={} preOrderSkips={} leadLagBlocks={} queueBlocks={} fills={}",
          conditionIds.size(),
          tradeTapePolls.get(),
          tradeTapePrints.get(),
          tradeTapeMatchedPrints.get(),
          tradeTapePriceMatches.get(),
          tradeTapePreOrderSkips.get(),
          tradeTapeLeadLagBlocks.get(),
          tradeTapeQueueBlocks.get(),
          tradeTapeFills.get()
      );
    }
  }

  private List<TradePrint> fetchClickhouseMarketTrades(java.util.Set<String> tokenIds, int limit) {
    if (tokenIds == null || tokenIds.isEmpty()) {
      return List.of();
    }
    String url = sim.tradeTapeClickhouseUrl();
    String database = sim.tradeTapeClickhouseDatabase();
    if (url == null || url.isBlank() || database == null || database.isBlank()) {
      return List.of();
    }

    int lookbackSeconds = Math.max(1, sim.tradeTapeClickhouseLookbackSeconds());
    int perTokenLimit = Math.max(1, limit);

    List<String> ids = new ArrayList<>(tokenIds);
    // Keep SQL payloads bounded.
    int chunkSize = 40;

    List<TradePrint> out = new ArrayList<>();
    for (int offset = 0; offset < ids.size(); offset += chunkSize) {
      List<String> chunk = ids.subList(offset, Math.min(ids.size(), offset + chunkSize));
      if (chunk.isEmpty()) {
        continue;
      }

      StringBuilder in = new StringBuilder();
      for (int i = 0; i < chunk.size(); i++) {
        if (i > 0) {
          in.append(",");
        }
        // token_id is numeric-like; still escape single quotes defensively.
        String id = chunk.get(i) == null ? "" : chunk.get(i).replace("'", "");
        in.append("'").append(id).append("'");
      }

      String sql =
          "SELECT "
              + "toUnixTimestamp64Milli(ts) AS ts_ms,"
              + "condition_id, token_id, side, price, size, transaction_hash, event_key "
              + "FROM polybot.market_trades "
              + "WHERE token_id IN (" + in + ") "
              + "  AND side = 'SELL' "
              + "  AND ts >= now() - INTERVAL " + lookbackSeconds + " SECOND "
              + "ORDER BY ts DESC "
              + "LIMIT " + perTokenLimit + " BY token_id "
              + "FORMAT JSONEachRow";

      String body = postClickhouse(url, database, sql);
      if (body == null || body.isBlank()) {
        continue;
      }
      for (String line : body.split("\n")) {
        String trimmed = line.trim();
        if (trimmed.isEmpty()) {
          continue;
        }
        try {
          JsonNode node = objectMapper.readTree(trimmed);
          if (node == null || node.isNull()) {
            continue;
          }
          String tokenId = node.path("token_id").asText(null);
          if (tokenId == null || tokenId.isBlank()) {
            continue;
          }
          String side = node.path("side").asText(null);
          if (side == null || side.isBlank()) {
            continue;
          }
          String sideNorm = side.trim().toUpperCase(Locale.ROOT);
          if (!"SELL".equals(sideNorm)) {
            continue;
          }

          long tsMs = node.path("ts_ms").asLong(0);
          if (tsMs <= 0) {
            continue;
          }
          String eventKey = node.path("event_key").asText(null);
          String tx = node.path("transaction_hash").asText(null);

          String key = "CH:" + (eventKey != null && !eventKey.isBlank() ? eventKey.trim() : (tokenId + ":" + tsMs + ":" + sideNorm));
          if (!seenTradeTapeKeys.add(key)) {
            continue;
          }

          BigDecimal price;
          BigDecimal size;
          try {
            price = new BigDecimal(node.get("price").asText());
            size = new BigDecimal(node.get("size").asText());
          } catch (Exception e) {
            continue;
          }
          if (size.compareTo(BigDecimal.valueOf(0.01)) < 0) {
            continue;
          }
          String conditionId = node.path("condition_id").asText(null);
          out.add(new TradePrint(
              conditionId,
              tokenId,
              sideNorm,
              price,
              size,
              Instant.ofEpochMilli(tsMs),
              tx != null ? tx.trim() : key
          ));
        } catch (Exception ignored) {
        }
      }
    }

    return out;
  }

  private List<TradePrint> fetchClickhouseMarketWsTrades(java.util.Set<String> tokenIds, int limit) {
    if (tokenIds == null || tokenIds.isEmpty()) {
      return List.of();
    }
    String url = sim.tradeTapeClickhouseUrl();
    String database = sim.tradeTapeClickhouseDatabase();
    if (url == null || url.isBlank() || database == null || database.isBlank()) {
      return List.of();
    }

    int lookbackSeconds = Math.max(1, sim.tradeTapeClickhouseLookbackSeconds());
    int perTokenLimit = Math.max(1, limit);

    List<String> ids = new ArrayList<>(tokenIds);
    int chunkSize = 40;

    List<TradePrint> out = new ArrayList<>();
    for (int offset = 0; offset < ids.size(); offset += chunkSize) {
      List<String> chunk = ids.subList(offset, Math.min(ids.size(), offset + chunkSize));
      if (chunk.isEmpty()) {
        continue;
      }

      StringBuilder in = new StringBuilder();
      for (int i = 0; i < chunk.size(); i++) {
        if (i > 0) {
          in.append(",");
        }
        String id = chunk.get(i) == null ? "" : chunk.get(i).replace("'", "");
        in.append("'").append(id).append("'");
      }

      String sql =
          "SELECT "
              + "toUnixTimestamp64Milli(ts) AS ts_ms,"
              + "asset_id, side, price, size, transaction_hash, event_key "
              + "FROM polybot.market_ws_trades "
              + "WHERE asset_id IN (" + in + ") "
              + "  AND side = 'SELL' "
              + "  AND ts >= now() - INTERVAL " + lookbackSeconds + " SECOND "
              + "ORDER BY ts DESC "
              + "LIMIT " + perTokenLimit + " BY asset_id "
              + "FORMAT JSONEachRow";

      String body = postClickhouse(url, database, sql);
      if (body == null || body.isBlank()) {
        continue;
      }
      for (String line : body.split("\n")) {
        String trimmed = line.trim();
        if (trimmed.isEmpty()) {
          continue;
        }
        try {
          JsonNode node = objectMapper.readTree(trimmed);
          if (node == null || node.isNull()) {
            continue;
          }
          String tokenId = node.path("asset_id").asText(null);
          if (tokenId == null || tokenId.isBlank()) {
            continue;
          }
          String side = node.path("side").asText(null);
          if (side == null || side.isBlank()) {
            continue;
          }
          String sideNorm = side.trim().toUpperCase(Locale.ROOT);
          if (!"SELL".equals(sideNorm)) {
            continue;
          }

          long tsMs = node.path("ts_ms").asLong(0);
          if (tsMs <= 0) {
            continue;
          }
          String eventKey = node.path("event_key").asText(null);
          String tx = node.path("transaction_hash").asText(null);

          String key = "CH_WS:" + (eventKey != null && !eventKey.isBlank() ? eventKey.trim() : (tokenId + ":" + tsMs + ":" + sideNorm));
          if (!seenTradeTapeKeys.add(key)) {
            continue;
          }

          BigDecimal price;
          BigDecimal size;
          try {
            price = new BigDecimal(node.get("price").asText());
            size = new BigDecimal(node.get("size").asText());
          } catch (Exception e) {
            continue;
          }
          if (size.compareTo(BigDecimal.valueOf(0.01)) < 0) {
            continue;
          }

          TokenMeta meta = resolveTokenMeta(tokenId).orElse(null);
          String conditionId = meta == null ? null : meta.conditionId();

          out.add(new TradePrint(
              conditionId,
              tokenId,
              sideNorm,
              price,
              size,
              Instant.ofEpochMilli(tsMs),
              tx != null ? tx.trim() : key
          ));
        } catch (Exception ignored) {
        }
      }
    }

    return out;
  }

  private String postClickhouse(String url, String database, String sql) {
    try {
      String base = url == null ? "" : url.trim();
      if (base.endsWith("/")) {
        base = base.substring(0, base.length() - 1);
      }

      StringBuilder q = new StringBuilder();
      q.append("database=").append(URLEncoder.encode(database, StandardCharsets.UTF_8));
      String user = sim.tradeTapeClickhouseUser();
      String password = sim.tradeTapeClickhousePassword();
      if (user != null && !user.isBlank()) {
        q.append("&user=").append(URLEncoder.encode(user.trim(), StandardCharsets.UTF_8));
      }
      if (password != null && !password.isBlank()) {
        q.append("&password=").append(URLEncoder.encode(password, StandardCharsets.UTF_8));
      }

      URI uri = URI.create(base + "/?" + q);
      HttpRequest req =
          HttpRequest.newBuilder(uri)
              .timeout(Duration.ofSeconds(5))
              .header("Content-Type", "text/plain; charset=utf-8")
              .POST(HttpRequest.BodyPublishers.ofString(sql))
              .build();
      HttpResponse<String> resp = CLICKHOUSE_HTTP.send(req, HttpResponse.BodyHandlers.ofString());
      if (resp.statusCode() != 200) {
        log.debug("ClickHouse trade-tape query failed status={} body={}", resp.statusCode(), resp.body());
        return null;
      }
      return resp.body();
    } catch (Exception e) {
      log.debug("ClickHouse trade-tape query error: {}", e.getMessage());
      return null;
    }
  }

  private BigDecimal synthesizeWsTradeSize(BigDecimal bestBidSize) {
    // WS "last_trade_price" events do not include size. We synthesize a print size that is:
    // - non-zero
    // - small enough to avoid instant unrealistic fills
    // - large enough to occasionally consume queue ahead
    BigDecimal max = BigDecimal.valueOf(200);
    BigDecimal min = BigDecimal.valueOf(1);
    if (bestBidSize == null || bestBidSize.compareTo(BigDecimal.ZERO) <= 0) {
      double sample = ThreadLocalRandom.current().nextDouble(5.0, 25.0);
      return BigDecimal.valueOf(sample).setScale(2, RoundingMode.DOWN);
    }

    double frac = ThreadLocalRandom.current().nextDouble(0.02, 0.15);
    BigDecimal candidate = bestBidSize.multiply(BigDecimal.valueOf(frac));
    if (candidate.compareTo(min) < 0) {
      candidate = min;
    }
    if (candidate.compareTo(max) > 0) {
      candidate = max;
    }
    return candidate.setScale(2, RoundingMode.DOWN);
  }

  private record BidSnapshot(
      BigDecimal bestBid,
      BigDecimal bestBidSize,
      Instant updatedAt,
      Instant lastTradeAt,
      BigDecimal lastTradePrice
  ) {}

  private void applyTradePrintToOrders(TradePrint trade) {
    if (trade == null) {
      return;
    }
    if (trade.tokenId == null || trade.tokenId.isBlank() || trade.price == null || trade.size == null) {
      return;
    }
    lastTradeTapePrintAtByTokenId.put(trade.tokenId, trade.ts != null ? trade.ts : clock.instant());
    BigDecimal remaining = trade.size;
    if (remaining.compareTo(BigDecimal.ZERO) <= 0) {
      return;
    }

    List<SimOrder> candidates = new ArrayList<>();
    for (SimOrder order : ordersById.values()) {
      if (order == null || isTerminal(order.status)) {
        continue;
      }
      if (order.side != OrderSide.BUY) {
        continue;
      }
      if (!isMakerLikeBuyOrder(order)) {
        continue;
      }
      if (!trade.tokenId.equals(order.tokenId)) {
        continue;
      }
      candidates.add(order);
    }
    if (candidates.isEmpty()) {
      return;
    }
    tradeTapeMatchedPrints.incrementAndGet();
    candidates.sort(java.util.Comparator.comparing(o -> o.createdAt));

    for (SimOrder order : candidates) {
      if (remaining.compareTo(BigDecimal.ZERO) <= 0) {
        break;
      }
      remaining = applySellPrintToBuyOrder(order, trade, remaining);
    }
  }

  private BigDecimal applySellPrintToBuyOrder(SimOrder order, TradePrint trade, BigDecimal tradeRemaining) {
    if (order == null || trade == null || tradeRemaining == null) {
      return tradeRemaining;
    }
    if (tradeRemaining.compareTo(BigDecimal.ZERO) <= 0) {
      return tradeRemaining;
    }
    BigDecimal tick = tickSize(order.tokenId);
    BigDecimal orderPrice = quantizeToTick(order.requestedPrice, tick, RoundingMode.HALF_UP);
    if (orderPrice == null || order.remainingSize == null) {
      return tradeRemaining;
    }

    // IMPORTANT: data-api /trades `price` is frequently an average across multiple fills, so it is
    // not guaranteed to be a valid tick price (e.g., 0.5607642857...). That makes a strict
    // `tradePrice > orderPrice` eligibility check unreliable and can suppress all tape-driven fills.
    //
    // Instead, treat SELL prints as consuming bid-side liquidity at the *current* best bid.
    // Only orders at/above best bid can be hit without modeling multi-level sweep depth.
    BigDecimal tradePrice = quantizeToTick(trade.price, tick, RoundingMode.HALF_UP);
    TopOfBook tob = marketWs.getTopOfBook(order.tokenId).orElse(null);
    BigDecimal bestBid = tob == null ? null : tob.bestBid();
    BigDecimal bestAsk = tob == null ? null : tob.bestAsk();
    BigDecimal bestBidQ = bestBid == null ? null : quantizeToTick(bestBid, tick, RoundingMode.HALF_UP);
    BigDecimal bestAskQ = bestAsk == null ? null : quantizeToTick(bestAsk, tick, RoundingMode.HALF_UP);

    // If the order is not maker-like anymore (crossed ask), let the normal sim logic handle it.
    if (bestAskQ != null && orderPrice.compareTo(bestAskQ) >= 0) {
      return tradeRemaining;
    }

    int ticksBehindBestBid = 0;
    if (bestBidQ != null && bestBidQ.compareTo(orderPrice) > 0) {
      try {
        ticksBehindBestBid = bestBidQ.subtract(orderPrice).divide(tick, 0, RoundingMode.UP).intValue();
      } catch (Exception ignored) {
        ticksBehindBestBid = 1;
      }
      // If we're too far behind the current best bid, assume this print did not sweep deep enough to reach us.
      // Keep this conservative to avoid unrealistically filling stale/behind quotes.
      if (ticksBehindBestBid > 2) {
        return tradeRemaining;
      }
    } else if (bestBidQ == null && tradePrice != null) {
      // No TOB snapshot: fall back to the (avg) trade price with a 1-tick tolerance.
      if (tradePrice.compareTo(orderPrice.add(tick)) > 0) {
        return tradeRemaining;
      }
    } else if (bestBidQ == null) {
      return tradeRemaining;
    }

    if (trade.ts != null && order.createdAt != null) {
      if (isTradeTapeDataApiSource()) {
        // Data API trade timestamps are seconds-resolution. Treat the print as occurring within [ts, ts+1).
        // Only skip if the whole second ended before the order existed.
        if (trade.ts.plusSeconds(1).isBefore(order.createdAt)) {
          tradeTapePreOrderSkips.incrementAndGet();
          return tradeRemaining;
        }
      } else {
        // WS timestamps are real-time; do not extend the window past order creation.
        if (trade.ts.isBefore(order.createdAt)) {
          tradeTapePreOrderSkips.incrementAndGet();
          return tradeRemaining;
        }
      }
    }
    tradeTapePriceMatches.incrementAndGet();
    // Record the last print that plausibly traded at/through our bid level (used for fallback gating + timestamp anchoring).
    // This avoids using "any print" on the token as a timing driver when prints are occurring above our bid.
    lastEligibleTradeTapePrintByTokenId.put(order.tokenId, new LastTradeTapePrint(trade.ts, trade.transactionHash));

    // If the tape print is at a lower price than our bid, we would have improved the book and been
    // at the front of the queue (since we are not actually represented in the public trade tape).
    // If we're behind the best bid, don't attempt deterministic queue consumption/filling on this print.
    // Use the print only as a timing driver for the trade-tape fallback path.
    if (ticksBehindBestBid > 0) {
      return tradeRemaining;
    }

    if (bestBidQ != null && orderPrice.compareTo(bestBidQ) > 0) {
      synchronized (order) {
        order.queueAheadShares = BigDecimal.ZERO;
      }
    } else {
      maybeInitQueueAheadShares(order);
    }

    if (sim.leadLagMinMillis() > 0) {
      TokenMeta meta = resolveTokenMeta(order.tokenId).orElse(null);
      if (meta != null && meta.conditionId != null && !meta.conditionId.isBlank() && meta.outcome != null && !meta.outcome.isBlank()) {
        LastFill last = lastFillByConditionId.get(meta.conditionId);
        if (last != null && last.outcome() != null && !last.outcome().equals(meta.outcome)) {
          Instant base = trade.ts != null ? trade.ts : clock.instant();
          if (Boolean.TRUE.equals(sim.tradeTapeUseTradeTimestamp()) && isTradeTapeDataApiSource()) {
            base = base.plusSeconds(1);
          }
          long lagMs = Math.max(0, Duration.between(last.ts(), base).toMillis());
          if (lagMs < sim.leadLagMinMillis()) {
            tradeTapeLeadLagBlocks.incrementAndGet();
            return tradeRemaining;
          }
        }
      }
    }

    // Optional floor on maker fill eligibility. Even with trade-tape queue consumption, we should not
    // allow immediate fills on a freshly placed maker order; otherwise simulated fills become far too fast
    // relative to real queue priority dynamics.
    boolean eligibleToFill = true;
    if (order.makerAtPlacement && sim.makerFillMinAgeMillis() > 0) {
      Instant base = trade.ts != null ? trade.ts : clock.instant();
      if (Boolean.TRUE.equals(sim.tradeTapeUseTradeTimestamp()) && isTradeTapeDataApiSource()) {
        // Data API timestamps are seconds-resolution; anchor to end-of-second for conservative age.
        base = base.plusSeconds(1);
      }
      long orderAgeMs = Duration.between(order.createdAt, base).toMillis();
      if (orderAgeMs >= 0 && orderAgeMs < sim.makerFillMinAgeMillis()) {
        eligibleToFill = false;
      }
    }

    BigDecimal consumeQueue = BigDecimal.ZERO;
    BigDecimal fillSize = BigDecimal.ZERO;
    synchronized (order) {
      if (isTerminal(order.status)) {
        return tradeRemaining;
      }
      BigDecimal remaining = order.remainingSize == null ? BigDecimal.ZERO : order.remainingSize;
      if (remaining.compareTo(BigDecimal.ZERO) <= 0) {
        return tradeRemaining;
      }

      BigDecimal queueAhead = order.queueAheadShares == null ? BigDecimal.ZERO : order.queueAheadShares;
      if (queueAhead.compareTo(BigDecimal.ZERO) > 0) {
        consumeQueue = tradeRemaining.min(queueAhead).setScale(2, RoundingMode.DOWN);
        if (consumeQueue.compareTo(BigDecimal.ZERO) > 0) {
          order.queueAheadShares = queueAhead.subtract(consumeQueue);
          if (order.queueAheadShares.compareTo(BigDecimal.ZERO) < 0) {
            order.queueAheadShares = BigDecimal.ZERO;
          }
        }
      }

      BigDecimal afterQueue = tradeRemaining.subtract(consumeQueue);
      if (afterQueue.compareTo(BigDecimal.ZERO) <= 0) {
        if (consumeQueue.compareTo(BigDecimal.ZERO) > 0) {
          tradeTapeQueueBlocks.incrementAndGet();
        }
        return BigDecimal.ZERO;
      }

      if (!eligibleToFill) {
        // Queue ahead can be consumed, but we don't fill yet.
        return afterQueue;
      }

      fillSize = afterQueue.min(remaining).setScale(2, RoundingMode.DOWN);
      if (fillSize.compareTo(BigDecimal.valueOf(0.01)) < 0) {
        fillSize = BigDecimal.ZERO;
      }
    }

    BigDecimal afterQueue = tradeRemaining.subtract(consumeQueue);
    if (fillSize.compareTo(BigDecimal.ZERO) > 0) {
      // Keep tape-driven fills from being unrealistically instantaneous on large prints.
      // Reuse the same knob as the probabilistic maker fill path.
      double frac = sim.makerFillFractionOfRemaining();
      if (frac > 0 && frac < 1.0) {
        BigDecimal cap = order.remainingSize.multiply(BigDecimal.valueOf(frac)).setScale(2, RoundingMode.DOWN);
        if (cap.compareTo(BigDecimal.valueOf(0.01)) >= 0) {
          fillSize = fillSize.min(cap);
        }
      }
      Instant fillTs = Boolean.TRUE.equals(sim.tradeTapeUseTradeTimestamp()) && trade.ts != null ? trade.ts : clock.instant();
      tradeTapeFills.incrementAndGet();
      fill(order, fillSize, order.requestedPrice, "MAKER_TAPE", fillTs, trade.transactionHash);
      return afterQueue.subtract(fillSize);
    }
    return afterQueue;
  }

  private void simulateOne(SimOrder order) {
    if (order == null) {
      return;
    }
    if (order.side != OrderSide.BUY) {
      return;
    }

    TopOfBook tob = marketWs.getTopOfBook(order.tokenId).orElse(null);
    if (tob == null || tob.bestBid() == null || tob.bestAsk() == null || tob.updatedAt() == null) {
      return;
    }
    long ageMs = Math.max(0, Instant.now(clock).toEpochMilli() - tob.updatedAt().toEpochMilli());
    long maxAgeMs = sim.tobMaxAgeMillis();
    if (maxAgeMs > 0 && ageMs > maxAgeMs) {
      return;
    }

    BigDecimal bestBid = tob.bestBid();
    BigDecimal bestAsk = tob.bestAsk();
    BigDecimal bestBidSize = tob.bestBidSize();
    BigDecimal price = order.requestedPrice;
    if (price == null) {
      return;
    }

    BigDecimal tick = tickSize(order.tokenId);
    boolean tradeTapeMakerLike = Boolean.TRUE.equals(sim.tradeTapeEnabled()) && isMakerLikeBuyOrder(order);
    int ticksBelowBestBid = 0;

    if (order.makerAtPlacement && sim.makerFillMinAgeMillis() > 0) {
      long orderAgeMs = Duration.between(order.createdAt, clock.instant()).toMillis();
      if (orderAgeMs < sim.makerFillMinAgeMillis()) {
        return;
      }
    }

    boolean usingTradeTapeFallback = false;
    LastTradeTapePrint lastEligiblePrint = null;
    Instant leadLagBaseTs = clock.instant();
    if (tradeTapeMakerLike) {
      if (!Boolean.TRUE.equals(sim.tradeTapeFallbackEnabled())) {
        // Maker fills are driven by the trade tape when enabled (queue-ahead model).
        return;
      }
      lastEligiblePrint = lastEligibleTradeTapePrintByTokenId.get(order.tokenId);
      if (lastEligiblePrint == null || lastEligiblePrint.ts == null) {
        return;
      }
      long idleMs = Math.max(0, Duration.between(lastEligiblePrint.ts, clock.instant()).toMillis());
      if (idleMs > sim.tradeTapeFallbackMaxIdleMillis()) {
        return;
      }
      usingTradeTapeFallback = true;
      if (Boolean.TRUE.equals(sim.tradeTapeUseTradeTimestamp())) {
        leadLagBaseTs = lastEligiblePrint.ts.plusSeconds(1);
      }
    }

    if (sim.leadLagMinMillis() > 0) {
      TokenMeta meta = resolveTokenMeta(order.tokenId).orElse(null);
      // If we can't reliably identify condition/outcome, don't simulate a fill yet; otherwise the
      // lead→lag floor becomes under-enforced and we can generate unrealistically fast (<2s) pairs.
      if (meta == null || meta.conditionId == null || meta.conditionId.isBlank() || meta.outcome == null || meta.outcome.isBlank()) {
        return;
      }
      LastFill last = lastFillByConditionId.get(meta.conditionId);
      if (last != null && last.outcome() != null && !last.outcome().equals(meta.outcome)) {
        long lagMs = Math.max(0, Duration.between(last.ts(), leadLagBaseTs).toMillis());
        if (lagMs < sim.leadLagMinMillis()) {
          return;
        }
      }
    }

    // Crossed book -> fill immediately at best ask (taker-like). This can happen even if the order
    // was maker at placement, if the ask moves down through our resting bid later.
    if (bestAsk.compareTo(price) <= 0) {
      // If the book appears locked/crossed through our bid, treat as a maker-side fill at our
      // resting limit price (the aggressor crossed into us).
      fill(order, order.remainingSize, price, "MAKER_CROSS");
      return;
    }

    // Maker-like fill heuristic: if we're at/above the best bid, we sometimes get hit.
    if (bestBid.compareTo(price) > 0) {
      // If we're slightly behind the best bid, allow only a small "queue behind" chance under
      // trade-tape mode; otherwise we'd never fill while still sitting close to the top of book.
      try {
        BigDecimal diff = bestBid.subtract(price);
        if (diff.compareTo(BigDecimal.ZERO) > 0 && tick.compareTo(BigDecimal.ZERO) > 0) {
          ticksBelowBestBid = diff.divide(tick, 0, RoundingMode.UP).intValue();
        }
      } catch (Exception ignored) {
      }
      if (!tradeTapeMakerLike || ticksBelowBestBid > 2) {
        return;
      }
    }

    double p = sim.makerFillProbabilityPerPoll();
    if (p <= 0) {
      return;
    }
    if (usingTradeTapeFallback) {
      p = p * sim.tradeTapeFallbackProbabilityScale();
    }

    // Queue/priority proxy: if we improve above the best bid, fill odds increase.
    int ticksAboveBestBid = 0;
    try {
      BigDecimal diff = price.subtract(bestBid);
      if (diff.compareTo(BigDecimal.ZERO) > 0 && tick.compareTo(BigDecimal.ZERO) > 0) {
        ticksAboveBestBid = diff.divide(tick, 0, RoundingMode.DOWN).intValue();
      }
    } catch (Exception ignored) {
    }

    double mult = sim.makerFillProbabilityMultiplierPerTick();
    if (ticksAboveBestBid > 0 && mult > 0 && mult != 1.0) {
      p = p * Math.pow(mult, ticksAboveBestBid);
    }
    if (ticksBelowBestBid > 0) {
      // Decay fill odds when we're sitting behind the best bid (queue behind).
      p = p * Math.pow(0.25, ticksBelowBestBid);
    }
    if (bestBidSize != null && bestBidSize.compareTo(BigDecimal.ZERO) > 0) {
      BigDecimal remaining = order.remainingSize;
      if (remaining != null && remaining.compareTo(BigDecimal.ZERO) > 0) {
        BigDecimal ratio = bestBidSize.divide(remaining, 6, RoundingMode.HALF_UP);
        double sizeScale = Math.min(1.0, Math.max(0.2, ratio.doubleValue()));
        p = p * sizeScale;
      }
    }
    if (order.queueFactor > 0) {
      p = p * order.queueFactor;
    }
    double maxP = sim.makerFillProbabilityMaxPerPoll();
    if (maxP > 0) {
      p = Math.min(p, maxP);
    }
    if (p <= 0) {
      return;
    }
    if (ThreadLocalRandom.current().nextDouble() > p) {
      return;
    }
    BigDecimal remaining;
    synchronized (order) {
      remaining = order.remainingSize;
      if (remaining == null || remaining.compareTo(BigDecimal.ZERO) <= 0 || isTerminal(order.status)) {
        return;
      }
    }
    BigDecimal fill = remaining.multiply(BigDecimal.valueOf(sim.makerFillFractionOfRemaining()))
        .setScale(2, RoundingMode.DOWN);
    if (fill.compareTo(BigDecimal.valueOf(0.01)) < 0) {
      fill = remaining.min(BigDecimal.valueOf(0.01));
    }
    if (!usingTradeTapeFallback) {
      fill(order, fill, price, "MAKER");
      return;
    }

    Instant fillTs = clock.instant();
    String triggerHash = "";
    if (Boolean.TRUE.equals(sim.tradeTapeUseTradeTimestamp()) && lastEligiblePrint != null && lastEligiblePrint.ts != null) {
      fillTs = lastEligiblePrint.ts;
      triggerHash = lastEligiblePrint.transactionHash == null ? "" : lastEligiblePrint.transactionHash;
    }
    fill(order, fill, price, "MAKER_TAPE_FALLBACK", fillTs, triggerHash);
  }

  private void fill(SimOrder order, BigDecimal fillSize, BigDecimal fillPrice, String kind) {
    fill(order, fillSize, fillPrice, kind, clock.instant(), "");
  }

  private void fill(SimOrder order, BigDecimal fillSize, BigDecimal fillPrice, String kind, Instant fillTs, String triggerTransactionHash) {
    if (order == null || fillSize == null || fillPrice == null) {
      return;
    }
    if (fillSize.compareTo(BigDecimal.ZERO) <= 0) {
      return;
    }
    if (fillTs == null) {
      fillTs = clock.instant();
    }

    BigDecimal applied;
    String nextStatus;
    BigDecimal matched;
    BigDecimal remaining;
    synchronized (order) {
      if (isTerminal(order.status)) {
        return;
      }
      remaining = order.remainingSize == null ? BigDecimal.ZERO : order.remainingSize;
      if (remaining.compareTo(BigDecimal.ZERO) <= 0) {
        return;
      }
      applied = fillSize.min(remaining).setScale(2, RoundingMode.DOWN);
      if (applied.compareTo(BigDecimal.valueOf(0.01)) < 0) {
        return;
      }
      matched = (order.matchedSize == null ? BigDecimal.ZERO : order.matchedSize).add(applied);
      remaining = remaining.subtract(applied);
      if (remaining.compareTo(BigDecimal.ZERO) < 0) {
        remaining = BigDecimal.ZERO;
      }
      order.matchedSize = matched;
      order.remainingSize = remaining;
      nextStatus = remaining.compareTo(BigDecimal.ZERO) == 0 ? "FILLED" : "PARTIALLY_FILLED";
      order.status = nextStatus;
    }

    // Update positions
    positionsByTokenId.compute(order.tokenId, (k, prev) -> {
      Position cur = prev == null ? new Position(BigDecimal.ZERO, BigDecimal.ZERO) : prev;
      BigDecimal shares = cur.shares.add(applied);
      BigDecimal cost = cur.costUsd.add(fillPrice.multiply(applied));
      return new Position(shares, cost);
    });

    publishOrderStatus(order, null, fillTs);
    publishUserTrade(order, applied, fillPrice, kind, fillTs, triggerTransactionHash);
    TokenMeta meta = resolveTokenMeta(order.tokenId).orElse(null);
    if (meta != null && meta.conditionId != null && !meta.conditionId.isBlank() && meta.outcome != null && !meta.outcome.isBlank()) {
      lastFillByConditionId.put(meta.conditionId, new LastFill(meta.outcome, fillTs));
    }
  }

  private boolean isTradeTapeDataApiSource() {
    String source = sim.tradeTapeSource();
    if (source == null || source.isBlank()) {
      return false;
    }
    return "DATA_API".equalsIgnoreCase(source.trim());
  }

  private void publishUserTrade(SimOrder order, BigDecimal fillSize, BigDecimal fillPrice, String kind) {
    publishUserTrade(order, fillSize, fillPrice, kind, clock.instant(), "");
  }

  private void publishUserTrade(
      SimOrder order,
      BigDecimal fillSize,
      BigDecimal fillPrice,
      String kind,
      Instant ts,
      String transactionHash
  ) {
    if (!events.isEnabled()) {
      return;
    }
    if (order == null || fillSize == null || fillPrice == null) {
      return;
    }
    TokenMeta meta = resolveTokenMeta(order.tokenId).orElse(null);
    long tsSeconds = (ts == null ? clock.instant() : ts).getEpochSecond();

    ObjectNode trade = objectMapper.createObjectNode();
    if (meta != null) {
      trade.put("slug", meta.marketSlug);
      trade.put("title", meta.title);
      trade.put("conditionId", meta.conditionId);
      trade.put("outcome", meta.outcome);
      trade.put("outcomeIndex", meta.outcomeIndex);
    }
    trade.put("asset", order.tokenId);
    trade.put("side", order.side == null ? "BUY" : order.side.name());
    trade.put("price", fillPrice.doubleValue());
    trade.put("size", fillSize.doubleValue());
    trade.put("timestamp", tsSeconds);
    trade.put("transactionHash", transactionHash == null ? "" : transactionHash);
    trade.put("simKind", kind == null ? "" : kind);

    Map<String, Object> data = Map.of(
        "username", sim.username(),
        "proxyAddress", sim.proxyAddress(),
        "trade", trade
    );
    String key = "simtrade:" + order.orderId + ":" + UUID.randomUUID();
    events.publish((ts == null ? clock.instant() : ts), USER_TRADE_EVENT_TYPE, key, data);
  }

  private Optional<TokenMeta> resolveTokenMeta(String tokenId) {
    if (tokenId == null || tokenId.isBlank()) {
      return Optional.empty();
    }
    TokenMeta cached = metaByTokenId.get(tokenId);
    if (cached != null) {
      return Optional.of(cached);
    }
    try {
      // NOTE: CLOB /markets does not reliably support token filters; use Gamma API.
      JsonNode arr = gammaClient.markets(Map.of("clob_token_ids", tokenId.trim(), "limit", "1"), Map.of());
      if (arr == null || !arr.isArray() || arr.isEmpty()) {
        return Optional.empty();
      }
      JsonNode m = arr.get(0);
      if (m == null || m.isNull()) {
        return Optional.empty();
      }
      String marketSlug = textOrNull(m.get("slug"));
      String title = textOrNull(m.get("question"));
      String conditionId = textOrNull(m.get("conditionId"));
      if (title == null) {
        title = marketSlug;
      }

      // Gamma encodes arrays as JSON strings (e.g. outcomes='["Up","Down"]').
      String outcome = "";
      int outcomeIndex = -1;
      String clobTokenIdsRaw = textOrNull(m.get("clobTokenIds"));
      String outcomesRaw = textOrNull(m.get("outcomes"));
      if (clobTokenIdsRaw != null && outcomesRaw != null) {
        try {
          JsonNode tokenIds = objectMapper.readTree(clobTokenIdsRaw);
          JsonNode outcomes = objectMapper.readTree(outcomesRaw);
          if (tokenIds != null && tokenIds.isArray() && outcomes != null && outcomes.isArray()) {
            for (int i = 0; i < tokenIds.size(); i++) {
              JsonNode tid = tokenIds.get(i);
              if (tid == null || tid.isNull()) {
                continue;
              }
              if (tokenId.trim().equals(tid.asText("").trim())) {
                outcomeIndex = i;
                JsonNode oc = i < outcomes.size() ? outcomes.get(i) : null;
                outcome = oc == null || oc.isNull() ? "" : oc.asText("");
                break;
              }
            }
          }
        } catch (Exception ignored) {
        }
      }

      TokenMeta meta = new TokenMeta(
          marketSlug == null ? "" : marketSlug,
          title == null ? "" : title,
          conditionId == null ? "" : conditionId,
          outcome,
          outcomeIndex
      );
      metaByTokenId.put(tokenId, meta);
      return Optional.of(meta);
    } catch (Exception e) {
      log.debug("sim token meta lookup failed tokenId={} error={}", suffix(tokenId), e.toString());
      return Optional.empty();
    }
  }

  private void publishOrderStatus(SimOrder order, String error) {
    publishOrderStatus(order, error, clock.instant());
  }

  private void publishOrderStatus(SimOrder order, String error, Instant ts) {
    if (!events.isEnabled()) {
      return;
    }
    if (order == null) {
      return;
    }
    String status;
    BigDecimal matched;
    BigDecimal remaining;
    synchronized (order) {
      status = order.status;
      matched = order.matchedSize == null ? BigDecimal.ZERO : order.matchedSize;
      remaining = order.remainingSize == null ? BigDecimal.ZERO : order.remainingSize;

      boolean changed = !Objects.equals(normalize(status), normalize(order.lastPublishedStatus))
          || !decimalEq(matched, order.lastPublishedMatched)
          || !decimalEq(remaining, order.lastPublishedRemaining)
          || error != null;
      if (!changed) {
        return;
      }
      order.lastPublishedStatus = status;
      order.lastPublishedMatched = matched;
      order.lastPublishedRemaining = remaining;
    }

    String orderJson;
    try {
      orderJson = objectMapper.writeValueAsString(getOrder(order.orderId));
    } catch (Exception ignored) {
      orderJson = null;
    }

    events.publish(ts == null ? clock.instant() : ts, HftEventTypes.EXECUTOR_ORDER_STATUS, order.orderId, new ExecutorOrderStatusEvent(
        order.orderId,
        order.tokenId,
        order.side,
        order.requestedPrice,
        order.requestedSize,
        status,
        matched,
        remaining,
        orderJson,
        error
    ));
  }

  private static boolean isTerminal(String status) {
    if (status == null) {
      return false;
    }
    String s = status.trim().toUpperCase(Locale.ROOT);
    return s.contains("FILLED")
        || s.contains("CANCELED")
        || s.contains("CANCELLED")
        || s.contains("EXPIRED")
        || s.contains("REJECTED")
        || s.contains("FAILED")
        || s.contains("DONE")
        || s.contains("CLOSED");
  }

  private static boolean decimalEq(BigDecimal a, BigDecimal b) {
    if (a == null && b == null) {
      return true;
    }
    if (a == null || b == null) {
      return false;
    }
    return a.compareTo(b) == 0;
  }

  private static String normalize(String s) {
    return s == null ? null : s.trim().toUpperCase(Locale.ROOT);
  }

  private static String textOrNull(JsonNode node) {
    if (node == null || node.isNull()) {
      return null;
    }
    String s = node.asText(null);
    return s == null || s.isBlank() ? null : s.trim();
  }

  private static String suffix(String tokenId) {
    if (tokenId == null) {
      return "null";
    }
    String t = tokenId.trim();
    if (t.length() <= 6) {
      return t;
    }
    return "..." + t.substring(t.length() - 6);
  }

  private BigDecimal bestEffortCurPrice(String tokenId) {
    try {
      TopOfBook tob = marketWs.getTopOfBook(tokenId).orElse(null);
      if (tob == null) {
        return null;
      }
      BigDecimal bid = tob.bestBid();
      BigDecimal ask = tob.bestAsk();
      if (bid == null || ask == null) {
        return null;
      }
      return bid.add(ask).divide(BigDecimal.valueOf(2), 6, RoundingMode.HALF_UP);
    } catch (Exception ignored) {
      return null;
    }
  }

  private record Position(BigDecimal shares, BigDecimal costUsd) {
    private BigDecimal avgPrice() {
      if (shares == null || shares.compareTo(BigDecimal.ZERO) == 0) {
        return null;
      }
      if (costUsd == null) {
        return null;
      }
      return costUsd.divide(shares, 6, RoundingMode.HALF_UP);
    }
  }

  private record TokenMeta(
      String marketSlug,
      String title,
      String conditionId,
      String outcome,
      int outcomeIndex
  ) {
  }

  private record LastFill(String outcome, Instant ts) {
  }

  private record LastTradeTapePrint(Instant ts, String transactionHash) {
  }

  private static final class SimOrder {
    private final String orderId;
    private final String tokenId;
    private final OrderSide side;
    private final BigDecimal requestedPrice;
    private final BigDecimal requestedSize;
    private final Instant createdAt;
    private final boolean makerAtPlacement;
    private final double queueFactor;

    private String status;
    private BigDecimal matchedSize;
    private BigDecimal remainingSize;
    private BigDecimal queueAheadShares;

    private String lastPublishedStatus;
    private BigDecimal lastPublishedMatched;
    private BigDecimal lastPublishedRemaining;

    private SimOrder(
        String orderId,
        String tokenId,
        OrderSide side,
        BigDecimal requestedPrice,
        BigDecimal requestedSize,
        Instant createdAt,
        String status,
        BigDecimal matchedSize,
        BigDecimal remainingSize,
        boolean makerAtPlacement,
        double queueFactor,
        BigDecimal queueAheadShares
    ) {
      this.orderId = orderId;
      this.tokenId = tokenId;
      this.side = side;
      this.requestedPrice = requestedPrice;
      this.requestedSize = requestedSize;
      this.createdAt = createdAt;
      this.makerAtPlacement = makerAtPlacement;
      this.queueFactor = queueFactor;
      this.status = status;
      this.matchedSize = matchedSize;
      this.remainingSize = remainingSize;
      this.queueAheadShares = queueAheadShares;
    }
  }
}
