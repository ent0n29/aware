package com.polybot.hft.polymarket.fund.strategy;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.polybot.hft.polymarket.fund.config.ActiveFundConfig;
import com.polybot.hft.polymarket.fund.model.AlphaSignal;
import com.polybot.hft.strategy.executor.ExecutorApiClient;
import io.micrometer.core.instrument.MeterRegistry;
import lombok.extern.slf4j.Slf4j;
import org.springframework.jdbc.core.JdbcTemplate;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.format.DateTimeFormatter;
import java.time.ZoneOffset;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * ALPHA-INSIDER Fund Strategy.
 *
 * Trades based on insider detection signals from the Python analytics pipeline.
 * When the InsiderDetector identifies unusual trading activity suggesting
 * informed trading, this strategy follows those signals.
 *
 * Signal Sources:
 * 1. ClickHouse polling: Reads from polybot.aware_alerts (alert_type = 'INSIDER_DETECTED')
 * 2. Future: Kafka consumption for real-time alerts
 *
 * Signal Flow:
 * 1. InsiderDetector (Python) writes alerts to aware_alerts table
 * 2. This strategy polls for new alerts every N seconds
 * 3. Alerts are converted to AlphaSignals with confidence/sizing
 * 4. ActiveFundExecutor handles execution
 *
 * Filtering:
 * - Minimum confidence threshold (from config)
 * - Signal freshness (max age)
 * - Deduplication (track processed alert IDs)
 * - Market validity (check market is still active)
 *
 * Risk Controls:
 * - Max position per signal
 * - Daily signal limit
 * - Cooldown between signals on same market
 */
@Slf4j
public class InsiderFollowStrategy extends ActiveFundExecutor {

    private static final String FUND_TYPE = "ALPHA-INSIDER";

    // Polling configuration
    private static final int DEFAULT_POLL_INTERVAL_SECONDS = 5;
    private static final int MAX_ALERT_AGE_SECONDS = 300;  // 5 minutes
    private static final int MARKET_COOLDOWN_SECONDS = 60;  // 1 minute between signals on same market

    // JSON parser for alert metadata
    private final ObjectMapper objectMapper = new ObjectMapper();

    // Track processed alerts to avoid duplicates
    private final Set<String> processedAlertIds = ConcurrentHashMap.newKeySet();

    // Track last signal time per market for cooldown
    private final Map<String, Instant> lastSignalByMarket = new ConcurrentHashMap<>();

    // Highwater mark for polling
    private Instant lastPollTime = null;

    // Metrics
    private long alertsPolled = 0;
    private long alertsProcessed = 0;
    private long alertsSkipped = 0;

    public InsiderFollowStrategy(
            ActiveFundConfig config,
            ExecutorApiClient executorApi,
            JdbcTemplate jdbcTemplate,
            Clock clock,
            MeterRegistry meterRegistry
    ) {
        super(config, executorApi, jdbcTemplate, clock, meterRegistry);
    }

    @Override
    public String getFundType() {
        return FUND_TYPE;
    }

    @Override
    protected void onStart() {
        super.onStart();
        log.info("InsiderFollowStrategy starting - polling interval: {}s, max alert age: {}s",
                DEFAULT_POLL_INTERVAL_SECONDS, MAX_ALERT_AGE_SECONDS);
    }

    /**
     * Poll ClickHouse for new insider alerts.
     *
     * Called periodically by scheduled task.
     */
    @Override
    public void pollForSignals() {
        if (!isEnabled()) {
            return;
        }

        try {
            List<InsiderAlert> alerts = fetchNewAlerts();
            alertsPolled += alerts.size();

            for (InsiderAlert alert : alerts) {
                try {
                    processInsiderAlert(alert);
                } catch (Exception e) {
                    log.warn("Error processing alert {}: {}", alert.id, e.getMessage());
                }
            }
        } catch (Exception e) {
            log.warn("Error polling for insider alerts: {}", e.getMessage());
        }
    }

