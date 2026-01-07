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
    max_traders: int = 30000  # Start with 30K for faster iteration
    sequence_length: int = 100
    train_ratio: float = 0.80  # 80/10/10 split
    val_ratio: float = 0.10
    test_ratio: float = 0.10

    # Sequence model (LSTM)
    seq_input_dim: int = 5  # price, size, side, hour_sin, hour_cos
    seq_hidden_dim: int = 128
    seq_embedding_dim: int = 64
    seq_num_layers: int = 2
    seq_dropout: float = 0.3  # Increased for regularization
    seq_bidirectional: bool = True

    # Tabular model (XGBoost)
    xgb_n_estimators: int = 300  # More trees for better fit
    xgb_max_depth: int = 8  # Deeper trees
    xgb_learning_rate: float = 0.05  # Lower LR for stability
    xgb_subsample: float = 0.8
    xgb_colsample_bytree: float = 0.8  # Column subsampling
    xgb_reg_alpha: float = 0.1  # L1 regularization
    xgb_reg_lambda: float = 1.0  # L2 regularization
    use_lightgbm: bool = False

    # Ensemble fusion
    ensemble_hidden_dim: int = 128
    ensemble_dropout: float = 0.3

    # Training
    batch_size: int = 128  # Larger batch for GPU
    num_epochs: int = 100  # More epochs with early stopping
    learning_rate: float = 5e-5  # Lower LR for stability
    weight_decay: float = 1e-5
    early_stopping_patience: int = 15  # More patience
    gradient_clip: float = 1.0

    # Paths
    checkpoint_dir: str = "ml/checkpoints"
    model_name: str = "aware_ensemble"

    # Device - detect automatically
    device: str = "mps"  # Apple Silicon GPU (change to "cuda" for NVIDIA)

    # Random seed
    seed: int = 42

    def get_checkpoint_path(self) -> Path:
        """Get full checkpoint path."""
        return Path(self.checkpoint_dir) / f"{self.model_name}.pt"

    @classmethod
    def from_dict(cls, config_dict: dict) -> 'TrainingConfig':
        """Create config from dictionary."""
        return cls(**{k: v for k, v in config_dict.items() if hasattr(cls, k)})
