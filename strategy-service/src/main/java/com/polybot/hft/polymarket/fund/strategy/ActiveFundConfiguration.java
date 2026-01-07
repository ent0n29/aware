package com.polybot.hft.polymarket.fund.strategy;

import com.polybot.hft.config.HftProperties;
import com.polybot.hft.polymarket.fund.config.ActiveFundConfig;
import com.polybot.hft.polymarket.fund.config.FundConfig;
import com.polybot.hft.polymarket.fund.model.FundType;
import com.polybot.hft.polymarket.fund.service.FundRegistry;
import com.polybot.hft.strategy.executor.ExecutorApiClient;
import io.micrometer.core.instrument.MeterRegistry;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

import java.time.Clock;

/**
 * Spring configuration for active alpha fund strategies.
 *
 * Enabled when hft.fund.enabled=true AND fund type starts with "ALPHA-".
 *
 * Wires up:
 * - ActiveFundConfig for alpha-specific settings
 * - InsiderFollowStrategy for ALPHA-INSIDER fund
 * - Scheduled tasks for polling and execution
 */
@Slf4j
@Configuration
@EnableScheduling
@ConditionalOnProperty(prefix = "hft.fund", name = "enabled", havingValue = "true")
public class ActiveFundConfiguration {

    /**
     * Create ActiveFundConfig from base FundConfig.
     * Only created for ALPHA-* fund types.
     */
    @Bean
    @ConditionalOnProperty(prefix = "hft.fund", name = "index-type", havingValue = "ALPHA-INSIDER")
    public ActiveFundConfig activeFundConfig(FundConfig fundConfig) {
        ActiveFundConfig config = ActiveFundConfig.forInsiderStrategy(fundConfig);
        log.info("Active fund configuration loaded: type={}, capital=${}, minConfidence={}",
                config.fundType(), config.capitalUsd(), config.minConfidence());
        return config;
    }

    /**
     * Create InsiderFollowStrategy for ALPHA-INSIDER fund.
     */
    @Bean
    @ConditionalOnProperty(prefix = "hft.fund", name = "index-type", havingValue = "ALPHA-INSIDER")
    public InsiderFollowStrategy insiderFollowStrategy(
            ActiveFundConfig config,
            ExecutorApiClient executorApi,
            JdbcTemplate jdbcTemplate,
            FundRegistry fundRegistry,
            MeterRegistry meterRegistry
    ) {
        InsiderFollowStrategy strategy = new InsiderFollowStrategy(
                config,
                executorApi,
                jdbcTemplate,
                Clock.systemUTC(),
                meterRegistry
        );

        // Register with FundRegistry
        if (config.enabled()) {
            try {
                FundType fundType = FundType.fromId(config.fundType());
                fundRegistry.registerFund(config.fundType(), fundType, config.capitalUsd());
                log.info("Registered {} with FundRegistry", config.fundType());
            } catch (IllegalArgumentException e) {
                log.warn("Unknown fund type '{}', skipping registry", config.fundType());
            }
        }

        log.info("InsiderFollowStrategy created for ALPHA-INSIDER fund");
        return strategy;
    }

    /**
     * Scheduled task to poll for insider alerts.
     *
     * Runs every 5 seconds to check for new alerts from the Python analytics pipeline.
     */
    @Bean
    @ConditionalOnProperty(prefix = "hft.fund", name = "index-type", havingValue = "ALPHA-INSIDER")
    public InsiderAlertPoller insiderAlertPoller(InsiderFollowStrategy strategy) {
        return new InsiderAlertPoller(strategy);
    }

    @Slf4j
    public static class InsiderAlertPoller {
        private final InsiderFollowStrategy strategy;

        public InsiderAlertPoller(InsiderFollowStrategy strategy) {
            this.strategy = strategy;
            log.info("InsiderAlertPoller initialized - will poll for alerts every 5 seconds");
        }

