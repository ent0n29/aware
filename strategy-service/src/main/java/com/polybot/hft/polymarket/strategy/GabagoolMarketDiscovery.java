package com.polybot.hft.polymarket.strategy;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.polybot.hft.config.HftProperties;
import com.polybot.hft.polymarket.discovery.PolymarketMarketDiscoveryService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;
import java.util.*;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * Discovers active Up/Down markets from Polymarket Gamma API.
 * These are the markets the target user trades.
 *
 * Notes:
 * - Market universe is stable: BTC/ETH Up/Down 15m + 1h series only.
 * - The replica strategy is intended to be market-neutral (no BTC direction bias); alpha is driven by
 *   platform mispricing + timing/execution, not by predicting Up vs Down.
 */
@Component
@Slf4j
@RequiredArgsConstructor
public class GabagoolMarketDiscovery {

    private static final Duration HTTP_TIMEOUT = Duration.ofSeconds(10);
    private static final ZoneId ET_ZONE = ZoneId.of("America/New_York");

    // Slug patterns for the target user's target markets
    // - 15min BTC: btc-updown-15m-{epoch}
    // - 15min ETH: eth-updown-15m-{epoch}
    // - 1hour BTC: bitcoin-up-or-down-{date}
    // - 1hour ETH: ethereum-up-or-down-{date}

    private final HftProperties properties;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient;
    private final PolymarketMarketDiscoveryService marketDiscoveryService;

    private final List<DiscoveredMarket> activeMarkets = new CopyOnWriteArrayList<>();

    /**
     * Get currently active markets suitable for gabagool strategy.
     */
    public List<DiscoveredMarket> getActiveMarkets() {
        return new ArrayList<>(activeMarkets);
    }

  /**
   * Refresh market discovery every 30 seconds.
   */
  @Scheduled(fixedDelay = 30_000, initialDelay = 5_000)
  public void discoverMarkets() {
        if (!properties.strategy().gabagool().enabled()) {
            return;
        }

        log.info("GABAGOOL DISCOVERY: Scanning for active markets...");

        try {
            // Fetch all active events once and filter locally
            List<DiscoveredMarket> discovered = fetchActiveUpDownEvents();

            // Keep markets that are currently open.
            //
            // Empirical timing:
            // - 15m series fills span ~0-15m before end
            // - 1h series fills span ~0-60m before end
            //
            // So we should track the "current" market instances, not only the ones ending soon.
            Instant now = Instant.now();
            Instant maxEnd = now.plus(2, ChronoUnit.HOURS);

            List<DiscoveredMarket> active = discovered.stream()
                    .filter(m -> isActiveNow(m, now, maxEnd))
                    .toList();

            // Merge with previous markets to avoid coverage drops on transient API failures.
            List<DiscoveredMarket> previous = new ArrayList<>(activeMarkets);
            Map<String, DiscoveredMarket> merged = new LinkedHashMap<>();
            for (DiscoveredMarket m : active) {
                merged.put(m.slug(), m);
            }
            for (DiscoveredMarket m : previous) {
                if (!merged.containsKey(m.slug()) && isActiveNow(m, now, maxEnd)) {
                    merged.put(m.slug(), m);
                }
            }

            activeMarkets.clear();
            activeMarkets.addAll(merged.values());

            log.info("GABAGOOL DISCOVERY: Found {} total, {} active/open", discovered.size(), merged.size());

            if (!merged.isEmpty()) {
                for (DiscoveredMarket m : merged.values()) {
                    long minutesToEnd = Duration.between(now, m.endTime()).toMinutes();
                    log.info("  - {} [{}] (ends in {}min)", m.slug(), m.marketType(), minutesToEnd);
                }
            } else if (!discovered.isEmpty()) {
                log.info("  (markets found but none currently open, waiting...)");
            } else {
                log.info("  (no matching BTC/ETH Up/Down markets found from API)");
            }
        } catch (Exception e) {
            log.error("GABAGOOL DISCOVERY: Error discovering markets: {}", e.getMessage(), e);
        }
    }

