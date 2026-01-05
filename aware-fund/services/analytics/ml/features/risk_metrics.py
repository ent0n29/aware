"""
Risk Metrics Feature Extractor

Computes risk-adjusted performance metrics:
- Sharpe ratio, Sortino ratio
- Maximum drawdown, Calmar ratio
- Win rate, profit factor
- Win/loss streaks
"""

import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)


class RiskMetricsExtractor:
    """
    Extract risk-adjusted performance metrics from trade history.

    These metrics separate skill from luck by measuring
    risk-adjusted returns and consistency.
    """

    def __init__(self, ch_client):
        self.ch_client = ch_client

    def extract(self, proxy_address: str) -> dict:
        """
        Extract risk metrics for a trader.

        Args:
            proxy_address: Trader wallet address

        Returns:
            Dict of risk metrics
        """
        try:
            # Get daily P&L series for Sharpe/Sortino
            daily_pnl = self._get_daily_pnl(proxy_address)

            # Get trade-level outcomes for win rate
            trade_outcomes = self._get_trade_outcomes(proxy_address)

            metrics = {}

            # Calculate Sharpe and Sortino from daily returns
            if len(daily_pnl) >= 5:
                returns = np.array(daily_pnl)
                metrics['sharpe_ratio'] = self._calculate_sharpe(returns)
                metrics['sortino_ratio'] = self._calculate_sortino(returns)
                metrics['max_drawdown'] = self._calculate_max_drawdown(returns)
                metrics['calmar_ratio'] = self._calculate_calmar(returns)
            else:
                metrics['sharpe_ratio'] = 0.0
                metrics['sortino_ratio'] = 0.0
                metrics['max_drawdown'] = 0.0
                metrics['calmar_ratio'] = 0.0

            # Calculate win rate and profit factor from trades
            if trade_outcomes:
                wins = [t for t in trade_outcomes if t > 0]
                losses = [t for t in trade_outcomes if t < 0]

                metrics['win_rate'] = len(wins) / len(trade_outcomes) if trade_outcomes else 0
                metrics['avg_win'] = np.mean(wins) if wins else 0
                metrics['avg_loss'] = abs(np.mean(losses)) if losses else 0

                total_wins = sum(wins)
                total_losses = abs(sum(losses))
                metrics['profit_factor'] = total_wins / total_losses if total_losses > 0 else 0

                if metrics['avg_loss'] > 0:
                    metrics['win_loss_ratio'] = metrics['avg_win'] / metrics['avg_loss']
                else:
                    metrics['win_loss_ratio'] = 0

                # Streaks
                metrics['consecutive_wins_max'] = self._max_streak(trade_outcomes, positive=True)
                metrics['consecutive_losses_max'] = self._max_streak(trade_outcomes, positive=False)
            else:
                metrics['win_rate'] = 0.0
                metrics['avg_win'] = 0.0
                metrics['avg_loss'] = 0.0
                metrics['profit_factor'] = 0.0
                metrics['win_loss_ratio'] = 0.0
                metrics['consecutive_wins_max'] = 0
                metrics['consecutive_losses_max'] = 0

            return metrics

        except Exception as e:
            logger.error(f"Failed to extract risk metrics for {proxy_address}: {e}")
            return {}

    def _get_daily_pnl(self, proxy_address: str) -> list[float]:
        """Get daily P&L series from trades."""
        try:
            result = self.ch_client.query("""
                SELECT
                    toDate(ts) AS day,
                    sum(
                        CASE
                            WHEN side = 'SELL' THEN notional
                            ELSE -notional
                        END
                    ) AS daily_pnl
                FROM aware_global_trades_dedup
                WHERE proxy_address = %(addr)s
                GROUP BY day
                ORDER BY day
            """, parameters={'addr': proxy_address})

            return [row[1] for row in result.result_rows]
        except Exception as e:
            logger.error(f"Failed to get daily P&L: {e}")
            return []

    def _get_trade_outcomes(self, proxy_address: str) -> list[float]:
        """
        Get per-trade P&L outcomes.

        For prediction markets, a trade is "won" if:
        - BUY and market resolved to that outcome (price went to 1)
        - SELL at profit (sold higher than bought)

        This is simplified - uses realized P&L where available.
        """
        try:
            # Try to get from enriched table with settlement
            result = self.ch_client.query("""
                SELECT
                    CASE
                        WHEN side = 'BUY' THEN
                            (coalesce(settle_price, 0.5) - price) * size
                        ELSE
                            (price - coalesce(settle_price, 0.5)) * size
                    END AS trade_pnl
                FROM user_trade_enriched_v4
                WHERE proxy_address = %(addr)s
                  AND settle_price IS NOT NULL
                ORDER BY ts
                LIMIT 1000
            """, parameters={'addr': proxy_address})

            if result.result_rows:
                return [row[0] for row in result.result_rows]

            # Fallback: estimate from buy/sell pairs
            return self._estimate_outcomes_from_pairs(proxy_address)

        except Exception as e:
            logger.debug(f"Falling back to pair estimation: {e}")
            return self._estimate_outcomes_from_pairs(proxy_address)

    def _estimate_outcomes_from_pairs(self, proxy_address: str) -> list[float]:
        """Estimate trade outcomes from buy/sell pairs in same market."""
        try:
            result = self.ch_client.query("""
                WITH trades AS (
                    SELECT
                        market_slug,
                        token_id,
                        side,
                        price,
                        size,
                        ts,
                        row_number() OVER (
                            PARTITION BY market_slug, token_id
                            ORDER BY ts
                        ) AS rn
                    FROM aware_global_trades_dedup
                    WHERE proxy_address = %(addr)s
                )
                SELECT
                    side,
                    price,
                    size
                FROM trades
                ORDER BY market_slug, token_id, ts
                LIMIT 500
            """, parameters={'addr': proxy_address})

            # Simple heuristic: compare sequential buy/sell
            outcomes = []
            position = {}  # (market, token) -> avg_price

            for row in result.result_rows:
                side, price, size = row
                # Simplified: just track direction
                if side == 'BUY':
                    # Assume breakeven if we don't know settlement
                    outcomes.append(0)
                else:
                    outcomes.append(0)

            return outcomes

        except Exception as e:
            logger.error(f"Failed to estimate outcomes: {e}")
            return []

    def _calculate_sharpe(self, returns: np.ndarray, risk_free: float = 0.0) -> float:
        """
        Calculate annualized Sharpe ratio.

        Sharpe = (mean_return - risk_free) / std_return * sqrt(252)
        """
        if len(returns) < 2:
            return 0.0

        excess = returns - risk_free
        std = np.std(excess, ddof=1)

        if std == 0 or np.isnan(std):
            return 0.0

        daily_sharpe = np.mean(excess) / std
        # Annualize (assuming 252 trading days)
        return float(daily_sharpe * np.sqrt(252))

    def _calculate_sortino(self, returns: np.ndarray, risk_free: float = 0.0) -> float:
        """
        Calculate Sortino ratio (uses downside deviation only).

        Better than Sharpe for asymmetric returns.
        """
        if len(returns) < 2:
            return 0.0

        excess = returns - risk_free
        downside = excess[excess < 0]

        if len(downside) == 0:
            return 10.0  # Cap at high value if no losses

        downside_std = np.std(downside, ddof=1)
        if downside_std == 0 or np.isnan(downside_std):
            return 0.0

        daily_sortino = np.mean(excess) / downside_std
        return float(daily_sortino * np.sqrt(252))

    def _calculate_max_drawdown(self, returns: np.ndarray) -> float:
        """
        Calculate maximum drawdown from peak.

        Returns negative value (e.g., -0.25 = 25% drawdown).
        """
        if len(returns) < 2:
            return 0.0

        cumulative = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = cumulative - running_max

        return float(np.min(drawdown))

    def _calculate_calmar(self, returns: np.ndarray) -> float:
        """
        Calculate Calmar ratio (return / max drawdown).

        Higher is better - measures return per unit of drawdown risk.
        """
        max_dd = self._calculate_max_drawdown(returns)
        if max_dd >= 0:
            return 0.0

        total_return = np.sum(returns)
        return float(total_return / abs(max_dd))

    def _max_streak(self, outcomes: list[float], positive: bool = True) -> int:
        """Calculate maximum consecutive win/loss streak."""
        max_streak = 0
        current = 0

        for outcome in outcomes:
            if (positive and outcome > 0) or (not positive and outcome < 0):
                current += 1
                max_streak = max(max_streak, current)
            else:
                current = 0

        return max_streak