    /**
     * Fetch new insider alerts from ClickHouse.
     */
    private List<InsiderAlert> fetchNewAlerts() {
        Instant now = clock.instant();

        // Initialize polling window
        if (lastPollTime == null) {
            lastPollTime = now.minusSeconds(MAX_ALERT_AGE_SECONDS);
        }

        // Format timestamps for ClickHouse
        DateTimeFormatter fmt = DateTimeFormatter
                .ofPattern("yyyy-MM-dd HH:mm:ss")
                .withZone(ZoneOffset.UTC);
        String fromStr = fmt.format(lastPollTime);
        String toStr = fmt.format(now);

        String sql = """
            SELECT
                id,
                alert_type,
                severity,
                source,
                username,
                market_slug,
                title,
                message,
                metadata,
                created_at,
                expires_at,
                status
            FROM polybot.aware_alerts FINAL
            WHERE alert_type IN ('INSIDER_DETECTED', 'UNUSUAL_ACTIVITY', 'SMART_MONEY_ENTRY')
              AND status = 'ACTIVE'
              AND created_at > toDateTime('%s')
              AND created_at <= toDateTime('%s')
            ORDER BY created_at
            LIMIT 50
            """.formatted(fromStr, toStr);

        try {
            List<InsiderAlert> alerts = jdbcTemplate.query(sql, (rs, rowNum) -> new InsiderAlert(
                    rs.getString("id"),
                    rs.getString("alert_type"),
                    rs.getString("severity"),
                    rs.getString("source"),
                    rs.getString("username"),
                    rs.getString("market_slug"),
                    rs.getString("title"),
                    rs.getString("message"),
                    rs.getString("metadata"),
                    rs.getTimestamp("created_at").toInstant(),
                    rs.getTimestamp("expires_at") != null
                            ? rs.getTimestamp("expires_at").toInstant()
                            : null,
                    rs.getString("status")
            ));

            // Update highwater mark
            lastPollTime = now;

            if (!alerts.isEmpty()) {
                log.info("Fetched {} new insider alerts", alerts.size());
            }

            return alerts;
        } catch (Exception e) {
            log.warn("Alert query error: {}", e.getMessage());
            return List.of();
        }
    }

    /**
     * Process a single insider alert.
     */
    private void processInsiderAlert(InsiderAlert alert) {
        // Skip if already processed
        if (processedAlertIds.contains(alert.id)) {
            return;
        }

        // Skip if too old
        Instant now = clock.instant();
        long ageSeconds = Duration.between(alert.createdAt, now).getSeconds();
        if (ageSeconds > MAX_ALERT_AGE_SECONDS) {
            log.debug("Alert {} too old ({} seconds)", alert.id, ageSeconds);
            alertsSkipped++;
            processedAlertIds.add(alert.id);
            return;
        }

        // Skip if expired
        if (alert.expiresAt != null && alert.expiresAt.isBefore(now)) {
            log.debug("Alert {} expired at {}", alert.id, alert.expiresAt);
            alertsSkipped++;
            processedAlertIds.add(alert.id);
            return;
        }

        // Check market cooldown
        if (isMarketOnCooldown(alert.marketSlug)) {
            log.debug("Market {} on cooldown, skipping alert {}", alert.marketSlug, alert.id);
            alertsSkipped++;
            return;  // Don't mark as processed - try again later
        }

        // Convert to AlphaSignal
        AlphaSignal signal = convertToSignal(alert);

        if (signal != null) {
            // Process through parent executor
            processSignal(signal);
            alertsProcessed++;

            // Update cooldown
            lastSignalByMarket.put(alert.marketSlug, now);
        }

        // Mark as processed
        processedAlertIds.add(alert.id);

        // Cleanup old processed IDs (keep last 1000)
        if (processedAlertIds.size() > 1000) {
            // Simple cleanup - remove oldest (this is a ConcurrentHashSet, so just clear some)
            Iterator<String> iter = processedAlertIds.iterator();
            int toRemove = processedAlertIds.size() - 500;
            while (toRemove > 0 && iter.hasNext()) {
                iter.next();
                iter.remove();
                toRemove--;
            }
        }
    }

