"""
AWARE Analytics - Scoring Job

Calculates Smart Money Scores for all traders.
"""

import logging
from dataclasses import dataclass
from typing import Optional
from enum import Enum

from clickhouse_client import ClickHouseClient, TraderMetrics, TraderScore

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    """Trader strategy classification"""
    UNKNOWN = "UNKNOWN"
    ARBITRAGEUR = "ARBITRAGEUR"
    MARKET_MAKER = "MARKET_MAKER"
    DIRECTIONAL_FUNDAMENTAL = "DIRECTIONAL_FUNDAMENTAL"
    DIRECTIONAL_MOMENTUM = "DIRECTIONAL_MOMENTUM"
    EVENT_DRIVEN = "EVENT_DRIVEN"
    SCALPER = "SCALPER"
    HYBRID = "HYBRID"


class TraderTier(Enum):
    """Trader tier based on Smart Money Score"""
    BRONZE = "BRONZE"      # Score 0-39
    SILVER = "SILVER"      # Score 40-59
    GOLD = "GOLD"          # Score 60-79
    DIAMOND = "DIAMOND"    # Score 80-100


@dataclass
class ScoringConfig:
    """Configuration for Smart Money Score calculation"""
    profitability_weight: float = 0.40
    risk_adjusted_weight: float = 0.30
    consistency_weight: float = 0.20
    track_record_weight: float = 0.10

    min_trades: int = 10
    min_volume_usd: float = 100.0


