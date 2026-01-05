"""
AWARE Analytics - P&L Calculator

Calculates realized P&L for traders based on their positions in resolved markets.

Formula:
    net_shares = BUY_shares - SELL_shares
    net_cost = BUY_value - SELL_value
    realized_pnl = (settlement_price × net_shares) - net_cost

Usage:
    calculator = PnLCalculator(ch_client)
    traders_updated = calculator.run()
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PositionPnL:
    """P&L for a single position (trader + market + outcome)"""
    proxy_address: str
    username: str
    condition_id: str
    market_slug: str
    outcome: str
    net_shares: float
    net_cost: float
    avg_entry_price: float
    settlement_price: float
    realized_pnl: float
    buy_count: int
    sell_count: int
    first_trade_at: Optional[datetime]
    last_trade_at: Optional[datetime]
    resolved_at: Optional[datetime]


@dataclass
class TraderPnL:
    """Aggregate P&L for a trader"""
    proxy_address: str
    username: str
    total_realized_pnl: float
    total_positions_closed: int
    winning_positions: int
    losing_positions: int
    win_rate: float


class PnLCalculator:
    """
    Calculates realized P&L from trade positions and market resolutions.

    The calculation joins trades with resolution data to determine
    actual profit/loss for each closed position.
    """

    def __init__(self, clickhouse_client):
        self.ch = clickhouse_client

    def run(self) -> int:
        """
        Main entry point: calculate and store P&L for all traders.

        Returns:
            Number of traders with P&L updated
        """
        logger.info("Starting P&L calculation...")

        # Step 1: Calculate position-level P&L
        positions = self._calculate_position_pnl()
        logger.info(f"Calculated P&L for {len(positions)} positions")

        if not positions:
            logger.info("No resolved positions found")
            return 0

        # Step 2: Store position P&L
        stored_positions = self._store_position_pnl(positions)
        logger.info(f"Stored {stored_positions} position P&L records")

        # Step 3: Aggregate to trader level
        trader_pnl = self._aggregate_trader_pnl(positions)
        logger.info(f"Aggregated P&L for {len(trader_pnl)} traders")

        # Step 4: Store trader P&L
        stored_traders = self._store_trader_pnl(trader_pnl)
        logger.info(f"Stored {stored_traders} trader P&L records")

        # Note: Profile updates are handled by the scoring job, which includes
        # P&L data from aware_trader_pnl when building profiles. This prevents
        # data quality issues from partial profile updates.

        return len(trader_pnl)

    def _calculate_position_pnl(self) -> list[PositionPnL]:
        """
        Calculate P&L for each position in resolved markets.

        Uses SQL to efficiently join trades with resolutions.
        """
        query = """
        WITH
        -- Get settlement prices for resolved markets
        resolutions AS (
            SELECT
                condition_id,
                market_slug,
                winning_outcome,
                winning_outcome_index,
                outcome_prices,
                resolution_time
            FROM polybot.aware_market_resolutions FINAL
            WHERE is_resolved = 1
        ),
        -- Aggregate trades per position
        positions AS (
            SELECT
                t.proxy_address,
                t.username,
                t.condition_id,
                t.market_slug,
                t.outcome,
                t.outcome_index,
                -- Net shares: BUY adds, SELL subtracts
                sum(if(t.side = 'BUY', t.size, -t.size)) AS net_shares,
                -- Net cost: BUY adds (price * size), SELL subtracts
                sum(if(t.side = 'BUY', t.notional, -t.notional)) AS net_cost,
                -- Average entry price
                sumIf(t.notional, t.side = 'BUY') / nullIf(sumIf(t.size, t.side = 'BUY'), 0) AS avg_entry_price,
                -- Trade counts
                countIf(t.side = 'BUY') AS buy_count,
                countIf(t.side = 'SELL') AS sell_count,
                min(t.ts) AS first_trade_at,
                max(t.ts) AS last_trade_at
            FROM polybot.aware_global_trades_dedup t
            WHERE t.condition_id IN (SELECT condition_id FROM resolutions)
              AND t.proxy_address != ''
            GROUP BY t.proxy_address, t.username, t.condition_id, t.market_slug, t.outcome, t.outcome_index
        )
        SELECT
            p.proxy_address,
            p.username,
            p.condition_id,
            p.market_slug,
            p.outcome,
            p.net_shares,
            p.net_cost,
            coalesce(p.avg_entry_price, 0) AS avg_entry_price,
            -- Settlement price: 1.0 if this outcome won, 0.0 otherwise
            if(p.outcome_index = r.winning_outcome_index, 1.0, 0.0) AS settlement_price,
            -- Realized P&L = (settlement_price * net_shares) - net_cost
            if(p.outcome_index = r.winning_outcome_index, 1.0, 0.0) * p.net_shares - p.net_cost AS realized_pnl,
            p.buy_count,
            p.sell_count,
            p.first_trade_at,
            p.last_trade_at,
            r.resolution_time
        FROM positions p
        INNER JOIN resolutions r ON p.condition_id = r.condition_id
        WHERE abs(p.net_shares) > 0.001  -- Include if still holding shares
           OR abs(p.net_cost) > 0.01     -- OR if spent money (captures closed positions)
        ORDER BY abs(realized_pnl) DESC
        """

        try:
            result = self.ch.query(query)
            positions = []

            for row in result.result_rows:
                positions.append(PositionPnL(
                    proxy_address=row[0],
                    username=row[1] or '',
                    condition_id=row[2],
                    market_slug=row[3],
                    outcome=row[4],
                    net_shares=float(row[5]),
                    net_cost=float(row[6]),
                    avg_entry_price=float(row[7]),
                    settlement_price=float(row[8]),
                    realized_pnl=float(row[9]),
                    buy_count=int(row[10]),
                    sell_count=int(row[11]),
                    first_trade_at=row[12],
                    last_trade_at=row[13],
                    resolved_at=row[14]
                ))

            return positions

        except Exception as e:
            logger.error(f"Failed to calculate position P&L: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _store_position_pnl(self, positions: list[PositionPnL]) -> int:
        """Store position-level P&L in ClickHouse"""
        if not positions:
            return 0

        columns = [
            'proxy_address', 'username', 'condition_id', 'market_slug', 'outcome',
            'net_shares', 'net_cost', 'avg_entry_price', 'settlement_price', 'realized_pnl',
            'buy_count', 'sell_count', 'total_trades',
            'first_trade_at', 'last_trade_at', 'resolved_at', 'calculated_at'
        ]

        now = datetime.utcnow()
        data = []

        for p in positions:
            data.append([
                p.proxy_address,
                p.username,
                p.condition_id,
                p.market_slug,
                p.outcome,
                p.net_shares,
                p.net_cost,
                p.avg_entry_price,
                p.settlement_price,
                p.realized_pnl,
                p.buy_count,
                p.sell_count,
                p.buy_count + p.sell_count,
                p.first_trade_at or now,
                p.last_trade_at or now,
                p.resolved_at or now,
                now
            ])

        try:
            self.ch.insert(
                'polybot.aware_position_pnl',
                data,
                column_names=columns
            )
            return len(data)

        except Exception as e:
            logger.error(f"Failed to store position P&L: {e}")
            return 0

    def _aggregate_trader_pnl(self, positions: list[PositionPnL]) -> list[TraderPnL]:
        """Aggregate positions to trader-level P&L"""
        by_trader = {}

        for p in positions:
            key = p.proxy_address
            if key not in by_trader:
                by_trader[key] = {
                    'proxy_address': p.proxy_address,
                    'username': p.username,
                    'total_realized_pnl': 0.0,
                    'total_positions_closed': 0,
                    'winning_positions': 0,
                    'losing_positions': 0
                }

            by_trader[key]['total_realized_pnl'] += p.realized_pnl
            by_trader[key]['total_positions_closed'] += 1

            if p.realized_pnl > 0:
                by_trader[key]['winning_positions'] += 1
            elif p.realized_pnl < 0:
                by_trader[key]['losing_positions'] += 1

        # Convert to TraderPnL objects
        traders = []
        for data in by_trader.values():
            total = data['total_positions_closed']
            win_rate = data['winning_positions'] / total if total > 0 else 0.0

            traders.append(TraderPnL(
                proxy_address=data['proxy_address'],
                username=data['username'],
                total_realized_pnl=data['total_realized_pnl'],
                total_positions_closed=data['total_positions_closed'],
                winning_positions=data['winning_positions'],
                losing_positions=data['losing_positions'],
                win_rate=win_rate
            ))

        # Sort by P&L descending
        traders.sort(key=lambda x: x.total_realized_pnl, reverse=True)

        return traders

    def _store_trader_pnl(self, traders: list[TraderPnL]) -> int:
        """Store trader-level P&L in ClickHouse"""
        if not traders:
            return 0

        columns = [
            'proxy_address', 'username',
            'total_realized_pnl', 'total_positions_closed',
            'winning_positions', 'losing_positions', 'win_rate',
            'top_winning_markets', 'top_losing_markets',
            'first_resolution_at', 'last_resolution_at', 'calculated_at'
        ]

        now = datetime.utcnow()
        data = []

        for t in traders:
            data.append([
                t.proxy_address,
                t.username,
                t.total_realized_pnl,
                t.total_positions_closed,
                t.winning_positions,
                t.losing_positions,
                t.win_rate,
                [],  # top_winning_markets (TODO: populate)
                [],  # top_losing_markets (TODO: populate)
                now,  # first_resolution_at
                now,  # last_resolution_at
                now
            ])

        try:
            self.ch.insert(
                'polybot.aware_trader_pnl',
                data,
                column_names=columns
            )
            return len(data)

        except Exception as e:
            logger.error(f"Failed to store trader P&L: {e}")
            return 0

    def _update_trader_profiles(self, traders: list[TraderPnL]) -> int:
        """Update trader profiles with realized P&L"""
        if not traders:
            return 0

        # Build update query for each trader
        updated = 0

        for t in traders:
            try:
                # Use ALTER TABLE UPDATE for ReplacingMergeTree
                # Note: This updates the existing row in-place
                query = f"""
                ALTER TABLE polybot.aware_trader_profiles
                UPDATE
                    realized_pnl = {t.total_realized_pnl},
                    total_pnl = {t.total_realized_pnl},
                    updated_at = now64(3)
                WHERE proxy_address = '{t.proxy_address}'
                """

                self.ch.command(query)
                updated += 1

            except Exception as e:
                logger.debug(f"Failed to update profile for {t.proxy_address}: {e}")
                # If ALTER fails, try inserting a new row that will be merged
                try:
                    self._upsert_profile_pnl(t)
                    updated += 1
                except Exception:
                    pass

        return updated

    def _upsert_profile_pnl(self, trader: TraderPnL):
        """Insert/update profile P&L using ReplacingMergeTree pattern.

        IMPORTANT: We must preserve existing profile fields when updating P&L.
        ReplacingMergeTree keeps the row with the newest updated_at, so we need
        to include all existing data to avoid zeroing out trade counts, volume, etc.
        """
        # First, fetch existing profile data to preserve it
        existing_query = f"""
        SELECT
            total_trades,
            total_volume_usd,
            unique_markets,
            first_trade_at,
            last_trade_at,
            days_active,
            buy_count,
            sell_count,
            avg_trade_size,
            avg_price,
            complete_set_ratio,
            direction_bias,
            data_quality
        FROM polybot.aware_trader_profiles FINAL
        WHERE proxy_address = '{trader.proxy_address}'
        """

        # Default values
        total_trades = 0
        total_volume_usd = 0.0
        unique_markets = 0
        first_trade_at = "now64(3)"
        last_trade_at = "now64(3)"
        days_active = 0
        buy_count = 0
        sell_count = 0
        avg_trade_size = 0.0
        avg_price = 0.0
        complete_set_ratio = 0.0
        direction_bias = 0.5
        existing_quality = 'partial'

        try:
            result = self.ch.query(existing_query)
            if result.result_rows:
                row = result.result_rows[0]
                total_trades = row[0] or 0
                total_volume_usd = row[1] or 0.0
                unique_markets = row[2] or 0
                first_trade_at = f"'{row[3]}'" if row[3] else "now64(3)"
                last_trade_at = f"'{row[4]}'" if row[4] else "now64(3)"
                days_active = row[5] or 0
                buy_count = row[6] or 0
                sell_count = row[7] or 0
                avg_trade_size = row[8] or 0.0
                avg_price = row[9] or 0.0
                complete_set_ratio = row[10] or 0.0
                direction_bias = row[11] if row[11] is not None else 0.5
                existing_quality = row[12] or 'partial'
        except Exception as e:
            logger.debug(f"No existing profile for {trader.proxy_address}: {e}")

        # Determine data quality - preserve 'good' if exists, else mark as pnl_calculated
        data_quality = existing_quality if existing_quality == 'good' else 'pnl_calculated'

        # Escape username for SQL
        safe_username = trader.username.replace("'", "''") if trader.username else ''

        # Insert complete row with all fields preserved
        query = f"""
        INSERT INTO polybot.aware_trader_profiles
            (proxy_address, username, pseudonym,
             total_trades, total_volume_usd, unique_markets,
             first_trade_at, last_trade_at, days_active,
             total_pnl, realized_pnl, unrealized_pnl,
             buy_count, sell_count, avg_trade_size, avg_price,
             complete_set_ratio, direction_bias,
             updated_at, data_quality)
        VALUES
            ('{trader.proxy_address}', '{safe_username}', '',
             {total_trades}, {total_volume_usd}, {unique_markets},
             {first_trade_at}, {last_trade_at}, {days_active},
             {trader.total_realized_pnl}, {trader.total_realized_pnl}, 0,
             {buy_count}, {sell_count}, {avg_trade_size}, {avg_price},
             {complete_set_ratio}, {direction_bias},
             now64(3), '{data_quality}')
        """

        self.ch.command(query)

    def get_pnl_summary(self) -> dict:
        """Get summary statistics of P&L calculations"""
        query = """
        SELECT
            count() AS total_traders,
            sum(total_realized_pnl) AS total_pnl,
            avg(total_realized_pnl) AS avg_pnl,
            countIf(total_realized_pnl > 0) AS profitable_traders,
            countIf(total_realized_pnl < 0) AS losing_traders,
            avg(win_rate) AS avg_win_rate
        FROM polybot.aware_trader_pnl FINAL
        """

        try:
            result = self.ch.query(query)
            if result.result_rows:
                row = result.result_rows[0]
                return {
                    'total_traders': row[0],
                    'total_pnl': round(row[1] or 0, 2),
                    'avg_pnl': round(row[2] or 0, 2),
                    'profitable_traders': row[3],
                    'losing_traders': row[4],
                    'avg_win_rate': round(row[5] or 0, 3)
                }
        except Exception as e:
            logger.error(f"Failed to get P&L summary: {e}")

        return {}

    def get_top_traders(self, limit: int = 20) -> list[dict]:
        """Get top traders by realized P&L"""
        query = f"""
        SELECT
            username,
            proxy_address,
            total_realized_pnl,
            total_positions_closed,
            win_rate
        FROM polybot.aware_trader_pnl FINAL
        ORDER BY total_realized_pnl DESC
        LIMIT {limit}
        """

        try:
            result = self.ch.query(query)
            return [
                {
                    'username': row[0],
                    'proxy_address': row[1],
                    'pnl': round(row[2], 2),
                    'positions': row[3],
                    'win_rate': round(row[4], 3)
                }
                for row in result.result_rows
            ]
        except Exception as e:
            logger.error(f"Failed to get top traders: {e}")
            return []


def run_pnl_calculation(clickhouse_client) -> dict:
    """Convenience function to run P&L calculation"""
    calculator = PnLCalculator(clickhouse_client)
    traders_updated = calculator.run()

    return {
        'status': 'success',
        'traders_updated': traders_updated,
        'summary': calculator.get_pnl_summary(),
        'top_traders': calculator.get_top_traders(10)
    }
