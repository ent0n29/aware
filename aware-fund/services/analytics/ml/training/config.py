"""
Training Configuration

Centralized configuration for model training hyperparameters.
"""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class TrainingConfig:
    """Configuration for training pipeline."""

    # Data
    min_trades: int = 10
    max_traders: int = 50000
    sequence_length: int = 100
    train_ratio: float = 0.7
    val_ratio: float = 0.15
    test_ratio: float = 0.15

    # Sequence model
    seq_input_dim: int = 5
    seq_hidden_dim: int = 128
    seq_embedding_dim: int = 64
    seq_num_layers: int = 2
    seq_dropout: float = 0.2
    seq_bidirectional: bool = True

    # Tabular model
    xgb_n_estimators: int = 200
    xgb_max_depth: int = 6
    xgb_learning_rate: float = 0.1
    xgb_subsample: float = 0.8
    use_lightgbm: bool = False

    # Ensemble
    ensemble_hidden_dim: int = 128
    ensemble_dropout: float = 0.2

    # Training
    batch_size: int = 64
    num_epochs: int = 50
    learning_rate: float = 1e-4
    weight_decay: float = 1e-5
    early_stopping_patience: int = 10
    gradient_clip: float = 1.0

    # Paths
    checkpoint_dir: str = "ml/checkpoints"
    model_name: str = "aware_ensemble"

    # Device
    device: str = "cpu"  # or "cuda" if available

    # Random seed
    seed: int = 42

    def get_checkpoint_path(self) -> Path:
        """Get full checkpoint path."""
        return Path(self.checkpoint_dir) / f"{self.model_name}.pt"

    @classmethod
    def from_dict(cls, config_dict: dict) -> 'TrainingConfig':
        """Create config from dictionary."""
        return cls(**{k: v for k, v in config_dict.items() if hasattr(cls, k)})
