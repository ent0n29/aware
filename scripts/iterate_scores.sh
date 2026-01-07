#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

GAB_USERNAME="${GAB_USERNAME:-gabagool22}"
SIM_USERNAME="${SIM_USERNAME:-polybot-sim}"
SIM_SOURCE="${SIM_SOURCE:-executor}" # executor | user-trades

LOOKBACK_MINUTES="${LOOKBACK_MINUTES:-120}"
COVERAGE_HOURS="${COVERAGE_HOURS:-6}"
MATCH_HOURS="${MATCH_HOURS:-2}"

mkdir -p logs
ts="$(date -u +"%Y%m%dT%H%M%SZ")"
out="logs/iteration_${ts}.txt"

{
  echo "Iteration report: ${ts}"
  echo "gab=${GAB_USERNAME} sim=${SIM_USERNAME} sim_source=${SIM_SOURCE}"
  echo

  python3 research/data_quality_report.py --username "${GAB_USERNAME}" --lookback-minutes "${LOOKBACK_MINUTES}"
  echo

  python3 research/market_coverage_report.py --gab-username "${GAB_USERNAME}" --hours "${COVERAGE_HOURS}"
  echo

  python3 research/sim_trade_match_report.py --hours "${MATCH_HOURS}" --sim-username "${SIM_USERNAME}" --gab-username "${GAB_USERNAME}" --sim-source "${SIM_SOURCE}"
  echo

  python3 research/replication_score_orders.py --hours "${MATCH_HOURS}" --baseline-username "${GAB_USERNAME}"
  echo
} | tee "${out}"

echo "Wrote: ${out}"
