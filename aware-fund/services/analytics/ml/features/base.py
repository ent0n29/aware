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
        Extract features for multiple traders.

        Args:
            proxy_addresses: List of wallet addresses

        Returns:
            List of TraderFeatures
        """
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