    /**
     * Fetch all active Up/Down events from Gamma API.
     *
     * Gamma's public /markets listing does not include the fast up/down series reliably.
     * Instead, we deterministically generate candidate slugs around \"now\" and query /events?slug=...
     */
    private List<DiscoveredMarket> fetchActiveUpDownEvents() {
        Instant now = Instant.now();

        List<String> candidates = new ArrayList<>();
        candidates.addAll(candidateUpDown15mSlugs("btc", now));
        candidates.addAll(candidateUpDown15mSlugs("eth", now));

        ZonedDateTime nowEt = ZonedDateTime.ofInstant(now, ET_ZONE);
        candidates.addAll(candidateUpOrDown1hSlugs("bitcoin", nowEt));
        candidates.addAll(candidateUpOrDown1hSlugs("ethereum", nowEt));

        List<DiscoveredMarket> markets = new ArrayList<>(candidates.size());
        Set<String> seenSlugs = new HashSet<>();
        for (String slug : candidates) {
            if (!seenSlugs.add(slug)) {
                continue;
            }
            DiscoveredMarket market = fetchMarketBySlug(slug);
            if (market != null) {
                markets.add(market);
            }
        }

        // Secondary discovery: gamma/clob search (best-effort).
        // This improves coverage when deterministic slug generation misses due to format changes.
        try {
            List<String> queries = List.of(
                    "btc updown 15m",
                    "btc up or down 15m",
                    "eth updown 15m",
                    "eth up or down 15m",
                    "bitcoin up or down",
                    "ethereum up or down"
            );

            for (String q : queries) {
                List<com.polybot.hft.polymarket.discovery.DiscoveredMarket> found = marketDiscoveryService.searchGamma(q);
                for (com.polybot.hft.polymarket.discovery.DiscoveredMarket m : found) {
                    DiscoveredMarket mapped = mapCoreDiscoveredMarket(m);
                    if (mapped != null && seenSlugs.add(mapped.slug())) {
                        markets.add(mapped);
                    }
                }
            }
        } catch (Exception e) {
            log.debug("GABAGOOL DISCOVERY: secondary discovery failed: {}", e.getMessage());
        }

        if (log.isDebugEnabled()) {
            log.debug("GABAGOOL DISCOVERY: Candidates: {}", candidates);
        }
        return markets;
    }

    private DiscoveredMarket mapCoreDiscoveredMarket(com.polybot.hft.polymarket.discovery.DiscoveredMarket m) {
        if (m == null) {
            return null;
        }
        String slug = m.slug();
        if (slug == null || slug.isBlank()) {
            return null;
        }

        String marketType;
        if (slug.contains("updown-15m")) {
            marketType = "updown-15m";
        } else if (slug.contains("up-or-down")) {
            marketType = "up-or-down";
        } else {
            return null;
        }

        String upTokenId = m.yesTokenId();
        String downTokenId = m.noTokenId();
        if (upTokenId == null || upTokenId.isBlank() || downTokenId == null || downTokenId.isBlank()) {
            return null;
        }

        Instant endTime = null;
        if (m.endEpochMillis() != null && m.endEpochMillis() > 0) {
            endTime = Instant.ofEpochMilli(m.endEpochMillis());
        }
        if (endTime == null) {
            endTime = parseEndTimeFromSlug(slug, marketType);
        }

        return new DiscoveredMarket(
                slug,
                m.id(),
                upTokenId,
                downTokenId,
                endTime,
                false,
                marketType
        );
    }

    private static List<String> candidateUpDown15mSlugs(String assetPrefix, Instant now) {
        long nowSec = now.getEpochSecond();
        // Include a wider window so we keep coverage through restarts and transient API failures.
        // This remains small (15m cadence) but dramatically reduces the chance we miss an active instance.
        long from = nowSec - Duration.ofMinutes(90).toSeconds();
        long to = nowSec + Duration.ofMinutes(60).toSeconds();

        long startFrom = (from / 900L) * 900L;
        long startTo = (to / 900L) * 900L;

        List<String> out = new ArrayList<>();
        for (long start = startFrom; start <= startTo; start += 900L) {
            out.add(assetPrefix + "-updown-15m-" + start);
        }
        return out;
    }

    private static List<String> candidateUpOrDown1hSlugs(String assetPrefix, ZonedDateTime nowEt) {
        // The 1-hour slug is formatted like: bitcoin-up-or-down-december-14-11am-et
        ZonedDateTime hourStart = nowEt.truncatedTo(ChronoUnit.HOURS);
        List<ZonedDateTime> candidates = List.of(
                hourStart.minusHours(2),
                hourStart.minusHours(1),
                hourStart,
                hourStart.plusHours(1),
                hourStart.plusHours(2)
        );
        List<String> out = new ArrayList<>(candidates.size());
        for (ZonedDateTime start : candidates) {
            out.add(buildUpOrDown1hSlug(assetPrefix, start));
        }
        return out;
    }

    private static String buildUpOrDown1hSlug(String assetPrefix, ZonedDateTime hourStartEt) {
        String month = hourStartEt.getMonth().getDisplayName(java.time.format.TextStyle.FULL, Locale.ENGLISH).toLowerCase(Locale.ROOT);
        int day = hourStartEt.getDayOfMonth();
        int hour24 = hourStartEt.getHour();
        int hour12 = hour24 % 12;
        if (hour12 == 0) {
            hour12 = 12;
        }
        String ampm = hour24 < 12 ? "am" : "pm";
        return "%s-up-or-down-%s-%d-%d%s-et".formatted(assetPrefix, month, day, hour12, ampm);
    }

