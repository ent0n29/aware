"""
AWARE Analytics - Price Service

Fetches current market prices for position valuation.
Uses multiple sources with fallback:
1. ClickHouse TOB data (real-time websocket data)
2. Polymarket CLOB API (fallback)

Includes caching to reduce API calls and database load.
"""

import os
import time
import logging
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
import requests

import clickhouse_connect

logger = logging.getLogger(__name__)

# Cache TTL in seconds
CACHE_TTL_SECONDS = 30

# Polymarket CLOB API
CLOB_API_BASE = "https://clob.polymarket.com"


@dataclass
class MarketPrice:
    """Market price data for a token."""
    token_id: str
    market_slug: str
    best_bid: Decimal
    best_ask: Decimal
    mid_price: Decimal
    last_trade_price: Decimal
    timestamp: datetime
    source: str  # 'tob' or 'clob_api'


class PriceCache:
    """Simple in-memory cache for prices."""

    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS):
        self._cache: Dict[str, tuple[MarketPrice, float]] = {}
        self._ttl = ttl_seconds

    def get(self, token_id: str) -> Optional[MarketPrice]:
        """Get cached price if not expired."""
        if token_id in self._cache:
            price, cached_at = self._cache[token_id]
            if time.time() - cached_at < self._ttl:
                return price
            del self._cache[token_id]
        return None

    def set(self, token_id: str, price: MarketPrice):
        """Cache a price."""
        self._cache[token_id] = (price, time.time())

    def get_many(self, token_ids: List[str]) -> Dict[str, MarketPrice]:
        """Get multiple prices from cache."""
        result = {}
        for tid in token_ids:
            if price := self.get(tid):
                result[tid] = price
        return result

    def clear(self):
        """Clear all cached prices."""
        self._cache.clear()


