-- AWARE FUND Schema Extensions
-- Extends the Polybot ClickHouse database with AWARE-specific tables for
-- global trade tracking, trader profiling, and Smart Money Scores.

-- ============================================================================
-- KAFKA CONSUMER FOR aware.events TOPIC
-- ============================================================================

-- Raw Kafka consumer table for AWARE events
CREATE TABLE IF NOT EXISTS polybot.aware_kafka_events_raw (
  raw String
)
ENGINE = Kafka
SETTINGS
  kafka_broker_list = 'redpanda:29092',
  kafka_topic_list = 'aware.events',
  kafka_group_name = 'clickhouse-aware-analytics',
  kafka_format = 'JSONAsString',
  kafka_num_consumers = 1;

-- Materialized view to parse and store AWARE events
CREATE MATERIALIZED VIEW IF NOT EXISTS polybot.aware_kafka_events_mv
TO polybot.analytics_events
AS
SELECT
  ifNull(parseDateTime64BestEffortOrNull(JSONExtractString(raw, 'ts')), toDateTime64(_timestamp, 3)) AS ts,
  ifNull(JSONExtractString(raw, 'source'), 'aware-ingestor') AS source,
  ifNull(JSONExtractString(raw, 'type'), 'unknown') AS type,
  ifNull(JSONExtractRaw(raw, 'data'), '{}') AS data,
  now64(3) AS ingested_at,
  _topic AS kafka_topic,
  toInt32(_partition) AS kafka_partition,
  toInt64(_offset) AS kafka_offset,
  toDateTime64(_timestamp, 3) AS kafka_timestamp,
  ifNull(_key, '') AS kafka_key
FROM polybot.aware_kafka_events_raw;

-- ============================================================================
-- GLOBAL TRADES TABLE
-- Stores ALL Polymarket trades from all users (not just tracked users)
-- ============================================================================

