"""
AWARE Analytics - Alerting System

Real-time alerts for trader activity and market events.

Alert Types:
1. Position Alerts - "Top trader X just entered market Y"
2. Consensus Alerts - "Smart money is converging on outcome Z"
3. Index Changes - "Trader X added/removed from PSI-10"
4. Edge Decay Alerts - "Trader X showing performance decline"
5. Hidden Alpha Alerts - "New rising star discovered"
6. Market Alerts - "High activity detected in market Y"
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Callable
from enum import Enum
import json

try:
    from .security import sanitize_username
except ImportError:
    from security import sanitize_username

logger = logging.getLogger(__name__)


class AlertType(Enum):
    """Types of alerts"""
    POSITION_ENTRY = "POSITION_ENTRY"       # Top trader enters position
    POSITION_EXIT = "POSITION_EXIT"         # Top trader exits position
    LARGE_TRADE = "LARGE_TRADE"             # Unusually large trade
    CONSENSUS_FORMING = "CONSENSUS"         # Smart money converging
    CONSENSUS_SHIFT = "CONSENSUS_SHIFT"     # Smart money changing direction
    INDEX_ADDITION = "INDEX_ADD"            # Trader added to index
    INDEX_REMOVAL = "INDEX_REMOVE"          # Trader removed from index
    EDGE_DECAY = "EDGE_DECAY"               # Performance declining
    RISING_STAR = "RISING_STAR"             # New high performer discovered
    MARKET_ACTIVITY = "MARKET_ACTIVITY"     # High volume in market


class AlertPriority(Enum):
    """Alert priority levels"""
    LOW = "LOW"           # FYI - informational
    MEDIUM = "MEDIUM"     # Notable - should review
    HIGH = "HIGH"         # Important - action may be needed
    URGENT = "URGENT"     # Critical - immediate attention


class AlertChannel(Enum):
    """Delivery channels for alerts"""
    LOG = "LOG"           # Just log it
    WEBHOOK = "WEBHOOK"   # HTTP webhook
    TELEGRAM = "TELEGRAM" # Telegram bot
    EMAIL = "EMAIL"       # Email notification
    DATABASE = "DATABASE" # Store in ClickHouse


@dataclass
class Alert:
    """A single alert"""
    alert_id: str
    alert_type: AlertType
    priority: AlertPriority
    title: str
    message: str

    # Context
    username: Optional[str] = None        # Related trader
    market_slug: Optional[str] = None     # Related market
    index_type: Optional[str] = None      # Related index

    # Data
    data: dict = field(default_factory=dict)

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    channels: list[AlertChannel] = field(default_factory=lambda: [AlertChannel.LOG])
    delivered: bool = False
    delivered_at: Optional[datetime] = None


@dataclass
class AlertRule:
    """A rule that triggers alerts"""
    rule_id: str
    name: str
    enabled: bool = True

    # What to watch
    alert_type: AlertType = AlertType.POSITION_ENTRY
    min_total_score: float = 70.0   # Only alert for high scorers
    min_trade_size_usd: float = 1000.0    # Minimum trade size
    markets: list[str] = field(default_factory=list)  # Specific markets to watch

    # How to alert
    priority: AlertPriority = AlertPriority.MEDIUM
    channels: list[AlertChannel] = field(default_factory=lambda: [AlertChannel.LOG])

    # Rate limiting
    cooldown_minutes: int = 5  # Don't re-alert same condition within


class AlertManager:
    """
    Manages alert generation, routing, and delivery.

    Usage:
        manager = AlertManager(ch_client)

        # Subscribe to alerts
        manager.add_webhook("https://webhook.site/xxx")

        # Process new trade (called by ingestor)
        alerts = manager.process_trade(trade)

        # Or run periodic scan
        alerts = manager.scan_for_alerts()
    """

    def __init__(self, clickhouse_client):
        self.ch = clickhouse_client
        self.rules: list[AlertRule] = self._default_rules()
        self.recent_alerts: dict[str, datetime] = {}  # For deduplication
        self.webhooks: list[str] = []
        self.handlers: dict[AlertChannel, Callable] = {
            AlertChannel.LOG: self._log_alert,
            AlertChannel.DATABASE: self._store_alert,
            AlertChannel.WEBHOOK: self._send_webhook,
        }

    def _default_rules(self) -> list[AlertRule]:
        """Default alert rules"""
        return [
            # Top trader position alerts
            AlertRule(
                rule_id="top10_position",
                name="Top 10 Trader Position",
                alert_type=AlertType.POSITION_ENTRY,
                min_total_score=80.0,
                min_trade_size_usd=5000.0,
                priority=AlertPriority.HIGH,
                channels=[AlertChannel.LOG, AlertChannel.DATABASE],
            ),

            # Large trade alerts
            AlertRule(
                rule_id="whale_trade",
                name="Whale Trade",
                alert_type=AlertType.LARGE_TRADE,
                min_total_score=0,
                min_trade_size_usd=50000.0,
                priority=AlertPriority.HIGH,
                channels=[AlertChannel.LOG, AlertChannel.DATABASE],
            ),

            # Rising star alerts
            AlertRule(
                rule_id="rising_star",
                name="Rising Star Discovery",
                alert_type=AlertType.RISING_STAR,
                min_total_score=0,
                priority=AlertPriority.MEDIUM,
                channels=[AlertChannel.LOG, AlertChannel.DATABASE],
            ),

            # Edge decay alerts
            AlertRule(
                rule_id="edge_decay",
                name="Edge Decay Warning",
                alert_type=AlertType.EDGE_DECAY,
                priority=AlertPriority.HIGH,
                channels=[AlertChannel.LOG, AlertChannel.DATABASE],
            ),
        ]

    def add_webhook(self, url: str) -> None:
        """Add a webhook URL for notifications"""
        if url not in self.webhooks:
            self.webhooks.append(url)
            logger.info(f"Added webhook: {url}")

    def process_trade(self, trade: dict) -> list[Alert]:
        """
        Process a new trade and generate any applicable alerts.

        Called by the ingestor for each new trade.
        """
        alerts = []

        username = trade.get('username', '')
        size_usd = trade.get('notional', 0)
        market = trade.get('market_slug', '')

        # Get trader's score (cached for performance)
        score = self._get_trader_score(username)

        # Check each rule
        for rule in self.rules:
            if not rule.enabled:
                continue

            # Check if trade matches rule criteria
            if rule.alert_type == AlertType.POSITION_ENTRY:
                if score >= rule.min_total_score and size_usd >= rule.min_trade_size_usd:
                    alert = self._create_position_alert(trade, score, rule)
                    if alert and self._should_send(alert):
                        alerts.append(alert)

            elif rule.alert_type == AlertType.LARGE_TRADE:
                if size_usd >= rule.min_trade_size_usd:
                    alert = self._create_large_trade_alert(trade, score, rule)
                    if alert and self._should_send(alert):
                        alerts.append(alert)

        # Deliver alerts
        for alert in alerts:
            self._deliver(alert)

        return alerts

    def scan_for_alerts(self) -> list[Alert]:
        """
        Periodic scan for alerts that can't be detected per-trade.
        E.g., consensus forming, edge decay, etc.
        """
        alerts = []

        # Check for consensus forming
        consensus_alerts = self._check_consensus()
        alerts.extend(consensus_alerts)

        # Edge decay is handled separately by EdgeDecayDetector

        # Deliver all alerts
        for alert in alerts:
            self._deliver(alert)

        return alerts

    def create_edge_decay_alert(
        self,
        username: str,
        signal: str,
        decay_score: float,
        message: str
    ) -> Alert:
        """Create an edge decay alert from EdgeDecayDetector results"""
        priority = AlertPriority.MEDIUM
        if decay_score >= 60:
            priority = AlertPriority.URGENT
        elif decay_score >= 40:
            priority = AlertPriority.HIGH

        alert = Alert(
            alert_id=f"edge_decay_{username}_{datetime.utcnow().timestamp()}",
            alert_type=AlertType.EDGE_DECAY,
            priority=priority,
            title=f"Edge Decay: {username}",
            message=message,
            username=username,
            data={
                'signal': signal,
                'decay_score': decay_score,
            },
            channels=[AlertChannel.LOG, AlertChannel.DATABASE],
        )

        if self._should_send(alert):
            self._deliver(alert)

        return alert

    def create_rising_star_alert(
        self,
        username: str,
        discovery_score: float,
        reason: str
    ) -> Alert:
        """Create a rising star discovery alert"""
        alert = Alert(
            alert_id=f"rising_star_{username}_{datetime.utcnow().timestamp()}",
            alert_type=AlertType.RISING_STAR,
            priority=AlertPriority.MEDIUM,
            title=f"Rising Star: {username}",
            message=reason,
            username=username,
            data={
                'discovery_score': discovery_score,
            },
            channels=[AlertChannel.LOG, AlertChannel.DATABASE],
        )

        if self._should_send(alert):
            self._deliver(alert)

        return alert

    def create_index_change_alert(
        self,
        index_type: str,
        username: str,
        action: str,  # "added" or "removed"
        reason: str
    ) -> Alert:
        """Create an index composition change alert"""
        alert_type = AlertType.INDEX_ADDITION if action == "added" else AlertType.INDEX_REMOVAL

        alert = Alert(
            alert_id=f"index_{action}_{username}_{datetime.utcnow().timestamp()}",
            alert_type=alert_type,
            priority=AlertPriority.HIGH,
            title=f"Index Change: {username} {action} to {index_type}",
            message=reason,
            username=username,
            index_type=index_type,
            data={
                'action': action,
            },
            channels=[AlertChannel.LOG, AlertChannel.DATABASE],
        )

        if self._should_send(alert):
            self._deliver(alert)

        return alert

    def _create_position_alert(
        self,
        trade: dict,
        score: float,
        rule: AlertRule
    ) -> Optional[Alert]:
        """Create a position entry alert"""
        username = trade.get('username', 'Unknown')
        market = trade.get('market_slug', 'Unknown')
        outcome = trade.get('outcome', '')
        size = trade.get('notional', 0)
        side = trade.get('side', '')

        return Alert(
            alert_id=f"pos_{username}_{market}_{datetime.utcnow().timestamp()}",
            alert_type=AlertType.POSITION_ENTRY,
            priority=rule.priority,
            title=f"Top Trader Position: {username}",
            message=f"{username} (Score: {score:.0f}) entered ${size:,.0f} {side} on '{outcome}' in {market}",
            username=username,
            market_slug=market,
            data={
                'total_score': score,
                'size_usd': size,
                'side': side,
                'outcome': outcome,
            },
            channels=rule.channels,
        )

    def _create_large_trade_alert(
        self,
        trade: dict,
        score: float,
        rule: AlertRule
    ) -> Optional[Alert]:
        """Create a large trade (whale) alert"""
        username = trade.get('username', 'Unknown')
        market = trade.get('market_slug', 'Unknown')
        size = trade.get('notional', 0)

        return Alert(
            alert_id=f"whale_{username}_{market}_{datetime.utcnow().timestamp()}",
            alert_type=AlertType.LARGE_TRADE,
            priority=rule.priority,
            title=f"Whale Trade: ${size:,.0f}",
            message=f"{username} executed ${size:,.0f} trade in {market}",
            username=username,
            market_slug=market,
            data={
                'total_score': score,
                'size_usd': size,
            },
            channels=rule.channels,
        )

    def _check_consensus(self) -> list[Alert]:
        """Check for smart money consensus forming on markets"""
        alerts = []

        # Query for markets with strong directional bias from top traders
        query = """
        WITH top_traders AS (
            SELECT username
            FROM polybot.aware_smart_money_scores FINAL
            WHERE total_score >= 70
            LIMIT 50
        )
        SELECT
            market_slug,
            outcome,
            count() as trade_count,
            sum(notional) as total_volume,
            avg(price) as avg_price
        FROM polybot.aware_global_trades
        WHERE
            username IN (SELECT username FROM top_traders)
            AND ts >= now() - INTERVAL 24 HOUR
        GROUP BY market_slug, outcome
        HAVING count() >= 3 AND sum(notional) >= 10000
        ORDER BY total_volume DESC
        LIMIT 10
        """

        try:
            result = self.ch.query(query)

            for row in result.result_rows:
                market = row[0]
                outcome = row[1]
                trade_count = row[2]
                volume = row[3]

                alert = Alert(
                    alert_id=f"consensus_{market}_{datetime.utcnow().timestamp()}",
                    alert_type=AlertType.CONSENSUS_FORMING,
                    priority=AlertPriority.MEDIUM,
                    title=f"Smart Money Consensus: {market}",
                    message=f"{trade_count} top traders (${ volume:,.0f} volume) favor '{outcome}'",
                    market_slug=market,
                    data={
                        'outcome': outcome,
                        'trade_count': trade_count,
                        'total_volume': volume,
                    },
                    channels=[AlertChannel.LOG, AlertChannel.DATABASE],
                )

                if self._should_send(alert):
                    alerts.append(alert)

        except Exception as e:
            logger.error(f"Error checking consensus: {e}")

        return alerts

    def _get_trader_score(self, username: str) -> float:
        """Get trader's Smart Money Score"""
        if not username:
            return 0

        safe_username = sanitize_username(username)
        query = f"""
        SELECT total_score
        FROM polybot.aware_smart_money_scores FINAL
        WHERE username = '{safe_username}'
        LIMIT 1
        """

        try:
            result = self.ch.query(query)
            if result.result_rows:
                return result.result_rows[0][0] or 0
        except Exception:
            pass

        return 0

    def _should_send(self, alert: Alert) -> bool:
        """Check if we should send this alert (deduplication)"""
        # Find matching rule for cooldown
        cooldown = 5  # Default 5 minutes
        for rule in self.rules:
            if rule.alert_type == alert.alert_type:
                cooldown = rule.cooldown_minutes
                break

        # Create dedup key
        key = f"{alert.alert_type.value}_{alert.username}_{alert.market_slug}"

        # Check if recently sent
        if key in self.recent_alerts:
            last_sent = self.recent_alerts[key]
            if datetime.utcnow() - last_sent < timedelta(minutes=cooldown):
                return False

        # Mark as sent
        self.recent_alerts[key] = datetime.utcnow()
        return True

    def _deliver(self, alert: Alert) -> None:
        """Deliver alert through configured channels"""
        for channel in alert.channels:
            handler = self.handlers.get(channel)
            if handler:
                try:
                    handler(alert)
                except Exception as e:
                    logger.error(f"Failed to deliver alert via {channel}: {e}")

        alert.delivered = True
        alert.delivered_at = datetime.utcnow()

    def _log_alert(self, alert: Alert) -> None:
        """Log alert to console/file"""
        priority_emoji = {
            AlertPriority.LOW: "ℹ️",
            AlertPriority.MEDIUM: "📢",
            AlertPriority.HIGH: "⚠️",
            AlertPriority.URGENT: "🚨",
        }

        emoji = priority_emoji.get(alert.priority, "📢")
        logger.info(f"{emoji} ALERT [{alert.priority.value}] {alert.title}: {alert.message}")

    def _store_alert(self, alert: Alert) -> None:
        """Store alert in ClickHouse for history"""
        try:
            row = (
                alert.alert_id,
                alert.alert_type.value,
                alert.priority.value,
                alert.title,
                alert.message,
                alert.username or '',
                alert.market_slug or '',
                alert.index_type or '',
                json.dumps(alert.data),
                alert.created_at,
            )

            # Would insert to aware_alerts table
            # self.ch.insert('aware_alerts', [row], column_names=[...])
            logger.debug(f"Would store alert: {alert.alert_id}")

        except Exception as e:
            logger.error(f"Failed to store alert: {e}")

    def _send_webhook(self, alert: Alert) -> None:
        """Send alert via webhook"""
        if not self.webhooks:
            return

        payload = {
            'alert_id': alert.alert_id,
            'type': alert.alert_type.value,
            'priority': alert.priority.value,
            'title': alert.title,
            'message': alert.message,
            'username': alert.username,
            'market': alert.market_slug,
            'data': alert.data,
            'timestamp': alert.created_at.isoformat(),
        }

        # Would use httpx/requests to POST to webhooks
        for url in self.webhooks:
            logger.info(f"Would POST to webhook: {url}")

    def get_recent_alerts(self, hours: int = 24, limit: int = 100) -> list[dict]:
        """Get recent alerts from storage"""
        # Would query from aware_alerts table
        return []

    def get_alert_stats(self) -> dict:
        """Get alert statistics"""
        return {
            'active_rules': len([r for r in self.rules if r.enabled]),
            'webhooks_configured': len(self.webhooks),
            'recent_alerts_cached': len(self.recent_alerts),
        }
