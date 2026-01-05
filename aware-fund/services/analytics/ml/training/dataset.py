"""
PyTorch Dataset for AWARE Training

Handles:
- Loading features from ClickHouse
- Creating train/val/test splits (time-based)
- DataLoader creation with proper batching
"""

import logging
from typing import Optional, Tuple, List
import numpy as np

import torch
from torch.utils.data import Dataset, DataLoader

logger = logging.getLogger(__name__)


class AWAREDataset(Dataset):
    """
    PyTorch Dataset for trader features.

    Each sample contains:
    - Trade sequence for LSTM
    - Tabular features for XGBoost
    - Labels: tier, Sharpe ratio, score
    """

    TIER_MAP = {'BRONZE': 0, 'SILVER': 1, 'GOLD': 2, 'DIAMOND': 3}

    def __init__(
        self,
        sequences: np.ndarray,
        lengths: np.ndarray,
        tabular_features: np.ndarray,
        tier_labels: np.ndarray,
        sharpe_labels: np.ndarray,
        score_labels: Optional[np.ndarray] = None,
        augment: bool = False
    ):
        """
        Initialize dataset.

        Args:
            sequences: (N, seq_len, seq_dim) trade sequences
            lengths: (N,) actual sequence lengths
            tabular_features: (N, n_features) tabular features
            tier_labels: (N,) tier indices (0-3)
            sharpe_labels: (N,) Sharpe ratio targets
            score_labels: (N,) optional score targets (0-100)
            augment: Apply data augmentation
        """
        self.sequences = sequences
        self.lengths = lengths
        self.tabular_features = tabular_features
        self.tier_labels = tier_labels
        self.sharpe_labels = sharpe_labels
        self.score_labels = score_labels if score_labels is not None else np.zeros(len(tier_labels))
        self.augment = augment

        # Validate shapes
        assert len(sequences) == len(lengths) == len(tabular_features)
        assert len(tier_labels) == len(sharpe_labels) == len(sequences)

    def __len__(self) -> int:
        return len(self.sequences)

    def __getitem__(self, idx: int) -> dict:
        seq = self.sequences[idx].copy()
        length = self.lengths[idx]

        # Optional augmentation
        if self.augment and np.random.random() < 0.3:
            seq = self._augment_sequence(seq, length)

        return {
            'sequence': torch.tensor(seq, dtype=torch.float32),
            'length': torch.tensor(length, dtype=torch.long),
            'tabular': torch.tensor(self.tabular_features[idx], dtype=torch.float32),
            'tier': torch.tensor(self.tier_labels[idx], dtype=torch.long),
            'sharpe': torch.tensor(self.sharpe_labels[idx], dtype=torch.float32),
            'score': torch.tensor(self.score_labels[idx], dtype=torch.float32),
        }

    def _augment_sequence(self, seq: np.ndarray, length: int) -> np.ndarray:
        """Apply random augmentation to sequence."""
        if length < 10:
            return seq

        # Random crop
        if np.random.random() < 0.5:
            new_len = max(10, int(length * np.random.uniform(0.7, 1.0)))
            start = np.random.randint(0, length - new_len + 1)
            cropped = np.zeros_like(seq)
            cropped[:new_len] = seq[start:start + new_len]
            seq = cropped

        # Add noise to continuous features
        if np.random.random() < 0.3:
            noise = np.random.normal(0, 0.02, seq[:, :2].shape)
            seq[:, :2] += noise

        return seq


