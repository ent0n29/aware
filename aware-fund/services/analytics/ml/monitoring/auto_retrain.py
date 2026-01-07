"""
Auto-Retraining Trigger for AWARE ML Models

Monitors model health and triggers retraining when:
1. Feature drift exceeds critical threshold (>30%)
2. Model age exceeds maximum days (30 days)
3. Sufficient new data is available (100k+ new trades)

Retraining can be triggered immediately or queued for background execution.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RetrainTrigger:
    """
    Evaluates whether model retraining is needed and triggers it.

    Retraining conditions:
    - Critical drift: >30% of features have drifted
    - Model staleness: >30 days since last training
    - New data: >100k new trades since last training

    Note: These thresholds are conservative for production.
    Adjust based on observed model degradation patterns.
    """

    drift_threshold: float = 0.3          # Critical drift level (30%)
    days_since_training: int = 30         # Max days between retrains
    min_new_trades: int = 100_000         # Min new trades to justify retrain
    queue_path: Path = field(default_factory=lambda: Path("ml/retrain_queue.json"))

    def should_retrain(
        self,
        drift_ratio: float,
        last_train_date: Optional[datetime],
        new_trade_count: int
    ) -> Tuple[bool, str]:
        """
        Evaluate whether retraining is needed.

        Args:
            drift_ratio: Fraction of features that have drifted (0-1)
            last_train_date: When the current model was trained
            new_trade_count: Number of new trades since last training

        Returns:
            Tuple of (should_retrain, reason_string)
        """
        reasons = []

        # Check drift
        if drift_ratio >= self.drift_threshold:
            reasons.append(f"Critical drift: {drift_ratio:.1%} features drifted")

        # Check model age
        if last_train_date:
            days_old = (datetime.utcnow() - last_train_date).days
            if days_old >= self.days_since_training:
                reasons.append(f"Model is {days_old} days old (max: {self.days_since_training})")

        # Check new data availability
        if new_trade_count >= self.min_new_trades:
            reasons.append(f"{new_trade_count:,} new trades available")

        should_retrain = len(reasons) > 0
        reason = "; ".join(reasons) if reasons else "No retraining needed"

        return should_retrain, reason

    def trigger_retrain(
        self,
        reason: str,
        priority: str = "normal",
        force: bool = False
    ) -> dict:
        """
        Queue a retraining job.

        Args:
            reason: Why retraining was triggered
            priority: "low", "normal", or "high"
            force: If True, bypass existing queue checks

        Returns:
            Dict with queue status
        """
        logger.info(f"Triggering model retrain: {reason}")

        # Load existing queue
        queue = []
        if self.queue_path.exists():
            try:
                queue = json.loads(self.queue_path.read_text())
            except json.JSONDecodeError:
                logger.warning("Corrupted retrain queue, resetting")
                queue = []

        # Check for pending retrains (avoid duplicate queuing)
        pending = [r for r in queue if r.get('status') == 'pending']
        if pending and not force:
            logger.info(f"Retrain already queued ({len(pending)} pending jobs)")
            return {
                'status': 'already_queued',
                'pending_count': len(pending)
            }

        # Add new retrain request
        request = {
            'id': datetime.utcnow().strftime('%Y%m%d_%H%M%S'),
            'requested_at': datetime.utcnow().isoformat(),
            'reason': reason,
            'priority': priority,
            'status': 'pending',
            'attempts': 0
        }
        queue.append(request)

        # Save queue
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        self.queue_path.write_text(json.dumps(queue, indent=2))

        logger.info(f"Retrain request queued: {request['id']}")
        return {
            'status': 'queued',
            'request_id': request['id'],
            'reason': reason
        }

    def get_pending_retrains(self) -> list:
        """Get list of pending retrain requests."""
        if not self.queue_path.exists():
            return []

        try:
            queue = json.loads(self.queue_path.read_text())
            return [r for r in queue if r.get('status') == 'pending']
        except Exception as e:
            logger.error(f"Failed to read retrain queue: {e}")
            return []

    def mark_retrain_complete(
        self,
        request_id: str,
        success: bool,
        metrics: Optional[dict] = None
    ) -> None:
        """
        Mark a retrain request as complete.

        Args:
            request_id: ID of the retrain request
            success: Whether retraining succeeded
            metrics: Optional training metrics to record
        """
        if not self.queue_path.exists():
            return

        try:
            queue = json.loads(self.queue_path.read_text())

            for request in queue:
                if request.get('id') == request_id:
                    request['status'] = 'success' if success else 'failed'
                    request['completed_at'] = datetime.utcnow().isoformat()
                    if metrics:
                        request['metrics'] = metrics
                    break

            self.queue_path.write_text(json.dumps(queue, indent=2))
            logger.info(f"Retrain {request_id} marked as {'success' if success else 'failed'}")

        except Exception as e:
            logger.error(f"Failed to update retrain queue: {e}")

    def cleanup_old_requests(self, days_to_keep: int = 30) -> int:
        """
        Remove old completed/failed requests from queue.

        Args:
            days_to_keep: Keep requests newer than this

        Returns:
            Number of requests removed
        """
        if not self.queue_path.exists():
            return 0

        try:
            queue = json.loads(self.queue_path.read_text())
            cutoff = datetime.utcnow().timestamp() - (days_to_keep * 86400)

            original_count = len(queue)
            queue = [
                r for r in queue
                if r.get('status') == 'pending' or
                datetime.fromisoformat(r.get('requested_at', '2000-01-01')).timestamp() > cutoff
            ]

            removed = original_count - len(queue)
            if removed > 0:
                self.queue_path.write_text(json.dumps(queue, indent=2))
                logger.info(f"Cleaned up {removed} old retrain requests")

            return removed

        except Exception as e:
            logger.error(f"Failed to cleanup retrain queue: {e}")
            return 0


def get_last_train_date(checkpoint_dir: Path = Path("ml/checkpoints")) -> Optional[datetime]:
    """
    Get the date of the last successful training.

    Reads from training_metadata.json if available.
    """
    metadata_path = checkpoint_dir / "training_metadata.json"

    if not metadata_path.exists():
        # Fall back to checkpoint file modification time
        checkpoint_path = checkpoint_dir / "aware_ensemble.pt"
        if checkpoint_path.exists():
            import os
            mtime = os.path.getmtime(checkpoint_path)
            return datetime.fromtimestamp(mtime)
        return None

    try:
        with open(metadata_path) as f:
            metadata = json.load(f)
        return datetime.fromisoformat(metadata['completed_at'])
    except Exception as e:
        logger.warning(f"Failed to read training metadata: {e}")
        return None


def get_new_trade_count_since(
    last_train_date: datetime,
    ch_client
) -> int:
    """
    Count new trades since the last training date.

    Args:
        last_train_date: When the model was last trained
        ch_client: ClickHouse client

    Returns:
        Number of new trades
    """
    if last_train_date is None:
        return 0

    try:
        result = ch_client.query(
            """
            SELECT count()
            FROM polybot.aware_global_trades_dedup
            WHERE ts > %(since)s
            """,
            parameters={'since': last_train_date}
        )
        return result.result_rows[0][0] if result.result_rows else 0
    except Exception as e:
        logger.warning(f"Failed to count new trades: {e}")
        return 0
