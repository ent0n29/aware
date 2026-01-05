package com.polybot.hft.polymarket.data;

import com.fasterxml.jackson.databind.JsonNode;
import com.polybot.hft.polymarket.http.HttpRequestFactory;
import com.polybot.hft.polymarket.http.PolymarketHttpTransport;
import lombok.NonNull;

import java.net.URI;
import java.net.http.HttpRequest;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

public final class PolymarketDataApiClient {

  private static final Duration HTTP_TIMEOUT = Duration.ofSeconds(10);

  private final HttpRequestFactory requestFactory;
  private final PolymarketHttpTransport transport;

  public PolymarketDataApiClient(@NonNull URI baseUri, @NonNull PolymarketHttpTransport transport) {
    this.requestFactory = new HttpRequestFactory(Objects.requireNonNull(baseUri, "baseUri"));
    this.transport = Objects.requireNonNull(transport, "transport");
  }

  public JsonNode getTrades(String userAddress, int limit, int offset) {
    Map<String, String> query = new LinkedHashMap<>();
    query.put("user", userAddress);
    query.put("limit", Integer.toString(Math.max(1, limit)));
    query.put("offset", Integer.toString(Math.max(0, offset)));
    return getArray("/trades", query);
  }

  public JsonNode getPositions(String userAddress, int limit, int offset) {
    Map<String, String> query = new LinkedHashMap<>();
    query.put("user", userAddress);
    query.put("limit", Integer.toString(Math.max(1, limit)));
    query.put("offset", Integer.toString(Math.max(0, offset)));
    return getArray("/positions", query);
  }

  /**
   * Fetch recent trades for a single market (condition).
   *
   * Note: the Polymarket data-api expects the {@code market} query param to be the conditionId
   * (a 0x... hex string), not the human-readable slug.
   */
  public JsonNode getMarketTrades(String conditionId, int limit, int offset) {
    if (conditionId == null || conditionId.isBlank()) {
      throw new IllegalArgumentException("conditionId must not be blank");
    }

    Map<String, String> query = new LinkedHashMap<>();
    query.put("market", conditionId);
    query.put("limit", Integer.toString(Math.max(1, limit)));
    query.put("offset", Integer.toString(Math.max(0, offset)));
    return getArray("/trades", query);
  }

  /**
   * Fetch global trades (all users, all markets).
   */
  public JsonNode getGlobalTrades(int limit, int offset) {
    Map<String, String> query = new LinkedHashMap<>();
    query.put("limit", Integer.toString(Math.max(1, limit)));
    query.put("offset", Integer.toString(Math.max(0, offset)));
    return getArray("/trades", query);
  }

  private JsonNode getArray(String path, Map<String, String> query) {
    if (query == null) {
      query = Map.of();
    }
    HttpRequest request = requestFactory.request(path, query)
        .GET()
        .timeout(HTTP_TIMEOUT)
        .header("Accept", "application/json")
        .build();
    return transport.sendJson(request, JsonNode.class);
  }
}
