-- ============================================================================
-- AWARE PSI Index Views
-- ============================================================================
-- Provides denormalized views for PSI index construction.
-- These views join scores with profiles and P&L for index eligibility queries.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- PSI ELIGIBLE TRADERS VIEW
-- ----------------------------------------------------------------------------
-- Joins smart_money_scores with trader_profiles, trader_pnl, and ml_scores
-- to provide all columns needed by psi_index.py for index construction.
--
-- Usage:
--   SELECT username, total_score, sharpe_ratio, strategy_type, ...
--   FROM polybot.aware_psi_eligible_traders
--   WHERE total_score >= 70 AND total_trades >= 100
-- ----------------------------------------------------------------------------

CREATE OR REPLACE VIEW polybot.aware_psi_eligible_traders AS
SELECT
    -- Identity
    s.proxy_address AS proxy_address,
    s.username AS username,

    -- Score data (from smart_money_scores)
    s.total_score AS total_score,
    s.tier AS tier,
    s.profitability_score AS profitability_score,
    s.risk_adjusted_score AS risk_adjusted_score,
    s.consistency_score AS consistency_score,
    s.track_record_score AS track_record_score,
    s.strategy_type AS strategy_type,
    s.strategy_confidence AS strategy_confidence,
    s.rank AS rank,
    s.rank_change AS rank_change,
    s.calculated_at AS calculated_at,
    s.model_version AS model_version,

    -- Profile metrics (from trader_profiles)
    coalesce(p.total_trades, 0) AS total_trades,
    coalesce(p.total_volume_usd, 0.0) AS total_volume_usd,
    coalesce(p.days_active, 0) AS days_active,
    coalesce(p.unique_markets, 0) AS unique_markets,
    p.first_trade_at,
    p.last_trade_at,
    coalesce(p.avg_trade_size, 0.0) AS avg_trade_size,

    -- P&L data (prefer trader_pnl, fallback to profiles)
    if(pnl.proxy_address != '', pnl.total_realized_pnl, coalesce(p.total_pnl, 0.0)) AS total_pnl,
    if(pnl.proxy_address != '', pnl.win_rate, 0.0) AS win_rate,
    if(pnl.proxy_address != '', pnl.total_positions_closed, 0) AS positions_closed,
    if(pnl.proxy_address != '', pnl.winning_positions, 0) AS winning_positions,
    if(pnl.proxy_address != '', pnl.losing_positions, 0) AS losing_positions,

    -- Risk metrics (from ML scores if available, else 0)
    -- TODO: Calculate Sharpe from P&L variance in Phase 2
    if(ml.proxy_address != '', ml.sharpe_ratio, 0.0) AS sharpe_ratio,
    if(ml.proxy_address != '', ml.max_drawdown, 0.0) AS max_drawdown,
    if(ml.proxy_address != '', ml.maker_ratio, 0.0) AS maker_ratio

FROM (SELECT * FROM polybot.aware_smart_money_scores FINAL) AS s
LEFT JOIN (SELECT * FROM polybot.aware_trader_profiles FINAL) AS p
    ON s.proxy_address = p.proxy_address
LEFT JOIN (SELECT * FROM polybot.aware_trader_pnl FINAL) AS pnl
    ON s.proxy_address = pnl.proxy_address
LEFT JOIN (SELECT * FROM polybot.aware_ml_scores FINAL) AS ml
    ON s.proxy_address = ml.proxy_address;

-- ----------------------------------------------------------------------------
-- AWARE LEADERBOARD VIEW (with ML scores)
-- ----------------------------------------------------------------------------
-- Combined leaderboard view with both rule-based and ML scores.
-- Note: ClickHouse LEFT JOIN returns 0/empty string for non-matches, not NULL
-- So we use if(ml.proxy_address = '', ...) instead of coalesce()
-- Joins aware_trader_pnl to get actual win_rate from P&L calculations.
-- ----------------------------------------------------------------------------

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
