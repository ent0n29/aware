-- AWARE Market Resolutions Schema
-- Tracks resolved markets from Polymarket for P&L calculation
--
-- This table stores the resolution status of markets that our tracked traders
-- have participated in, enabling accurate P&L calculation.

-- ============================================================================
-- MARKET RESOLUTIONS TABLE
-- ============================================================================

CREATE TABLE IF NOT EXISTS polybot.aware_market_resolutions (
    -- Market identification
    condition_id String,                    -- Primary key for matching trades
    market_slug LowCardinality(String),     -- Human-readable slug
    title String,                           -- Market title/question

    -- Resolution details
    is_resolved UInt8,                      -- 1 = resolved, 0 = pending
    winning_outcome LowCardinality(String), -- 'Yes', 'No', or specific outcome
    winning_outcome_index UInt8,            -- 0 or 1 (for binary markets)

    -- Outcome prices (settlement values)
    outcome_prices Array(Float64),          -- [1.0, 0.0] means first outcome won

    -- Timing
    end_time DateTime64(3),                 -- When market ended
    resolution_time DateTime64(3),          -- When resolution was detected

    -- Metadata
    outcomes Array(String),                 -- ['Yes', 'No'] or custom outcomes
    ingested_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (condition_id);

-- ============================================================================
-- TRADER P&L SUMMARY TABLE
-- ============================================================================
-- Aggregated P&L per trader from resolved positions

CREATE TABLE IF NOT EXISTS polybot.aware_trader_pnl (
    -- Identity
    proxy_address String,
    username LowCardinality(String),

    -- Aggregate P&L
    total_realized_pnl Float64,             -- Sum of all realized P&L
    total_positions_closed UInt32,          -- Number of closed positions
    winning_positions UInt32,               -- Positions with positive P&L
    losing_positions UInt32,                -- Positions with negative P&L

    -- Win rate
    win_rate Float64,                       -- winning / total

    -- Per-market breakdown (top 10)
    top_winning_markets Array(String),
    top_losing_markets Array(String),

    -- Timing
    first_resolution_at DateTime64(3),
    last_resolution_at DateTime64(3),

    -- Metadata
    calculated_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(calculated_at)
ORDER BY (proxy_address);

-- ============================================================================
-- POSITION-LEVEL P&L TABLE
-- ============================================================================
-- Detailed P&L for each position (trader + market combination)

CREATE TABLE IF NOT EXISTS polybot.aware_position_pnl (
    -- Position identification
    proxy_address String,
    username LowCardinality(String),
    condition_id String,
    market_slug LowCardinality(String),
    outcome LowCardinality(String),         -- Which outcome they traded

    -- Position details
    net_shares Float64,                     -- BUY - SELL shares
    net_cost Float64,                       -- Total cost basis
    avg_entry_price Float64,                -- Weighted average entry

    -- Resolution
    settlement_price Float64,               -- 1.0 or 0.0
    realized_pnl Float64,                   -- (settlement_price * net_shares) - net_cost

    -- Trade counts
    buy_count UInt32,
    sell_count UInt32,
    total_trades UInt32,

    -- Timing
    first_trade_at DateTime64(3),
    last_trade_at DateTime64(3),
    resolved_at DateTime64(3),

    -- Metadata
    calculated_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(calculated_at)
ORDER BY (proxy_address, condition_id, outcome);

-- ============================================================================
-- HELPER VIEWS
-- ============================================================================

-- View of resolved markets only
CREATE OR REPLACE VIEW polybot.aware_resolved_markets AS
SELECT *
FROM polybot.aware_market_resolutions FINAL
WHERE is_resolved = 1;

-- Leaderboard with accurate P&L
CREATE OR REPLACE VIEW polybot.aware_leaderboard_with_pnl AS
SELECT
    s.rank,
    s.username,
    s.proxy_address,
    s.total_score AS smart_money_score,
    s.tier,
    -- Use calculated P&L from pnl table, fallback to profile
    if(pnl.proxy_address != '', pnl.total_realized_pnl, p.realized_pnl) AS realized_pnl,
    if(pnl.proxy_address != '', pnl.win_rate, 0.0) AS win_rate,
    if(pnl.proxy_address != '', pnl.total_positions_closed, 0) AS positions_closed,
    p.total_volume_usd AS total_volume,
    s.strategy_type,
    s.calculated_at
FROM (SELECT * FROM polybot.aware_smart_money_scores FINAL) AS s
LEFT JOIN (SELECT * FROM polybot.aware_trader_profiles FINAL) AS p
    ON s.proxy_address = p.proxy_address
LEFT JOIN (SELECT * FROM polybot.aware_trader_pnl FINAL) AS pnl
    ON s.proxy_address = pnl.proxy_address
ORDER BY s.rank ASC;