class PriceService:
    """
    Service for fetching current market prices.

    Uses ClickHouse TOB data as primary source, falls back to CLOB API.
    Includes caching to reduce load.
    """

    def __init__(
        self,
        clickhouse_client=None,
        cache_ttl_seconds: int = CACHE_TTL_SECONDS,
        tob_staleness_seconds: int = 300  # Consider TOB stale after 5 minutes
    ):
        self.client = clickhouse_client or self._get_default_client()
        self.cache = PriceCache(cache_ttl_seconds)
        self.tob_staleness_seconds = tob_staleness_seconds

    def _get_default_client(self):
        """Create default ClickHouse client."""
        return clickhouse_connect.get_client(
            host=os.getenv('CLICKHOUSE_HOST', 'localhost'),
            port=int(os.getenv('CLICKHOUSE_PORT', '8123')),
            database=os.getenv('CLICKHOUSE_DATABASE', 'polybot')
        )

    def get_price(self, token_id: str) -> Optional[MarketPrice]:
        """
        Get current price for a single token.

        Returns cached value if available, otherwise fetches fresh.
        """
        # Check cache first
        if cached := self.cache.get(token_id):
            return cached

        # Try TOB data
        price = self._fetch_from_tob(token_id)
        if price and self._is_price_fresh(price):
            self.cache.set(token_id, price)
            return price

        # Fallback to CLOB API
        price = self._fetch_from_clob_api(token_id)
        if price:
            self.cache.set(token_id, price)
            return price

        return None

    def get_prices(self, token_ids: List[str]) -> Dict[str, MarketPrice]:
        """
        Get prices for multiple tokens efficiently.

        Uses batch queries where possible.
        """
        if not token_ids:
            return {}

        # Check cache
        result = self.cache.get_many(token_ids)
        missing = [tid for tid in token_ids if tid not in result]

        if not missing:
            return result

        # Batch fetch from TOB
        tob_prices = self._fetch_batch_from_tob(missing)
        for tid, price in tob_prices.items():
            if self._is_price_fresh(price):
                result[tid] = price
                self.cache.set(tid, price)

        # Fallback for any still missing (stale TOB or not in TOB)
        still_missing = [tid for tid in missing if tid not in result]
        for tid in still_missing[:10]:  # Limit API calls
            price = self._fetch_from_clob_api(tid)
            if price:
                result[tid] = price
                self.cache.set(tid, price)

        return result

    def _fetch_from_tob(self, token_id: str) -> Optional[MarketPrice]:
        """Fetch price from ClickHouse TOB table."""
        try:
            query = """
                SELECT
                    asset_id,
                    best_bid_price,
                    best_ask_price,
                    last_trade_price,
                    tob_ts
                FROM polybot.market_ws_tob_latest
                WHERE asset_id = %(token_id)s
            """
            result = self.client.query(query, parameters={'token_id': token_id})

            if result.result_rows:
                row = result.result_rows[0]
                bid = Decimal(str(row[1] or 0))
                ask = Decimal(str(row[2] or 0))
                last = Decimal(str(row[3] or 0))
                mid = (bid + ask) / 2 if bid and ask else last

                return MarketPrice(
                    token_id=token_id,
                    market_slug='',  # Not available in TOB
                    best_bid=bid,
                    best_ask=ask,
                    mid_price=mid,
                    last_trade_price=last,
                    timestamp=row[4],
                    source='tob'
                )
        except Exception as e:
            logger.debug(f"TOB fetch failed for {token_id}: {e}")

        return None

    def _fetch_batch_from_tob(self, token_ids: List[str]) -> Dict[str, MarketPrice]:
        """Batch fetch prices from TOB."""
        if not token_ids:
            return {}

        try:
            query = """
                SELECT
                    asset_id,
                    best_bid_price,
                    best_ask_price,
                    last_trade_price,
                    tob_ts
                FROM polybot.market_ws_tob_latest
                WHERE asset_id IN %(token_ids)s
            """
            result = self.client.query(query, parameters={'token_ids': token_ids})

            prices = {}
            for row in result.result_rows:
                token_id = row[0]
                bid = Decimal(str(row[1] or 0))
                ask = Decimal(str(row[2] or 0))
                last = Decimal(str(row[3] or 0))
                mid = (bid + ask) / 2 if bid and ask else last

                prices[token_id] = MarketPrice(
                    token_id=token_id,
                    market_slug='',
                    best_bid=bid,
                    best_ask=ask,
                    mid_price=mid,
                    last_trade_price=last,
                    timestamp=row[4],
                    source='tob'
                )

            return prices

        except Exception as e:
            logger.warning(f"Batch TOB fetch failed: {e}")
            return {}

    def _fetch_from_clob_api(self, token_id: str) -> Optional[MarketPrice]:
        """Fetch price from Polymarket CLOB API."""
        try:
            response = requests.get(
                f"{CLOB_API_BASE}/book",
                params={'token_id': token_id},
                timeout=5
            )

            if not response.ok:
                return None

            data = response.json()

            # Parse orderbook to get best bid/ask
            bids = data.get('bids', [])
            asks = data.get('asks', [])

            best_bid = Decimal(bids[0]['price']) if bids else Decimal('0')
            best_ask = Decimal(asks[0]['price']) if asks else Decimal('0')
            mid = (best_bid + best_ask) / 2 if best_bid and best_ask else Decimal('0')

            return MarketPrice(
                token_id=token_id,
                market_slug=data.get('market', ''),
                best_bid=best_bid,
                best_ask=best_ask,
                mid_price=mid,
                last_trade_price=mid,  # CLOB API doesn't return last trade
                timestamp=datetime.utcnow(),
                source='clob_api'
            )

        except Exception as e:
            logger.debug(f"CLOB API fetch failed for {token_id}: {e}")
            return None

    def _is_price_fresh(self, price: MarketPrice) -> bool:
        """Check if a price is fresh enough to use."""
        age = datetime.utcnow() - price.timestamp
        return age.total_seconds() < self.tob_staleness_seconds


# Singleton instance for easy import
_price_service: Optional[PriceService] = None


def get_price_service() -> PriceService:
    """Get or create singleton price service."""
    global _price_service
    if _price_service is None:
        _price_service = PriceService()
    return _price_service


def get_prices(token_ids: List[str]) -> Dict[str, MarketPrice]:
    """Convenience function to get prices."""
    return get_price_service().get_prices(token_ids)


def get_price(token_id: str) -> Optional[MarketPrice]:
    """Convenience function to get a single price."""
    return get_price_service().get_price(token_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test the price service
    service = PriceService()

    # Get sample token IDs from positions
    print("Testing price service...")

    # Try to get a price (will use TOB or API)
    test_token = "0x123"  # Replace with actual token ID
    price = service.get_price(test_token)

    if price:
        print(f"Token: {price.token_id}")
        print(f"Mid price: {price.mid_price}")
        print(f"Source: {price.source}")
        print(f"Timestamp: {price.timestamp}")
    else:
        print("No price available for test token")
