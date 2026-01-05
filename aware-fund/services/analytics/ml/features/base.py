"""
Base Feature Extractor - Orchestrates all feature extraction.

Combines risk, execution, behavioral, and sequence features into
a unified feature vector for each trader.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
import numpy as np

from .risk_metrics import RiskMetricsExtractor
from .execution_quality import ExecutionQualityExtractor
from .behavioral import BehavioralExtractor
from .sequence import SequenceExtractor

logger = logging.getLogger(__name__)


@dataclass
class TraderFeatures:
    """Complete feature vector for a single trader."""
    proxy_address: str
    username: str

    # Risk metrics
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    calmar_ratio: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    win_loss_ratio: float = 0.0
    consecutive_wins_max: int = 0
    consecutive_losses_max: int = 0

    # Execution quality
    maker_ratio: float = 0.0
    taker_ratio: float = 0.0
    avg_slippage_bps: float = 0.0
    effective_spread_ratio: float = 0.0
    price_improvement_ratio: float = 0.0

    # Behavioral
    avg_hold_hours: float = 0.0
    hold_time_std: float = 0.0
    scalper_ratio: float = 0.0
    swing_trader_ratio: float = 0.0
    active_hours_entropy: float = 0.0
    weekend_activity_ratio: float = 0.0
    trades_per_day: float = 0.0
    days_active_ratio: float = 0.0
    market_concentration: float = 0.0
    top_3_markets_ratio: float = 0.0

    # Aggregated stats
    total_trades: int = 0
    total_volume_usd: float = 0.0
    total_pnl: float = 0.0
    unique_markets: int = 0
    days_active: int = 0

    # HFT/Arb detection features
    complete_set_ratio: float = 0.0      # % of markets where both outcomes traded
    avg_inter_trade_seconds: float = 0.0  # Average time between trades
    updown_market_ratio: float = 0.0      # % trades on Up/Down markets
    trades_per_hour: float = 0.0          # Trade frequency (high = HFT)

    # Sequence data (for LSTM)
    trade_sequence: Optional[np.ndarray] = None
    sequence_length: int = 0

    def to_tabular_vector(self) -> np.ndarray:
        """Convert to numpy array for XGBoost."""
        return np.array([
            self.sharpe_ratio,
            self.sortino_ratio,
            self.max_drawdown,
            self.calmar_ratio,
            self.win_rate,
            self.profit_factor,
            self.avg_win,
            self.avg_loss,
            self.win_loss_ratio,
            self.consecutive_wins_max,
            self.consecutive_losses_max,
            self.maker_ratio,
            self.taker_ratio,
            self.avg_slippage_bps,
            self.effective_spread_ratio,
            self.price_improvement_ratio,
            self.avg_hold_hours,
            self.hold_time_std,
            self.scalper_ratio,
            self.swing_trader_ratio,
            self.active_hours_entropy,
            self.weekend_activity_ratio,
            self.trades_per_day,
            self.days_active_ratio,
            self.market_concentration,
            self.top_3_markets_ratio,
            self.total_trades,
            self.total_volume_usd,
            self.total_pnl,
            self.unique_markets,
            self.days_active,
            # HFT/Arb detection features
            self.complete_set_ratio,
            self.avg_inter_trade_seconds,
            self.updown_market_ratio,
            self.trades_per_hour,
        ], dtype=np.float32)

    @staticmethod
    def feature_names() -> list[str]:
        """Get feature names for interpretability."""
        return [
            'sharpe_ratio', 'sortino_ratio', 'max_drawdown', 'calmar_ratio',
            'win_rate', 'profit_factor', 'avg_win', 'avg_loss', 'win_loss_ratio',
            'consecutive_wins_max', 'consecutive_losses_max',
            'maker_ratio', 'taker_ratio', 'avg_slippage_bps',
            'effective_spread_ratio', 'price_improvement_ratio',
            'avg_hold_hours', 'hold_time_std', 'scalper_ratio', 'swing_trader_ratio',
            'active_hours_entropy', 'weekend_activity_ratio',
            'trades_per_day', 'days_active_ratio',
            'market_concentration', 'top_3_markets_ratio',
            'total_trades', 'total_volume_usd', 'total_pnl',
            'unique_markets', 'days_active',
            # HFT/Arb detection features
            'complete_set_ratio', 'avg_inter_trade_seconds',
            'updown_market_ratio', 'trades_per_hour',
        ]


class FeatureExtractor:
    """
    Main feature extraction orchestrator.

    Combines all feature extractors to produce comprehensive
    feature vectors for ML models.
    """

    def __init__(self, ch_client, sequence_length: int = 100):
        """
        Initialize feature extractor.

        Args:
            ch_client: ClickHouse client for data access
            sequence_length: Number of recent trades for LSTM
        """
        self.ch_client = ch_client
        self.sequence_length = sequence_length

        # Initialize sub-extractors
        self.risk_extractor = RiskMetricsExtractor(ch_client)
        self.execution_extractor = ExecutionQualityExtractor(ch_client)
        self.behavioral_extractor = BehavioralExtractor(ch_client)
        self.sequence_extractor = SequenceExtractor(ch_client, sequence_length)

    def extract_features(self, proxy_address: str) -> TraderFeatures:
        """
        Extract all features for a single trader.

        Args:
            proxy_address: Trader's wallet address

        Returns:
            TraderFeatures with all computed features
        """
        # Get basic info
        basic = self._get_basic_info(proxy_address)

        # Extract each feature category
        risk = self.risk_extractor.extract(proxy_address)
        execution = self.execution_extractor.extract(proxy_address)
        behavioral = self.behavioral_extractor.extract(proxy_address)
        sequence = self.sequence_extractor.extract(proxy_address)
        hft = self._get_hft_features(proxy_address)

        return TraderFeatures(
            proxy_address=proxy_address,
            username=basic.get('username', ''),
            # Risk
            sharpe_ratio=risk.get('sharpe_ratio', 0),
            sortino_ratio=risk.get('sortino_ratio', 0),
            max_drawdown=risk.get('max_drawdown', 0),
            calmar_ratio=risk.get('calmar_ratio', 0),
            win_rate=risk.get('win_rate', 0),
            profit_factor=risk.get('profit_factor', 0),
            avg_win=risk.get('avg_win', 0),
            avg_loss=risk.get('avg_loss', 0),
            win_loss_ratio=risk.get('win_loss_ratio', 0),
            consecutive_wins_max=risk.get('consecutive_wins_max', 0),
            consecutive_losses_max=risk.get('consecutive_losses_max', 0),
            # Execution
            maker_ratio=execution.get('maker_ratio', 0),
            taker_ratio=execution.get('taker_ratio', 0),
            avg_slippage_bps=execution.get('avg_slippage_bps', 0),
            effective_spread_ratio=execution.get('effective_spread_ratio', 0),
            price_improvement_ratio=execution.get('price_improvement_ratio', 0),
            # Behavioral
            avg_hold_hours=behavioral.get('avg_hold_hours', 0),
            hold_time_std=behavioral.get('hold_time_std', 0),
            scalper_ratio=behavioral.get('scalper_ratio', 0),
            swing_trader_ratio=behavioral.get('swing_trader_ratio', 0),
            active_hours_entropy=behavioral.get('active_hours_entropy', 0),
            weekend_activity_ratio=behavioral.get('weekend_activity_ratio', 0),
            trades_per_day=behavioral.get('trades_per_day', 0),
            days_active_ratio=behavioral.get('days_active_ratio', 0),
            market_concentration=behavioral.get('market_concentration', 0),
            top_3_markets_ratio=behavioral.get('top_3_markets_ratio', 0),
            # Aggregated
            total_trades=basic.get('total_trades', 0),
            total_volume_usd=basic.get('total_volume_usd', 0),
            total_pnl=basic.get('total_pnl', 0),
            unique_markets=basic.get('unique_markets', 0),
            days_active=basic.get('days_active', 0),
            # HFT/Arb detection
            complete_set_ratio=hft.get('complete_set_ratio', 0),
            avg_inter_trade_seconds=hft.get('avg_inter_trade_seconds', 0),
            updown_market_ratio=hft.get('updown_market_ratio', 0),
            trades_per_hour=hft.get('trades_per_hour', 0),
            # Sequence
            trade_sequence=sequence.get('sequence'),
            sequence_length=sequence.get('length', 0),
        )

    def extract_batch(self, proxy_addresses: list[str]) -> list[TraderFeatures]:
        """
        Extract features for multiple traders using the optimized batch view.

        This method uses polybot.aware_ml_features_batch which computes all 35
        features in a single query, replacing 6+ queries per trader with 1 batch query.

        Args:
            proxy_addresses: List of wallet addresses

        Returns:
            List of TraderFeatures
        """
        if not proxy_addresses:
            return []

        # Use the optimized batch view
        return self._extract_batch_from_view(proxy_addresses)

    def _extract_batch_from_view(self, proxy_addresses: list[str]) -> list[TraderFeatures]:
        """
        Extract features using the pre-computed ClickHouse batch view.

        The view polybot.aware_ml_features_batch computes all 35 ML features
        in a single pass using CTEs and window functions, dramatically reducing
        query overhead from ~6 queries/trader to 1 query for ALL traders.
        """
        logger.info(f"Batch extracting features for {len(proxy_addresses)} traders using view...")

        try:
            # For large batches or "all traders", don't filter by address
            if len(proxy_addresses) > 5000:
                # Query all features (view already filters for min 5 trades)
                result = self.ch_client.query("""
                    SELECT
                        proxy_address,
                        total_trades,
                        total_volume_usd,
                        total_pnl,
                        unique_markets,
                        days_active,
                        sharpe_ratio,
                        sortino_ratio,
                        max_drawdown,
                        calmar_ratio,
                        win_rate,
                        profit_factor,
                        avg_win,
                        avg_loss,
                        win_loss_ratio,
                        consecutive_wins_max,
                        consecutive_losses_max,
                        maker_ratio,
                        taker_ratio,
                        avg_slippage_bps,
                        effective_spread_ratio,
                        price_improvement_ratio,
                        avg_hold_hours,
                        hold_time_std,
                        scalper_ratio,
                        swing_trader_ratio,
                        active_hours_entropy,
                        weekend_activity_ratio,
                        trades_per_day,
                        days_active_ratio,
                        market_concentration,
                        top_3_markets_ratio,
                        complete_set_ratio,
                        avg_inter_trade_seconds,
                        updown_market_ratio,
                        trades_per_hour
                    FROM polybot.aware_ml_features_batch
                """)
                requested = set(proxy_addresses)
            else:
                # Filter in SQL for smaller batches
                addr_list = "', '".join(proxy_addresses)
                result = self.ch_client.query(f"""
                    SELECT
                        proxy_address,
                        total_trades,
                        total_volume_usd,
                        total_pnl,
                        unique_markets,
                        days_active,
                        sharpe_ratio,
                        sortino_ratio,
                        max_drawdown,
                        calmar_ratio,
                        win_rate,
                        profit_factor,
                        avg_win,
                        avg_loss,
                        win_loss_ratio,
                        consecutive_wins_max,
                        consecutive_losses_max,
                        maker_ratio,
                        taker_ratio,
                        avg_slippage_bps,
                        effective_spread_ratio,
                        price_improvement_ratio,
                        avg_hold_hours,
                        hold_time_std,
                        scalper_ratio,
                        swing_trader_ratio,
                        active_hours_entropy,
                        weekend_activity_ratio,
                        trades_per_day,
                        days_active_ratio,
                        market_concentration,
                        top_3_markets_ratio,
                        complete_set_ratio,
                        avg_inter_trade_seconds,
                        updown_market_ratio,
                        trades_per_hour
                    FROM polybot.aware_ml_features_batch
                    WHERE proxy_address IN ('{addr_list}')
                """)
                requested = None  # No need to filter in Python

            if not result.result_rows:
                logger.warning("No features returned from batch view")
                return []

            features = []
            for row in result.result_rows:
                addr = row[0]
                if requested and addr not in requested:
                    continue

                features.append(TraderFeatures(
                    proxy_address=addr,
                    username='',  # Will be filled from profiles if needed
                    # Aggregated stats
                    total_trades=int(row[1] or 0),
                    total_volume_usd=float(row[2] or 0),
                    total_pnl=float(row[3] or 0),
                    unique_markets=int(row[4] or 0),
                    days_active=int(row[5] or 0),
                    # Risk metrics
                    sharpe_ratio=float(row[6] or 0),
                    sortino_ratio=float(row[7] or 0),
                    max_drawdown=float(row[8] or 0),
                    calmar_ratio=float(row[9] or 0),
                    win_rate=float(row[10] or 0),
                    profit_factor=float(row[11] or 0),
                    avg_win=float(row[12] or 0),
                    avg_loss=float(row[13] or 0),
                    win_loss_ratio=float(row[14] or 0),
                    consecutive_wins_max=int(row[15] or 0),
                    consecutive_losses_max=int(row[16] or 0),
                    # Execution quality
                    maker_ratio=float(row[17] or 0),
                    taker_ratio=float(row[18] or 0),
                    avg_slippage_bps=float(row[19] or 0),
                    effective_spread_ratio=float(row[20] or 0),
                    price_improvement_ratio=float(row[21] or 0),
                    # Behavioral
                    avg_hold_hours=float(row[22] or 0),
                    hold_time_std=float(row[23] or 0),
                    scalper_ratio=float(row[24] or 0),
                    swing_trader_ratio=float(row[25] or 0),
                    active_hours_entropy=float(row[26] or 0),
                    weekend_activity_ratio=float(row[27] or 0),
                    trades_per_day=float(row[28] or 0),
                    days_active_ratio=float(row[29] or 0),
                    market_concentration=float(row[30] or 0),
                    top_3_markets_ratio=float(row[31] or 0),
                    # HFT/Arb detection
                    complete_set_ratio=float(row[32] or 0),
                    avg_inter_trade_seconds=float(row[33] or 0),
                    updown_market_ratio=float(row[34] or 0),
                    trades_per_hour=float(row[35] or 0),
                ))

            logger.info(f"Batch extracted {len(features)} feature sets")
            return features

        except Exception as e:
            logger.error(f"Batch feature extraction failed: {e}")
            # Fallback to per-trader extraction (slow but works)
            logger.warning("Falling back to per-trader extraction")
            return self._extract_batch_legacy(proxy_addresses)

    def _extract_batch_legacy(self, proxy_addresses: list[str]) -> list[TraderFeatures]:
        """Legacy per-trader extraction (fallback only)."""
        features = []
        for addr in proxy_addresses:
            try:
                feat = self.extract_features(addr)
                features.append(feat)
            except Exception as e:
                logger.warning(f"Failed to extract features for {addr}: {e}")
        return features

    def _get_basic_info(self, proxy_address: str) -> dict:
        """Get basic trader info from profiles table."""
        try:
            result = self.ch_client.query(f"""
                SELECT
                    username,
                    total_trades,
                    total_volume_usd,
                    total_pnl,
                    unique_markets,
                    days_active
                FROM aware_trader_profiles FINAL
                WHERE proxy_address = %(addr)s
            """, parameters={'addr': proxy_address})

            if result.result_rows:
                row = result.result_rows[0]
                return {
                    'username': row[0] or '',
                    'total_trades': row[1] or 0,
                    'total_volume_usd': row[2] or 0,
                    'total_pnl': row[3] or 0,
                    'unique_markets': row[4] or 0,
                    'days_active': row[5] or 0,
                }
        except Exception as e:
            logger.error(f"Failed to get basic info: {e}")

        return {}

    def _get_hft_features(self, proxy_address: str) -> dict:
        """
        Extract HFT/arbitrage detection features.

        Returns:
            - complete_set_ratio: % of markets where both outcomes traded (arb indicator)
            - avg_inter_trade_seconds: Average time between trades (speed indicator)
            - updown_market_ratio: % trades on Up/Down price markets
            - trades_per_hour: Trade frequency
        """
        try:
            result = self.ch_client.query("""
                WITH trader_markets AS (
                    SELECT
                        market_slug,
                        countDistinct(outcome) AS outcomes_traded,
                        count() AS trade_count,
                        min(ts) AS first_trade,
                        max(ts) AS last_trade
                    FROM polybot.aware_global_trades_dedup
                    WHERE proxy_address = %(addr)s
                    GROUP BY market_slug
                ),
                updown_markets AS (
                    SELECT count() AS updown_count
                    FROM trader_markets
                    WHERE market_slug LIKE '%%-up-%%'
                       OR market_slug LIKE '%%-down-%%'
                       OR market_slug LIKE '%%-above-%%'
                       OR market_slug LIKE '%%-below-%%'
                )
                SELECT
                    -- Complete set ratio: markets where both YES and NO traded
                    countIf(outcomes_traded = 2) / greatest(count(), 1) AS complete_set_ratio,
                    -- Total trades for frequency calc
                    sum(trade_count) AS total_trades,
                    -- Time span
                    dateDiff('second', min(first_trade), max(last_trade)) AS time_span_seconds,
                    -- Up/down market ratio
                    (SELECT updown_count FROM updown_markets) / greatest(count(), 1) AS updown_ratio
                FROM trader_markets
            """, parameters={'addr': proxy_address})

            if result.result_rows:
                row = result.result_rows[0]
                complete_set_ratio = float(row[0] or 0)
                total_trades = int(row[1] or 0)
                time_span_seconds = int(row[2] or 0)
                updown_ratio = float(row[3] or 0)

                # Calculate derived metrics
                avg_inter_trade = time_span_seconds / max(total_trades - 1, 1) if total_trades > 1 else 0
                trades_per_hour = (total_trades / max(time_span_seconds, 1)) * 3600 if time_span_seconds > 0 else 0

                return {
                    'complete_set_ratio': complete_set_ratio,
                    'avg_inter_trade_seconds': avg_inter_trade,
                    'updown_market_ratio': updown_ratio,
                    'trades_per_hour': trades_per_hour,
                }
        except Exception as e:
            logger.warning(f"Failed to extract HFT features: {e}")

        return {
            'complete_set_ratio': 0.0,
            'avg_inter_trade_seconds': 0.0,
            'updown_market_ratio': 0.0,
            'trades_per_hour': 0.0,
        }

    def to_training_batch(
        self,
        features_list: list[TraderFeatures]
    ) -> tuple[np.ndarray, np.ndarray, list[int]]:
        """
        Convert features to training batch format.

        Returns:
            - tabular_features: (N, n_features) array
            - sequences: (N, seq_len, seq_features) array
            - sequence_lengths: List of actual sequence lengths
        """
        n = len(features_list)
        n_features = len(TraderFeatures.feature_names())

        tabular = np.zeros((n, n_features), dtype=np.float32)
        seq_dim = 5  # price, size, side, time_delta, outcome_idx
        sequences = np.zeros((n, self.sequence_length, seq_dim), dtype=np.float32)
        lengths = []

        for i, feat in enumerate(features_list):
            tabular[i] = feat.to_tabular_vector()
            if feat.trade_sequence is not None:
                seq_len = min(feat.sequence_length, self.sequence_length)
                sequences[i, :seq_len] = feat.trade_sequence[:seq_len]
                lengths.append(seq_len)
            else:
                lengths.append(0)

        return tabular, sequences, lengths
