"""
AWARE Analytics - Discord Notification Handler

Sends insider alerts to Discord via webhooks with rich embeds.

Usage:
    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/...")
    await notifier.send_alert(alert)

Environment Variables:
    DISCORD_WEBHOOK_URL - Default webhook URL if not provided in constructor
"""

import os
import logging
from datetime import datetime
from typing import Optional, Any

import httpx

# Import from parent package
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from insider_detector import InsiderAlert, AlertSeverity, InsiderSignalType

logger = logging.getLogger(__name__)


# Severity to Discord embed color mapping
SEVERITY_COLORS = {
    AlertSeverity.CRITICAL: 0xFF0000,  # Red
    AlertSeverity.HIGH: 0xFFA500,      # Orange
    AlertSeverity.MEDIUM: 0xFFFF00,    # Yellow
    AlertSeverity.LOW: 0x00FF00,       # Green
}

# Severity to emoji mapping
SEVERITY_EMOJI = {
    AlertSeverity.CRITICAL: "\U0001f6a8",  # Rotating light
    AlertSeverity.HIGH: "\u26a0\ufe0f",     # Warning
    AlertSeverity.MEDIUM: "\U0001f50d",    # Magnifying glass
    AlertSeverity.LOW: "\U0001f4a1",       # Light bulb
}

# Signal type descriptions for humans
SIGNAL_DESCRIPTIONS = {
    InsiderSignalType.NEW_ACCOUNT_WHALE: "New Account Whale",
    InsiderSignalType.VOLUME_SPIKE: "Volume Spike",
    InsiderSignalType.SMART_MONEY_DIVERGENCE: "Smart Money Divergence",
    InsiderSignalType.WHALE_ANOMALY: "Whale Anomaly",
    InsiderSignalType.COORDINATED_ENTRY: "Coordinated Entry",
    InsiderSignalType.LATE_ENTRY_CONVICTION: "Late Entry Conviction",
}


class DiscordNotifier:
    """
    Send insider alerts to Discord via webhook.

    Uses Discord's rich embed format with:
    - Color-coded severity (red=critical, orange=high, etc.)
    - Structured fields for market info, volume, traders
    - Link to Polymarket for easy access
    """

    def __init__(self, webhook_url: Optional[str] = None):
        """
        Initialize Discord notifier.

        Args:
            webhook_url: Discord webhook URL. Falls back to DISCORD_WEBHOOK_URL env var.
        """
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
        if not self.webhook_url:
            logger.warning("No Discord webhook URL configured - notifications disabled")

    @property
    def is_configured(self) -> bool:
        """Check if Discord is properly configured."""
        return bool(self.webhook_url)

    async def send_alert(self, alert: InsiderAlert) -> bool:
        """
        Send an insider alert to Discord.

        Args:
            alert: The InsiderAlert to send

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.is_configured:
            logger.debug("Discord not configured, skipping alert")
            return False

        try:
            embed = self._build_embed(alert)
            payload = {
                "embeds": [embed],
                "username": "AWARE Fund Intelligence",
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    timeout=10.0
                )

            if response.status_code == 204:
                logger.info(f"Discord alert sent: {alert.signal_type.value} for {alert.market_slug}")
                return True
            else:
                logger.error(f"Discord webhook failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            logger.error(f"Failed to send Discord alert: {e}")
            return False

    def _build_embed(self, alert: InsiderAlert) -> dict[str, Any]:
        """
        Build Discord embed from alert.

        Returns a dict matching Discord's embed structure:
        https://discord.com/developers/docs/resources/channel#embed-object
        """
        severity_emoji = SEVERITY_EMOJI.get(alert.severity, "\U0001f4a1")
        signal_name = SIGNAL_DESCRIPTIONS.get(alert.signal_type, alert.signal_type.value)

        # Direction emoji
        direction_emoji = "\U0001f7e2" if alert.direction == "YES" else "\U0001f534"  # Green/Red circle

        # Build title
        title = f"{severity_emoji} Insider Signal: {signal_name}"

        # Build fields
        fields = [
            {
                "name": "\U0001f4ca Market",
                "value": alert.market_question[:100] + ("..." if len(alert.market_question) > 100 else ""),
                "inline": False
            },
            {
                "name": f"{direction_emoji} Direction",
                "value": alert.direction,
                "inline": True
            },
            {
                "name": "\U0001f4b0 Volume",
                "value": f"${alert.total_volume_usd:,.0f}",
                "inline": True
            },
            {
                "name": "\U0001f512 Confidence",
                "value": f"{alert.confidence * 100:.0f}%",
                "inline": True
            },
        ]

        # Add traders if available
        if alert.traders_involved:
            traders_str = ", ".join(alert.traders_involved[:5])
            if len(alert.traders_involved) > 5:
                traders_str += f" (+{len(alert.traders_involved) - 5} more)"
            fields.append({
                "name": "\U0001f464 Traders",
                "value": traders_str,
                "inline": False
            })

        # Add number of traders if no names
        elif alert.num_traders > 0:
            fields.append({
                "name": "\U0001f465 Traders",
                "value": f"{alert.num_traders} traders involved",
                "inline": True
            })

        # Build market URL
        market_url = f"https://polymarket.com/event/{alert.market_slug}"

        embed = {
            "title": title,
            "description": alert.description,
            "color": SEVERITY_COLORS.get(alert.severity, 0x808080),
            "fields": fields,
            "url": market_url,
            "footer": {
                "text": "AWARE Fund Intelligence"
            },
            "timestamp": alert.detected_at.isoformat() if alert.detected_at else datetime.utcnow().isoformat()
        }

        return embed

    async def send_test_alert(self) -> bool:
        """
        Send a test alert to verify webhook configuration.

        Returns:
            True if test message sent successfully
        """
        if not self.is_configured:
            logger.error("Cannot send test: Discord not configured")
            return False

        test_embed = {
            "title": "\u2705 AWARE Fund Test Alert",
            "description": "This is a test message from AWARE Fund Intelligence.\n\nIf you see this, your Discord notifications are working correctly!",
            "color": 0x00FF00,  # Green
            "fields": [
                {"name": "Status", "value": "Connected", "inline": True},
                {"name": "Channel", "value": "Discord Webhook", "inline": True},
            ],
            "footer": {"text": "AWARE Fund Intelligence"},
            "timestamp": datetime.utcnow().isoformat()
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json={"embeds": [test_embed], "username": "AWARE Fund Intelligence"},
                    timeout=10.0
                )

            if response.status_code == 204:
                logger.info("Discord test message sent successfully")
                return True
            else:
                logger.error(f"Discord test failed: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Discord test failed: {e}")
            return False


# Convenience function for sync usage
def send_alert_sync(alert: InsiderAlert, webhook_url: Optional[str] = None) -> bool:
    """
    Synchronous wrapper for sending alerts.

    Useful for scripts that aren't async.
    """
    import asyncio
    notifier = DiscordNotifier(webhook_url)
    return asyncio.run(notifier.send_alert(alert))
