package com.polybot.hft.polymarket.fund.config;

import com.polybot.hft.polymarket.fund.model.FundType;
import com.polybot.hft.polymarket.fund.service.*;
import com.polybot.hft.polymarket.fund.strategy.*;
import com.polybot.hft.polymarket.ws.ClobMarketWebSocketClient;
import com.polybot.hft.strategy.executor.ExecutorApiClient;
import io.micrometer.core.instrument.MeterRegistry;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

import jakarta.annotation.PostConstruct;
import java.math.BigDecimal;
import java.time.Clock;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Multi-fund configuration for running ALL fund strategies simultaneously.
 *
 * This replaces the single-fund ActiveFundConfiguration when multi-fund mode is enabled.
 * Each fund runs independently with its own capital allocation and risk limits.
 *
 * Enabled via: hft.multi-fund.enabled=true
 */
@Slf4j
@Configuration
@EnableScheduling
@RequiredArgsConstructor
@ConditionalOnProperty(prefix = "hft.multi-fund", name = "enabled", havingValue = "true")
public class MultiFundConfiguration {

    private final MultiFundProperties multiFundProps;
    private final ExecutorApiClient executorApi;
    private final JdbcTemplate jdbcTemplate;
    private final FundRegistry fundRegistry;
    private final MeterRegistry meterRegistry;
    private final ClobMarketWebSocketClient marketWs;

    // Track all active ALPHA strategies for polling
    private final Map<String, ActiveFundExecutor> activeStrategies = new ConcurrentHashMap<>();

    // Track PSI mirror fund components (trade listener + position mirror pairs)
    private final Map<String, PsiMirrorFund> psiMirrorFunds = new ConcurrentHashMap<>();

    // Shared weight provider for all PSI funds
    private IndexWeightProvider weightProvider;

    @PostConstruct
    public void initializeFunds() {
        log.info("========================================");
        log.info("MULTI-FUND MODE ENABLED");
        log.info("Total Capital: ${}", multiFundProps.getTotalCapitalUsd());
        log.info("========================================");

        // Create shared weight provider for PSI funds
        this.weightProvider = new IndexWeightProvider(jdbcTemplate);

        int psiCount = 0;
        int alphaCount = 0;

        // Initialize each configured fund
        for (Map.Entry<String, MultiFundProperties.FundAllocation> entry :
                multiFundProps.getFunds().entrySet()) {

            String fundType = entry.getKey();
            MultiFundProperties.FundAllocation allocation = entry.getValue();

            if (!allocation.isEnabled()) {
                log.info("Fund {} is DISABLED, skipping", fundType);
                continue;
            }

            BigDecimal capital = allocation.getEffectiveCapital(multiFundProps.getTotalCapitalUsd());
            log.info("Initializing fund: {} with ${} capital ({}%)",
                    fundType, capital, allocation.getCapitalPct());

            try {
                // PSI funds use mirror architecture
                if (fundType.startsWith("PSI-")) {
                    PsiMirrorFund mirrorFund = createPsiMirrorFund(fundType, capital, allocation);
                    if (mirrorFund != null) {
                        psiMirrorFunds.put(fundType, mirrorFund);
                        psiCount++;

                        // Register with FundRegistry
                        try {
                            FundType ft = FundType.fromId(fundType);
                            fundRegistry.registerFund(fundType, ft, capital);
                        } catch (IllegalArgumentException e) {
                            log.warn("Unknown fund type '{}', skipping registry", fundType);
                        }

                        log.info("Successfully initialized PSI mirror fund: {}", fundType);
                    }
                } else {
                    // ALPHA funds use active strategy architecture
                    ActiveFundExecutor strategy = createStrategy(fundType, capital, allocation);
                    if (strategy != null) {
                        activeStrategies.put(fundType, strategy);
                        alphaCount++;

                        // Register with FundRegistry
                        try {
                            FundType ft = FundType.fromId(fundType);
                            fundRegistry.registerFund(fundType, ft, capital);
                        } catch (IllegalArgumentException e) {
                            log.warn("Unknown fund type '{}', skipping registry", fundType);
                        }

                        log.info("Successfully initialized ALPHA strategy: {}", fundType);
                    }
                }
            } catch (Exception e) {
                log.error("Failed to initialize fund {}: {}", fundType, e.getMessage(), e);
            }
        }

        log.info("========================================");
        log.info("Initialized {} PSI mirror funds + {} ALPHA strategies = {} total",
                psiCount, alphaCount, psiCount + alphaCount);
        log.info("========================================");
    }

