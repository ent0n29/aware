-- ============================================================================
-- AWARE ML Explainability Schema
-- ============================================================================
-- Stores ML model metadata, feature importance, tier boundaries, and training history
-- for transparency, monitoring, and debugging.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Feature Importance
-- ----------------------------------------------------------------------------
-- Stores feature importance scores from XGBoost and other models.
-- Updated after each training run.

CREATE TABLE IF NOT EXISTS polybot.aware_ml_feature_importance (
    feature_name        String,
    importance_score    Float32,
    importance_rank     UInt16,
    model_version       LowCardinality(String),
    importance_type     LowCardinality(String) DEFAULT 'weight',  -- 'weight', 'gain', 'cover'
    calculated_at       DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(calculated_at)
ORDER BY (model_version, feature_name)
SETTINGS index_granularity = 8192;


-- ----------------------------------------------------------------------------
-- Tier Boundaries
-- ----------------------------------------------------------------------------
-- Documents the score ranges for each tier (BRONZE, SILVER, GOLD, DIAMOND).
-- Used for explainability and consistency checks.

CREATE TABLE IF NOT EXISTS polybot.aware_ml_tier_boundaries (
    tier_name           LowCardinality(String),  -- BRONZE, SILVER, GOLD, DIAMOND
    tier_order          UInt8,                   -- 1, 2, 3, 4 for sorting
    score_min           Float32,
    score_max           Float32,
    confidence_threshold Float32 DEFAULT 0.5,
    description         String,
    model_version       LowCardinality(String),
    updated_at          DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (model_version, tier_order)
SETTINGS index_granularity = 8192;


-- ----------------------------------------------------------------------------
-- Training Runs
-- ----------------------------------------------------------------------------
-- Logs each model training run for tracking and rollback capability.

CREATE TABLE IF NOT EXISTS polybot.aware_ml_training_runs (
    run_id              UUID DEFAULT generateUUIDv4(),
    model_version       LowCardinality(String),
    started_at          DateTime64(3),
    completed_at        DateTime64(3),
    duration_seconds    UInt32,
    status              LowCardinality(String) DEFAULT 'running',  -- 'running', 'success', 'failed', 'rolled_back'

    -- Training data stats
    n_traders           UInt32,
    n_trades            UInt32,
    train_split_ratio   Float32,

    -- Final metrics
    tier_accuracy       Float32,
    sharpe_mae          Float32,
    val_loss            Float32,

    -- Trigger info
    trigger_reason      LowCardinality(String),  -- 'scheduled', 'drift', 'manual'
    triggered_by        String DEFAULT 'system',

    -- Hyperparameters (JSON blob)
    hyperparameters     String,

    -- Notes
    notes               String DEFAULT ''
)
ENGINE = MergeTree()
ORDER BY (started_at)
PARTITION BY toYYYYMM(started_at)
SETTINGS index_granularity = 8192;


-- ----------------------------------------------------------------------------
-- Drift Reports
-- ----------------------------------------------------------------------------
-- Stores drift detection results for monitoring.

CREATE TABLE IF NOT EXISTS polybot.aware_ml_drift_reports (
    report_id           UUID DEFAULT generateUUIDv4(),
    checked_at          DateTime64(3) DEFAULT now64(3),

    -- Summary
    alert_level         LowCardinality(String),  -- 'normal', 'warning', 'critical'
    drift_ratio         Float32,                 -- Fraction of features that drifted
    n_features          UInt16,
    n_drifted           UInt16,

    -- Baseline info
    baseline_date       DateTime64(3),
    n_samples_baseline  UInt32,
    n_samples_current   UInt32,

    -- Action taken
    retrain_triggered   UInt8 DEFAULT 0,
    retrain_reason      String DEFAULT '',

    -- Detailed results (JSON array)
    feature_results     String
)
ENGINE = MergeTree()
ORDER BY (checked_at)
PARTITION BY toYYYYMM(checked_at)
SETTINGS index_granularity = 8192;


-- ============================================================================
-- Seed Data: Default Tier Boundaries
-- ============================================================================

INSERT INTO polybot.aware_ml_tier_boundaries
(tier_name, tier_order, score_min, score_max, confidence_threshold, description, model_version)
VALUES
('BRONZE', 1, 0.0, 49.9, 0.3, 'Entry-level traders. May have limited history or inconsistent performance.', 'ensemble_v1'),
('SILVER', 2, 50.0, 69.9, 0.4, 'Developing traders. Show some edge but not consistently profitable.', 'ensemble_v1'),
('GOLD', 3, 70.0, 89.9, 0.5, 'Skilled traders. Consistent profitability with good risk management.', 'ensemble_v1'),
('DIAMOND', 4, 90.0, 100.0, 0.7, 'Elite traders. Top performers with exceptional track records.', 'ensemble_v1');


-- ============================================================================
-- Views
-- ============================================================================

-- Latest feature importance
CREATE VIEW IF NOT EXISTS polybot.v_ml_feature_importance_latest AS
SELECT
    feature_name,
    importance_score,
    importance_rank,
    model_version,
    importance_type
FROM polybot.aware_ml_feature_importance FINAL
WHERE model_version = (
    SELECT model_version
    FROM polybot.aware_ml_feature_importance
    ORDER BY calculated_at DESC
    LIMIT 1
)
ORDER BY importance_rank;


-- Latest training run
CREATE VIEW IF NOT EXISTS polybot.v_ml_training_latest AS
SELECT *
FROM polybot.aware_ml_training_runs
WHERE status = 'success'
ORDER BY completed_at DESC
LIMIT 1;


-- Drift trend (last 30 days)
CREATE VIEW IF NOT EXISTS polybot.v_ml_drift_trend AS
SELECT
    toDate(checked_at) AS date,
    avg(drift_ratio) AS avg_drift_ratio,
    max(drift_ratio) AS max_drift_ratio,
    countIf(alert_level = 'warning') AS warning_count,
    countIf(alert_level = 'critical') AS critical_count,
    countIf(retrain_triggered = 1) AS retrains_triggered
FROM polybot.aware_ml_drift_reports
WHERE checked_at >= now() - INTERVAL 30 DAY
GROUP BY date
ORDER BY date;
