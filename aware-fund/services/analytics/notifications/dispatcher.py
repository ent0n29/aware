"""
AWARE Analytics - Alert Dispatcher

Unified dispatcher that routes insider alerts to configured notification channels.

Features:
- Deduplication: Prevents sending the same alert twice
- Severity filtering: Only send alerts above configured threshold
- Multi-channel support: Extensible for Telegram, email, etc.

Usage:
    dispatcher = AlertDispatcher()
    await dispatcher.dispatch(alert)

Environment Variables:
    DISCORD_WEBHOOK_URL - Discord webhook for notifications
    ALERT_MIN_SEVERITY - Minimum severity to send (LOW, MEDIUM, HIGH, CRITICAL)
    ALERT_DEDUP_TTL_HOURS - Hours to remember sent alerts (default: 24)
"""

import os
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from collections import OrderedDict

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from insider_detector import InsiderAlert, AlertSeverity

from .discord import DiscordNotifier

logger = logging.getLogger(__name__)


# Severity ordering for comparison
SEVERITY_ORDER = {
    AlertSeverity.LOW: 0,
    AlertSeverity.MEDIUM: 1,
    AlertSeverity.HIGH: 2,
    AlertSeverity.CRITICAL: 3,
}


class AlertDispatcher:
    """
    Dispatch alerts to all configured notification channels.

    Handles:
    - Deduplication (same alert won't be sent twice within TTL)
    - Severity filtering (only send alerts above threshold)
    - Rate limiting (don't flood channels)
    """

    def __init__(
        self,
        min_severity: Optional[str] = None,
        dedup_ttl_hours: Optional[int] = None,
    ):
        """
        Initialize dispatcher with configured channels.

        Args:
            min_severity: Minimum severity to dispatch (default: env var or "LOW")
            dedup_ttl_hours: Hours to remember sent alerts (default: 24)
        """
        # Initialize notification channels
        self.discord = DiscordNotifier() if os.getenv("DISCORD_WEBHOOK_URL") else None

        # Future: Add Telegram support
        # self.telegram = TelegramNotifier() if os.getenv("TELEGRAM_BOT_TOKEN") else None

        # Severity filter
        severity_str = min_severity or os.getenv("ALERT_MIN_SEVERITY", "LOW")
        try:
            self.min_severity = AlertSeverity[severity_str.upper()]
        except KeyError:
            logger.warning(f"Invalid severity '{severity_str}', using LOW")
            self.min_severity = AlertSeverity.LOW

        # Deduplication cache (LRU with TTL)
        self.dedup_ttl = timedelta(hours=dedup_ttl_hours or int(os.getenv("ALERT_DEDUP_TTL_HOURS", "24")))
        self._sent_alerts: OrderedDict[str, datetime] = OrderedDict()
        self._max_cache_size = 10000  # Max alerts to remember

        # Statistics
        self.alerts_dispatched = 0
        self.alerts_filtered = 0
        self.alerts_deduplicated = 0

        logger.info(f"AlertDispatcher initialized: min_severity={self.min_severity.value}, "
                   f"channels=[{'Discord' if self.discord else ''}, "
                   f"{'(more coming)' if not self.discord else ''}]")

    @property
    def has_channels(self) -> bool:
        """Check if any notification channel is configured."""
        return bool(self.discord and self.discord.is_configured)

    def _get_alert_key(self, alert: InsiderAlert) -> str:
        """
        Generate unique key for alert deduplication.

        Key is based on: signal_type + market_slug + direction + rounded_volume
        """
        # Round volume to nearest $1000 to avoid duplicates from minor volume changes
        volume_bucket = int(alert.total_volume_usd / 1000) * 1000

        key_data = f"{alert.signal_type.value}:{alert.market_slug}:{alert.direction}:{volume_bucket}"
        return hashlib.md5(key_data.encode()).hexdigest()[:16]

    def _is_duplicate(self, alert: InsiderAlert) -> bool:
        """
        Check if alert was already sent within TTL.

        Also cleans up expired entries from cache.
        """
        now = datetime.utcnow()

        # Clean up expired entries
        expired_keys = [
            key for key, sent_at in self._sent_alerts.items()
            if now - sent_at > self.dedup_ttl
        ]
        for key in expired_keys:
            del self._sent_alerts[key]

        # Trim cache if too large (LRU eviction)
        while len(self._sent_alerts) > self._max_cache_size:
            self._sent_alerts.popitem(last=False)

        # Check if this alert was sent
        alert_key = self._get_alert_key(alert)
        if alert_key in self._sent_alerts:
            return True

        return False

    def _mark_sent(self, alert: InsiderAlert) -> None:
        """Mark alert as sent in dedup cache."""
        alert_key = self._get_alert_key(alert)
        self._sent_alerts[alert_key] = datetime.utcnow()
        # Move to end (LRU behavior)
        self._sent_alerts.move_to_end(alert_key)

    def _meets_severity_threshold(self, alert: InsiderAlert) -> bool:
        """Check if alert meets minimum severity threshold."""
        alert_level = SEVERITY_ORDER.get(alert.severity, 0)
        min_level = SEVERITY_ORDER.get(self.min_severity, 0)
        return alert_level >= min_level

    async def dispatch(self, alert: InsiderAlert) -> bool:
        """
        Dispatch alert to all configured channels.

        Args:
            alert: The InsiderAlert to dispatch

        Returns:
            True if alert was sent to at least one channel
        """
        # Check severity threshold
        if not self._meets_severity_threshold(alert):
            logger.debug(f"Alert filtered (below {self.min_severity.value}): {alert}")
            self.alerts_filtered += 1
            return False

        # Check for duplicate
        if self._is_duplicate(alert):
            logger.debug(f"Alert deduplicated: {alert}")
            self.alerts_deduplicated += 1
            return False

        # Dispatch to channels
        sent = False

        if self.discord and self.discord.is_configured:
            if await self.discord.send_alert(alert):
                sent = True

        # Future: Add more channels
        # if self.telegram and self.telegram.is_configured:
        #     if await self.telegram.send_alert(alert):
        #         sent = True

        if sent:
            self._mark_sent(alert)
            self.alerts_dispatched += 1
            logger.info(f"Dispatched alert: {alert.signal_type.value} - {alert.market_slug}")

        return sent

    async def dispatch_batch(self, alerts: list[InsiderAlert]) -> int:
        """
        Dispatch multiple alerts.

        Args:
            alerts: List of alerts to dispatch

        Returns:
            Number of alerts successfully dispatched
        """
        count = 0
        for alert in alerts:
            if await self.dispatch(alert):
                count += 1
        return count

    def get_stats(self) -> dict:
        """Get dispatcher statistics."""
        return {
            "alerts_dispatched": self.alerts_dispatched,
            "alerts_filtered": self.alerts_filtered,
            "alerts_deduplicated": self.alerts_deduplicated,
            "cache_size": len(self._sent_alerts),
            "channels_active": int(bool(self.discord and self.discord.is_configured)),
        }


# Singleton instance for convenience
_dispatcher: Optional[AlertDispatcher] = None


def get_dispatcher() -> AlertDispatcher:
    """Get or create singleton AlertDispatcher instance."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = AlertDispatcher()
    return _dispatcher


async def dispatch_alert(alert: InsiderAlert) -> bool:
    """Convenience function to dispatch a single alert."""
    return await get_dispatcher().dispatch(alert)


async def dispatch_alerts(alerts: list[InsiderAlert]) -> int:
    """Convenience function to dispatch multiple alerts."""
    return await get_dispatcher().dispatch_batch(alerts)