    private static boolean isActiveNow(DiscoveredMarket market, Instant now, Instant maxEnd) {
        if (market == null || market.endTime() == null || market.closed()) {
            return false;
        }
        if (market.endTime().isBefore(now) || market.endTime().isAfter(maxEnd)) {
            return false;
        }
        Duration duration = "updown-15m".equals(market.marketType()) ? Duration.ofMinutes(15) : Duration.ofHours(1);
        Instant startTime = market.endTime().minus(duration);
        // Pre-warm a little before the market "start" so WS TOB is hot at the first decision tick.
        Duration prewarm = "updown-15m".equals(market.marketType()) ? Duration.ofSeconds(90) : Duration.ofMinutes(3);
        return !now.isBefore(startTime.minus(prewarm));
    }

    /**
     * Parse a market node directly from /markets endpoint
     */
    private DiscoveredMarket parseMarketNode(JsonNode marketNode) {
        try {
            String slug = marketNode.path("slug").asText(null);
            if (slug == null || slug.isBlank()) {
                return null;
            }

            boolean closed = marketNode.path("closed").asBoolean(false);
            if (closed) {
                return null;
            }

            // Determine market type
            String marketType;
            if (slug.contains("updown-15m")) {
                marketType = "updown-15m";
            } else if (slug.contains("up-or-down")) {
                marketType = "up-or-down";
            } else {
                return null;
            }

            // Parse end time
            Instant endTime = null;
            String endDateStr = marketNode.path("endDate").asText(null);
            if (endDateStr != null && !endDateStr.isBlank()) {
                try {
                    endTime = Instant.parse(endDateStr);
                } catch (Exception e) {
                    endTime = parseEndTimeFromSlug(slug, marketType);
                }
            } else {
                endTime = parseEndTimeFromSlug(slug, marketType);
            }

            String marketId = marketNode.path("id").asText(null);

            // Parse tokens and outcomes directly from market node
            List<String> tokenIds = parseStringArray(marketNode.path("clobTokenIds"));
            List<String> outcomes = parseStringArray(marketNode.path("outcomes"));

            String upTokenId = null;
            String downTokenId = null;

            if (tokenIds.size() >= 2 && outcomes.size() >= 2) {
                for (int i = 0; i < outcomes.size() && i < tokenIds.size(); i++) {
                    String outcome = outcomes.get(i).toLowerCase().trim();
                    String tokenId = tokenIds.get(i);

                    if (tokenId != null && !tokenId.isBlank()) {
                        if (outcome.equals("up")) {
                            upTokenId = tokenId;
                        } else if (outcome.equals("down")) {
                            downTokenId = tokenId;
                        }
                    }
                }
            }

            if (upTokenId == null || downTokenId == null) {
                log.debug("Could not find Up/Down tokens for {}", slug);
                return null;
            }

            log.debug("GABAGOOL DISCOVERY: Parsed {} -> endTime={}", slug, endTime);

            return new DiscoveredMarket(
                    slug,
                    marketId,
                    upTokenId,
                    downTokenId,
                    endTime,
                    closed,
                    marketType
            );
        } catch (Exception e) {
            log.debug("Failed to parse market: {}", e.getMessage());
            return null;
        }
    }

