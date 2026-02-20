package com.polybot.ingestor.ingest;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.polybot.ingestor.config.IngestorProperties;
import com.polybot.ingestor.polymarket.PolymarketDataApiClient;
import lombok.NonNull;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import com.fasterxml.jackson.databind.ObjectMapper;

import java.time.Clock;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * AWARE Fund Global Trades Ingestor
 *
 * Continuously polls Polymarket for ALL trades (not filtered by user)
 * and publishes to the 'aware.events' Kafka topic for ClickHouse consumption.
 *
 * This enables building the Smart Money Index by tracking all trader activity.
 */
@Component
@ConditionalOnProperty(prefix = "ingestor.global-trades", name = "enabled", havingValue = "true")
@RequiredArgsConstructor
@Slf4j
public class PolymarketGlobalTradesIngestor {

  private static final int DEFAULT_SEEN_KEYS_CAPACITY = 500_000;
  private static final int DATA_API_MAX_LIMIT = 500;
  private static final String AWARE_TOPIC = "aware.events";
  private static final String EVENT_TYPE = "aware.global.trade";

  private final @NonNull IngestorProperties properties;
  private final @NonNull PolymarketDataApiClient dataApi;
  private final @NonNull KafkaTemplate<String, String> kafkaTemplate;
  private final @NonNull ObjectMapper objectMapper;
  private final @NonNull Clock clock;

  private final AtomicBoolean initOnce = new AtomicBoolean(false);
  private final AtomicBoolean started = new AtomicBoolean(false);
  private final AtomicBoolean pollingNow = new AtomicBoolean(false);

  private final EvictingKeySet seenTradeIds = new EvictingKeySet(DEFAULT_SEEN_KEYS_CAPACITY);

  private final AtomicLong polls = new AtomicLong(0);
  private final AtomicLong publishedTrades = new AtomicLong(0);
  private final AtomicLong skippedTrades = new AtomicLong(0);
  private final AtomicLong failures = new AtomicLong(0);

  private volatile long lastPollAtMillis;

  @EventListener(ApplicationReadyEvent.class)
  public void onReady() {
    if (!initOnce.compareAndSet(false, true)) {
      return;
    }

    log.info("============================================================");
    log.info("  AWARE Global Trades Ingestor - Starting");
    log.info("============================================================");
    log.info("  Topic: {}", AWARE_TOPIC);
    log.info("  Page size: {}", getPageSize());
    log.info("  Poll interval: {}s", getPollIntervalSeconds());
    log.info("  Dedup capacity: {} trade keys", DEFAULT_SEEN_KEYS_CAPACITY);
    log.info("============================================================");

    // Optional backfill on start
    if (isBackfillOnStart()) {
      try {
        backfill();
      } catch (Exception e) {
        failures.incrementAndGet();
        log.warn("Global trades backfill failed: {}", e.toString());
      }
    }

    started.set(true);
  }

  @Scheduled(initialDelayString = "5000", fixedDelay = 30000)
  public void poll() {
    if (!isEnabled()) {
      return;
    }
    if (!started.get()) {
      return;
    }
    if (!pollingNow.compareAndSet(false, true)) {
      return;
    }

    try {
      polls.incrementAndGet();
      lastPollAtMillis = Instant.now(clock).toEpochMilli();

      int pageSize = getPageSize();
      ArrayNode trades = dataApi.getGlobalTrades(pageSize, 0);

      if (trades.isEmpty()) {
        return;
      }

      int published = publishTrades(trades);

      if (published > 0) {
        log.info("AWARE global trades poll: fetched={} published={} total={} skipped={}",
            trades.size(), published, publishedTrades.get(), skippedTrades.get());
      } else if (trades.size() > 0) {
        log.warn("AWARE global trades poll: fetched={} but published=0 (all skipped/duplicates)", trades.size());
      }
    } catch (Exception e) {
      failures.incrementAndGet();
      log.warn("Global trades poll failed: {}", e.toString());
    } finally {
      pollingNow.set(false);
    }
  }

  /**
   * Backfill historical trades with pagination.
   * Useful for initial data population.
   */
  public void backfill() {
    int pageSize = Math.min(DATA_API_MAX_LIMIT, getPageSize());
    int maxPages = getBackfillMaxPages();
    long delayMillis = getRequestDelayMillis();

    log.info("AWARE global trades backfill starting: pageSize={} maxPages={}", pageSize, maxPages);

    int offset = 0;
    int page = 0;
    int totalPublished = 0;

    while (page < maxPages) {
      try {
        ArrayNode trades = dataApi.getGlobalTrades(pageSize, offset);

        if (trades.isEmpty()) {
          log.info("AWARE backfill: reached end at page={} offset={}", page, offset);
          break;
        }

        int published = publishTrades(trades);
        totalPublished += published;

        if (page % 10 == 0) {
          log.info("AWARE backfill progress: page={} offset={} fetched={} published={} totalPublished={}",
              page, offset, trades.size(), published, totalPublished);
        }

        offset += trades.size();
        page++;

        if (delayMillis > 0) {
          Thread.sleep(delayMillis);
        }
      } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        break;
      } catch (Exception e) {
        failures.incrementAndGet();
        log.warn("AWARE backfill page {} failed: {}", page, e.toString());
        break;
      }
    }

