"""
AWARE Analytics - Generic Webhook Notification Handler

Sends alerts to any HTTP endpoint as JSON payloads.
Supports custom headers, authentication, and retry logic.

Usage:
    notifier = WebhookNotifier(
        url="https://example.com/webhook",
        headers={"Authorization": "Bearer TOKEN"}
    )
    await notifier.send_alert(alert)

Environment Variables:
    WEBHOOK_URL - Default webhook URL
    WEBHOOK_SECRET - Secret for HMAC signature (optional)
    WEBHOOK_AUTH_HEADER - Authorization header value (optional)
"""

import os
import logging
import hmac
import hashlib
import json
from datetime import datetime
from typing import Optional, Any, Union
from dataclasses import asdict

import httpx

# Import alert types from parent modules
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from insider_detector import InsiderAlert, AlertSeverity, InsiderSignalType
from alerts import Alert, AlertType, AlertPriority

logger = logging.getLogger(__name__)


class WebhookNotifier:
    """
    Send alerts to generic HTTP webhooks.

    Features:
    - JSON payload format
    - Custom headers support
    - HMAC signature for security
    - Configurable retry logic
    - Timeout handling
    """

    def __init__(
        self,
        url: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
        secret: Optional[str] = None,
        timeout: float = 10.0,
        max_retries: int = 3,
    ):
        """
        Initialize webhook notifier.

        Args:
            url: Webhook URL. Falls back to WEBHOOK_URL env var.
            headers: Custom headers to include. Falls back to WEBHOOK_AUTH_HEADER.
            secret: Secret for HMAC-SHA256 signature. Falls back to WEBHOOK_SECRET.
            timeout: Request timeout in seconds.
            max_retries: Maximum retry attempts for failed requests.
        """
        self.url = url or os.getenv("WEBHOOK_URL")
        self.secret = secret or os.getenv("WEBHOOK_SECRET")
        self.timeout = timeout
        self.max_retries = max_retries

        # Build headers
        self.headers: dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": "AWARE-Fund-Analytics/1.0",
        }

        if headers:
            self.headers.update(headers)
        elif os.getenv("WEBHOOK_AUTH_HEADER"):
            self.headers["Authorization"] = os.getenv("WEBHOOK_AUTH_HEADER")

        if not self.url:
            logger.warning("No webhook URL configured - notifications disabled")

    @property
    def is_configured(self) -> bool:
        """Check if webhook is properly configured."""
        return bool(self.url)

    def _sign_payload(self, payload: str) -> str:
        """
        Generate HMAC-SHA256 signature for payload.

        Args:
            payload: JSON string payload

        Returns:
            Hex-encoded signature
        """
        if not self.secret:
            return ""

        signature = hmac.new(
            self.secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        return signature

    def _build_insider_payload(self, alert: InsiderAlert) -> dict[str, Any]:
        """Build JSON payload from insider alert."""
        return {
            "event_type": "insider_alert",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "alert": {
                "signal_type": alert.signal_type.value,
                "severity": alert.severity.value,
                "market_slug": alert.market_slug,
                "market_question": alert.market_question,
                "description": alert.description,
                "confidence": alert.confidence,
                "direction": alert.direction,
                "total_volume_usd": alert.total_volume_usd,
                "num_traders": alert.num_traders,
                "detected_at": alert.detected_at.isoformat() + "Z" if alert.detected_at else None,
                "traders_involved": alert.traders_involved,
            },
            "metadata": {
                "source": "aware-analytics",
                "version": "1.0",
            }
        }

    def _build_general_payload(self, alert: Alert) -> dict[str, Any]:
        """Build JSON payload from general alert."""
        return {
            "event_type": "general_alert",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "alert": {
                "alert_id": alert.alert_id,
                "alert_type": alert.alert_type.value,
                "priority": alert.priority.value,
                "title": alert.title,
                "message": alert.message,
                "username": alert.username,
                "market_slug": alert.market_slug,
                "index_type": alert.index_type,
                "data": alert.data,
                "created_at": alert.created_at.isoformat() + "Z" if alert.created_at else None,
            },
            "metadata": {
                "source": "aware-analytics",
                "version": "1.0",
            }
        }

    async def send_alert(self, alert: InsiderAlert) -> bool:
        """
        Send an insider alert to the webhook.

        Args:
            alert: The InsiderAlert to send

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.is_configured:
            logger.debug("Webhook not configured, skipping alert")
            return False

        payload = self._build_insider_payload(alert)
        return await self._send_payload(payload)

    async def send_general_alert(self, alert: Alert) -> bool:
        """
        Send a general alert to the webhook.

        Args:
            alert: The Alert object to send

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.is_configured:
            logger.debug("Webhook not configured, skipping alert")
            return False

        payload = self._build_general_payload(alert)
        return await self._send_payload(payload)

    async def send_consensus_signal(
        self,
        market_slug: str,
        direction: str,
        strength: str,
        agreement_pct: float,
        num_traders: int,
        total_volume: float,
        current_price: Optional[float] = None,
    ) -> bool:
        """
        Send a consensus signal to the webhook.

        Args:
            market_slug: Market identifier
            direction: "YES" or "NO"
            strength: Consensus strength
            agreement_pct: Percentage agreement
            num_traders: Number of traders
            total_volume: Total smart money volume
            current_price: Current market price

        Returns:
            True if sent successfully
        """
        if not self.is_configured:
            return False

        payload = {
            "event_type": "consensus_signal",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "signal": {
                "market_slug": market_slug,
                "direction": direction,
                "strength": strength,
                "agreement_pct": agreement_pct,
                "num_traders": num_traders,
                "total_volume_usd": total_volume,
                "current_price": current_price,
            },
            "metadata": {
                "source": "aware-analytics",
                "version": "1.0",
            }
        }

        return await self._send_payload(payload)

    async def send_edge_decay_alert(
        self,
        username: str,
        decay_type: str,
        signal: str,
        decay_score: float,
        historical_value: float,
        current_value: float,
        decline_pct: float,
        recommended_action: str,
    ) -> bool:
        """
        Send an edge decay alert to the webhook.

        Args:
            username: Trader username
            decay_type: Type of decay
            signal: Signal strength
            decay_score: Decay severity score
            historical_value: Historical metric
            current_value: Current metric
            decline_pct: Percentage decline
            recommended_action: Suggested action

        Returns:
            True if sent successfully
        """
        if not self.is_configured:
            return False

        payload = {
            "event_type": "edge_decay_alert",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "alert": {
                "username": username,
                "decay_type": decay_type,
                "signal": signal,
                "decay_score": decay_score,
                "historical_value": historical_value,
                "current_value": current_value,
                "decline_pct": decline_pct,
                "recommended_action": recommended_action,
            },
            "metadata": {
                "source": "aware-analytics",
                "version": "1.0",
            }
        }

        return await self._send_payload(payload)

    async def send_hidden_gem_alert(
        self,
        username: str,
        discovery_type: str,
        discovery_score: float,
        reason: str,
        metrics: dict[str, Any],
    ) -> bool:
        """
        Send a hidden gem discovery alert to the webhook.

        Args:
            username: Trader username
            discovery_type: Type of discovery
            discovery_score: Discovery score
            reason: Discovery reason
            metrics: Performance metrics dict

        Returns:
            True if sent successfully
        """
        if not self.is_configured:
            return False

        payload = {
            "event_type": "hidden_gem_alert",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "discovery": {
                "username": username,
                "discovery_type": discovery_type,
                "discovery_score": discovery_score,
                "reason": reason,
                "metrics": metrics,
            },
            "metadata": {
                "source": "aware-analytics",
                "version": "1.0",
            }
        }

        return await self._send_payload(payload)

    async def send_custom_event(
        self,
        event_type: str,
        data: dict[str, Any],
    ) -> bool:
        """
        Send a custom event to the webhook.

        Args:
            event_type: Type of event
            data: Event data

        Returns:
            True if sent successfully
        """
        if not self.is_configured:
            return False

        payload = {
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": data,
            "metadata": {
                "source": "aware-analytics",
                "version": "1.0",
            }
        }

        return await self._send_payload(payload)

    async def _send_payload(self, payload: dict[str, Any]) -> bool:
        """
        Send a JSON payload to the webhook with retry logic.

        Args:
            payload: Dictionary to send as JSON

        Returns:
            True if sent successfully
        """
        payload_json = json.dumps(payload, default=str)

        # Add signature if secret is configured
        headers = self.headers.copy()
        if self.secret:
            signature = self._sign_payload(payload_json)
            headers["X-Aware-Signature"] = f"sha256={signature}"

        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.url,
                        content=payload_json,
                        headers=headers,
                        timeout=self.timeout
                    )

                if response.status_code in (200, 201, 202, 204):
                    logger.info(f"Webhook sent successfully: {payload.get('event_type')}")
                    return True
                elif response.status_code >= 500:
                    # Server error, retry
                    last_error = f"Server error: {response.status_code}"
                    logger.warning(f"Webhook server error (attempt {attempt + 1}): {response.status_code}")
                    continue
                else:
                    # Client error, don't retry
                    logger.error(f"Webhook client error: {response.status_code} - {response.text}")
                    return False

            except httpx.TimeoutException:
                last_error = "Request timed out"
                logger.warning(f"Webhook timeout (attempt {attempt + 1})")
                continue
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Webhook error (attempt {attempt + 1}): {e}")
                continue

        logger.error(f"Webhook failed after {self.max_retries} attempts: {last_error}")
        return False

    async def send_test_event(self) -> bool:
        """
        Send a test event to verify webhook configuration.

        Returns:
            True if test sent successfully
        """
        if not self.is_configured:
            logger.error("Cannot send test: Webhook not configured")
            return False

        payload = {
            "event_type": "test",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "message": "This is a test from AWARE Fund Intelligence",
            "metadata": {
                "source": "aware-analytics",
                "version": "1.0",
            }
        }

        return await self._send_payload(payload)


