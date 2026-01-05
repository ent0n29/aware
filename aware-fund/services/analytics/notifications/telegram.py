"""
AWARE Analytics - Telegram Notification Handler

Sends insider alerts and trading signals to Telegram via bot API.

Usage:
    notifier = TelegramNotifier(
        bot_token="123456:ABC-DEF...",
        chat_id="-1001234567890"
    )
    await notifier.send_alert(alert)

Environment Variables:
    TELEGRAM_BOT_TOKEN - Telegram bot token from @BotFather
    TELEGRAM_CHAT_ID - Chat/channel/group ID to send messages to
    TELEGRAM_THREAD_ID - Optional thread ID for forum topics
"""

import os
import logging
from datetime import datetime
from typing import Optional, Any, Union

import httpx

# Import alert types from parent modules
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from insider_detector import InsiderAlert, AlertSeverity, InsiderSignalType
from alerts import Alert, AlertType, AlertPriority

logger = logging.getLogger(__name__)


# Severity to emoji mapping for insider alerts
INSIDER_SEVERITY_EMOJI = {
    AlertSeverity.CRITICAL: "\U0001f6a8",  # Rotating light
    AlertSeverity.HIGH: "\u26a0\ufe0f",     # Warning
    AlertSeverity.MEDIUM: "\U0001f50d",    # Magnifying glass
    AlertSeverity.LOW: "\U0001f4a1",       # Light bulb
}

# Priority to emoji mapping for general alerts
PRIORITY_EMOJI = {
    AlertPriority.URGENT: "\U0001f6a8",    # Rotating light
    AlertPriority.HIGH: "\u26a0\ufe0f",     # Warning
    AlertPriority.MEDIUM: "\U0001f4ca",    # Chart
    AlertPriority.LOW: "\U0001f4a1",       # Light bulb
}

# Alert type emoji mapping
ALERT_TYPE_EMOJI = {
    AlertType.POSITION_ENTRY: "\U0001f4b0",     # Money bag
    AlertType.POSITION_EXIT: "\U0001f3c3",      # Running
    AlertType.LARGE_TRADE: "\U0001f40b",        # Whale
    AlertType.CONSENSUS_FORMING: "\U0001f91d",   # Handshake
    AlertType.CONSENSUS_SHIFT: "\U0001f504",    # Arrows
    AlertType.INDEX_ADDITION: "\u2795",          # Plus
    AlertType.INDEX_REMOVAL: "\u2796",           # Minus
    AlertType.EDGE_DECAY: "\U0001f4c9",         # Chart down
    AlertType.RISING_STAR: "\u2b50",             # Star
    AlertType.MARKET_ACTIVITY: "\U0001f525",    # Fire
}

# Insider signal type descriptions
SIGNAL_DESCRIPTIONS = {
    InsiderSignalType.NEW_ACCOUNT_WHALE: "New Account Whale",
    InsiderSignalType.VOLUME_SPIKE: "Volume Spike",
    InsiderSignalType.SMART_MONEY_DIVERGENCE: "Smart Money Divergence",
    InsiderSignalType.WHALE_ANOMALY: "Whale Anomaly",
    InsiderSignalType.COORDINATED_ENTRY: "Coordinated Entry",
    InsiderSignalType.LATE_ENTRY_CONVICTION: "Late Entry Conviction",
}


