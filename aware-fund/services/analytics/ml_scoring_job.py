"""
ML-Based Smart Money Scoring Job

Replaces rule-based SmartMoneyScorer with trained ensemble model predictions.
Falls back to rule-based scoring if ML model is unavailable.

This is the production scoring pipeline that runs in run_all.py.
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
import numpy as np

import torch

from clickhouse_client import ClickHouseClient

logger = logging.getLogger(__name__)


@dataclass
class MLTraderScore:
    """ML-based trader score with additional metadata."""
    proxy_address: str
    username: str
    total_score: int         # 0-100 overall score
    tier: str                # BRONZE/SILVER/GOLD/DIAMOND
    tier_confidence: float   # Softmax probability for assigned tier
    predicted_sharpe: float  # Model's Sharpe prediction
    rank: int                # Global rank
    model_version: str       # For tracking/rollback


class MLScoringJob:
    """
    Smart Money Scoring using trained ML ensemble.

    Flow:
    1. Load trained ensemble model
    2. Fetch traders to score
    3. Extract features (batch)
    4. Run ensemble predictions
    5. Save to aware_smart_money_scores AND aware_ml_scores

    Falls back to rule-based scoring if model unavailable.
    """

    TIER_LABELS = ['BRONZE', 'SILVER', 'GOLD', 'DIAMOND']
    MODEL_VERSION = 'ensemble_v1'

    def __init__(
        self,
        ch_client: ClickHouseClient,
        model_path: str = "ml/checkpoints/aware_ensemble.pt",
        device: str = "cpu"
    ):
        """
        Initialize ML scoring job.

        Args:
            ch_client: ClickHouse client
            model_path: Path to trained ensemble checkpoint
            device: Device for inference (cpu/cuda/mps)
        """
        self.ch_client = ch_client
        self.device = device
        self.ensemble = None
        self.feature_extractor = None
        self.model_path = model_path

        # Try to load model
        self._load_model()

    def _load_model(self) -> bool:
        """Load trained ensemble model."""
        path = Path(self.model_path)
        if not path.exists():
            logger.warning(f"ML model not found at {self.model_path}")
            return False

        try:
            from ml.models.ensemble import AWAREEnsemble
            self.ensemble = AWAREEnsemble.load(str(path), device=self.device)
            self.ensemble.eval()
            logger.info(f"Loaded ML ensemble from {self.model_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load ML model: {e}")
            return False

    def _init_feature_extractor(self):
        """Lazy-load feature extractor."""
        if self.feature_extractor is None:
            from ml.features import FeatureExtractor
            self.feature_extractor = FeatureExtractor(
                self.ch_client,
                sequence_length=100
            )

    def run(
        self,
        min_trades: int = 10,
        max_traders: int = 10000,
        force_rule_based: bool = False
    ) -> int:
        """
        Run ML scoring job.

        Args:
            min_trades: Minimum trades to be scored
            max_traders: Maximum traders to score
            force_rule_based: Force rule-based scoring even if ML available

        Returns:
            Number of traders scored
        """
        logger.info(f"Starting ML scoring job (max_traders={max_traders})...")

        # Get traders to score
        traders = self._get_traders(min_trades, max_traders)
        if not traders:
            logger.warning("No traders to score")
            return 0

        logger.info(f"Scoring {len(traders)} traders")

        # Choose scoring method
        if self.ensemble is not None and not force_rule_based:
            scores = self._score_with_ml(traders)
            method = "ml"
        else:
            logger.warning("Using rule-based fallback scoring")
            scores = self._score_rule_based(traders)
            method = "rule_based"

        if not scores:
            logger.warning("No scores generated")
            return 0

        # Save scores to both tables
        saved = self._save_scores(scores, method)

        logger.info(f"Scored {saved} traders using {method}")
        return saved

    def _get_traders(self, min_trades: int, max_traders: int) -> List[Dict]:
        """Fetch traders eligible for scoring."""
        query = f"""
            SELECT
                proxy_address,
                username,
                total_trades,
                first_trade_at
            FROM polybot.aware_trader_profiles FINAL
            WHERE total_trades >= {min_trades}
            ORDER BY first_trade_at ASC
            LIMIT {max_traders}
        """

        try:
            result = self.ch_client.query(query)
            return [
                {
                    'proxy_address': row[0],
                    'username': row[1] or '',
                    'total_trades': row[2],
                    'first_trade_at': row[3]
                }
                for row in result.result_rows
            ]
        except Exception as e:
            logger.error(f"Failed to fetch traders: {e}")
            return []

    def _score_with_ml(self, traders: List[Dict]) -> List[MLTraderScore]:
        """Score traders using trained ML ensemble."""
        self._init_feature_extractor()

        addresses = [t['proxy_address'] for t in traders]

        # Extract features (batch)
        logger.info("Extracting features...")
        features_list = self.feature_extractor.extract_batch(addresses)

        # Extract sequences (batch)
        logger.info("Extracting sequences...")
        from ml.training.dataset import extract_sequences_batch
        sequences, lengths = extract_sequences_batch(
            self.ch_client, addresses, sequence_length=100
        )

        # Build tabular features array
        n = len(addresses)
        n_tabular = len(features_list[0].to_tabular_vector()) if features_list else 35
        tabular = np.zeros((n, n_tabular), dtype=np.float32)

        for i, feat in enumerate(features_list):
            if feat is not None:
                tabular[i] = feat.to_tabular_vector()

        # Convert to tensors
        sequences_t = torch.tensor(sequences, dtype=torch.float32)
        lengths_t = torch.tensor(lengths, dtype=torch.long)
        tabular_t = torch.tensor(tabular, dtype=torch.float32)

        # Run inference
        logger.info("Running ML inference...")
        with torch.no_grad():
            predictions = self.ensemble.predict(
                sequences_t, lengths_t, tabular_t,
                device=self.device
            )

        # Convert predictions to scores
        scores = []
        for i, trader in enumerate(traders):
            tier_idx = int(predictions['tier_pred'][i])
            tier_probs = predictions['tier_probs'][i]
            ml_score = float(predictions['score'][i])
            sharpe_pred = float(predictions['sharpe_pred'][i])

            # Clamp score to 0-100
            ml_score = max(0, min(100, ml_score))

            scores.append(MLTraderScore(
                proxy_address=trader['proxy_address'],
                username=trader['username'],
                total_score=int(round(ml_score)),
                tier=self.TIER_LABELS[tier_idx],
                tier_confidence=float(tier_probs[tier_idx]),
                predicted_sharpe=sharpe_pred,
                rank=0,  # Set after sorting
                model_version=self.MODEL_VERSION
            ))

        # Sort and assign ranks
        scores.sort(key=lambda s: s.total_score, reverse=True)
        for i, score in enumerate(scores):
            score.rank = i + 1

        return scores

    def _score_rule_based(self, traders: List[Dict]) -> List[MLTraderScore]:
        """Fallback to rule-based scoring."""
        try:
            from scoring_job import ScoringJob

            # Run the original scoring job
            job = ScoringJob(self.ch_client)
            job.run(min_trades=10, max_traders=len(traders))

            # Fetch results and convert to MLTraderScore format
            result = self.ch_client.query("""
                SELECT
                    proxy_address, username, total_score, tier, rank
                FROM polybot.aware_smart_money_scores FINAL
                ORDER BY rank ASC
                LIMIT 10000
            """)

            return [
                MLTraderScore(
                    proxy_address=row[0],
                    username=row[1] or '',
                    total_score=int(row[2] or 50),
                    tier=row[3] or 'BRONZE',
                    tier_confidence=0.5,  # No confidence from rule-based
                    predicted_sharpe=0.0,
                    rank=int(row[4] or 0),
                    model_version='rule_based'
                )
                for row in result.result_rows
            ]

        except Exception as e:
            logger.error(f"Rule-based scoring failed: {e}")
            return []

    def _save_scores(self, scores: List[MLTraderScore], method: str) -> int:
        """
        Save scores to ClickHouse tables.

        Saves to:
        - aware_smart_money_scores: For API compatibility
        - aware_ml_scores: For MLEdgeStrategy consumption
        """
        if not scores:
            return 0

        now = datetime.utcnow()

        # Save to aware_smart_money_scores (API compatibility)
        try:
            smart_money_records = [
                (
                    s.proxy_address,
                    s.username,
                    s.total_score,
                    s.tier,
                    0.0,  # profitability_score (not available from ML)
                    0.0,  # risk_adjusted_score
                    0.0,  # consistency_score
                    0.0,  # track_record_score
                    '',   # strategy_type
                    s.tier_confidence,  # strategy_confidence
                    s.rank,
                    0,    # rank_change (not tracked in ML)
                    now,
                    s.model_version,
                )
                for s in scores
            ]

            self.ch_client.client.insert(
                'polybot.aware_smart_money_scores',
                smart_money_records,
                column_names=[
                    'proxy_address', 'username', 'total_score', 'tier',
                    'profitability_score', 'risk_adjusted_score',
                    'consistency_score', 'track_record_score',
                    'strategy_type', 'strategy_confidence', 'rank', 'rank_change',
                    'calculated_at', 'model_version'
                ]
            )
            logger.info(f"Saved {len(scores)} scores to aware_smart_money_scores")

        except Exception as e:
            logger.error(f"Failed to save to aware_smart_money_scores: {e}")

        # Save to aware_ml_scores (for MLEdgeStrategy.java)
        try:
            ml_records = [
                (
                    s.proxy_address,
                    s.username,
                    float(s.total_score),  # ml_score
                    s.tier,                # ml_tier
                    s.tier_confidence,     # tier_confidence
                    s.predicted_sharpe,    # predicted_sharpe_30d
                    0.0,                   # sharpe_ratio (filled by enrichment)
                    0.0,                   # win_rate
                    0.0,                   # max_drawdown
                    0.0,                   # maker_ratio
                    0.0,                   # avg_hold_hours
                    s.rank,                # rank
                    s.model_version,       # model_version
                    now                    # calculated_at
                )
                for s in scores
            ]

            self.ch_client.client.insert(
                'polybot.aware_ml_scores',
                ml_records,
                column_names=[
                    'proxy_address', 'username', 'ml_score', 'ml_tier',
                    'tier_confidence', 'predicted_sharpe_30d', 'sharpe_ratio',
                    'win_rate', 'max_drawdown', 'maker_ratio', 'avg_hold_hours',
                    'rank', 'model_version', 'calculated_at'
                ]
            )
            logger.info(f"Saved {len(scores)} scores to aware_ml_scores")

        except Exception as e:
            logger.error(f"Failed to save to aware_ml_scores: {e}")

        return len(scores)


def run_ml_scoring():
    """
    Main entry point for ML scoring.

    Called by run_all.py or standalone.
    """
    ch_host = os.getenv('CLICKHOUSE_HOST', 'localhost')
    ch_port = int(os.getenv('CLICKHOUSE_PORT', '8123'))

    logger.info("Starting ML scoring job...")

    from clickhouse_client import ClickHouseClient
    client = ClickHouseClient()

    # Determine device
    device = 'cpu'
    if torch.cuda.is_available():
        device = 'cuda'
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        device = 'mps'

    job = MLScoringJob(
        client,
        model_path="ml/checkpoints/aware_ensemble.pt",
        device=device
    )

    scored = job.run(min_trades=10, max_traders=10000)

    logger.info(f"ML scoring complete: {scored} traders scored")
    return scored


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    run_ml_scoring()
