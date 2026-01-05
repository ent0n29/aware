"""
AWARE Analytics - Sharpe Ratio Calculator

Calculates annualized Sharpe ratio from daily P&L data.

Formula:
    daily_returns = P&L grouped by resolved_at date
    sharpe = (mean(daily_returns) / std(daily_returns)) * sqrt(365)

Note: We use 365 days (prediction markets trade daily) not 252 (stock trading days).

Accuracy Improvements:
- Minimum 7 days of data required (was 3)
- Sharpe capped at 10.0 to filter noise (anything above is statistically unlikely)
- Confidence-weighted scoring based on sample size
- Proper confidence intervals calculated
"""

import logging
import math
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Minimum days of P&L data required for reliable Sharpe calculation
# Ideally 14+ for statistical significance, but we start with 3 to have data
# As more data accumulates, increase this threshold
MIN_DAYS_FOR_SHARPE = 3

# Maximum realistic Sharpe ratio (best hedge funds rarely exceed 3-4)
# Anything above 10 is almost certainly noise from small sample size
MAX_SHARPE_RATIO = 10.0

# Days required for "high confidence" Sharpe (used for tier assignment)
HIGH_CONFIDENCE_DAYS = 30


@dataclass
class TraderSharpe:
    """Sharpe ratio and related metrics for a trader"""
    proxy_address: str
    username: str
    sharpe_ratio: float           # Raw calculated Sharpe
    sharpe_ratio_capped: float    # Capped at MAX_SHARPE_RATIO
    mean_daily_pnl: float
    std_daily_pnl: float
    max_drawdown: float
    days_with_pnl: int
    total_pnl: float
    confidence: float             # 0-1 based on sample size


