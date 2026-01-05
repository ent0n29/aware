"""
Execution Quality Feature Extractor

Measures trading skill through execution analysis:
- Maker vs taker ratio
- Slippage and spread capture
- Price improvement
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)


class ExecutionQualityExtractor:
    """
    Extract execution quality metrics from trade data.

    These metrics help distinguish skilled traders from lucky ones
    by measuring how well they execute trades relative to market prices.
    """

    def __init__(self, ch_client):
        self.ch_client = ch_client

    def extract(self, proxy_address: str) -> dict:
        """
        Extract execution quality metrics.

        Args:
            proxy_address: Trader wallet address

        Returns:
            Dict of execution metrics
        """
        try:
            # Try enriched table with TOB data
            metrics = self._extract_from_enriched(proxy_address)

            if not metrics:
                # Fallback to estimation
                metrics = self._estimate_from_trades(proxy_address)

            return metrics

        except Exception as e:
            logger.error(f"Failed to extract execution metrics for {proxy_address}: {e}")
            return {}

    def _extract_from_enriched(self, proxy_address: str) -> dict:
        """Extract from enriched table with TOB data."""
        try:
            result = self.ch_client.query("""
                SELECT
                    -- Maker/Taker classification
                    countIf(exec_type = 'MAKER_LIKE') AS maker_count,
                    countIf(exec_type = 'TAKER_LIKE') AS taker_count,
                    count() AS total_trades,

                    -- Slippage (price vs mid)
                    avg(abs(price_minus_mid)) AS avg_price_deviation,
                    avg(effective_spread) AS avg_effective_spread,
                    avg(effective_spread_ratio) AS avg_spread_ratio,

                    -- Price improvement (got better than best bid/ask)
                    countIf(
                        (side = 'BUY' AND price < best_ask_price) OR
                        (side = 'SELL' AND price > best_bid_price)
                    ) AS improved_count

                FROM user_trade_enriched_v4
                WHERE proxy_address = %(addr)s
                  AND best_bid_price > 0
                  AND best_ask_price > 0
            """, parameters={'addr': proxy_address})

            if not result.result_rows or result.result_rows[0][2] == 0:
                return {}

            row = result.result_rows[0]
            maker, taker, total = row[0], row[1], row[2]

            return {
                'maker_ratio': maker / total if total > 0 else 0,
                'taker_ratio': taker / total if total > 0 else 0,
                'avg_slippage_bps': (row[3] or 0) * 10000,  # Convert to bps
                'effective_spread_ratio': row[5] or 0,
                'price_improvement_ratio': row[6] / total if total > 0 else 0,
            }

        except Exception as e:
            logger.debug(f"Enriched extraction failed, using fallback: {e}")
            return {}

    def _estimate_from_trades(self, proxy_address: str) -> dict:
        """
        Estimate execution quality from raw trades.

        Without TOB data, we use heuristics:
        - Small trades more likely maker
        - Trades at round prices more likely taker
        """
        try:
            result = self.ch_client.query("""
                SELECT
                    count() AS total_trades,
                    avg(size) AS avg_size,
                    avg(price) AS avg_price,
                    stddevPop(price) AS price_std,

                    -- Heuristic: trades at exactly 0.5 likely taker
                    countIf(abs(price - 0.5) < 0.01) AS mid_trades,

                    -- Small trades (<$50) more likely maker
                    countIf(notional < 50) AS small_trades

                FROM aware_global_trades_dedup
                WHERE proxy_address = %(addr)s
            """, parameters={'addr': proxy_address})

            if not result.result_rows or result.result_rows[0][0] == 0:
                return {
                    'maker_ratio': 0.5,
                    'taker_ratio': 0.5,
                    'avg_slippage_bps': 0,
                    'effective_spread_ratio': 0,
                    'price_improvement_ratio': 0,
                }

            row = result.result_rows[0]
            total = row[0]
            small_ratio = row[5] / total if total > 0 else 0.5

            # Estimate: more small trades = more likely maker
            estimated_maker = min(0.8, max(0.2, small_ratio * 1.5))

            return {
                'maker_ratio': estimated_maker,
                'taker_ratio': 1 - estimated_maker,
                'avg_slippage_bps': 0,  # Can't estimate without TOB
                'effective_spread_ratio': 0,
                'price_improvement_ratio': 0,
            }

        except Exception as e:
            logger.error(f"Failed to estimate execution quality: {e}")
            return {
                'maker_ratio': 0.5,
                'taker_ratio': 0.5,
                'avg_slippage_bps': 0,
                'effective_spread_ratio': 0,
                'price_improvement_ratio': 0,
            }
