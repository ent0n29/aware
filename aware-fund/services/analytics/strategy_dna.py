"""
AWARE Analytics - Strategy DNA / Fingerprinting

Identifies unique trading strategies through behavioral clustering.
Each trader gets a "Strategy DNA" - a fingerprint of their approach.

DNA Components:
1. Timing Pattern - When they trade (time of day, day of week)
2. Position Sizing - How they size positions (fixed, scaled, etc.)
3. Market Selection - What markets they prefer
4. Holding Period - How long they hold positions
5. Risk Profile - How they manage risk (stop-loss behavior)
6. Entry/Exit Style - How they enter and exit (aggressive vs passive)
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum
import math

try:
    from .security import sanitize_username
except ImportError:
    from security import sanitize_username

logger = logging.getLogger(__name__)


class TimingStyle(Enum):
    """When the trader is most active"""
    EARLY_BIRD = "EARLY_BIRD"       # Most active in morning
    NIGHT_OWL = "NIGHT_OWL"         # Most active at night
    MARKET_HOURS = "MARKET_HOURS"   # Traditional trading hours
    AROUND_THE_CLOCK = "24/7"       # No clear pattern
    EVENT_DRIVEN = "EVENT_DRIVEN"   # Around news/events


class SizingStyle(Enum):
    """How they size positions"""
    FIXED = "FIXED"                 # Same size every trade
    SCALED = "SCALED"               # Size based on conviction
    MARTINGALE = "MARTINGALE"       # Increase size after losses
    KELLY = "KELLY"                 # Kelly criterion-like sizing
    RANDOM = "RANDOM"               # No clear pattern


class HoldingStyle(Enum):
    """How long they hold positions"""
    SCALPER = "SCALPER"             # Seconds to minutes
    DAY_TRADER = "DAY_TRADER"       # Hours
    SWING_TRADER = "SWING_TRADER"   # Days
    POSITION_TRADER = "POSITION"    # Weeks to months
    MIXED = "MIXED"                 # Variable


class EntryStyle(Enum):
    """How they enter positions"""
    AGGRESSIVE = "AGGRESSIVE"       # Market orders, immediate
    PASSIVE = "PASSIVE"             # Limit orders, patient
    MOMENTUM = "MOMENTUM"           # Chase price moves
    CONTRARIAN = "CONTRARIAN"       # Fade price moves
    BALANCED = "BALANCED"           # Mix of styles


class RiskStyle(Enum):
    """How they manage risk"""
    TIGHT_STOPS = "TIGHT_STOPS"     # Quick to cut losses
    WIDE_STOPS = "WIDE_STOPS"       # Let positions breathe
    NO_STOPS = "NO_STOPS"           # Hold to resolution
    SCALE_OUT = "SCALE_OUT"         # Partial exits
    ALL_OR_NOTHING = "ALL_OR_NOTHING"  # Full size always


@dataclass
class StrategyDNA:
    """The unique fingerprint of a trader's strategy"""
    username: str

    # DNA Components
    timing_style: TimingStyle
    sizing_style: SizingStyle
    holding_style: HoldingStyle
    entry_style: EntryStyle
    risk_style: RiskStyle

    # Numerical DNA (for clustering)
    dna_vector: list[float]  # Normalized 0-1 values

    # Cluster assignment
    cluster_id: int
    cluster_name: str
    cluster_similarity: float  # How similar to cluster center

    # Metrics used to derive DNA
    avg_hold_hours: float
    trade_size_std: float     # Variation in trade sizes
    active_hours: list[int]   # Hours of day most active
    market_concentration: float
    win_streak_tendency: float

    # Uniqueness score
    uniqueness_score: float   # How different from others (0-100)

    created_at: datetime


@dataclass
class StrategyCluster:
    """A cluster of similar strategies"""
    cluster_id: int
    name: str
    description: str

    # Cluster characteristics
    typical_holding_hours: float
    typical_win_rate: float
    typical_sharpe: float

    # Members
    num_members: int
    top_performers: list[str]  # Top usernames

    # Cluster center (DNA vector)
    center_vector: list[float]


