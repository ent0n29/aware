"""
Training Pipeline for AWARE ML Models

Provides:
- Data preparation from ClickHouse
- PyTorch Dataset and DataLoader
- Training loop with validation
- Model checkpointing
"""

from .config import TrainingConfig
from .dataset import AWAREDataset, create_dataloaders, create_dataloaders_v2, extract_sequences_batch
from .label_generator import LabelGenerator, TraderLabel
from .trainer import AWARETrainer

__all__ = [
    'TrainingConfig',
    'AWAREDataset',
    'create_dataloaders',
    'create_dataloaders_v2',
    'extract_sequences_batch',
    'LabelGenerator',
    'TraderLabel',
    'AWARETrainer',
]
