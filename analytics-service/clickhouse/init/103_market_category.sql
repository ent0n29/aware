-- Market Category Classification
-- Adds market_category column to aware_global_trades for sectorial index filtering.
-- Categories: CRYPTO, POLITICS, SPORTS, NEWS, ENTERTAINMENT, ECONOMICS, SCIENCE, OTHER

-- =============================================================================
-- ADD market_category COLUMN TO aware_global_trades
-- =============================================================================

-- Add the column if it doesn't exist (ClickHouse will skip if already exists)
ALTER TABLE polybot.aware_global_trades
ADD COLUMN IF NOT EXISTS market_category LowCardinality(String) DEFAULT '';

-- =============================================================================
-- CREATE DEDICATED MARKET CLASSIFICATION TABLE
-- This stores the classification for each unique market_slug
-- Python job classifies each slug once, then we can join efficiently
-- =============================================================================

CREATE TABLE IF NOT EXISTS polybot.aware_market_classifications (
    market_slug LowCardinality(String),
    market_category LowCardinality(String),  -- CRYPTO, POLITICS, SPORTS, etc.
    confidence Float32,                       -- Classification confidence (0-1)
    matched_patterns String,                  -- Debug: which patterns matched
    classified_at DateTime64(3) DEFAULT now64(3),
    _version UInt64 DEFAULT toUnixTimestamp64Milli(now64(3))
)
ENGINE = ReplacingMergeTree(_version)
ORDER BY (market_slug)
SETTINGS index_granularity = 8192;

-- =============================================================================
-- CREATE VIEW FOR CATEGORY-ENRICHED TRADES
-- Joins trades with classifications for easy querying
-- =============================================================================

CREATE OR REPLACE VIEW polybot.aware_global_trades_with_category AS
SELECT
    t.*,
    COALESCE(c.market_category, 'OTHER') AS category,
    COALESCE(c.confidence, 0.0) AS category_confidence
FROM polybot.aware_global_trades_dedup t
LEFT JOIN polybot.aware_market_classifications c FINAL
    ON t.market_slug = c.market_slug;

-- =============================================================================
-- TRADER CATEGORY DISTRIBUTION VIEW
-- Pre-aggregated category breakdown per trader (used by PSI sectorial indexes)
-- =============================================================================

CREATE OR REPLACE VIEW polybot.aware_trader_category_distribution AS
SELECT
    t.proxy_address,
    t.username,
    c.market_category AS category,
    sum(t.notional) AS volume,
    count() AS trade_count,
    sum(t.notional) / sum(sum(t.notional)) OVER (PARTITION BY t.proxy_address) AS concentration
FROM polybot.aware_global_trades_dedup t
LEFT JOIN polybot.aware_market_classifications c FINAL
    ON t.market_slug = c.market_slug
WHERE t.proxy_address != ''
GROUP BY t.proxy_address, t.username, c.market_category;

-- =============================================================================
-- MATERIALIZED VIEW: AUTO-CLASSIFY NEW TRADES (FUTURE)
-- When proper ML classification is in place, this can auto-tag new trades
-- For now, classification is done by batch job (market_classification_job.py)
-- =============================================================================

-- Placeholder: In future, could use a MV to set category on insert:
-- CREATE MATERIALIZED VIEW IF NOT EXISTS polybot.aware_global_trades_classify_mv
-- TO polybot.aware_global_trades
-- AS SELECT *, classifyMarket(market_slug) AS market_category ...

-- =============================================================================
-- CATEGORY STATISTICS VIEW
-- Shows trade distribution across categories
-- =============================================================================

CREATE OR REPLACE VIEW polybot.aware_category_stats AS
SELECT
    COALESCE(c.market_category, 'UNCLASSIFIED') AS category,
    count() AS trade_count,
    uniqExact(t.proxy_address) AS unique_traders,
    uniqExact(t.market_slug) AS unique_markets,
    sum(t.notional) AS total_volume,
    min(t.ts) AS first_trade,
    max(t.ts) AS last_trade
FROM polybot.aware_global_trades_dedup t
LEFT JOIN polybot.aware_market_classifications c FINAL
    ON t.market_slug = c.market_slug
GROUP BY category
ORDER BY total_volume DESC;
