"""
Model Metrics - Track and log model performance.

Records:
- Classification accuracy per tier
- Sharpe prediction MAE/RMSE
- Calibration curves
- Feature importance
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TierMetrics:
    """Metrics for a single tier."""
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    support: int = 0


@dataclass
class ModelMetrics:
    """
    Comprehensive model performance metrics.

    Tracks classification and regression performance
    with detailed breakdowns.
    """

    # Overall
    accuracy: float = 0.0
    sharpe_mae: float = 0.0
    sharpe_rmse: float = 0.0

    # Per-tier
    tier_metrics: Dict[str, TierMetrics] = field(default_factory=dict)

    # Calibration (confidence vs actual accuracy)
    calibration_bins: List[float] = field(default_factory=list)
    calibration_accuracy: List[float] = field(default_factory=list)

    # Feature importance (from XGBoost)
    feature_importance: Dict[str, float] = field(default_factory=dict)

    # Metadata
    n_samples: int = 0
    model_version: str = ""
    evaluated_at: datetime = field(default_factory=datetime.utcnow)

    TIER_LABELS = ['BRONZE', 'SILVER', 'GOLD', 'DIAMOND']

    @classmethod
    def compute(
        cls,
        y_true_tier: np.ndarray,
        y_pred_tier: np.ndarray,
        tier_probs: np.ndarray,
        y_true_sharpe: np.ndarray,
        y_pred_sharpe: np.ndarray,
        feature_importance: Optional[Dict[str, float]] = None,
        model_version: str = ""
    ) -> 'ModelMetrics':
        """
        Compute all metrics from predictions.

        Args:
            y_true_tier: True tier indices (0-3)
            y_pred_tier: Predicted tier indices
            tier_probs: Prediction probabilities (N, 4)
            y_true_sharpe: True Sharpe ratios
            y_pred_sharpe: Predicted Sharpe ratios
            feature_importance: Optional feature importance dict
            model_version: Model version string

        Returns:
            ModelMetrics instance
        """
        metrics = cls()
        metrics.n_samples = len(y_true_tier)
        metrics.model_version = model_version

        # Overall accuracy
        metrics.accuracy = (y_true_tier == y_pred_tier).mean()

        # Sharpe metrics (filter invalid values)
        valid = np.isfinite(y_true_sharpe) & np.isfinite(y_pred_sharpe)
        if valid.sum() > 0:
            residuals = y_pred_sharpe[valid] - y_true_sharpe[valid]
            metrics.sharpe_mae = np.mean(np.abs(residuals))
            metrics.sharpe_rmse = np.sqrt(np.mean(residuals ** 2))

        # Per-tier metrics
        for i, tier in enumerate(cls.TIER_LABELS):
            true_mask = y_true_tier == i
            pred_mask = y_pred_tier == i

            tp = (true_mask & pred_mask).sum()
            fp = (~true_mask & pred_mask).sum()
            fn = (true_mask & ~pred_mask).sum()

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

            metrics.tier_metrics[tier] = TierMetrics(
                precision=precision,
                recall=recall,
                f1=f1,
                support=true_mask.sum()
            )

        # Calibration curve
        confidences = np.max(tier_probs, axis=1)
        correct = y_true_tier == y_pred_tier

        n_bins = 10
        bin_edges = np.linspace(0, 1, n_bins + 1)

        for i in range(n_bins):
            mask = (confidences >= bin_edges[i]) & (confidences < bin_edges[i + 1])
            if mask.sum() > 0:
                metrics.calibration_bins.append((bin_edges[i] + bin_edges[i + 1]) / 2)
                metrics.calibration_accuracy.append(correct[mask].mean())

        # Feature importance
        if feature_importance:
            metrics.feature_importance = feature_importance

        return metrics

    def to_dict(self) -> Dict:
        """Convert to dictionary for logging/storage."""
        return {
            'accuracy': self.accuracy,
            'sharpe_mae': self.sharpe_mae,
            'sharpe_rmse': self.sharpe_rmse,
            'tier_metrics': {
                tier: {
                    'precision': m.precision,
                    'recall': m.recall,
                    'f1': m.f1,
                    'support': m.support
                }
                for tier, m in self.tier_metrics.items()
            },
            'calibration': {
                'bins': self.calibration_bins,
                'accuracy': self.calibration_accuracy
            },
            'top_features': dict(sorted(
                self.feature_importance.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]),
            'n_samples': self.n_samples,
            'model_version': self.model_version,
            'evaluated_at': self.evaluated_at.isoformat(),
        }

    def log_summary(self) -> None:
        """Log metrics summary."""
        logger.info("=" * 50)
        logger.info("Model Performance Summary")
        logger.info("=" * 50)
        logger.info(f"Samples: {self.n_samples}")
        logger.info(f"Overall Accuracy: {self.accuracy:.3f}")
        logger.info(f"Sharpe MAE: {self.sharpe_mae:.3f}")
        logger.info(f"Sharpe RMSE: {self.sharpe_rmse:.3f}")

        logger.info("\nPer-Tier Metrics:")
        for tier, m in self.tier_metrics.items():
            logger.info(f"  {tier}: P={m.precision:.3f} R={m.recall:.3f} F1={m.f1:.3f} (n={m.support})")

        if self.feature_importance:
            logger.info("\nTop Features:")
            sorted_features = sorted(
                self.feature_importance.items(),
                key=lambda x: x[1], reverse=True
            )[:5]
            for name, imp in sorted_features:
                logger.info(f"  {name}: {imp:.3f}")

        logger.info("=" * 50)

    def save_to_clickhouse(self, ch_client) -> None:
        """Save metrics to ClickHouse for historical tracking."""
        try:
            data = [
                [
                    datetime.utcnow(),
                    'ml_accuracy',
                    self.accuracy,
                    {'model_version': self.model_version}
                ],
                [
                    datetime.utcnow(),
                    'ml_sharpe_mae',
                    self.sharpe_mae,
                    {'model_version': self.model_version}
                ],
                [
                    datetime.utcnow(),
                    'ml_sharpe_rmse',
                    self.sharpe_rmse,
                    {'model_version': self.model_version}
                ],
            ]

            # Add per-tier metrics
            for tier, m in self.tier_metrics.items():
                data.append([
                    datetime.utcnow(),
                    f'ml_{tier.lower()}_f1',
                    m.f1,
                    {'model_version': self.model_version}
                ])

            ch_client.insert(
                'aware_ingestion_metrics',
                data,
                column_names=['ts', 'metric_name', 'metric_value', 'tags']
            )

            logger.info("Saved metrics to ClickHouse")

        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")
