"""
Drift Detection - Monitor feature and prediction distribution changes.

Detects:
- Feature drift (input distribution changes)
- Concept drift (relationship between features and labels changes)
- Prediction drift (output distribution changes)
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


@dataclass
class DriftResult:
    """Result of drift detection for a single feature."""
    feature_name: str
    baseline_mean: float
    current_mean: float
    baseline_std: float
    current_std: float
    ks_statistic: float
    ks_pvalue: float
    is_drifted: bool
    drift_severity: str  # 'none', 'low', 'medium', 'high'


@dataclass
class DriftReport:
    """Complete drift detection report."""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    n_features: int = 0
    n_drifted: int = 0
    drift_ratio: float = 0.0
    feature_results: List[DriftResult] = field(default_factory=list)
    prediction_drift: Optional[DriftResult] = None
    alert_level: str = 'normal'  # 'normal', 'warning', 'critical'

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'n_features': self.n_features,
            'n_drifted': self.n_drifted,
            'drift_ratio': self.drift_ratio,
            'alert_level': self.alert_level,
            'drifted_features': [
                {
                    'name': r.feature_name,
                    'severity': r.drift_severity,
                    'ks_statistic': r.ks_statistic,
                    'ks_pvalue': r.ks_pvalue,
                }
                for r in self.feature_results if r.is_drifted
            ],
        }


class DriftDetector:
    """
    Statistical drift detector for ML features.

    Uses Kolmogorov-Smirnov test to detect distribution changes
    between baseline (training) and current (inference) data.
    """

    def __init__(
        self,
        significance_level: float = 0.01,
        min_samples: int = 100,
        warning_threshold: float = 0.1,
        critical_threshold: float = 0.3
    ):
        """
        Initialize drift detector.

        Args:
            significance_level: P-value threshold for KS test
            min_samples: Minimum samples needed for detection
            warning_threshold: Ratio of drifted features for warning
            critical_threshold: Ratio of drifted features for critical alert
        """
        self.significance_level = significance_level
        self.min_samples = min_samples
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold

        # Baseline statistics (from training data)
        self.baseline_stats: Dict[str, Tuple[float, float]] = {}  # feature -> (mean, std)
        self.baseline_distributions: Dict[str, np.ndarray] = {}

    def fit_baseline(
        self,
        features: np.ndarray,
        feature_names: List[str]
    ) -> None:
        """
        Compute baseline statistics from training data.

        Args:
            features: (N, n_features) training feature matrix
            feature_names: List of feature names
        """
        for i, name in enumerate(feature_names):
            col = features[:, i]
            valid = np.isfinite(col)
            if valid.sum() > 0:
                self.baseline_stats[name] = (
                    np.mean(col[valid]),
                    np.std(col[valid])
                )
                self.baseline_distributions[name] = col[valid]

        logger.info(f"Fitted baseline on {len(feature_names)} features, {len(features)} samples")

    def detect(
        self,
        features: np.ndarray,
        feature_names: List[str],
        predictions: Optional[np.ndarray] = None
    ) -> DriftReport:
        """
        Detect drift in current data vs baseline.

        Args:
            features: (N, n_features) current feature matrix
            feature_names: List of feature names
            predictions: Optional prediction values to check

        Returns:
            DriftReport with detailed results
        """
        if len(features) < self.min_samples:
            logger.warning(f"Not enough samples for drift detection: {len(features)}")
            return DriftReport()

        report = DriftReport(n_features=len(feature_names))
        drifted_count = 0

        for i, name in enumerate(feature_names):
            if name not in self.baseline_distributions:
                continue

            col = features[:, i]
            valid = np.isfinite(col)

            if valid.sum() < self.min_samples:
                continue

            result = self._test_feature(
                name,
                self.baseline_distributions[name],
                col[valid]
            )
            report.feature_results.append(result)

            if result.is_drifted:
                drifted_count += 1

        report.n_drifted = drifted_count
        report.drift_ratio = drifted_count / report.n_features if report.n_features > 0 else 0

        # Check prediction drift
        if predictions is not None and 'predictions' in self.baseline_distributions:
            report.prediction_drift = self._test_feature(
                'predictions',
                self.baseline_distributions['predictions'],
                predictions
            )

        # Set alert level
        if report.drift_ratio >= self.critical_threshold:
            report.alert_level = 'critical'
        elif report.drift_ratio >= self.warning_threshold:
            report.alert_level = 'warning'
        else:
            report.alert_level = 'normal'

        return report

    def _test_feature(
        self,
        name: str,
        baseline: np.ndarray,
        current: np.ndarray
    ) -> DriftResult:
        """
        Test a single feature for drift using KS test.

        Args:
            name: Feature name
            baseline: Baseline distribution samples
            current: Current distribution samples

        Returns:
            DriftResult
        """
        # Compute statistics
        baseline_mean = np.mean(baseline)
        baseline_std = np.std(baseline)
        current_mean = np.mean(current)
        current_std = np.std(current)

        # Kolmogorov-Smirnov test
        ks_stat, ks_pvalue = stats.ks_2samp(baseline, current)

        # Determine if drifted
        is_drifted = ks_pvalue < self.significance_level

        # Severity based on effect size (mean shift in std units)
        if baseline_std > 0:
            effect_size = abs(current_mean - baseline_mean) / baseline_std
        else:
            effect_size = 0

        if not is_drifted:
            severity = 'none'
        elif effect_size < 0.5:
            severity = 'low'
        elif effect_size < 1.0:
            severity = 'medium'
        else:
            severity = 'high'

        return DriftResult(
            feature_name=name,
            baseline_mean=baseline_mean,
            current_mean=current_mean,
            baseline_std=baseline_std,
            current_std=current_std,
            ks_statistic=ks_stat,
            ks_pvalue=ks_pvalue,
            is_drifted=is_drifted,
            drift_severity=severity
        )

    def save_baseline(self, path: str) -> None:
        """
        Persist baseline statistics to file.

        Args:
            path: Path to save baseline (pickle format)
        """
        import pickle
        from pathlib import Path

        data = {
            'baseline_stats': self.baseline_stats,
            'baseline_distributions': {
                k: v.tolist() for k, v in self.baseline_distributions.items()
            },
            'significance_level': self.significance_level,
            'min_samples': self.min_samples,
            'warning_threshold': self.warning_threshold,
            'critical_threshold': self.critical_threshold,
            'saved_at': datetime.utcnow().isoformat(),
        }

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'wb') as f:
            pickle.dump(data, f)

        logger.info(f"Saved drift baseline to {path} ({len(self.baseline_stats)} features)")

    @classmethod
    def load_baseline(cls, path: str) -> 'DriftDetector':
        """
        Load baseline from file.

        Args:
            path: Path to saved baseline

        Returns:
            DriftDetector with loaded baseline
        """
        import pickle
        from pathlib import Path

        if not Path(path).exists():
            raise FileNotFoundError(f"Drift baseline not found at {path}")

        with open(path, 'rb') as f:
            data = pickle.load(f)

        detector = cls(
            significance_level=data.get('significance_level', 0.01),
            min_samples=data.get('min_samples', 100),
            warning_threshold=data.get('warning_threshold', 0.1),
            critical_threshold=data.get('critical_threshold', 0.3),
        )

        detector.baseline_stats = data['baseline_stats']
        detector.baseline_distributions = {
            k: np.array(v) for k, v in data['baseline_distributions'].items()
        }

        logger.info(f"Loaded drift baseline from {path} ({len(detector.baseline_stats)} features)")
        return detector

    def log_report(self, report: DriftReport) -> None:
        """Log drift report summary."""
        logger.info("=" * 50)
        logger.info("Drift Detection Report")
        logger.info("=" * 50)
        logger.info(f"Features checked: {report.n_features}")
        logger.info(f"Features drifted: {report.n_drifted} ({report.drift_ratio:.1%})")
        logger.info(f"Alert level: {report.alert_level.upper()}")

        if report.n_drifted > 0:
            logger.info("\nDrifted features:")
            for r in report.feature_results:
                if r.is_drifted:
                    logger.info(f"  {r.feature_name}: {r.drift_severity} "
                               f"(KS={r.ks_statistic:.3f}, p={r.ks_pvalue:.4f})")

        if report.prediction_drift and report.prediction_drift.is_drifted:
            logger.warning("PREDICTION DRIFT DETECTED!")

        logger.info("=" * 50)

    def save_to_clickhouse(self, ch_client, report: DriftReport) -> None:
        """Save drift report to ClickHouse."""
        try:
            data = [
                [datetime.utcnow(), 'drift_ratio', report.drift_ratio, {}],
                [datetime.utcnow(), 'drift_alert_level',
                 {'normal': 0, 'warning': 1, 'critical': 2}[report.alert_level],
                 {}],
            ]

            for r in report.feature_results:
                if r.is_drifted:
                    data.append([
                        datetime.utcnow(),
                        f'drift_{r.feature_name}',
                        r.ks_statistic,
                        {'severity': r.drift_severity}
                    ])

            ch_client.insert(
                'aware_ingestion_metrics',
                data,
                column_names=['ts', 'metric_name', 'metric_value', 'tags']
            )

        except Exception as e:
            logger.error(f"Failed to save drift report: {e}")