class SmartMoneyScorer:
    """Calculates Smart Money Scores for traders"""

    def __init__(self, config: Optional[ScoringConfig] = None):
        self.config = config or ScoringConfig()

    def calculate_score(
        self,
        metrics: TraderMetrics,
        strategy_indicators: dict,
        all_trader_pnls: Optional[list[float]] = None
    ) -> TraderScore:
        """
        Calculate Smart Money Score for a trader.

        Args:
            metrics: Trader metrics from ClickHouse
            strategy_indicators: complete_set_ratio, direction_bias
            all_trader_pnls: List of all trader P&Ls for percentile ranking

        Returns:
            TraderScore
        """
        # Calculate component scores
        profitability = self._score_profitability(metrics, all_trader_pnls)
        risk_adjusted = self._score_risk_management(metrics)
        consistency = self._score_consistency(metrics)
        track_record = self._score_track_record(metrics)

        # Classify strategy
        strategy_type, confidence = self._classify_strategy(
            metrics, strategy_indicators
        )

        # Apply strategy adjustments
        profitability, risk_adjusted, consistency, track_record = \
            self._apply_strategy_adjustments(
                strategy_type, profitability, risk_adjusted,
                consistency, track_record
            )

        # Calculate weighted total
        total = (
            profitability * self.config.profitability_weight +
            risk_adjusted * self.config.risk_adjusted_weight +
            consistency * self.config.consistency_weight +
            track_record * self.config.track_record_weight
        )

        total_score = int(min(100, max(0, round(total))))
        tier = self._get_tier(total_score)

        return TraderScore(
            proxy_address=metrics.proxy_address,
            username=metrics.username,
            total_score=total_score,
            tier=tier.value,
            profitability_score=profitability,
            risk_adjusted_score=risk_adjusted,
            consistency_score=consistency,
            track_record_score=track_record,
            strategy_type=strategy_type.value,
            strategy_confidence=confidence,
            rank=0  # Set later when ranking all traders
        )

    def _score_profitability(
        self,
        metrics: TraderMetrics,
        all_pnls: Optional[list[float]] = None
    ) -> float:
        """Score based on P&L"""
        pnl = metrics.total_pnl

        if pnl <= 0:
            return max(0, 20 + (pnl / 100))

        # Use percentile ranking if peer data available
        if all_pnls and len(all_pnls) > 10:
            below = sum(1 for p in all_pnls if p < pnl)
            percentile = (below / len(all_pnls)) * 100
            return min(percentile, 95)

        # Fallback: absolute P&L tiers
        if pnl >= 100000:
            return 95
        elif pnl >= 50000:
            return 85
        elif pnl >= 20000:
            return 75
        elif pnl >= 10000:
            return 65
        elif pnl >= 5000:
            return 55
        elif pnl >= 1000:
            return 45
        else:
            return 35 + (pnl / 1000) * 10

    def _score_risk_management(self, metrics: TraderMetrics) -> float:
        """Score based on risk-adjusted metrics"""
        score = 50.0

        # Volume-weighted position sizing
        avg_size = metrics.avg_trade_size
        if avg_size > 0:
            if avg_size <= 100:
                score += 20  # Small, controlled positions
            elif avg_size <= 500:
                score += 15
            elif avg_size <= 1000:
                score += 10
            else:
                score += 5

        # Trade diversity
        if metrics.unique_markets >= 50:
            score += 30
        elif metrics.unique_markets >= 20:
            score += 25
        elif metrics.unique_markets >= 10:
            score += 20
        elif metrics.unique_markets >= 5:
            score += 15
        else:
            score += 10

        return min(100, score)

    def _score_consistency(self, metrics: TraderMetrics) -> float:
        """Score based on consistency"""
        if metrics.total_trades < 50:
            return metrics.total_trades / 50 * 30

        score = 0.0

        # Trade frequency
        if metrics.days_active > 0:
            trades_per_day = metrics.total_trades / metrics.days_active
            if trades_per_day >= 5:
                score += 30
            elif trades_per_day >= 2:
                score += 25
            elif trades_per_day >= 1:
                score += 20
            elif trades_per_day >= 0.5:
                score += 15
            else:
                score += 10

        # Buy/sell balance
        total = metrics.buy_count + metrics.sell_count
        if total > 0:
            balance = min(metrics.buy_count, metrics.sell_count) / (total / 2)
            score += balance * 35  # 0-35 points for balance

        # Days active bonus
        if metrics.days_active >= 365:
            score += 35
        elif metrics.days_active >= 180:
            score += 30
        elif metrics.days_active >= 90:
            score += 25
        elif metrics.days_active >= 30:
            score += 20
        else:
            score += metrics.days_active / 30 * 20

        return min(100, score)

    def _score_track_record(self, metrics: TraderMetrics) -> float:
        """Score based on track record"""
        score = 0.0

        # Days active
        if metrics.days_active >= 365:
            score += 35
        elif metrics.days_active >= 180:
            score += 30
        elif metrics.days_active >= 90:
            score += 25
        elif metrics.days_active >= 60:
            score += 20
        elif metrics.days_active >= 30:
            score += 15
        else:
            score += metrics.days_active / 30 * 15

        # Volume
        vol = metrics.total_volume_usd
        if vol >= 100000:
            score += 35
        elif vol >= 50000:
            score += 30
        elif vol >= 20000:
            score += 25
        elif vol >= 10000:
            score += 20
        elif vol >= 5000:
            score += 15
        elif vol >= 1000:
            score += 10
        else:
            score += 5

        # Market diversity
        if metrics.unique_markets >= 50:
            score += 30
        elif metrics.unique_markets >= 30:
            score += 25
        elif metrics.unique_markets >= 20:
            score += 20
        elif metrics.unique_markets >= 10:
            score += 15
        elif metrics.unique_markets >= 5:
            score += 10
        else:
            score += 5

        return min(100, score)

    def _classify_strategy(
        self,
        metrics: TraderMetrics,
        indicators: dict
    ) -> tuple[StrategyType, float]:
        """Classify trader strategy"""
        complete_set_ratio = indicators.get('complete_set_ratio', 0)
        direction_bias = indicators.get('direction_bias', 0.5)

        scores = {}

        # Arbitrageur: high complete-set ratio
        arb_score = complete_set_ratio * 100
        if metrics.total_trades > 500:
            arb_score += 20
        scores[StrategyType.ARBITRAGEUR] = min(100, arb_score)

        # Market maker: balanced buys/sells, high frequency
        total = metrics.buy_count + metrics.sell_count
        if total > 0:
            balance = 1 - abs(0.5 - (metrics.buy_count / total)) * 2
            mm_score = balance * 50
            if metrics.total_trades > 500:
                mm_score += 30
            scores[StrategyType.MARKET_MAKER] = min(100, mm_score)

        # Directional: strong direction bias, fewer markets
        dir_score = abs(direction_bias - 0.5) * 100
        if metrics.unique_markets < 50:
            dir_score += 30
        scores[StrategyType.DIRECTIONAL_MOMENTUM] = min(100, dir_score)

        # Find best match
        best_type = max(scores, key=lambda x: scores[x])
        best_score = scores[best_type]

        # Check for hybrid
        sorted_scores = sorted(scores.values(), reverse=True)
        if len(sorted_scores) >= 2 and sorted_scores[0] - sorted_scores[1] < 15:
            return StrategyType.HYBRID, best_score * 0.7

        if best_score < 30:
            return StrategyType.UNKNOWN, best_score

        return best_type, best_score

    def _apply_strategy_adjustments(
        self,
        strategy: StrategyType,
        profitability: float,
        risk_adjusted: float,
        consistency: float,
        track_record: float
    ) -> tuple[float, float, float, float]:
        """Apply strategy-specific adjustments"""
        if strategy == StrategyType.ARBITRAGEUR:
            if consistency < 70:
                consistency *= 0.8
            else:
                consistency = min(100, consistency * 1.1)

        elif strategy == StrategyType.DIRECTIONAL_MOMENTUM:
            if profitability > 60:
                profitability = min(100, profitability * 1.1)

        return profitability, risk_adjusted, consistency, track_record

    def _get_tier(self, score: int) -> TraderTier:
        """Get tier from score"""
        if score >= 80:
            return TraderTier.DIAMOND
        elif score >= 60:
            return TraderTier.GOLD
        elif score >= 40:
            return TraderTier.SILVER
        else:
            return TraderTier.BRONZE


