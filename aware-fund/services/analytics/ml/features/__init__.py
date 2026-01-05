"""
Feature extraction modules for AWARE ML.

Provides comprehensive feature engineering from ClickHouse trade data:
- Risk metrics (Sharpe, drawdown, win rate)
- Execution quality (maker/taker, slippage)
- Behavioral patterns (hold time, trading hours)
- Trade sequences for LSTM models
"""

from .base import FeatureExtractor
from .risk_metrics import RiskMetricsExtractor
from .execution_quality import ExecutionQualityExtractor
from .behavioral import BehavioralExtractor
from .sequence import SequenceExtractor

__all__ = [
    'FeatureExtractor',
    'RiskMetricsExtractor',
    'ExecutionQualityExtractor',
    'BehavioralExtractor',
    'SequenceExtractor',
]
