"""
AWARE Analytics - Real-time Notification System

Sends insider alerts and trading signals to multiple channels:
- Discord (via webhooks with rich embeds)
- Telegram (via bot API with formatted messages)
- Webhooks (generic JSON payloads for integrations)

Usage:
    from notifications import AlertDispatcher, get_dispatcher

    # Get singleton dispatcher (auto-configures from env vars)
    dispatcher = get_dispatcher()

    # Dispatch an insider alert
    await dispatcher.dispatch(insider_alert)

    # Dispatch a general alert (edge decay, consensus, etc.)
    await dispatcher.dispatch_general(general_alert)

    # Send specialized notifications
    await dispatcher.send_consensus_signal(...)
    await dispatcher.send_edge_decay_warning(...)
    await dispatcher.send_hidden_gem_discovery(...)

    # Process undelivered alerts from ClickHouse
    await dispatcher.process_pending_alerts()

Environment Variables:
    # Discord
    DISCORD_WEBHOOK_URL - Discord webhook URL

    # Telegram
    TELEGRAM_BOT_TOKEN - Bot token from @BotFather
    TELEGRAM_CHAT_ID - Chat/channel/group ID
    TELEGRAM_THREAD_ID - Optional forum topic thread ID

    # Webhooks
    WEBHOOK_URL - Single webhook endpoint
    WEBHOOK_URLS - Comma-separated list of endpoints
    WEBHOOK_SECRET - HMAC secret for signatures
    WEBHOOK_AUTH_HEADER - Authorization header value

    # Filtering
    ALERT_MIN_SEVERITY - Minimum severity to send (LOW, MEDIUM, HIGH, CRITICAL)
    ALERT_DEDUP_TTL_HOURS - Hours to remember sent alerts (default: 24)
"""

from .discord import DiscordNotifier
from .telegram import TelegramNotifier
from .webhook import WebhookNotifier, MultiWebhookNotifier
from .dispatcher import (
    AlertDispatcher,
    NotificationChannel,
    get_dispatcher,
    dispatch_alert,
    dispatch_alerts,
    dispatch_general_alert,
    dispatch_general_alerts,
)

__all__ = [
    # Notifiers
    "DiscordNotifier",
    "TelegramNotifier",
    "WebhookNotifier",
    "MultiWebhookNotifier",
    # Dispatcher
    "AlertDispatcher",
    "NotificationChannel",
    "get_dispatcher",
    # Convenience functions
    "dispatch_alert",
    "dispatch_alerts",
    "dispatch_general_alert",
    "dispatch_general_alerts",
]