def create_dataloaders(
    ch_client,
    feature_extractor,
    config,
    use_cache: bool = True,
    cache_path: Optional[str] = None
) -> Tuple[DataLoader, DataLoader, DataLoader]:
    """
    Create train/val/test DataLoaders from ClickHouse data.

    Uses time-based splits to avoid data leakage.

    Args:
        ch_client: ClickHouse client
        feature_extractor: FeatureExtractor instance
        config: TrainingConfig
        use_cache: Use cached features if available
        cache_path: Path to cache file

    Returns:
        (train_loader, val_loader, test_loader)
    """
    logger.info("Creating dataloaders...")

    # Try loading from cache
    if use_cache and cache_path:
        try:
            data = np.load(cache_path, allow_pickle=True)
            logger.info(f"Loaded cached data from {cache_path}")
            return _create_loaders_from_arrays(data, config)
        except Exception as e:
            logger.info(f"Cache not found or invalid: {e}")

    # Fetch trader data
    logger.info("Fetching trader data from ClickHouse...")
    traders = _get_traders_for_training(ch_client, config.min_trades, config.max_traders)

    if len(traders) < 100:
        raise ValueError(f"Not enough traders for training: {len(traders)}")

    logger.info(f"Found {len(traders)} traders")

    # Extract features
    logger.info("Extracting features...")
    features_list = feature_extractor.extract_batch([t['proxy_address'] for t in traders])

    # Build arrays
    n = len(features_list)
    seq_len = config.sequence_length
    seq_dim = 5
    n_tabular = len(features_list[0].to_tabular_vector()) if features_list else 31

    sequences = np.zeros((n, seq_len, seq_dim), dtype=np.float32)
    lengths = np.zeros(n, dtype=np.int32)
    tabular = np.zeros((n, n_tabular), dtype=np.float32)
    tiers = np.zeros(n, dtype=np.int32)
    sharpes = np.zeros(n, dtype=np.float32)
    scores = np.zeros(n, dtype=np.float32)

    for i, feat in enumerate(features_list):
        if feat.trade_sequence is not None:
            seq_actual = min(feat.sequence_length, seq_len)
            sequences[i, :seq_actual] = feat.trade_sequence[:seq_actual]
            lengths[i] = seq_actual

        tabular[i] = feat.to_tabular_vector()

        # Get labels from traders data
        trader = traders[i]
        tiers[i] = _tier_to_idx(trader.get('tier', 'BRONZE'))
        sharpes[i] = feat.sharpe_ratio
        scores[i] = _compute_score(feat)

    # Time-based split (using first_trade_at or index order)
    logger.info("Creating time-based splits...")
    n_train = int(n * config.train_ratio)
    n_val = int(n * config.val_ratio)

    train_idx = np.arange(0, n_train)
    val_idx = np.arange(n_train, n_train + n_val)
    test_idx = np.arange(n_train + n_val, n)

    # Save to cache
    if cache_path:
        np.savez(
            cache_path,
            sequences=sequences,
            lengths=lengths,
            tabular=tabular,
            tiers=tiers,
            sharpes=sharpes,
            scores=scores,
            train_idx=train_idx,
            val_idx=val_idx,
            test_idx=test_idx
        )
        logger.info(f"Saved cache to {cache_path}")

    # Create datasets
    train_ds = AWAREDataset(
        sequences[train_idx], lengths[train_idx], tabular[train_idx],
        tiers[train_idx], sharpes[train_idx], scores[train_idx],
        augment=True
    )
    val_ds = AWAREDataset(
        sequences[val_idx], lengths[val_idx], tabular[val_idx],
        tiers[val_idx], sharpes[val_idx], scores[val_idx],
        augment=False
    )
    test_ds = AWAREDataset(
        sequences[test_idx], lengths[test_idx], tabular[test_idx],
        tiers[test_idx], sharpes[test_idx], scores[test_idx],
        augment=False
    )

    # Create loaders
    train_loader = DataLoader(
        train_ds, batch_size=config.batch_size, shuffle=True,
        num_workers=0, pin_memory=True
    )
    val_loader = DataLoader(
        val_ds, batch_size=config.batch_size, shuffle=False,
        num_workers=0, pin_memory=True
    )
    test_loader = DataLoader(
        test_ds, batch_size=config.batch_size, shuffle=False,
        num_workers=0, pin_memory=True
    )

    logger.info(f"Created loaders: train={len(train_ds)}, val={len(val_ds)}, test={len(test_ds)}")

    return train_loader, val_loader, test_loader


def _get_traders_for_training(ch_client, min_trades: int, max_traders: int) -> List[dict]:
    """Fetch traders with labels for training."""
    try:
        result = ch_client.query(f"""
            SELECT
                s.proxy_address,
                s.username,
                s.tier,
                s.total_score,
                p.total_pnl,
                p.first_trade_at
            FROM (SELECT * FROM aware_smart_money_scores FINAL) s
            LEFT JOIN (SELECT * FROM aware_trader_profiles FINAL) p
                ON s.proxy_address = p.proxy_address
            WHERE p.total_trades >= {min_trades}
            ORDER BY p.first_trade_at ASC
            LIMIT {max_traders}
        """)

        return [
            {
                'proxy_address': row[0],
                'username': row[1],
                'tier': row[2],
                'score': row[3],
                'total_pnl': row[4],
                'first_trade_at': row[5],
            }
            for row in result.result_rows
        ]
    except Exception as e:
        logger.error(f"Failed to fetch traders: {e}")
        return []


def _tier_to_idx(tier: str) -> int:
    """Convert tier string to index."""
    return {'BRONZE': 0, 'SILVER': 1, 'GOLD': 2, 'DIAMOND': 3}.get(tier, 0)


def _compute_score(feat) -> float:
    """Compute initial score from features (before ML training)."""
    # Simple heuristic based on current rule-based scoring
    score = 50.0

    if feat.sharpe_ratio > 2:
        score += 20
    elif feat.sharpe_ratio > 1:
        score += 10

    if feat.win_rate > 0.6:
        score += 15
    elif feat.win_rate > 0.5:
        score += 5

    if feat.max_drawdown > -0.1:
        score += 10

    return min(100, max(0, score))


def _create_loaders_from_arrays(data, config) -> Tuple[DataLoader, DataLoader, DataLoader]:
    """Create loaders from cached numpy arrays."""
    train_ds = AWAREDataset(
        data['sequences'][data['train_idx']],
        data['lengths'][data['train_idx']],
        data['tabular'][data['train_idx']],
        data['tiers'][data['train_idx']],
        data['sharpes'][data['train_idx']],
        data['scores'][data['train_idx']],
        augment=True
    )
    val_ds = AWAREDataset(
        data['sequences'][data['val_idx']],
        data['lengths'][data['val_idx']],
        data['tabular'][data['val_idx']],
        data['tiers'][data['val_idx']],
        data['sharpes'][data['val_idx']],
        data['scores'][data['val_idx']],
        augment=False
    )
    test_ds = AWAREDataset(
        data['sequences'][data['test_idx']],
        data['lengths'][data['test_idx']],
        data['tabular'][data['test_idx']],
        data['tiers'][data['test_idx']],
        data['sharpes'][data['test_idx']],
        data['scores'][data['test_idx']],
        augment=False
    )

    return (
        DataLoader(train_ds, batch_size=config.batch_size, shuffle=True),
        DataLoader(val_ds, batch_size=config.batch_size, shuffle=False),
        DataLoader(test_ds, batch_size=config.batch_size, shuffle=False),
    )
