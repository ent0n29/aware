"""
Behavioral Feature Extractor

Analyzes trading behavior patterns:
- Hold time distribution
- Trading hours and timezone
- Market concentration
- Activity patterns
"""

import logging
import numpy as np
from collections import Counter

logger = logging.getLogger(__name__)


class BehavioralExtractor:
    """
    Extract behavioral patterns from trading activity.

    These features help classify trading style (scalper, swing, position)
    and detect consistent patterns that indicate skill.
    """

    def __init__(self, ch_client):
        self.ch_client = ch_client

    def extract(self, proxy_address: str) -> dict:
        """
        Extract behavioral metrics.

        Args:
            proxy_address: Trader wallet address

        Returns:
            Dict of behavioral metrics
        """
        try:
            # Get hold time metrics
            hold_metrics = self._get_hold_time_metrics(proxy_address)

            # Get activity pattern metrics
            activity_metrics = self._get_activity_metrics(proxy_address)

            # Get market concentration
            concentration = self._get_market_concentration(proxy_address)

            return {**hold_metrics, **activity_metrics, **concentration}

        except Exception as e:
            logger.error(f"Failed to extract behavioral metrics for {proxy_address}: {e}")
            return {}

    def _get_hold_time_metrics(self, proxy_address: str) -> dict:
        """
        Calculate hold time distribution.

        Hold time = time between opening and closing a position
        (approximated by matching buys with subsequent sells in same market)
        """
        try:
            result = self.ch_client.query("""
                WITH ordered_trades AS (
                    SELECT
                        market_slug,
                        token_id,
                        side,
                        ts,
                        size,
                        row_number() OVER (
                            PARTITION BY market_slug, token_id, side
                            ORDER BY ts
                        ) AS rn
                    FROM aware_global_trades_dedup
                    WHERE proxy_address = %(addr)s
                ),
                -- Match buys with sells
                matched AS (
                    SELECT
                        b.market_slug,
                        b.ts AS buy_ts,
                        s.ts AS sell_ts,
                        dateDiff('second', b.ts, s.ts) AS hold_seconds
                    FROM ordered_trades b
                    JOIN ordered_trades s ON
                        b.market_slug = s.market_slug AND
                        b.token_id = s.token_id AND
                        b.side = 'BUY' AND
                        s.side = 'SELL' AND
                        b.rn = s.rn
                    WHERE s.ts > b.ts
                )
                SELECT
                    avg(hold_seconds) / 3600 AS avg_hold_hours,
                    stddevPop(hold_seconds) / 3600 AS hold_std_hours,
                    countIf(hold_seconds < 3600) AS scalp_count,  -- < 1 hour
                    countIf(hold_seconds >= 86400) AS swing_count,  -- >= 1 day
                    count() AS total_matched
                FROM matched
            """, parameters={'addr': proxy_address})

            if not result.result_rows or result.result_rows[0][4] == 0:
                return {
                    'avg_hold_hours': 24.0,  # Default to 1 day
                    'hold_time_std': 48.0,
                    'scalper_ratio': 0.0,
                    'swing_trader_ratio': 0.0,
                }

            row = result.result_rows[0]
            total = row[4]

            return {
                'avg_hold_hours': row[0] or 24.0,
                'hold_time_std': row[1] or 48.0,
                'scalper_ratio': row[2] / total if total > 0 else 0,
                'swing_trader_ratio': row[3] / total if total > 0 else 0,
            }

        except Exception as e:
            logger.warning(f"Hold time calculation failed: {e}")
            return {
                'avg_hold_hours': 24.0,
                'hold_time_std': 48.0,
                'scalper_ratio': 0.0,
                'swing_trader_ratio': 0.0,
            }

    def _get_activity_metrics(self, proxy_address: str) -> dict:
        """
        Analyze trading activity patterns.

        Measures:
        - When trader is active (hour of day)
        - Weekend vs weekday
        - Trading frequency
        """
        try:
            result = self.ch_client.query("""
                SELECT
                    -- Activity by hour
                    toHour(ts) AS hour,
                    count() AS trades_in_hour,

                    -- Overall metrics (repeated in each row)
                    (SELECT count() FROM aware_global_trades_dedup
                     WHERE proxy_address = %(addr)s) AS total_trades,
                    (SELECT countIf(toDayOfWeek(ts) IN (6, 7))
                     FROM aware_global_trades_dedup
                     WHERE proxy_address = %(addr)s) AS weekend_trades,
                    (SELECT dateDiff('day', min(ts), max(ts)) + 1
                     FROM aware_global_trades_dedup
                     WHERE proxy_address = %(addr)s) AS span_days,
                    (SELECT uniqExact(toDate(ts))
                     FROM aware_global_trades_dedup
                     WHERE proxy_address = %(addr)s) AS active_days

                FROM aware_global_trades_dedup
                WHERE proxy_address = %(addr)s
                GROUP BY hour
                ORDER BY hour
            """, parameters={'addr': proxy_address})

            if not result.result_rows:
                return {
                    'active_hours_entropy': 0.0,
                    'weekend_activity_ratio': 0.0,
                    'trades_per_day': 0.0,
                    'days_active_ratio': 0.0,
                }

            # Calculate hour distribution entropy
            hour_counts = [0] * 24
            total_trades = 0
            weekend_trades = 0
            span_days = 1
            active_days = 1

            for row in result.result_rows:
                hour = row[0]
                count = row[1]
                hour_counts[hour] = count
                total_trades = row[2]
                weekend_trades = row[3]
                span_days = max(1, row[4])
                active_days = max(1, row[5])

            # Entropy of hour distribution (higher = more spread out)
            probs = np.array(hour_counts) / max(1, sum(hour_counts))
            probs = probs[probs > 0]  # Remove zeros for log
            entropy = -np.sum(probs * np.log2(probs)) if len(probs) > 0 else 0
            max_entropy = np.log2(24)  # Max if perfectly uniform
            normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0

            return {
                'active_hours_entropy': float(normalized_entropy),
                'weekend_activity_ratio': weekend_trades / total_trades if total_trades > 0 else 0,
                'trades_per_day': total_trades / span_days,
                'days_active_ratio': active_days / span_days,
            }

        except Exception as e:
            logger.warning(f"Activity metrics calculation failed: {e}")
            return {
                'active_hours_entropy': 0.0,
                'weekend_activity_ratio': 0.0,
                'trades_per_day': 0.0,
                'days_active_ratio': 0.0,
            }

    def _get_market_concentration(self, proxy_address: str) -> dict:
        """
        Measure market concentration (diversification).

        Herfindahl index - lower means more diversified.
        """
        try:
            result = self.ch_client.query("""
                SELECT
                    market_slug,
                    count() AS trades,
                    sum(notional) AS volume
                FROM aware_global_trades_dedup
                WHERE proxy_address = %(addr)s
                GROUP BY market_slug
                ORDER BY volume DESC
            """, parameters={'addr': proxy_address})

            if not result.result_rows:
                return {
                    'market_concentration': 1.0,
                    'top_3_markets_ratio': 1.0,
                }

            volumes = [row[2] for row in result.result_rows]
            total_volume = sum(volumes)

            if total_volume == 0:
                return {
                    'market_concentration': 1.0,
                    'top_3_markets_ratio': 1.0,
                }

            # Herfindahl-Hirschman Index
            shares = [v / total_volume for v in volumes]
            hhi = sum(s ** 2 for s in shares)

            # Top 3 concentration
            top_3 = sum(volumes[:3]) / total_volume

            return {
                'market_concentration': float(hhi),
                'top_3_markets_ratio': float(top_3),
            }

        except Exception as e:
            logger.warning(f"Market concentration calculation failed: {e}")
            return {
                'market_concentration': 1.0,
                'top_3_markets_ratio': 1.0,
            }
