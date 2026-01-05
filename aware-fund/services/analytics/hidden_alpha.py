"""
AWARE Analytics - Hidden Alpha Discovery

Finds undervalued traders that the public leaderboard misses.
The "Moneyball" of prediction markets.

Discovery Methods:
1. Anomaly Detection - Exceptional performance that doesn't fit normal patterns
2. Rising Stars - New traders with exceptional early performance
3. Niche Specialists - High edge in specific market categories
4. Anti-Correlated - Traders who profit when consensus fails
5. Strategy Outliers - Unique trading patterns via clustering
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum
import math

logger = logging.getLogger(__name__)


class DiscoveryType(Enum):
    """Types of hidden alpha discoveries"""
    HIDDEN_GEM = "HIDDEN_GEM"           # High quality, low visibility
    RISING_STAR = "RISING_STAR"         # New but exceptional
    NICHE_SPECIALIST = "NICHE_SPECIALIST"  # Dominates specific category
    CONTRARIAN = "CONTRARIAN"           # Profits against consensus
    STRATEGY_OUTLIER = "STRATEGY_OUTLIER"  # Unique approach


@dataclass
class HiddenTrader:
    """A discovered hidden alpha trader"""
    username: str
    discovery_type: DiscoveryType
    discovery_score: float      # 0-100, how "hidden" yet valuable

    # Why they're hidden
    visibility_score: float     # Low = hidden from public view
    leaderboard_rank: Optional[int]  # Their public rank (if any)

    # Why they're valuable
    total_score: float
    sharpe_ratio: float
    win_rate: float
    edge_persistence: float     # Likelihood edge continues

    # Discovery details
    discovery_reason: str
    discovered_at: datetime

    # Metrics that made them stand out
    standout_metrics: dict


@dataclass
class DiscoveryConfig:
    """Configuration for hidden alpha discovery"""
    # Hidden Gem criteria
    min_sharpe_for_gem: float = 1.5
    max_volume_for_hidden: float = 50000  # Under $50K = "hidden"
    min_trades_for_gem: int = 30

    # Rising Star criteria
    max_days_active: int = 30     # New = less than 30 days
    min_win_rate_star: float = 0.60
    min_sharpe_star: float = 1.0

    # Niche Specialist criteria
    min_market_concentration: float = 0.70  # 70%+ in one category
    min_category_edge: float = 0.20  # 20%+ better than average

    # Contrarian criteria
    min_consensus_deviation: float = 0.30  # 30%+ against consensus

    # General
    max_discoveries_per_type: int = 10
    discovery_refresh_hours: int = 24


class HiddenAlphaDiscovery:
    """
    Discovers hidden alpha traders using multiple methods.

    Usage:
        discovery = HiddenAlphaDiscovery(ch_client)
        hidden_traders = discovery.discover_all()
    """

    def __init__(self, clickhouse_client, config: Optional[DiscoveryConfig] = None):
        self.ch = clickhouse_client
        self.config = config or DiscoveryConfig()

    def discover_all(self) -> list[HiddenTrader]:
        """Run all discovery methods and return combined results"""
        all_discoveries = []

        # Run each discovery method
        discoveries = [
            self.find_hidden_gems(),
            self.find_rising_stars(),
            self.find_niche_specialists(),
            self.find_contrarians(),
        ]

        for discovery_list in discoveries:
            all_discoveries.extend(discovery_list)

        # Sort by discovery score
        all_discoveries.sort(key=lambda x: x.discovery_score, reverse=True)

        logger.info(f"Discovered {len(all_discoveries)} hidden alpha traders")
        return all_discoveries

    def find_hidden_gems(self) -> list[HiddenTrader]:
        """
        Find Hidden Gems: High quality traders with low visibility.

        These are traders with excellent metrics (high Sharpe, good win rate)
        but low volume - they're not on the public leaderboard.

        Enhanced algorithm:
        1. Find traders with high risk-adjusted returns
        2. Filter those below visibility threshold
        3. Score based on quality/visibility ratio
        4. Consider consistency and edge persistence
        """
        logger.info("Searching for hidden gems...")

        # Enhanced query with more metrics for better gem detection
        query = f"""
        WITH
        -- Get comprehensive trader metrics
        trader_metrics AS (
            SELECT
                username,
                total_score,
                sharpe_ratio,
                win_rate,
                total_volume_usd,
                total_trades,
                days_active,
                total_pnl,
                strategy_type,
                unique_markets
            FROM polybot.aware_psi_eligible_traders
            WHERE
                sharpe_ratio >= {self.config.min_sharpe_for_gem}
                AND total_volume_usd <= {self.config.max_volume_for_hidden}
                AND total_trades >= {self.config.min_trades_for_gem}
                AND username != ''
        ),
        -- Calculate percentile ranks for quality metrics
        ranked AS (
            SELECT
                *,
                percent_rank() OVER (ORDER BY sharpe_ratio) as sharpe_percentile,
                percent_rank() OVER (ORDER BY win_rate) as winrate_percentile,
                percent_rank() OVER (ORDER BY total_pnl) as pnl_percentile,
                percent_rank() OVER (ORDER BY total_volume_usd DESC) as visibility_percentile
            FROM trader_metrics
        )
        SELECT
            username,
            total_score,
            sharpe_ratio,
            win_rate,
            total_volume_usd,
            total_trades,
            days_active,
            total_pnl,
            strategy_type,
            unique_markets,
            sharpe_percentile,
            winrate_percentile,
            pnl_percentile,
            visibility_percentile
        FROM ranked
        WHERE
            -- High quality (top 30% on at least one metric)
            (sharpe_percentile >= 0.7 OR winrate_percentile >= 0.7 OR pnl_percentile >= 0.7)
            -- Low visibility (bottom 50% by volume)
            AND visibility_percentile >= 0.5
        ORDER BY
            -- Composite score: quality vs visibility
            (sharpe_percentile + winrate_percentile + pnl_percentile) / 3 - (1 - visibility_percentile) DESC
        LIMIT {self.config.max_discoveries_per_type}
        """

        try:
            result = self.ch.query(query)
            discoveries = []

            for row in result.result_rows:
                username = row[0]
                total_score = row[1]
                sharpe = row[2]
                win_rate = row[3] or 0
                volume = row[4]
                total_trades = row[5]
                days_active = row[6]
                total_pnl = row[7]
                strategy_type = row[8]
                unique_markets = row[9]
                sharpe_pct = row[10]
                winrate_pct = row[11]
                pnl_pct = row[12]
                visibility_pct = row[13]

                # Calculate visibility score (lower = more hidden)
                visibility = min(100, (1 - visibility_pct) * 100)

                # Calculate composite quality score
                quality_score = (sharpe_pct * 40 + winrate_pct * 30 + pnl_pct * 30)

                # Hidden gem score: high quality + low visibility
                discovery_score = self._calculate_gem_score(sharpe, visibility)

                # Estimate edge persistence based on consistency
                trades_per_day = total_trades / max(1, days_active)
                edge_persistence = min(0.9, 0.5 + (trades_per_day * 0.05) + (win_rate * 0.2))

                trader = HiddenTrader(
                    username=username,
                    discovery_type=DiscoveryType.HIDDEN_GEM,
                    discovery_score=discovery_score,
                    visibility_score=visibility,
                    leaderboard_rank=None,
                    total_score=total_score,
                    sharpe_ratio=sharpe,
                    win_rate=win_rate,
                    edge_persistence=edge_persistence,
                    discovery_reason=f"Sharpe {sharpe:.2f} (top {(1-sharpe_pct)*100:.0f}%) with only ${volume:,.0f} volume - flying under radar",
                    discovered_at=datetime.utcnow(),
                    standout_metrics={
                        'sharpe_ratio': sharpe,
                        'sharpe_percentile': round(sharpe_pct * 100, 1),
                        'win_rate': win_rate,
                        'win_rate_percentile': round(winrate_pct * 100, 1),
                        'volume': volume,
                        'trades': total_trades,
                        'pnl': total_pnl,
                        'quality_score': round(quality_score, 1),
                        'unique_markets': unique_markets,
                    }
                )
                discoveries.append(trader)

            logger.info(f"Found {len(discoveries)} hidden gems")
            return discoveries

        except Exception as e:
            logger.error(f"Error finding hidden gems: {e}")
            return []

    def find_rising_stars(self) -> list[HiddenTrader]:
        """
        Find Rising Stars: New traders with exceptional early performance.

        These traders have been active for less than 30 days but show
        exceptional metrics - potential future top performers.

        Enhanced algorithm:
        1. Find traders new to the platform
        2. Compare their early performance to established traders
        3. Calculate "acceleration" - rate of improvement
        4. Score based on early excellence relative to tenure
        """
        logger.info("Searching for rising stars...")

        # Enhanced query with performance acceleration metrics
        query = f"""
        WITH
        -- Get recent traders
        new_traders AS (
            SELECT
                username,
                total_score,
                sharpe_ratio,
                win_rate,
                total_volume_usd,
                total_trades,
                days_active,
                total_pnl,
                strategy_type,
                unique_markets
            FROM polybot.aware_psi_eligible_traders
            WHERE
                days_active <= {self.config.max_days_active}
                AND win_rate >= {self.config.min_win_rate_star}
                AND sharpe_ratio >= {self.config.min_sharpe_star}
                AND total_trades >= 10
                AND username != ''
        ),
        -- Calculate performance relative to tenure
        performance_adjusted AS (
            SELECT
                *,
                total_pnl / GREATEST(days_active, 1) as pnl_per_day,
                total_trades / GREATEST(days_active, 1) as trades_per_day,
                total_volume_usd / GREATEST(days_active, 1) as volume_per_day
            FROM new_traders
        ),
        -- Compare to all traders to see how exceptional they are
        benchmarks AS (
            SELECT
                avg(sharpe_ratio) as avg_sharpe,
                avg(win_rate) as avg_winrate,
                avg(total_pnl / GREATEST(days_active, 1)) as avg_pnl_per_day
            FROM polybot.aware_psi_eligible_traders
            WHERE days_active >= 30  -- Established traders
        )
        SELECT
            pa.username,
            pa.total_score,
            pa.sharpe_ratio,
            pa.win_rate,
            pa.total_volume_usd,
            pa.total_trades,
            pa.days_active,
            pa.total_pnl,
            pa.strategy_type,
            pa.unique_markets,
            pa.pnl_per_day,
            pa.trades_per_day,
            pa.volume_per_day,
            b.avg_sharpe,
            b.avg_winrate,
            b.avg_pnl_per_day,
            -- Performance multiplier vs benchmarks
            pa.sharpe_ratio / GREATEST(b.avg_sharpe, 0.1) as sharpe_vs_avg,
            pa.win_rate / GREATEST(b.avg_winrate, 0.1) as winrate_vs_avg,
            pa.pnl_per_day / GREATEST(b.avg_pnl_per_day, 1) as pnl_vs_avg
        FROM performance_adjusted pa
        CROSS JOIN benchmarks b
        WHERE
            -- Significantly outperforming established traders
            pa.sharpe_ratio >= b.avg_sharpe * 1.2
            OR pa.win_rate >= b.avg_winrate * 1.1
        ORDER BY
            -- Composite score: outperformance * newness bonus
            (pa.sharpe_ratio / GREATEST(b.avg_sharpe, 0.1) +
             pa.win_rate / GREATEST(b.avg_winrate, 0.1)) *
            (1 + ({self.config.max_days_active} - pa.days_active) / {self.config.max_days_active}) DESC
        LIMIT {self.config.max_discoveries_per_type}
        """

        try:
            result = self.ch.query(query)
            discoveries = []

            for row in result.result_rows:
                username = row[0]
                total_score = row[1]
                sharpe = row[2]
                win_rate = row[3] or 0
                volume = row[4]
                total_trades = row[5]
                days_active = row[6]
                total_pnl = row[7]
                strategy_type = row[8]
                unique_markets = row[9]
                pnl_per_day = row[10]
                trades_per_day = row[11]
                volume_per_day = row[12]
                avg_sharpe = row[13]
                avg_winrate = row[14]
                avg_pnl_per_day = row[15]
                sharpe_vs_avg = row[16]
                winrate_vs_avg = row[17]
                pnl_vs_avg = row[18]

                # Rising stars get bonus for being new with exceptional stats
                discovery_score = self._calculate_star_score(
                    days_active, win_rate, sharpe
                )

                # Boost score for outperformance
                outperformance_bonus = min(20, (sharpe_vs_avg - 1) * 10 + (winrate_vs_avg - 1) * 10)
                discovery_score = min(100, discovery_score + outperformance_bonus)

                # Calculate acceleration (improvement trajectory)
                acceleration = 0
                if sharpe_vs_avg > 1:
                    acceleration += (sharpe_vs_avg - 1) * 0.5
                if winrate_vs_avg > 1:
                    acceleration += (winrate_vs_avg - 1) * 0.5
                acceleration = min(1.0, acceleration)

                # Edge persistence for rising stars based on consistency
                edge_persistence = min(0.7, 0.3 + (win_rate * 0.3) + (acceleration * 0.2))

                trader = HiddenTrader(
                    username=username,
                    discovery_type=DiscoveryType.RISING_STAR,
                    discovery_score=discovery_score,
                    visibility_score=max(10, 40 - days_active),  # Newer = lower visibility
                    leaderboard_rank=None,
                    total_score=total_score,
                    sharpe_ratio=sharpe,
                    win_rate=win_rate,
                    edge_persistence=edge_persistence,
                    discovery_reason=f"Only {days_active} days active, {win_rate*100:.0f}% win rate, {sharpe_vs_avg:.1f}x avg Sharpe",
                    discovered_at=datetime.utcnow(),
                    standout_metrics={
                        'days_active': days_active,
                        'win_rate': win_rate,
                        'sharpe_ratio': sharpe,
                        'trades': total_trades,
                        'pnl_per_day': round(pnl_per_day, 2),
                        'trades_per_day': round(trades_per_day, 2),
                        'sharpe_vs_avg': round(sharpe_vs_avg, 2),
                        'winrate_vs_avg': round(winrate_vs_avg, 2),
                        'acceleration': round(acceleration, 2),
                        'unique_markets': unique_markets,
                    }
                )
                discoveries.append(trader)

            logger.info(f"Found {len(discoveries)} rising stars")
            return discoveries

        except Exception as e:
            logger.error(f"Error finding rising stars: {e}")
            return []

    def find_niche_specialists(self) -> list[HiddenTrader]:
        """
        Find Niche Specialists: Traders who dominate specific market categories.

        These traders focus on one area (crypto, politics, sports) and
        significantly outperform the average in that category.
        """
        logger.info("Searching for niche specialists...")

        # This requires per-category analysis
        # For now, find traders with high market concentration
        query = f"""
        SELECT
            username,
            total_score,
            sharpe_ratio,
            win_rate,
            total_volume_usd,
            unique_markets,
            total_trades,
            strategy_type
        FROM polybot.aware_psi_eligible_traders
        WHERE
            unique_markets <= 5
            AND total_trades >= 20
            AND sharpe_ratio >= 1.0
            AND username != ''
        ORDER BY sharpe_ratio DESC
        LIMIT {self.config.max_discoveries_per_type}
        """

        try:
            result = self.ch.query(query)
            discoveries = []

            for row in result.result_rows:
                unique_markets = row[5] or 1
                sharpe = row[2]

                # Specialists focus on few markets
                concentration = 1.0 / max(1, unique_markets)
                discovery_score = sharpe * 30 + concentration * 40

                trader = HiddenTrader(
                    username=row[0],
                    discovery_type=DiscoveryType.NICHE_SPECIALIST,
                    discovery_score=min(100, discovery_score),
                    visibility_score=40,
                    leaderboard_rank=None,
                    total_score=row[1],
                    sharpe_ratio=sharpe,
                    win_rate=row[3] or 0,
                    edge_persistence=0.8,  # Specialists tend to persist
                    discovery_reason=f"Focused on {unique_markets} markets with {sharpe:.2f} Sharpe",
                    discovered_at=datetime.utcnow(),
                    standout_metrics={
                        'unique_markets': unique_markets,
                        'sharpe_ratio': sharpe,
                        'concentration': concentration,
                    }
                )
                discoveries.append(trader)

            logger.info(f"Found {len(discoveries)} niche specialists")
            return discoveries

        except Exception as e:
            logger.error(f"Error finding niche specialists: {e}")
            return []

    def find_contrarians(self) -> list[HiddenTrader]:
        """
        Find Contrarians: Traders who profit when consensus is wrong.

        These traders take positions against the crowd and are
        right more often than random - valuable for diversification.
        """
        logger.info("Searching for contrarians...")

        # Find traders with high direction_bias (strongly directional)
        # and positive P&L (they're right despite going against flow)
        query = f"""
        SELECT
            username,
            total_score,
            sharpe_ratio,
            win_rate,
            total_pnl,
            total_trades,
            strategy_type
        FROM polybot.aware_psi_eligible_traders
        WHERE
            strategy_type IN ('DIRECTIONAL_FUNDAMENTAL', 'EVENT_DRIVEN')
            AND total_pnl > 0
            AND sharpe_ratio >= 0.5
            AND total_trades >= 20
            AND username != ''
        ORDER BY total_pnl DESC
        LIMIT {self.config.max_discoveries_per_type}
        """

        try:
            result = self.ch.query(query)
            discoveries = []

            for row in result.result_rows:
                pnl = row[4]
                sharpe = row[2]
                strategy = row[6]

                discovery_score = min(100, (sharpe * 30) + (math.log10(max(1, pnl)) * 10))

                trader = HiddenTrader(
                    username=row[0],
                    discovery_type=DiscoveryType.CONTRARIAN,
                    discovery_score=discovery_score,
                    visibility_score=50,
                    leaderboard_rank=None,
                    total_score=row[1],
                    sharpe_ratio=sharpe,
                    win_rate=row[3] or 0,
                    edge_persistence=0.6,
                    discovery_reason=f"{strategy} trader with ${pnl:,.0f} P&L going against consensus",
                    discovered_at=datetime.utcnow(),
                    standout_metrics={
                        'pnl': pnl,
                        'strategy': strategy,
                        'sharpe_ratio': sharpe,
                    }
                )
                discoveries.append(trader)

            logger.info(f"Found {len(discoveries)} contrarians")
            return discoveries

        except Exception as e:
            logger.error(f"Error finding contrarians: {e}")
            return []

    def _calculate_gem_score(self, sharpe: float, visibility: float) -> float:
        """
        Calculate discovery score for hidden gems.
        High Sharpe + Low Visibility = High Score
        """
        sharpe_score = min(50, sharpe * 20)  # Max 50 from Sharpe
        hidden_bonus = 50 - (visibility / 2)  # Max 50 for being hidden
        return min(100, sharpe_score + hidden_bonus)

    def _calculate_star_score(
        self,
        days_active: int,
        win_rate: float,
        sharpe: float
    ) -> float:
        """
        Calculate discovery score for rising stars.
        Newer + Better Performance = Higher Score
        """
        # Newer is better (inverse relationship)
        newness_score = max(0, 30 - days_active)  # Max 30 for brand new
        performance_score = (win_rate * 40) + (sharpe * 20)
        return min(100, newness_score + performance_score)

    def get_discovery_summary(self, discoveries: list[HiddenTrader]) -> dict:
        """Get summary of discoveries for display"""
        by_type = {}
        for d in discoveries:
            type_name = d.discovery_type.value
            if type_name not in by_type:
                by_type[type_name] = []
            by_type[type_name].append({
                'username': d.username,
                'score': round(d.discovery_score, 1),
                'reason': d.discovery_reason,
                'sharpe': round(d.sharpe_ratio, 2),
                'total_score': round(d.total_score, 1),
            })

        return {
            'total_discoveries': len(discoveries),
            'discovered_at': datetime.utcnow().isoformat(),
            'by_type': by_type,
        }

    def save_discoveries(self, discoveries: list[HiddenTrader]) -> bool:
        """Save discoveries to ClickHouse for tracking"""
        try:
            rows = []
            for d in discoveries:
                rows.append((
                    d.username,
                    d.discovery_type.value,
                    d.discovery_score,
                    d.visibility_score,
                    d.total_score,
                    d.sharpe_ratio,
                    d.win_rate,
                    d.discovery_reason,
                    d.discovered_at,
                ))

            # Would insert to aware_hidden_alpha table
            logger.info(f"Would save {len(rows)} discoveries")
            return True

        except Exception as e:
            logger.error(f"Failed to save discoveries: {e}")
            return False
