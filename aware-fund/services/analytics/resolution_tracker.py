"""
AWARE Analytics - Resolution Tracker

Fetches resolved market data from Polymarket's Gamma API.
Enables P&L calculation by tracking which markets have settled.

Usage:
    tracker = ResolutionTracker(ch_client)
    resolved_count = tracker.run()
"""

import os
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class MarketResolution:
    """A resolved market from Gamma API"""
    condition_id: str
    market_slug: str
    title: str
    is_resolved: bool
    winning_outcome: str
    winning_outcome_index: int
    outcome_prices: list[float]
    outcomes: list[str]
    end_time: Optional[datetime]
    resolution_time: datetime


class ResolutionTracker:
    """
    Tracks market resolutions from Polymarket Gamma API.

    The Gamma API provides market metadata including resolution status.
    We query it for markets our traders have participated in, and store
    resolution data for P&L calculation.
    """

    GAMMA_API_BASE = "https://gamma-api.polymarket.com"

    def __init__(self, clickhouse_client, batch_size: int = 100):
        """
        Args:
            clickhouse_client: ClickHouse connection client
            batch_size: Number of markets to fetch per API call
        """
        self.ch = clickhouse_client
        self.batch_size = batch_size
        self.http_client = httpx.Client(timeout=30.0)

    def run(self) -> int:
        """
        Main entry point: fetch and store market resolutions.

        Returns:
            Number of resolved markets stored
        """
        logger.info("Starting resolution tracking...")

        # Step 1: Get unique condition_ids from our trades
        condition_ids = self._get_traded_condition_ids()
        logger.info(f"Found {len(condition_ids)} unique markets traded")

        if not condition_ids:
            return 0

        # Step 2: Get already-tracked resolutions (to avoid re-fetching)
        already_resolved = self._get_already_resolved_ids()
        pending_ids = set(cid for cid in condition_ids if cid not in already_resolved)
        logger.info(f"{len(already_resolved)} already tracked, {len(pending_ids)} to check")

        if not pending_ids:
            logger.info("No new condition IDs to check")
            return 0

        # Step 3: Fetch resolved markets from Gamma API
        resolutions = self._fetch_resolved_markets(pending_ids)

        # Step 4: Store resolutions
        if resolutions:
            stored = self._store_resolutions(resolutions)
            logger.info(f"Stored {stored} market resolutions")
            return stored

        return 0

    def _get_traded_condition_ids(self) -> list[str]:
        """Get unique condition IDs from our trades table"""
        query = """
        SELECT DISTINCT condition_id
        FROM polybot.aware_global_trades_dedup
        WHERE condition_id != ''
        """

        try:
            result = self.ch.query(query)
            return [row[0] for row in result.result_rows if row[0]]
        except Exception as e:
            logger.error(f"Failed to get condition IDs: {e}")
            return []

    def _get_already_resolved_ids(self) -> set[str]:
        """Get condition IDs we've already tracked as resolved"""
        query = """
        SELECT condition_id
        FROM polybot.aware_market_resolutions FINAL
        WHERE is_resolved = 1
        """

        try:
            result = self.ch.query(query)
            return {row[0] for row in result.result_rows if row[0]}
        except Exception as e:
            logger.warning(f"Failed to get resolved IDs (table may not exist): {e}")
            return set()

    def _fetch_resolved_markets(self, wanted_condition_ids: set[str]) -> list[MarketResolution]:
        """
        Fetch all resolved markets from Gamma API and match with our condition IDs.

        The Gamma API doesn't support efficient condition_id filtering,
        so we fetch resolved markets and match locally.
        """
        resolutions = []
        offset = 0
        limit = 100  # Max per request
        max_pages = 50  # Safety limit

        logger.info(f"Fetching resolved markets (looking for {len(wanted_condition_ids)} condition IDs)...")

        for page in range(max_pages):
            try:
                url = f"{self.GAMMA_API_BASE}/markets"
                params = {
                    "closed": "true",
                    "limit": limit,
                    "offset": offset,
                    "order": "closedTime",
                    "ascending": "false"
                }

                response = self.http_client.get(url, params=params)
                response.raise_for_status()

                markets = response.json()
                if not markets:
                    break

                # Parse and match
                for market in markets:
                    condition_id = market.get("conditionId", "")
                    if condition_id in wanted_condition_ids:
                        parsed = self._parse_market(market)
                        if parsed and parsed.is_resolved:
                            resolutions.append(parsed)
                            logger.debug(f"Found resolution: {condition_id[:20]}... -> {parsed.winning_outcome}")

                offset += limit
                time.sleep(0.2)  # Rate limiting

                # Early exit if we found all we need
                found_ids = {r.condition_id for r in resolutions}
                if len(found_ids) >= len(wanted_condition_ids):
                    break

            except Exception as e:
                logger.warning(f"Error fetching markets page {page}: {e}")
                break

        logger.info(f"Fetched {len(resolutions)} matching resolved markets")
        return resolutions

    def _fetch_single_market(self, condition_id: str) -> Optional[MarketResolution]:
        """Fetch a single market by condition ID (fallback method)"""
        try:
            # Try slug-based lookup if we have a mapping
            url = f"{self.GAMMA_API_BASE}/markets"
            params = {"limit": 100, "closed": "true"}

            response = self.http_client.get(url, params=params)
            response.raise_for_status()

            markets = response.json()

            # Find matching condition ID
            for market in markets:
                if market.get("conditionId") == condition_id:
                    return self._parse_market(market)

            return None

        except httpx.HTTPStatusError as e:
            logger.debug(f"HTTP error for {condition_id}: {e}")
        except Exception as e:
            logger.debug(f"Error fetching {condition_id}: {e}")

        return None

    def _parse_market(self, market: dict) -> Optional[MarketResolution]:
        """Parse Gamma API market response into MarketResolution"""
        import json as json_lib

        try:
            condition_id = market.get("conditionId") or market.get("condition_id", "")
            is_resolved = market.get("closed", False) or market.get("isResolved", False)

            # Parse outcome prices (may be JSON string or list)
            outcome_prices_raw = market.get("outcomePrices", [])
            if isinstance(outcome_prices_raw, str):
                try:
                    outcome_prices = json_lib.loads(outcome_prices_raw)
                except json_lib.JSONDecodeError:
                    outcome_prices = []
            else:
                outcome_prices = outcome_prices_raw or []

            # Convert to floats, handling empty strings
            outcome_prices = [float(p) if p else 0.0 for p in outcome_prices] if outcome_prices else []

            # Parse outcomes (may be JSON string or list)
            outcomes_raw = market.get("outcomes", [])
            if isinstance(outcomes_raw, str):
                try:
                    outcomes = json_lib.loads(outcomes_raw)
                except json_lib.JSONDecodeError:
                    outcomes = ["Yes", "No"]
            else:
                outcomes = outcomes_raw or ["Yes", "No"]

            # Determine winning outcome
            winning_outcome = ""
            winning_outcome_index = -1

            if is_resolved and outcome_prices:
                # Find the outcome with price >= 0.99 (winner)
                for i, price in enumerate(outcome_prices):
                    try:
                        if float(price) >= 0.99:  # Allow for floating point imprecision
                            winning_outcome_index = i
                            if i < len(outcomes):
                                winning_outcome = str(outcomes[i])
                            break
                    except (ValueError, TypeError):
                        continue

            # Parse end time
            end_time = None
            end_time_raw = market.get("endDate") or market.get("endTime")
            if end_time_raw:
                try:
                    if isinstance(end_time_raw, str):
                        end_time = datetime.fromisoformat(end_time_raw.replace("Z", "+00:00"))
                    elif isinstance(end_time_raw, (int, float)):
                        end_time = datetime.fromtimestamp(end_time_raw / 1000)
                except Exception:
                    pass

            return MarketResolution(
                condition_id=condition_id,
                market_slug=market.get("slug", ""),
                title=market.get("question", "") or market.get("title", ""),
                is_resolved=is_resolved,
                winning_outcome=winning_outcome,
                winning_outcome_index=winning_outcome_index,
                outcome_prices=outcome_prices,
                outcomes=outcomes,
                end_time=end_time,
                resolution_time=datetime.utcnow()
            )

        except Exception as e:
            logger.warning(f"Failed to parse market: {e}")
            return None

    def _store_resolutions(self, resolutions: list[MarketResolution]) -> int:
        """Store market resolutions in ClickHouse"""
        if not resolutions:
            return 0

        columns = [
            'condition_id', 'market_slug', 'title',
            'is_resolved', 'winning_outcome', 'winning_outcome_index',
            'outcome_prices', 'end_time', 'resolution_time', 'outcomes'
        ]

        data = []
        now = datetime.utcnow()

        for r in resolutions:
            data.append([
                r.condition_id,
                r.market_slug,
                r.title,
                1 if r.is_resolved else 0,
                r.winning_outcome,
                r.winning_outcome_index if r.winning_outcome_index >= 0 else 0,
                r.outcome_prices,
                r.end_time or now,
                r.resolution_time,
                r.outcomes
            ])

        try:
            self.ch.insert(
                'polybot.aware_market_resolutions',
                data,
                column_names=columns
            )
            return len(data)

        except Exception as e:
            logger.error(f"Failed to store resolutions: {e}")
            return 0

    def get_resolution_stats(self) -> dict:
        """Get statistics about tracked resolutions"""
        query = """
        SELECT
            count() AS total_markets,
            countIf(is_resolved = 1) AS resolved_markets,
            countIf(winning_outcome = 'Yes') AS yes_winners,
            countIf(winning_outcome = 'No') AS no_winners
        FROM polybot.aware_market_resolutions FINAL
        """

        try:
            result = self.ch.query(query)
            if result.result_rows:
                row = result.result_rows[0]
                return {
                    'total_markets': row[0],
                    'resolved_markets': row[1],
                    'yes_winners': row[2],
                    'no_winners': row[3]
                }
        except Exception as e:
            logger.error(f"Failed to get resolution stats: {e}")

        return {}

    def close(self):
        """Close HTTP client"""
        self.http_client.close()


def run_resolution_tracking(clickhouse_client) -> dict:
    """Convenience function to run resolution tracking"""
    tracker = ResolutionTracker(clickhouse_client)
    try:
        resolved_count = tracker.run()
        stats = tracker.get_resolution_stats()
        return {
            'status': 'success',
            'resolutions_stored': resolved_count,
            'stats': stats
        }
    finally:
        tracker.close()
