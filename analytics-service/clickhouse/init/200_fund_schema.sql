-- AWARE Fund Schema
-- Tables for tracking fund positions, NAV, and trade history

-- =============================================================================
-- PSI Index Storage (written by Python psi_index.py)
-- =============================================================================

CREATE TABLE IF NOT EXISTS polybot.aware_psi_index
(
    index_type       String,           -- 'PSI-10', 'PSI-25', 'PSI-CRYPTO', etc.
    username         String,           -- Trader username
    proxy_address    String,           -- Trader's proxy wallet address
    weight           Float64,          -- Portfolio weight (0.0 to 1.0)
    total_score      Float64,          -- Smart Money Score at inclusion
    sharpe_ratio     Float64,          -- Sharpe at inclusion
    strategy_type    String,           -- 'ARBITRAGEUR', 'DIRECTIONAL', etc.
    created_at       DateTime64(3),    -- When index was created
    rebalanced_at    DateTime64(3),    -- When last rebalanced
    _version         UInt64 DEFAULT toUnixTimestamp64Milli(now64(3))
)
ENGINE = ReplacingMergeTree(_version)
ORDER BY (index_type, proxy_address)
SETTINGS index_granularity = 8192;

-- =============================================================================
-- Fund Positions
-- =============================================================================

CREATE TABLE IF NOT EXISTS polybot.aware_fund_positions
(
    fund_id          String,           -- Fund identifier (e.g., 'psi-10-main')
    token_id         String,           -- Polymarket token ID
    market_slug      String,           -- Market slug
    outcome          String,           -- 'Yes' or 'No'
    shares           Decimal(18, 6),   -- Current position size
    avg_entry_price  Decimal(10, 6),   -- VWAP entry price
    current_price    Decimal(10, 6),   -- Latest market price
    unrealized_pnl   Decimal(18, 6),   -- Paper P&L
    opened_at        DateTime64(3),    -- When position was first opened
    updated_at       DateTime64(3),    -- Last update time
    _version         UInt64 DEFAULT toUnixTimestamp64Milli(now64(3))
)
ENGINE = ReplacingMergeTree(_version)
ORDER BY (fund_id, token_id)
SETTINGS index_granularity = 8192;

-- =============================================================================
-- Fund NAV History
-- =============================================================================

CREATE TABLE IF NOT EXISTS polybot.aware_fund_nav_history
(
    fund_id          String,           -- Fund identifier
    ts               DateTime64(3),    -- Timestamp
    nav              Decimal(18, 6),   -- Net Asset Value
    capital          Decimal(18, 6),   -- Initial capital
    position_value   Decimal(18, 6),   -- Value of open positions
    unrealized_pnl   Decimal(18, 6),   -- Unrealized P&L
    realized_pnl     Decimal(18, 6),   -- Realized P&L
    daily_return     Float64,          -- Daily return percentage
    total_return     Float64,          -- Total return since inception
    max_drawdown     Float64,          -- Max drawdown percentage
    open_positions   UInt32,           -- Number of open positions
    num_traders      UInt32            -- Number of traders being mirrored
)
ENGINE = MergeTree()
ORDER BY (fund_id, ts)
PARTITION BY toYYYYMM(ts)
SETTINGS index_granularity = 8192;

-- =============================================================================
-- Fund Executions (written by Java FundPositionMirror)
-- =============================================================================

CREATE TABLE IF NOT EXISTS polybot.aware_fund_executions
(
    signal_id        String,           -- Signal ID that triggered this execution
    fund_id          String,           -- Fund identifier (e.g., 'PSI-10')
    trader_username  String,           -- Trader whose signal we mirrored
    market_slug      String,           -- Market slug
    token_id         String,           -- Polymarket token ID
    outcome          String,           -- 'Yes' or 'No'
    signal_type      String,           -- 'BUY', 'SELL', or 'CLOSE'
    trader_shares    Decimal(18, 6),   -- Trader's original trade size
    fund_shares      Decimal(18, 6),   -- Fund's scaled trade size
    execution_price  Decimal(10, 6),   -- Fund's execution price
    order_id         String,           -- Polymarket order ID
    detected_at      DateTime64(3),    -- When signal was detected
    executed_at      DateTime64(3)     -- When fund executed
)
ENGINE = MergeTree()
ORDER BY (fund_id, executed_at)
PARTITION BY toYYYYMM(executed_at)
SETTINGS index_granularity = 8192;