        @Scheduled(fixedRate = 5000)
        public void pollForAlerts() {
            try {
                strategy.pollForSignals();
            } catch (Exception e) {
                log.warn("Error polling for insider alerts: {}", e.getMessage());
            }
        }
    }

    /**
     * Scheduled task to process queued signals.
     *
     * Runs every 100ms to execute signals whose delay has expired.
     */
    @Bean
    @ConditionalOnProperty(prefix = "hft.fund", name = "index-type", havingValue = "ALPHA-INSIDER")
    public ActiveSignalProcessor activeSignalProcessor(InsiderFollowStrategy strategy) {
        return new ActiveSignalProcessor(strategy);
    }

    @Slf4j
    public static class ActiveSignalProcessor {
        private final ActiveFundExecutor executor;

        public ActiveSignalProcessor(ActiveFundExecutor executor) {
            this.executor = executor;
        }

        @Scheduled(fixedRate = 100)
        public void processQueuedSignals() {
            try {
                executor.processQueuedSignals();
            } catch (Exception e) {
                log.warn("Error processing queued signals: {}", e.getMessage());
            }
        }
    }

    // ============== ALPHA-EDGE Configuration ==============

    /**
     * Create ActiveFundConfig for ALPHA-EDGE fund.
     * Uses ML edge scores to identify high-edge traders.
     */
    @Bean
    @ConditionalOnProperty(prefix = "hft.fund", name = "index-type", havingValue = "ALPHA-EDGE")
    public ActiveFundConfig edgeFundConfig(FundConfig fundConfig) {
        ActiveFundConfig config = ActiveFundConfig.forEdgeStrategy(fundConfig);
        log.info("Edge fund configuration loaded: type={}, capital=${}, minConfidence={}",
                config.fundType(), config.capitalUsd(), config.minConfidence());
        return config;
    }

    /**
     * Create MLEdgeStrategy for ALPHA-EDGE fund.
     */
    @Bean
    @ConditionalOnProperty(prefix = "hft.fund", name = "index-type", havingValue = "ALPHA-EDGE")
    public MLEdgeStrategy mlEdgeStrategy(
            ActiveFundConfig config,
            ExecutorApiClient executorApi,
            JdbcTemplate jdbcTemplate,
            FundRegistry fundRegistry,
            MeterRegistry meterRegistry
    ) {
        MLEdgeStrategy strategy = new MLEdgeStrategy(
                config,
                executorApi,
                jdbcTemplate,
                Clock.systemUTC(),
                meterRegistry
        );

        // Register with FundRegistry
        if (config.enabled()) {
            try {
                FundType fundType = FundType.fromId(config.fundType());
                fundRegistry.registerFund(config.fundType(), fundType, config.capitalUsd());
                log.info("Registered {} with FundRegistry", config.fundType());
            } catch (IllegalArgumentException e) {
                log.warn("Unknown fund type '{}', skipping registry", config.fundType());
            }
        }

        log.info("MLEdgeStrategy created for ALPHA-EDGE fund");
        return strategy;
    }

    /**
     * Scheduled task to poll for ML edge scores and trades.
     *
     * Runs every 10 seconds to check for high-edge trader activity.
     */
    @Bean
    @ConditionalOnProperty(prefix = "hft.fund", name = "index-type", havingValue = "ALPHA-EDGE")
    public MLEdgePoller mlEdgePoller(MLEdgeStrategy strategy) {
        return new MLEdgePoller(strategy);
    }

    @Slf4j
    public static class MLEdgePoller {
        private final MLEdgeStrategy strategy;

        public MLEdgePoller(MLEdgeStrategy strategy) {
            this.strategy = strategy;
            log.info("MLEdgePoller initialized - will poll for ML scores every 10 seconds");
        }

        @Scheduled(fixedRate = 10000)
        public void pollForEdgeScores() {
            try {
                strategy.pollForSignals();
            } catch (Exception e) {
                log.warn("Error polling for ML edge scores: {}", e.getMessage());
            }
        }
    }