    /**
     * Convert an insider alert to an AlphaSignal.
     */
    private AlphaSignal convertToSignal(InsiderAlert alert) {
        // Parse metadata JSON for additional context
        Map<String, Object> metadata = parseMetadata(alert.metadata);

        // Extract key fields from metadata
        String tokenId = getStringOrNull(metadata, "token_id");
        String outcome = getStringOrNull(metadata, "outcome");
        String direction = getStringOrNull(metadata, "direction");
        Double confidence = getDoubleOrDefault(metadata, "confidence", 0.6);
        Double strength = getDoubleOrDefault(metadata, "strength", 0.5);
        Double suggestedSize = getDoubleOrDefault(metadata, "suggested_size_usd", 0.0);

        // Validate required fields
        if (tokenId == null || tokenId.isBlank()) {
            log.warn("Alert {} missing token_id in metadata", alert.id);
            return null;
        }

        // Determine action from direction or alert type
        AlphaSignal.SignalAction action = determineAction(direction, alert.alertType);
        if (action == null) {
            log.warn("Could not determine action for alert {}", alert.id);
            return null;
        }

        // Determine urgency from severity
        AlphaSignal.SignalUrgency urgency = switch (alert.severity.toUpperCase()) {
            case "CRITICAL" -> AlphaSignal.SignalUrgency.CRITICAL;
            case "HIGH" -> AlphaSignal.SignalUrgency.HIGH;
            case "WARNING" -> AlphaSignal.SignalUrgency.MEDIUM;
            default -> AlphaSignal.SignalUrgency.LOW;
        };

        // Build the signal
        return AlphaSignal.builder()
                .signalId(UUID.randomUUID().toString())
                .source(AlphaSignal.SignalSource.INSIDER_DETECTOR)
                .action(action)
                .marketSlug(alert.marketSlug)
                .tokenId(tokenId)
                .outcome(outcome != null ? outcome : "Yes")
                .confidence(confidence)
                .strength(strength)
                .urgency(urgency)
                .suggestedSizeUsd(suggestedSize > 0 ? BigDecimal.valueOf(suggestedSize) : null)
                .suggestedSizePct(config.basePositionPct())
                .reason(alert.title + ": " + alert.message)
                .metadata(metadata)
                .detectedAt(alert.createdAt)
                .expiresAt(alert.expiresAt != null
                        ? alert.expiresAt
                        : alert.createdAt.plusSeconds(config.signalExpirySeconds()))
                .build();
    }

    /**
     * Determine trade action from direction hint or alert type.
     */
    private AlphaSignal.SignalAction determineAction(String direction, String alertType) {
        if (direction != null) {
            return switch (direction.toUpperCase()) {
                case "BUY", "LONG", "YES" -> AlphaSignal.SignalAction.BUY;
                case "SELL", "SHORT", "NO" -> AlphaSignal.SignalAction.SELL;
                default -> null;
            };
        }

        // Default based on alert type (insider entry = BUY)
        return switch (alertType.toUpperCase()) {
            case "INSIDER_DETECTED", "SMART_MONEY_ENTRY" -> AlphaSignal.SignalAction.BUY;
            case "INSIDER_EXIT", "SMART_MONEY_EXIT" -> AlphaSignal.SignalAction.SELL;
            default -> AlphaSignal.SignalAction.BUY;
        };
    }

    /**
     * Check if market is on cooldown.
     */
    private boolean isMarketOnCooldown(String marketSlug) {
        Instant lastSignal = lastSignalByMarket.get(marketSlug);
        if (lastSignal == null) {
            return false;
        }

        long secondsSinceLastSignal = Duration.between(lastSignal, clock.instant()).getSeconds();
        return secondsSinceLastSignal < MARKET_COOLDOWN_SECONDS;
    }

    /**
     * Parse metadata JSON string into a map.
     *
     * Uses Jackson ObjectMapper for proper JSON parsing.
     */
    private Map<String, Object> parseMetadata(String metadataJson) {
        if (metadataJson == null || metadataJson.isBlank() || metadataJson.equals("{}")) {
            return Map.of();
        }

        try {
            return objectMapper.readValue(
                    metadataJson,
                    new TypeReference<Map<String, Object>>() {}
            );
        } catch (Exception e) {
            log.warn("Failed to parse alert metadata: {} - {}", e.getClass().getSimpleName(), e.getMessage());
            return Map.of();
        }
    }

    private String getStringOrNull(Map<String, Object> map, String key) {
        Object value = map.get(key);
        return value != null ? value.toString() : null;
    }

    private Double getDoubleOrDefault(Map<String, Object> map, String key, Double defaultValue) {
        Object value = map.get(key);
        if (value instanceof Number) {
            return ((Number) value).doubleValue();
        }
        return defaultValue;
    }

    // ========== Status Methods ==========

    @Override
    public Map<String, Object> getMetrics() {
        Map<String, Object> baseMetrics = super.getMetrics();
        Map<String, Object> metrics = new HashMap<>(baseMetrics);

        // Add strategy-specific metrics
        metrics.put("alertsPolled", alertsPolled);
        metrics.put("alertsProcessed", alertsProcessed);
        metrics.put("alertsSkipped", alertsSkipped);
        metrics.put("processedAlertIds", processedAlertIds.size());
        metrics.put("marketsOnCooldown", lastSignalByMarket.size());
        metrics.put("lastPollTime", lastPollTime != null ? lastPollTime.toString() : "never");

        return metrics;
    }

    /**
     * Internal record for raw alert data from ClickHouse.
     */
    private record InsiderAlert(
            String id,
            String alertType,
            String severity,
            String source,
            String username,
            String marketSlug,
            String title,
            String message,
            String metadata,
            Instant createdAt,
            Instant expiresAt,
            String status
    ) {}
}
