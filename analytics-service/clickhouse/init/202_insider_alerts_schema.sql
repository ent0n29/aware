-- ═══════════════════════════════════════════════════════════════════════════════
-- AWARE Analytics - Insider Detection Schema
-- ═══════════════════════════════════════════════════════════════════════════════
--
-- Tables for storing insider activity alerts and tracking detection performance.
--

-- Insider alerts table
CREATE TABLE IF NOT EXISTS polybot.aware_insider_alerts (
    signal_type String,           -- NEW_ACCOUNT_WHALE, VOLUME_SPIKE, etc.
    severity String,              -- LOW, MEDIUM, HIGH, CRITICAL
    market_slug String,
    market_question String,
    description String,
    confidence Float32,           -- 0.0 to 1.0
    direction String,             -- YES or NO
    total_volume_usd Float64,
    num_traders UInt32,
    detected_at DateTime,
    traders_involved String,      -- Comma-separated list

    -- Tracking fields
    outcome Nullable(String),     -- Filled when market resolves (YES/NO)
    was_correct Nullable(UInt8),  -- 1 if alert direction matched outcome
    resolved_at Nullable(DateTime),

    -- Versioning for updates
    _version UInt64 DEFAULT toUnixTimestamp(now())
)
ENGINE = ReplacingMergeTree(_version)
ORDER BY (market_slug, signal_type, detected_at)
PARTITION BY toYYYYMM(detected_at);


-- Insider detection performance view
CREATE OR REPLACE VIEW polybot.aware_insider_detection_performance AS
SELECT
    signal_type,
    severity,
    count() as total_alerts,
    countIf(was_correct = 1) as correct_predictions,
    countIf(was_correct = 0) as incorrect_predictions,
    countIf(was_correct IS NULL) as unresolved,
    if(countIf(was_correct IS NOT NULL) > 0,
       countIf(was_correct = 1) / countIf(was_correct IS NOT NULL),
       0) as accuracy,
    avg(confidence) as avg_confidence,
    sum(total_volume_usd) as total_volume_flagged
FROM polybot.aware_insider_alerts FINAL
GROUP BY signal_type, severity
ORDER BY signal_type, severity;


-- Daily insider activity summary
CREATE OR REPLACE VIEW polybot.aware_insider_daily_summary AS
SELECT
    toDate(detected_at) as date,
    count() as total_alerts,
    countIf(severity = 'CRITICAL') as critical_alerts,
    countIf(severity = 'HIGH') as high_alerts,
    countIf(severity = 'MEDIUM') as medium_alerts,
    sum(total_volume_usd) as total_suspicious_volume,
    uniqExact(market_slug) as unique_markets,
    avg(confidence) as avg_confidence
FROM polybot.aware_insider_alerts FINAL
GROUP BY date
ORDER BY date DESC;


-- Top suspicious markets (for dashboard)
CREATE OR REPLACE VIEW polybot.aware_top_suspicious_markets AS
SELECT
    market_slug,
    argMax(signal_type, detected_at) as latest_signal,
    argMax(severity, detected_at) as latest_severity,
    argMax(direction, detected_at) as predicted_direction,
    count() as total_signals,
    max(confidence) as max_confidence,
    sum(total_volume_usd) as total_suspicious_volume,
    max(detected_at) as last_alert_at
FROM polybot.aware_insider_alerts FINAL
WHERE detected_at >= now() - INTERVAL 7 DAY
GROUP BY market_slug
HAVING total_signals >= 1
ORDER BY max_confidence DESC, total_signals DESC
LIMIT 100;


-- Trader insider activity tracking
-- Track which traders appear in insider alerts (for identifying potential insiders)
CREATE TABLE IF NOT EXISTS polybot.aware_insider_traders (
    proxy_address String,
    username String,
    signal_type String,
    market_slug String,
    bet_direction String,
    bet_size_usd Float64,
    detected_at DateTime,
    market_outcome Nullable(String),  -- Updated when resolved
    profit_if_correct Float64,        -- Estimated profit

    _version UInt64 DEFAULT toUnixTimestamp(now())
)
ENGINE = ReplacingMergeTree(_version)
ORDER BY (proxy_address, market_slug, detected_at)
PARTITION BY toYYYYMM(detected_at);


-- Traders with repeated insider-like behavior
CREATE OR REPLACE VIEW polybot.aware_repeat_insider_suspects AS
SELECT
    proxy_address,
    username,
    count() as times_flagged,
    countIf(market_outcome IS NOT NULL AND bet_direction = market_outcome) as correct_bets,
    countIf(market_outcome IS NOT NULL) as resolved_bets,
    if(resolved_bets > 0, correct_bets / resolved_bets, 0) as success_rate,
    sum(bet_size_usd) as total_suspicious_volume,
    arrayDistinct(groupArray(signal_type)) as signal_types
FROM polybot.aware_insider_traders FINAL
GROUP BY proxy_address, username
HAVING times_flagged >= 2  -- Flagged at least twice
ORDER BY success_rate DESC, times_flagged DESC;
