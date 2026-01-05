#!/usr/bin/env python3
"""
Match gabagool22 trade prints to *our strategy decision stream* (PLACE events).

This answers: "are we placing the same orders (market/outcome/price) around the same time?"
It is intentionally separate from sim_trade_match_report.py, which matches fills reconstructed
from executor_order_status.

Matching rule (strict by default)
---------------------------------
A gabagool trade is considered matched if we have an unused strategy PLACE with:
  - same market_slug
  - same outcome (Up/Down)
  - same side (BUY)
  - price within --price-eps
  - timestamp within --max-delta-ms

Note: gabagool maker fills can occur after placement, so for maker-heavy windows you may want a
larger --max-delta-ms to treat this as an approximate "did we decide similarly?" metric.

Requires ClickHouse (HTTP). Uses only Python stdlib.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SERIES_WHERE = (
    "(market_slug LIKE 'btc-updown-15m-%' OR market_slug LIKE 'eth-updown-15m-%' "
    " OR market_slug LIKE 'bitcoin-up-or-down-%' OR market_slug LIKE 'ethereum-up-or-down-%')"
)


def _parse_dt64(s: str) -> datetime:
    s = s.strip()
    if not s:
        raise ValueError("empty timestamp")
    if "T" in s:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc)
    if "." in s:
        base, frac = s.split(".", 1)
        dt = datetime.strptime(base, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        ms = int((frac + "000")[:3])
        return dt.replace(microsecond=ms * 1000)
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


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

    def query_rows(self, sql: str) -> List[Dict[str, str]]:
        sql = sql.strip().rstrip(";") + "\nFORMAT CSVWithNames"
        text = self._post(sql)
        if not text.strip():
            return []
        reader = csv.DictReader(StringIO(text))
        return [dict(r) for r in reader]

    def show_tables(self) -> set[str]:
        text = self._post(
            "SELECT name FROM system.tables WHERE database = currentDatabase() FORMAT TabSeparated"
        )
        out: set[str] = set()
        for line in text.splitlines():
            name = line.strip()
            if name:
                out.add(name)
        return out


def _pick_trade_source(ch: ClickHouseHttp) -> str:
    tables = ch.show_tables()
    for t in ("user_trades", "user_trades_dedup", "user_trade_enriched_v4", "user_trade_enriched_v3", "user_trade_enriched_v2"):
        if t in tables:
            return t
    raise RuntimeError("No trade source found (expected user_trades/user_trades_dedup or user_trade_enriched_v2/v3/v4)")


def _time_where(col: str, start_ts: Optional[str], end_ts: Optional[str], hours: int) -> str:
    if start_ts or end_ts:
        parts = []
        if start_ts:
            parts.append(f"{col} >= parseDateTime64BestEffort('{start_ts}')")
        if end_ts:
            parts.append(f"{col} < parseDateTime64BestEffort('{end_ts}')")
        return " AND " + " AND ".join(parts) if parts else ""
    return f" AND {col} >= now() - INTERVAL {int(hours)} HOUR"


def _fetch_user_trades(
    ch: ClickHouseHttp,
    *,
    trade_source: str,
    username: str,
    where_time: str,
) -> List[Dict[str, str]]:
    sql = f"""
    SELECT
      ts,
      username,
      market_slug,
      outcome,
      side,
      price,
      size
    FROM polybot.{trade_source}
    WHERE username = '{username}'
      AND {SERIES_WHERE}
      {where_time}
    ORDER BY ts
    """
    return ch.query_rows(sql)


def _fetch_strategy_places(
    ch: ClickHouseHttp,
    *,
    where_time: str,
    run_id: Optional[str],
) -> List[Dict[str, str]]:
    run_where = f" AND run_id = '{run_id}'" if run_id else ""
    sql = f"""
    SELECT
      ts,
      'polybot-place' AS username,
      market_slug,
      if(direction = 'UP', 'Up', 'Down') AS outcome,
      'BUY' AS side,
      price,
      size
    FROM polybot.strategy_gabagool_orders
    WHERE action = 'PLACE'
      AND success = 1
      AND market_slug != ''
      AND price IS NOT NULL
      AND ({SERIES_WHERE})
      {run_where}
      {where_time}
    ORDER BY ts
    """
    return ch.query_rows(sql)


def _median(values: List[float]) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return float(s[mid])
    return float((s[mid - 1] + s[mid]) / 2.0)


def _quantile(values: List[float], q: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    idx = int(round((len(s) - 1) * q))
    idx = max(0, min(len(s) - 1, idx))
    return float(s[idx])


def _match_one_bucket(
    gab: List[Dict[str, str]],
    sim: List[Dict[str, str]],
    *,
    max_delta_ms: int,
    price_eps: float,
    require_place_before: bool,
    require_place_after: bool,
) -> Tuple[int, int, List[float], List[float], Dict[str, int]]:
    gab_sorted = sorted(gab, key=lambda r: r["ts"])
    sim_sorted = sorted(sim, key=lambda r: r["ts"])

    matched_sim = [False] * len(sim_sorted)
    abs_deltas: List[float] = []
    signed_deltas: List[float] = []
    reasons: Dict[str, int] = {"NO_SIM": 0, "NO_PRICE_MATCH": 0, "NO_TIME_MATCH": 0}

    j = 0
    matched_g = 0
    matched_s = 0

    for g in gab_sorted:
        g_ts = _parse_dt64(g["ts"])
        g_ms = int(g_ts.timestamp() * 1000)
        g_price = float(g["price"])

        while j < len(sim_sorted):
            s_ts = _parse_dt64(sim_sorted[j]["ts"])
            s_ms = int(s_ts.timestamp() * 1000)
            if s_ms < g_ms - max_delta_ms:
                j += 1
                continue
            break

        best_idx = None
        best_delta = None
        best_price_diff = None
        scanned_any = False
        saw_time_ok_dir = False

        k = j
        while k < len(sim_sorted):
            if matched_sim[k]:
                k += 1
                continue
            s_ts = _parse_dt64(sim_sorted[k]["ts"])
            s_ms = int(s_ts.timestamp() * 1000)
            delta = s_ms - g_ms
            if delta > max_delta_ms:
                break
            scanned_any = True

            if require_place_before and delta > 0:
                k += 1
                continue
            if require_place_after and delta < 0:
                k += 1
                continue
            saw_time_ok_dir = True

            s_price = float(sim_sorted[k]["price"])
            price_diff = abs(s_price - g_price)
            if price_diff <= price_eps:
                abs_delta = abs(delta)
                if best_delta is None or abs_delta < best_delta or (
                    abs_delta == best_delta and price_diff < (best_price_diff or 1e9)
                ):
                    best_idx = k
                    best_delta = abs_delta
                    best_price_diff = price_diff
            k += 1

        if best_idx is not None:
            matched_sim[best_idx] = True
            matched_g += 1
            matched_s += 1
            abs_deltas.append(float(best_delta or 0))
            # Recompute signed delta for the chosen match.
            s_ts = _parse_dt64(sim_sorted[best_idx]["ts"])
            s_ms = int(s_ts.timestamp() * 1000)
            signed_deltas.append(float(s_ms - g_ms))
        else:
            if not scanned_any:
                reasons["NO_SIM"] += 1
            elif not saw_time_ok_dir:
                reasons["NO_TIME_MATCH"] += 1
            else:
                reasons["NO_PRICE_MATCH"] += 1

    return matched_g, matched_s, abs_deltas, signed_deltas, reasons


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gab-username", default=os.getenv("POLYMARKET_TARGET_USER", "TARGET_USER"))
    ap.add_argument("--run-id", default=None, help="Optional run_id filter for strategy events")
    ap.add_argument("--hours", type=int, default=6)
    ap.add_argument("--start-ts", default=None)
    ap.add_argument("--end-ts", default=None)
    ap.add_argument("--max-delta-ms", type=int, default=1500)
    ap.add_argument("--price-eps", type=float, default=0.0005)
    ap.add_argument(
        "--require-place-before",
        action="store_true",
        help="Only count matches where our PLACE timestamp is <= gab trade timestamp (maker-like).",
    )
    ap.add_argument(
        "--require-place-after",
        action="store_true",
        help="Only count matches where our PLACE timestamp is >= gab trade timestamp (taker-like).",
    )
    args = ap.parse_args()
    if args.require_place_before and args.require_place_after:
        print("Error: --require-place-before and --require-place-after are mutually exclusive.", file=sys.stderr)
        return 2

    ch = ClickHouseHttp(
        url=(
            os.getenv("CLICKHOUSE_URL")
            or f"http://{os.getenv('CLICKHOUSE_HOST', '127.0.0.1')}:{os.getenv('CLICKHOUSE_PORT', '8123')}"
        ),
        database=os.getenv("CLICKHOUSE_DATABASE", "polybot"),
        user=os.getenv("CLICKHOUSE_USER", "intellij"),
        password=os.getenv("CLICKHOUSE_PASSWORD", ""),
        timeout_seconds=int(os.getenv("CLICKHOUSE_TIMEOUT_SECONDS", "30")),
    )

    where = _time_where("ts", args.start_ts, args.end_ts, args.hours)
    trade_source = _pick_trade_source(ch)
    try:
        gab_rows = _fetch_user_trades(ch, trade_source=trade_source, username=args.gab_username, where_time=where)
        place_rows = _fetch_strategy_places(ch, where_time=where, run_id=args.run_id)
    except Exception as e:
        print(f"ClickHouse query failed: {e}", file=sys.stderr)
        return 2

    print(f"Window: hours={args.hours} start={args.start_ts or '(auto)'} end={args.end_ts or '(auto)'}")
    print(f"Source: gab=polybot.{trade_source} places=polybot.strategy_gabagool_orders{' run_id=' + args.run_id if args.run_id else ''}")
    print(f"Trades: gab={len(gab_rows):,} places={len(place_rows):,}")
    if not gab_rows or not place_rows:
        print("Not enough data to match.")
        return 2

    gab_by: Dict[Tuple[str, str, str], List[Dict[str, str]]] = {}
    place_by: Dict[Tuple[str, str, str], List[Dict[str, str]]] = {}

    def key(r: Dict[str, str]) -> Tuple[str, str, str]:
        return (str(r.get("market_slug") or ""), str(r.get("outcome") or ""), str(r.get("side") or ""))

    for r in gab_rows:
        gab_by.setdefault(key(r), []).append(r)
    for r in place_rows:
        place_by.setdefault(key(r), []).append(r)

    matched_g_total = 0
    matched_p_total = 0
    abs_deltas: List[float] = []
    signed_deltas: List[float] = []
    reasons_total: Dict[str, int] = {"NO_SIM": 0, "NO_PRICE_MATCH": 0, "NO_TIME_MATCH": 0}

    keys = set(gab_by) | set(place_by)
    for k in keys:
        g = gab_by.get(k, [])
        s = place_by.get(k, [])
        if not g:
            continue
        if not s:
            reasons_total["NO_SIM"] += len(g)
            continue
        mg, mp, deltas, s_deltas, reasons = _match_one_bucket(
            g,
            s,
            max_delta_ms=args.max_delta_ms,
            price_eps=args.price_eps,
            require_place_before=args.require_place_before,
            require_place_after=args.require_place_after,
        )
        matched_g_total += mg
        matched_p_total += mp
        abs_deltas.extend(deltas)
        signed_deltas.extend(s_deltas)
        for rk, rv in reasons.items():
            reasons_total[rk] = reasons_total.get(rk, 0) + rv

    recall = matched_g_total / len(gab_rows) if gab_rows else 0.0
    precision = matched_p_total / len(place_rows) if place_rows else 0.0

    print("\n**Strict Match (gab trade ↔ place)**")
    print(f"- recall (gab matched): {matched_g_total:,}/{len(gab_rows):,} = {recall*100:.2f}%")
    print(f"- precision (places matched): {matched_p_total:,}/{len(place_rows):,} = {precision*100:.2f}%")
    print(f"- abs time delta ms: median={_median(abs_deltas):.1f} p90={_quantile(abs_deltas, 0.9):.1f} n={len(abs_deltas):,}")
    if signed_deltas:
        before = sum(1 for d in signed_deltas if d <= 0)
        after = len(signed_deltas) - before
        print(
            f"- signed delta ms (place - trade): median={_median(signed_deltas):.1f} "
            f"p10={_quantile(signed_deltas, 0.1):.1f} p90={_quantile(signed_deltas, 0.9):.1f} "
            f"before={before} after={after}"
        )
    print(f"- mismatch reasons: {reasons_total}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