class ScoringJob:
    """Job to calculate and store Smart Money Scores"""

    def __init__(self, ch_client: ClickHouseClient):
        self.ch_client = ch_client
        self.scorer = SmartMoneyScorer()

    def run(self, min_trades: int = 10, max_traders: int = 10000) -> int:
        """
        Run scoring job for all traders.

        Args:
            min_trades: Minimum trades to be scored
            max_traders: Maximum traders to score

        Returns:
            Number of traders scored
        """
        logger.info("Starting scoring job...")

        # Fetch trader metrics
        metrics_list = self.ch_client.get_trader_metrics(
            min_trades=min_trades,
            limit=max_traders
        )

        if not metrics_list:
            logger.warning("No traders to score")
            return 0

        logger.info(f"Fetched metrics for {len(metrics_list)} traders")

        # Collect all P&Ls for percentile ranking
        all_pnls = [m.total_pnl for m in metrics_list if m.total_pnl != 0]

        # OPTIMIZATION: Batch fetch all strategy indicators in one query
        # This replaces 10,000 individual queries with 1 batch query
        all_indicators = self.ch_client.get_all_strategy_indicators(limit=max_traders)
        logger.info(f"Fetched strategy indicators for {len(all_indicators)} traders (batch)")

        # Calculate scores
        scores = []
        profiles = []

        for metrics in metrics_list:
            try:
                # Look up pre-fetched indicators (O(1) dict lookup vs O(n) query)
                indicators = all_indicators.get(
                    metrics.proxy_address,
                    {'complete_set_ratio': 0.0, 'direction_bias': 0.5}
                )

                # Calculate score
                score = self.scorer.calculate_score(metrics, indicators, all_pnls)
                scores.append(score)

                # Build profile - include P&L from metrics (which joins aware_trader_pnl)
                profiles.append({
                    'proxy_address': metrics.proxy_address,
                    'username': metrics.username,
                    'pseudonym': metrics.pseudonym,
                    'total_trades': metrics.total_trades,
                    'total_volume_usd': metrics.total_volume_usd,
                    'unique_markets': metrics.unique_markets,
                    'first_trade_at': metrics.first_trade_at,
                    'last_trade_at': metrics.last_trade_at,
                    'days_active': metrics.days_active,
                    'total_pnl': metrics.total_pnl,  # From aware_trader_pnl
                    'realized_pnl': metrics.total_pnl,  # Same as total_pnl (all realized)
                    'unrealized_pnl': 0.0,
                    'buy_count': metrics.buy_count,
                    'sell_count': metrics.sell_count,
                    'avg_trade_size': metrics.avg_trade_size,
                    'avg_price': metrics.avg_price,
                    'complete_set_ratio': indicators.get('complete_set_ratio', 0),
                    'direction_bias': indicators.get('direction_bias', 0.5),
                    'data_quality': 'good' if metrics.total_trades >= 50 else 'partial'
                })

            except Exception as e:
                logger.warning(f"Failed to score {metrics.proxy_address}: {e}")

        # Sort by score and assign ranks
        scores.sort(key=lambda s: s.total_score, reverse=True)
        for i, score in enumerate(scores):
            score.rank = i + 1

        # Save to ClickHouse
        self.ch_client.save_trader_profiles(profiles)
        saved = self.ch_client.save_smart_money_scores(scores)

        logger.info(f"Scoring complete: {saved} traders scored")
        return saved
