#!/usr/bin/env python3
"""
AWARE ML Training Script

Usage:
    python -m ml.training.train

Environment Variables:
    CLICKHOUSE_HOST - ClickHouse host (default: localhost)
    CLICKHOUSE_PORT - ClickHouse port (default: 8123)
    CLICKHOUSE_DATABASE - Database name (default: polybot)
"""

import os
import sys
import logging
import argparse
from pathlib import Path

import numpy as np
import torch

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from clickhouse_client import ClickHouseClient
from ml.features import FeatureExtractor
from ml.training import TrainingConfig, AWARETrainer, create_dataloaders_v2

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('aware-training')


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Train AWARE ML models')

    # Data
    parser.add_argument('--min-trades', type=int, default=10,
                        help='Minimum trades per trader')
    parser.add_argument('--max-traders', type=int, default=50000,
                        help='Maximum traders to use')
    parser.add_argument('--sequence-length', type=int, default=100,
                        help='Trade sequence length')

    # Model
    parser.add_argument('--hidden-dim', type=int, default=128,
                        help='Hidden dimension')
    parser.add_argument('--embedding-dim', type=int, default=64,
                        help='Embedding dimension')
    parser.add_argument('--num-layers', type=int, default=2,
                        help='Number of LSTM layers')
    parser.add_argument('--dropout', type=float, default=0.2,
                        help='Dropout rate')

    # Training
    parser.add_argument('--batch-size', type=int, default=64,
                        help='Batch size')
    parser.add_argument('--epochs', type=int, default=50,
                        help='Number of epochs')
    parser.add_argument('--lr', type=float, default=1e-4,
                        help='Learning rate')
    parser.add_argument('--early-stopping', type=int, default=10,
                        help='Early stopping patience')

    # XGBoost
    parser.add_argument('--xgb-estimators', type=int, default=200,
                        help='XGBoost estimators')
    parser.add_argument('--xgb-depth', type=int, default=6,
                        help='XGBoost max depth')
    parser.add_argument('--use-lightgbm', action='store_true',
                        help='Use LightGBM instead of XGBoost')

    # Paths
    parser.add_argument('--checkpoint-dir', type=str, default='ml/checkpoints',
                        help='Checkpoint directory')
    parser.add_argument('--cache-path', type=str, default='ml/data_cache.npz',
                        help='Feature cache path')
    parser.add_argument('--no-cache', action='store_true',
                        help='Disable feature caching')

    # Device
    parser.add_argument('--device', type=str, default='auto',
                        help='Device (cpu, cuda, mps, auto)')

    parser.add_argument('--seed', type=int, default=42,
                        help='Random seed')

    return parser.parse_args()


def get_device(device_arg: str) -> str:
    """Determine best available device."""
    if device_arg != 'auto':
        return device_arg

    if torch.cuda.is_available():
        return 'cuda'
    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        return 'mps'
    else:
        return 'cpu'


def set_seed(seed: int):
    """Set random seeds for reproducibility."""
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def main():
    """Main training entry point."""
    args = parse_args()

    # Set device
    device = get_device(args.device)
    logger.info(f"Using device: {device}")

    # Set seed
    set_seed(args.seed)

    # Create config
    config = TrainingConfig(
        min_trades=args.min_trades,
        max_traders=args.max_traders,
        sequence_length=args.sequence_length,
        seq_hidden_dim=args.hidden_dim,
        seq_embedding_dim=args.embedding_dim,
        seq_num_layers=args.num_layers,
        seq_dropout=args.dropout,
        ensemble_hidden_dim=args.hidden_dim,
        ensemble_dropout=args.dropout,
        batch_size=args.batch_size,
        num_epochs=args.epochs,
        learning_rate=args.lr,
        early_stopping_patience=args.early_stopping,
        xgb_n_estimators=args.xgb_estimators,
        xgb_max_depth=args.xgb_depth,
        use_lightgbm=args.use_lightgbm,
        checkpoint_dir=args.checkpoint_dir,
        device=device,
        seed=args.seed,
    )

    # Initialize ClickHouse client
    ch_host = os.getenv('CLICKHOUSE_HOST', 'localhost')
    ch_port = int(os.getenv('CLICKHOUSE_PORT', '8123'))
    ch_database = os.getenv('CLICKHOUSE_DATABASE', 'polybot')

    logger.info(f"Connecting to ClickHouse at {ch_host}:{ch_port}/{ch_database}")

    ch_client = ClickHouseClient(
        host=ch_host,
        port=ch_port,
        database=ch_database
    )

    # Initialize feature extractor
    feature_extractor = FeatureExtractor(ch_client, sequence_length=config.sequence_length)

    # Create data loaders (using v2 with batch sequence extraction)
    cache_path = None if args.no_cache else args.cache_path
    train_loader, val_loader, test_loader = create_dataloaders_v2(
        ch_client,
        feature_extractor,
        config,
        use_cache=not args.no_cache,
        cache_path=cache_path
    )

    # Create trainer
    trainer = AWARETrainer(config)

    # Train
    metrics = trainer.train(train_loader, val_loader, test_loader)

    # Print summary
    print("\n" + "=" * 60)
    print("Training Summary")
    print("=" * 60)
    print(f"Tabular Model Accuracy: {metrics['tabular'].get('val_accuracy', 0):.3f}")
    print(f"Sequence Model Val Loss: {metrics['sequence'].get('best_val_loss', 0):.4f}")
    print(f"Ensemble Val Loss: {metrics['ensemble'].get('best_val_loss', 0):.4f}")
    if 'test' in metrics:
        print(f"\nTest Results:")
        print(f"  Tier Accuracy: {metrics['test'].get('accuracy', 0):.3f}")
        print(f"  Sharpe MAE: {metrics['test'].get('sharpe_mae', 0):.3f}")
        print(f"  Sharpe RMSE: {metrics['test'].get('sharpe_rmse', 0):.3f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
