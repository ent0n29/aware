"""
AWARE Analytics - Alert Dispatcher

Unified dispatcher that routes alerts to configured notification channels.
Supports reading undelivered alerts from ClickHouse and delivering them.

Features:
- Multi-channel delivery: Discord, Telegram, Webhooks
- Deduplication: Prevents sending the same alert twice
- Severity filtering: Only send alerts above configured threshold
- ClickHouse integration: Read and mark alerts as delivered
- Rate limiting: Configurable limits per channel

Usage:
    dispatcher = AlertDispatcher()

    # Dispatch a single alert
    await dispatcher.dispatch(insider_alert)
    await dispatcher.dispatch_general(general_alert)

    # Process undelivered alerts from ClickHouse
    await dispatcher.process_pending_alerts()

Environment Variables:
    DISCORD_WEBHOOK_URL - Discord webhook for notifications
    TELEGRAM_BOT_TOKEN - Telegram bot token
    TELEGRAM_CHAT_ID - Telegram chat/channel ID
    WEBHOOK_URL - Generic webhook endpoint
    ALERT_MIN_SEVERITY - Minimum severity to send (LOW, MEDIUM, HIGH, CRITICAL)
    ALERT_DEDUP_TTL_HOURS - Hours to remember sent alerts (default: 24)
"""

import os
import logging
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional, Any, Union
from collections import OrderedDict
from enum import Enum

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from insider_detector import InsiderAlert, AlertSeverity, InsiderSignalType
from alerts import Alert, AlertType, AlertPriority

from .discord import DiscordNotifier
from .telegram import TelegramNotifier
from .webhook import WebhookNotifier, MultiWebhookNotifier

logger = logging.getLogger(__name__)


# Severity ordering for InsiderAlert
INSIDER_SEVERITY_ORDER = {
    AlertSeverity.LOW: 0,
    AlertSeverity.MEDIUM: 1,
    AlertSeverity.HIGH: 2,
    AlertSeverity.CRITICAL: 3,
}

# Priority ordering for general Alert
PRIORITY_ORDER = {
    AlertPriority.LOW: 0,
    AlertPriority.MEDIUM: 1,
    AlertPriority.HIGH: 2,
    AlertPriority.URGENT: 3,
}


class NotificationChannel(Enum):
    """Available notification channels"""
    DISCORD = "discord"
    TELEGRAM = "telegram"
    WEBHOOK = "webhook"