    log.info("AWARE global trades backfill complete: pages={} totalPublished={}", page, totalPublished);
  }

  private int publishTrades(ArrayNode trades) {
    int published = 0;

    for (int i = trades.size() - 1; i >= 0; i--) {
      JsonNode trade = trades.get(i);
      if (trade == null || trade.isNull()) {
        continue;
      }

      String txHash = trade.path("transactionHash").asText(null);
      if (txHash == null || txHash.isBlank()) {
        continue;
      }

      // A single tx hash can include multiple distinct trades; use composite key.
      String tradeId = buildTradeId(trade);

      // Deduplicate
      if (!seenTradeIds.add(tradeId)) {
        skippedTrades.incrementAndGet();
        continue;
      }

      // Build event envelope
      try {
        long tsMillis = trade.path("timestamp").asLong(0);
        Instant ts = tsMillis > 1_000_000_000_000L
            ? Instant.ofEpochMilli(tsMillis)
            : Instant.ofEpochSecond(tsMillis);

        Map<String, Object> envelope = new LinkedHashMap<>();
        envelope.put("ts", ts.toString());
        envelope.put("source", "aware-ingestor");
        envelope.put("type", EVENT_TYPE);
        envelope.put("key", tradeId);
        envelope.put("data", buildTradeData(tradeId, trade));

        String json = objectMapper.writeValueAsString(envelope);
        kafkaTemplate.send(AWARE_TOPIC, tradeId, json);

        publishedTrades.incrementAndGet();
        published++;
      } catch (Exception e) {
        log.warn("Failed to publish trade {}: {}", tradeId, e.getMessage());
      }
    }

    return published;
  }

  private String buildTradeId(JsonNode trade) {
    String transactionHash = trade.path("transactionHash").asText("");
    String asset = trade.path("asset").asText("");
    int outcomeIndex = trade.path("outcomeIndex").asInt(0);
    String side = trade.path("side").asText("");
    String price = trade.path("price").asText("0");
    String size = trade.path("size").asText("0");
    long timestamp = trade.path("timestamp").asLong(0);

    return String.join("|",
        transactionHash,
        asset,
        Integer.toString(outcomeIndex),
        side,
        price,
        size,
        Long.toString(timestamp));
  }

  private Map<String, Object> buildTradeData(String tradeId, JsonNode trade) {
    Map<String, Object> data = new LinkedHashMap<>();

    data.put("id", tradeId);
    data.put("pseudonym", trade.path("pseudonym").asText(null));
    data.put("proxyWallet", trade.path("proxyWallet").asText(null));
    data.put("maker", trade.path("maker").asText(null));
    data.put("taker", trade.path("taker").asText(null));
    data.put("slug", trade.path("slug").asText(null));
    data.put("title", trade.path("title").asText(null));
    data.put("conditionId", trade.path("conditionId").asText(null));
    data.put("asset", trade.path("asset").asText(null));
    data.put("outcome", trade.path("outcome").asText(null));
    data.put("outcomeIndex", trade.path("outcomeIndex").asInt(0));
    data.put("side", trade.path("side").asText(null));
    data.put("price", trade.path("price").asText("0"));
    data.put("size", trade.path("size").asText("0"));
    data.put("transactionHash", trade.path("transactionHash").asText(null));
    data.put("timestamp", trade.path("timestamp").asLong(0));

    return data;
  }

  // Configuration accessors with defaults
  private boolean isEnabled() {
    var gt = properties.globalTrades();
    return gt != null && Boolean.TRUE.equals(gt.enabled());
  }

  private int getPageSize() {
    var gt = properties.globalTrades();
    return gt != null && gt.pageSize() != null ? gt.pageSize() : 500;
  }

  private int getPollIntervalSeconds() {
    var gt = properties.globalTrades();
    return gt != null && gt.pollIntervalSeconds() != null ? gt.pollIntervalSeconds() : 30;
  }

  private long getRequestDelayMillis() {
    var gt = properties.globalTrades();
    return gt != null && gt.requestDelayMillis() != null ? gt.requestDelayMillis() : 100L;
  }

  private boolean isBackfillOnStart() {
    var gt = properties.globalTrades();
    return gt != null && Boolean.TRUE.equals(gt.backfillOnStart());
  }

  private int getBackfillMaxPages() {
    var gt = properties.globalTrades();
    return gt != null && gt.backfillMaxPages() != null ? gt.backfillMaxPages() : 100;
  }

  // Status accessors for monitoring endpoint
  public long polls() { return polls.get(); }
  public long publishedTrades() { return publishedTrades.get(); }
  public long skippedTrades() { return skippedTrades.get(); }
  public long failures() { return failures.get(); }
  public long lastPollAtMillis() { return lastPollAtMillis; }
  public int seenTradeIdsSize() { return seenTradeIds.size(); }
}
