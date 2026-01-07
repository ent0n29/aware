"""
AWARE Analytics - ClickHouse Client

Read/write operations for trader profiles and scores.
"""

import os
import logging
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

import clickhouse_connect

logger = logging.getLogger(__name__)


@dataclass
class TraderMetrics:
    """Raw metrics from ClickHouse"""
    proxy_address: str
    username: str
    pseudonym: str
    total_trades: int
    total_volume_usd: float
    unique_markets: int
    first_trade_at: Optional[datetime]
    last_trade_at: Optional[datetime]
    days_active: int
    buy_count: int
    sell_count: int
    avg_trade_size: float
    avg_price: float
    # P&L from leaderboard (if available)
    total_pnl: float = 0.0


@dataclass
class TraderScore:
    """Smart Money Score result"""
    proxy_address: str
    username: str
    total_score: int
    tier: str
    profitability_score: float
    risk_adjusted_score: float
    consistency_score: float
    track_record_score: float
    strategy_type: str
    strategy_confidence: float
    rank: int


class ClickHouseClient:
    """ClickHouse client for AWARE analytics"""

    def __init__(
        self,
        host: str = None,
        port: int = None,
        database: str = None,
        username: str = "default",
        password: str = ""
    ):
        # Read from env vars with defaults
        host = host or os.getenv('CLICKHOUSE_HOST', 'localhost')
        port = port or int(os.getenv('CLICKHOUSE_PORT', '8123'))
        database = database or os.getenv('CLICKHOUSE_DATABASE', 'polybot')

        self.client = clickhouse_connect.get_client(
            host=host,
            port=port,
            database=database,
            username=username,
            password=password
        )
        self.database = database

    def query(self, sql: str, parameters: dict = None):
        """
        Execute a raw SQL query and return the result.
        Delegates to the underlying clickhouse_connect client.

        Args:
            sql: SQL query string
            parameters: Optional dict of query parameters (for parameterized queries)

        Returns:
            Query result with .result_rows attribute
        """
        if parameters:
            return self.client.query(sql, parameters=parameters)
        return self.client.query(sql)

    def get_trader_metrics(self, min_trades: int = 10, limit: int = 10000) -> list[TraderMetrics]:
        """
        Fetch trader metrics from global trades, including P&L from resolved positions.

        Args:
            min_trades: Minimum trades to be included
            limit: Max traders to return

        Returns:
            List of TraderMetrics
        """
        query = f"""
        SELECT
            t.proxy_address,
            t.username,
            any(t.pseudonym) AS pseudonym,
            count() AS total_trades,
            sum(t.notional) AS total_volume_usd,
            uniqExact(t.market_slug) AS unique_markets,
            min(t.ts) AS first_trade_at,
            max(t.ts) AS last_trade_at,
            dateDiff('day', min(t.ts), max(t.ts)) + 1 AS days_active,
            countIf(t.side = 'BUY') AS buy_count,
            countIf(t.side = 'SELL') AS sell_count,
            avg(t.notional) AS avg_trade_size,
            avg(t.price) AS avg_price,
            -- Join with P&L table to get realized P&L
            coalesce(pnl.total_realized_pnl, 0) AS total_pnl
        FROM {self.database}.aware_global_trades_dedup t
        LEFT JOIN (
            SELECT proxy_address, total_realized_pnl
            FROM {self.database}.aware_trader_pnl FINAL
        ) pnl ON t.proxy_address = pnl.proxy_address
        WHERE t.proxy_address != ''
        GROUP BY t.proxy_address, t.username, pnl.total_realized_pnl
        HAVING total_trades >= {min_trades}
        ORDER BY total_volume_usd DESC
        LIMIT {limit}
        """

        try:
            result = self.client.query(query)
            traders = []

            for row in result.result_rows:
                traders.append(TraderMetrics(
                    proxy_address=row[0],
                    username=row[1] or '',
                    pseudonym=row[2] or '',
                    total_trades=row[3],
                    total_volume_usd=row[4],
                    unique_markets=row[5],
                    first_trade_at=row[6],
                    last_trade_at=row[7],
                    days_active=row[8],
                    buy_count=row[9],
                    sell_count=row[10],
                    avg_trade_size=row[11],
                    avg_price=row[12],
                    total_pnl=row[13] or 0.0  # Include P&L from joined table
                ))

            logger.info(f"Fetched metrics for {len(traders)} traders")
            return traders

        except Exception as e:
            logger.error(f"Failed to fetch trader metrics: {e}")
            return []

    def get_strategy_indicators(self, proxy_address: str) -> dict:
        """
        Get strategy indicators for a trader.

        Returns dict with complete_set_ratio, direction_bias, etc.

        NOTE: For batch operations, use get_all_strategy_indicators() instead.
        """
        query = f"""
        WITH trades AS (
            SELECT
                condition_id,
                outcome_index,
                side,
                count() AS trade_count
            FROM {self.database}.aware_global_trades_dedup
            WHERE proxy_address = %(proxy_address)s
            GROUP BY condition_id, outcome_index, side
        ),
        markets AS (
            SELECT
                condition_id,
                uniqExact(outcome_index) AS outcomes_traded
            FROM trades
            GROUP BY condition_id
        )
        SELECT
            -- Complete set ratio (markets with both outcomes)
            countIf(outcomes_traded >= 2) / count() AS complete_set_ratio,
            -- Direction bias (YES vs NO buys)
            sumIf(trade_count, outcome_index = 0 AND side = 'BUY') /
                nullIf(sumIf(trade_count, side = 'BUY'), 0) AS direction_bias
        FROM markets
        LEFT JOIN trades USING (condition_id)
        """

        try:
            result = self.client.query(query, parameters={'proxy_address': proxy_address})
            if result.result_rows:
                row = result.result_rows[0]
                return {
                    'complete_set_ratio': float(row[0] or 0),
                    'direction_bias': float(row[1] or 0.5)
                }
        except Exception as e:
            logger.warning(f"Failed to get strategy indicators for {proxy_address}: {e}")

        return {'complete_set_ratio': 0.0, 'direction_bias': 0.5}

    def get_all_strategy_indicators(self, limit: int = 10000) -> dict[str, dict]:
        """
        Get strategy indicators for ALL traders in a single batch query.

        This is much more efficient than calling get_strategy_indicators()
        for each trader individually (10,000 queries → 1 query).

        Args:
            limit: Maximum number of traders to process

        Returns:
            Dict mapping proxy_address to {complete_set_ratio, direction_bias}
        """
        query = f"""
        WITH
        -- Get trade counts per trader/market/outcome/side
        trades AS (
            SELECT
                proxy_address,
                condition_id,
                outcome_index,
                side,
                count() AS trade_count
            FROM {self.database}.aware_global_trades_dedup
            WHERE proxy_address != ''
            GROUP BY proxy_address, condition_id, outcome_index, side
        ),
        -- Count outcomes per trader/market
        market_outcomes AS (
            SELECT
                proxy_address,
                condition_id,
                uniqExact(outcome_index) AS outcomes_traded
            FROM trades
            GROUP BY proxy_address, condition_id
        ),
        -- Aggregate per trader
        trader_indicators AS (
            SELECT
                mo.proxy_address,
                -- Complete set ratio: markets where trader traded both outcomes
                countIf(mo.outcomes_traded >= 2) / nullIf(count(), 0) AS complete_set_ratio,
                -- Direction bias: proportion of YES buys vs all buys
                sumIf(t.trade_count, t.outcome_index = 0 AND t.side = 'BUY') /
                    nullIf(sumIf(t.trade_count, t.side = 'BUY'), 0) AS direction_bias
            FROM market_outcomes mo
            LEFT JOIN trades t ON mo.proxy_address = t.proxy_address
                AND mo.condition_id = t.condition_id
            GROUP BY mo.proxy_address
        ),
        -- Join with trade volume to get top traders by volume (matching get_trader_metrics order)
        volume_ranked AS (
            SELECT
                proxy_address,
                sum(notional) AS total_volume
            FROM {self.database}.aware_global_trades_dedup
            WHERE proxy_address != ''
            GROUP BY proxy_address
            ORDER BY total_volume DESC
            LIMIT {limit}
        )
        SELECT
            ti.proxy_address,
            ti.complete_set_ratio,
            ti.direction_bias
        FROM trader_indicators ti
        INNER JOIN volume_ranked vr ON ti.proxy_address = vr.proxy_address
        """

        try:
            logger.info("Fetching strategy indicators for all traders (batch)...")
            result = self.client.query(query)

            indicators = {}
            for row in result.result_rows:
                proxy_address = row[0]
                indicators[proxy_address] = {
                    'complete_set_ratio': float(row[1] or 0),
                    'direction_bias': float(row[2] or 0.5)
                }

            logger.info(f"Fetched strategy indicators for {len(indicators)} traders")
            return indicators

        except Exception as e:
            logger.error(f"Failed to batch fetch strategy indicators: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def save_trader_profiles(self, profiles: list[dict]) -> int:
        """
        Save trader profiles to ClickHouse.

        Args:
            profiles: List of profile dictionaries

        Returns:
            Number of profiles saved
        """
        if not profiles:
            return 0

        columns = [
            'proxy_address', 'username', 'pseudonym',
            'total_trades', 'total_volume_usd', 'unique_markets',
            'first_trade_at', 'last_trade_at', 'days_active',
            'total_pnl', 'realized_pnl', 'unrealized_pnl',
            'buy_count', 'sell_count', 'avg_trade_size', 'avg_price',
            'complete_set_ratio', 'direction_bias',
            'updated_at', 'data_quality'
        ]

        data = []
        for p in profiles:
            data.append([
                p.get('proxy_address', ''),
                p.get('username', ''),
                p.get('pseudonym', ''),
                p.get('total_trades', 0),
                p.get('total_volume_usd', 0.0),
                p.get('unique_markets', 0),
                p.get('first_trade_at'),
                p.get('last_trade_at'),
                p.get('days_active', 0),
                p.get('total_pnl', 0.0),
                p.get('realized_pnl', 0.0),
                p.get('unrealized_pnl', 0.0),
                p.get('buy_count', 0),
                p.get('sell_count', 0),
                p.get('avg_trade_size', 0.0),
                p.get('avg_price', 0.0),
                p.get('complete_set_ratio', 0.0),
                p.get('direction_bias', 0.5),
                datetime.utcnow(),
                p.get('data_quality', 'good')
            ])

        try:
            self.client.insert(
                f'{self.database}.aware_trader_profiles',
                data,
                column_names=columns
            )
            logger.info(f"Saved {len(profiles)} trader profiles")
            return len(profiles)

        except Exception as e:
            logger.error(f"Failed to save trader profiles: {e}")
            return 0

    def save_smart_money_scores(self, scores: list[TraderScore], model_version: str = "v1") -> int:
        """
        Save Smart Money Scores to ClickHouse.

        Args:
            scores: List of TraderScore objects
            model_version: Version of scoring model

        Returns:
            Number of scores saved
        """
        if not scores:
            return 0

        columns = [
            'proxy_address', 'username', 'total_score', 'tier',
            'profitability_score', 'risk_adjusted_score',
            'consistency_score', 'track_record_score',
            'strategy_type', 'strategy_confidence',
            'rank', 'rank_change', 'calculated_at', 'model_version'
        ]

        data = []
        now = datetime.utcnow()

        for s in scores:
            data.append([
                s.proxy_address,
                s.username,
                s.total_score,
                s.tier,
                s.profitability_score,
                s.risk_adjusted_score,
                s.consistency_score,
                s.track_record_score,
                s.strategy_type,
                s.strategy_confidence,
                s.rank,
                0,  # rank_change (calculated separately)
                now,
                model_version
            ])

        try:
            # Insert current scores
            self.client.insert(
                f'{self.database}.aware_smart_money_scores',
                data,
                column_names=columns
            )

            # Also insert to history
            history_columns = [
                'proxy_address', 'username', 'total_score', 'tier', 'rank', 'calculated_at'
            ]
            history_data = [
                [s.proxy_address, s.username, s.total_score, s.tier, s.rank, now]
                for s in scores
            ]
            self.client.insert(
                f'{self.database}.aware_smart_money_scores_history',
                history_data,
                column_names=history_columns
            )

            logger.info(f"Saved {len(scores)} Smart Money Scores")
            return len(scores)

        except Exception as e:
            logger.error(f"Failed to save Smart Money Scores: {e}")
            return 0

    def get_trader_count(self) -> int:
        """Get total number of unique traders"""
        try:
            result = self.client.query(
                f"SELECT uniqExact(proxy_address) FROM {self.database}.aware_global_trades_dedup"
            )
            return result.result_rows[0][0] if result.result_rows else 0
        except Exception:
            return 0

    def get_trade_count(self) -> int:
        """Get total number of trades"""
        try:
            result = self.client.query(
                f"SELECT count() FROM {self.database}.aware_global_trades_dedup"
            )
            return result.result_rows[0][0] if result.result_rows else 0
        except Exception:
            return 0

    def insert(self, table: str, data: list, column_names: list[str]) -> None:
        """
        Insert data into a ClickHouse table.

        Args:
            table: Table name (can include database prefix)
            data: List of rows to insert
            column_names: List of column names
        """
        # Add database prefix if not already present
        if '.' not in table:
            table = f"{self.database}.{table}"

        self.client.insert(table, data, column_names=column_names)

    def command(self, sql: str) -> None:
        """Execute a command (INSERT, CREATE, etc.) that doesn't return results."""
        self.client.command(sql)
