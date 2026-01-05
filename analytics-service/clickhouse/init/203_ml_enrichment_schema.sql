-- ============================================================================
-- ML ENRICHMENT SCHEMA
-- Stores unsupervised ML model outputs: Strategy DNA clustering + Anomaly Detection
-- ============================================================================

-- ============================================================================
-- STRATEGY DNA CLUSTERING
-- Groups traders into behavioral archetypes based on 35-feature analysis
-- ============================================================================

-- Current cluster assignments
CREATE TABLE IF NOT EXISTS polybot.aware_ml_enrichment (
  -- Identity
  proxy_address String,
  username LowCardinality(String),

  -- Strategy DNA Clustering
  cluster_id UInt8,                                -- 0-7 cluster index
  strategy_cluster LowCardinality(String),         -- ARBITRAGEUR, SCALPER, WHALE, etc.
  cluster_description String,                      -- Human-readable description

  -- Anomaly Detection
  is_anomaly UInt8,                                -- 0 or 1
  anomaly_score Float32,                           -- Isolation Forest score (-1 to 1, lower = more anomalous)
  anomaly_type LowCardinality(String),             -- NORMAL, ISOLATION, RECONSTRUCTION, BOTH

  -- Metadata
  updated_at DateTime64(3) DEFAULT now64(3),
  model_version LowCardinality(String) DEFAULT 'v1'
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (proxy_address);


-- Historical cluster assignments (for tracking strategy evolution)
CREATE TABLE IF NOT EXISTS polybot.aware_ml_enrichment_history (
  proxy_address String,
  username LowCardinality(String),
  cluster_id UInt8,
  strategy_cluster LowCardinality(String),
  is_anomaly UInt8,
  anomaly_score Float32,
  updated_at DateTime64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(updated_at)
ORDER BY (proxy_address, updated_at)
TTL toDateTime(updated_at) + INTERVAL 90 DAY;


-- Cluster profiles (updated by ML job)
CREATE TABLE IF NOT EXISTS polybot.aware_cluster_profiles (
  cluster_id UInt8,
  cluster_label LowCardinality(String),
  description String,
  trader_count UInt32,

  -- Centroid feature values
  avg_sharpe_ratio Float32,
  avg_win_rate Float32,
  avg_trades_per_day Float32,
  avg_hold_hours Float32,
  avg_complete_set_ratio Float32,
  avg_volume_usd Float64,

  -- Replicability (can this strategy be mirrored with delay?)
  is_replicable UInt8,                            -- 0 = HFT/arb, 1 = can mirror

  -- Metadata
  updated_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (cluster_id);


-- ============================================================================
-- ANOMALY TRACKING
-- Track detected anomalies for investigation
-- ============================================================================

-- Detected anomalies (subset of traders flagged as anomalous)
CREATE TABLE IF NOT EXISTS polybot.aware_anomalies (
  detected_at DateTime64(3) DEFAULT now64(3),
  proxy_address String,
  username LowCardinality(String),

  -- Detection details
  anomaly_type LowCardinality(String),            -- ISOLATION, RECONSTRUCTION, BOTH
  anomaly_score Float32,
  isolation_forest_score Float32,
  autoencoder_score Nullable(Float32),

  -- Suspicious indicators
  suspected_reason LowCardinality(String),        -- WASH_TRADING, SYBIL, INDEX_GAMING, UNUSUAL, etc.
  confidence Float32,

  -- Investigation status
  status LowCardinality(String) DEFAULT 'NEW',    -- NEW, INVESTIGATING, CONFIRMED, DISMISSED
  notes String DEFAULT '',
  resolved_at Nullable(DateTime64(3)),

  -- Feature snapshot at detection time
  total_trades UInt64,
  total_volume_usd Float64,
  complete_set_ratio Float32,
  trades_per_hour Float32
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(detected_at)
ORDER BY (detected_at, proxy_address);


-- ============================================================================
-- VIEWS FOR DASHBOARD
-- ============================================================================

-- Traders with ML enrichment (Strategy DNA + Anomaly flag)
CREATE OR REPLACE VIEW polybot.aware_traders_enriched AS
SELECT
  s.rank,
  s.username,
  p.pseudonym,
  s.proxy_address,
  s.total_score AS smart_money_score,
  s.tier,
  p.total_pnl,
  p.total_volume_usd AS total_volume,
  s.strategy_type AS rule_based_strategy,        -- From rule-based classifier
  ml.strategy_cluster AS ml_strategy,            -- From K-means clustering
  ml.cluster_id,
  ml.is_anomaly,
  ml.anomaly_score,
  ml.anomaly_type,
  s.calculated_at
FROM (SELECT * FROM polybot.aware_smart_money_scores FINAL) AS s
LEFT JOIN (SELECT * FROM polybot.aware_trader_profiles FINAL) AS p
  ON s.proxy_address = p.proxy_address
LEFT JOIN (SELECT * FROM polybot.aware_ml_enrichment FINAL) AS ml
  ON s.proxy_address = ml.proxy_address
ORDER BY s.rank ASC;


-- Cluster distribution summary
CREATE OR REPLACE VIEW polybot.aware_cluster_summary AS
SELECT
  cluster_id,
  strategy_cluster,
  count() AS trader_count,
  sum(is_anomaly) AS anomaly_count,
  avg(anomaly_score) AS avg_anomaly_score,
  min(updated_at) AS first_assigned,
  max(updated_at) AS last_updated
FROM polybot.aware_ml_enrichment FINAL
GROUP BY cluster_id, strategy_cluster
ORDER BY trader_count DESC;


-- Active anomalies for investigation
CREATE OR REPLACE VIEW polybot.aware_active_anomalies AS
SELECT
  a.*,
  p.username AS profile_username,
  p.total_pnl,
  s.total_score AS smart_money_score,
  s.tier
FROM polybot.aware_anomalies AS a
LEFT JOIN (SELECT * FROM polybot.aware_trader_profiles FINAL) AS p
  ON a.proxy_address = p.proxy_address
LEFT JOIN (SELECT * FROM polybot.aware_smart_money_scores FINAL) AS s
  ON a.proxy_address = s.proxy_address
WHERE a.status IN ('NEW', 'INVESTIGATING')
ORDER BY a.detected_at DESC;


-- Strategy cluster performance (compare clusters by profitability)
CREATE OR REPLACE VIEW polybot.aware_cluster_performance AS
SELECT
  ml.strategy_cluster,
  ml.cluster_id,
  count() AS trader_count,
  avg(p.total_pnl) AS avg_pnl,
  sum(p.total_pnl) AS total_pnl,
  avg(s.total_score) AS avg_smart_money_score,
  avg(p.total_volume_usd) AS avg_volume,
  countIf(p.total_pnl > 0) AS profitable_traders,
  countIf(p.total_pnl > 0) / count() AS profitable_ratio
FROM (SELECT * FROM polybot.aware_ml_enrichment FINAL) AS ml
LEFT JOIN (SELECT * FROM polybot.aware_trader_profiles FINAL) AS p
  ON ml.proxy_address = p.proxy_address
LEFT JOIN (SELECT * FROM polybot.aware_smart_money_scores FINAL) AS s
  ON ml.proxy_address = s.proxy_address
GROUP BY ml.strategy_cluster, ml.cluster_id
ORDER BY avg_pnl DESC;


-- Replicable vs non-replicable strategies
CREATE OR REPLACE VIEW polybot.aware_replicability_summary AS
SELECT
  is_replicable,
  count() AS cluster_count,
  sum(trader_count) AS total_traders,
  arrayStringConcat(groupArray(cluster_label), ', ') AS strategy_types
FROM (SELECT * FROM polybot.aware_cluster_profiles FINAL)
GROUP BY is_replicable;