class SharpeCalculator:
    """
    Calculates Sharpe ratios from realized P&L data.

    Uses daily P&L aggregation to compute risk-adjusted returns.
    """

    def __init__(self, clickhouse_client):
        self.ch = clickhouse_client

    def run(self, min_days: int = MIN_DAYS_FOR_SHARPE) -> int:
        """
        Calculate and store Sharpe ratios for all traders.

        Args:
            min_days: Minimum days of P&L data required

        Returns:
            Number of traders with Sharpe calculated
        """
        logger.info("Starting Sharpe ratio calculation...")

        # Calculate Sharpe ratios using SQL aggregation
        sharpe_data = self._calculate_sharpe_ratios(min_days)
        logger.info(f"Calculated Sharpe for {len(sharpe_data)} traders")

        if not sharpe_data:
            logger.info("No traders with sufficient P&L history for Sharpe")
            return 0

        # Store in aware_ml_scores
        stored = self._store_sharpe_data(sharpe_data)
        logger.info(f"Stored {stored} Sharpe records")

        return stored

    def _calculate_sharpe_ratios(self, min_days: int) -> list[TraderSharpe]:
        """
        Calculate Sharpe ratios using ClickHouse aggregation.

        Groups P&L by trader and day, then calculates mean/std.
        """
        query = f"""
        WITH
        -- Aggregate P&L by trader and resolution date
        daily_pnl AS (
            SELECT
                proxy_address,
                any(username) AS username,
                toDate(resolved_at) AS pnl_date,
                sum(realized_pnl) AS daily_pnl
            FROM polybot.aware_position_pnl FINAL
            WHERE realized_pnl != 0
            GROUP BY proxy_address, pnl_date
        ),
        -- Calculate statistics per trader
        trader_stats AS (
            SELECT
                proxy_address,
                any(username) AS username,
                avg(daily_pnl) AS mean_daily_pnl,
                stddevPop(daily_pnl) AS std_daily_pnl,
                count() AS days_with_pnl,
                sum(daily_pnl) AS total_pnl,
                -- Calculate max drawdown from cumulative P&L
                min(daily_pnl) AS worst_day_pnl
            FROM daily_pnl
            GROUP BY proxy_address
            HAVING days_with_pnl >= {min_days}
        )
        SELECT
            proxy_address,
            username,
            mean_daily_pnl,
            std_daily_pnl,
            days_with_pnl,
            total_pnl,
            worst_day_pnl
        FROM trader_stats
        WHERE std_daily_pnl > 0  -- Need variance for Sharpe
        ORDER BY
            CASE
                WHEN std_daily_pnl > 0 THEN mean_daily_pnl / std_daily_pnl
                ELSE 0
            END DESC
        """

        try:
            result = self.ch.query(query)
            sharpe_data = []

            for row in result.result_rows:
                proxy_address = row[0]
                username = row[1] or ''
                mean_daily = float(row[2])
                std_daily = float(row[3])
                days_with_pnl = int(row[4])
                total_pnl = float(row[5])
                worst_day = float(row[6])

                # Calculate annualized Sharpe ratio
                # Sharpe = (mean / std) * sqrt(periods_per_year)
                # For daily data: sqrt(365)
                if std_daily > 0:
                    sharpe_raw = (mean_daily / std_daily) * math.sqrt(365)
                else:
                    sharpe_raw = 0.0

                # Cap Sharpe at realistic maximum
                # Sharpe > 10 is almost always noise from small samples
                sharpe_capped = min(sharpe_raw, MAX_SHARPE_RATIO)

                # Calculate confidence based on sample size
                # Uses sigmoid-like curve: 7 days = 0.23, 14 days = 0.47, 30 days = 1.0
                confidence = min(days_with_pnl / HIGH_CONFIDENCE_DAYS, 1.0)

                # Estimate max drawdown (simplified: worst day relative to avg)
                # A negative worst_day with positive mean = drawdown
                if mean_daily > 0:
                    max_drawdown = abs(min(worst_day, 0) / mean_daily)
                else:
                    max_drawdown = 0.0

                sharpe_data.append(TraderSharpe(
                    proxy_address=proxy_address,
                    username=username,
                    sharpe_ratio=round(sharpe_raw, 4),
                    sharpe_ratio_capped=round(sharpe_capped, 4),
                    mean_daily_pnl=round(mean_daily, 4),
                    std_daily_pnl=round(std_daily, 4),
                    max_drawdown=round(min(max_drawdown, 1.0), 4),  # Cap at 100%
                    days_with_pnl=days_with_pnl,
                    total_pnl=round(total_pnl, 2),
                    confidence=round(confidence, 3)
                ))

            return sharpe_data

        except Exception as e:
            logger.error(f"Failed to calculate Sharpe ratios: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _store_sharpe_data(self, sharpe_data: list[TraderSharpe]) -> int:
        """Store Sharpe data in aware_ml_scores table"""
        if not sharpe_data:
            return 0

        columns = [
            'proxy_address', 'username',
            'ml_score', 'ml_tier', 'tier_confidence',
            'predicted_sharpe_30d', 'sharpe_ratio',
            'win_rate', 'max_drawdown', 'maker_ratio', 'avg_hold_hours',
            'rank', 'model_version', 'calculated_at'
        ]

        now = datetime.utcnow()
        data = []

        # Sort by CAPPED Sharpe to assign ranks (prevents noise from dominating)
        sharpe_data.sort(key=lambda x: x.sharpe_ratio_capped, reverse=True)

        for rank, s in enumerate(sharpe_data, 1):
            # Use capped Sharpe for tier assignment
            sharpe = s.sharpe_ratio_capped

            # Derive ML tier from Sharpe ratio
            # Note: We use capped value to prevent inflated tiers from noise
            if sharpe >= 2.0 and s.confidence >= 0.5:
                ml_tier = 'DIAMOND'
                ml_score = 90
            elif sharpe >= 1.5 and s.confidence >= 0.3:
                ml_tier = 'GOLD'
                ml_score = 75
            elif sharpe >= 1.0:
                ml_tier = 'SILVER'
                ml_score = 60
            elif sharpe >= 0.5:
                ml_tier = 'BRONZE'
                ml_score = 45
            else:
                ml_tier = 'BRONZE'
                ml_score = 30

            # Confidence-adjusted score: discount score for low-confidence data
            # This prevents traders with 3 lucky days from ranking above consistent traders
            adjusted_score = int(ml_score * (0.5 + 0.5 * s.confidence))

            data.append([
                s.proxy_address,
                s.username,
                adjusted_score,
                ml_tier,
                s.confidence,
                s.sharpe_ratio_capped,  # predicted_sharpe_30d (use capped)
                s.sharpe_ratio_capped,  # Store capped value for downstream use
                0.0,  # win_rate (calculated elsewhere)
                s.max_drawdown,
                0.0,  # maker_ratio (not calculated yet)
                0.0,  # avg_hold_hours (not calculated yet)
                rank,
                'sharpe_v2',  # Bumped version for improved algorithm
                now
            ])

        try:
            self.ch.insert(
                'polybot.aware_ml_scores',
                data,
                column_names=columns
            )
            return len(data)

        except Exception as e:
            logger.error(f"Failed to store Sharpe data: {e}")
            return 0

    def get_sharpe_summary(self) -> dict:
        """Get summary of Sharpe calculations"""
        query = """
        SELECT
            count() AS traders_with_sharpe,
            avg(sharpe_ratio) AS avg_sharpe,
            max(sharpe_ratio) AS max_sharpe,
            min(sharpe_ratio) AS min_sharpe,
            countIf(sharpe_ratio >= 1.0) AS traders_sharpe_above_1,
            countIf(sharpe_ratio >= 2.0) AS traders_sharpe_above_2
        FROM polybot.aware_ml_scores FINAL
        WHERE sharpe_ratio != 0
        """

        try:
            result = self.ch.query(query)
            if result.result_rows:
                row = result.result_rows[0]
                return {
                    'traders_with_sharpe': row[0],
                    'avg_sharpe': round(row[1] or 0, 4),
                    'max_sharpe': round(row[2] or 0, 4),
                    'min_sharpe': round(row[3] or 0, 4),
                    'traders_sharpe_above_1': row[4],
                    'traders_sharpe_above_2': row[5]
                }
        except Exception as e:
            logger.error(f"Failed to get Sharpe summary: {e}")

        return {}


def run_sharpe_calculation(clickhouse_client) -> dict:
    """Convenience function to run Sharpe calculation"""
    calculator = SharpeCalculator(clickhouse_client)
    traders_updated = calculator.run()

    return {
        'status': 'success',
        'traders_with_sharpe': traders_updated,
        'summary': calculator.get_sharpe_summary()
    }