class AlertDispatcher:
    """
    Dispatch alerts to all configured notification channels.

    Handles:
    - Multi-channel delivery (Discord, Telegram, Webhooks)
    - Deduplication (same alert won't be sent twice within TTL)
    - Severity/priority filtering (only send alerts above threshold)
    - Rate limiting (don't flood channels)
    - ClickHouse integration for persistence
    """

    def __init__(
        self,
        min_severity: Optional[str] = None,
        dedup_ttl_hours: Optional[int] = None,
        clickhouse_client=None,
    ):
        """
        Initialize dispatcher with configured channels.

        Args:
            min_severity: Minimum severity to dispatch (default: env var or "LOW")
            dedup_ttl_hours: Hours to remember sent alerts (default: 24)
            clickhouse_client: Optional ClickHouse client for persistence
        """
        self.ch = clickhouse_client

        # Initialize notification channels
        self.discord = self._init_discord()
        self.telegram = self._init_telegram()
        self.webhook = self._init_webhook()
        self.multi_webhook = self._init_multi_webhook()

        # Severity filter for InsiderAlerts
        severity_str = min_severity or os.getenv("ALERT_MIN_SEVERITY", "LOW")
        try:
            self.min_insider_severity = AlertSeverity[severity_str.upper()]
        except KeyError:
            logger.warning(f"Invalid severity '{severity_str}', using LOW")
            self.min_insider_severity = AlertSeverity.LOW

        # Map severity to priority for general alerts
        self.min_priority = {
            AlertSeverity.LOW: AlertPriority.LOW,
            AlertSeverity.MEDIUM: AlertPriority.MEDIUM,
            AlertSeverity.HIGH: AlertPriority.HIGH,
            AlertSeverity.CRITICAL: AlertPriority.URGENT,
        }.get(self.min_insider_severity, AlertPriority.LOW)

        # Deduplication cache (LRU with TTL)
        self.dedup_ttl = timedelta(hours=dedup_ttl_hours or int(os.getenv("ALERT_DEDUP_TTL_HOURS", "24")))
        self._sent_alerts: OrderedDict[str, datetime] = OrderedDict()
        self._max_cache_size = 10000

        # Statistics
        self.stats = {
            "insider_alerts_dispatched": 0,
            "general_alerts_dispatched": 0,
            "alerts_filtered": 0,
            "alerts_deduplicated": 0,
            "discord_sent": 0,
            "telegram_sent": 0,
            "webhook_sent": 0,
        }

        # Log configuration
        channels = []
        if self.discord and self.discord.is_configured:
            channels.append("Discord")
        if self.telegram and self.telegram.is_configured:
            channels.append("Telegram")
        if self.webhook and self.webhook.is_configured:
            channels.append("Webhook")
        if self.multi_webhook and self.multi_webhook.is_configured:
            channels.append(f"MultiWebhook({len(self.multi_webhook.notifiers)})")

        logger.info(f"AlertDispatcher initialized: min_severity={self.min_insider_severity.value}, "
                   f"channels=[{', '.join(channels) or 'none'}]")

    def _init_discord(self) -> Optional[DiscordNotifier]:
        """Initialize Discord notifier if configured."""
        if os.getenv("DISCORD_WEBHOOK_URL"):
            return DiscordNotifier()
        return None

    def _init_telegram(self) -> Optional[TelegramNotifier]:
        """Initialize Telegram notifier if configured."""
        if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
            return TelegramNotifier()
        return None

    def _init_webhook(self) -> Optional[WebhookNotifier]:
        """Initialize webhook notifier if configured."""
        if os.getenv("WEBHOOK_URL"):
            return WebhookNotifier()
        return None

    def _init_multi_webhook(self) -> Optional[MultiWebhookNotifier]:
        """Initialize multi-webhook notifier if configured."""
        if os.getenv("WEBHOOK_URLS"):
            notifier = MultiWebhookNotifier()
            if notifier.is_configured:
                return notifier
        return None

    @property
    def has_channels(self) -> bool:
        """Check if any notification channel is configured."""
        return any([
            self.discord and self.discord.is_configured,
            self.telegram and self.telegram.is_configured,
            self.webhook and self.webhook.is_configured,
            self.multi_webhook and self.multi_webhook.is_configured,
        ])

    @property
    def active_channels(self) -> list[str]:
        """Get list of active channel names."""
        channels = []
        if self.discord and self.discord.is_configured:
            channels.append("discord")
        if self.telegram and self.telegram.is_configured:
            channels.append("telegram")
        if self.webhook and self.webhook.is_configured:
            channels.append("webhook")
        if self.multi_webhook and self.multi_webhook.is_configured:
            channels.append("multi_webhook")
        return channels

    def _get_insider_alert_key(self, alert: InsiderAlert) -> str:
        """Generate unique key for insider alert deduplication."""
        volume_bucket = int(alert.total_volume_usd / 1000) * 1000
        key_data = f"insider:{alert.signal_type.value}:{alert.market_slug}:{alert.direction}:{volume_bucket}"
        return hashlib.md5(key_data.encode()).hexdigest()[:16]

    def _get_general_alert_key(self, alert: Alert) -> str:
        """Generate unique key for general alert deduplication."""
        key_data = f"general:{alert.alert_type.value}:{alert.username or ''}:{alert.market_slug or ''}"
        return hashlib.md5(key_data.encode()).hexdigest()[:16]

    def _is_duplicate(self, key: str) -> bool:
        """Check if alert was already sent within TTL."""
        now = datetime.utcnow()

        # Clean up expired entries
        expired_keys = [
            k for k, sent_at in self._sent_alerts.items()
            if now - sent_at > self.dedup_ttl
        ]
        for k in expired_keys:
            del self._sent_alerts[k]

        # Trim cache if too large (LRU eviction)
        while len(self._sent_alerts) > self._max_cache_size:
            self._sent_alerts.popitem(last=False)

        return key in self._sent_alerts

    def _mark_sent(self, key: str) -> None:
        """Mark alert as sent in dedup cache."""
        self._sent_alerts[key] = datetime.utcnow()
        self._sent_alerts.move_to_end(key)

    def _meets_insider_severity(self, alert: InsiderAlert) -> bool:
        """Check if insider alert meets minimum severity threshold."""
        alert_level = INSIDER_SEVERITY_ORDER.get(alert.severity, 0)
        min_level = INSIDER_SEVERITY_ORDER.get(self.min_insider_severity, 0)
        return alert_level >= min_level

    def _meets_general_priority(self, alert: Alert) -> bool:
        """Check if general alert meets minimum priority threshold."""
        alert_level = PRIORITY_ORDER.get(alert.priority, 0)
        min_level = PRIORITY_ORDER.get(self.min_priority, 0)
        return alert_level >= min_level

    async def dispatch(self, alert: InsiderAlert) -> bool:
        """
        Dispatch an insider alert to all configured channels.

        Args:
            alert: The InsiderAlert to dispatch

        Returns:
            True if alert was sent to at least one channel
        """
        # Check severity threshold
        if not self._meets_insider_severity(alert):
            logger.debug(f"Insider alert filtered (below {self.min_insider_severity.value})")
            self.stats["alerts_filtered"] += 1
            return False

        # Check for duplicate
        key = self._get_insider_alert_key(alert)
        if self._is_duplicate(key):
            logger.debug(f"Insider alert deduplicated: {alert.signal_type.value}")
            self.stats["alerts_deduplicated"] += 1
            return False

        # Dispatch to all channels
        sent = False
        sent_channels = []

        # Discord
        if self.discord and self.discord.is_configured:
            if await self.discord.send_alert(alert):
                sent = True
                sent_channels.append("discord")
                self.stats["discord_sent"] += 1

        # Telegram
        if self.telegram and self.telegram.is_configured:
            if await self.telegram.send_alert(alert):
                sent = True
                sent_channels.append("telegram")
                self.stats["telegram_sent"] += 1

        # Webhook
        if self.webhook and self.webhook.is_configured:
            if await self.webhook.send_alert(alert):
                sent = True
                sent_channels.append("webhook")
                self.stats["webhook_sent"] += 1

        # Multi-webhook
        if self.multi_webhook and self.multi_webhook.is_configured:
            results = await self.multi_webhook.send_alert(alert)
            if any(results.values()):
                sent = True
                sent_channels.append("multi_webhook")
                self.stats["webhook_sent"] += sum(results.values())

        if sent:
            self._mark_sent(key)
            self.stats["insider_alerts_dispatched"] += 1
            logger.info(f"Dispatched insider alert via [{', '.join(sent_channels)}]: "
                       f"{alert.signal_type.value} - {alert.market_slug}")

        return sent

    async def dispatch_general(self, alert: Alert) -> bool:
        """
        Dispatch a general alert (edge decay, consensus, etc.) to all channels.

        Args:
            alert: The Alert to dispatch

        Returns:
            True if alert was sent to at least one channel
        """
        # Check priority threshold
        if not self._meets_general_priority(alert):
            logger.debug(f"General alert filtered (below {self.min_priority.value})")
            self.stats["alerts_filtered"] += 1
            return False

        # Check for duplicate
        key = self._get_general_alert_key(alert)
        if self._is_duplicate(key):
            logger.debug(f"General alert deduplicated: {alert.alert_type.value}")
            self.stats["alerts_deduplicated"] += 1
            return False

        # Dispatch to channels
        sent = False
        sent_channels = []

        # Telegram (supports general alerts)
        if self.telegram and self.telegram.is_configured:
            if await self.telegram.send_general_alert(alert):
                sent = True
                sent_channels.append("telegram")
                self.stats["telegram_sent"] += 1

        # Webhook (supports general alerts)
        if self.webhook and self.webhook.is_configured:
            if await self.webhook.send_general_alert(alert):
                sent = True
                sent_channels.append("webhook")
                self.stats["webhook_sent"] += 1

        # Multi-webhook
        if self.multi_webhook and self.multi_webhook.is_configured:
            results = await self.multi_webhook.send_general_alert(alert)
            if any(results.values()):
                sent = True
                sent_channels.append("multi_webhook")
                self.stats["webhook_sent"] += sum(results.values())

        if sent:
            self._mark_sent(key)
            self.stats["general_alerts_dispatched"] += 1
            logger.info(f"Dispatched general alert via [{', '.join(sent_channels)}]: "
                       f"{alert.alert_type.value} - {alert.title}")

        return sent

    async def dispatch_batch(self, alerts: list[InsiderAlert]) -> int:
        """
        Dispatch multiple insider alerts.

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

    async def dispatch_general_batch(self, alerts: list[Alert]) -> int:
        """
        Dispatch multiple general alerts.

        Args:
            alerts: List of alerts to dispatch

        Returns:
            Number of alerts successfully dispatched
        """
        count = 0
        for alert in alerts:
            if await self.dispatch_general(alert):
                count += 1
        return count

    async def send_consensus_signal(
        self,
        market_slug: str,
        direction: str,
        strength: str,
        agreement_pct: float,
        num_traders: int,
        total_volume: float,
    ) -> bool:
        """
        Send a consensus signal notification directly.

        Args:
            market_slug: Market identifier
            direction: "YES" or "NO"
            strength: Consensus strength
            agreement_pct: Percentage agreement
            num_traders: Number of traders
            total_volume: Total smart money volume

        Returns:
            True if sent to at least one channel
        """
        sent = False

        if self.telegram and self.telegram.is_configured:
            if await self.telegram.send_consensus_signal(
                market_slug, direction, strength, agreement_pct, num_traders, total_volume
            ):
                sent = True
                self.stats["telegram_sent"] += 1

        if self.webhook and self.webhook.is_configured:
            if await self.webhook.send_consensus_signal(
                market_slug, direction, strength, agreement_pct, num_traders, total_volume
            ):
                sent = True
                self.stats["webhook_sent"] += 1

        return sent

    async def send_edge_decay_warning(
        self,
        username: str,
        decay_type: str,
        signal: str,
        historical_value: float,
        current_value: float,
        decline_pct: float,
        recommended_action: str,
    ) -> bool:
        """
        Send an edge decay warning notification directly.

        Args:
            username: Trader username
            decay_type: Type of decay
            signal: Signal strength
            historical_value: Historical metric
            current_value: Current metric
            decline_pct: Percentage decline
            recommended_action: Suggested action

        Returns:
            True if sent to at least one channel
        """
        sent = False

        if self.telegram and self.telegram.is_configured:
            if await self.telegram.send_edge_decay_warning(
                username, decay_type, signal, historical_value, current_value,
                decline_pct, recommended_action
            ):
                sent = True
                self.stats["telegram_sent"] += 1

        if self.webhook and self.webhook.is_configured:
            # Calculate decay score from decline percentage
            decay_score = min(100, decline_pct * 2)
            if await self.webhook.send_edge_decay_alert(
                username, decay_type, signal, decay_score, historical_value,
                current_value, decline_pct, recommended_action
            ):
                sent = True
                self.stats["webhook_sent"] += 1

        return sent

    async def send_hidden_gem_discovery(
        self,
        username: str,
        discovery_type: str,
        discovery_score: float,
        reason: str,
        sharpe_ratio: float,
        win_rate: float,
        total_pnl: float,
    ) -> bool:
        """
        Send a hidden gem discovery notification directly.

        Args:
            username: Trader username
            discovery_type: Type of discovery
            discovery_score: Discovery score
            reason: Discovery reason
            sharpe_ratio: Trader's Sharpe ratio
            win_rate: Trader's win rate
            total_pnl: Trader's total P&L

        Returns:
            True if sent to at least one channel
        """
        sent = False

        if self.telegram and self.telegram.is_configured:
            if await self.telegram.send_hidden_gem_discovery(
                username, discovery_type, discovery_score, reason,
                sharpe_ratio, win_rate, total_pnl
            ):
                sent = True
                self.stats["telegram_sent"] += 1

        if self.webhook and self.webhook.is_configured:
            metrics = {
                "sharpe_ratio": sharpe_ratio,
                "win_rate": win_rate,
                "total_pnl": total_pnl,
            }
            if await self.webhook.send_hidden_gem_alert(
                username, discovery_type, discovery_score, reason, metrics
            ):
                sent = True
                self.stats["webhook_sent"] += 1

        return sent

    async def process_pending_alerts(self, limit: int = 100) -> int:
        """
        Read undelivered alerts from ClickHouse and dispatch them.

        Args:
            limit: Maximum number of alerts to process

        Returns:
            Number of alerts processed
        """
        if not self.ch:
            logger.warning("No ClickHouse client configured for pending alerts")
            return 0

        try:
            # Query for undelivered alerts
            query = f"""
            SELECT
                id,
                alert_type,
                severity,
                source,
                username,
                market_slug,
                index_type,
                title,
                message,
                metadata,
                created_at
            FROM polybot.aware_alerts FINAL
            WHERE status = 'ACTIVE'
            ORDER BY created_at DESC
            LIMIT {limit}
            """

            result = self.ch.query(query)
            processed = 0

            for row in result.result_rows:
                try:
                    # Reconstruct Alert object
                    alert_id = row[0]
                    alert_type_str = row[1]
                    severity = row[2]
                    source = row[3]
                    username = row[4]
                    market_slug = row[5]
                    index_type = row[6]
                    title = row[7]
                    message = row[8]
                    metadata_str = row[9]
                    created_at = row[10]

                    # Parse metadata
                    try:
                        metadata = json.loads(metadata_str) if metadata_str else {}
                    except:
                        metadata = {}

                    # Map severity to priority
                    priority_map = {
                        "INFO": AlertPriority.LOW,
                        "WARNING": AlertPriority.MEDIUM,
                        "HIGH": AlertPriority.HIGH,
                        "CRITICAL": AlertPriority.URGENT,
                    }
                    priority = priority_map.get(severity, AlertPriority.MEDIUM)

                    # Map alert type
                    type_map = {
                        "POSITION_ENTRY": AlertType.POSITION_ENTRY,
                        "POSITION_EXIT": AlertType.POSITION_EXIT,
                        "LARGE_TRADE": AlertType.LARGE_TRADE,
                        "CONSENSUS": AlertType.CONSENSUS_FORMING,
                        "CONSENSUS_SHIFT": AlertType.CONSENSUS_SHIFT,
                        "INDEX_ADD": AlertType.INDEX_ADDITION,
                        "INDEX_REMOVE": AlertType.INDEX_REMOVAL,
                        "EDGE_DECAY": AlertType.EDGE_DECAY,
                        "RISING_STAR": AlertType.RISING_STAR,
                        "MARKET_ACTIVITY": AlertType.MARKET_ACTIVITY,
                    }
                    alert_type = type_map.get(alert_type_str, AlertType.MARKET_ACTIVITY)

                    # Create Alert object
                    alert = Alert(
                        alert_id=alert_id,
                        alert_type=alert_type,
                        priority=priority,
                        title=title,
                        message=message,
                        username=username,
                        market_slug=market_slug,
                        index_type=index_type,
                        data=metadata,
                        created_at=created_at,
                    )

                    # Dispatch
                    if await self.dispatch_general(alert):
                        # Mark as acknowledged in ClickHouse
                        await self._mark_alert_delivered(alert_id)
                        processed += 1

                except Exception as e:
                    logger.error(f"Error processing alert row: {e}")
                    continue

            logger.info(f"Processed {processed} pending alerts")
            return processed

        except Exception as e:
            logger.error(f"Error reading pending alerts: {e}")
            return 0

    async def _mark_alert_delivered(self, alert_id: str) -> None:
        """Mark an alert as delivered in ClickHouse."""
        if not self.ch:
            return

        try:
            # Use ALTER to update (ClickHouse style)
            # Note: This requires MergeTree table with ReplacingMergeTree
            # For now, we insert a new row with ACKNOWLEDGED status
            query = f"""
            INSERT INTO polybot.aware_alerts (id, status, acknowledged_at, _version)
            SELECT
                id,
                'ACKNOWLEDGED' as status,
                now64(3) as acknowledged_at,
                toUnixTimestamp64Milli(now64(3)) as _version
            FROM polybot.aware_alerts FINAL
            WHERE id = '{alert_id}'
            """
            self.ch.command(query)
        except Exception as e:
            logger.error(f"Error marking alert delivered: {e}")

    async def send_test_notifications(self) -> dict[str, bool]:
        """
        Send test notifications to all configured channels.

        Returns:
            Dict mapping channel name to success status
        """
        results = {}

        if self.discord and self.discord.is_configured:
            results["discord"] = await self.discord.send_test_alert()

        if self.telegram and self.telegram.is_configured:
            results["telegram"] = await self.telegram.send_test_message()

        if self.webhook and self.webhook.is_configured:
            results["webhook"] = await self.webhook.send_test_event()

        return results

    def get_stats(self) -> dict[str, Any]:
        """Get dispatcher statistics."""
        return {
            **self.stats,
            "cache_size": len(self._sent_alerts),
            "channels_active": len(self.active_channels),
            "active_channels": self.active_channels,
        }


# Singleton instance for convenience
_dispatcher: Optional[AlertDispatcher] = None


def get_dispatcher(clickhouse_client=None) -> AlertDispatcher:
    """Get or create singleton AlertDispatcher instance."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = AlertDispatcher(clickhouse_client=clickhouse_client)
    return _dispatcher


async def dispatch_alert(alert: InsiderAlert) -> bool:
    """Convenience function to dispatch a single insider alert."""
    return await get_dispatcher().dispatch(alert)


async def dispatch_alerts(alerts: list[InsiderAlert]) -> int:
    """Convenience function to dispatch multiple insider alerts."""
    return await get_dispatcher().dispatch_batch(alerts)


async def dispatch_general_alert(alert: Alert) -> bool:
    """Convenience function to dispatch a single general alert."""
    return await get_dispatcher().dispatch_general(alert)


async def dispatch_general_alerts(alerts: list[Alert]) -> int:
    """Convenience function to dispatch multiple general alerts."""
    return await get_dispatcher().dispatch_general_batch(alerts)
