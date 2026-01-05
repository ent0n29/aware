"""
AWARE Analytics - Data Quality Monitoring

Tracks ingestion health, data freshness, and pipeline metrics.

Usage:
    from monitoring import DataMonitor
    monitor = DataMonitor(clickhouse_client)
    health = monitor.get_health_status()
"""

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class IngestionHealth:
    """Health status of data ingestion"""
    status: str  # 'healthy', 'degraded', 'unhealthy'
    trades_last_hour: int
    trades_last_24h: int
    traders_last_24h: int
    latest_trade_at: Optional[datetime]
    ingestion_lag_seconds: int
    markets_covered: int
    avg_trades_per_hour: float
    issues: list[str]


@dataclass
class PipelineMetrics:
    """Metrics for the analytics pipeline"""
    total_trades: int
    total_traders: int
    traders_scored: int
    traders_with_pnl: int
    traders_with_sharpe: int
    resolutions_tracked: int
    last_scoring_at: Optional[datetime]
    last_pnl_calc_at: Optional[datetime]


class DataMonitor:
    """Monitors data quality and pipeline health"""

    def __init__(self, clickhouse_client):
        self.ch = clickhouse_client

    def get_health_status(self) -> IngestionHealth:
        """
        Get overall health status of data ingestion.

        Returns:
            IngestionHealth with status and metrics
        """
        issues = []

        # Get trade counts
        trades_1h = self._get_trades_since_hours(1)
        trades_24h = self._get_trades_since_hours(24)
        traders_24h = self._get_unique_traders_since_hours(24)

        # Get latest trade timestamp
        latest_trade = self._get_latest_trade_time()
        lag_seconds = 0
        if latest_trade:
            lag_seconds = int((datetime.utcnow() - latest_trade).total_seconds())

        # Get market coverage
        markets = self._get_active_markets_count()

        # Calculate average trades per hour (last 24h)
        avg_per_hour = trades_24h / 24.0 if trades_24h > 0 else 0

        # Determine health status
        status = 'healthy'

        if lag_seconds > 300:  # 5 minutes
            issues.append(f"Ingestion lag: {lag_seconds}s (>5min)")
            status = 'degraded'

        if lag_seconds > 900:  # 15 minutes
            status = 'unhealthy'

        if trades_1h == 0:
            issues.append("No trades in last hour")
            status = 'unhealthy'

        if trades_1h < avg_per_hour * 0.5 and avg_per_hour > 0:
            issues.append(f"Trade rate dropped: {trades_1h}/hr vs avg {avg_per_hour:.0f}/hr")
            if status == 'healthy':
                status = 'degraded'

        return IngestionHealth(
            status=status,
            trades_last_hour=trades_1h,
            trades_last_24h=trades_24h,
            traders_last_24h=traders_24h,
            latest_trade_at=latest_trade,
            ingestion_lag_seconds=lag_seconds,
            markets_covered=markets,
            avg_trades_per_hour=round(avg_per_hour, 1),
            issues=issues
        )

    def get_pipeline_metrics(self) -> PipelineMetrics:
        """
        Get metrics about the analytics pipeline.

        Returns:
            PipelineMetrics with counts and timestamps
        """
        return PipelineMetrics(
            total_trades=self._get_total_trades(),
            total_traders=self._get_total_traders(),
            traders_scored=self._get_scored_traders_count(),
            traders_with_pnl=self._get_traders_with_pnl(),
            traders_with_sharpe=self._get_traders_with_sharpe(),
            resolutions_tracked=self._get_resolutions_count(),
            last_scoring_at=self._get_last_scoring_time(),
            last_pnl_calc_at=self._get_last_pnl_time()
        )

    def get_daily_stats(self, days: int = 7) -> list[dict]:
        """
        Get daily trade statistics for the last N days.

        Args:
            days: Number of days to return

        Returns:
            List of daily stats dicts
        """
        query = f"""
        SELECT
            toDate(ts) AS trade_date,
            count() AS trades,
            uniqExact(proxy_address) AS traders,
            uniqExact(market_slug) AS markets,
            sum(notional) AS volume_usd
        FROM polybot.aware_global_trades_dedup
        WHERE ts >= now() - INTERVAL {days} DAY
        GROUP BY trade_date
        ORDER BY trade_date DESC
        """

        try:
            result = self.ch.query(query)
            stats = []
            for row in result.result_rows:
                stats.append({
                    'date': row[0].isoformat() if row[0] else None,
                    'trades': row[1],
                    'traders': row[2],
                    'markets': row[3],
                    'volume_usd': round(row[4], 2)
                })
            return stats
        except Exception as e:
            logger.error(f"Failed to get daily stats: {e}")
            return []

    def get_hourly_stats(self, hours: int = 24) -> list[dict]:
        """
        Get hourly trade statistics.

        Args:
            hours: Number of hours to return

        Returns:
            List of hourly stats dicts
        """
        query = f"""
        SELECT
            toStartOfHour(ts) AS hour,
            count() AS trades,
            uniqExact(proxy_address) AS traders
        FROM polybot.aware_global_trades_dedup
        WHERE ts >= now() - INTERVAL {hours} HOUR
        GROUP BY hour
        ORDER BY hour DESC
        """

        try:
            result = self.ch.query(query)
            stats = []
            for row in result.result_rows:
                stats.append({
                    'hour': row[0].isoformat() if row[0] else None,
                    'trades': row[1],
                    'traders': row[2]
                })
            return stats
        except Exception as e:
            logger.error(f"Failed to get hourly stats: {e}")
            return []

    # Private helper methods

    def _get_trades_since_hours(self, hours: int) -> int:
        query = f"""
        SELECT count()
        FROM polybot.aware_global_trades_dedup
        WHERE ts >= now() - INTERVAL {hours} HOUR
        """
        try:
            result = self.ch.query(query)
            return result.result_rows[0][0] if result.result_rows else 0
        except Exception:
            return 0

    def _get_unique_traders_since_hours(self, hours: int) -> int:
        query = f"""
        SELECT uniqExact(proxy_address)
        FROM polybot.aware_global_trades_dedup
        WHERE ts >= now() - INTERVAL {hours} HOUR
        """
        try:
            result = self.ch.query(query)
            return result.result_rows[0][0] if result.result_rows else 0
        except Exception:
            return 0

    def _get_latest_trade_time(self) -> Optional[datetime]:
        query = """
        SELECT max(ts)
        FROM polybot.aware_global_trades_dedup
        """
        try:
            result = self.ch.query(query)
            return result.result_rows[0][0] if result.result_rows else None
        except Exception:
            return None

    def _get_active_markets_count(self) -> int:
        query = """
        SELECT uniqExact(market_slug)
        FROM polybot.aware_global_trades_dedup
        WHERE ts >= now() - INTERVAL 24 HOUR
        """
        try:
            result = self.ch.query(query)
            return result.result_rows[0][0] if result.result_rows else 0
        except Exception:
            return 0

    def _get_total_trades(self) -> int:
        query = "SELECT count() FROM polybot.aware_global_trades_dedup"
        try:
            result = self.ch.query(query)
            return result.result_rows[0][0] if result.result_rows else 0
        except Exception:
            return 0

    def _get_total_traders(self) -> int:
        query = "SELECT uniqExact(proxy_address) FROM polybot.aware_global_trades_dedup"
        try:
            result = self.ch.query(query)
            return result.result_rows[0][0] if result.result_rows else 0
        except Exception:
            return 0

    def _get_scored_traders_count(self) -> int:
        query = "SELECT count() FROM polybot.aware_smart_money_scores FINAL"
        try:
            result = self.ch.query(query)
            return result.result_rows[0][0] if result.result_rows else 0
        except Exception:
            return 0

    def _get_traders_with_pnl(self) -> int:
        query = "SELECT count() FROM polybot.aware_trader_pnl FINAL WHERE total_realized_pnl != 0"
        try:
            result = self.ch.query(query)
            return result.result_rows[0][0] if result.result_rows else 0
        except Exception:
            return 0

    def _get_traders_with_sharpe(self) -> int:
        query = "SELECT count() FROM polybot.aware_ml_scores FINAL WHERE sharpe_ratio != 0"
        try:
            result = self.ch.query(query)
            return result.result_rows[0][0] if result.result_rows else 0
        except Exception:
            return 0

    def _get_resolutions_count(self) -> int:
        query = "SELECT count() FROM polybot.aware_resolutions FINAL"
        try:
            result = self.ch.query(query)
            return result.result_rows[0][0] if result.result_rows else 0
        except Exception:
            return 0

    def _get_last_scoring_time(self) -> Optional[datetime]:
        query = "SELECT max(calculated_at) FROM polybot.aware_smart_money_scores FINAL"
        try:
            result = self.ch.query(query)
            return result.result_rows[0][0] if result.result_rows else None
        except Exception:
            return None

    def _get_last_pnl_time(self) -> Optional[datetime]:
        query = "SELECT max(updated_at) FROM polybot.aware_trader_pnl FINAL"
        try:
            result = self.ch.query(query)
            return result.result_rows[0][0] if result.result_rows else None
        except Exception:
            return None


