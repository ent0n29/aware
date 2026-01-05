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
from typing import Optional, Tuple
from enum import Enum
import math

try:
    from .security import sanitize_username
except ImportError:
    from security import sanitize_username

logger = logging.getLogger(__name__)


# =============================================================================
# Statistical Significance Testing
# =============================================================================

def calculate_z_score(p1: float, p2: float, n1: int, n2: int) -> float:
    """
    Calculate Z-score for comparing two proportions (e.g., win rates).

    Uses the pooled proportion method for two-proportion z-test.

    Args:
        p1: First proportion (historical win rate)
        p2: Second proportion (recent win rate)
        n1: Sample size for first proportion
        n2: Sample size for second proportion

    Returns:
        Z-score (positive = decline, negative = improvement)
    """
    if n1 == 0 or n2 == 0:
        return 0.0

    # Pooled proportion
    p_pool = (p1 * n1 + p2 * n2) / (n1 + n2)

    # Standard error
    se = math.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))

    if se == 0:
        return 0.0

    # Z-score (p1 - p2) / SE
    # Positive means p1 > p2 (historical > recent = decline)
    return (p1 - p2) / se


def calculate_t_statistic(
    mean1: float, mean2: float,
    std1: float, std2: float,
    n1: int, n2: int
) -> float:
    """
    Calculate Welch's t-statistic for comparing two means.

    Welch's t-test does not assume equal variances.

    Args:
        mean1: Mean of first sample (historical)
        mean2: Mean of second sample (recent)
        std1: Standard deviation of first sample
        std2: Standard deviation of second sample
        n1: Sample size for first
        n2: Sample size for second

    Returns:
        t-statistic (positive = decline)
    """
    if n1 <= 1 or n2 <= 1:
        return 0.0

    # Pooled standard error using Welch's method
    var1 = std1 ** 2 / n1
    var2 = std2 ** 2 / n2
    se = math.sqrt(var1 + var2)

    if se == 0:
        return 0.0

    return (mean1 - mean2) / se


def z_to_pvalue(z: float, two_tailed: bool = True) -> float:
    """
    Convert Z-score to p-value using standard normal approximation.

    Uses the error function approximation for the normal CDF.

    Args:
        z: Z-score
        two_tailed: If True, return two-tailed p-value

    Returns:
        p-value
    """
    # Standard normal CDF approximation using error function
    # CDF(z) = 0.5 * (1 + erf(z / sqrt(2)))

    def erf_approx(x: float) -> float:
        """Approximation of error function"""
        # Constants for Horner form approximation
        a1 = 0.254829592
        a2 = -0.284496736
        a3 = 1.421413741
        a4 = -1.453152027
        a5 = 1.061405429
        p = 0.3275911

        sign = 1 if x >= 0 else -1
        x = abs(x)

        t = 1.0 / (1.0 + p * x)
        y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)

        return sign * y

    # Calculate CDF
    cdf = 0.5 * (1 + erf_approx(abs(z) / math.sqrt(2)))

    # p-value is the tail probability
    p = 1 - cdf

    if two_tailed:
        p = 2 * p

    return min(1.0, max(0.0, p))


def t_to_pvalue(t: float, df: int, two_tailed: bool = True) -> float:
    """
    Approximate p-value from t-statistic using normal approximation.

    For large degrees of freedom, t-distribution approaches normal.
    For smaller df, this is an approximation.

    Args:
        t: t-statistic
        df: degrees of freedom
        two_tailed: If True, return two-tailed p-value

    Returns:
        Approximate p-value
    """
    if df <= 0:
        return 1.0

    # For df > 30, normal approximation is reasonable
    # For smaller df, we adjust the z-score slightly
    if df > 30:
        z = t
    else:
        # Simple adjustment for smaller samples
        z = t * math.sqrt(df / (df - 2)) if df > 2 else t

    return z_to_pvalue(z, two_tailed)


def calculate_welch_df(std1: float, std2: float, n1: int, n2: int) -> int:
    """
    Calculate degrees of freedom for Welch's t-test.

    Args:
        std1, std2: Standard deviations
        n1, n2: Sample sizes

    Returns:
        Degrees of freedom (rounded to int)
    """
    if n1 <= 1 or n2 <= 1:
        return 1

    var1 = std1 ** 2 / n1
    var2 = std2 ** 2 / n2

    numerator = (var1 + var2) ** 2
    denominator = (var1 ** 2 / (n1 - 1)) + (var2 ** 2 / (n2 - 1))

    if denominator == 0:
        return max(n1 + n2 - 2, 1)

    df = numerator / denominator
    return max(1, int(df))


