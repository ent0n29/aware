#!/usr/bin/env python3
"""
AWARE Analytics - Discord Notification Test Script

Tests Discord webhook integration by sending a test alert.

Usage:
    # Set webhook URL and run
    DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/... python test_discord.py

    # Or pass webhook URL as argument
    python test_discord.py --webhook "https://discord.com/api/webhooks/..."

    # Send a mock insider alert (instead of just test message)
    python test_discord.py --mock-alert

Environment Variables:
    DISCORD_WEBHOOK_URL - Discord webhook URL
"""

import os
import sys
import asyncio
import argparse
import logging
from datetime import datetime

# Setup path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from insider_detector import InsiderAlert, AlertSeverity, InsiderSignalType
from notifications.discord import DiscordNotifier
from notifications.dispatcher import AlertDispatcher

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test-discord')


def create_mock_alert(severity: str = "HIGH") -> InsiderAlert:
    """Create a mock insider alert for testing."""
    return InsiderAlert(
        signal_type=InsiderSignalType.NEW_ACCOUNT_WHALE,
        severity=AlertSeverity[severity.upper()],
        market_slug="btc-100k-march-2025",
        market_question="Will Bitcoin hit $100,000 by March 2025?",
        description="A 5-day-old account just placed a $47,500 bet on YES. "
                    "This account has 92% of its volume concentrated in this single market.",
        confidence=0.87,
        direction="YES",
        total_volume_usd=47500.0,
        num_traders=1,
        detected_at=datetime.utcnow(),
        trade_timestamps=[datetime.utcnow()],
        traders_involved=["whale_account_new_7d"]
    )


async def test_webhook(webhook_url: str | None = None) -> bool:
    """
    Test Discord webhook with a simple test message.

    Returns True if successful.
    """
    notifier = DiscordNotifier(webhook_url)

    if not notifier.is_configured:
        logger.error("Discord webhook not configured!")
        logger.error("Set DISCORD_WEBHOOK_URL environment variable or pass --webhook argument")
        return False

    logger.info("Sending test message to Discord...")
    success = await notifier.send_test_alert()

    if success:
        logger.info("\u2705 Test message sent successfully!")
        logger.info("Check your Discord channel for the test message.")
    else:
        logger.error("\u274c Failed to send test message")
        logger.error("Check webhook URL and channel permissions")

    return success


async def test_mock_alert(webhook_url: str | None = None, severity: str = "HIGH") -> bool:
    """
    Test Discord webhook with a mock insider alert.

    Returns True if successful.
    """
    notifier = DiscordNotifier(webhook_url)

    if not notifier.is_configured:
        logger.error("Discord webhook not configured!")
        return False

    alert = create_mock_alert(severity)

    logger.info(f"Sending mock {severity} alert to Discord...")
    logger.info(f"  Signal: {alert.signal_type.value}")
    logger.info(f"  Market: {alert.market_slug}")
    logger.info(f"  Direction: {alert.direction}")
    logger.info(f"  Volume: ${alert.total_volume_usd:,.0f}")

    success = await notifier.send_alert(alert)

    if success:
        logger.info("\u2705 Mock alert sent successfully!")
    else:
        logger.error("\u274c Failed to send mock alert")

    return success


async def test_dispatcher(webhook_url: str | None = None) -> bool:
    """
    Test the full alert dispatcher pipeline.

    Returns True if successful.
    """
    # Set webhook URL in env if provided
    if webhook_url:
        os.environ["DISCORD_WEBHOOK_URL"] = webhook_url

    dispatcher = AlertDispatcher()

    if not dispatcher.has_channels:
        logger.error("No notification channels configured!")
        return False

    # Create alerts with different severities
    alerts = [
        create_mock_alert("CRITICAL"),
        create_mock_alert("HIGH"),
        create_mock_alert("MEDIUM"),
    ]

    logger.info(f"Testing dispatcher with {len(alerts)} alerts...")
    dispatched = await dispatcher.dispatch_batch(alerts)

    logger.info(f"\u2705 Dispatched {dispatched}/{len(alerts)} alerts")
    logger.info(f"Stats: {dispatcher.get_stats()}")

    return dispatched > 0


def main():
    parser = argparse.ArgumentParser(
        description='Test AWARE Discord notifications',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Test basic webhook connection
    DISCORD_WEBHOOK_URL=https://... python test_discord.py

    # Test with explicit webhook
    python test_discord.py --webhook "https://discord.com/api/webhooks/..."

    # Send mock insider alert
    python test_discord.py --mock-alert

    # Send mock alert with specific severity
    python test_discord.py --mock-alert --severity CRITICAL

    # Test full dispatcher pipeline
    python test_discord.py --dispatcher
        """
    )
    parser.add_argument(
        '--webhook', type=str,
        help='Discord webhook URL (overrides DISCORD_WEBHOOK_URL env var)'
    )
    parser.add_argument(
        '--mock-alert', action='store_true',
        help='Send a mock insider alert instead of test message'
    )
    parser.add_argument(
        '--severity', type=str, default='HIGH',
        choices=['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'],
        help='Severity level for mock alert (default: HIGH)'
    )
    parser.add_argument(
        '--dispatcher', action='store_true',
        help='Test the full alert dispatcher pipeline'
    )

    args = parser.parse_args()

    # Run appropriate test
    if args.dispatcher:
        success = asyncio.run(test_dispatcher(args.webhook))
    elif args.mock_alert:
        success = asyncio.run(test_mock_alert(args.webhook, args.severity))
    else:
        success = asyncio.run(test_webhook(args.webhook))

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
