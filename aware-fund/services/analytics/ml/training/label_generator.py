"""
Label Generator for ML Training

Bootstraps training labels from existing rule-based Smart Money Scores.
This allows us to train supervised models without manually labeling data.

The idea: use current scores as "soft labels" to train ML models that can
then generalize and potentially improve upon the rule-based approach.
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TraderLabel:
    """Training labels for a single trader."""
    proxy_address: str
    username: str
    tier_idx: int          # 0=BRONZE, 1=SILVER, 2=GOLD, 3=DIAMOND
    tier_name: str
    score: float           # 0-100 Smart Money Score
    sharpe_ratio: float    # Risk-adjusted return
    total_pnl: float       # Total P&L
    first_trade_at: str    # For time-based splitting


class LabelGenerator:
    """
    Bootstrap training labels from existing rule-based Smart Money Scores.

    Strategy:
    1. Query aware_smart_money_scores for tier assignments and scores
    2. Query aware_ml_scores for Sharpe ratios (if available)
    3. Query aware_trader_profiles for P&L and temporal data
    4. Combine into training labels

    This creates a "teacher" dataset from the rule-based system that
    the ML model can learn to replicate and potentially improve.
    """

    TIER_MAP = {'BRONZE': 0, 'SILVER': 1, 'GOLD': 2, 'DIAMOND': 3}
    TIER_NAMES = ['BRONZE', 'SILVER', 'GOLD', 'DIAMOND']

    def __init__(self, ch_client):
        """
        Initialize label generator.

        Args:
            ch_client: ClickHouse client (clickhouse_connect)
        """
        self.ch_client = ch_client

    def generate_labels(
        self,
        min_trades: int = 10,
        max_traders: int = 50000,
        require_sharpe: bool = False
    ) -> Dict[str, TraderLabel]:
        """
        Generate training labels for all eligible traders.

        Labels are bootstrapped from:
        - tier: From aware_smart_money_scores (BRONZE/SILVER/GOLD/DIAMOND)
        - score: From aware_smart_money_scores (0-100)
        - sharpe: From aware_ml_scores or calculated from P&L
        - pnl: From aware_trader_profiles

        Args:
            min_trades: Minimum trades to be included
            max_traders: Maximum traders to return
            require_sharpe: Only include traders with Sharpe data

        Returns:
            Dict mapping proxy_address -> TraderLabel
        """
        logger.info(f"Generating labels (min_trades={min_trades}, max={max_traders})...")

        # Build query with all label sources
        sharpe_filter = "AND ml.sharpe_ratio IS NOT NULL" if require_sharpe else ""

        query = f"""
            SELECT
                s.proxy_address,
                s.username,
                s.tier,
                s.total_score,
                coalesce(ml.sharpe_ratio, 0) as sharpe_ratio,
                coalesce(p.total_pnl, 0) as total_pnl,
                p.first_trade_at,
                p.total_trades
            FROM (SELECT * FROM polybot.aware_smart_money_scores FINAL) s
            LEFT JOIN (SELECT * FROM polybot.aware_ml_scores FINAL) ml
                ON s.proxy_address = ml.proxy_address
            LEFT JOIN (SELECT * FROM polybot.aware_trader_profiles FINAL) p
                ON s.proxy_address = p.proxy_address
            WHERE p.total_trades >= {min_trades}
            {sharpe_filter}
            ORDER BY p.first_trade_at ASC
            LIMIT {max_traders}
        """

        try:
            result = self.ch_client.query(query)
            rows = result.result_rows

            logger.info(f"Found {len(rows)} traders with labels")

            labels = {}
            for row in rows:
                proxy_address = row[0]
                tier_name = row[2] or 'BRONZE'

                labels[proxy_address] = TraderLabel(
                    proxy_address=proxy_address,
                    username=row[1] or '',
                    tier_idx=self.TIER_MAP.get(tier_name, 0),
                    tier_name=tier_name,
                    score=float(row[3] or 50),
                    sharpe_ratio=float(row[4] or 0),
                    total_pnl=float(row[5] or 0),
                    first_trade_at=str(row[6]) if row[6] else ''
                )

            # Log tier distribution
            tier_counts = {}
            for label in labels.values():
                tier_counts[label.tier_name] = tier_counts.get(label.tier_name, 0) + 1
            logger.info(f"Tier distribution: {tier_counts}")

            return labels

        except Exception as e:
            logger.error(f"Failed to generate labels: {e}")
            raise

    def generate_labels_with_derived_sharpe(
        self,
        min_trades: int = 10,
        max_traders: int = 50000,
        lookback_days: int = 90
    ) -> Dict[str, TraderLabel]:
        """
        Generate labels with Sharpe ratio calculated from daily P&L.

        For traders without pre-computed Sharpe, calculate from position P&L:
        Sharpe = mean(daily_returns) / std(daily_returns) * sqrt(252)

        This provides more complete training data.
        """
        logger.info("Generating labels with derived Sharpe ratios...")

        # First get base labels
        labels = self.generate_labels(min_trades, max_traders, require_sharpe=False)

        # For traders with sharpe=0, calculate from daily P&L
        traders_needing_sharpe = [
            addr for addr, label in labels.items()
            if label.sharpe_ratio == 0
        ]

        if traders_needing_sharpe:
            logger.info(f"Calculating Sharpe for {len(traders_needing_sharpe)} traders...")
            derived_sharpes = self._calculate_sharpe_batch(
                traders_needing_sharpe, lookback_days
            )

            for addr, sharpe in derived_sharpes.items():
                if addr in labels:
                    labels[addr].sharpe_ratio = sharpe

        # Log statistics
        sharpes = [l.sharpe_ratio for l in labels.values()]
        logger.info(
            f"Sharpe stats: min={min(sharpes):.2f}, max={max(sharpes):.2f}, "
            f"mean={np.mean(sharpes):.2f}, non-zero={sum(1 for s in sharpes if s != 0)}"
        )

        return labels

    def _calculate_sharpe_batch(
        self,
        proxy_addresses: List[str],
        lookback_days: int
    ) -> Dict[str, float]:
        """
        Calculate Sharpe ratio from daily P&L for multiple traders.

        Uses aware_position_pnl or aware_global_trades to compute daily returns.
        """
        if not proxy_addresses:
            return {}

        # Format addresses for SQL IN clause
        addr_list = "', '".join(proxy_addresses)

        query = f"""
            SELECT
                proxy_address,
                toDate(ts) as day,
                sum(
                    CASE side
                        WHEN 'BUY' THEN -size * price
                        ELSE size * price
                    END
                ) as daily_pnl
            FROM polybot.aware_global_trades_dedup
            WHERE proxy_address IN ('{addr_list}')
            AND ts >= now() - INTERVAL {lookback_days} DAY
            GROUP BY proxy_address, day
            ORDER BY proxy_address, day
        """

        try:
            result = self.ch_client.query(query)

            # Group by trader
            trader_pnls: Dict[str, List[float]] = {}
            for row in result.result_rows:
                addr = row[0]
                pnl = float(row[2])
                if addr not in trader_pnls:
                    trader_pnls[addr] = []
                trader_pnls[addr].append(pnl)

            # Calculate Sharpe for each trader
            sharpes = {}
            for addr, pnls in trader_pnls.items():
                if len(pnls) >= 5:  # Need at least 5 days of data
                    mean_ret = np.mean(pnls)
                    std_ret = np.std(pnls)
                    if std_ret > 0:
                        # Annualized Sharpe (252 trading days)
                        sharpes[addr] = (mean_ret / std_ret) * np.sqrt(252)
                    else:
                        sharpes[addr] = 0.0
                else:
                    sharpes[addr] = 0.0

            return sharpes

        except Exception as e:
            logger.warning(f"Failed to calculate Sharpe batch: {e}")
            return {}

    def get_label_arrays(
        self,
        labels: Dict[str, TraderLabel],
        addresses: List[str]
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Convert labels dict to numpy arrays aligned with address list.

        Args:
            labels: Dict from generate_labels()
            addresses: Ordered list of proxy addresses

        Returns:
            (tier_labels, sharpe_labels, score_labels) arrays
        """
        n = len(addresses)
        tiers = np.zeros(n, dtype=np.int32)
        sharpes = np.zeros(n, dtype=np.float32)
        scores = np.zeros(n, dtype=np.float32)

        for i, addr in enumerate(addresses):
            if addr in labels:
                label = labels[addr]
                tiers[i] = label.tier_idx
                sharpes[i] = label.sharpe_ratio
                scores[i] = label.score
            else:
                # Default values for missing labels
                tiers[i] = 0  # BRONZE
                sharpes[i] = 0.0
                scores[i] = 50.0

        return tiers, sharpes, scores

    def get_tier_weights(self, labels: Dict[str, TraderLabel]) -> np.ndarray:
        """
        Calculate class weights for imbalanced tier distribution.

        Higher-tier traders are rarer, so we weight them more heavily
        during training to prevent the model from just predicting BRONZE.
        """
        tier_counts = np.zeros(4)
        for label in labels.values():
            tier_counts[label.tier_idx] += 1

        # Inverse frequency weighting
        total = sum(tier_counts)
        weights = total / (4 * tier_counts + 1e-6)

        # Normalize so weights sum to 4 (number of classes)
        weights = weights / weights.sum() * 4

        logger.info(f"Tier weights: {dict(zip(self.TIER_NAMES, weights))}")

        return weights.astype(np.float32)