    /**
     * Create a PSI mirror fund with trade listener and position mirror.
     */
    private PsiMirrorFund createPsiMirrorFund(
            String indexType,
            BigDecimal capital,
            MultiFundProperties.FundAllocation allocation
    ) {
        // Create fund config for this PSI index
        FundConfig config = new FundConfig(
                true,
                indexType,
                capital,
                allocation.getMaxPositionPct(),
                allocation.getMinTradeUsd(),
                5, // signalDelaySeconds
                0.02, // maxSlippagePct
                com.polybot.hft.config.HftProperties.FundExecutionMode.LIMIT_THEN_MARKET,
                FundConfig.RiskLimits.defaults()
        );

        // Create position mirror
        FundPositionMirror positionMirror = new FundPositionMirror(
                config, weightProvider, executorApi, Clock.systemUTC(), jdbcTemplate, meterRegistry
        );

        // Create trade listener
        FundTradeListener tradeListener = new FundTradeListener(
                config, weightProvider, positionMirror, jdbcTemplate, Clock.systemUTC(), meterRegistry
        );

        return new PsiMirrorFund(indexType, config, tradeListener, positionMirror);
    }

    /**
     * Container for PSI mirror fund components.
     */
    private record PsiMirrorFund(
            String indexType,
            FundConfig config,
            FundTradeListener tradeListener,
            FundPositionMirror positionMirror
    ) {}

    /**
     * Create the appropriate strategy for a fund type.
     */
    private ActiveFundExecutor createStrategy(
            String fundType,
            BigDecimal capital,
            MultiFundProperties.FundAllocation allocation
    ) {
        // Create base FundConfig
        FundConfig baseConfig = new FundConfig(
                true,
                fundType,
                capital,
                allocation.getMaxPositionPct(),
                allocation.getMinTradeUsd(),
                5, // signalDelaySeconds
                0.02, // maxSlippagePct
                com.polybot.hft.config.HftProperties.FundExecutionMode.LIMIT_THEN_MARKET,
                FundConfig.RiskLimits.defaults()
        );

        return switch (fundType.toUpperCase()) {
            case "ALPHA-INSIDER" -> {
                ActiveFundConfig config = ActiveFundConfig.forInsiderStrategy(baseConfig);
                yield new InsiderFollowStrategy(config, executorApi, jdbcTemplate, Clock.systemUTC(), meterRegistry);
            }
            case "ALPHA-EDGE" -> {
                ActiveFundConfig config = ActiveFundConfig.forEdgeStrategy(baseConfig);
                yield new MLEdgeStrategy(config, executorApi, jdbcTemplate, Clock.systemUTC(), meterRegistry);
            }
            case "ALPHA-ARB" -> {
                ActiveFundConfig config = ActiveFundConfig.forArbStrategy(baseConfig);
                yield new ArbStrategy(config, executorApi, jdbcTemplate, Clock.systemUTC(), meterRegistry, marketWs);
            }
            default -> {
                // PSI-* index funds use the mirror strategy (handled elsewhere)
                if (fundType.startsWith("PSI-")) {
                    log.info("PSI index fund {} - uses FundPositionMirror (separate config)", fundType);
                    yield null;
                }
                log.warn("Unknown fund type: {}", fundType);
                yield null;
            }
        };
    }

    // ========== Scheduled Polling Tasks ==========

    /**
     * Poll all active strategies for signals.
     * Runs every 2 seconds for responsive signal detection.
     */
    @Scheduled(fixedRate = 2000)
    public void pollAllStrategies() {
        for (Map.Entry<String, ActiveFundExecutor> entry : activeStrategies.entrySet()) {
            try {
                entry.getValue().pollForSignals();
            } catch (Exception e) {
                log.warn("Error polling {}: {}", entry.getKey(), e.getMessage());
            }
        }
    }

