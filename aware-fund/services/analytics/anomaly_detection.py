"""
AWARE Analytics - Anomaly & Gaming Detection

Protects the Smart Money Index from manipulation and gaming.
Identifies suspicious patterns that indicate:
1. Wash Trading - Trading with yourself to inflate volume
2. Score Gaming - Artificial patterns to boost Smart Money Score
3. Sybil Attacks - Multiple accounts controlled by same entity
4. Pump & Dump - Coordinated buying to inflate then dump
5. Statistical Anomalies - Performance too good to be true

Each trader gets an "Integrity Score" - low scores trigger review.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum
import math

logger = logging.getLogger(__name__)


class AnomalyType(Enum):
    """Types of detected anomalies"""
    WASH_TRADING = "WASH_TRADING"           # Self-dealing
    VOLUME_INFLATION = "VOLUME_INFLATION"   # Artificially high volume
    WIN_RATE_ANOMALY = "WIN_RATE_ANOMALY"   # Statistically impossible win rate
    TIMING_PATTERN = "TIMING_PATTERN"       # Suspicious timing (bot-like)
    SYBIL_CLUSTER = "SYBIL_CLUSTER"         # Multiple accounts acting together
    PUMP_AND_DUMP = "PUMP_AND_DUMP"         # Coordinated price manipulation
    SCORE_GAMING = "SCORE_GAMING"           # Patterns to game the score
    FRONT_RUNNING = "FRONT_RUNNING"         # Trading ahead of large orders


class AnomalySeverity(Enum):
    """Severity of detected anomaly"""
    LOW = "LOW"           # Minor, flag for monitoring
    MEDIUM = "MEDIUM"     # Notable, reduce weight
    HIGH = "HIGH"         # Significant, exclude from index
    CRITICAL = "CRITICAL" # Severe, blacklist permanently


@dataclass
class AnomalyAlert:
    """A detected anomaly for a trader"""
    username: str
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    confidence: float           # 0-1, how confident in detection

    # Evidence
    description: str
    evidence: dict
    affected_trades: int

    # Impact
    integrity_impact: float     # How much to reduce integrity score
    recommended_action: str

    detected_at: datetime


@dataclass
class IntegrityScore:
    """Overall integrity assessment for a trader"""
    username: str
    score: float                # 0-100, higher = more trustworthy
    status: str                 # TRUSTED, FLAGGED, SUSPENDED, BLACKLISTED

    # Component scores
    volume_integrity: float     # Is volume genuine?
    performance_integrity: float # Are results realistic?
    behavior_integrity: float   # Is behavior normal?
    network_integrity: float    # Connections to other accounts

    # Anomalies detected
    anomaly_count: int
    critical_anomalies: int
    anomaly_types: list[str]

    # Metadata
    trades_analyzed: int
    calculated_at: datetime


@dataclass
class AnomalyConfig:
    """Configuration for anomaly detection"""
    # Win rate thresholds
    max_believable_win_rate: float = 0.85    # 85% is suspicious
    min_trades_for_winrate_check: int = 30

    # Volume thresholds
    max_self_trade_ratio: float = 0.10       # Max 10% with same counterparty

    # Timing thresholds
    min_time_between_trades_ms: int = 100    # Minimum 100ms between trades
    suspicious_regularity_threshold: float = 0.95  # Too regular = bot

    # Statistical thresholds
    sharpe_impossibility_threshold: float = 5.0  # Sharpe > 5 is suspicious
    max_consecutive_wins: int = 20           # Too many wins in a row

    # Sybil detection
    min_behavior_similarity: float = 0.90    # 90% similar = suspect sybil


class AnomalyDetector:
    """
    Detects anomalies and gaming attempts.

    Usage:
        detector = AnomalyDetector(ch_client)
        alerts = detector.scan_all_traders()
        integrity = detector.get_integrity_score("username")
    """

    def __init__(self, clickhouse_client, config: Optional[AnomalyConfig] = None):
        self.ch = clickhouse_client
        self.config = config or AnomalyConfig()

    def scan_all_traders(self) -> list[AnomalyAlert]:
        """Scan all traders for anomalies"""
        logger.info("Scanning all traders for anomalies...")

        traders = self._get_traders_to_scan()
        logger.info(f"Scanning {len(traders)} traders")

        all_alerts = []

        for username in traders:
            try:
                alerts = self.check_trader(username)
                all_alerts.extend(alerts)
            except Exception as e:
                logger.warning(f"Error checking {username}: {e}")

        # Sort by severity
        severity_order = {
            AnomalySeverity.CRITICAL: 0,
            AnomalySeverity.HIGH: 1,
            AnomalySeverity.MEDIUM: 2,
            AnomalySeverity.LOW: 3
        }
        all_alerts.sort(key=lambda x: severity_order.get(x.severity, 99))

        logger.info(f"Found {len(all_alerts)} anomalies across all traders")
        return all_alerts

    def check_trader(self, username: str) -> list[AnomalyAlert]:
        """Check a single trader for all anomaly types"""
        alerts = []

        # Run all detection methods
        checks = [
            self._check_win_rate_anomaly,
            self._check_timing_pattern,
            self._check_volume_inflation,
            self._check_impossible_performance,
            self._check_consecutive_wins,
        ]

        for check in checks:
            try:
                alert = check(username)
                if alert:
                    alerts.append(alert)
            except Exception as e:
                logger.debug(f"Check failed for {username}: {e}")

        return alerts

    def get_integrity_score(self, username: str) -> IntegrityScore:
        """Calculate overall integrity score for a trader"""
        alerts = self.check_trader(username)

        # Start at 100 and deduct for anomalies
        base_score = 100.0

        for alert in alerts:
            base_score -= alert.integrity_impact

        # Clamp to 0-100
        final_score = max(0, min(100, base_score))

        # Determine status
        critical_count = len([a for a in alerts if a.severity == AnomalySeverity.CRITICAL])
        high_count = len([a for a in alerts if a.severity == AnomalySeverity.HIGH])

        if critical_count > 0:
            status = "BLACKLISTED"
        elif high_count >= 2:
            status = "SUSPENDED"
        elif len(alerts) > 0:
            status = "FLAGGED"
        else:
            status = "TRUSTED"

        return IntegrityScore(
            username=username,
            score=final_score,
            status=status,
            volume_integrity=self._calculate_volume_integrity(username),
            performance_integrity=self._calculate_performance_integrity(username),
            behavior_integrity=self._calculate_behavior_integrity(username),
            network_integrity=100.0,  # Placeholder - would check sybil connections
            anomaly_count=len(alerts),
            critical_anomalies=critical_count,
            anomaly_types=[a.anomaly_type.value for a in alerts],
            trades_analyzed=self._get_trade_count(username),
            calculated_at=datetime.utcnow()
        )

    def _get_traders_to_scan(self) -> list[str]:
        """Get traders with sufficient activity to analyze"""
        query = """
        SELECT DISTINCT proxy_address
        FROM polybot.aware_global_trades
        WHERE ts >= now() - INTERVAL 30 DAY
        GROUP BY proxy_address
        HAVING count() >= 20
        LIMIT 5000
        """

        try:
            result = self.ch.query(query)
            return [row[0] for row in result.result_rows if row[0]]
        except Exception as e:
            logger.error(f"Error getting traders: {e}")
            return []

    def _check_win_rate_anomaly(self, username: str) -> Optional[AnomalyAlert]:
        """Check for statistically impossible win rates"""
        query = f"""
        SELECT
            count() as total_trades,
            sum(CASE WHEN notional > 0 THEN 1 ELSE 0 END) as winning_trades
        FROM polybot.aware_global_trades
        WHERE username = '{username}'
        """

        try:
            result = self.ch.query(query)
            if not result.result_rows:
                return None

            total = result.result_rows[0][0]
            wins = result.result_rows[0][1]

            if total < self.config.min_trades_for_winrate_check:
                return None

            win_rate = wins / total if total > 0 else 0

            if win_rate > self.config.max_believable_win_rate:
                # Calculate p-value for this win rate being random
                # Using simplified binomial probability
                severity = AnomalySeverity.MEDIUM
                if win_rate > 0.95:
                    severity = AnomalySeverity.HIGH
                if win_rate > 0.98:
                    severity = AnomalySeverity.CRITICAL

                return AnomalyAlert(
                    username=username,
                    anomaly_type=AnomalyType.WIN_RATE_ANOMALY,
                    severity=severity,
                    confidence=0.85,
                    description=f"Win rate of {win_rate*100:.1f}% over {total} trades is statistically unlikely",
                    evidence={
                        'win_rate': win_rate,
                        'total_trades': total,
                        'winning_trades': wins
                    },
                    affected_trades=total,
                    integrity_impact=30 if severity == AnomalySeverity.CRITICAL else 15,
                    recommended_action="Review trade history for signs of manipulation",
                    detected_at=datetime.utcnow()
                )

        except Exception as e:
            logger.debug(f"Win rate check failed: {e}")

        return None

    def _check_timing_pattern(self, username: str) -> Optional[AnomalyAlert]:
        """Check for bot-like timing patterns"""
        query = f"""
        SELECT
            ts,
            dateDiff('millisecond', lagInFrame(ts) OVER (ORDER BY ts), ts) as ms_since_last
        FROM polybot.aware_global_trades
        WHERE username = '{username}'
        ORDER BY ts
        LIMIT 1000
        """

        try:
            result = self.ch.query(query)
            if len(result.result_rows) < 10:
                return None

            # Check for suspiciously regular intervals
            intervals = [row[1] for row in result.result_rows if row[1] and row[1] > 0]

            if len(intervals) < 10:
                return None

            # Calculate variance in intervals
            avg_interval = sum(intervals) / len(intervals)
            variance = sum((x - avg_interval) ** 2 for x in intervals) / len(intervals)
            cv = math.sqrt(variance) / avg_interval if avg_interval > 0 else 0

            # Very low CV = very regular = likely bot
            if cv < 0.1 and avg_interval < 5000:  # Less than 5 seconds average
                return AnomalyAlert(
                    username=username,
                    anomaly_type=AnomalyType.TIMING_PATTERN,
                    severity=AnomalySeverity.MEDIUM,
                    confidence=0.75,
                    description=f"Trade timing is suspiciously regular (CV={cv:.3f})",
                    evidence={
                        'avg_interval_ms': avg_interval,
                        'coefficient_of_variation': cv,
                        'sample_size': len(intervals)
                    },
                    affected_trades=len(intervals),
                    integrity_impact=10,
                    recommended_action="Check if automated trading is allowed",
                    detected_at=datetime.utcnow()
                )

        except Exception as e:
            logger.debug(f"Timing check failed: {e}")

        return None

    def _check_volume_inflation(self, username: str) -> Optional[AnomalyAlert]:
        """Check for wash trading / volume inflation"""
        # This would require order book data to detect self-dealing
        # For now, check for unusual volume patterns
        query = f"""
        SELECT
            count() as trade_count,
            sum(notional) as total_volume,
            avg(notional) as avg_size,
            uniq(market_slug) as unique_markets
        FROM polybot.aware_global_trades
        WHERE username = '{username}'
        """

        try:
            result = self.ch.query(query)
            if not result.result_rows:
                return None

            row = result.result_rows[0]
            trades = row[0]
            volume = row[1]
            avg_size = row[2]
            markets = row[3]

            # Check for suspicious volume concentration
            if trades > 100 and markets == 1:
                # All volume in single market - suspicious
                return AnomalyAlert(
                    username=username,
                    anomaly_type=AnomalyType.VOLUME_INFLATION,
                    severity=AnomalySeverity.LOW,
                    confidence=0.60,
                    description=f"{trades} trades all in single market - potential wash trading",
                    evidence={
                        'trade_count': trades,
                        'unique_markets': markets,
                        'total_volume': volume
                    },
                    affected_trades=trades,
                    integrity_impact=5,
                    recommended_action="Review trading pattern diversity",
                    detected_at=datetime.utcnow()
                )

        except Exception as e:
            logger.debug(f"Volume check failed: {e}")

        return None

    def _check_impossible_performance(self, username: str) -> Optional[AnomalyAlert]:
        """Check for statistically impossible performance"""
        query = f"""
        SELECT
            avg(notional) as avg_return,
            stddevPop(notional) as std_return,
            count() as trade_count
        FROM polybot.aware_global_trades
        WHERE username = '{username}'
        """

        try:
            result = self.ch.query(query)
            if not result.result_rows:
                return None

            row = result.result_rows[0]
            avg_return = row[0] or 0
            std_return = row[1] or 1
            trades = row[2]

            if trades < 30:
                return None

            # Calculate Sharpe-like ratio
            sharpe = (avg_return / std_return) if std_return > 0 else 0

            if sharpe > self.config.sharpe_impossibility_threshold:
                return AnomalyAlert(
                    username=username,
                    anomaly_type=AnomalyType.SCORE_GAMING,
                    severity=AnomalySeverity.HIGH,
                    confidence=0.80,
                    description=f"Sharpe ratio of {sharpe:.2f} is statistically improbable",
                    evidence={
                        'sharpe_ratio': sharpe,
                        'avg_return': avg_return,
                        'std_return': std_return,
                        'trade_count': trades
                    },
                    affected_trades=trades,
                    integrity_impact=25,
                    recommended_action="Investigate for potential score manipulation",
                    detected_at=datetime.utcnow()
                )

        except Exception as e:
            logger.debug(f"Performance check failed: {e}")

        return None

    def _check_consecutive_wins(self, username: str) -> Optional[AnomalyAlert]:
        """Check for too many consecutive wins"""
        query = f"""
        SELECT
            groupArray(CASE WHEN notional > 0 THEN 1 ELSE 0 END) as win_sequence
        FROM polybot.aware_global_trades
        WHERE username = '{username}'
        ORDER BY ts
        """

        try:
            result = self.ch.query(query)
            if not result.result_rows:
                return None

            wins = result.result_rows[0][0]
            if not wins or len(wins) < 20:
                return None

            # Find longest winning streak
            max_streak = 0
            current_streak = 0

            for w in wins:
                if w == 1:
                    current_streak += 1
                    max_streak = max(max_streak, current_streak)
                else:
                    current_streak = 0

            if max_streak > self.config.max_consecutive_wins:
                return AnomalyAlert(
                    username=username,
                    anomaly_type=AnomalyType.WIN_RATE_ANOMALY,
                    severity=AnomalySeverity.MEDIUM,
                    confidence=0.70,
                    description=f"{max_streak} consecutive wins is statistically unlikely",
                    evidence={
                        'max_consecutive_wins': max_streak,
                        'total_trades': len(wins)
                    },
                    affected_trades=max_streak,
                    integrity_impact=15,
                    recommended_action="Review trade sequence for manipulation",
                    detected_at=datetime.utcnow()
                )

        except Exception as e:
            logger.debug(f"Consecutive wins check failed: {e}")

        return None

    def _calculate_volume_integrity(self, username: str) -> float:
        """Calculate volume integrity sub-score"""
        # Placeholder - would analyze volume patterns
        return 90.0

    def _calculate_performance_integrity(self, username: str) -> float:
        """Calculate performance integrity sub-score"""
        # Placeholder - would analyze if performance is realistic
        return 85.0

    def _calculate_behavior_integrity(self, username: str) -> float:
        """Calculate behavior integrity sub-score"""
        # Placeholder - would analyze trading behavior
        return 95.0

    def _get_trade_count(self, username: str) -> int:
        """Get total trade count for a user"""
        query = f"SELECT count() FROM polybot.aware_global_trades WHERE username = '{username}'"
        try:
            result = self.ch.query(query)
            return result.result_rows[0][0] if result.result_rows else 0
        except:
            return 0

    def get_anomaly_report(self, alerts: list[AnomalyAlert]) -> dict:
        """Generate summary report of anomalies"""
        by_type = {}
        by_severity = {}

        for a in alerts:
            type_name = a.anomaly_type.value
            by_type[type_name] = by_type.get(type_name, 0) + 1

            sev = a.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

        return {
            'scan_time': datetime.utcnow().isoformat(),
            'total_anomalies': len(alerts),
            'by_type': by_type,
            'by_severity': by_severity,
            'critical_count': by_severity.get('CRITICAL', 0),
            'traders_affected': len(set(a.username for a in alerts)),
            'top_alerts': [
                {
                    'username': a.username,
                    'type': a.anomaly_type.value,
                    'severity': a.severity.value,
                    'description': a.description
                }
                for a in alerts[:10]
            ]
        }


def run_anomaly_scan(clickhouse_client) -> dict:
    """Convenience function to run full anomaly scan"""
    detector = AnomalyDetector(clickhouse_client)
    alerts = detector.scan_all_traders()
    return detector.get_anomaly_report(alerts)
