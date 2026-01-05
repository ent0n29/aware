"""
AWARE ML Module - Machine Learning for Smart Money Scoring

This module provides:
- Feature extraction from trade data
- LSTM sequence model for trade pattern analysis
- XGBoost tabular model for aggregated metrics
- Ensemble model combining both approaches
- Training and evaluation pipelines
"""

from .features import FeatureExtractor
from .models import AWAREEnsemble, TraderSequenceModel, TabularScorer

__all__ = [
    'FeatureExtractor',
    'AWAREEnsemble',
    'TraderSequenceModel',
    'TabularScorer',
]