    /**
     * Process queued signals for all strategies.
     * Runs every 100ms for fast execution.
     */
    @Scheduled(fixedRate = 100)
    public void processAllSignals() {
        for (Map.Entry<String, ActiveFundExecutor> entry : activeStrategies.entrySet()) {
            try {
                entry.getValue().processQueuedSignals();
            } catch (Exception e) {
                log.warn("Error processing signals for {}: {}", entry.getKey(), e.getMessage());
            }
        }
    }

    /**
     * Check for resolved arb positions.
     * Runs every minute.
     */
    @Scheduled(fixedRate = 60000)
    public void checkArbResolutions() {
        ActiveFundExecutor arb = activeStrategies.get("ALPHA-ARB");
        if (arb instanceof ArbStrategy arbStrategy) {
            try {
                arbStrategy.checkResolvedPositions();
            } catch (Exception e) {
                log.warn("Error checking arb resolutions: {}", e.getMessage());
            }
        }
    }

    // ========== PSI Mirror Fund Polling ==========

    /**
     * Poll all PSI mirror funds for new trades from indexed traders.
     * Runs every second to catch trades quickly.
     */
    @Scheduled(fixedRate = 1000)
    public void pollPsiMirrorFunds() {
        for (Map.Entry<String, PsiMirrorFund> entry : psiMirrorFunds.entrySet()) {
            try {
                entry.getValue().tradeListener().pollForTrades();
            } catch (Exception e) {
                log.warn("Error polling PSI fund {}: {}", entry.getKey(), e.getMessage());
            }
        }
    }

    /**
     * Process pending signals for all PSI mirror funds.
     * Runs every 500ms to execute signals after delay period.
     */
    @Scheduled(fixedRate = 500)
    public void processPsiMirrorSignals() {
        for (Map.Entry<String, PsiMirrorFund> entry : psiMirrorFunds.entrySet()) {
            try {
                entry.getValue().positionMirror().processPendingSignals();
            } catch (Exception e) {
                log.warn("Error processing signals for PSI fund {}: {}", entry.getKey(), e.getMessage());
            }
        }
    }

    // ========== Status Endpoints ==========

    /**
     * Get all active strategies for status/metrics.
     */
    @Bean
    public MultiFundStatus multiFundStatus() {
        return new MultiFundStatus(activeStrategies, psiMirrorFunds, multiFundProps);
    }

    /**
     * Status holder for multi-fund metrics.
     */
    public record MultiFundStatus(
            Map<String, ActiveFundExecutor> alphaStrategies,
            Map<String, PsiMirrorFund> psiMirrorFunds,
            MultiFundProperties properties
    ) {
        public List<FundStatus> getAllStatus() {
            List<FundStatus> result = new ArrayList<>();

            // Add ALPHA strategies
            for (Map.Entry<String, ActiveFundExecutor> entry : alphaStrategies.entrySet()) {
                result.add(new FundStatus(
                        entry.getKey(),
                        "ALPHA",
                        entry.getValue().isEnabled(),
                        entry.getValue().getMetrics()
                ));
            }

            // Add PSI mirror funds
            for (Map.Entry<String, PsiMirrorFund> entry : psiMirrorFunds.entrySet()) {
                Map<String, Object> metrics = new HashMap<>();
                metrics.put("tradeListener", entry.getValue().tradeListener().getMetrics());
                metrics.put("positionMirror", entry.getValue().positionMirror().getMetrics());
                result.add(new FundStatus(
                        entry.getKey(),
                        "MIRROR",
                        entry.getValue().config().enabled(),
                        metrics
                ));
            }

            return result;
        }

        public int activeCount() {
            int alphaCount = (int) alphaStrategies.values().stream()
                    .filter(ActiveFundExecutor::isEnabled).count();
            int psiCount = (int) psiMirrorFunds.values().stream()
                    .filter(f -> f.config().enabled()).count();
            return alphaCount + psiCount;
        }
    }

    public record FundStatus(
            String fundType,
            String category,
            boolean enabled,
            Map<String, Object> metrics
    ) {}
}