class TelegramNotifier:
    """
    Send alerts to Telegram via bot API.

    Supports:
    - Plain text messages
    - Markdown formatted messages
    - HTML formatted messages
    - Silent notifications (no sound)
    - Message threading (forum topics)
    """

    TELEGRAM_API_BASE = "https://api.telegram.org/bot"

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[Union[str, int]] = None,
        thread_id: Optional[int] = None,
        silent: bool = False,
    ):
        """
        Initialize Telegram notifier.

        Args:
            bot_token: Telegram bot token. Falls back to TELEGRAM_BOT_TOKEN env var.
            chat_id: Chat/channel/group ID. Falls back to TELEGRAM_CHAT_ID env var.
            thread_id: Optional forum topic thread ID. Falls back to TELEGRAM_THREAD_ID.
            silent: If True, send notifications without sound.
        """
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.thread_id = thread_id or os.getenv("TELEGRAM_THREAD_ID")
        self.silent = silent

        if not self.bot_token:
            logger.warning("No Telegram bot token configured - notifications disabled")
        if not self.chat_id:
            logger.warning("No Telegram chat ID configured - notifications disabled")

    @property
    def is_configured(self) -> bool:
        """Check if Telegram is properly configured."""
        return bool(self.bot_token and self.chat_id)

    @property
    def api_url(self) -> str:
        """Get the Telegram API base URL for this bot."""
        return f"{self.TELEGRAM_API_BASE}{self.bot_token}"

    async def send_alert(self, alert: InsiderAlert) -> bool:
        """
        Send an insider alert to Telegram.

        Args:
            alert: The InsiderAlert to send

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.is_configured:
            logger.debug("Telegram not configured, skipping alert")
            return False

        try:
            message = self._format_insider_alert(alert)
            return await self._send_message(message, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            return False

    async def send_general_alert(self, alert: Alert) -> bool:
        """
        Send a general alert (edge decay, consensus, etc.) to Telegram.

        Args:
            alert: The Alert object to send

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.is_configured:
            logger.debug("Telegram not configured, skipping alert")
            return False

        try:
            message = self._format_general_alert(alert)
            return await self._send_message(message, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
            return False

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
        Send a consensus signal notification.

        Args:
            market_slug: Market identifier
            direction: "YES" or "NO"
            strength: Consensus strength (WEAK, MODERATE, STRONG, VERY_STRONG)
            agreement_pct: Percentage of smart money in agreement
            num_traders: Number of traders analyzed
            total_volume: Total volume from smart money

        Returns:
            True if sent successfully
        """
        if not self.is_configured:
            return False

        direction_emoji = "\U0001f7e2" if direction == "YES" else "\U0001f534"

        message = f"""
\U0001f91d <b>Smart Money Consensus</b>

<b>Market:</b> {market_slug}
{direction_emoji} <b>Direction:</b> {direction}
\U0001f4aa <b>Strength:</b> {strength}
\U0001f4ca <b>Agreement:</b> {agreement_pct:.1f}%
\U0001f465 <b>Traders:</b> {num_traders}
\U0001f4b0 <b>Volume:</b> ${total_volume:,.0f}

<a href="https://polymarket.com/event/{market_slug}">View on Polymarket</a>
""".strip()

        return await self._send_message(message, parse_mode="HTML")

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
        Send an edge decay warning notification.

        Args:
            username: Trader username
            decay_type: Type of decay (WIN_RATE, SHARPE_RATIO, etc.)
            signal: Signal strength (EARLY_WARNING, MODERATE, SEVERE, CRITICAL)
            historical_value: Historical metric value
            current_value: Current metric value
            decline_pct: Percentage decline
            recommended_action: Suggested action

        Returns:
            True if sent successfully
        """
        if not self.is_configured:
            return False

        signal_emoji = {
            "EARLY_WARNING": "\U0001f7e1",    # Yellow circle
            "MODERATE": "\U0001f7e0",         # Orange circle
            "SEVERE": "\U0001f534",           # Red circle
            "CRITICAL": "\U0001f6a8",         # Rotating light
        }.get(signal, "\U0001f4c9")

        message = f"""
{signal_emoji} <b>Edge Decay Alert</b>

\U0001f464 <b>Trader:</b> {username}
\U0001f4c9 <b>Decay Type:</b> {decay_type}
\U0001f6a6 <b>Signal:</b> {signal}

<b>Performance Change:</b>
  Historical: {historical_value:.2f}
  Current: {current_value:.2f}
  Decline: {decline_pct:.1f}%

\u27a1\ufe0f <b>Recommended:</b> {recommended_action}
""".strip()

        return await self._send_message(message, parse_mode="HTML")

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
        Send a hidden gem discovery notification.

        Args:
            username: Trader username
            discovery_type: Type of discovery (HIDDEN_GEM, RISING_STAR, etc.)
            discovery_score: How "hidden" yet valuable (0-100)
            reason: Why they were discovered
            sharpe_ratio: Trader's Sharpe ratio
            win_rate: Trader's win rate
            total_pnl: Trader's total P&L

        Returns:
            True if sent successfully
        """
        if not self.is_configured:
            return False

        type_emoji = {
            "HIDDEN_GEM": "\U0001f48e",        # Gem
            "RISING_STAR": "\u2b50",           # Star
            "NICHE_SPECIALIST": "\U0001f3af", # Target
            "CONTRARIAN": "\U0001f504",       # Arrows
            "STRATEGY_OUTLIER": "\U0001f52e", # Crystal ball
        }.get(discovery_type, "\U0001f4a1")

        pnl_emoji = "\U0001f7e2" if total_pnl >= 0 else "\U0001f534"

        message = f"""
{type_emoji} <b>Hidden Alpha Discovery</b>

\U0001f464 <b>Trader:</b> {username}
\U0001f3c6 <b>Type:</b> {discovery_type}
\U0001f4af <b>Discovery Score:</b> {discovery_score:.0f}/100

<b>Why Discovered:</b>
{reason}

<b>Performance Metrics:</b>
  Sharpe: {sharpe_ratio:.2f}
  Win Rate: {win_rate:.1%}
  {pnl_emoji} P&L: ${total_pnl:,.0f}
""".strip()

        return await self._send_message(message, parse_mode="HTML")

    def _format_insider_alert(self, alert: InsiderAlert) -> str:
        """Format an insider alert for Telegram."""
        emoji = INSIDER_SEVERITY_EMOJI.get(alert.severity, "\U0001f4a1")
        signal_name = SIGNAL_DESCRIPTIONS.get(alert.signal_type, alert.signal_type.value)
        direction_emoji = "\U0001f7e2" if alert.direction == "YES" else "\U0001f534"

        # Build traders list if available
        traders_info = ""
        if alert.traders_involved:
            traders_str = ", ".join(alert.traders_involved[:5])
            if len(alert.traders_involved) > 5:
                traders_str += f" (+{len(alert.traders_involved) - 5} more)"
            traders_info = f"\n\U0001f464 <b>Traders:</b> {traders_str}"
        elif alert.num_traders > 0:
            traders_info = f"\n\U0001f465 <b>Traders:</b> {alert.num_traders} involved"

        message = f"""
{emoji} <b>Insider Signal: {signal_name}</b>
<i>{alert.severity.value}</i>

<b>Market:</b> {alert.market_slug}
{direction_emoji} <b>Direction:</b> {alert.direction}
\U0001f4b0 <b>Volume:</b> ${alert.total_volume_usd:,.0f}
\U0001f512 <b>Confidence:</b> {alert.confidence * 100:.0f}%{traders_info}

{alert.description}

<a href="https://polymarket.com/event/{alert.market_slug}">View on Polymarket</a>
""".strip()

        return message

    def _format_general_alert(self, alert: Alert) -> str:
        """Format a general alert for Telegram."""
        emoji = PRIORITY_EMOJI.get(alert.priority, "\U0001f4a1")
        type_emoji = ALERT_TYPE_EMOJI.get(alert.alert_type, "\U0001f4cb")

        # Build context info
        context_parts = []
        if alert.username:
            context_parts.append(f"\U0001f464 <b>Trader:</b> {alert.username}")
        if alert.market_slug:
            context_parts.append(f"\U0001f4ca <b>Market:</b> {alert.market_slug}")
        if alert.index_type:
            context_parts.append(f"\U0001f4c8 <b>Index:</b> {alert.index_type}")

        context_info = "\n".join(context_parts)
        if context_info:
            context_info = f"\n{context_info}"

        # Build data info if available
        data_info = ""
        if alert.data:
            data_parts = []
            if "total_score" in alert.data:
                data_parts.append(f"Score: {alert.data['total_score']:.0f}")
            if "size_usd" in alert.data:
                data_parts.append(f"Size: ${alert.data['size_usd']:,.0f}")
            if "decay_score" in alert.data:
                data_parts.append(f"Decay: {alert.data['decay_score']:.0f}")
            if "discovery_score" in alert.data:
                data_parts.append(f"Discovery: {alert.data['discovery_score']:.0f}")
            if data_parts:
                data_info = "\n\U0001f4ca " + " | ".join(data_parts)

        message = f"""
{emoji} {type_emoji} <b>{alert.title}</b>
<i>{alert.priority.value}</i>
{context_info}{data_info}

{alert.message}
""".strip()

        if alert.market_slug:
            message += f"\n\n<a href=\"https://polymarket.com/event/{alert.market_slug}\">View on Polymarket</a>"

        return message

    async def _send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        disable_notification: Optional[bool] = None,
    ) -> bool:
        """
        Send a message via Telegram Bot API.

        Args:
            text: Message text
            parse_mode: Parse mode (HTML, Markdown, MarkdownV2)
            disable_notification: Override silent setting

        Returns:
            True if sent successfully
        """
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False,
        }

        # Handle notification settings
        if disable_notification is not None:
            payload["disable_notification"] = disable_notification
        elif self.silent:
            payload["disable_notification"] = True

        # Handle forum topics (thread_id)
        if self.thread_id:
            payload["message_thread_id"] = int(self.thread_id)

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/sendMessage",
                    json=payload,
                    timeout=10.0
                )

            result = response.json()
            if result.get("ok"):
                logger.info("Telegram message sent successfully")
                return True
            else:
                logger.error(f"Telegram API error: {result.get('description', 'Unknown error')}")
                return False

        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    async def send_test_message(self) -> bool:
        """
        Send a test message to verify configuration.

        Returns:
            True if test message sent successfully
        """
        if not self.is_configured:
            logger.error("Cannot send test: Telegram not configured")
            return False

        message = f"""
\u2705 <b>AWARE Fund Test Message</b>

This is a test from AWARE Fund Intelligence.

If you see this, your Telegram notifications are configured correctly!

<b>Status:</b> Connected
<b>Channel:</b> Telegram Bot
<b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
""".strip()

        return await self._send_message(message)


# Convenience function for sync usage
def send_alert_sync(alert: InsiderAlert, bot_token: Optional[str] = None, chat_id: Optional[str] = None) -> bool:
    """
    Synchronous wrapper for sending alerts.

    Useful for scripts that aren't async.
    """
    import asyncio
    notifier = TelegramNotifier(bot_token, chat_id)
    return asyncio.run(notifier.send_alert(alert))


def send_general_alert_sync(alert: Alert, bot_token: Optional[str] = None, chat_id: Optional[str] = None) -> bool:
    """
    Synchronous wrapper for sending general alerts.
    """
    import asyncio
    notifier = TelegramNotifier(bot_token, chat_id)
    return asyncio.run(notifier.send_general_alert(alert))