    /**
     * Scheduled task to process queued signals for ALPHA-EDGE.
     *
     * Runs every 100ms to execute signals whose delay has expired.
     */
    @Bean
    @ConditionalOnProperty(prefix = "hft.fund", name = "index-type", havingValue = "ALPHA-EDGE")
    public ActiveSignalProcessor edgeSignalProcessor(MLEdgeStrategy strategy) {
        return new ActiveSignalProcessor(strategy);
    }

    // ============== ALPHA-ARB Configuration ==============

    /**
     * Create ActiveFundConfig for ALPHA-ARB fund.
     * Complete-set arbitrage on binary markets.
     */
    @Bean
    @ConditionalOnProperty(prefix = "hft.fund", name = "index-type", havingValue = "ALPHA-ARB")
    public ActiveFundConfig arbFundConfig(FundConfig fundConfig) {
        ActiveFundConfig config = ActiveFundConfig.forArbStrategy(fundConfig);
        log.info("Arb fund configuration loaded: type={}, capital=${}, minConfidence={}",
                config.fundType(), config.capitalUsd(), config.minConfidence());
        return config;
    }

    /**
     * Create ArbStrategy for ALPHA-ARB fund.
     */
    @Bean
    @ConditionalOnProperty(prefix = "hft.fund", name = "index-type", havingValue = "ALPHA-ARB")
    public ArbStrategy arbStrategy(
            ActiveFundConfig config,
            ExecutorApiClient executorApi,
            JdbcTemplate jdbcTemplate,
            FundRegistry fundRegistry,
            MeterRegistry meterRegistry,
            com.polybot.hft.polymarket.ws.ClobMarketWebSocketClient marketWs
    ) {
        ArbStrategy strategy = new ArbStrategy(
                config,
                executorApi,
                jdbcTemplate,
                Clock.systemUTC(),
                meterRegistry,
                marketWs
        );

        // Register with FundRegistry
        if (config.enabled()) {
            try {
                FundType fundType = FundType.fromId(config.fundType());
                fundRegistry.registerFund(config.fundType(), fundType, config.capitalUsd());
                log.info("Registered {} with FundRegistry", config.fundType());
            } catch (IllegalArgumentException e) {
                log.warn("Unknown fund type '{}', skipping registry", config.fundType());
            }
        }

        log.info("ArbStrategy created for ALPHA-ARB fund");
        return strategy;
    }

    /**
     * Scheduled task to poll for arb opportunities.
     *
     * Runs every 2 seconds to check for pricing inefficiencies.
     */
    @Bean
    @ConditionalOnProperty(prefix = "hft.fund", name = "index-type", havingValue = "ALPHA-ARB")
    public ArbOpportunityPoller arbOpportunityPoller(ArbStrategy strategy) {
        return new ArbOpportunityPoller(strategy);
    }

    @Slf4j
    public static class ArbOpportunityPoller {
        private final ArbStrategy strategy;

        public ArbOpportunityPoller(ArbStrategy strategy) {
            this.strategy = strategy;
            log.info("ArbOpportunityPoller initialized - will poll for arb opportunities every 2 seconds");
        }

        @Scheduled(fixedRate = 2000)
        public void pollForArbOpportunities() {
            try {
                strategy.pollForSignals();
            } catch (Exception e) {
                log.warn("Error polling for arb opportunities: {}", e.getMessage());
            }
        }

        @Scheduled(fixedRate = 60000)
        public void checkResolvedPositions() {
            try {
                strategy.checkResolvedPositions();
            } catch (Exception e) {
                log.warn("Error checking resolved positions: {}", e.getMessage());
            }
        }
    }

    /**
     * Scheduled task to process queued signals for ALPHA-ARB.
     *
     * Runs every 50ms for faster execution (arb opportunities are time-sensitive).
     */
    @Bean
    @ConditionalOnProperty(prefix = "hft.fund", name = "index-type", havingValue = "ALPHA-ARB")
    public ActiveSignalProcessor arbSignalProcessor(ArbStrategy strategy) {
        return new ActiveSignalProcessor(strategy);
    }
}
