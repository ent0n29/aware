-- ============================================================================
-- AWARE Fund - User Investment Schema (Custodial MVP)
-- ============================================================================
-- Tracks user deposits, withdrawals, and share ownership across all funds.
-- This is a custodial model where AWARE holds funds and tracks ownership in DB.
--
-- Migration path: This schema will be replaced by smart contracts for V1.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- User Accounts
-- ----------------------------------------------------------------------------
-- Stores basic user information. In MVP, users are identified by wallet address.
-- Future: Add KYC fields, verification status, etc.

CREATE TABLE IF NOT EXISTS polybot.aware_users
(
    user_id          UUID DEFAULT generateUUIDv4(),
    wallet_address   String,                          -- Primary identifier (Ethereum address)
    email            Nullable(String),                -- Optional email for notifications
    username         Nullable(String),                -- Display name
    created_at       DateTime64(3) DEFAULT now64(3),
    updated_at       DateTime64(3) DEFAULT now64(3),
    status           String DEFAULT 'active',         -- active, suspended, closed
    kyc_verified     Bool DEFAULT false,
    referral_code    Nullable(String),
    referred_by      Nullable(UUID)
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (wallet_address)
SETTINGS index_granularity = 8192;

-- Index for user lookups
CREATE INDEX IF NOT EXISTS idx_users_email ON polybot.aware_users(email) TYPE bloom_filter GRANULARITY 4;


-- ----------------------------------------------------------------------------
-- User Transactions (Deposits & Withdrawals)
-- ----------------------------------------------------------------------------
-- Immutable log of all deposit/withdrawal transactions.
-- Each transaction mints or burns shares based on current NAV.

CREATE TABLE IF NOT EXISTS polybot.aware_user_transactions
(
    tx_id            UUID DEFAULT generateUUIDv4(),
    user_id          UUID,
    wallet_address   String,
    fund_type        String,                          -- PSI-10, ALPHA-INSIDER, etc.
    tx_type          String,                          -- DEPOSIT, WITHDRAW, FEE

    -- Amounts
    usdc_amount      Decimal(18, 6),                  -- USDC amount (6 decimals)
    shares_amount    Decimal(18, 8),                  -- Shares minted/burned
    nav_per_share    Decimal(18, 8),                  -- NAV at time of transaction

    -- Fees
    fee_amount       Decimal(18, 6) DEFAULT 0,        -- Any fees charged
    fee_type         Nullable(String),                -- MANAGEMENT, PERFORMANCE, WITHDRAWAL

    -- Status
    status           String DEFAULT 'pending',        -- pending, confirmed, failed, cancelled
    tx_hash          Nullable(String),                -- On-chain tx hash (for USDC transfer)

    -- Timestamps
    created_at       DateTime64(3) DEFAULT now64(3),
    confirmed_at     Nullable(DateTime64(3)),

    -- Metadata
    notes            Nullable(String)
)
ENGINE = MergeTree()
ORDER BY (fund_type, user_id, created_at)
PARTITION BY toYYYYMM(created_at)
SETTINGS index_granularity = 8192;


-- ----------------------------------------------------------------------------
-- User Share Holdings (Current State)
-- ----------------------------------------------------------------------------
-- Tracks current share balance per user per fund.
-- Updated on each deposit/withdrawal via materialized view or application logic.

CREATE TABLE IF NOT EXISTS polybot.aware_user_shares
(
    user_id          UUID,
    wallet_address   String,
    fund_type        String,                          -- PSI-10, ALPHA-INSIDER, etc.

    -- Current holdings
    shares_balance   Decimal(18, 8),                  -- Current share balance
    cost_basis_usdc  Decimal(18, 6),                  -- Total USDC deposited (for P&L calc)

    -- Timestamps
    first_deposit_at DateTime64(3),
    last_activity_at DateTime64(3),
    updated_at       DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (fund_type, user_id)
SETTINGS index_granularity = 8192;


-- ----------------------------------------------------------------------------
-- Fund NAV History
-- ----------------------------------------------------------------------------
-- Tracks Net Asset Value per share for each fund over time.
-- NAV = (Total Fund Value) / (Total Shares Outstanding)

CREATE TABLE IF NOT EXISTS polybot.aware_fund_nav
(
    fund_type            String,                      -- PSI-10, ALPHA-INSIDER, etc.
    calculated_at        DateTime64(3) DEFAULT now64(3),

    -- NAV Components
    total_usdc_balance   Decimal(18, 6),              -- Cash in fund
    total_position_value Decimal(18, 6),              -- Value of open positions
    total_fund_value     Decimal(18, 6),              -- total_usdc + total_position_value

    -- Shares
    total_shares         Decimal(18, 8),              -- Total shares outstanding
    nav_per_share        Decimal(18, 8),              -- total_fund_value / total_shares

    -- Performance (cumulative)
    total_pnl            Decimal(18, 6),              -- Realized + unrealized P&L
    total_fees_collected Decimal(18, 6),              -- Fees taken

    -- Daily metrics
    daily_return_pct     Decimal(10, 4),              -- % change from previous day

    -- Metadata
    num_depositors       UInt32,                      -- Number of unique depositors
    num_positions        UInt32                       -- Number of open positions
)
ENGINE = MergeTree()
ORDER BY (fund_type, calculated_at)
PARTITION BY toYYYYMM(calculated_at)
SETTINGS index_granularity = 8192;


-- ----------------------------------------------------------------------------
-- Fund Summary (Current State)
-- ----------------------------------------------------------------------------
-- Quick lookup for current fund status. Updated frequently.

CREATE TABLE IF NOT EXISTS polybot.aware_fund_summary
(
    fund_type            String,
    updated_at           DateTime64(3) DEFAULT now64(3),

    -- Current State
    status               String DEFAULT 'active',     -- active, paused, closed
    total_aum            Decimal(18, 6),              -- Assets Under Management
    total_shares         Decimal(18, 8),
    nav_per_share        Decimal(18, 8),
    num_depositors       UInt32,

    -- Performance
    return_24h_pct       Decimal(10, 4),
    return_7d_pct        Decimal(10, 4),
    return_30d_pct       Decimal(10, 4),
    return_inception_pct Decimal(10, 4),
    sharpe_ratio         Decimal(10, 4),
    max_drawdown_pct     Decimal(10, 4),

    -- Fees
    management_fee_pct   Decimal(6, 4) DEFAULT 0.005, -- 0.5% annually
    performance_fee_pct  Decimal(6, 4) DEFAULT 0.10,  -- 10% of profits

    -- Limits
    min_deposit_usdc     Decimal(18, 6) DEFAULT 10,
    max_deposit_usdc     Decimal(18, 6) DEFAULT 100000,

    -- Metadata
    description          String,
    inception_date       Date
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (fund_type)
SETTINGS index_granularity = 8192;


-- ----------------------------------------------------------------------------
-- Withdrawal Requests Queue
-- ----------------------------------------------------------------------------
-- For processing withdrawals (may have delay for liquidity management)

CREATE TABLE IF NOT EXISTS polybot.aware_withdrawal_requests
(
    request_id       UUID DEFAULT generateUUIDv4(),
    user_id          UUID,
    wallet_address   String,
    fund_type        String,

    -- Request details
    shares_amount    Decimal(18, 8),                  -- Shares to redeem
    estimated_usdc   Decimal(18, 6),                  -- Estimated USDC at request time
    nav_at_request   Decimal(18, 8),

    -- Status
    status           String DEFAULT 'pending',        -- pending, processing, completed, cancelled

    -- Timestamps
    requested_at     DateTime64(3) DEFAULT now64(3),
    process_after    DateTime64(3),                   -- Earliest processing time (for delays)
    processed_at     Nullable(DateTime64(3)),

    -- Result
    actual_usdc      Nullable(Decimal(18, 6)),        -- Actual USDC sent
    nav_at_process   Nullable(Decimal(18, 8)),
    tx_hash          Nullable(String)
)
ENGINE = MergeTree()
ORDER BY (status, requested_at)
SETTINGS index_granularity = 8192;


-- ============================================================================
-- SEED DATA: Initialize fund summaries
-- ============================================================================

-- Passive Index Funds: PSI-10, PSI-SPORTS, PSI-CRYPTO, PSI-POLITICS
-- Alpha Funds: ALPHA-INSIDER, ALPHA-EDGE, ALPHA-ARB
INSERT INTO polybot.aware_fund_summary
(fund_type, status, total_aum, total_shares, nav_per_share, num_depositors,
 return_24h_pct, return_7d_pct, return_30d_pct, return_inception_pct,
 management_fee_pct, performance_fee_pct, min_deposit_usdc, description, inception_date)
VALUES
('PSI-10', 'active', 0, 0, 1.0, 0, 0, 0, 0, 0, 0.005, 0.10, 10,
 'Top 10 Smart Money traders by score. Mirrors their positions proportionally.', today()),
('PSI-25', 'active', 0, 0, 1.0, 0, 0, 0, 0, 0, 0.005, 0.10, 10,
 'Top 25 Smart Money traders by score. Broader diversification than PSI-10.', today()),
('PSI-SPORTS', 'active', 0, 0, 1.0, 0, 0, 0, 0, 0, 0.005, 0.10, 10,
 'Top sports betting specialists. Focus on NFL, NBA, Soccer markets.', today()),
('PSI-CRYPTO', 'active', 0, 0, 1.0, 0, 0, 0, 0, 0, 0.005, 0.10, 10,
 'Top cryptocurrency traders. Bitcoin, Ethereum, and altcoin markets.', today()),
('PSI-POLITICS', 'active', 0, 0, 1.0, 0, 0, 0, 0, 0, 0.005, 0.10, 10,
 'Top political forecasters. Elections, policy, and geopolitical events.', today()),
('ALPHA-INSIDER', 'active', 0, 0, 1.0, 0, 0, 0, 0, 0, 0.01, 0.15, 100,
 'Follows detected insider activity signals. Higher risk, higher reward.', today()),
('ALPHA-EDGE', 'active', 0, 0, 1.0, 0, 0, 0, 0, 0, 0.01, 0.15, 100,
 'ML-powered trading based on edge scores and trader patterns.', today()),
('ALPHA-ARB', 'active', 0, 0, 1.0, 0, 0, 0, 0, 0, 0.005, 0.05, 50,
 'Complete-set arbitrage. Lower risk, consistent small returns.', today());


-- ============================================================================
-- VIEWS (depend on tables above)
-- ============================================================================

-- Latest NAV per fund
CREATE VIEW IF NOT EXISTS polybot.v_fund_nav_latest AS
SELECT
    fund_type,
    nav_per_share,
    total_usdc_balance as capital,
    total_position_value as position_value,
    total_fund_value,
    total_pnl,
    daily_return_pct,
    num_depositors,
    num_positions,
    calculated_at as last_updated
FROM polybot.aware_fund_nav
WHERE (fund_type, calculated_at) IN (
    SELECT fund_type, max(calculated_at)
    FROM polybot.aware_fund_nav
    GROUP BY fund_type
);