-- =============================================================================
-- Fund Trades (mirrors of trader trades)
-- =============================================================================

CREATE TABLE IF NOT EXISTS polybot.aware_fund_trades
(
    fund_id          String,           -- Fund identifier
    ts               DateTime64(3),    -- Execution timestamp
    signal_id        String,           -- Signal that triggered this trade
    source_trader    String,           -- Trader we mirrored
    source_weight    Float64,          -- Trader's weight at time of trade
    market_slug      String,           -- Market
    token_id         String,           -- Token
    outcome          String,           -- 'Yes' or 'No'
    side             String,           -- 'BUY' or 'SELL'
    shares           Decimal(18, 6),   -- Fund trade size
    price            Decimal(10, 6),   -- Execution price
    notional_usd     Decimal(18, 6),   -- Trade value in USD
    slippage         Float64,          -- Slippage from trader's price
    order_id         String,           -- Polymarket order ID
    status           String            -- 'FILLED', 'PARTIAL', 'FAILED'
)
ENGINE = MergeTree()
ORDER BY (fund_id, ts)
PARTITION BY toYYYYMM(ts)
SETTINGS index_granularity = 8192;

-- =============================================================================
-- Fund Performance Summary (materialized for quick dashboard access)
-- =============================================================================

CREATE TABLE IF NOT EXISTS polybot.aware_fund_performance
(
    fund_id           String,
    period            String,          -- 'daily', 'weekly', 'monthly', 'all_time'
    period_start      Date,
    period_end        Date,
    start_nav         Decimal(18, 6),
    end_nav           Decimal(18, 6),
    return_pct        Float64,
    trades_count      UInt32,
    volume_traded     Decimal(18, 6),
    win_rate          Float64,
    sharpe_ratio      Float64,
    max_drawdown      Float64,
    calculated_at     DateTime64(3),
    _version          UInt64 DEFAULT toUnixTimestamp64Milli(now64(3))
)
ENGINE = ReplacingMergeTree(_version)
ORDER BY (fund_id, period, period_start)
SETTINGS index_granularity = 8192;

-- =============================================================================
-- Trader contributions to fund performance
-- =============================================================================

CREATE TABLE IF NOT EXISTS polybot.aware_fund_trader_contributions
(
    fund_id           String,
    period_start      Date,
    period_end        Date,
    username          String,          -- Trader username
    weight            Float64,         -- Weight during period
    trades_mirrored   UInt32,          -- Number of trades we mirrored
    pnl_contribution  Decimal(18, 6),  -- P&L attributed to this trader
    return_pct        Float64,         -- Return from this trader's signals
    calculated_at     DateTime64(3),
    _version          UInt64 DEFAULT toUnixTimestamp64Milli(now64(3))
)
ENGINE = ReplacingMergeTree(_version)
ORDER BY (fund_id, period_start, username)
SETTINGS index_granularity = 8192;

-- =============================================================================
-- Views
-- =============================================================================

-- Current index constituents (latest snapshot)
CREATE VIEW IF NOT EXISTS polybot.v_psi_index_current AS
SELECT
    index_type,
    username,
    proxy_address,
    weight,
    total_score,
    sharpe_ratio,
    strategy_type,
    rebalanced_at
FROM polybot.aware_psi_index FINAL
ORDER BY index_type, weight DESC;

-- Latest NAV per fund
-- NOTE: v_fund_nav_latest moved to 300_user_investments.sql (depends on aware_fund_nav table there)

-- Fund positions with market values
-- Note: toFloat64 casts required to avoid ClickHouse Decimal scale mismatch errors
CREATE VIEW IF NOT EXISTS polybot.v_fund_positions_valued AS
SELECT
    fund_id,
    token_id,
    market_slug,
    outcome,
    shares,
    avg_entry_price,
    current_price,
    toFloat64(shares) * toFloat64(current_price) as current_value,
    unrealized_pnl,
    (toFloat64(unrealized_pnl) / (toFloat64(shares) * toFloat64(avg_entry_price))) * 100 as unrealized_pnl_pct,
    updated_at
FROM polybot.aware_fund_positions FINAL
WHERE shares > 0;
