"""
AWARE Analytics - Real-time Notification System

Sends insider alerts and trading signals to Discord, Telegram, and other channels.
"""

from .discord import DiscordNotifier
from .dispatcher import AlertDispatcher

__all__ = ["DiscordNotifier", "AlertDispatcher"]