def bootstrap_confidence_interval(
    metric_diff: float,
    n_samples: int = 100,
    confidence: float = 0.95
) -> Tuple[float, float]:
    """
    Estimate confidence interval for metric difference using simple approximation.

    For production, you'd want actual bootstrap resampling with the data.
    This provides a rough estimate based on normal theory.

    Args:
        metric_diff: Observed difference in metric
        n_samples: Effective sample size
        confidence: Confidence level (e.g., 0.95)

    Returns:
        Tuple of (lower, upper) confidence interval bounds
    """
    # Z-score for confidence level
    z_scores = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
    z = z_scores.get(confidence, 1.96)

    # Approximate standard error (using rule of thumb)
    se = abs(metric_diff) / math.sqrt(n_samples) if n_samples > 0 else 0

    lower = metric_diff - z * se
    upper = metric_diff + z * se

    return (lower, upper)


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
        """
        Check for Sharpe ratio decay with statistical significance.

        Uses Welch's t-test to compare return/risk ratios between periods.
        """
        hist_sharpe = historical.get('sharpe_ratio', 0)
        recent_sharpe = recent.get('sharpe_ratio', 0)
        hist_avg_return = historical.get('avg_return', 0)
        recent_avg_return = recent.get('avg_return', 0)
        hist_std = historical.get('return_std', 1)
        recent_std = recent.get('return_std', 1)
        hist_n = historical.get('trade_count', 0)
        recent_n = recent.get('trade_count', 0)

        if hist_sharpe <= 0:
            return None

        pct_decline = (hist_sharpe - recent_sharpe) / hist_sharpe

        if pct_decline < self.config.early_warning_decline_pct:
            return None

        # Statistical significance test using Welch's t-test on returns
        t_stat = calculate_t_statistic(
            hist_avg_return, recent_avg_return,
            hist_std, recent_std,
            hist_n, recent_n
        )
        df = calculate_welch_df(hist_std, recent_std, hist_n, recent_n)
        p_value = t_to_pvalue(t_stat, df, two_tailed=False)  # One-tailed: testing for decline

        # Calculate confidence based on statistical significance
        # Lower p-value = higher confidence in the decline being real
        if p_value < 0.01:
            stat_confidence = 0.95
        elif p_value < 0.05:
            stat_confidence = 0.85
        elif p_value < 0.10:
            stat_confidence = 0.70
        else:
            stat_confidence = 0.50

        # Sample size factor (more data = higher confidence)
        sample_factor = min(1.0, (hist_n + recent_n) / 100)

        # Combined confidence
        confidence = stat_confidence * sample_factor

        # Only alert if statistically significant or very large decline
        if p_value > self.config.significance_level and pct_decline < self.config.moderate_decline_pct:
            return None

        decay_score = min(100, pct_decline * 100 * confidence)

        return {
            'type': DecayType.SHARPE_RATIO,
            'historical': hist_sharpe,
            'recent': recent_sharpe,
            'pct_decline': pct_decline,
            'decay_score': decay_score,
            'confidence': confidence,
            'p_value': p_value,
            't_statistic': t_stat,
            'degrees_freedom': df,
            'is_significant': p_value < self.config.significance_level,
            'message': f"Sharpe ratio declined {pct_decline*100:.1f}% from {hist_sharpe:.2f} to {recent_sharpe:.2f} (p={p_value:.3f})"
        }

    def _check_winrate_decay(self, historical: dict, recent: dict) -> Optional[dict]:
        """
        Check for win rate decay with statistical significance.

        Uses two-proportion z-test to compare win rates between periods.
        This is the appropriate test for comparing proportions/percentages.
        """
        hist_wr = historical.get('win_rate', 0)
        recent_wr = recent.get('win_rate', 0)
        hist_n = historical.get('trade_count', 0)
        recent_n = recent.get('trade_count', 0)

        if hist_wr <= 0.5:  # Already losing
            return None

        pct_decline = (hist_wr - recent_wr) / hist_wr

        if pct_decline < self.config.early_warning_decline_pct:
            return None

        # Two-proportion z-test for win rates
        z_score = calculate_z_score(hist_wr, recent_wr, hist_n, recent_n)
        p_value = z_to_pvalue(z_score, two_tailed=False)  # One-tailed: testing for decline

        # Calculate confidence based on statistical significance
        if p_value < 0.01:
            stat_confidence = 0.95
        elif p_value < 0.05:
            stat_confidence = 0.85
        elif p_value < 0.10:
            stat_confidence = 0.70
        else:
            stat_confidence = 0.50

        # Sample size factor
        sample_factor = min(1.0, (hist_n + recent_n) / 100)

        # Combined confidence
        confidence = stat_confidence * sample_factor

        # Only alert if statistically significant or very large decline
        if p_value > self.config.significance_level and pct_decline < self.config.moderate_decline_pct:
            return None

        # Win rate slightly less weighted (0.8 factor)
        decay_score = min(100, pct_decline * 100 * 0.8 * confidence)

        # Calculate 95% confidence interval for the difference
        ci_lower, ci_upper = bootstrap_confidence_interval(
            hist_wr - recent_wr,
            hist_n + recent_n,
            confidence=0.95
        )

        return {
            'type': DecayType.WIN_RATE,
            'historical': hist_wr,
            'recent': recent_wr,
            'pct_decline': pct_decline,
            'decay_score': decay_score,
            'confidence': confidence,
            'p_value': p_value,
            'z_score': z_score,
            'is_significant': p_value < self.config.significance_level,
            'ci_95': (ci_lower, ci_upper),
            'message': f"Win rate declined from {hist_wr*100:.1f}% to {recent_wr*100:.1f}% (p={p_value:.3f}, z={z_score:.2f})"
        }

    def _check_returns_decay(self, historical: dict, recent: dict) -> Optional[dict]:
        """
        Check for returns decay with statistical significance.

        Uses Welch's t-test to compare mean returns between periods.
        """
        hist_returns = historical.get('avg_return', 0)
        recent_returns = recent.get('avg_return', 0)
        hist_std = historical.get('return_std', 1)
        recent_std = recent.get('return_std', 1)
        hist_n = historical.get('trade_count', 0)
        recent_n = recent.get('trade_count', 0)

        if hist_returns <= 0:
            return None

        pct_decline = (hist_returns - recent_returns) / hist_returns

        if pct_decline < self.config.early_warning_decline_pct:
            return None

        # Welch's t-test for mean returns
        t_stat = calculate_t_statistic(
            hist_returns, recent_returns,
            hist_std, recent_std,
            hist_n, recent_n
        )
        df = calculate_welch_df(hist_std, recent_std, hist_n, recent_n)
        p_value = t_to_pvalue(t_stat, df, two_tailed=False)

        # Calculate confidence based on statistical significance
        if p_value < 0.01:
            stat_confidence = 0.95
        elif p_value < 0.05:
            stat_confidence = 0.85
        elif p_value < 0.10:
            stat_confidence = 0.70
        else:
            stat_confidence = 0.50

        # Sample size factor
        sample_factor = min(1.0, (hist_n + recent_n) / 100)

        # Combined confidence
        confidence = stat_confidence * sample_factor

        # Only alert if statistically significant or very large decline
        if p_value > self.config.significance_level and pct_decline < self.config.moderate_decline_pct:
            return None

        decay_score = min(100, pct_decline * 100 * confidence)

        return {
            'type': DecayType.RETURNS,
            'historical': hist_returns,
            'recent': recent_returns,
            'pct_decline': pct_decline,
            'decay_score': decay_score,
            'confidence': confidence,
            'p_value': p_value,
            't_statistic': t_stat,
            'degrees_freedom': df,
            'is_significant': p_value < self.config.significance_level,
            'message': f"Average returns declined {pct_decline*100:.1f}% (p={p_value:.3f}, t={t_stat:.2f})"
        }

    def _check_consistency_decay(self, historical: dict, recent: dict) -> Optional[dict]:
        """
        Check for consistency decay (increased volatility) with statistical significance.

        Uses F-test for comparing variances to determine if volatility increase
        is statistically significant.
        """
        hist_std = historical.get('return_std', 0)
        recent_std = recent.get('return_std', 0)
        hist_n = historical.get('trade_count', 0)
        recent_n = recent.get('trade_count', 0)

        if hist_std <= 0:
            return None

        # For consistency, INCREASE in std is bad
        pct_increase = (recent_std - hist_std) / hist_std

        if pct_increase < self.config.early_warning_decline_pct:
            return None

        # F-test for variance comparison
        # F = s2_larger^2 / s2_smaller^2
        # For testing if recent variance is significantly GREATER than historical
        if recent_std > hist_std:
            f_stat = (recent_std ** 2) / (hist_std ** 2) if hist_std > 0 else 0
        else:
            # No increase in variance, skip
            return None

        # Approximate p-value for F-test using normal approximation
        # For large samples, ln(F) is approximately normal
        if f_stat > 0 and hist_n > 2 and recent_n > 2:
            # Use log-F approximation
            ln_f = math.log(f_stat)
            # Variance of ln(F) approximately 2/n1 + 2/n2
            var_ln_f = 2 / (hist_n - 1) + 2 / (recent_n - 1)
            z_f = ln_f / math.sqrt(var_ln_f) if var_ln_f > 0 else 0
            p_value = z_to_pvalue(z_f, two_tailed=False)  # One-tailed: testing for increase
        else:
            p_value = 0.5

        # Calculate confidence based on statistical significance
        if p_value < 0.01:
            stat_confidence = 0.90
        elif p_value < 0.05:
            stat_confidence = 0.80
        elif p_value < 0.10:
            stat_confidence = 0.65
        else:
            stat_confidence = 0.45

        # Sample size factor
        sample_factor = min(1.0, (hist_n + recent_n) / 100)

        # Combined confidence
        confidence = stat_confidence * sample_factor

        # Only alert if statistically significant or very large increase
        if p_value > self.config.significance_level and pct_increase < self.config.moderate_decline_pct:
            return None

        # Consistency less weighted (0.6 factor)
        decay_score = min(100, pct_increase * 100 * 0.6 * confidence)

        return {
            'type': DecayType.CONSISTENCY,
            'historical': hist_std,
            'recent': recent_std,
            'pct_decline': pct_increase,  # Actually an increase in volatility
            'decay_score': decay_score,
            'confidence': confidence,
            'p_value': p_value,
            'f_statistic': f_stat,
            'is_significant': p_value < self.config.significance_level,
            'message': f"Return volatility increased {pct_increase*100:.1f}% - less consistent (p={p_value:.3f}, F={f_stat:.2f})"
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
