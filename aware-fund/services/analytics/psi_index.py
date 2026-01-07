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

from market_classifier import TraderCategoryProfiler

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
    ML_CLUSTER_BALANCED = "ML_CLUSTER_BALANCED"  # Equal weight per cluster, then by score within cluster


class RebalanceFrequency(Enum):
    """How often to rebalance the index"""
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    EVENT_DRIVEN = "EVENT_DRIVEN"  # Rebalance on significant events


@dataclass
class IndexConstituent:
    """A single trader in the index"""
    proxy_address: str         # Trader's wallet address (required for fund mirroring)
    username: str
    weight: float              # Portfolio weight (0.0 to 1.0)
    total_score: float         # Score at time of inclusion
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
    # NOTE: Relaxed for bootstrap - allow all non-arb strategies
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
        # Exclude arb/HFT but allow all other strategies including empty
        excluded_strategies=NON_REPLICABLE_STRATEGIES,
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
    # NOTE: Relaxed for bootstrap - remove category filter until more data
    IndexType.PSI_SPORTS: IndexConfig(
        index_type=IndexType.PSI_SPORTS,
        num_constituents=10,
        weighting_method=WeightingMethod.SCORE_WEIGHTED,
        rebalance_frequency=RebalanceFrequency.WEEKLY,
        min_total_score=40.0,
        min_trades=5,            # Relaxed from 10 (bootstrap)
        min_days_active=1,       # Relaxed from 7 (bootstrap)
        min_volume_usd=500.0,    # Relaxed from 1000 (bootstrap)
        min_sharpe=0.0,
        # Only directional traders (no arb on sports)
        excluded_strategies=NON_REPLICABLE_STRATEGIES,
        # DISABLED for bootstrap - enable when category profiler has data
        # required_categories=["SPORTS"],
        # min_category_concentration=0.5,
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

    # ═══════════════════════════════════════════════════════════════════════════
    # ML-POWERED INDEX
    # ═══════════════════════════════════════════════════════════════════════════

    # PSI-ALPHA: ML-selected traders with cluster-balanced diversification
    # Uses Strategy DNA clustering to ensure diverse strategy mix
    # NOTE: Relaxed for bootstrap - use score weighting until ML clusters ready
    IndexType.PSI_ALPHA: IndexConfig(
        index_type=IndexType.PSI_ALPHA,
        num_constituents=15,
        weighting_method=WeightingMethod.SCORE_WEIGHTED,  # Fallback from ML_CLUSTER_BALANCED
        rebalance_frequency=RebalanceFrequency.WEEKLY,
        min_total_score=50.0,
        min_trades=5,            # Relaxed from 10 (bootstrap)
        min_days_active=1,       # Relaxed from 7 (bootstrap)
        min_volume_usd=500.0,    # Relaxed from 1000 (bootstrap)
        min_sharpe=0.0,
        # Exclude HFT/arb (non-replicable)
        excluded_strategies=NON_REPLICABLE_STRATEGIES,
        # No category filter - ML selects across all markets
        max_weight_per_trader=0.15,  # Max 15% per trader (more diversified)
        max_strategy_concentration=0.30,  # Max 30% in one strategy cluster
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
        # Category profiler for sectorial indexes (lazy-loaded)
        self._category_profiler = None

    @property
    def category_profiler(self) -> TraderCategoryProfiler:
        """Lazy-load category profiler to avoid overhead for non-sectorial indexes"""
        if self._category_profiler is None:
            self._category_profiler = TraderCategoryProfiler(self.ch)
        return self._category_profiler

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
            proxy_address,
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
                    'proxy_address': row[0],
                    'username': row[1],
                    'total_score': row[2],
                    'sharpe_ratio': row[3],
                    'strategy_type': row[4] or 'UNKNOWN',
                    'total_trades': row[5],
                    'days_active': row[6],
                    'total_volume_usd': row[7],
                    'total_pnl': row[8],
                    'win_rate': row[9],
                }

                # Apply strategy filters
                strategy = trader['strategy_type']

                if config.allowed_strategies:
                    # Empty/unknown strategies pass through allowed filter
                    if strategy and strategy not in ['', 'UNKNOWN'] and strategy not in config.allowed_strategies:
                        continue

                if config.excluded_strategies:
                    # Only exclude if strategy is explicitly in exclusion list
                    if strategy and strategy in config.excluded_strategies:
                        continue

                traders.append(trader)

            # Apply category filters for sectorial indexes
            if config.required_categories:
                traders = self._filter_by_category(
                    traders,
                    config.required_categories,
                    config.min_category_concentration
                )
                logger.info(
                    f"After category filter ({config.required_categories}): "
                    f"{len(traders)} traders"
                )

            return traders

        except Exception as e:
            logger.error(f"Failed to get eligible traders: {e}")
            return []

    def _filter_by_category(
        self,
        traders: list[dict],
        required_categories: list[str],
        min_concentration: float
    ) -> list[dict]:
        """
        Filter traders by market category concentration.

        Args:
            traders: List of trader dicts (must have 'proxy_address')
            required_categories: Category names trader must specialize in
            min_concentration: Minimum % of volume in required categories

        Returns:
            Filtered list of traders meeting category concentration
        """
        if not traders:
            return []

        # Get category profiles for all traders
        addresses = [t['proxy_address'] for t in traders]
        logger.info(f"Profiling {len(addresses)} traders for category concentration...")

        filtered = []
        for trader in traders:
            profile = self.category_profiler.get_trader_category_distribution(
                trader['proxy_address']
            )

            # Sum concentration across required categories
            total_concentration = sum(
                profile.get(cat, 0.0)
                for cat in required_categories
            )

            if total_concentration >= min_concentration:
                # Store concentration for debugging/display
                trader['category_concentration'] = total_concentration
                filtered.append(trader)

        return filtered

    def _get_ml_cluster_assignments(
        self,
        proxy_addresses: list[str]
    ) -> dict[str, str]:
        """
        Get ML strategy cluster assignments from aware_ml_enrichment table.

        Args:
            proxy_addresses: List of trader addresses

        Returns:
            Dict mapping proxy_address -> strategy_cluster name
        """
        if not proxy_addresses:
            return {}

        try:
            # Build IN clause safely
            addr_list = "', '".join(proxy_addresses)
            query = f"""
            SELECT
                proxy_address,
                strategy_cluster
            FROM polybot.aware_ml_enrichment FINAL
            WHERE proxy_address IN ('{addr_list}')
            """

            result = self.ch.query(query)

            assignments = {}
            for row in result.result_rows:
                addr, cluster = row[0], row[1]
                assignments[addr] = cluster or 'UNKNOWN'

            logger.info(f"Got ML cluster assignments for {len(assignments)}/{len(proxy_addresses)} traders")
            return assignments

        except Exception as e:
            logger.warning(f"Failed to get ML cluster assignments: {e}")
            # Fall back to UNKNOWN for all
            return {addr: 'UNKNOWN' for addr in proxy_addresses}

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
                    proxy_address=t['proxy_address'],
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
                    proxy_address=t['proxy_address'],
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
                    proxy_address=t['proxy_address'],
                    username=t['username'],
                    weight=weight,
                    total_score=t['total_score'],
                    sharpe_ratio=t['sharpe_ratio'],
                    strategy_type=t['strategy_type'],
                    added_at=now,
                ))

        elif config.weighting_method == WeightingMethod.ML_CLUSTER_BALANCED:
            # ML-based: Equal weight per cluster, score-weighted within cluster
            # This ensures diversification across strategy archetypes
            cluster_assignments = self._get_ml_cluster_assignments(
                [t['proxy_address'] for t in traders]
            )

            # Group traders by cluster
            clusters = {}
            for t in traders:
                cluster = cluster_assignments.get(t['proxy_address'], 'UNKNOWN')
                if cluster not in clusters:
                    clusters[cluster] = []
                clusters[cluster].append(t)

            # Calculate weights: equal across clusters, score-weighted within
            num_clusters = len(clusters) if clusters else 1
            cluster_weight = 1.0 / num_clusters

            for cluster_name, cluster_traders in clusters.items():
                # Score-weighted within cluster
                cluster_total_score = sum(t['total_score'] for t in cluster_traders)
                for t in cluster_traders:
                    if cluster_total_score > 0:
                        within_cluster_weight = t['total_score'] / cluster_total_score
                    else:
                        within_cluster_weight = 1.0 / len(cluster_traders)

                    weight = cluster_weight * within_cluster_weight
                    weight = min(weight, config.max_weight_per_trader)

                    constituents.append(IndexConstituent(
                        proxy_address=t['proxy_address'],
                        username=t['username'],
                        weight=weight,
                        total_score=t['total_score'],
                        sharpe_ratio=t['sharpe_ratio'],
                        strategy_type=cluster_name,  # Use ML cluster as strategy
                        added_at=now,
                    ))

            logger.info(f"ML cluster weighting: {len(clusters)} clusters, {len(constituents)} traders")

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
            # Delete old entries for this index type first (synchronous mutation)
            # This ensures removed traders don't remain in the table
            # mutations_sync=1 makes the DELETE wait until complete
            self.ch.command(
                f"ALTER TABLE polybot.aware_psi_index DELETE WHERE index_type = '{index.index_type.value}' SETTINGS mutations_sync = 1"
            )
            logger.info(f"Cleared old {index.index_type.value} entries (sync)")

            # Prepare data for insertion
            rows = []
            for c in index.constituents:
                rows.append((
                    index.index_type.value,
                    c.username,
                    c.proxy_address,
                    c.weight,
                    c.total_score,
                    c.sharpe_ratio,
                    c.strategy_type,
                    index.created_at,
                    index.last_rebalanced,
                ))

            self.ch.insert(
                'polybot.aware_psi_index',
                rows,
                column_names=[
                    'index_type', 'username', 'proxy_address', 'weight',
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
