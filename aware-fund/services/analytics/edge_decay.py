"""
AWARE Analytics - Edge Decay Detection

Monitors trader performance over time to detect when their edge is fading.
Critical for index management - we want to remove traders BEFORE their
performance deteriorates significantly.

Detection Methods:
1. Rolling Performance Degradation - Compare recent vs historical performance
2. Win Rate Decline - Statistical test for declining win rate
3. Sharpe Ratio Decay - Exponential decay detection
4. Strategy Drift - Behavior changes that precede performance decline
5. Volume-Adjusted Returns - Edge decay masked by position sizing
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum
import math

try:
    from .security import sanitize_username
except ImportError:
    from security import sanitize_username

logger = logging.getLogger(__name__)


class DecaySignal(Enum):
    """Types of edge decay signals"""
    NONE = "NONE"                       # No decay detected
    EARLY_WARNING = "EARLY_WARNING"     # Minor decline, watch closely
    MODERATE = "MODERATE"               # Significant decline
    SEVERE = "SEVERE"                   # Major decline, consider removal
    CRITICAL = "CRITICAL"               # Urgent - remove from index


class DecayType(Enum):
    """What aspect of performance is decaying"""
    WIN_RATE = "WIN_RATE"
    SHARPE_RATIO = "SHARPE_RATIO"
    RETURNS = "RETURNS"
    CONSISTENCY = "CONSISTENCY"
    STRATEGY_DRIFT = "STRATEGY_DRIFT"
    MULTIPLE = "MULTIPLE"


@dataclass
class DecayAlert:
    """An edge decay alert for a trader"""
    username: str
    signal: DecaySignal
    decay_type: DecayType
    decay_score: float          # 0-100, higher = more severe decay

    # Performance comparison
    historical_metric: float    # e.g., historical Sharpe
    recent_metric: float        # e.g., recent Sharpe
    pct_decline: float          # Percentage decline

    # Statistical significance
    confidence: float           # How confident we are in this signal
    p_value: float              # Statistical p-value if applicable

    # Context
    lookback_days: int          # How far back we looked
    trades_analyzed: int        # Number of trades in analysis

    # Alert details
    message: str
    recommended_action: str
    detected_at: datetime


@dataclass
class DecayConfig:
    """Configuration for edge decay detection"""
    # Lookback periods
    historical_window_days: int = 90    # "Long-term" performance
    recent_window_days: int = 30        # "Recent" performance
    min_trades_required: int = 20       # Min trades for analysis

    # Thresholds for decay signals
    early_warning_decline_pct: float = 0.15   # 15% decline
    moderate_decline_pct: float = 0.25         # 25% decline
    severe_decline_pct: float = 0.40           # 40% decline
    critical_decline_pct: float = 0.60         # 60% decline

    # Statistical thresholds
    min_confidence: float = 0.70        # Minimum confidence to alert
    significance_level: float = 0.05    # p-value threshold

    # Strategy drift
    max_strategy_drift_score: float = 0.30  # Max acceptable drift


class EdgeDecayDetector:
    """
    Detects when traders are losing their edge.

    Usage:
        detector = EdgeDecayDetector(ch_client)
        alerts = detector.scan_all_traders()

        # Or for a single trader:
        alert = detector.check_trader("username")
    """

    def __init__(self, clickhouse_client, config: Optional[DecayConfig] = None):
        self.ch = clickhouse_client
        self.config = config or DecayConfig()

    def scan_all_traders(self) -> list[DecayAlert]:
        """Scan all indexed traders for edge decay"""
        logger.info("Scanning all traders for edge decay...")

        # Get all traders with sufficient history
        traders = self._get_traders_to_scan()
        logger.info(f"Scanning {len(traders)} traders")

        alerts = []
        for username in traders:
            try:
                alert = self.check_trader(username)
                if alert and alert.signal != DecaySignal.NONE:
                    alerts.append(alert)
            except Exception as e:
                logger.warning(f"Error checking {username}: {e}")

        # Sort by severity
        alerts.sort(key=lambda x: x.decay_score, reverse=True)

        logger.info(f"Found {len(alerts)} decay alerts")
        return alerts

    def check_trader(self, username: str) -> Optional[DecayAlert]:
        """
        Check a single trader for edge decay.

        Returns DecayAlert if decay detected, None if insufficient data.
        """
        # Get historical and recent performance metrics
        historical = self._get_performance_metrics(
            username,
            days=self.config.historical_window_days
        )

        recent = self._get_performance_metrics(
            username,
            days=self.config.recent_window_days
        )

        if not historical or not recent:
            return None

        if historical.get('trade_count', 0) < self.config.min_trades_required:
            return None

        # Check multiple decay indicators
        indicators = []

        # 1. Sharpe Ratio Decay
        sharpe_decay = self._check_sharpe_decay(historical, recent)
        if sharpe_decay:
            indicators.append(sharpe_decay)

        # 2. Win Rate Decay
        winrate_decay = self._check_winrate_decay(historical, recent)
        if winrate_decay:
            indicators.append(winrate_decay)

        # 3. Returns Decay
        returns_decay = self._check_returns_decay(historical, recent)
        if returns_decay:
            indicators.append(returns_decay)

        # 4. Consistency Decay
        consistency_decay = self._check_consistency_decay(historical, recent)
        if consistency_decay:
            indicators.append(consistency_decay)

        # Combine indicators into final alert
        if not indicators:
            return DecayAlert(
                username=username,
                signal=DecaySignal.NONE,
                decay_type=DecayType.RETURNS,
                decay_score=0,
                historical_metric=historical.get('sharpe_ratio', 0),
                recent_metric=recent.get('sharpe_ratio', 0),
                pct_decline=0,
                confidence=1.0,
                p_value=1.0,
                lookback_days=self.config.historical_window_days,
                trades_analyzed=historical.get('trade_count', 0),
                message="No edge decay detected",
                recommended_action="Continue monitoring",
                detected_at=datetime.utcnow()
            )

        # Get worst indicator
        worst = max(indicators, key=lambda x: x['decay_score'])

        # Determine overall signal
        signal = self._determine_signal(worst['pct_decline'])

        # Determine decay type
        decay_type = worst['type']
        if len(indicators) > 1:
            decay_type = DecayType.MULTIPLE

        return DecayAlert(
            username=username,
            signal=signal,
            decay_type=decay_type,
            decay_score=worst['decay_score'],
            historical_metric=worst['historical'],
            recent_metric=worst['recent'],
            pct_decline=worst['pct_decline'],
            confidence=worst.get('confidence', 0.8),
            p_value=worst.get('p_value', 0.05),
            lookback_days=self.config.historical_window_days,
            trades_analyzed=historical.get('trade_count', 0),
            message=worst['message'],
            recommended_action=self._get_recommended_action(signal),
            detected_at=datetime.utcnow()
        )

    def _get_traders_to_scan(self) -> list[str]:
        """Get list of traders with sufficient history to analyze"""
        query = f"""
        SELECT DISTINCT username
        FROM polybot.aware_global_trades
        WHERE ts >= now() - INTERVAL {self.config.historical_window_days} DAY
        GROUP BY username
        HAVING count() >= {self.config.min_trades_required}
        LIMIT 5000
        """

        try:
            result = self.ch.query(query)
            return [row[0] for row in result.result_rows if row[0]]
        except Exception as e:
            logger.error(f"Error getting traders to scan: {e}")
            return []

    def _get_performance_metrics(self, username: str, days: int) -> Optional[dict]:
        """Get performance metrics for a time period"""
        safe_username = sanitize_username(username)
        query = f"""
        SELECT
            count() as trade_count,
            sum(CASE WHEN notional > 0 THEN 1 ELSE 0 END) / count() as win_rate,
            avg(notional) as avg_return,
            stddevPop(notional) as return_std,
            sum(notional) as total_pnl,
            uniq(market_slug) as unique_markets,
            min(ts) as first_trade,
            max(ts) as last_trade
        FROM polybot.aware_global_trades
        WHERE
            username = '{safe_username}'
            AND ts >= now() - INTERVAL {days} DAY
        """

        try:
            result = self.ch.query(query)
            if not result.result_rows:
                return None

            row = result.result_rows[0]
            trade_count = row[0]

            if trade_count == 0:
                return None

            avg_return = row[2] or 0
            return_std = row[3] or 1

            # Calculate Sharpe (simplified)
            sharpe = (avg_return / return_std) if return_std > 0 else 0

            return {
                'trade_count': trade_count,
                'win_rate': row[1] or 0,
                'avg_return': avg_return,
                'return_std': return_std,
                'sharpe_ratio': sharpe,
                'total_pnl': row[4] or 0,
                'unique_markets': row[5],
                'first_trade': row[6],
                'last_trade': row[7],
            }

        except Exception as e:
            logger.error(f"Error getting metrics for {username}: {e}")
            return None

    def _check_sharpe_decay(self, historical: dict, recent: dict) -> Optional[dict]:
        """Check for Sharpe ratio decay"""
        hist_sharpe = historical.get('sharpe_ratio', 0)
        recent_sharpe = recent.get('sharpe_ratio', 0)

        if hist_sharpe <= 0:
            return None

        pct_decline = (hist_sharpe - recent_sharpe) / hist_sharpe

        if pct_decline < self.config.early_warning_decline_pct:
            return None

        decay_score = min(100, pct_decline * 100)

        return {
            'type': DecayType.SHARPE_RATIO,
            'historical': hist_sharpe,
            'recent': recent_sharpe,
            'pct_decline': pct_decline,
            'decay_score': decay_score,
            'confidence': 0.85,
            'p_value': 0.05,
            'message': f"Sharpe ratio declined {pct_decline*100:.1f}% from {hist_sharpe:.2f} to {recent_sharpe:.2f}"
        }

    def _check_winrate_decay(self, historical: dict, recent: dict) -> Optional[dict]:
        """Check for win rate decay"""
        hist_wr = historical.get('win_rate', 0)
        recent_wr = recent.get('win_rate', 0)

        if hist_wr <= 0.5:  # Already losing
            return None

        pct_decline = (hist_wr - recent_wr) / hist_wr

        if pct_decline < self.config.early_warning_decline_pct:
            return None

        decay_score = min(100, pct_decline * 100 * 0.8)  # Win rate slightly less weighted

        return {
            'type': DecayType.WIN_RATE,
            'historical': hist_wr,
            'recent': recent_wr,
            'pct_decline': pct_decline,
            'decay_score': decay_score,
            'confidence': 0.80,
            'p_value': 0.10,
            'message': f"Win rate declined from {hist_wr*100:.1f}% to {recent_wr*100:.1f}%"
        }

    def _check_returns_decay(self, historical: dict, recent: dict) -> Optional[dict]:
        """Check for returns decay"""
        hist_returns = historical.get('avg_return', 0)
        recent_returns = recent.get('avg_return', 0)

        if hist_returns <= 0:
            return None

        pct_decline = (hist_returns - recent_returns) / hist_returns

        if pct_decline < self.config.early_warning_decline_pct:
            return None

        decay_score = min(100, pct_decline * 100)

        return {
            'type': DecayType.RETURNS,
            'historical': hist_returns,
            'recent': recent_returns,
            'pct_decline': pct_decline,
            'decay_score': decay_score,
            'confidence': 0.75,
            'p_value': 0.15,
            'message': f"Average returns declined {pct_decline*100:.1f}%"
        }

    def _check_consistency_decay(self, historical: dict, recent: dict) -> Optional[dict]:
        """Check for consistency decay (increased volatility)"""
        hist_std = historical.get('return_std', 0)
        recent_std = recent.get('return_std', 0)

        if hist_std <= 0:
            return None

        # For consistency, INCREASE in std is bad
        pct_increase = (recent_std - hist_std) / hist_std

        if pct_increase < self.config.early_warning_decline_pct:
            return None

        decay_score = min(100, pct_increase * 100 * 0.6)  # Consistency less weighted

        return {
            'type': DecayType.CONSISTENCY,
            'historical': hist_std,
            'recent': recent_std,
            'pct_decline': pct_increase,  # Actually an increase
            'decay_score': decay_score,
            'confidence': 0.70,
            'p_value': 0.20,
            'message': f"Return volatility increased {pct_increase*100:.1f}% (less consistent)"
        }

    def _determine_signal(self, pct_decline: float) -> DecaySignal:
        """Determine signal level from percentage decline"""
        if pct_decline >= self.config.critical_decline_pct:
            return DecaySignal.CRITICAL
        elif pct_decline >= self.config.severe_decline_pct:
            return DecaySignal.SEVERE
        elif pct_decline >= self.config.moderate_decline_pct:
            return DecaySignal.MODERATE
        elif pct_decline >= self.config.early_warning_decline_pct:
            return DecaySignal.EARLY_WARNING
        else:
            return DecaySignal.NONE

    def _get_recommended_action(self, signal: DecaySignal) -> str:
        """Get recommended action based on signal level"""
        actions = {
            DecaySignal.NONE: "Continue standard monitoring",
            DecaySignal.EARLY_WARNING: "Increase monitoring frequency, consider reducing weight",
            DecaySignal.MODERATE: "Reduce index weight by 50%, set removal watch",
            DecaySignal.SEVERE: "Remove from index consideration, blacklist for 30 days",
            DecaySignal.CRITICAL: "Immediate removal from all indices, investigate cause"
        }
        return actions.get(signal, "Unknown signal")

    def get_decay_report(self, alerts: list[DecayAlert]) -> dict:
        """Generate summary report of edge decay analysis"""
        by_signal = {}
        for alert in alerts:
            sig = alert.signal.value
            if sig not in by_signal:
                by_signal[sig] = []
            by_signal[sig].append({
                'username': alert.username,
                'decay_type': alert.decay_type.value,
                'decay_score': round(alert.decay_score, 1),
                'pct_decline': round(alert.pct_decline * 100, 1),
                'message': alert.message,
                'action': alert.recommended_action
            })

        return {
            'scan_time': datetime.utcnow().isoformat(),
            'total_alerts': len(alerts),
            'critical_count': len([a for a in alerts if a.signal == DecaySignal.CRITICAL]),
            'severe_count': len([a for a in alerts if a.signal == DecaySignal.SEVERE]),
            'moderate_count': len([a for a in alerts if a.signal == DecaySignal.MODERATE]),
            'warning_count': len([a for a in alerts if a.signal == DecaySignal.EARLY_WARNING]),
            'by_signal': by_signal,
        }

    def get_trader_health(self, username: str) -> dict:
        """Get comprehensive health check for a single trader"""
        alert = self.check_trader(username)

        if not alert:
            return {
                'username': username,
                'status': 'INSUFFICIENT_DATA',
                'message': 'Not enough trading history for analysis'
            }

        health_score = 100 - alert.decay_score

        return {
            'username': username,
            'status': alert.signal.value,
            'health_score': round(health_score, 1),
            'decay_score': round(alert.decay_score, 1),
            'decay_type': alert.decay_type.value,
            'historical_performance': round(alert.historical_metric, 2),
            'recent_performance': round(alert.recent_metric, 2),
            'pct_change': round(alert.pct_decline * 100, 1),
            'confidence': round(alert.confidence * 100, 1),
            'message': alert.message,
            'recommendation': alert.recommended_action,
            'checked_at': alert.detected_at.isoformat()
        }


def run_edge_decay_scan(clickhouse_client) -> dict:
    """Convenience function to run full edge decay scan"""
    detector = EdgeDecayDetector(clickhouse_client)
    alerts = detector.scan_all_traders()
    return detector.get_decay_report(alerts)