class StrategyDNAAnalyzer:
    """
    Analyzes trader behavior to extract Strategy DNA.

    Usage:
        analyzer = StrategyDNAAnalyzer(ch_client)
        dna = analyzer.extract_dna("username")
        clusters = analyzer.cluster_all_traders()
    """

    def __init__(self, clickhouse_client):
        self.ch = clickhouse_client
        self.clusters: list[StrategyCluster] = []

    def extract_dna(self, username: str) -> Optional[StrategyDNA]:
        """Extract Strategy DNA for a single trader"""
        logger.info(f"Extracting DNA for {username}")

        # Get trader's behavioral metrics
        metrics = self._get_behavioral_metrics(username)
        if not metrics:
            return None

        # Classify each DNA component
        timing = self._classify_timing(metrics)
        sizing = self._classify_sizing(metrics)
        holding = self._classify_holding(metrics)
        entry = self._classify_entry(metrics)
        risk = self._classify_risk(metrics)

        # Create DNA vector for clustering
        dna_vector = self._create_dna_vector(metrics)

        # Find cluster assignment
        cluster_id, cluster_name, similarity = self._assign_cluster(dna_vector)

        # Calculate uniqueness
        uniqueness = self._calculate_uniqueness(dna_vector)

        return StrategyDNA(
            username=username,
            timing_style=timing,
            sizing_style=sizing,
            holding_style=holding,
            entry_style=entry,
            risk_style=risk,
            dna_vector=dna_vector,
            cluster_id=cluster_id,
            cluster_name=cluster_name,
            cluster_similarity=similarity,
            avg_hold_hours=metrics.get('avg_hold_hours', 0),
            trade_size_std=metrics.get('trade_size_std', 0),
            active_hours=metrics.get('active_hours', []),
            market_concentration=metrics.get('market_concentration', 0),
            win_streak_tendency=metrics.get('win_streak_tendency', 0),
            uniqueness_score=uniqueness,
            created_at=datetime.utcnow(),
        )

    def _get_behavioral_metrics(self, username: str) -> Optional[dict]:
        """Get behavioral metrics for DNA extraction"""
        safe_username = sanitize_username(username)
        query = f"""
        SELECT
            count() as trade_count,
            avg(size) as avg_size,
            stddevPop(size) as size_std,
            uniq(market_slug) as unique_markets,
            count() / uniq(market_slug) as trades_per_market
        FROM polybot.aware_global_trades
        WHERE username = '{safe_username}'
        """

        try:
            result = self.ch.query(query)
            if not result.result_rows:
                return None

            row = result.result_rows[0]
            return {
                'trade_count': row[0],
                'avg_size': row[1] or 0,
                'trade_size_std': row[2] or 0,
                'unique_markets': row[3],
                'trades_per_market': row[4] or 0,
                'avg_hold_hours': 24,  # Would calculate from actual hold times
                'market_concentration': min(1.0, (row[4] or 0) / 10),
                'active_hours': [9, 10, 11, 14, 15, 16],  # Placeholder
                'win_streak_tendency': 0.5,  # Placeholder
            }

        except Exception as e:
            logger.error(f"Error getting behavioral metrics: {e}")
            return None

    def _classify_timing(self, metrics: dict) -> TimingStyle:
        """Classify timing style from metrics"""
        active_hours = metrics.get('active_hours', [])

        if not active_hours:
            return TimingStyle.AROUND_THE_CLOCK

        avg_hour = sum(active_hours) / len(active_hours)

        if avg_hour < 10:
            return TimingStyle.EARLY_BIRD
        elif avg_hour > 20:
            return TimingStyle.NIGHT_OWL
        elif 9 <= avg_hour <= 17:
            return TimingStyle.MARKET_HOURS
        else:
            return TimingStyle.AROUND_THE_CLOCK

    def _classify_sizing(self, metrics: dict) -> SizingStyle:
        """Classify position sizing style"""
        size_std = metrics.get('trade_size_std', 0)
        avg_size = metrics.get('avg_size', 1)

        if avg_size == 0:
            return SizingStyle.RANDOM

        cv = size_std / avg_size if avg_size > 0 else 0  # Coefficient of variation

        if cv < 0.1:
            return SizingStyle.FIXED
        elif cv < 0.3:
            return SizingStyle.SCALED
        elif cv > 0.8:
            return SizingStyle.RANDOM
        else:
            return SizingStyle.KELLY

    def _classify_holding(self, metrics: dict) -> HoldingStyle:
        """Classify holding period style"""
        avg_hold = metrics.get('avg_hold_hours', 24)

        if avg_hold < 1:
            return HoldingStyle.SCALPER
        elif avg_hold < 24:
            return HoldingStyle.DAY_TRADER
        elif avg_hold < 168:  # 1 week
            return HoldingStyle.SWING_TRADER
        else:
            return HoldingStyle.POSITION_TRADER

    def _classify_entry(self, metrics: dict) -> EntryStyle:
        """Classify entry style"""
        # Would need order book data for accurate classification
        # For now, use trade frequency as proxy
        trades_per_market = metrics.get('trades_per_market', 0)

        if trades_per_market > 10:
            return EntryStyle.AGGRESSIVE
        elif trades_per_market < 3:
            return EntryStyle.PASSIVE
        else:
            return EntryStyle.BALANCED

    def _classify_risk(self, metrics: dict) -> RiskStyle:
        """Classify risk management style"""
        # Would need position-level data for accurate classification
        win_streak = metrics.get('win_streak_tendency', 0.5)

        if win_streak > 0.7:
            return RiskStyle.TIGHT_STOPS
        elif win_streak < 0.3:
            return RiskStyle.WIDE_STOPS
        else:
            return RiskStyle.SCALE_OUT

    def _create_dna_vector(self, metrics: dict) -> list[float]:
        """Create numerical DNA vector for clustering"""
        # Normalize all metrics to 0-1 range
        vector = [
            min(1.0, metrics.get('avg_hold_hours', 0) / 168),  # Normalized by week
            min(1.0, metrics.get('trade_size_std', 0) / 100),
            min(1.0, metrics.get('market_concentration', 0)),
            min(1.0, metrics.get('trades_per_market', 0) / 20),
            min(1.0, metrics.get('win_streak_tendency', 0)),
            min(1.0, metrics.get('trade_count', 0) / 1000),
        ]
        return vector

    def _assign_cluster(self, dna_vector: list[float]) -> tuple[int, str, float]:
        """Assign trader to a strategy cluster"""
        if not self.clusters:
            # Default clusters if none exist
            return 0, "Unclustered", 0.5

        # Find nearest cluster
        best_cluster = None
        best_similarity = -1

        for cluster in self.clusters:
            similarity = self._vector_similarity(dna_vector, cluster.center_vector)
            if similarity > best_similarity:
                best_similarity = similarity
                best_cluster = cluster

        if best_cluster:
            return best_cluster.cluster_id, best_cluster.name, best_similarity

        return 0, "Unclustered", 0.5

    def _vector_similarity(self, v1: list[float], v2: list[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        if len(v1) != len(v2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a * a for a in v1))
        norm2 = math.sqrt(sum(b * b for b in v2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def _calculate_uniqueness(self, dna_vector: list[float]) -> float:
        """Calculate how unique this DNA is compared to all traders"""
        # Would compare against all other traders
        # For now, return based on vector variance
        variance = sum((x - 0.5) ** 2 for x in dna_vector) / len(dna_vector)
        return min(100, variance * 200)

    def cluster_all_traders(self, num_clusters: int = 8) -> list[StrategyCluster]:
        """
        Cluster all traders by their Strategy DNA.
        Uses K-means style clustering.
        """
        logger.info(f"Clustering traders into {num_clusters} strategy groups")

        # Get all traders with sufficient trades
        query = """
        SELECT DISTINCT username
        FROM polybot.aware_global_trades
        GROUP BY username
        HAVING count() >= 20
        LIMIT 1000
        """

        try:
            result = self.ch.query(query)
            usernames = [row[0] for row in result.result_rows if row[0]]

            # Extract DNA for each trader
            dna_list = []
            for username in usernames:
                dna = self.extract_dna(username)
                if dna:
                    dna_list.append(dna)

            logger.info(f"Extracted DNA for {len(dna_list)} traders")

            # Simple clustering (would use proper K-means in production)
            clusters = self._simple_cluster(dna_list, num_clusters)
            self.clusters = clusters

            return clusters

        except Exception as e:
            logger.error(f"Error clustering traders: {e}")
            return []

    def _simple_cluster(
        self,
        dna_list: list[StrategyDNA],
        num_clusters: int
    ) -> list[StrategyCluster]:
        """Simple clustering based on holding style"""
        # Group by holding style as simple clustering
        clusters = []

        cluster_names = {
            HoldingStyle.SCALPER: ("Scalpers", "Quick in-and-out traders"),
            HoldingStyle.DAY_TRADER: ("Day Traders", "Intraday position holders"),
            HoldingStyle.SWING_TRADER: ("Swing Traders", "Multi-day position holders"),
            HoldingStyle.POSITION_TRADER: ("Position Traders", "Long-term holders"),
            HoldingStyle.MIXED: ("Flexible Traders", "Variable holding periods"),
        }

        for i, (style, (name, desc)) in enumerate(cluster_names.items()):
            members = [d for d in dna_list if d.holding_style == style]

            if members:
                cluster = StrategyCluster(
                    cluster_id=i,
                    name=name,
                    description=desc,
                    typical_holding_hours=sum(d.avg_hold_hours for d in members) / len(members),
                    typical_win_rate=0.5,  # Would calculate
                    typical_sharpe=1.0,    # Would calculate
                    num_members=len(members),
                    top_performers=[d.username for d in members[:5]],
                    center_vector=[0.5] * 6,  # Would calculate actual center
                )
                clusters.append(cluster)

        return clusters

    def get_dna_summary(self, dna: StrategyDNA) -> dict:
        """Get human-readable DNA summary"""
        return {
            'username': dna.username,
            'strategy_profile': {
                'timing': dna.timing_style.value,
                'sizing': dna.sizing_style.value,
                'holding': dna.holding_style.value,
                'entry': dna.entry_style.value,
                'risk': dna.risk_style.value,
            },
            'cluster': {
                'id': dna.cluster_id,
                'name': dna.cluster_name,
                'similarity': round(dna.cluster_similarity * 100, 1),
            },
            'uniqueness_score': round(dna.uniqueness_score, 1),
            'metrics': {
                'avg_hold_hours': round(dna.avg_hold_hours, 1),
                'market_concentration': round(dna.market_concentration * 100, 1),
            }
        }
