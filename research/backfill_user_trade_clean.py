#!/usr/bin/env python3
"""
Incrementally populate `polybot.user_trade_clean` without a ClickHouse MV.

Why this exists
---------------
The original implementation used a materialized view attached to `polybot.user_trades`
to compute a clean/validated trade table. In practice that was brittle: the ingest hot
path ended up doing heavy enrichment + ASOF joins and could OOM or stall Kafka consumers.

This script does the same work as a bounded batch INSERT, intended to run periodically
(e.g., every 1–5 minutes) for a *single* username.

Design goals
------------
- Keep ClickHouse ingest fast and stable.
- Only use decision-time WS TOB (no trade-triggered REST TOB fallback).
- Time-bound all work (last N hours or since last clean ts).
- Use only Python stdlib + ClickHouse HTTP.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SERIES_WHERE = (
    "(u.market_slug LIKE 'btc-updown-15m-%' OR u.market_slug LIKE 'eth-updown-15m-%' "
    " OR u.market_slug LIKE 'bitcoin-up-or-down-%' OR u.market_slug LIKE 'ethereum-up-or-down-%')"
)


def _parse_dt64(s: str) -> datetime:
    s = (s or "").strip()
    if not s:
        raise ValueError("empty timestamp")
    if "T" in s:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    if "." in s:
        base, frac = s.split(".", 1)
        dt = datetime.strptime(base, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        ms = int((frac + "000")[:3])
        return dt.replace(microsecond=ms * 1000)
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def _fmt_dt64(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{int(dt.microsecond/1000):03d}"


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

    def query_scalar(self, sql: str) -> str:
        text = self._post(sql.strip().rstrip(";") + "\nFORMAT TabSeparated")
        return (text.splitlines()[0].strip() if text.strip() else "")

    def exec(self, sql: str) -> None:
        self._post(sql.strip().rstrip(";") + "\n")


def _default_client() -> ClickHouseHttp:
    return ClickHouseHttp(
        url=(
            os.getenv("CLICKHOUSE_URL")
            or f"http://{os.getenv('CLICKHOUSE_HOST', '127.0.0.1')}:{os.getenv('CLICKHOUSE_PORT', '8123')}"
        ),
        database=os.getenv("CLICKHOUSE_DATABASE", "polybot"),
        user=os.getenv("CLICKHOUSE_USER", "default"),
        password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        timeout_seconds=int(os.getenv("CLICKHOUSE_TIMEOUT_SECONDS", "60")),
    )


def _resolve_window(
    ch: ClickHouseHttp,
    *,
    username: str,
    hours: int,
    overlap_seconds: int,
    start_ts: str | None,
    end_ts: str | None,
) -> tuple[str, str]:
    now = datetime.now(tz=timezone.utc)
    end = _parse_dt64(end_ts) if end_ts else now

    if start_ts:
        start = _parse_dt64(start_ts)
        return _fmt_dt64(start), _fmt_dt64(end)

    last_clean = ch.query_scalar(
        f"SELECT maxOrNull(ts) FROM polybot.user_trade_clean WHERE username = '{username}'"
    )
    if last_clean and last_clean != "\\N":
        start = _parse_dt64(last_clean) - timedelta(seconds=max(0, int(overlap_seconds)))
    else:
        start = end - timedelta(hours=max(1, int(hours)))

    return _fmt_dt64(start), _fmt_dt64(end)


def _build_insert_sql(
    *,
    username: str,
    start_ts: str,
    end_ts: str,
    max_tob_lag_ms: int,
) -> str:
    # Important: only use WS TOB (w/o clob_tob_by_trade fallback) to keep query light and
    # match our "decision-time state" requirements.
    # Also: constrain the WS TOB table to a small time window to avoid ASOF JOIN OOMs.
    return f"""
    INSERT INTO polybot.user_trade_clean (
      ts,
      username,
      market_slug,
      series,
      token_id,
      other_token_id,
      outcome,
      side,
      price,
      size,
      seconds_to_end,
      our_best_bid,
      our_best_bid_size,
      our_best_ask,
      our_best_ask_size,
      our_mid,
      our_tob_lag_ms,
      other_best_bid,
      other_best_bid_size,
      other_best_ask,
      other_best_ask_size,
      other_mid,
      other_tob_lag_ms,
      complete_set_edge,
      is_resolved,
      settle_price,
      realized_pnl,
      tob_source,
      event_key,
      ingested_at
    )
    WITH
      toDateTime64('2000-01-01 00:00:00', 3) AS min_valid_dt,
      parseDateTime64BestEffort('{start_ts}') AS start_dt,
      parseDateTime64BestEffort('{end_ts}') AS end_dt,
      trades_window AS (
        SELECT
          ts,
          username,
          market_slug,
          token_id,
          outcome,
          side,
          price,
          size,
          event_key
        FROM polybot.user_trades u
        WHERE u.username = '{username}'
          AND {SERIES_WHERE}
          AND u.ts >= start_dt
          AND u.ts <  end_dt
      ),
      gamma_latest AS (
        SELECT
          slug,
          argMax(end_date, captured_at) AS end_date,
          argMax(outcomes, captured_at) AS outcomes,
          argMax(outcome_prices, captured_at) AS outcome_prices,
          argMax(token_ids, captured_at) AS token_ids
        FROM polybot.gamma_markets
        WHERE slug IN (SELECT DISTINCT market_slug FROM trades_window)
        GROUP BY slug
      ),
      ws_window AS (
        SELECT
          ts,
          asset_id,
          best_bid_price,
          best_bid_size,
          best_ask_price,
          best_ask_size
        FROM polybot.market_ws_tob
        WHERE ts >= (start_dt - INTERVAL 2 HOUR)
          AND ts <  (end_dt + INTERVAL 1 HOUR)
      )
    SELECT
      u.ts AS ts,
      u.username AS username,
      u.market_slug AS market_slug,
      multiIf(
        u.market_slug LIKE 'btc-updown-15m-%', 'btc-15m',
        u.market_slug LIKE 'eth-updown-15m-%', 'eth-15m',
        u.market_slug LIKE 'bitcoin-up-or-down-%', 'btc-1h',
        u.market_slug LIKE 'ethereum-up-or-down-%', 'eth-1h',
        'other'
      ) AS series,
      u.token_id AS token_id,
      if(u.outcome = 'Up', g.token_ids[2], g.token_ids[1]) AS other_token_id,
      u.outcome AS outcome,
      u.side AS side,
      u.price AS price,
      u.size AS size,

      -- seconds_to_end (Gamma end_date, with 15m slug fallback)
      if(
         coalesce(
           if(g.end_date < min_valid_dt, CAST(NULL, 'Nullable(DateTime64(3))'), toNullable(g.end_date)),
           if(
             (position(toString(u.market_slug), 'updown-15m-') > 0)
               AND (toUInt32OrZero(splitByChar('-', toString(u.market_slug))[-1]) > 0),
             toDateTime64(toUInt32OrZero(splitByChar('-', toString(u.market_slug))[-1]) + 900, 3),
             CAST(NULL, 'Nullable(DateTime64(3))')
           )
         ) IS NULL,
         CAST(NULL, 'Nullable(Int64)'),
         dateDiff(
           'second',
           u.ts,
           coalesce(
             if(g.end_date < min_valid_dt, CAST(NULL, 'Nullable(DateTime64(3))'), toNullable(g.end_date)),
             if(
               (position(toString(u.market_slug), 'updown-15m-') > 0)
                 AND (toUInt32OrZero(splitByChar('-', toString(u.market_slug))[-1]) > 0),
               toDateTime64(toUInt32OrZero(splitByChar('-', toString(u.market_slug))[-1]) + 900, 3),
               CAST(NULL, 'Nullable(DateTime64(3))')
             )
           )
         )
      ) AS seconds_to_end,

      -- WS TOB at decision time (our token)
      w.best_bid_price AS our_best_bid,
      w.best_bid_size AS our_best_bid_size,
      w.best_ask_price AS our_best_ask,
      w.best_ask_size AS our_best_ask_size,
      (w.best_bid_price + w.best_ask_price) / 2 AS our_mid,
      toInt64(dateDiff('millisecond', w.ts, u.ts)) AS our_tob_lag_ms,

      -- WS TOB at decision time (other token)
      o.best_bid_price AS other_best_bid,
      o.best_bid_size AS other_best_bid_size,
      o.best_ask_price AS other_best_ask,
      o.best_ask_size AS other_best_ask_size,
      (o.best_bid_price + o.best_ask_price) / 2 AS other_mid,
      toInt64(dateDiff('millisecond', o.ts, u.ts)) AS other_tob_lag_ms,

      -- Complete-set edge (bid/bid)
      if(u.outcome = 'Up',
         1.0 - w.best_bid_price - o.best_bid_price,
         1.0 - o.best_bid_price - w.best_bid_price
      ) AS complete_set_edge,

      -- Resolution (Gamma)
      ((arrayMax(g.outcome_prices) >= 0.999) AND (arrayMin(g.outcome_prices) <= 0.001)) AS is_resolved,
      if(
        is_resolved
          AND (indexOf(g.outcomes, toString(u.outcome)) > 0),
        arrayElement(g.outcome_prices, indexOf(g.outcomes, toString(u.outcome))),
        CAST(NULL, 'Nullable(Float64)')
      ) AS settle_price,
      if(is_resolved AND (settle_price IS NOT NULL),
         u.size * if(u.side = 'SELL', u.price - settle_price, settle_price - u.price),
         CAST(NULL, 'Nullable(Float64)')
      ) AS realized_pnl,

      'WS' AS tob_source,
      u.event_key AS event_key,
      now64(3) AS ingested_at

    FROM trades_window u
    LEFT JOIN gamma_latest g ON g.slug = u.market_slug
    ASOF LEFT JOIN ws_window w
      ON (w.asset_id = u.token_id) AND (u.ts >= w.ts)
    ASOF LEFT JOIN ws_window o
      ON (o.asset_id = if(u.outcome = 'Up', g.token_ids[2], g.token_ids[1])) AND (u.ts >= o.ts)

    WHERE series != 'other'
      AND seconds_to_end IS NOT NULL
      AND seconds_to_end >= 0
      AND length(g.token_ids) = 2
      AND our_best_bid > 0 AND our_best_ask > 0
      AND other_best_bid > 0 AND other_best_ask > 0
      AND abs(our_tob_lag_ms) < {int(max_tob_lag_ms)}
      AND abs(other_tob_lag_ms) < {int(max_tob_lag_ms)}
    """


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", default=os.getenv("POLYMARKET_TARGET_USER", "gabagool22"))
    ap.add_argument("--hours", type=int, default=6, help="Backfill window when no prior clean data exists.")
    ap.add_argument("--overlap-seconds", type=int, default=120, help="Reprocess overlap to catch late WS snapshots.")
    ap.add_argument("--start-ts", default=None, help="Override start (UTC). Example: 2026-01-04 18:00:00.000")
    ap.add_argument("--end-ts", default=None, help="Override end (UTC). Example: 2026-01-04 19:00:00.000")
    ap.add_argument("--max-tob-lag-ms", type=int, default=5000)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    username = args.username.strip()
    if not username:
        raise SystemExit("username is required")

    ch = _default_client()
    start_ts, end_ts = _resolve_window(
        ch,
        username=username,
        hours=args.hours,
        overlap_seconds=args.overlap_seconds,
        start_ts=args.start_ts,
        end_ts=args.end_ts,
    )
    sql = _build_insert_sql(
        username=username,
        start_ts=start_ts,
        end_ts=end_ts,
        max_tob_lag_ms=args.max_tob_lag_ms,
    )

    print(f"Backfill user_trade_clean for username={username}")
    print(f"Window: {start_ts} → {end_ts}")
    if args.dry_run:
        print(sql.strip())
        return 0

    ch.exec(sql)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
