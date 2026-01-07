"""
AWARE ML Model Retraining Scheduler

Handles periodic model retraining with:
- Automated scheduling (monthly or on-demand)
- Model versioning and archiving
- Rollback capability on training failures
- ClickHouse persistence of training history

Usage:
    # Run scheduler daemon
    python -m ml.training.scheduler --daemon

    # Single retrain
    python -m ml.training.scheduler --retrain

    # Process queued retrains
    python -m ml.training.scheduler --process-queue
"""

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RetrainScheduler:
    """
    Manages periodic model retraining with archiving and rollback.

    Features:
    - Archives current model before retraining
    - Automatic rollback on training failure
    - Tracks training history in ClickHouse
    - Supports manual and scheduled retrains
    """

    checkpoint_dir: Path = field(default_factory=lambda: Path("ml/checkpoints"))
    archive_dir: Path = field(default_factory=lambda: Path("ml/checkpoints/archive"))
    queue_path: Path = field(default_factory=lambda: Path("ml/retrain_queue.json"))
    max_archives: int = 10  # Keep last N archived models

    def __post_init__(self):
        """Ensure directories exist."""
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def archive_current_model(self) -> Optional[str]:
        """
        Move current model to archive with timestamp.

        Returns:
            Archive path if successful, None if no model exists
        """
        current_model = self.checkpoint_dir / "aware_ensemble.pt"
        current_metadata = self.checkpoint_dir / "training_metadata.json"

        if not current_model.exists():
            logger.info("No current model to archive")
            return None

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        archive_model = self.archive_dir / f"aware_ensemble_{timestamp}.pt"
        archive_metadata = self.archive_dir / f"training_metadata_{timestamp}.json"

        # Copy (not move) to preserve current model during training
        shutil.copy2(current_model, archive_model)
        if current_metadata.exists():
            shutil.copy2(current_metadata, archive_metadata)

        logger.info(f"Archived model to {archive_model}")

        # Cleanup old archives (keep max_archives most recent)
        self._cleanup_old_archives()

        return str(archive_model)

    def _cleanup_old_archives(self) -> int:
        """Remove old archived models beyond max_archives limit."""
        archives = sorted(
            self.archive_dir.glob("aware_ensemble_*.pt"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        removed = 0
        for old_archive in archives[self.max_archives:]:
            try:
                old_archive.unlink()
                # Also remove corresponding metadata
                metadata = old_archive.with_name(
                    old_archive.name.replace("aware_ensemble_", "training_metadata_").replace(".pt", ".json")
                )
                if metadata.exists():
                    metadata.unlink()
                removed += 1
            except Exception as e:
                logger.warning(f"Failed to remove old archive {old_archive}: {e}")

        if removed > 0:
            logger.info(f"Cleaned up {removed} old model archives")

        return removed

    def rollback_model(self) -> bool:
        """
        Restore most recent archived model.

        Returns:
            True if rollback successful, False otherwise
        """
        archives = sorted(
            self.archive_dir.glob("aware_ensemble_*.pt"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        if not archives:
            logger.error("No archived models available for rollback")
            return False

        latest = archives[0]
        target = self.checkpoint_dir / "aware_ensemble.pt"

        try:
            shutil.copy2(latest, target)

            # Also restore metadata if available
            metadata = latest.with_name(
                latest.name.replace("aware_ensemble_", "training_metadata_").replace(".pt", ".json")
            )
            if metadata.exists():
                shutil.copy2(metadata, self.checkpoint_dir / "training_metadata.json")

            logger.info(f"Rolled back to {latest.name}")
            return True

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False

    def run_training(
        self,
        trigger_reason: str = "manual",
        max_traders: int = 50000,
        epochs: int = 100
    ) -> Dict:
        """
        Execute full training pipeline with safety measures.

        Args:
            trigger_reason: Why training was triggered
            max_traders: Max traders to train on
            epochs: Number of training epochs

        Returns:
            Dict with training results
        """
        logger.info(f"Starting model retrain (reason: {trigger_reason})")

        # Archive current model first
        archive_path = self.archive_current_model()

        started_at = datetime.utcnow()

        try:
            from ml.training.trainer import AWAREModelTrainer, TrainingConfig
            import torch

            # Detect device
            device = 'cpu'
            if torch.cuda.is_available():
                device = 'cuda'
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                device = 'mps'

            config = TrainingConfig(
                epochs=epochs,
                checkpoint_dir=str(self.checkpoint_dir),
                device=device,
                model_version=f"ensemble_v{started_at.strftime('%Y%m%d')}"
            )

            trainer = AWAREModelTrainer(config)
            metrics = trainer.train(max_traders=max_traders)

            completed_at = datetime.utcnow()
            duration = (completed_at - started_at).total_seconds()

            # Log to ClickHouse
            self._persist_training_run(
                started_at=started_at,
                completed_at=completed_at,
                status='success',
                trigger_reason=trigger_reason,
                metrics=metrics,
                config=config
            )

            logger.info(f"Training completed successfully in {duration:.0f}s")

            return {
                'status': 'success',
                'model_version': config.model_version,
                'duration_seconds': duration,
                'metrics': metrics,
                'archived_from': archive_path
            }

        except Exception as e:
            logger.error(f"Training failed: {e}")
            import traceback
            traceback.print_exc()

            # Rollback to previous model
            if archive_path:
                logger.info("Rolling back to previous model...")
                self.rollback_model()

            # Log failure
            self._persist_training_run(
                started_at=started_at,
                completed_at=datetime.utcnow(),
                status='failed',
                trigger_reason=trigger_reason,
                error=str(e)
            )

            return {
                'status': 'failed',
                'error': str(e),
                'rolled_back': archive_path is not None
            }

    def process_queue(self) -> List[Dict]:
        """
        Process pending retrain requests from queue.

        Returns:
            List of results for each processed request
        """
        if not self.queue_path.exists():
            return []

        try:
            queue = json.loads(self.queue_path.read_text())
        except json.JSONDecodeError:
            logger.warning("Corrupted retrain queue, clearing")
            self.queue_path.unlink()
            return []

        pending = [r for r in queue if r.get('status') == 'pending']
        if not pending:
            return []

        # Sort by priority (high first)
        priority_order = {'high': 0, 'normal': 1, 'low': 2}
        pending.sort(key=lambda r: priority_order.get(r.get('priority', 'normal'), 1))

        results = []

        # Process one at a time (no concurrent training)
        request = pending[0]
        request_id = request.get('id', 'unknown')

        logger.info(f"Processing retrain request {request_id}: {request.get('reason')}")

        # Mark as in-progress
        for r in queue:
            if r.get('id') == request_id:
                r['status'] = 'in_progress'
                r['started_at'] = datetime.utcnow().isoformat()
                break
        self.queue_path.write_text(json.dumps(queue, indent=2))

        # Run training
        result = self.run_training(
            trigger_reason=request.get('reason', 'queued'),
            max_traders=request.get('max_traders', 50000),
            epochs=request.get('epochs', 100)
        )

        # Update queue with result
        for r in queue:
            if r.get('id') == request_id:
                r['status'] = 'success' if result['status'] == 'success' else 'failed'
                r['completed_at'] = datetime.utcnow().isoformat()
                r['result'] = result
                break
        self.queue_path.write_text(json.dumps(queue, indent=2))

        results.append({
            'request_id': request_id,
            'result': result
        })

        return results

    def _persist_training_run(
        self,
        started_at: datetime,
        completed_at: datetime,
        status: str,
        trigger_reason: str,
        metrics: Optional[Dict] = None,
        config: Optional['TrainingConfig'] = None,
        error: Optional[str] = None
    ) -> None:
        """Persist training run to ClickHouse."""
        try:
            from clickhouse_client import ClickHouseClient
            client = ClickHouseClient()

            duration = int((completed_at - started_at).total_seconds())

            hyperparams = {}
            if config:
                hyperparams = {
                    'epochs': config.epochs,
                    'learning_rate': config.learning_rate,
                    'batch_size': config.batch_size,
                    'device': config.device
                }

            client.command("""
                INSERT INTO polybot.aware_ml_training_runs (
                    model_version, started_at, completed_at, duration_seconds,
                    status, tier_accuracy, sharpe_mae, val_loss,
                    trigger_reason, hyperparameters, notes
                ) VALUES (
                    %(version)s, %(started)s, %(completed)s, %(duration)s,
                    %(status)s, %(tier_acc)s, %(sharpe_mae)s, %(val_loss)s,
                    %(trigger)s, %(hyperparams)s, %(notes)s
                )
            """, parameters={
                'version': config.model_version if config else 'unknown',
                'started': started_at,
                'completed': completed_at,
                'duration': duration,
                'status': status,
                'tier_acc': metrics.get('tier_accuracy', 0.0) if metrics else 0.0,
                'sharpe_mae': metrics.get('sharpe_mae', 0.0) if metrics else 0.0,
                'val_loss': metrics.get('val_loss', 0.0) if metrics else 0.0,
                'trigger': trigger_reason,
                'hyperparams': json.dumps(hyperparams),
                'notes': error or ''
            })

            logger.info("Training run persisted to ClickHouse")

        except Exception as e:
            logger.warning(f"Failed to persist training run: {e}")

    def get_training_history(self, limit: int = 10) -> List[Dict]:
        """Get recent training runs from ClickHouse."""
        try:
            from clickhouse_client import ClickHouseClient
            client = ClickHouseClient()

            result = client.query(f"""
                SELECT
                    model_version, started_at, completed_at, duration_seconds,
                    status, tier_accuracy, sharpe_mae, trigger_reason
                FROM polybot.aware_ml_training_runs
                ORDER BY started_at DESC
                LIMIT {limit}
            """)

            return [
                {
                    'model_version': row[0],
                    'started_at': row[1].isoformat() if row[1] else None,
                    'completed_at': row[2].isoformat() if row[2] else None,
                    'duration_seconds': row[3],
                    'status': row[4],
                    'tier_accuracy': float(row[5]) if row[5] else 0.0,
                    'sharpe_mae': float(row[6]) if row[6] else 0.0,
                    'trigger_reason': row[7]
                }
                for row in result.result_rows
            ]

        except Exception as e:
            logger.warning(f"Failed to get training history: {e}")
            return []


def run_scheduled_retrain():
    """Run scheduled monthly retrain."""
    scheduler = RetrainScheduler()
    return scheduler.run_training(trigger_reason='scheduled')


def main():
    """CLI entry point."""
    import argparse

    logging.basicConfig(
        level=os.getenv('LOG_LEVEL', 'INFO'),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    parser = argparse.ArgumentParser(description='AWARE ML Retraining Scheduler')
    parser.add_argument('--daemon', action='store_true',
                       help='Run as daemon (monthly scheduled retrains)')
    parser.add_argument('--retrain', action='store_true',
                       help='Trigger immediate retrain')
    parser.add_argument('--process-queue', action='store_true',
                       help='Process pending retrain requests')
    parser.add_argument('--rollback', action='store_true',
                       help='Rollback to previous model')
    parser.add_argument('--history', action='store_true',
                       help='Show training history')
    args = parser.parse_args()

    scheduler = RetrainScheduler()

    if args.daemon:
        logger.info("Starting retraining scheduler daemon")
        logger.info("Scheduled: Monthly on 1st at 02:00 UTC")

        try:
            import schedule
        except ImportError:
            logger.error("schedule package required for daemon mode: pip install schedule")
            return

        # Schedule monthly retrain on 1st at 02:00
        schedule.every().day.at("02:00").do(
            lambda: scheduler.run_training(trigger_reason='scheduled')
            if datetime.utcnow().day == 1 else None
        )

        # Also check queue every hour
        schedule.every().hour.do(scheduler.process_queue)

        while True:
            schedule.run_pending()
            time.sleep(60)

    elif args.retrain:
        result = scheduler.run_training(trigger_reason='manual')
        print(json.dumps(result, indent=2, default=str))

    elif args.process_queue:
        results = scheduler.process_queue()
        print(json.dumps(results, indent=2, default=str))

    elif args.rollback:
        success = scheduler.rollback_model()
        print(f"Rollback {'succeeded' if success else 'failed'}")

    elif args.history:
        history = scheduler.get_training_history()
        print(json.dumps(history, indent=2, default=str))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
