"""
Training Pipeline for AWARE ML Models

Provides:
- Data preparation from ClickHouse
- PyTorch Dataset and DataLoader
- Training loop with validation
- Model checkpointing
"""

from .config import TrainingConfig
from .dataset import AWAREDataset, create_dataloaders
from .trainer import AWARETrainer

__all__ = [
    'TrainingConfig',
    'AWAREDataset',
    'create_dataloaders',
    'AWARETrainer',
]