class MultiWebhookNotifier:
    """
    Send alerts to multiple webhook endpoints.

    Useful for broadcasting to multiple services (Zapier, n8n, custom services).
    """

    def __init__(self, webhooks: Optional[list[dict[str, Any]]] = None):
        """
        Initialize multi-webhook notifier.

        Args:
            webhooks: List of webhook configs, each with:
                - url: Webhook URL (required)
                - headers: Custom headers (optional)
                - secret: HMAC secret (optional)
                - name: Friendly name (optional)

        Falls back to WEBHOOK_URLS env var (comma-separated URLs).
        """
        self.notifiers: list[tuple[str, WebhookNotifier]] = []

        if webhooks:
            for config in webhooks:
                name = config.get("name", config.get("url", "unnamed"))
                notifier = WebhookNotifier(
                    url=config.get("url"),
                    headers=config.get("headers"),
                    secret=config.get("secret"),
                )
                if notifier.is_configured:
                    self.notifiers.append((name, notifier))
        else:
            # Fall back to env var
            urls = os.getenv("WEBHOOK_URLS", "").split(",")
            for i, url in enumerate(urls):
                url = url.strip()
                if url:
                    notifier = WebhookNotifier(url=url)
                    self.notifiers.append((f"webhook_{i}", notifier))

        if not self.notifiers:
            logger.warning("No webhooks configured for MultiWebhookNotifier")

    @property
    def is_configured(self) -> bool:
        """Check if any webhook is configured."""
        return bool(self.notifiers)

    async def send_alert(self, alert: InsiderAlert) -> dict[str, bool]:
        """
        Send alert to all configured webhooks.

        Returns:
            Dict mapping webhook name to success status
        """
        results = {}
        for name, notifier in self.notifiers:
            results[name] = await notifier.send_alert(alert)
        return results

    async def send_general_alert(self, alert: Alert) -> dict[str, bool]:
        """
        Send general alert to all configured webhooks.

        Returns:
            Dict mapping webhook name to success status
        """
        results = {}
        for name, notifier in self.notifiers:
            results[name] = await notifier.send_general_alert(alert)
        return results

    async def send_custom_event(self, event_type: str, data: dict[str, Any]) -> dict[str, bool]:
        """
        Send custom event to all configured webhooks.

        Returns:
            Dict mapping webhook name to success status
        """
        results = {}
        for name, notifier in self.notifiers:
            results[name] = await notifier.send_custom_event(event_type, data)
        return results


# Convenience functions for sync usage
def send_alert_sync(alert: InsiderAlert, url: Optional[str] = None) -> bool:
    """Synchronous wrapper for sending alerts."""
    import asyncio
    notifier = WebhookNotifier(url)
    return asyncio.run(notifier.send_alert(alert))


def send_general_alert_sync(alert: Alert, url: Optional[str] = None) -> bool:
    """Synchronous wrapper for sending general alerts."""
    import asyncio
    notifier = WebhookNotifier(url)
    return asyncio.run(notifier.send_general_alert(alert))
