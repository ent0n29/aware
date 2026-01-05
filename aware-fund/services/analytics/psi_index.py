"""
AWARE Analytics - PSI Index Construction

Polymarket Smart-money Index (PSI) - investable indices that track top traders.

Index Family:
- PSI-10: Top 10 traders by Smart Money Score (equal weight)
- PSI-25: Top 25 traders (equal weight)
- PSI-CRYPTO: Top crypto market specialists (sharpe-weighted)
- PSI-POLITICS: Top political market specialists (win-rate weighted)
- PSI-ALPHA: ML-selected edge traders (dynamic weights)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class IndexType(Enum):
    """Types of PSI indices"""
    # Core Indexes
    PSI_10 = "PSI-10"           # Top 10 replicable traders (for fund mirroring)
    PSI_25 = "PSI-25"           # Top 25 replicable traders
    PSI_ALL = "PSI-ALL"         # All top traders (including arb/HFT, for leaderboard only)

    # Sectorial Indexes (by market category)
    PSI_CRYPTO = "PSI-CRYPTO"       # Crypto price market specialists (BTC, ETH, etc.)
    PSI_POLITICS = "PSI-POLITICS"   # Political market specialists (elections, policy)
    PSI_SPORTS = "PSI-SPORTS"       # Sports betting specialists (NBA, NFL, soccer)
    PSI_NEWS = "PSI-NEWS"           # Breaking news specialists (current events)

    # Alpha Indexes (ML/proprietary)
    PSI_ALPHA = "PSI-ALPHA"     # ML-selected edge traders


# Strategies that CANNOT be profitably replicated with a 5+ second delay
# These traders profit from latency - copying them late loses money
NON_REPLICABLE_STRATEGIES = [
    "ARBITRAGEUR",   # Profits from arb spreads that close in milliseconds
    "MARKET_MAKER",  # Profits from bid-ask spread, needs to be first
    "SCALPER",       # Short-term moves, latency-sensitive
]

# Strategies that CAN be replicated (directional bets, not latency-sensitive)
REPLICABLE_STRATEGIES = [
    "DIRECTIONAL_FUNDAMENTAL",  # Research-based positions, held for days/weeks
    "DIRECTIONAL_MOMENTUM",     # Trend following, positions held hours/days
    "EVENT_DRIVEN",             # Event-based, positions around specific dates
    "HYBRID",                   # Mixed, generally replicable if hold time > 1hr
    "UNKNOWN",                  # Unknown strategy, include cautiously
]


class MarketCategory(Enum):
    """Categories of prediction markets for sectorial filtering"""
    CRYPTO = "CRYPTO"           # BTC, ETH, crypto price markets
    POLITICS = "POLITICS"       # Elections, policy, geopolitical
    SPORTS = "SPORTS"           # NBA, NFL, soccer, tennis, etc.
    NEWS = "NEWS"               # Breaking news, current events
    ENTERTAINMENT = "ENTERTAINMENT"  # Awards, TV, celebrities
    SCIENCE = "SCIENCE"         # Scientific discoveries, space
    ECONOMICS = "ECONOMICS"     # Fed rates, GDP, employment
    OTHER = "OTHER"             # Uncategorized


class WeightingMethod(Enum):
    """How to weight constituents in the index"""
    EQUAL = "EQUAL"                    # Each trader gets 1/N weight
    SCORE_WEIGHTED = "SCORE_WEIGHTED"  # Weight by Smart Money Score
    SHARPE_WEIGHTED = "SHARPE_WEIGHTED"  # Weight by Sharpe ratio
    VOLUME_WEIGHTED = "VOLUME_WEIGHTED"  # Weight by trading volume


class RebalanceFrequency(Enum):
    """How often to rebalance the index"""
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    EVENT_DRIVEN = "EVENT_DRIVEN"  # Rebalance on significant events


@dataclass
class IndexConstituent:
    """A single trader in the index"""
    username: str
    weight: float              # Portfolio weight (0.0 to 1.0)
    total_score: float   # Score at time of inclusion
    sharpe_ratio: float        # Sharpe at time of inclusion
    strategy_type: str         # e.g., "ARBITRAGEUR", "DIRECTIONAL"
    added_at: datetime         # When added to index

    # Performance tracking
    pnl_since_added: float = 0.0
    contribution_to_index: float = 0.0


@dataclass
class IndexConfig:
    """Configuration for a PSI index"""
    index_type: IndexType
    num_constituents: int
    weighting_method: WeightingMethod
    rebalance_frequency: RebalanceFrequency

    # Eligibility criteria
    min_total_score: float = 60.0   # Minimum score to qualify
    min_trades: int = 50                   # Minimum trades
    min_days_active: int = 30              # Minimum days trading
    min_volume_usd: float = 10000.0        # Minimum volume
    min_sharpe: float = 0.5                # Minimum Sharpe ratio

    # Strategy filters (optional)
    allowed_strategies: list[str] = field(default_factory=list)
    excluded_strategies: list[str] = field(default_factory=list)

    # Market category filter (for sectorial indexes)
    # Trader must have >= min_category_concentration in these categories
    required_categories: list[str] = field(default_factory=list)
    min_category_concentration: float = 0.5  # At least 50% of volume in category

    # Concentration limits
    max_weight_per_trader: float = 0.20    # Max 20% in single trader
    max_strategy_concentration: float = 0.40  # Max 40% in one strategy type


# Pre-defined index configurations
# NOTE: Criteria relaxed for bootstrap phase - tighten as data matures
# Target criteria (when 90+ days of data): 60 days active, 100 trades, $50k volume
INDEX_CONFIGS = {
    # PSI-10: Top 10 REPLICABLE traders (excludes HFT/arb strategies)
    # This is the primary index used for fund mirroring
    IndexType.PSI_10: IndexConfig(
        index_type=IndexType.PSI_10,
        num_constituents=10,
        weighting_method=WeightingMethod.EQUAL,
        rebalance_frequency=RebalanceFrequency.MONTHLY,
        min_total_score=50.0,    # Relaxed from 70 (bootstrap)
        min_trades=10,           # Relaxed from 100 (bootstrap)
        min_days_active=1,       # Relaxed from 60 (bootstrap)
        min_volume_usd=1000.0,   # Relaxed from 50000 (bootstrap)
        min_sharpe=0.0,
        # CRITICAL: Exclude non-replicable strategies
        # HFT/arb bots are profitable but can't be copied with 5s delay
        excluded_strategies=NON_REPLICABLE_STRATEGIES,
    ),
    # PSI-25: Top 25 REPLICABLE traders
    IndexType.PSI_25: IndexConfig(
        index_type=IndexType.PSI_25,
        num_constituents=25,
        weighting_method=WeightingMethod.EQUAL,
        rebalance_frequency=RebalanceFrequency.MONTHLY,
        min_total_score=45.0,    # Relaxed from 60 (bootstrap)
        min_trades=5,            # Relaxed from 50 (bootstrap)
        min_days_active=1,       # Relaxed from 30 (bootstrap)
        min_volume_usd=500.0,    # Relaxed from 10000 (bootstrap)
        min_sharpe=0.0,
        excluded_strategies=NON_REPLICABLE_STRATEGIES,
    ),
    # PSI-CRYPTO: Crypto market specialists (DIRECTIONAL only, no arb)
    IndexType.PSI_CRYPTO: IndexConfig(
        index_type=IndexType.PSI_CRYPTO,
        num_constituents=15,
        weighting_method=WeightingMethod.SHARPE_WEIGHTED,
        rebalance_frequency=RebalanceFrequency.WEEKLY,
        min_total_score=40.0,    # Relaxed from 50 (bootstrap)
        min_trades=5,            # Relaxed from 30 (bootstrap)
        min_days_active=1,       # Relaxed from 14 (bootstrap)
        min_volume_usd=500.0,    # Relaxed from 10000 (bootstrap)
        min_sharpe=0.0,
        # Only include directional traders in crypto markets
        allowed_strategies=["DIRECTIONAL_MOMENTUM", "DIRECTIONAL_FUNDAMENTAL", "HYBRID"],
    ),
    # PSI-POLITICS: Political market specialists (directional/event-driven)
    IndexType.PSI_POLITICS: IndexConfig(
        index_type=IndexType.PSI_POLITICS,
        num_constituents=15,
        weighting_method=WeightingMethod.SCORE_WEIGHTED,
        rebalance_frequency=RebalanceFrequency.EVENT_DRIVEN,
        min_total_score=40.0,    # Relaxed from 50 (bootstrap)
        min_trades=5,            # Added minimum trades (bootstrap)
        min_days_active=1,       # Added minimum days (bootstrap)
        min_volume_usd=500.0,    # Added minimum volume (bootstrap)
        min_sharpe=0.0,
        allowed_strategies=["DIRECTIONAL_FUNDAMENTAL", "EVENT_DRIVEN"],
    ),
    # PSI-ALL: ALL traders including arb/HFT (for leaderboard display only, NOT for mirroring)
    IndexType.PSI_ALL: IndexConfig(
        index_type=IndexType.PSI_ALL,
        num_constituents=50,
        weighting_method=WeightingMethod.SCORE_WEIGHTED,
        rebalance_frequency=RebalanceFrequency.WEEKLY,
        min_total_score=40.0,
        min_trades=5,
        min_days_active=1,
        min_volume_usd=500.0,
        min_sharpe=0.0,
        # No strategy filter - includes everyone for leaderboard
    ),

    # ═══════════════════════════════════════════════════════════════════════════
    # SECTORIAL INDEXES (by market category)
    # ═══════════════════════════════════════════════════════════════════════════

    # PSI-SPORTS: Sports betting specialists
    IndexType.PSI_SPORTS: IndexConfig(
        index_type=IndexType.PSI_SPORTS,
        num_constituents=10,
        weighting_method=WeightingMethod.SCORE_WEIGHTED,
        rebalance_frequency=RebalanceFrequency.WEEKLY,
        min_total_score=40.0,
        min_trades=10,
        min_days_active=7,
        min_volume_usd=1000.0,
        min_sharpe=0.0,
        # Only directional traders (no arb on sports)
        excluded_strategies=NON_REPLICABLE_STRATEGIES,
        # Must specialize in sports markets
        required_categories=["SPORTS"],
        min_category_concentration=0.5,  # 50% of volume in sports
    ),

    # PSI-NEWS: Breaking news specialists
    IndexType.PSI_NEWS: IndexConfig(
        index_type=IndexType.PSI_NEWS,
        num_constituents=10,
        weighting_method=WeightingMethod.SHARPE_WEIGHTED,
        rebalance_frequency=RebalanceFrequency.WEEKLY,
        min_total_score=40.0,
        min_trades=10,
        min_days_active=7,
        min_volume_usd=1000.0,
        min_sharpe=0.0,
        # Event-driven and directional (news reacts fast but not arb)
        allowed_strategies=["EVENT_DRIVEN", "DIRECTIONAL_MOMENTUM", "DIRECTIONAL_FUNDAMENTAL"],
        # Must specialize in news/current events markets
        required_categories=["NEWS", "POLITICS"],  # News often overlaps with politics
        min_category_concentration=0.5,
    ),
}


@dataclass
class PSIIndex:
    """A constructed PSI index with constituents and performance"""
    index_type: IndexType
    constituents: list[IndexConstituent]
    created_at: datetime
    last_rebalanced: datetime

    # Index level metrics
    total_value: float = 100.0  # Starts at 100 (like S&P)
    cumulative_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0

    @property
    def num_constituents(self) -> int:
        return len(self.constituents)

    def get_constituent(self, username: str) -> Optional[IndexConstituent]:
        """Get a constituent by username"""
        for c in self.constituents:
            if c.username == username:
                return c
        return None


class PSIIndexBuilder:
    """
    Builds and manages PSI indices.

    Usage:
        builder = PSIIndexBuilder(ch_client)
        psi_10 = builder.build_index(IndexType.PSI_10)
    """

    def __init__(self, clickhouse_client):
        self.ch = clickhouse_client

    def build_index(self, index_type: IndexType) -> PSIIndex:
        """
        Build a PSI index from current trader scores.

        Args:
            index_type: Which index to build

        Returns:
            Constructed PSIIndex with constituents
        """
        config = INDEX_CONFIGS.get(index_type)
        if not config:
            raise ValueError(f"Unknown index type: {index_type}")

        logger.info(f"Building {index_type.value} index...")

        # Step 1: Get eligible traders
        eligible_traders = self._get_eligible_traders(config)
        logger.info(f"Found {len(eligible_traders)} eligible traders")

        if len(eligible_traders) < config.num_constituents:
            logger.warning(
                f"Only {len(eligible_traders)} eligible traders, "
                f"need {config.num_constituents} for {index_type.value}"
            )

        # Step 2: Select top N traders
        selected = self._select_constituents(eligible_traders, config)
        logger.info(f"Selected {len(selected)} constituents")

        # Step 3: Calculate weights
        constituents = self._calculate_weights(selected, config)

        # Step 4: Build index
        now = datetime.utcnow()
        index = PSIIndex(
            index_type=index_type,
            constituents=constituents,
            created_at=now,
            last_rebalanced=now,
        )

        logger.info(
            f"Built {index_type.value}: {index.num_constituents} traders, "
            f"weights sum to {sum(c.weight for c in constituents):.4f}"
        )

        return index

    def _get_eligible_traders(self, config: IndexConfig) -> list[dict]:
        """Get traders that meet eligibility criteria"""

        # Query traders with scores from ClickHouse
        query = f"""
        SELECT
            username,
            total_score,
            sharpe_ratio,
            strategy_type,
            total_trades,
            days_active,
            total_volume_usd,
            total_pnl,
            win_rate
        FROM polybot.aware_psi_eligible_traders
        WHERE
            total_score >= {config.min_total_score}
            AND total_trades >= {config.min_trades}
            AND days_active >= {config.min_days_active}
            AND total_volume_usd >= {config.min_volume_usd}
            AND sharpe_ratio >= {config.min_sharpe}
            AND username != ''
        ORDER BY total_score DESC
        LIMIT 1000
        """

        try:
            result = self.ch.query(query)
            traders = []

            for row in result.result_rows:
                trader = {
                    'username': row[0],
                    'total_score': row[1],
                    'sharpe_ratio': row[2],
                    'strategy_type': row[3] or 'UNKNOWN',
                    'total_trades': row[4],
                    'days_active': row[5],
                    'total_volume_usd': row[6],
                    'total_pnl': row[7],
                    'win_rate': row[8],
                }

                # Apply strategy filters
                if config.allowed_strategies:
                    if trader['strategy_type'] not in config.allowed_strategies:
                        continue

                if config.excluded_strategies:
                    if trader['strategy_type'] in config.excluded_strategies:
                        continue

                traders.append(trader)

            return traders

        except Exception as e:
            logger.error(f"Failed to get eligible traders: {e}")
            return []

    def _select_constituents(
        self,
        traders: list[dict],
        config: IndexConfig
    ) -> list[dict]:
        """Select the top N traders for the index"""

        # Already sorted by score, just take top N
        selected = traders[:config.num_constituents]

        # Check strategy concentration
        strategy_counts = {}
        for t in selected:
            s = t['strategy_type']
            strategy_counts[s] = strategy_counts.get(s, 0) + 1

        max_per_strategy = int(config.num_constituents * config.max_strategy_concentration)

        # If any strategy is over-concentrated, we might want to adjust
        for strategy, count in strategy_counts.items():
            if count > max_per_strategy:
                logger.warning(
                    f"Strategy {strategy} has {count} traders, "
                    f"exceeds {max_per_strategy} concentration limit"
                )

        return selected

    def _calculate_weights(
        self,
        traders: list[dict],
        config: IndexConfig
    ) -> list[IndexConstituent]:
        """Calculate portfolio weights for each constituent"""

        if not traders:
            return []

        constituents = []
        now = datetime.utcnow()

        if config.weighting_method == WeightingMethod.EQUAL:
            # Equal weight
            weight = 1.0 / len(traders)
            for t in traders:
                constituents.append(IndexConstituent(
                    username=t['username'],
                    weight=weight,
                    total_score=t['total_score'],
                    sharpe_ratio=t['sharpe_ratio'],
                    strategy_type=t['strategy_type'],
                    added_at=now,
                ))

        elif config.weighting_method == WeightingMethod.SCORE_WEIGHTED:
            # Weight by Smart Money Score
            total_score = sum(t['total_score'] for t in traders)
            for t in traders:
                weight = t['total_score'] / total_score if total_score > 0 else 0
                weight = min(weight, config.max_weight_per_trader)
                constituents.append(IndexConstituent(
                    username=t['username'],
                    weight=weight,
                    total_score=t['total_score'],
                    sharpe_ratio=t['sharpe_ratio'],
                    strategy_type=t['strategy_type'],
                    added_at=now,
                ))

        elif config.weighting_method == WeightingMethod.SHARPE_WEIGHTED:
            # Weight by Sharpe ratio (risk-adjusted)
            total_sharpe = sum(max(0, t['sharpe_ratio']) for t in traders)
            for t in traders:
                sharpe = max(0, t['sharpe_ratio'])
                weight = sharpe / total_sharpe if total_sharpe > 0 else 0
                weight = min(weight, config.max_weight_per_trader)
                constituents.append(IndexConstituent(
                    username=t['username'],
                    weight=weight,
                    total_score=t['total_score'],
                    sharpe_ratio=t['sharpe_ratio'],
                    strategy_type=t['strategy_type'],
                    added_at=now,
                ))

        # Normalize weights to sum to 1.0
        total_weight = sum(c.weight for c in constituents)
        if total_weight > 0:
            for c in constituents:
                c.weight = c.weight / total_weight

        return constituents

    def rebalance_index(self, index: PSIIndex) -> PSIIndex:
        """
        Rebalance an existing index.

        Compares current constituents to new eligible traders
        and adjusts weights/composition.
        """
        config = INDEX_CONFIGS.get(index.index_type)
        if not config:
            raise ValueError(f"Unknown index type: {index.index_type}")

        logger.info(f"Rebalancing {index.index_type.value}...")

        # Build fresh index
        new_index = self.build_index(index.index_type)

        # Track changes
        old_usernames = {c.username for c in index.constituents}
        new_usernames = {c.username for c in new_index.constituents}

        additions = new_usernames - old_usernames
        removals = old_usernames - new_usernames

        logger.info(
            f"Rebalance: +{len(additions)} additions, -{len(removals)} removals"
        )

        if additions:
            logger.info(f"  Added: {', '.join(additions)}")
        if removals:
            logger.info(f"  Removed: {', '.join(removals)}")

        # Preserve historical data
        new_index.created_at = index.created_at
        new_index.cumulative_return = index.cumulative_return

        return new_index

    def save_index(self, index: PSIIndex) -> bool:
        """Save index to ClickHouse"""
        try:
            # Prepare data for insertion
            rows = []
            for c in index.constituents:
                rows.append((
                    index.index_type.value,
                    c.username,
                    c.weight,
                    c.total_score,
                    c.sharpe_ratio,
                    c.strategy_type,
                    index.created_at,
                    index.last_rebalanced,
                ))

            self.ch.insert(
                'aware_psi_index',
                rows,
                column_names=[
                    'index_type', 'username', 'weight',
                    'total_score', 'sharpe_ratio', 'strategy_type',
                    'created_at', 'rebalanced_at'
                ]
            )

            logger.info(f"Saved {index.index_type.value} with {len(rows)} constituents")
            return True

        except Exception as e:
            logger.error(f"Failed to save index: {e}")
            return False

    def get_index_summary(self, index: PSIIndex) -> dict:
        """Get a summary of the index for display"""
        return {
            'index_type': index.index_type.value,
            'num_constituents': index.num_constituents,
            'created_at': index.created_at.isoformat(),
            'last_rebalanced': index.last_rebalanced.isoformat(),
            'total_value': index.total_value,
            'cumulative_return': index.cumulative_return,
            'constituents': [
                {
                    'rank': i + 1,
                    'username': c.username,
                    'weight': round(c.weight * 100, 2),  # As percentage
                    'score': c.total_score,
                    'sharpe': c.sharpe_ratio,
                    'strategy': c.strategy_type,
                }
                for i, c in enumerate(index.constituents)
            ]
        }


def build_all_indices(clickhouse_client) -> dict[IndexType, PSIIndex]:
    """Build all configured PSI indices"""
    builder = PSIIndexBuilder(clickhouse_client)
    indices = {}

    for index_type in INDEX_CONFIGS.keys():
        try:
            index = builder.build_index(index_type)
            indices[index_type] = index
        except Exception as e:
            logger.error(f"Failed to build {index_type.value}: {e}")

    return indices