    /**
     * Fetch full market details by slug using /events?slug={slug}
     */
    private DiscoveredMarket fetchMarketBySlug(String slug) {
        try {
            String url = properties.polymarket().gammaUrl() + "/events?slug=" + slug;

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(HTTP_TIMEOUT)
                    .header("Accept", "application/json")
                    .GET()
                    .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() != 200) {
                return null;
            }

            JsonNode root = objectMapper.readTree(response.body());
            if (!root.isArray() || root.isEmpty()) {
                return null;
            }

            JsonNode eventNode = root.get(0);
            return parseEventWithFullDetails(eventNode, slug);

        } catch (Exception e) {
            log.debug("Error fetching market {}: {}", slug, e.getMessage());
            return null;
        }
    }

    /**
     * Parse event with full market details (from /events?slug= query)
     */
    private DiscoveredMarket parseEventWithFullDetails(JsonNode eventNode, String slug) {
        try {
            String eventSlug = eventNode.path("slug").asText(null);
            if (eventSlug == null || eventSlug.isBlank()) {
                return null;
            }

            boolean closed = eventNode.path("closed").asBoolean(false);
            if (closed) {
                return null;
            }

            // Determine market type
            String marketType;
            if (eventSlug.contains("updown-15m")) {
                marketType = "updown-15m";
            } else if (eventSlug.contains("up-or-down")) {
                marketType = "up-or-down";
            } else {
                return null;
            }

            // Parse end time
            Instant endTime = null;
            String endDateStr = eventNode.path("endDate").asText(null);
            if (endDateStr != null && !endDateStr.isBlank()) {
                try {
                    endTime = Instant.parse(endDateStr);
                } catch (Exception e) {
                    endTime = parseEndTimeFromSlug(eventSlug, marketType);
                }
            } else {
                endTime = parseEndTimeFromSlug(eventSlug, marketType);
            }

            // Get markets array - this should have full details when queried by slug
            JsonNode marketsArray = eventNode.path("markets");
            if (!marketsArray.isArray() || marketsArray.isEmpty()) {
                log.debug("Event {} has no markets array", eventSlug);
                return null;
            }

            String upTokenId = null;
            String downTokenId = null;
            String marketId = null;

            // The first market should have the tokens
            JsonNode firstMarket = marketsArray.get(0);
            marketId = firstMarket.path("id").asText(null);

            // Parse clobTokenIds and outcomes - they can be either:
            // 1. A JSON array: ["token1", "token2"]
            // 2. A string containing JSON: "[\"token1\", \"token2\"]"
            List<String> tokenIds = parseStringArray(firstMarket.path("clobTokenIds"));
            List<String> outcomes = parseStringArray(firstMarket.path("outcomes"));

            if (tokenIds.size() >= 2 && outcomes.size() >= 2) {
                for (int i = 0; i < outcomes.size() && i < tokenIds.size(); i++) {
                    String outcome = outcomes.get(i).toLowerCase().trim();
                    String tokenId = tokenIds.get(i);

                    if (tokenId != null && !tokenId.isBlank()) {
                        if (outcome.equals("up")) {
                            upTokenId = tokenId;
                        } else if (outcome.equals("down")) {
                            downTokenId = tokenId;
                        }
                    }
                }
            }

            if (upTokenId == null || downTokenId == null) {
                log.debug("Could not find Up/Down tokens for {}: outcomes={} tokens={}", eventSlug, outcomes, tokenIds);
                return null;
            }

            log.info("GABAGOOL DISCOVERY: Parsed {} -> endTime={}", eventSlug, endTime);

            return new DiscoveredMarket(
                    eventSlug,
                    marketId,
                    upTokenId,
                    downTokenId,
                    endTime,
                    closed,
                    marketType
            );
        } catch (Exception e) {
            log.debug("Failed to parse event {}: {}", slug, e.getMessage());
            return null;
        }
    }

    /**
     * Parse a JSON node that can be either:
     * 1. A JSON array: ["a", "b"]
     * 2. A string containing a JSON array: "[\"a\", \"b\"]"
     */
    private List<String> parseStringArray(JsonNode node) {
        if (node == null || node.isNull() || node.isMissingNode()) {
            return List.of();
        }

        // Case 1: Already a JSON array
        if (node.isArray()) {
            List<String> result = new ArrayList<>(node.size());
            for (JsonNode n : node) {
                if (n != null && !n.isNull()) {
                    String s = n.asText(null);
                    if (s != null) {
                        result.add(s);
                    }
                }
            }
            return result;
        }

        // Case 2: A string containing a JSON array
        if (node.isTextual()) {
            String raw = node.asText();
            if (raw == null || raw.isBlank()) {
                return List.of();
            }
            try {
                JsonNode parsed = objectMapper.readTree(raw);
                return parseStringArray(parsed);
            } catch (Exception e) {
                return List.of();
            }
        }

        return List.of();
    }

    private Instant parseEndTimeFromSlug(String slug, String marketType) {
        try {
            if (marketType.equals("updown-15m")) {
                // Slug format: btc-updown-15m-1734364800
                // The last part is the epoch timestamp, add 15 min for end time
                String[] parts = slug.split("-");
                if (parts.length >= 4) {
                    String epochStr = parts[parts.length - 1];
                    long epoch = Long.parseLong(epochStr);
                    return Instant.ofEpochSecond(epoch + 900); // +15 minutes
                }
            } else {
                // 1hour markets: bitcoin-up-or-down-december-16-8am-et
                // These don't have epoch in slug, need to use endDate from API
                // Return null to rely on API endDate field
                return null;
            }
        } catch (Exception e) {
            // ignore
        }
        return null;
    }

    public record DiscoveredMarket(
            String slug,
            String marketId,
            String upTokenId,
            String downTokenId,
            Instant endTime,
            boolean closed,
            String marketType
    ) {}
}