def print_health_report(clickhouse_client):
    """Print a formatted health report to console"""
    monitor = DataMonitor(clickhouse_client)

    print("\n" + "=" * 60)
    print("  AWARE Data Quality Monitor")
    print("=" * 60)

    # Ingestion health
    health = monitor.get_health_status()
    status_color = {
        'healthy': '\033[92m',  # Green
        'degraded': '\033[93m',  # Yellow
        'unhealthy': '\033[91m'  # Red
    }
    reset = '\033[0m'

    print(f"\n📊 Ingestion Status: {status_color.get(health.status, '')}{health.status.upper()}{reset}")
    print(f"   Trades (1h):     {health.trades_last_hour:,}")
    print(f"   Trades (24h):    {health.trades_last_24h:,}")
    print(f"   Traders (24h):   {health.traders_last_24h:,}")
    print(f"   Markets active:  {health.markets_covered}")
    print(f"   Avg trades/hr:   {health.avg_trades_per_hour:.0f}")
    print(f"   Ingestion lag:   {health.ingestion_lag_seconds}s")

    if health.issues:
        print(f"\n⚠️  Issues:")
        for issue in health.issues:
            print(f"   - {issue}")

    # Pipeline metrics
    metrics = monitor.get_pipeline_metrics()
    print(f"\n📈 Pipeline Metrics:")
    print(f"   Total trades:     {metrics.total_trades:,}")
    print(f"   Total traders:    {metrics.total_traders:,}")
    print(f"   Traders scored:   {metrics.traders_scored:,}")
    print(f"   Traders w/ P&L:   {metrics.traders_with_pnl:,}")
    print(f"   Traders w/ Sharpe:{metrics.traders_with_sharpe:,}")
    print(f"   Resolutions:      {metrics.resolutions_tracked:,}")

    if metrics.last_scoring_at:
        print(f"   Last scoring:     {metrics.last_scoring_at.strftime('%Y-%m-%d %H:%M')}")

    # Daily stats
    daily = monitor.get_daily_stats(days=5)
    if daily:
        print(f"\n📅 Daily Summary (last 5 days):")
        print(f"   {'Date':<12} {'Trades':>10} {'Traders':>8} {'Markets':>8} {'Volume':>12}")
        print(f"   {'-'*12} {'-'*10} {'-'*8} {'-'*8} {'-'*12}")
        for d in daily:
            print(f"   {d['date']:<12} {d['trades']:>10,} {d['traders']:>8,} {d['markets']:>8} ${d['volume_usd']:>10,.0f}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    import os
    import clickhouse_connect

    client = clickhouse_connect.get_client(
        host=os.getenv('CLICKHOUSE_HOST', 'localhost'),
        port=int(os.getenv('CLICKHOUSE_PORT', '8123')),
        database='polybot'
    )

    print_health_report(client)
