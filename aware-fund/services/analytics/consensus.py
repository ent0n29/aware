"""
AWARE Analytics - Consensus Signal Detection

Identifies when smart money traders converge on the same market opinion.
When top traders agree, their collective signal is stronger than any individual.

Consensus Types:
1. Strong Consensus - 70%+ of smart money agrees
2. Building Consensus - Trend forming, not yet strong
3. Split Opinion - Smart money divided
4. Contrarian Signal - Smart money vs public sentiment
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum
import math

try:
    from .security import sanitize_market_slug
except ImportError:
    from security import sanitize_market_slug

logger = logging.getLogger(__name__)


class ConsensusStrength(Enum):
    """Strength of smart money consensus"""
    NONE = "NONE"                 # No clear consensus
    WEAK = "WEAK"                 # 50-60% agreement
    MODERATE = "MODERATE"         # 60-70% agreement
    STRONG = "STRONG"             # 70-80% agreement
    VERY_STRONG = "VERY_STRONG"   # 80%+ agreement


class ConsensusDirection(Enum):
    """Direction of the consensus"""
    YES = "YES"                   # Consensus favors YES outcome
    NO = "NO"                     # Consensus favors NO outcome
    SPLIT = "SPLIT"               # No clear direction
    SHIFTING = "SHIFTING"         # Direction changing


@dataclass
class ConsensusSignal:
    """A consensus signal for a specific market"""
    market_slug: str
    title: str

    # Consensus metrics
    strength: ConsensusStrength
    direction: ConsensusDirection
    agreement_pct: float          # % of smart money that agrees

    # Smart money details
    num_traders_analyzed: int
    num_traders_for: int          # Traders supporting consensus
    num_traders_against: int
    total_volume_for: float
    total_volume_against: float

    # Confidence
    confidence_score: float       # 0-100, how confident in signal
    signal_quality: float         # Based on trader quality

    # Market context
    current_price: float          # Current market price
    implied_prob_shift: float     # How much smart money disagrees with market

    # Timing
    first_trade_at: datetime
    last_trade_at: datetime
    detected_at: datetime


@dataclass
class ConsensusConfig:
    """Configuration for consensus detection"""
    # Lookback period
    lookback_hours: int = 48

    # Minimum requirements
    min_traders: int = 3          # Need at least 3 smart traders
    min_volume: float = 5000      # $5K minimum smart money volume
    min_total_score: float = 60.0  # Only count high-score traders

    # Consensus thresholds
    weak_threshold: float = 0.55        # 55% for weak
    moderate_threshold: float = 0.65    # 65% for moderate
    strong_threshold: float = 0.75      # 75% for strong
    very_strong_threshold: float = 0.85  # 85% for very strong


class ConsensusDetector:
    """
    Detects smart money consensus across markets.

    Usage:
        detector = ConsensusDetector(ch_client)
        signals = detector.scan_all_markets()

        # Or for a specific market:
        signal = detector.analyze_market("market-slug")
    """

    def __init__(self, clickhouse_client, config: Optional[ConsensusConfig] = None):
        self.ch = clickhouse_client
        self.config = config or ConsensusConfig()

    def scan_all_markets(self) -> list[ConsensusSignal]:
        """Scan all active markets for consensus signals"""
        logger.info("Scanning all markets for consensus signals...")

        # Get active markets with smart money activity
        markets = self._get_active_markets()
        logger.info(f"Analyzing {len(markets)} active markets")

        signals = []
        for market_slug, title in markets:
            try:
                signal = self.analyze_market(market_slug, title)
                if signal and signal.strength != ConsensusStrength.NONE:
                    signals.append(signal)
            except Exception as e:
                logger.warning(f"Error analyzing {market_slug}: {e}")

        # Sort by strength and confidence
        signals.sort(
            key=lambda x: (x.agreement_pct, x.confidence_score),
            reverse=True
        )

        logger.info(f"Found {len(signals)} consensus signals")
        return signals

    def analyze_market(
        self,
        market_slug: str,
        title: Optional[str] = None
    ) -> Optional[ConsensusSignal]:
        """
        Analyze a specific market for smart money consensus.

        Returns ConsensusSignal if consensus detected, None if insufficient data.
        """
        # Get smart money trades for this market
        trades = self._get_smart_money_trades(market_slug)

        if not trades:
            return None

        # Aggregate by trader and direction
        trader_positions = self._aggregate_positions(trades)

        if len(trader_positions) < self.config.min_traders:
            return None

        # Calculate consensus metrics
        yes_traders = [t for t in trader_positions if t['net_direction'] == 'YES']
        no_traders = [t for t in trader_positions if t['net_direction'] == 'NO']

        num_yes = len(yes_traders)
        num_no = len(no_traders)
        total_traders = num_yes + num_no

        if total_traders == 0:
            return None

        # Calculate agreement percentage
        majority_count = max(num_yes, num_no)
        agreement_pct = majority_count / total_traders

        # Determine direction
        if num_yes > num_no:
            direction = ConsensusDirection.YES
            traders_for = yes_traders
            traders_against = no_traders
        elif num_no > num_yes:
            direction = ConsensusDirection.NO
            traders_for = no_traders
            traders_against = yes_traders
        else:
            direction = ConsensusDirection.SPLIT
            traders_for = yes_traders
            traders_against = no_traders

        # Calculate volumes
        volume_for = sum(t['total_volume'] for t in traders_for)
        volume_against = sum(t['total_volume'] for t in traders_against)
        total_volume = volume_for + volume_against

        if total_volume < self.config.min_volume:
            return None

        # Determine strength
        strength = self._determine_strength(agreement_pct)

        # Calculate confidence
        confidence = self._calculate_confidence(
            trader_positions, traders_for, volume_for, total_volume
        )

        # Calculate signal quality (weighted by trader scores)
        signal_quality = self._calculate_signal_quality(traders_for)

        # Get market price (placeholder - would query market data)
        current_price = 0.5  # Would fetch from API

        # Calculate implied probability shift
        smart_money_prob = volume_for / total_volume if total_volume > 0 else 0.5
        implied_shift = smart_money_prob - current_price

        # Get time range
        all_times = [t['last_trade'] for t in trader_positions if t['last_trade']]
        first_trade = min(all_times) if all_times else datetime.utcnow()
        last_trade = max(all_times) if all_times else datetime.utcnow()

        return ConsensusSignal(
            market_slug=market_slug,
            title=title or market_slug,
            strength=strength,
            direction=direction,
            agreement_pct=agreement_pct,
            num_traders_analyzed=total_traders,
            num_traders_for=len(traders_for),
            num_traders_against=len(traders_against),
            total_volume_for=volume_for,
            total_volume_against=volume_against,
            confidence_score=confidence,
            signal_quality=signal_quality,
            current_price=current_price,
            implied_prob_shift=implied_shift,
            first_trade_at=first_trade,
            last_trade_at=last_trade,
            detected_at=datetime.utcnow(),
        )

    def _get_active_markets(self) -> list[tuple[str, str]]:
        """Get markets with recent smart money activity"""
        query = f"""
        SELECT DISTINCT
            t.market_slug,
            any(t.title) as title
        FROM polybot.aware_global_trades t
        INNER JOIN (
            SELECT username
            FROM polybot.aware_smart_money_scores FINAL
            WHERE total_score >= {self.config.min_total_score}
        ) s ON t.username = s.username
        WHERE t.ts >= now() - INTERVAL {self.config.lookback_hours} HOUR
        GROUP BY t.market_slug
        HAVING count() >= {self.config.min_traders}
        ORDER BY count() DESC
        LIMIT 100
        """

        try:
            result = self.ch.query(query)
            return [(row[0], row[1]) for row in result.result_rows if row[0]]
        except Exception as e:
            logger.error(f"Error getting active markets: {e}")
            return []

    def _get_smart_money_trades(self, market_slug: str) -> list[dict]:
        """Get smart money trades for a market"""
        safe_market_slug = sanitize_market_slug(market_slug)
        query = f"""
        SELECT
            t.username,
            t.side,
            t.outcome,
            t.size,
            t.notional,
            t.price,
            t.ts,
            s.total_score
        FROM polybot.aware_global_trades t
        INNER JOIN (
            SELECT username, total_score
            FROM polybot.aware_smart_money_scores FINAL
            WHERE total_score >= {self.config.min_total_score}
        ) s ON t.username = s.username
        WHERE
            t.market_slug = '{safe_market_slug}'
            AND t.ts >= now() - INTERVAL {self.config.lookback_hours} HOUR
        ORDER BY t.ts DESC
        """

        try:
            result = self.ch.query(query)
            trades = []

            for row in result.result_rows:
                trades.append({
                    'username': row[0],
                    'side': row[1],
                    'outcome': row[2],
                    'size': row[3],
                    'notional': row[4],
                    'price': row[5],
                    'ts': row[6],
                    'total_score': row[7],
                })

            return trades

        except Exception as e:
            logger.error(f"Error getting trades for {market_slug}: {e}")
            return []

    def _aggregate_positions(self, trades: list[dict]) -> list[dict]:
        """Aggregate trades by trader to get net positions"""
        by_trader = {}

        for t in trades:
            username = t['username']
            if username not in by_trader:
                by_trader[username] = {
                    'username': username,
                    'total_score': t['total_score'],
                    'yes_volume': 0,
                    'no_volume': 0,
                    'total_volume': 0,
                    'trade_count': 0,
                    'last_trade': None,
                }

            # Determine direction
            outcome = t['outcome'].upper() if t['outcome'] else ''
            side = t['side'].upper() if t['side'] else ''
            notional = t['notional'] or 0

            # BUY YES or SELL NO = YES direction
            # SELL YES or BUY NO = NO direction
            if (side == 'BUY' and 'YES' in outcome) or (side == 'SELL' and 'NO' in outcome):
                by_trader[username]['yes_volume'] += notional
            else:
                by_trader[username]['no_volume'] += notional

            by_trader[username]['total_volume'] += notional
            by_trader[username]['trade_count'] += 1

            if t['ts']:
                if not by_trader[username]['last_trade'] or t['ts'] > by_trader[username]['last_trade']:
                    by_trader[username]['last_trade'] = t['ts']

        # Determine net direction for each trader
        positions = []
        for username, data in by_trader.items():
            if data['yes_volume'] > data['no_volume']:
                data['net_direction'] = 'YES'
            elif data['no_volume'] > data['yes_volume']:
                data['net_direction'] = 'NO'
            else:
                data['net_direction'] = 'NEUTRAL'

            # Only include traders with a clear direction
            if data['net_direction'] != 'NEUTRAL':
                positions.append(data)

        return positions

    def _determine_strength(self, agreement_pct: float) -> ConsensusStrength:
        """Determine consensus strength from agreement percentage"""
        if agreement_pct >= self.config.very_strong_threshold:
            return ConsensusStrength.VERY_STRONG
        elif agreement_pct >= self.config.strong_threshold:
            return ConsensusStrength.STRONG
        elif agreement_pct >= self.config.moderate_threshold:
            return ConsensusStrength.MODERATE
        elif agreement_pct >= self.config.weak_threshold:
            return ConsensusStrength.WEAK
        else:
            return ConsensusStrength.NONE

    def _calculate_confidence(
        self,
        all_positions: list[dict],
        majority_positions: list[dict],
        volume_for: float,
        total_volume: float
    ) -> float:
        """Calculate confidence score for the consensus signal"""
        # Factors:
        # 1. Number of traders (more = higher confidence)
        # 2. Volume concentration (more volume = higher confidence)
        # 3. Trader quality (higher scores = higher confidence)

        num_traders = len(all_positions)
        num_majority = len(majority_positions)

        # Trader count factor (log scale, max out at ~20 traders)
        trader_factor = min(1.0, math.log(num_traders + 1) / math.log(21))

        # Volume factor
        volume_factor = volume_for / total_volume if total_volume > 0 else 0

        # Quality factor (average score of majority traders)
        if majority_positions:
            avg_score = sum(p['total_score'] for p in majority_positions) / len(majority_positions)
            quality_factor = avg_score / 100
        else:
            quality_factor = 0

        # Combined confidence
        confidence = (
            0.30 * trader_factor +
            0.40 * volume_factor +
            0.30 * quality_factor
        ) * 100

        return min(100, max(0, confidence))

    def _calculate_signal_quality(self, majority_positions: list[dict]) -> float:
        """Calculate signal quality based on trader scores"""
        if not majority_positions:
            return 0

        # Weight by both score and volume
        total_weight = 0
        weighted_score = 0

        for p in majority_positions:
            weight = p['total_volume']
            score = p['total_score']
            weighted_score += weight * score
            total_weight += weight

        if total_weight > 0:
            return weighted_score / total_weight

        return 0

    def get_consensus_summary(self, signals: list[ConsensusSignal]) -> dict:
        """Get summary of consensus signals for display"""
        by_strength = {}
        for s in signals:
            strength = s.strength.value
            if strength not in by_strength:
                by_strength[strength] = []

            by_strength[strength].append({
                'market': s.market_slug,
                'title': s.title,
                'direction': s.direction.value,
                'agreement': round(s.agreement_pct * 100, 1),
                'confidence': round(s.confidence_score, 1),
                'traders': s.num_traders_analyzed,
                'volume': round(s.total_volume_for + s.total_volume_against, 0),
                'implied_shift': round(s.implied_prob_shift * 100, 1),
            })

        return {
            'scan_time': datetime.utcnow().isoformat(),
            'total_signals': len(signals),
            'very_strong': len([s for s in signals if s.strength == ConsensusStrength.VERY_STRONG]),
            'strong': len([s for s in signals if s.strength == ConsensusStrength.STRONG]),
            'moderate': len([s for s in signals if s.strength == ConsensusStrength.MODERATE]),
            'weak': len([s for s in signals if s.strength == ConsensusStrength.WEAK]),
            'by_strength': by_strength,
        }

    def get_market_smart_money_summary(self, market_slug: str) -> dict:
        """Get detailed smart money analysis for a specific market"""
        signal = self.analyze_market(market_slug)

        if not signal:
            return {
                'market': market_slug,
                'status': 'INSUFFICIENT_DATA',
                'message': 'Not enough smart money activity to analyze'
            }

        return {
            'market': market_slug,
            'title': signal.title,
            'consensus': {
                'strength': signal.strength.value,
                'direction': signal.direction.value,
                'agreement_pct': round(signal.agreement_pct * 100, 1),
            },
            'smart_money': {
                'traders_analyzed': signal.num_traders_analyzed,
                'traders_for': signal.num_traders_for,
                'traders_against': signal.num_traders_against,
                'volume_for': round(signal.total_volume_for, 2),
                'volume_against': round(signal.total_volume_against, 2),
            },
            'confidence': round(signal.confidence_score, 1),
            'signal_quality': round(signal.signal_quality, 1),
            'market_context': {
                'current_price': round(signal.current_price, 3),
                'implied_shift': round(signal.implied_prob_shift * 100, 1),
            },
            'timing': {
                'first_trade': signal.first_trade_at.isoformat() if signal.first_trade_at else None,
                'last_trade': signal.last_trade_at.isoformat() if signal.last_trade_at else None,
                'analyzed_at': signal.detected_at.isoformat(),
            }
        }


def detect_market_consensus(
    clickhouse_client,
    market_slug: Optional[str] = None,
    min_traders: int = 3,
    min_volume: float = 5000,
    lookback_hours: int = 48
) -> dict:
    """
    Detect when multiple smart money traders agree on market direction.

    This is the main entry point for consensus detection. It identifies markets
    where top traders are converging on the same opinion, which can be a
    strong signal for trading decisions.

    Algorithm:
    1. Identify smart money traders (based on score threshold)
    2. Aggregate their positions by market and direction
    3. Calculate agreement percentage (% of traders on same side)
    4. Weight by trader quality and volume
    5. Return consensus signals above threshold

    Args:
        clickhouse_client: ClickHouse database client
        market_slug: Optional specific market to analyze (None = all markets)
        min_traders: Minimum smart money traders for valid signal
        min_volume: Minimum aggregate volume for valid signal
        lookback_hours: Time window for analysis

    Returns:
        Dictionary with consensus analysis results
    """
    logger.info(f"Running consensus detection (lookback={lookback_hours}h, min_traders={min_traders})")

    config = ConsensusConfig(
        min_traders=min_traders,
        min_volume=min_volume,
        lookback_hours=lookback_hours
    )
    detector = ConsensusDetector(clickhouse_client, config)

    if market_slug:
        # Single market analysis
        signal = detector.analyze_market(market_slug)
        if not signal:
            return {
                'market': market_slug,
                'status': 'INSUFFICIENT_DATA',
                'message': 'Not enough smart money activity for consensus detection'
            }

        return {
            'market': market_slug,
            'status': 'ANALYZED',
            'consensus': {
                'strength': signal.strength.value,
                'direction': signal.direction.value,
                'agreement_pct': round(signal.agreement_pct * 100, 1),
                'confidence': round(signal.confidence_score, 1),
            },
            'details': {
                'traders_analyzed': signal.num_traders_analyzed,
                'traders_for': signal.num_traders_for,
                'traders_against': signal.num_traders_against,
                'volume_for': round(signal.total_volume_for, 2),
                'volume_against': round(signal.total_volume_against, 2),
                'signal_quality': round(signal.signal_quality, 1),
            },
            'market_context': {
                'current_price': round(signal.current_price, 3),
                'implied_shift': round(signal.implied_prob_shift * 100, 1),
            },
            'timing': {
                'first_trade': signal.first_trade_at.isoformat() if signal.first_trade_at else None,
                'last_trade': signal.last_trade_at.isoformat() if signal.last_trade_at else None,
            }
        }

    # Multi-market scan
    signals = detector.scan_all_markets()

    # Group by consensus strength
    by_strength = {
        'VERY_STRONG': [],
        'STRONG': [],
        'MODERATE': [],
        'WEAK': [],
    }

    for signal in signals:
        strength = signal.strength.value
        if strength in by_strength:
            by_strength[strength].append({
                'market': signal.market_slug,
                'title': signal.title,
                'direction': signal.direction.value,
                'agreement_pct': round(signal.agreement_pct * 100, 1),
                'confidence': round(signal.confidence_score, 1),
                'traders': signal.num_traders_analyzed,
                'volume': round(signal.total_volume_for + signal.total_volume_against, 0),
                'implied_shift': round(signal.implied_prob_shift * 100, 1),
            })

    # Calculate summary statistics
    strong_signals = [s for s in signals if s.strength in (ConsensusStrength.VERY_STRONG, ConsensusStrength.STRONG)]
    yes_consensus = [s for s in strong_signals if s.direction == ConsensusDirection.YES]
    no_consensus = [s for s in strong_signals if s.direction == ConsensusDirection.NO]

    return {
        'status': 'SCAN_COMPLETE',
        'scan_params': {
            'lookback_hours': lookback_hours,
            'min_traders': min_traders,
            'min_volume': min_volume,
        },
        'summary': {
            'total_signals': len(signals),
            'strong_signals': len(strong_signals),
            'yes_consensus': len(yes_consensus),
            'no_consensus': len(no_consensus),
            'average_confidence': round(
                sum(s.confidence_score for s in signals) / len(signals), 1
            ) if signals else 0,
        },
        'by_strength': by_strength,
        'top_signals': [
            {
                'market': s.market_slug,
                'title': s.title,
                'strength': s.strength.value,
                'direction': s.direction.value,
                'agreement_pct': round(s.agreement_pct * 100, 1),
                'confidence': round(s.confidence_score, 1),
            }
            for s in sorted(signals, key=lambda x: x.confidence_score, reverse=True)[:10]
        ],
        'scan_time': datetime.utcnow().isoformat(),
    }


def run_consensus_scan(clickhouse_client) -> dict:
    """Convenience function to run full consensus scan"""
    detector = ConsensusDetector(clickhouse_client)
    signals = detector.scan_all_markets()
    return detector.get_consensus_summary(signals)