CREATE TABLE IF NOT EXISTS polybot.aware_global_trades (
  ts DateTime64(3),
  trade_id String,
  username LowCardinality(String),
  pseudonym String,
  proxy_address String,
  market_slug LowCardinality(String),
  title String,
  condition_id String,
  token_id String,
  side LowCardinality(String),           -- BUY or SELL
  outcome LowCardinality(String),
  outcome_index Int32,
  price Float64,
  size Float64,
  notional Float64,                       -- price * size
  transaction_hash String,
  -- Metadata
  ingested_at DateTime64(3),
  kafka_offset Int64
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(ts)
ORDER BY (trade_id);

-- Materialized view to populate global trades from aware.events
CREATE MATERIALIZED VIEW IF NOT EXISTS polybot.aware_global_trades_mv
TO polybot.aware_global_trades
AS
SELECT
  ts,
  JSONExtractString(data, 'id') AS trade_id,
  JSONExtractString(data, 'username') AS username,
  JSONExtractString(data, 'pseudonym') AS pseudonym,
  JSONExtractString(data, 'proxyWallet') AS proxy_address,
  JSONExtractString(data, 'slug') AS market_slug,
  JSONExtractString(data, 'title') AS title,
  JSONExtractString(data, 'conditionId') AS condition_id,
  JSONExtractString(data, 'asset') AS token_id,
  JSONExtractString(data, 'side') AS side,
  JSONExtractString(data, 'outcome') AS outcome,
  toInt32OrZero(JSONExtractString(data, 'outcomeIndex')) AS outcome_index,
  JSONExtractFloat(data, 'price') AS price,
  JSONExtractFloat(data, 'size') AS size,
  JSONExtractFloat(data, 'price') * JSONExtractFloat(data, 'size') AS notional,
  JSONExtractString(data, 'transactionHash') AS transaction_hash,
  ingested_at,
  kafka_offset
FROM polybot.analytics_events
WHERE type = 'aware.global.trade'
  AND source = 'aware-ingestor';

-- Deduplicated view of global trades
CREATE OR REPLACE VIEW polybot.aware_global_trades_dedup AS
SELECT *
FROM polybot.aware_global_trades
FINAL;

-- ============================================================================
-- TRADER PROFILES (Aggregated Metrics)
-- Updated periodically by the aware-analytics service
-- ============================================================================

CREATE TABLE IF NOT EXISTS polybot.aware_trader_profiles (
  -- Identity
  proxy_address String,
  username LowCardinality(String),
  pseudonym String,

  -- Activity metrics
  total_trades UInt64,
  total_volume_usd Float64,
  unique_markets UInt32,
  first_trade_at DateTime64(3),
  last_trade_at DateTime64(3),
  days_active UInt32,

  -- P&L (from Polymarket leaderboard)
  total_pnl Float64,
  realized_pnl Float64,
  unrealized_pnl Float64,

  -- Trading patterns
  buy_count UInt64,
  sell_count UInt64,
  avg_trade_size Float64,
  avg_price Float64,

  -- Strategy indicators
  complete_set_ratio Float64,             -- % trades in complete sets (hedged)
  direction_bias Float64,                 -- 0-1, tendency towards YES outcomes

  -- Metadata
  updated_at DateTime64(3),
  data_quality LowCardinality(String)     -- 'good', 'partial', 'limited'
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (proxy_address);

-- ============================================================================
-- SMART MONEY SCORES
-- Core AWARE ranking algorithm results
-- ============================================================================

CREATE TABLE IF NOT EXISTS polybot.aware_smart_money_scores (
  -- Identity
  proxy_address String,
  username LowCardinality(String),

  -- Total score (0-100)
  total_score UInt8,
  tier LowCardinality(String),            -- DIAMOND, GOLD, SILVER, BRONZE

  -- Component scores (0-100 each)
  profitability_score Float32,
  risk_adjusted_score Float32,
  consistency_score Float32,
  track_record_score Float32,

  -- Strategy classification
  strategy_type LowCardinality(String),   -- ARBITRAGEUR, MARKET_MAKER, etc.
  strategy_confidence Float32,

  -- Rank tracking
  rank UInt32,
  rank_change Int32,                      -- Positive = moved up

  -- Metadata
  calculated_at DateTime64(3),
  model_version LowCardinality(String)
)
ENGINE = ReplacingMergeTree(calculated_at)
ORDER BY (proxy_address);

-- Historical scores for tracking changes
CREATE TABLE IF NOT EXISTS polybot.aware_smart_money_scores_history (
  proxy_address String,
  username LowCardinality(String),
  total_score UInt8,
  tier LowCardinality(String),
  rank UInt32,
  calculated_at DateTime64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(calculated_at)
ORDER BY (proxy_address, calculated_at);

-- ============================================================================
-- LEADERBOARD VIEW
-- Fast access to current rankings
-- ============================================================================

CREATE OR REPLACE VIEW polybot.aware_leaderboard AS
SELECT
  s.rank,
  s.username,
  p.pseudonym,
  s.proxy_address,
  s.total_score AS smart_money_score,
  s.tier,
  p.total_pnl,
  p.total_volume_usd AS total_volume,
  -- Win rate placeholder (calculated from closed positions)
  0.0 AS win_rate,
  s.strategy_type,
  s.strategy_confidence,
  s.rank_change,
  s.calculated_at
FROM (SELECT * FROM polybot.aware_smart_money_scores FINAL) AS s
LEFT JOIN (SELECT * FROM polybot.aware_trader_profiles FINAL) AS p
  ON s.proxy_address = p.proxy_address
ORDER BY s.rank ASC;

-- ============================================================================
-- PSI INDEX COMPOSITION
-- Moved to 200_fund_schema.sql for better organization
-- ============================================================================

-- ============================================================================
-- INGESTION METRICS
-- Track data quality and ingestion health
-- ============================================================================

CREATE TABLE IF NOT EXISTS polybot.aware_ingestion_metrics (
  ts DateTime64(3),
  metric_name LowCardinality(String),
  metric_value Float64,
  tags Map(String, String)
)
ENGINE = MergeTree
PARTITION BY toDate(ts)
ORDER BY (metric_name, ts)
TTL toDateTime(ts) + INTERVAL 30 DAY;

-- ============================================================================
-- HELPER VIEWS FOR ANALYTICS
-- ============================================================================

-- Trader activity summary (last 24h, 7d, 30d)
CREATE OR REPLACE VIEW polybot.aware_trader_activity_summary AS
SELECT
  proxy_address,
  username,
  count() AS trades_total,
  countIf(ts >= now() - INTERVAL 1 DAY) AS trades_24h,
  countIf(ts >= now() - INTERVAL 7 DAY) AS trades_7d,
  countIf(ts >= now() - INTERVAL 30 DAY) AS trades_30d,
  sum(notional) AS volume_total,
  sumIf(notional, ts >= now() - INTERVAL 1 DAY) AS volume_24h,
  sumIf(notional, ts >= now() - INTERVAL 7 DAY) AS volume_7d,
  uniqExact(market_slug) AS unique_markets,
  min(ts) AS first_trade,
  max(ts) AS last_trade
FROM polybot.aware_global_trades_dedup
GROUP BY proxy_address, username;

-- Daily trade counts for monitoring
CREATE OR REPLACE VIEW polybot.aware_daily_stats AS
SELECT
  toDate(ts) AS day,
  count() AS trade_count,
  uniqExact(proxy_address) AS unique_traders,
  sum(notional) AS total_volume,
  uniqExact(market_slug) AS unique_markets
FROM polybot.aware_global_trades_dedup
GROUP BY day
ORDER BY day DESC;

-- ============================================================================
-- ML-BASED SCORING (Phase 2)
-- Stores predictions from trained ML models
-- ============================================================================

-- Current ML predictions
CREATE TABLE IF NOT EXISTS polybot.aware_ml_scores (
  -- Identity
  proxy_address String,
  username LowCardinality(String),

  -- ML predictions
  ml_score Float32,                          -- 0-100 combined score
  ml_tier LowCardinality(String),            -- Predicted tier
  tier_confidence Float32,                   -- Softmax probability
  predicted_sharpe_30d Float32,              -- Predicted future Sharpe

  -- Key features (for explainability)
  sharpe_ratio Float32,
  win_rate Float32,
  max_drawdown Float32,
  maker_ratio Float32,
  avg_hold_hours Float32,

  -- Ranking
  rank UInt32,

  -- Metadata
  model_version LowCardinality(String),
  calculated_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(calculated_at)
ORDER BY (proxy_address);

-- ML score history for tracking model performance
CREATE TABLE IF NOT EXISTS polybot.aware_ml_scores_history (
  proxy_address String,
  ml_score Float32,
  ml_tier LowCardinality(String),
  predicted_sharpe_30d Float32,
  model_version LowCardinality(String),
  calculated_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(calculated_at)
ORDER BY (proxy_address, calculated_at);

-- Combined leaderboard view with both rule-based and ML scores
-- Note: ClickHouse LEFT JOIN returns 0/empty string for non-matches, not NULL
-- So we use if(ml.proxy_address = '', ...) instead of coalesce()
-- Updated: Now joins aware_trader_pnl to get actual win_rate from P&L calculations
CREATE OR REPLACE VIEW polybot.aware_leaderboard_ml AS
SELECT
  if(ml.proxy_address = '', s.rank, ml.rank) AS rank,
  s.username AS username,
  p.pseudonym AS pseudonym,
  s.proxy_address AS proxy_address,
  -- Use ML score if available, fallback to rule-based
  if(ml.proxy_address = '', toFloat32(s.total_score), ml.ml_score) AS smart_money_score,
  if(ml.proxy_address = '', s.tier, ml.ml_tier) AS tier,
  if(ml.proxy_address = '', 0.0, ml.tier_confidence) AS tier_confidence,
  if(ml.proxy_address = '', 0.0, ml.predicted_sharpe_30d) AS predicted_sharpe_30d,
  -- Features: prefer ML, fallback to P&L-calculated metrics
  if(ml.proxy_address = '', 0.0, ml.sharpe_ratio) AS sharpe_ratio,
  if(ml.proxy_address != '', ml.win_rate, if(pnl.proxy_address != '', pnl.win_rate, 0.0)) AS win_rate,
  if(ml.proxy_address = '', 0.0, ml.max_drawdown) AS max_drawdown,
  if(ml.proxy_address = '', 0.0, ml.maker_ratio) AS maker_ratio,
  -- Profile data
  p.total_pnl AS total_pnl,
  p.total_volume_usd AS total_volume,
  s.strategy_type AS strategy_type,
  s.strategy_confidence AS strategy_confidence,
  -- Metadata
  if(ml.proxy_address = '', 'rule-based', ml.model_version) AS model_version,
  s.calculated_at AS calculated_at
FROM (SELECT * FROM polybot.aware_smart_money_scores FINAL) AS s
LEFT JOIN (SELECT * FROM polybot.aware_trader_profiles FINAL) AS p
  ON s.proxy_address = p.proxy_address
LEFT JOIN (SELECT * FROM polybot.aware_ml_scores FINAL) AS ml
  ON s.proxy_address = ml.proxy_address
LEFT JOIN (SELECT * FROM polybot.aware_trader_pnl FINAL) AS pnl
  ON s.proxy_address = pnl.proxy_address
ORDER BY rank ASC;
