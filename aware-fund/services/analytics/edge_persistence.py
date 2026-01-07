"""
AWARE Analytics - Edge Persistence Prediction

Predicts whether a trader's edge will persist into the future.
Critical for index composition - we want traders whose edge is DURABLE.

Persistence Factors:
1. Strategy Type - Some strategies persist longer (fundamentals > momentum)
2. Market Regime - How dependent is performance on current conditions?
3. Track Record Length - Longer track records = more confidence
4. Consistency - Steady performers > streaky performers
5. Capacity - Is the strategy hitting volume limits?
6. Competition - How crowded is their strategy space?

Output: Probability that trader maintains positive edge over next 30/60/90 days.
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


class PersistenceRisk(Enum):
    """Risk levels for edge persistence"""
    LOW = "LOW"           # High confidence edge will persist
    MODERATE = "MODERATE" # Some uncertainty
    HIGH = "HIGH"         # Significant risk of edge decay
    VERY_HIGH = "VERY_HIGH" # Edge likely to fade soon


class StrategyDurability(Enum):
    """How durable different strategy types typically are"""
    HIGH_DURABILITY = "HIGH"       # Fundamental, arbitrage
    MEDIUM_DURABILITY = "MEDIUM"   # Event-driven, swing
    LOW_DURABILITY = "LOW"         # Momentum, scalping


@dataclass
class PersistencePrediction:
    """Prediction of edge persistence for a trader"""
    username: str

    # Main predictions
    persist_prob_30d: float    # P(positive edge in next 30 days)
    persist_prob_60d: float    # P(positive edge in next 60 days)
    persist_prob_90d: float    # P(positive edge in next 90 days)

    # Risk assessment
    persistence_risk: PersistenceRisk
    confidence: float          # How confident in this prediction

    # Contributing factors
    factors: dict              # Factor name -> contribution to prediction

    # Expected performance
    expected_sharpe_30d: float
    expected_sharpe_range: tuple[float, float]  # 95% confidence interval

    # Recommendations
    index_recommendation: str  # INCLUDE, REDUCE_WEIGHT, EXCLUDE, WATCH
    rebalance_suggestion: str

    predicted_at: datetime


@dataclass
class PersistenceConfig:
    """Configuration for persistence prediction"""
    # Minimum data requirements
    min_trades: int = 30
    min_days_active: int = 14

    # Strategy durability mapping
    high_durability_strategies: list[str] = None
    medium_durability_strategies: list[str] = None

    # Weighting for factors
    strategy_type_weight: float = 0.25
    consistency_weight: float = 0.25
    track_record_weight: float = 0.20
    recent_performance_weight: float = 0.15
    market_conditions_weight: float = 0.15

    def __post_init__(self):
        if self.high_durability_strategies is None:
            self.high_durability_strategies = [
                "ARBITRAGEUR", "MARKET_MAKER", "DIRECTIONAL_FUNDAMENTAL"
            ]
        if self.medium_durability_strategies is None:
            self.medium_durability_strategies = [
                "EVENT_DRIVEN", "SWING_TRADER", "DIRECTIONAL_MOMENTUM"
            ]


class EdgePersistencePredictor:
    """
    Predicts edge persistence for traders.

    Usage:
        predictor = EdgePersistencePredictor(ch_client)
        prediction = predictor.predict("username")
        predictions = predictor.predict_all()
    """

    def __init__(self, clickhouse_client, config: Optional[PersistenceConfig] = None):
        self.ch = clickhouse_client
        self.config = config or PersistenceConfig()

    def predict_all(self) -> list[PersistencePrediction]:
        """Predict persistence for all eligible traders"""
        logger.info("Predicting edge persistence for all traders...")

        traders = self._get_eligible_traders()
        logger.info(f"Analyzing {len(traders)} traders")

        predictions = []
        for username in traders:
            try:
                pred = self.predict(username)
                if pred:
                    predictions.append(pred)
            except Exception as e:
                logger.warning(f"Error predicting {username}: {e}")

        # Sort by persistence probability
        predictions.sort(key=lambda x: x.persist_prob_30d, reverse=True)

        logger.info(f"Generated {len(predictions)} persistence predictions")
        return predictions

    def predict(self, username: str) -> Optional[PersistencePrediction]:
        """
        Predict edge persistence for a single trader.

        Uses multiple factors to estimate probability of continued positive edge.
        """
        # Get trader metrics
        metrics = self._get_trader_metrics(username)
        if not metrics:
            return None

        if metrics['trade_count'] < self.config.min_trades:
            return None

        # Calculate factor contributions
        factors = {}

        # 1. Strategy Type Factor
        strategy_factor = self._calculate_strategy_factor(metrics)
        factors['strategy_type'] = strategy_factor

        # 2. Consistency Factor
        consistency_factor = self._calculate_consistency_factor(metrics)
        factors['consistency'] = consistency_factor

        # 3. Track Record Factor
        track_record_factor = self._calculate_track_record_factor(metrics)
        factors['track_record'] = track_record_factor

        # 4. Recent Performance Factor
        recent_factor = self._calculate_recent_performance_factor(username)
        factors['recent_performance'] = recent_factor

        # 5. Market Conditions Factor
        conditions_factor = self._calculate_market_conditions_factor(metrics)
        factors['market_conditions'] = conditions_factor

        # Combine factors into persistence probability
        weighted_score = (
            self.config.strategy_type_weight * strategy_factor +
            self.config.consistency_weight * consistency_factor +
            self.config.track_record_weight * track_record_factor +
            self.config.recent_performance_weight * recent_factor +
            self.config.market_conditions_weight * conditions_factor
        )

        # Convert to probability (sigmoid-like transformation)
        base_prob = 1 / (1 + math.exp(-2 * (weighted_score - 0.5)))

        # Adjust for different time horizons (longer = less certain)
        prob_30d = base_prob
        prob_60d = base_prob * 0.90  # 10% decay
        prob_90d = base_prob * 0.80  # 20% decay

        # Determine risk level
        risk = self._determine_risk_level(prob_30d, consistency_factor)

        # Calculate expected Sharpe
        current_sharpe = metrics.get('sharpe_ratio', 0)
        expected_sharpe = current_sharpe * prob_30d
        sharpe_std = abs(current_sharpe) * 0.3  # 30% uncertainty
        sharpe_range = (
            max(0, expected_sharpe - 2 * sharpe_std),
            expected_sharpe + 2 * sharpe_std
        )

        # Generate recommendation
        recommendation = self._generate_recommendation(prob_30d, risk, metrics)
        rebalance = self._generate_rebalance_suggestion(prob_30d, risk)

        # Calculate confidence
        confidence = min(0.95, track_record_factor * consistency_factor)

        return PersistencePrediction(
            username=username,
            persist_prob_30d=round(prob_30d, 3),
            persist_prob_60d=round(prob_60d, 3),
            persist_prob_90d=round(prob_90d, 3),
            persistence_risk=risk,
            confidence=round(confidence, 3),
            factors={k: round(v, 3) for k, v in factors.items()},
            expected_sharpe_30d=round(expected_sharpe, 2),
            expected_sharpe_range=(round(sharpe_range[0], 2), round(sharpe_range[1], 2)),
            index_recommendation=recommendation,
            rebalance_suggestion=rebalance,
            predicted_at=datetime.utcnow()
        )

    def _get_eligible_traders(self) -> list[str]:
        """Get traders eligible for prediction"""
        query = f"""
        SELECT DISTINCT proxy_address
        FROM polybot.aware_global_trades
        WHERE ts >= now() - INTERVAL 90 DAY
        GROUP BY proxy_address
        HAVING count() >= {self.config.min_trades}
        LIMIT 2000
        """

        try:
            result = self.ch.query(query)
            return [row[0] for row in result.result_rows if row[0]]
        except Exception as e:
            logger.error(f"Error getting eligible traders: {e}")
            return []

    def _get_trader_metrics(self, username: str) -> Optional[dict]:
        """Get comprehensive metrics for a trader"""
        safe_username = sanitize_username(username)
        query = f"""
        SELECT
            count() as trade_count,
            sum(notional) as total_pnl,
            avg(notional) as avg_return,
            stddevPop(notional) as return_std,
            uniq(market_slug) as unique_markets,
            min(ts) as first_trade,
            max(ts) as last_trade,
            sum(CASE WHEN notional > 0 THEN 1 ELSE 0 END) / count() as win_rate
        FROM polybot.aware_global_trades
        WHERE username = '{safe_username}'
        """

        try:
            result = self.ch.query(query)
            if not result.result_rows:
                return None

            row = result.result_rows[0]
            avg_return = row[2] or 0
            return_std = row[3] or 1

            # Get strategy type from scores table
            strategy_query = f"""
            SELECT strategy_type, strategy_confidence
            FROM polybot.aware_smart_money_scores FINAL
            WHERE username = '{safe_username}'
            LIMIT 1
            """

            strategy_result = self.ch.query(strategy_query)
            strategy_type = "UNKNOWN"
            strategy_confidence = 0.5

            if strategy_result.result_rows:
                strategy_type = strategy_result.result_rows[0][0] or "UNKNOWN"
                strategy_confidence = strategy_result.result_rows[0][1] or 0.5

            return {
                'trade_count': row[0],
                'total_pnl': row[1] or 0,
                'avg_return': avg_return,
                'return_std': return_std,
                'sharpe_ratio': avg_return / return_std if return_std > 0 else 0,
                'unique_markets': row[4],
                'first_trade': row[5],
                'last_trade': row[6],
                'win_rate': row[7] or 0,
                'strategy_type': strategy_type,
                'strategy_confidence': strategy_confidence,
                'days_active': (row[6] - row[5]).days if row[5] and row[6] else 0
            }

        except Exception as e:
            logger.error(f"Error getting metrics for {username}: {e}")
            return None

    def _calculate_strategy_factor(self, metrics: dict) -> float:
        """Calculate persistence factor from strategy type"""
        strategy = metrics.get('strategy_type', 'UNKNOWN')

        if strategy in self.config.high_durability_strategies:
            return 0.85
        elif strategy in self.config.medium_durability_strategies:
            return 0.65
        else:
            return 0.45

    def _calculate_consistency_factor(self, metrics: dict) -> float:
        """Calculate persistence factor from performance consistency"""
        sharpe = metrics.get('sharpe_ratio', 0)
        win_rate = metrics.get('win_rate', 0.5)
        return_std = metrics.get('return_std', 1)
        avg_return = metrics.get('avg_return', 0)

        # High Sharpe = consistent
        sharpe_score = min(1.0, sharpe / 2.0) if sharpe > 0 else 0

        # High win rate = consistent
        winrate_score = (win_rate - 0.5) * 2 if win_rate > 0.5 else 0

        # Low CV (coefficient of variation) = consistent
        cv = return_std / abs(avg_return) if avg_return != 0 else 10
        cv_score = max(0, 1 - cv / 5)

        return (sharpe_score * 0.4 + winrate_score * 0.3 + cv_score * 0.3)

    def _calculate_track_record_factor(self, metrics: dict) -> float:
        """Calculate persistence factor from track record length"""
        days_active = metrics.get('days_active', 0)
        trade_count = metrics.get('trade_count', 0)

        # More days = higher confidence
        days_score = min(1.0, days_active / 90)  # Max out at 90 days

        # More trades = higher confidence
        trades_score = min(1.0, trade_count / 200)  # Max out at 200 trades

        return days_score * 0.6 + trades_score * 0.4

    def _calculate_recent_performance_factor(self, username: str) -> float:
        """Calculate factor from recent vs historical performance"""
        safe_username = sanitize_username(username)
        # Get recent (7 day) vs overall performance
        query = f"""
        SELECT
            avg(notional) as overall_avg,
            avgIf(notional, ts >= now() - INTERVAL 7 DAY) as recent_avg
        FROM polybot.aware_global_trades
        WHERE username = '{safe_username}'
        """

        try:
            result = self.ch.query(query)
            if not result.result_rows:
                return 0.5

            overall = result.result_rows[0][0] or 0
            recent = result.result_rows[0][1] or 0

            if overall == 0:
                return 0.5

            # Recent outperforming = positive, underperforming = negative
            ratio = recent / overall if overall != 0 else 1

            # Transform to 0-1 score
            if ratio >= 1:
                return min(1.0, 0.5 + (ratio - 1) * 0.5)
            else:
                return max(0, 0.5 * ratio)

        except Exception as e:
            logger.debug(f"Recent performance check failed: {e}")
            return 0.5

    def _calculate_market_conditions_factor(self, metrics: dict) -> float:
        """Calculate how dependent performance is on market conditions"""
        # Diversified across markets = less dependent on conditions
        unique_markets = metrics.get('unique_markets', 1)

        # More markets = more robust
        diversification_score = min(1.0, unique_markets / 10)

        return 0.5 + diversification_score * 0.5

    def _determine_risk_level(self, prob: float, consistency: float) -> PersistenceRisk:
        """Determine overall risk level"""
        if prob >= 0.75 and consistency >= 0.7:
            return PersistenceRisk.LOW
        elif prob >= 0.55:
            return PersistenceRisk.MODERATE
        elif prob >= 0.35:
            return PersistenceRisk.HIGH
        else:
            return PersistenceRisk.VERY_HIGH

    def _generate_recommendation(
        self,
        prob: float,
        risk: PersistenceRisk,
        metrics: dict
    ) -> str:
        """Generate index inclusion recommendation"""
        if risk == PersistenceRisk.LOW and prob >= 0.75:
            return "INCLUDE"
        elif risk == PersistenceRisk.MODERATE:
            return "INCLUDE" if metrics.get('sharpe_ratio', 0) > 1.5 else "REDUCE_WEIGHT"
        elif risk == PersistenceRisk.HIGH:
            return "REDUCE_WEIGHT"
        else:
            return "EXCLUDE"

    def _generate_rebalance_suggestion(self, prob: float, risk: PersistenceRisk) -> str:
        """Generate rebalancing suggestion"""
        if risk == PersistenceRisk.LOW:
            return "Maintain current weight, review quarterly"
        elif risk == PersistenceRisk.MODERATE:
            return "Monitor monthly, reduce if performance declines"
        elif risk == PersistenceRisk.HIGH:
            return "Reduce weight by 50%, review weekly"
        else:
            return "Remove from index or reduce to minimum weight"

    def get_persistence_summary(self, predictions: list[PersistencePrediction]) -> dict:
        """Generate summary of persistence predictions"""
        by_risk = {}
        by_recommendation = {}

        for p in predictions:
            risk = p.persistence_risk.value
            by_risk[risk] = by_risk.get(risk, 0) + 1

            rec = p.index_recommendation
            by_recommendation[rec] = by_recommendation.get(rec, 0) + 1

        avg_prob = sum(p.persist_prob_30d for p in predictions) / len(predictions) if predictions else 0

        return {
            'prediction_time': datetime.utcnow().isoformat(),
            'traders_analyzed': len(predictions),
            'avg_persistence_prob_30d': round(avg_prob, 3),
            'by_risk_level': by_risk,
            'by_recommendation': by_recommendation,
            'high_persistence': [
                {
                    'username': p.username,
                    'prob_30d': p.persist_prob_30d,
                    'expected_sharpe': p.expected_sharpe_30d
                }
                for p in predictions if p.persist_prob_30d >= 0.75
            ][:10],
            'at_risk': [
                {
                    'username': p.username,
                    'prob_30d': p.persist_prob_30d,
                    'risk': p.persistence_risk.value
                }
                for p in predictions if p.persistence_risk in [PersistenceRisk.HIGH, PersistenceRisk.VERY_HIGH]
            ][:10]
        }


def run_persistence_prediction(clickhouse_client) -> dict:
    """Convenience function to run persistence prediction"""
    predictor = EdgePersistencePredictor(clickhouse_client)
    predictions = predictor.predict_all()
    return predictor.get_persistence_summary(predictions)
