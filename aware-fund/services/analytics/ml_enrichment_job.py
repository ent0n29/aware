"""
AWARE Analytics - ML Enrichment Job

Runs unsupervised ML models to enrich trader data:
1. Strategy DNA Clustering - Groups traders into behavioral archetypes
2. Anomaly Detection - Identifies suspicious/unusual traders
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from clickhouse_client import ClickHouseClient
from ml.features.base import FeatureExtractor, TraderFeatures
from ml.models.clustering import StrategyDNAClustering, ClusterProfile
from ml.models.anomaly import TraderAnomalyDetector, AnomalyResult

logger = logging.getLogger(__name__)


@dataclass
class MLEnrichmentConfig:
    """Configuration for ML enrichment job."""
    n_clusters: int = 8
    anomaly_contamination: float = 0.01
    use_autoencoder: bool = True
    min_trades: int = 10
    max_traders: int = 10000
    model_dir: Path = Path("models")
    save_models: bool = True


class MLEnrichmentJob:
    """
    Enriches trader data with ML-derived classifications.

    Runs periodically to:
    - Cluster traders by Strategy DNA (K-means on 35 features)
    - Detect anomalous traders (Isolation Forest + Autoencoder)
    - Save results to ClickHouse for dashboard/API consumption
    """

    def __init__(self, ch_client: ClickHouseClient, config: Optional[MLEnrichmentConfig] = None):
        self.ch_client = ch_client
        self.config = config or MLEnrichmentConfig()
        self.feature_extractor = FeatureExtractor(ch_client)

        # Initialize models
        self.clustering = StrategyDNAClustering(n_clusters=self.config.n_clusters)
        self.anomaly_detector = TraderAnomalyDetector(
            contamination=self.config.anomaly_contamination,
            use_autoencoder=self.config.use_autoencoder,
        )

        # Model paths
        self.config.model_dir.mkdir(exist_ok=True)
        self.clustering_path = self.config.model_dir / "strategy_dna.pkl"
        self.anomaly_path = self.config.model_dir / "anomaly_detector.pkl"

    def run(self) -> dict:
        """
        Run full ML enrichment pipeline.

        Returns:
            Statistics about the run
        """
        logger.info("Starting ML enrichment job...")
        stats = {
            'traders_processed': 0,
            'clusters_created': 0,
            'anomalies_detected': 0,
            'features_extracted': 0,
        }

        # Get top traders by volume
        traders = self._get_trader_addresses()
        if not traders:
            logger.warning("No traders to enrich")
            return stats

        logger.info(f"Processing {len(traders)} traders")
        stats['traders_processed'] = len(traders)

        # Extract features
        features_list = self._extract_features(traders)
        if not features_list:
            logger.warning("No features extracted")
            return stats

        stats['features_extracted'] = len(features_list)
        logger.info(f"Extracted features for {len(features_list)} traders")

        # Convert to matrix
        feature_matrix = np.array([f.to_tabular_vector() for f in features_list])
        addresses = [f.proxy_address for f in features_list]
        usernames = [f.username for f in features_list]

        # Run clustering
        cluster_results = self._run_clustering(feature_matrix, addresses, usernames)
        stats['clusters_created'] = self.config.n_clusters

        # Run anomaly detection
        anomaly_results = self._run_anomaly_detection(feature_matrix, addresses)
        stats['anomalies_detected'] = sum(1 for r in anomaly_results if r.is_anomaly)

        # Save to ClickHouse
        self._save_results(cluster_results, anomaly_results)

        # Save models
        if self.config.save_models:
            self._save_models()

        logger.info(f"ML enrichment complete: {stats}")
        return stats

    def run_clustering_only(self) -> list[tuple[str, str, int]]:
        """Run only clustering. Returns (address, label, cluster_id) tuples."""
        traders = self._get_trader_addresses()
        features_list = self._extract_features(traders)

        if not features_list:
            return []

        feature_matrix = np.array([f.to_tabular_vector() for f in features_list])
        addresses = [f.proxy_address for f in features_list]
        usernames = [f.username for f in features_list]

        results = self._run_clustering(feature_matrix, addresses, usernames)
        return [(r['proxy_address'], r['strategy_cluster'], r['cluster_id']) for r in results]

    def run_anomaly_only(self) -> list[AnomalyResult]:
        """Run only anomaly detection."""
        traders = self._get_trader_addresses()
        features_list = self._extract_features(traders)

        if not features_list:
            return []

        feature_matrix = np.array([f.to_tabular_vector() for f in features_list])
        addresses = [f.proxy_address for f in features_list]

        return self._run_anomaly_detection(feature_matrix, addresses)

    def _get_trader_addresses(self) -> list[str]:
        """Get trader addresses to process."""
        result = self.ch_client.query(f"""
            SELECT proxy_address
            FROM polybot.aware_global_trades_dedup
            GROUP BY proxy_address
            HAVING count() >= {self.config.min_trades}
            ORDER BY sum(notional) DESC
            LIMIT {self.config.max_traders}
        """)

        return [row[0] for row in result.result_rows] if result.result_rows else []

    def _extract_features(self, addresses: list[str]) -> list[TraderFeatures]:
        """Extract features for all addresses."""
        # Use batch extraction for efficiency
        return self.feature_extractor.extract_batch(addresses)

    def _run_clustering(
        self,
        feature_matrix: np.ndarray,
        addresses: list[str],
        usernames: list[str],
    ) -> list[dict]:
        """Run Strategy DNA clustering."""
        logger.info("Running Strategy DNA clustering...")

        # Fit clustering
        labels = self.clustering.fit_predict(feature_matrix)

        # Build results
        results = []
        for i, (addr, username) in enumerate(zip(addresses, usernames)):
            cluster_id = int(labels[i])
            profile = self.clustering.get_cluster_profile(cluster_id)

            results.append({
                'proxy_address': addr,
                'username': username,
                'cluster_id': cluster_id,
                'strategy_cluster': profile.label if profile else f'CLUSTER_{cluster_id}',
                'cluster_description': profile.description if profile else '',
                'cluster_size': profile.size if profile else 0,
            })

        # Log cluster distribution
        logger.info("Cluster distribution:")
        for profile in self.clustering.get_all_profiles():
            logger.info(f"  {profile.label}: {profile.size} traders")

        return results

    def _run_anomaly_detection(
        self,
        feature_matrix: np.ndarray,
        addresses: list[str],
    ) -> list[AnomalyResult]:
        """Run anomaly detection."""
        logger.info("Running anomaly detection...")

        # Fit and detect
        self.anomaly_detector.fit(feature_matrix)
        results = self.anomaly_detector.detect(feature_matrix, addresses)

        # Log anomaly stats
        n_anomalies = sum(1 for r in results if r.is_anomaly)
        logger.info(f"Detected {n_anomalies} anomalies ({100*n_anomalies/len(results):.2f}%)")

        by_type = {}
        for r in results:
            by_type[r.anomaly_type] = by_type.get(r.anomaly_type, 0) + 1
        logger.info(f"Anomaly types: {by_type}")

        return results

    def _save_results(
        self,
        cluster_results: list[dict],
        anomaly_results: list[AnomalyResult],
    ) -> None:
        """Save ML results to ClickHouse."""
        timestamp = datetime.utcnow()

        # Build combined records
        anomaly_map = {r.proxy_address: r for r in anomaly_results}

        records = []
        for cluster in cluster_results:
            addr = cluster['proxy_address']
            anomaly = anomaly_map.get(addr)

            records.append({
                'proxy_address': addr,
                'username': cluster['username'],
                'cluster_id': cluster['cluster_id'],
                'strategy_cluster': cluster['strategy_cluster'],
                'cluster_description': cluster['cluster_description'],
                'is_anomaly': anomaly.is_anomaly if anomaly else False,
                'anomaly_score': anomaly.anomaly_score if anomaly else 0.0,
                'anomaly_type': anomaly.anomaly_type if anomaly else 'NORMAL',
                'updated_at': timestamp,
            })

        # Save to ClickHouse
        self._save_ml_enrichment(records)

    def _save_ml_enrichment(self, records: list[dict]) -> int:
        """Save ML enrichment results to ClickHouse."""
        if not records:
            return 0

        # Build INSERT statement
        columns = [
            'proxy_address', 'username', 'cluster_id', 'strategy_cluster',
            'cluster_description', 'is_anomaly', 'anomaly_score', 'anomaly_type',
            'updated_at'
        ]

        values = []
        for r in records:
            values.append((
                r['proxy_address'],
                r['username'],
                r['cluster_id'],
                r['strategy_cluster'],
                r['cluster_description'],
                1 if r['is_anomaly'] else 0,
                r['anomaly_score'],
                r['anomaly_type'],
                r['updated_at'],
            ))

        try:
            self.ch_client.client.insert(
                'polybot.aware_ml_enrichment',
                values,
                column_names=columns,
            )
            logger.info(f"Saved {len(records)} ML enrichment records")
            return len(records)
        except Exception as e:
            logger.error(f"Failed to save ML enrichment: {e}")
            return 0

    def _save_models(self) -> None:
        """Save trained models to disk."""
        try:
            self.clustering.save(self.clustering_path)
            self.anomaly_detector.save(self.anomaly_path)
            logger.info("Saved ML models to disk")
        except Exception as e:
            logger.error(f"Failed to save models: {e}")

    def load_models(self) -> bool:
        """Load pre-trained models from disk."""
        try:
            if self.clustering_path.exists():
                self.clustering = StrategyDNAClustering.load(self.clustering_path)
                logger.info("Loaded clustering model")

            if self.anomaly_path.exists():
                self.anomaly_detector = TraderAnomalyDetector.load(self.anomaly_path)
                logger.info("Loaded anomaly model")

            return True
        except Exception as e:
            logger.error(f"Failed to load models: {e}")
            return False


def run_ml_enrichment(
    clickhouse_host: str = "localhost",
    n_clusters: int = 8,
    max_traders: int = 10000,
) -> dict:
    """
    Convenience function to run ML enrichment.

    Args:
        clickhouse_host: ClickHouse host
        n_clusters: Number of strategy clusters
        max_traders: Maximum traders to process

    Returns:
        Run statistics
    """
    ch_client = ClickHouseClient(host=clickhouse_host)
    config = MLEnrichmentConfig(n_clusters=n_clusters, max_traders=max_traders)
    job = MLEnrichmentJob(ch_client, config)
    return job.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    host = os.getenv("CLICKHOUSE_HOST", "localhost")
    stats = run_ml_enrichment(clickhouse_host=host)
    print(f"ML Enrichment complete: {stats}")
