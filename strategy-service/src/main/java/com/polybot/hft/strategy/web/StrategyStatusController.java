package com.polybot.hft.strategy.web;

import com.polybot.hft.config.HftProperties;
import com.polybot.hft.polymarket.fund.service.FundPositionMirror;
import com.polybot.hft.polymarket.fund.service.FundRegistry;
import com.polybot.hft.polymarket.fund.service.FundTradeListener;
import com.polybot.hft.polymarket.strategy.GabagoolDirectionalEngine;
import com.polybot.hft.polymarket.ws.ClobMarketWebSocketClient;
import lombok.NonNull;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.env.Environment;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/strategy")
@Slf4j
public class StrategyStatusController {

  private final @NonNull HftProperties properties;
  private final @NonNull Environment environment;
  private final @NonNull ClobMarketWebSocketClient marketWs;
  private final @NonNull GabagoolDirectionalEngine gabagoolEngine;

  // Optional fund components (only present when hft.fund.enabled=true)
  private final FundTradeListener fundTradeListener;
  private final FundPositionMirror fundPositionMirror;
  private final FundRegistry fundRegistry;

  @Autowired
  public StrategyStatusController(
      HftProperties properties,
      Environment environment,
      ClobMarketWebSocketClient marketWs,
      GabagoolDirectionalEngine gabagoolEngine,
      @Autowired(required = false) FundTradeListener fundTradeListener,
      @Autowired(required = false) FundPositionMirror fundPositionMirror,
      @Autowired(required = false) FundRegistry fundRegistry
  ) {
    this.properties = properties;
    this.environment = environment;
    this.marketWs = marketWs;
    this.gabagoolEngine = gabagoolEngine;
    this.fundTradeListener = fundTradeListener;
    this.fundPositionMirror = fundPositionMirror;
    this.fundRegistry = fundRegistry;
  }

  @GetMapping("/status")
  public ResponseEntity<StrategyStatusResponse> status() {
    HftProperties.Gabagool gabagool = properties.strategy().gabagool();
    return ResponseEntity.ok(new StrategyStatusResponse(
        properties.mode().name(),
        environment.getActiveProfiles(),
        properties.executor().baseUrl(),
        properties.polymarket().marketWsEnabled(),
        environment.getProperty("hft.polymarket.market-ws-enabled"),
        marketWs.isStarted(),
        marketWs.subscribedAssetCount(),
        gabagool.enabled(),
        gabagoolEngine.activeMarketCount(),
        gabagoolEngine.isRunning()
    ));
  }

  public record StrategyStatusResponse(
      String mode,
      String[] activeProfiles,
      String executorBaseUrl,
      boolean marketWsEnabled,
      String resolvedMarketWsEnabledProperty,
      boolean marketWsStarted,
      int marketWsSubscribedAssets,
      boolean gabagoolEnabled,
      int gabagoolActiveMarkets,
      boolean gabagoolRunning
  ) {
  }

  /**
   * Get fund status and metrics.
   * Returns fund configuration and trading metrics if fund is enabled.
   */
  @GetMapping("/fund/status")
  public ResponseEntity<Map<String, Object>> fundStatus() {
    Map<String, Object> response = new HashMap<>();

    // Check if fund is enabled
    boolean fundEnabled = properties.fund() != null && properties.fund().enabled();
    response.put("fundEnabled", fundEnabled);

    if (!fundEnabled) {
      response.put("message", "Fund is not enabled. Set hft.fund.enabled=true to enable.");
      return ResponseEntity.ok(response);
    }

    // Fund configuration
    response.put("indexType", properties.fund().indexType());
    response.put("capitalUsd", properties.fund().capitalUsd());
    response.put("maxPositionPct", properties.fund().maxPositionPct());
    response.put("minTradeUsd", properties.fund().minTradeUsd());
    response.put("signalDelaySeconds", properties.fund().signalDelaySeconds());

    // Check if beans are injected
    response.put("tradeListenerInjected", fundTradeListener != null);
    response.put("positionMirrorInjected", fundPositionMirror != null);

    // Get metrics from trade listener
    if (fundTradeListener != null) {
      response.put("tradeListenerMetrics", fundTradeListener.getMetrics());
    } else {
      response.put("tradeListenerMetrics", "NOT AVAILABLE - Bean not created");
    }

    // Get metrics from position mirror
    if (fundPositionMirror != null) {
      response.put("positionMirrorMetrics", fundPositionMirror.getMetrics());
    } else {
      response.put("positionMirrorMetrics", "NOT AVAILABLE - Bean not created");
    }

    return ResponseEntity.ok(response);
  }

  /**
   * Get status of all registered funds (multi-fund view).
   */
  @GetMapping("/funds/all")
  public ResponseEntity<Map<String, Object>> allFundsStatus() {
    Map<String, Object> response = new HashMap<>();

    if (fundRegistry == null) {
      response.put("enabled", false);
      response.put("message", "Fund system not enabled");
      return ResponseEntity.ok(response);
    }

    response.put("enabled", true);

    // Get all funds
    List<Map<String, Object>> funds = fundRegistry.getAllFunds().stream()
        .map(fund -> {
          Map<String, Object> fundInfo = new HashMap<>();
          fundInfo.put("fundId", fund.fundId());
          fundInfo.put("type", fund.type().getId());
          fundInfo.put("category", fund.type().isMirrorFund() ? "MIRROR" : "ACTIVE");
          fundInfo.put("capitalUsd", fund.capitalUsd());
          fundInfo.put("realizedPnl", fund.realizedPnl());
          fundInfo.put("unrealizedPnl", fund.unrealizedPnl());
          fundInfo.put("totalPnl", fund.totalPnl());
          fundInfo.put("returnPct", fund.returnPct());
          fundInfo.put("nav", fund.nav());
          fundInfo.put("openPositions", fund.openPositions());
          fundInfo.put("startedAt", fund.startedAt().toString());
          return fundInfo;
        })
        .toList();

    response.put("funds", funds);
    response.put("fundCount", funds.size());

    // Aggregate metrics
    FundRegistry.AggregateMetrics aggregate = fundRegistry.getAggregateMetrics();
    Map<String, Object> aggregateMap = new HashMap<>();
    aggregateMap.put("totalCapital", aggregate.totalCapital());
    aggregateMap.put("totalRealizedPnl", aggregate.totalRealizedPnl());
    aggregateMap.put("totalUnrealizedPnl", aggregate.totalUnrealizedPnl());
    aggregateMap.put("totalPnl", aggregate.totalPnl());
    aggregateMap.put("totalNav", aggregate.totalNav());
    aggregateMap.put("totalOpenPositions", aggregate.totalOpenPositions());
    response.put("aggregate", aggregateMap);

    return ResponseEntity.ok(response);
  }
}
