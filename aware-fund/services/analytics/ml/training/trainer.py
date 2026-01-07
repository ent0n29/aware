"""
Training Loop for AWARE ML Models

Handles:
- Training sequence model (LSTM)
- Training tabular model (XGBoost)
- Training ensemble fusion layers
- Validation and early stopping
- Checkpointing
- Feature importance export
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Tuple
import numpy as np

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from ..models import TraderSequenceModel, TabularScorer, AWAREEnsemble
from .config import TrainingConfig

logger = logging.getLogger(__name__)


class AWARETrainer:
    """
    End-to-end trainer for AWARE ML models.

    Training proceeds in three stages:
    1. Train tabular model (XGBoost) on aggregated features
    2. Train sequence model (LSTM) on trade sequences
    3. Train ensemble fusion on combined predictions
    """

    def __init__(self, config: TrainingConfig):
        self.config = config
        self.device = torch.device(config.device)

        # Models
        self.sequence_model: Optional[TraderSequenceModel] = None
        self.tabular_scorer: Optional[TabularScorer] = None
        self.ensemble: Optional[AWAREEnsemble] = None

        # Training state
        self.best_val_loss = float('inf')
        self.patience_counter = 0

        # Metrics tracking for explainability
        self.n_traders = 0
        self.n_trades = 0
        self.best_tier_accuracy = 0.0
        self.best_sharpe_mae = float('inf')
        self.training_started_at: Optional[datetime] = None
        self.feature_names: Optional[list] = None

    def train(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader,
        test_loader: Optional[DataLoader] = None
    ) -> Dict:
        """
        Full training pipeline.

        Args:
            train_loader: Training data
            val_loader: Validation data
            test_loader: Test data (optional)

        Returns:
            Dict with training metrics
        """
        logger.info("=" * 60)
        logger.info("AWARE ML Training Pipeline")
        logger.info("=" * 60)

        self.training_started_at = datetime.utcnow()
        metrics = {}

        # Stage 1: Train tabular model
        logger.info("\nStage 1: Training Tabular Model (XGBoost)")
        logger.info("-" * 40)
        tabular_metrics = self._train_tabular(train_loader, val_loader)
        metrics['tabular'] = tabular_metrics
        self.best_tier_accuracy = tabular_metrics.get('val_accuracy', 0)
        self.best_sharpe_mae = tabular_metrics.get('val_sharpe_mae', float('inf'))
        logger.info(f"Tabular training complete: accuracy={tabular_metrics.get('val_accuracy', 0):.3f}")

        # Export feature importance after tabular training
        self._export_feature_importance()

        # Stage 2: Train sequence model
        logger.info("\nStage 2: Training Sequence Model (LSTM)")
        logger.info("-" * 40)
        seq_metrics = self._train_sequence(train_loader, val_loader)
        metrics['sequence'] = seq_metrics
        logger.info(f"Sequence training complete: val_loss={seq_metrics.get('best_val_loss', 0):.4f}")

        # Stage 3: Train ensemble
        logger.info("\nStage 3: Training Ensemble Fusion")
        logger.info("-" * 40)
        ensemble_metrics = self._train_ensemble(train_loader, val_loader)
        metrics['ensemble'] = ensemble_metrics
        logger.info(f"Ensemble training complete: val_loss={ensemble_metrics.get('best_val_loss', 0):.4f}")

        # Evaluate on test set
        if test_loader:
            logger.info("\nEvaluating on Test Set")
            logger.info("-" * 40)
            test_metrics = self._evaluate(test_loader)
            metrics['test'] = test_metrics
            logger.info(f"Test accuracy: {test_metrics.get('accuracy', 0):.3f}")
            logger.info(f"Test Sharpe MAE: {test_metrics.get('sharpe_mae', 0):.3f}")

        # Save final model and metadata
        self._save_checkpoint()
        self._save_training_metadata(metrics)

        logger.info("\n" + "=" * 60)
        logger.info("Training Complete!")
        logger.info("=" * 60)

        return metrics

    def _train_tabular(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader
    ) -> Dict:
        """Train XGBoost model on tabular features."""
        # Collect all training data
        X_train, y_tier_train, y_sharpe_train = [], [], []
        X_val, y_tier_val, y_sharpe_val = [], [], []

        for batch in train_loader:
            X_train.append(batch['tabular'].numpy())
            y_tier_train.append(batch['tier'].numpy())
            y_sharpe_train.append(batch['sharpe'].numpy())

        for batch in val_loader:
            X_val.append(batch['tabular'].numpy())
            y_tier_val.append(batch['tier'].numpy())
            y_sharpe_val.append(batch['sharpe'].numpy())

        X_train = np.concatenate(X_train)
        y_tier_train = np.concatenate(y_tier_train)
        y_sharpe_train = np.concatenate(y_sharpe_train)
        X_val = np.concatenate(X_val)
        y_tier_val = np.concatenate(y_tier_val)
        y_sharpe_val = np.concatenate(y_sharpe_val)

        # Track training stats
        self.n_traders = len(X_train) + len(X_val)

        # Store training features for drift baseline
        self._train_features = X_train

        # Train XGBoost
        self.tabular_scorer = TabularScorer(
            use_lightgbm=self.config.use_lightgbm,
            n_estimators=self.config.xgb_n_estimators,
            max_depth=self.config.xgb_max_depth,
            learning_rate=self.config.xgb_learning_rate,
            subsample=self.config.xgb_subsample,
        )

        train_metrics = self.tabular_scorer.fit(
            X_train, y_tier_train, y_sharpe_train,
            eval_set=(X_val, y_tier_val, y_sharpe_val)
        )

        # Validation metrics
        tier_probs, tier_pred, sharpe_pred = self.tabular_scorer.predict(X_val)
        val_accuracy = (tier_pred == y_tier_val).mean()
        val_sharpe_mae = np.mean(np.abs(sharpe_pred - y_sharpe_val))

        return {
            **train_metrics,
            'val_accuracy': val_accuracy,
            'val_sharpe_mae': val_sharpe_mae,
        }

    def _train_sequence(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader
    ) -> Dict:
        """Train LSTM sequence model."""
        self.sequence_model = TraderSequenceModel(
            input_dim=self.config.seq_input_dim,
            hidden_dim=self.config.seq_hidden_dim,
            embedding_dim=self.config.seq_embedding_dim,
            num_layers=self.config.seq_num_layers,
            dropout=self.config.seq_dropout,
            bidirectional=self.config.seq_bidirectional,
        ).to(self.device)

        optimizer = torch.optim.AdamW(
            self.sequence_model.parameters(),
            lr=self.config.learning_rate,
            weight_decay=self.config.weight_decay
        )

        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', factor=0.5, patience=5
        )

        criterion = nn.CrossEntropyLoss()

        # Add classification head for standalone training
        classifier = nn.Linear(self.config.seq_embedding_dim, 4).to(self.device)

        best_val_loss = float('inf')
        patience = 0
        train_losses = []
        val_losses = []

        for epoch in range(self.config.num_epochs):
            # Training
            self.sequence_model.train()
            classifier.train()
            epoch_loss = 0
            n_batches = 0

            for batch in train_loader:
                seq = batch['sequence'].to(self.device)
                lengths = batch['length'].to(self.device)
                tier = batch['tier'].to(self.device)

                optimizer.zero_grad()

                embedding = self.sequence_model(seq, lengths)
                logits = classifier(embedding)
                loss = criterion(logits, tier)

                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    list(self.sequence_model.parameters()) + list(classifier.parameters()),
                    self.config.gradient_clip
                )
                optimizer.step()

                epoch_loss += loss.item()
                n_batches += 1

            train_loss = epoch_loss / n_batches
            train_losses.append(train_loss)

            # Validation
            self.sequence_model.eval()
            classifier.eval()
            val_loss = 0
            val_correct = 0
            val_total = 0

            with torch.no_grad():
                for batch in val_loader:
                    seq = batch['sequence'].to(self.device)
                    lengths = batch['length'].to(self.device)
                    tier = batch['tier'].to(self.device)

                    embedding = self.sequence_model(seq, lengths)
                    logits = classifier(embedding)
                    loss = criterion(logits, tier)

                    val_loss += loss.item()
                    val_correct += (logits.argmax(1) == tier).sum().item()
                    val_total += len(tier)

            val_loss /= len(val_loader)
            val_losses.append(val_loss)
            val_acc = val_correct / val_total

            scheduler.step(val_loss)

            # Early stopping
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience = 0
            else:
                patience += 1
                if patience >= self.config.early_stopping_patience:
                    logger.info(f"Early stopping at epoch {epoch+1}")
                    break

            if (epoch + 1) % 10 == 0:
                logger.info(f"Epoch {epoch+1}: train_loss={train_loss:.4f}, val_loss={val_loss:.4f}, val_acc={val_acc:.3f}")

        return {
            'best_val_loss': best_val_loss,
            'train_losses': train_losses,
            'val_losses': val_losses,
        }

    def _train_ensemble(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader
    ) -> Dict:
        """Train ensemble fusion layers."""
        # Get number of tabular features
        sample_batch = next(iter(train_loader))
        n_features = sample_batch['tabular'].shape[1]

        self.ensemble = AWAREEnsemble(
            sequence_model=self.sequence_model,
            tabular_scorer=self.tabular_scorer,
            n_tabular_features=n_features,
            hidden_dim=self.config.ensemble_hidden_dim,
            dropout=self.config.ensemble_dropout,
        ).to(self.device)

        # Only train fusion layers
        trainable_params = []
        for name, param in self.ensemble.named_parameters():
            if 'sequence_model' not in name:  # Freeze LSTM
                trainable_params.append(param)

        optimizer = torch.optim.AdamW(
            trainable_params,
            lr=self.config.learning_rate,
            weight_decay=self.config.weight_decay
        )

        tier_criterion = nn.CrossEntropyLoss()
        sharpe_criterion = nn.SmoothL1Loss()
        score_criterion = nn.MSELoss()

        best_val_loss = float('inf')
        patience = 0

        for epoch in range(self.config.num_epochs):
            # Training
            self.ensemble.train()
            epoch_loss = 0
            n_batches = 0

            for batch in train_loader:
                seq = batch['sequence'].to(self.device)
                lengths = batch['length'].to(self.device)
                tabular = batch['tabular'].to(self.device)
                tier = batch['tier'].to(self.device)
                sharpe = batch['sharpe'].to(self.device)
                score = batch['score'].to(self.device)

                optimizer.zero_grad()

                tier_logits, sharpe_pred, score_pred = self.ensemble(seq, lengths, tabular)

                loss = tier_criterion(tier_logits, tier)
                loss += 0.5 * sharpe_criterion(sharpe_pred, sharpe)
                loss += 0.3 * score_criterion(score_pred, score)

                loss.backward()
                torch.nn.utils.clip_grad_norm_(trainable_params, self.config.gradient_clip)
                optimizer.step()

                epoch_loss += loss.item()
                n_batches += 1

            train_loss = epoch_loss / n_batches

            # Validation
            val_loss = self._compute_val_loss(val_loader)

            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience = 0
            else:
                patience += 1
                if patience >= self.config.early_stopping_patience:
                    logger.info(f"Early stopping at epoch {epoch+1}")
                    break

            if (epoch + 1) % 10 == 0:
                logger.info(f"Epoch {epoch+1}: train_loss={train_loss:.4f}, val_loss={val_loss:.4f}")

        return {'best_val_loss': best_val_loss}

    def _compute_val_loss(self, val_loader: DataLoader) -> float:
        """Compute validation loss."""
        self.ensemble.eval()
        total_loss = 0
        n_batches = 0

        tier_criterion = nn.CrossEntropyLoss()
        sharpe_criterion = nn.SmoothL1Loss()

        with torch.no_grad():
            for batch in val_loader:
                seq = batch['sequence'].to(self.device)
                lengths = batch['length'].to(self.device)
                tabular = batch['tabular'].to(self.device)
                tier = batch['tier'].to(self.device)
                sharpe = batch['sharpe'].to(self.device)

                tier_logits, sharpe_pred, _ = self.ensemble(seq, lengths, tabular)

                loss = tier_criterion(tier_logits, tier)
                loss += 0.5 * sharpe_criterion(sharpe_pred, sharpe)

                total_loss += loss.item()
                n_batches += 1

        return total_loss / n_batches

    def _evaluate(self, test_loader: DataLoader) -> Dict:
        """Evaluate on test set."""
        self.ensemble.eval()

        all_tier_pred = []
        all_tier_true = []
        all_sharpe_pred = []
        all_sharpe_true = []
        all_scores = []

        with torch.no_grad():
            for batch in test_loader:
                seq = batch['sequence'].to(self.device)
                lengths = batch['length'].to(self.device)
                tabular = batch['tabular'].to(self.device)

                tier_logits, sharpe_pred, scores = self.ensemble(seq, lengths, tabular)

                all_tier_pred.extend(tier_logits.argmax(1).cpu().numpy())
                all_tier_true.extend(batch['tier'].numpy())
                all_sharpe_pred.extend(sharpe_pred.cpu().numpy())
                all_sharpe_true.extend(batch['sharpe'].numpy())
                all_scores.extend(scores.cpu().numpy())

        tier_pred = np.array(all_tier_pred)
        tier_true = np.array(all_tier_true)
        sharpe_pred = np.array(all_sharpe_pred)
        sharpe_true = np.array(all_sharpe_true)

        return {
            'accuracy': (tier_pred == tier_true).mean(),
            'sharpe_mae': np.mean(np.abs(sharpe_pred - sharpe_true)),
            'sharpe_rmse': np.sqrt(np.mean((sharpe_pred - sharpe_true) ** 2)),
            'avg_score': np.mean(all_scores),
        }

    def _save_checkpoint(self) -> None:
        """Save trained ensemble and drift baseline."""
        if self.ensemble is None:
            return

        checkpoint_path = self.config.get_checkpoint_path()
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

        self.ensemble.save(str(checkpoint_path))
        logger.info(f"Saved checkpoint to {checkpoint_path}")

        # Save drift baseline from collected training features
        if hasattr(self, '_train_features') and self._train_features is not None:
            try:
                from ..monitoring.drift import DriftDetector

                detector = DriftDetector()
                feature_names = self._get_feature_names()

                n_features = self._train_features.shape[1]
                detector.fit_baseline(self._train_features, feature_names[:n_features])

                baseline_path = checkpoint_path.parent / 'drift_baseline.pkl'
                detector.save_baseline(str(baseline_path))
                logger.info(f"Saved drift baseline to {baseline_path}")

            except Exception as e:
                logger.warning(f"Failed to save drift baseline: {e}")

    def _get_feature_names(self) -> list:
        """Get the list of feature names used in training."""
        return [
            'total_trades', 'win_rate', 'avg_trade_size', 'max_trade_size',
            'trade_frequency', 'avg_hold_hours', 'sharpe_ratio', 'sortino_ratio',
            'max_drawdown', 'profit_factor', 'avg_pnl', 'total_pnl',
            'unique_markets', 'market_concentration', 'active_days',
            'trades_per_day', 'morning_ratio', 'evening_ratio',
            'crypto_ratio', 'politics_ratio', 'sports_ratio',
            'avg_entry_odds', 'avg_exit_odds', 'maker_ratio',
            'price_improvement', 'execution_quality', 'slippage_avg',
            'streak_current', 'streak_max_win', 'streak_max_loss',
            'consecutive_wins', 'consecutive_losses', 'recovery_speed',
            'win_loss_ratio', 'risk_reward_ratio'
        ]

    def _export_feature_importance(self) -> None:
        """Export XGBoost feature importance to JSON file."""
        if self.tabular_scorer is None:
            return

        try:
            importance = self.tabular_scorer.get_feature_importance()
            if not importance:
                logger.warning("No feature importance available")
                return

            checkpoint_dir = self.config.get_checkpoint_path().parent
            checkpoint_dir.mkdir(parents=True, exist_ok=True)

            # Sort by importance
            sorted_importance = dict(
                sorted(importance.items(), key=lambda x: x[1], reverse=True)
            )

            export_data = {
                'importance_type': 'weight',
                'model_version': self.config.model_version,
                'n_features': len(sorted_importance),
                'generated_at': datetime.utcnow().isoformat(),
                'features': {
                    name: float(score) for name, score in sorted_importance.items()
                },
                'top_10': list(sorted_importance.keys())[:10]
            }

            importance_path = checkpoint_dir / 'feature_importance.json'
            with open(importance_path, 'w') as f:
                json.dump(export_data, f, indent=2)

            logger.info(f"Exported feature importance to {importance_path}")
            logger.info(f"Top 5 features: {list(sorted_importance.keys())[:5]}")

        except Exception as e:
            logger.warning(f"Failed to export feature importance: {e}")

    def _save_training_metadata(self, metrics: Dict) -> None:
        """Save training run metadata for tracking and reproducibility."""
        if self.training_started_at is None:
            return

        try:
            checkpoint_dir = self.config.get_checkpoint_path().parent
            completed_at = datetime.utcnow()
            duration = (completed_at - self.training_started_at).total_seconds()

            metadata = {
                'model_version': self.config.model_version,
                'started_at': self.training_started_at.isoformat(),
                'completed_at': completed_at.isoformat(),
                'duration_seconds': int(duration),
                'status': 'success',
                'n_traders': self.n_traders,
                'final_metrics': {
                    'tier_accuracy': float(self.best_tier_accuracy),
                    'sharpe_mae': float(self.best_sharpe_mae) if self.best_sharpe_mae != float('inf') else None,
                    'val_loss': float(self.best_val_loss) if self.best_val_loss != float('inf') else None,
                },
                'hyperparameters': {
                    'learning_rate': self.config.learning_rate,
                    'batch_size': self.config.batch_size,
                    'num_epochs': self.config.num_epochs,
                    'seq_hidden_dim': self.config.seq_hidden_dim,
                    'seq_embedding_dim': self.config.seq_embedding_dim,
                    'seq_num_layers': self.config.seq_num_layers,
                    'xgb_n_estimators': self.config.xgb_n_estimators,
                    'xgb_max_depth': self.config.xgb_max_depth,
                    'xgb_learning_rate': self.config.xgb_learning_rate,
                    'ensemble_hidden_dim': self.config.ensemble_hidden_dim,
                    'early_stopping_patience': self.config.early_stopping_patience,
                },
                'metrics_by_stage': {
                    'tabular': metrics.get('tabular', {}),
                    'sequence': metrics.get('sequence', {}),
                    'ensemble': metrics.get('ensemble', {}),
                    'test': metrics.get('test', {}),
                }
            }

            metadata_path = checkpoint_dir / 'training_metadata.json'
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)

            logger.info(f"Saved training metadata to {metadata_path}")

        except Exception as e:
            logger.warning(f"Failed to save training metadata: {e}")
