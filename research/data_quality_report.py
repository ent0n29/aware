#!/usr/bin/env python3
"""
Quick "are we collecting the right data?" report.

Focuses on the two biggest gaps for reverse-engineering accuracy:
- decision-time market state (WS TOB vs trade-triggered TOB, which is very stale)
- on-chain receipts (needed for fees + log decoding)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _has_format(sql: str) -> bool:
    return " format " in f" {sql.lower()} "


@dataclass(frozen=True)
class QueryResult:
    result_rows: list[tuple[str, ...]]


@dataclass(frozen=True)
class ClickHouseHttp:
    url: str
    database: str
    user: str
    password: str
    timeout_seconds: int

    def _post(self, sql: str) -> str:
        params = {"database": self.database}
        if self.user:
            params["user"] = self.user
        if self.password:
            params["password"] = self.password
        full = f"{self.url.rstrip('/')}/?{urlencode(params)}"
        req = Request(full, data=sql.encode("utf-8"), method="POST")
        with urlopen(req, timeout=self.timeout_seconds) as resp:
            return resp.read().decode("utf-8")

    def query(self, sql: str) -> QueryResult:
        sql = sql.strip().rstrip(";")
        if not _has_format(sql):
            sql = sql + "\nFORMAT TabSeparated"
        text = self._post(sql)
        rows: list[tuple[str, ...]] = []
        for line in text.splitlines():
            if not line.strip():
                continue
            rows.append(tuple(line.split("\t")))
        return QueryResult(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", default=os.getenv("POLYMARKET_TARGET_USER", "TARGET_USER"))
    ap.add_argument("--lookback-minutes", type=int, default=60)
    args = ap.parse_args()

    user = args.username
    lookback = max(1, int(args.lookback_minutes))
    time_where = f"AND ts >= now() - INTERVAL {lookback} MINUTE"

    client = ClickHouseHttp(
        url=(
            os.getenv("CLICKHOUSE_URL")
            or f"http://{os.getenv('CLICKHOUSE_HOST', '127.0.0.1')}:{os.getenv('CLICKHOUSE_PORT', '8123')}"
        ),
        database=os.getenv("CLICKHOUSE_DATABASE", "polybot"),
        user=os.getenv("CLICKHOUSE_USER", "intellij"),
        password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        timeout_seconds=int(os.getenv("CLICKHOUSE_TIMEOUT_SECONDS", "30")),
    )

    print("=" * 80)
    print("DATA QUALITY REPORT")
    print(f"Timestamp: {datetime.utcnow().isoformat(timespec='seconds')}Z")
    print(f"Username:  {user}")
    print(f"Lookback:  {lookback} minutes")
    print("=" * 80)

    tables = set(r[0] for r in client.query("SHOW TABLES").result_rows)
    # Prefer the raw `user_trades` table because it supports efficient time-window filtering.
    # `user_trades_dedup` is a global aggregate view and becomes extremely expensive for lookbacks.
    trade_source = None
    for candidate in ("user_trades", "user_trades_dedup", "user_trade_enriched_v4", "user_trade_enriched_v3", "user_trade_enriched_v2"):
        if candidate in tables:
            trade_source = candidate
            break
    if trade_source is None:
        print("No trade source found (expected user_trades or user_trade_enriched_v2/v3/v4).")
        return 2

    uses_enriched = trade_source.startswith("user_trade_enriched")
    columns = set(r[0] for r in client.query(f"DESCRIBE TABLE {trade_source}").result_rows)

    print(f"\nUsing trade source: {trade_source}")

    # Core dataset
    if uses_enriched and "settle_price" in columns and "seconds_to_end" in columns:
        r = client.query(
            f"""
            SELECT
              count() AS trades,
              countIf(settle_price IS NOT NULL) AS resolved,
              countIf(seconds_to_end IS NOT NULL) AS with_timing
            FROM {trade_source}
            WHERE username = '{user}'
              {time_where}
            """
        ).result_rows[0]
        trades, resolved, with_timing = int(r[0]), int(r[1]), int(r[2])
    else:
        r = client.query(
            f"""
            SELECT
              count() AS trades
            FROM {trade_source}
            WHERE username = '{user}'
              {time_where}
            """
        ).result_rows[0]
        trades, resolved, with_timing = int(r[0]), 0, 0
    print("\n=== Trades ===")
    print(f"Trades:    {trades:,}")
    print(f"Resolved:  {resolved:,}")
    print(f"Timing:    {with_timing:,}")

    # Trade-triggered TOB lag
    if "tob_captured_at" in columns:
        r = client.query(
            f"""
            SELECT
              count() AS n,
              quantileExact(0.5)(abs(dateDiff('millisecond', tob_captured_at, ts))) AS p50_abs_lag_ms,
              quantileExact(0.9)(abs(dateDiff('millisecond', tob_captured_at, ts))) AS p90_abs_lag_ms,
              quantileExact(0.99)(abs(dateDiff('millisecond', tob_captured_at, ts))) AS p99_abs_lag_ms
            FROM {trade_source}
            WHERE username = '{user}'
              {time_where}
              AND tob_captured_at > toDateTime64('2000-01-01 00:00:00',3)
            """
        ).result_rows[0]
        print("\n=== TOB Snapshot Lag (trade-triggered) ===")
        print(f"Rows:   {int(r[0]):,}")
        print(f"P50:    {int(r[1]):,} ms")
        print(f"P90:    {int(r[2]):,} ms")
        print(f"P99:    {int(r[3]):,} ms")
    else:
        print("\n=== TOB Snapshot Lag (trade-triggered) ===")
        print("Skipping: tob_captured_at not available in trade source.")

    # WS TOB coverage (ASOF join on token_id).
    #
    # Note: do NOT use `user_trades_dedup` here; it forces a global GROUP BY and blows up memory.
    if "token_id" in columns and "market_ws_tob" in tables:
        r = client.query(
            f"""
            SELECT
              count() AS trades,
              countIf(ws.asset_id != '') AS with_ws,
              round(with_ws * 100.0 / trades, 2) AS pct_with_ws,
              countIf(ws.asset_id != '' AND abs(dateDiff('millisecond', ws.ts, t.ts)) <= 500) AS with_ws_le_500ms,
              round(with_ws_le_500ms * 100.0 / trades, 2) AS pct_with_ws_le_500ms,
              countIf(ws.asset_id != '' AND abs(dateDiff('millisecond', ws.ts, t.ts)) <= 2000) AS with_ws_le_2s,
              round(with_ws_le_2s * 100.0 / trades, 2) AS pct_with_ws_le_2s,
              quantileExactIf(0.5)(abs(dateDiff('millisecond', ws.ts, t.ts)), ws.asset_id != '') AS p50_ws_lag_ms,
              quantileExactIf(0.9)(abs(dateDiff('millisecond', ws.ts, t.ts)), ws.asset_id != '') AS p90_ws_lag_ms
            FROM polybot.{trade_source} t
            ASOF LEFT JOIN polybot.market_ws_tob ws
              ON t.token_id = ws.asset_id AND t.ts >= ws.ts
            WHERE t.username = '{user}'
              {time_where.replace('ts', 't.ts')}
            """
        ).result_rows[0]
        print("\n=== WS TOB Coverage (ASOF join) ===")
        print(f"Trades (lookback): {int(r[0]):,}")
        print(f"With WS:           {int(r[1]):,} ({float(r[2]):.2f}%)")
        print(f"With WS <= 500ms:  {int(r[3]):,} ({float(r[4]):.2f}%)")
        print(f"With WS <= 2s:     {int(r[5]):,} ({float(r[6]):.2f}%)")
        if r[7] is not None:
            print(f"WS lag P50:        {int(r[7]):,} ms")
            print(f"WS lag P90:        {int(r[8]):,} ms")
    else:
        print("\n=== WS TOB Coverage (ASOF join) ===")
        print("Skipping: token_id or market_ws_tob not available.")

    # Polygon receipts coverage (if enabled)
    if "tx_block_number" in columns:
        r = client.query(
            f"""
            SELECT
              countIf(tx_block_number IS NOT NULL) AS trades_with_receipt_join,
              minIf(ts, tx_block_number IS NOT NULL) AS first_trade_with_receipt,
              maxIf(ts, tx_block_number IS NOT NULL) AS last_trade_with_receipt
            FROM {trade_source}
            WHERE username = '{user}'
              {time_where}
            """
        ).result_rows[0]
        print("\n=== Polygon Receipt Join (trades) ===")
        print(f"Trades w/receipt:  {int(r[0]):,}")
        print(f"First trade w/tx:  {r[1]}")
        print(f"Last trade w/tx:   {r[2]}")
    elif "block_number" in columns:
        r = client.query(
            f"""
            SELECT
              countIf(block_number > 0) AS trades_with_block,
              minIf(ts, block_number > 0) AS first_trade_with_block,
              maxIf(ts, block_number > 0) AS last_trade_with_block
            FROM {trade_source}
            WHERE username = '{user}'
              {time_where}
            """
        ).result_rows[0]
        print("\n=== Polygon Receipt Join (trades) ===")
        print(f"Trades w/block:    {int(r[0]):,}")
        print(f"First trade w/blk: {r[1]}")
        print(f"Last trade w/blk:  {r[2]}")
    else:
        print("\n=== Polygon Receipt Join (trades) ===")
        print("Skipping: tx_block_number not available in trade source.")

    if "polygon_tx_receipts_latest" in tables and "transaction_hash" in columns:
        r = client.query(
            f"""
            SELECT
              countDistinct(lower(u.transaction_hash)) AS total_txs,
              countDistinctIf(lower(u.transaction_hash), pr.tx_hash != '') AS txs_with_receipts,
              (total_txs - txs_with_receipts) AS missing_txs
            FROM polybot.{trade_source} u
            LEFT JOIN polybot.polygon_tx_receipts_latest pr
              ON pr.tx_hash = lower(u.transaction_hash)
            WHERE u.username = '{user}'
              {time_where.replace('ts', 'u.ts')}
              AND u.transaction_hash != ''
            """
        ).result_rows[0]
        print("\nReceipt backlog (tx-level):")
        print(f"Tx hashes total:    {int(r[0]):,}")
        print(f"Txs with receipts:  {int(r[1]):,}")
        print(f"Txs missing:        {int(r[2]):,}")
    else:
        print("\nReceipt backlog (tx-level):")
        print("Skipping: polygon_tx_receipts_latest missing or transaction_hash unavailable.")

    if "polygon_tx_receipts" in tables:
        r = client.query(
            f"""
            SELECT
              count() AS receipt_rows,
              countDistinct(tx_hash) AS distinct_txs,
              max(block_timestamp) AS last_block_ts
            FROM polybot.polygon_tx_receipts
            """
        ).result_rows[0]
        print("\n=== Polygon Receipts Table ===")
        print(f"Rows:      {int(r[0]):,}")
        print(f"Tx hashes: {int(r[1]):,}")
        print(f"Last blk:  {r[2]}")
    else:
        print("\n=== Polygon Receipts Table ===")
        print("Skipping: polygon_tx_receipts table missing.")

    # NOTE: tx_from is typically a relayer, not the trader.
    if "tx_from_address" in columns and "proxy_address" in columns:
        r = client.query(
            f"""
            SELECT
              count() AS trades_with_receipt,
              countIf(lower(tx_from_address) = lower(proxy_address)) AS from_matches_proxy
            FROM {trade_source}
            WHERE username = '{user}'
              {time_where}
              AND tx_from_address IS NOT NULL
            """
        ).result_rows[0]
        if int(r[0]) > 0:
            print("\nReceipt tx.from vs proxy (should usually be 0):")
            print(f"Trades w/receipt: {int(r[0]):,}")
        print(f"from==proxy:      {int(r[1]):,}")
    else:
        print("\nReceipt tx.from vs proxy (should usually be 0):")
        print("Skipping: tx_from_address or proxy_address not available in trade source.")

    # Bot order lifecycle (populates when strategy/executor are running)
    r = client.query(
        f"""
        SELECT
          count() AS gabagool_order_events,
          countIf(action = 'PLACE') AS places,
          countIf(action = 'CANCEL') AS cancels,
          countIf(action = 'STATUS') AS status_polls
        FROM polybot.strategy_gabagool_orders
        WHERE ts >= now() - INTERVAL {lookback} MINUTE
        """
    ).result_rows[0]
    print("\n=== Bot Order Lifecycle (lookback) ===")
    print(f"strategy_gabagool_orders: {int(r[0]):,} (place={int(r[1]):,} cancel={int(r[2]):,} status={int(r[3]):,})")

    r = client.query(
        f"""
        SELECT
          count() AS status_events,
          countIf(exchange_status ILIKE '%FILLED%') AS filled,
          countIf(exchange_status ILIKE '%CANCEL%') AS canceled
        FROM polybot.executor_order_status
        WHERE ts >= now() - INTERVAL {lookback} MINUTE
        """
    ).result_rows[0]
    print(f"executor_order_status:     {int(r[0]):,} (filled={int(r[1]):,} canceled={int(r[2]):,})")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
