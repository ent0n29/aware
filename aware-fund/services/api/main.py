#!/usr/bin/env python3
"""
AWARE API - Public REST API Service

Provides endpoints for:
- Leaderboard & Trader Profiles
- PSI Indices (PSI-10, PSI-25, PSI-CRYPTO, PSI-POLITICS)
- Hidden Alpha Discovery
- Strategy DNA / Fingerprinting
- Consensus Signal Detection
- Edge Decay Monitoring

Usage:
    python main.py

Environment Variables:
    CLICKHOUSE_HOST - ClickHouse host (default: localhost)
    CLICKHOUSE_PORT - ClickHouse port (default: 8123)
    CLICKHOUSE_DATABASE - Database name (default: polybot)
    API_HOST - API host (default: 0.0.0.0)
    API_PORT - API port (default: 8000)
    LOG_LEVEL - Logging level (default: INFO)
"""

import os
import sys
import logging
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

import clickhouse_connect

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Authentication
from auth import verify_api_key, optional_api_key, is_auth_enabled

# Investment module (Custodial MVP)
from investments import router as invest_router, funds_router

# Add analytics to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'analytics'))

# Configure logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('aware-api')

# Initialize Rate Limiter
# Default: 100 requests per minute per IP
# Override with RATE_LIMIT env var (e.g., "200/minute")
limiter = Limiter(key_func=get_remote_address)

# Initialize FastAPI
app = FastAPI(
    title="AWARE FUND API",
    description="The Smart Money Index for Prediction Markets",
    version="1.0.0"
)

# Attach rate limiter to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware
# Note: In production, replace "*" with specific allowed origins
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:3002",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if os.getenv('ENV', 'development') == 'production' else ["*"],
    allow_credentials=False,  # Don't allow credentials with wildcard origins
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

# Register investment routers
app.include_router(invest_router)
app.include_router(funds_router)


# ============================================================================
# MODELS
# ============================================================================

class LeaderboardEntry(BaseModel):
    rank: int
    username: str
    pseudonym: Optional[str]
    proxy_address: str
    smart_money_score: float
    tier: str
    total_pnl: float
    total_volume: float
    win_rate: float
    sharpe_ratio: float
    strategy_type: str
    strategy_confidence: float
    rank_change: int
    total_trades: int = 0
    model_version: Optional[str] = None
    tier_confidence: Optional[float] = None


class TraderProfile(BaseModel):
    username: str
    pseudonym: Optional[str]
    proxy_address: str
    # Scores
    smart_money_score: int
    tier: str
    profitability_score: float
    risk_adjusted_score: float
    consistency_score: float
    track_record_score: float
    # Strategy
    strategy_type: str
    strategy_confidence: float
    complete_set_ratio: float
    direction_bias: float
    # Performance
    total_pnl: float
    total_volume: float
    # Activity
    total_trades: int
    unique_markets: int
    days_active: int
    first_trade_at: Optional[datetime]
    last_trade_at: Optional[datetime]


class IndexComposition(BaseModel):
    rank: int
    username: str
    proxy_address: str
    smart_money_score: int
    weight: float
    total_pnl: float


class PSIIndex(BaseModel):
    name: str
    description: str
    trader_count: int
    total_weight: float
    composition: list[IndexComposition]
    calculated_at: datetime


class HealthResponse(BaseModel):
    status: str
    database: str
    trade_count: int
    trader_count: int
    last_score_update: Optional[datetime]


class StatsResponse(BaseModel):
    total_trades: int
    total_traders: int
    total_volume_usd: float
    trades_24h: int
    traders_24h: int


class MonitoringResponse(BaseModel):
    """Comprehensive monitoring status"""
    ingestion_status: str  # healthy, degraded, unhealthy
    trades_last_hour: int
    trades_last_24h: int
    traders_last_24h: int
    latest_trade_at: Optional[datetime]
    ingestion_lag_seconds: int
    markets_active: int
    avg_trades_per_hour: float
    issues: list[str]
    # Pipeline
    total_trades: int
    total_traders: int
    traders_scored: int
    traders_with_pnl: int
    traders_with_sharpe: int
    resolutions_tracked: int
    last_scoring_at: Optional[datetime]


class DailyStats(BaseModel):
    date: str
    trades: int
    traders: int
    markets: int
    volume_usd: float


class DataFreshness(BaseModel):
    """Data freshness indicators for UI display"""
    status: str  # fresh, stale, outdated
    status_emoji: str  # 🟢, 🟡, 🔴
    latest_trade_at: Optional[datetime]
    latest_trade_age_seconds: int
    latest_trade_age_human: str  # "2 minutes ago"
    last_scoring_at: Optional[datetime]
    last_scoring_age_human: str
    last_pnl_at: Optional[datetime]
    last_pnl_age_human: str
    data_coverage_days: int
    recommendation: str  # For users: "Data is current" or "Scores may be outdated"


# ============================================================================
# DATABASE
# ============================================================================

def get_clickhouse_client():
    """Get ClickHouse client"""
    return clickhouse_connect.get_client(
        host=os.getenv('CLICKHOUSE_HOST', 'localhost'),
        port=int(os.getenv('CLICKHOUSE_PORT', '8123')),
        database=os.getenv('CLICKHOUSE_DATABASE', 'polybot')
    )


# ============================================================================
# HELPERS
# ============================================================================

def _human_readable_age(seconds: int) -> str:
    """Convert seconds to human readable string like '2 minutes ago'"""
    if seconds < 60:
        return f"{seconds} seconds ago"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    else:
        days = seconds // 86400
        return f"{days} day{'s' if days > 1 else ''} ago"


def _get_freshness_status(lag_seconds: int) -> tuple[str, str]:
    """
    Get freshness status and emoji based on lag.

    Returns (status, emoji) tuple.
    """
    if lag_seconds < 300:  # < 5 minutes
        return 'fresh', '🟢'
    elif lag_seconds < 1800:  # < 30 minutes
        return 'stale', '🟡'
    else:
        return 'outdated', '🔴'


def _sanitize_identifier(value: str, max_length: int = 100) -> str:
    """
    Sanitize a string identifier for safe SQL usage.

    - Escapes single quotes
    - Limits length
    - Removes dangerous characters
    """
    if not value:
        return ''
    # Remove null bytes and control characters
    sanitized = ''.join(c for c in value if c.isprintable() and c not in '\x00\n\r')
    # Escape single quotes for SQL
    sanitized = sanitized.replace("'", "''")
    # Limit length
    return sanitized[:max_length]


def _validate_wallet_address(address: str) -> bool:
    """Validate Ethereum-style wallet address format."""
    import re
    return bool(re.match(r'^0x[a-fA-F0-9]{40}$', address))


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    try:
        client = get_clickhouse_client()

        # Get counts
        trade_count = client.query(
            "SELECT count() FROM aware_global_trades_dedup"
        ).result_rows[0][0]

        trader_count = client.query(
            "SELECT count() FROM aware_smart_money_scores FINAL"
        ).result_rows[0][0]

        # Get last update
        result = client.query(
            "SELECT max(calculated_at) FROM aware_smart_money_scores"
        )
        last_update = result.result_rows[0][0] if result.result_rows else None

        return HealthResponse(
            status="healthy",
            database="connected",
            trade_count=trade_count,
            trader_count=trader_count,
            last_score_update=last_update
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            database=str(e),
            trade_count=0,
            trader_count=0,
            last_score_update=None
        )


@app.get("/api/freshness", response_model=DataFreshness)
async def get_data_freshness():
    """
    Get data freshness indicators for UI display.

    Returns human-readable timestamps and status indicators
    to help users understand how current the data is.
    """
    try:
        client = get_clickhouse_client()
        from datetime import timezone

        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

        # Get latest trade timestamp
        result = client.query("SELECT max(ts) FROM aware_global_trades_dedup")
        latest_trade = result.result_rows[0][0] if result.result_rows else None

        trade_lag_seconds = 0
        if latest_trade:
            trade_lag_seconds = int((now_utc - latest_trade).total_seconds())

        # Get last scoring timestamp
        result = client.query("SELECT max(calculated_at) FROM aware_smart_money_scores")
        last_scoring = result.result_rows[0][0] if result.result_rows else None

        scoring_lag_seconds = 0
        if last_scoring:
            scoring_lag_seconds = int((now_utc - last_scoring).total_seconds())

        # Get last P&L calculation timestamp
        result = client.query("SELECT max(calculated_at) FROM aware_trader_pnl")
        last_pnl = result.result_rows[0][0] if result.result_rows else None

        pnl_lag_seconds = 0
        if last_pnl:
            pnl_lag_seconds = int((now_utc - last_pnl).total_seconds())

        # Get data coverage (days of data)
        result = client.query("""
            SELECT dateDiff('day', min(ts), max(ts)) + 1
            FROM aware_global_trades_dedup
        """)
        data_coverage_days = result.result_rows[0][0] if result.result_rows else 0

        # Determine overall status (based on trade ingestion lag)
        status, status_emoji = _get_freshness_status(trade_lag_seconds)

        # Generate recommendation
        if status == 'fresh':
            recommendation = "Data is current and reliable"
        elif status == 'stale':
            recommendation = "Data may be slightly delayed - scores are still valid"
        else:
            recommendation = "Data is outdated - please wait for ingestion to resume"

        return DataFreshness(
            status=status,
            status_emoji=status_emoji,
            latest_trade_at=latest_trade,
            latest_trade_age_seconds=trade_lag_seconds,
            latest_trade_age_human=_human_readable_age(trade_lag_seconds) if latest_trade else "No data",
            last_scoring_at=last_scoring,
            last_scoring_age_human=_human_readable_age(scoring_lag_seconds) if last_scoring else "Never",
            last_pnl_at=last_pnl,
            last_pnl_age_human=_human_readable_age(pnl_lag_seconds) if last_pnl else "Never",
            data_coverage_days=data_coverage_days or 0,
            recommendation=recommendation
        )

    except Exception as e:
        logger.error(f"Freshness check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/monitoring", response_model=MonitoringResponse)
async def get_monitoring():
    """
    Comprehensive monitoring endpoint for data quality and pipeline health.

    Returns ingestion status, lag metrics, and pipeline health.
    """
    try:
        client = get_clickhouse_client()

        # Ingestion metrics
        result = client.query("""
            SELECT
                countIf(ts >= now() - INTERVAL 1 HOUR) AS trades_1h,
                countIf(ts >= now() - INTERVAL 24 HOUR) AS trades_24h,
                uniqExactIf(proxy_address, ts >= now() - INTERVAL 24 HOUR) AS traders_24h,
                uniqExactIf(market_slug, ts >= now() - INTERVAL 24 HOUR) AS markets_active,
                max(ts) AS latest_trade
            FROM aware_global_trades_dedup
        """)
        row = result.result_rows[0]
        trades_1h = row[0]
        trades_24h = row[1]
        traders_24h = row[2]
        markets_active = row[3]
        latest_trade = row[4]

        # Calculate lag
        lag_seconds = 0
        if latest_trade:
            from datetime import timezone
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            lag_seconds = int((now_utc - latest_trade).total_seconds())

        avg_per_hour = trades_24h / 24.0 if trades_24h > 0 else 0

        # Determine status
        status = 'healthy'
        issues = []

        if lag_seconds > 300:
            issues.append(f"Ingestion lag: {lag_seconds}s (>5min)")
            status = 'degraded'
        if lag_seconds > 900:
            status = 'unhealthy'
        if trades_1h == 0:
            issues.append("No trades in last hour")
            status = 'unhealthy'

        # Pipeline metrics (with fallbacks for missing tables)
        def safe_count(query: str) -> int:
            try:
                return client.query(query).result_rows[0][0]
            except Exception:
                return 0

        def safe_datetime(query: str):
            try:
                result = client.query(query)
                return result.result_rows[0][0] if result.result_rows else None
            except Exception:
                return None

        total_trades = safe_count("SELECT count() FROM aware_global_trades_dedup")
        total_traders = safe_count("SELECT uniqExact(proxy_address) FROM aware_global_trades_dedup")
        traders_scored = safe_count("SELECT count() FROM aware_smart_money_scores FINAL")
        traders_pnl = safe_count("SELECT count() FROM aware_trader_pnl FINAL WHERE total_realized_pnl != 0")
        traders_sharpe = safe_count("SELECT count() FROM aware_ml_scores FINAL WHERE sharpe_ratio != 0")
        resolutions = safe_count("SELECT count() FROM aware_resolutions FINAL")
        last_scoring = safe_datetime("SELECT max(calculated_at) FROM aware_smart_money_scores")

        return MonitoringResponse(
            ingestion_status=status,
            trades_last_hour=trades_1h,
            trades_last_24h=trades_24h,
            traders_last_24h=traders_24h,
            latest_trade_at=latest_trade,
            ingestion_lag_seconds=lag_seconds,
            markets_active=markets_active,
            avg_trades_per_hour=round(avg_per_hour, 1),
            issues=issues,
            total_trades=total_trades,
            total_traders=total_traders,
            traders_scored=traders_scored,
            traders_with_pnl=traders_pnl,
            traders_with_sharpe=traders_sharpe,
            resolutions_tracked=resolutions,
            last_scoring_at=last_scoring
        )

    except Exception as e:
        logger.error(f"Monitoring check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/monitoring/daily", response_model=list[DailyStats])
async def get_daily_stats(days: int = Query(default=7, ge=1, le=30)):
    """Get daily trade statistics for the last N days"""
    try:
        client = get_clickhouse_client()

        result = client.query(f"""
            SELECT
                toDate(ts) AS trade_date,
                count() AS trades,
                uniqExact(proxy_address) AS traders,
                uniqExact(market_slug) AS markets,
                sum(notional) AS volume_usd
            FROM aware_global_trades_dedup
            WHERE ts >= now() - INTERVAL {days} DAY
            GROUP BY trade_date
            ORDER BY trade_date DESC
        """)

        stats = []
        for row in result.result_rows:
            stats.append(DailyStats(
                date=row[0].isoformat() if row[0] else '',
                trades=row[1],
                traders=row[2],
                markets=row[3],
                volume_usd=round(row[4], 2)
            ))

        return stats

    except Exception as e:
        logger.error(f"Daily stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats", response_model=StatsResponse)
async def get_stats():
    """Get overall statistics"""
    try:
        client = get_clickhouse_client()

        result = client.query("""
            SELECT
                count() AS total_trades,
                uniqExact(proxy_address) AS total_traders,
                sum(notional) AS total_volume,
                countIf(ts >= now() - INTERVAL 1 DAY) AS trades_24h,
                uniqExactIf(proxy_address, ts >= now() - INTERVAL 1 DAY) AS traders_24h
            FROM aware_global_trades_dedup
        """)

        row = result.result_rows[0]
        return StatsResponse(
            total_trades=row[0],
            total_traders=row[1],
            total_volume_usd=row[2],
            trades_24h=row[3],
            traders_24h=row[4]
        )

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Valid tier and strategy values (whitelist for SQL injection prevention)
VALID_TIERS = {'BRONZE', 'SILVER', 'GOLD', 'DIAMOND'}
VALID_STRATEGIES = {'UNKNOWN', 'ARBITRAGEUR', 'MARKET_MAKER', 'DIRECTIONAL_FUNDAMENTAL',
                    'DIRECTIONAL_MOMENTUM', 'EVENT_DRIVEN', 'SCALPER', 'HYBRID'}


@app.get("/api/leaderboard", response_model=list[LeaderboardEntry])
@limiter.limit("100/minute")
async def get_leaderboard(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    tier: Optional[str] = Query(default=None),
    strategy: Optional[str] = Query(default=None),
    api_key: Optional[str] = Depends(optional_api_key)
):
    """
    Get the AWARE leaderboard.

    Traders ranked by Smart Money Score.
    """
    try:
        client = get_clickhouse_client()

        # Input validation - whitelist approach prevents SQL injection
        where_clauses = []
        if tier:
            tier_upper = tier.upper()
            if tier_upper not in VALID_TIERS:
                raise HTTPException(status_code=400, detail=f"Invalid tier. Must be one of: {', '.join(VALID_TIERS)}")
            where_clauses.append(f"tier = '{tier_upper}'")
        if strategy:
            strategy_upper = strategy.upper()
            if strategy_upper not in VALID_STRATEGIES:
                raise HTTPException(status_code=400, detail=f"Invalid strategy. Must be one of: {', '.join(VALID_STRATEGIES)}")
            where_clauses.append(f"strategy_type = '{strategy_upper}'")

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Use the ML-enhanced leaderboard view which includes sharpe_ratio and win_rate
        query = f"""
            SELECT
                rank,
                username,
                pseudonym,
                proxy_address,
                smart_money_score,
                tier,
                total_pnl,
                total_volume,
                coalesce(win_rate, 0.0) AS win_rate,
                coalesce(sharpe_ratio, 0.0) AS sharpe_ratio,
                strategy_type,
                strategy_confidence,
                0 AS rank_change,
                coalesce(p.total_trades, 0) AS total_trades,
                lb.model_version,
                lb.tier_confidence
            FROM aware_leaderboard_ml AS lb
            LEFT JOIN (SELECT proxy_address, total_trades FROM aware_trader_profiles FINAL) AS p
                ON lb.proxy_address = p.proxy_address
            WHERE {where_sql}
            ORDER BY rank ASC
            LIMIT {limit} OFFSET {offset}
        """

        result = client.query(query)

        entries = []
        for row in result.result_rows:
            entries.append(LeaderboardEntry(
                rank=row[0],
                username=row[1] or '',
                pseudonym=row[2],
                proxy_address=row[3],
                smart_money_score=row[4] or 0,
                tier=row[5] or 'BRONZE',
                total_pnl=row[6] or 0,
                total_volume=row[7] or 0,
                win_rate=row[8] or 0,
                sharpe_ratio=row[9] or 0,
                strategy_type=row[10] or 'UNKNOWN',
                strategy_confidence=row[11] or 0,
                rank_change=row[12] or 0,
                total_trades=row[13] or 0,
                model_version=row[14] if len(row) > 14 else None,
                tier_confidence=row[15] if len(row) > 15 else None
            ))

        return entries

    except Exception as e:
        logger.error(f"Failed to get leaderboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/traders/{identifier}", response_model=TraderProfile)
async def get_trader(identifier: str):
    """
    Get detailed profile for a trader.

    Looks up by username or proxy_address (wallet address).
    """
    try:
        client = get_clickhouse_client()

        # Check if identifier looks like a wallet address (starts with 0x)
        is_address = identifier.lower().startswith('0x')

        query = """
            SELECT
                s.username,
                p.pseudonym,
                s.proxy_address,
                s.total_score,
                s.tier,
                s.profitability_score,
                s.risk_adjusted_score,
                s.consistency_score,
                s.track_record_score,
                s.strategy_type,
                s.strategy_confidence,
                p.complete_set_ratio,
                p.direction_bias,
                p.total_pnl,
                p.total_volume_usd,
                p.total_trades,
                p.unique_markets,
                p.days_active,
                p.first_trade_at,
                p.last_trade_at
            FROM (SELECT * FROM aware_smart_money_scores FINAL) AS s
            LEFT JOIN (SELECT * FROM aware_trader_profiles FINAL) AS p
                ON s.proxy_address = p.proxy_address
            WHERE lower(s.username) = lower(%(identifier)s)
               OR lower(p.username) = lower(%(identifier)s)
               OR lower(s.proxy_address) = lower(%(identifier)s)
               OR lower(p.proxy_address) = lower(%(identifier)s)
            LIMIT 1
        """

        result = client.query(query, parameters={'identifier': identifier})

        if not result.result_rows:
            raise HTTPException(status_code=404, detail=f"Trader '{identifier}' not found")

        row = result.result_rows[0]
        return TraderProfile(
            username=row[0] or '',
            pseudonym=row[1],
            proxy_address=row[2],
            smart_money_score=row[3],
            tier=row[4],
            profitability_score=row[5],
            risk_adjusted_score=row[6],
            consistency_score=row[7],
            track_record_score=row[8],
            strategy_type=row[9],
            strategy_confidence=row[10],
            complete_set_ratio=row[11] or 0,
            direction_bias=row[12] or 0.5,
            total_pnl=row[13] or 0,
            total_volume=row[14] or 0,
            total_trades=row[15] or 0,
            unique_markets=row[16] or 0,
            days_active=row[17] or 0,
            first_trade_at=row[18],
            last_trade_at=row[19]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get trader: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/index/psi-10", response_model=PSIIndex)
async def get_psi_10():
    """
    Get the PSI-10 index composition.

    Top 10 traders weighted by Smart Money Score.
    """
    try:
        client = get_clickhouse_client()

        # Get top 10 by score
        query = """
            SELECT
                s.rank,
                s.username,
                s.proxy_address,
                s.total_score,
                p.total_pnl
            FROM (SELECT * FROM aware_smart_money_scores FINAL) AS s
            LEFT JOIN (SELECT * FROM aware_trader_profiles FINAL) AS p
                ON s.proxy_address = p.proxy_address
            ORDER BY s.rank ASC
            LIMIT 10
        """

        result = client.query(query)

        # Calculate weights (proportional to score)
        total_score = sum(row[3] for row in result.result_rows)

        composition = []
        for row in result.result_rows:
            weight = row[3] / total_score if total_score > 0 else 0
            composition.append(IndexComposition(
                rank=row[0],
                username=row[1] or '',
                proxy_address=row[2],
                smart_money_score=row[3],
                weight=weight,
                total_pnl=row[4] or 0
            ))

        # Get last calculation time
        calc_result = client.query(
            "SELECT max(calculated_at) FROM aware_smart_money_scores"
        )
        calculated_at = calc_result.result_rows[0][0] if calc_result.result_rows else datetime.utcnow()

        return PSIIndex(
            name="PSI-10",
            description="Top 10 traders weighted by Smart Money Score",
            trader_count=len(composition),
            total_weight=1.0,
            composition=composition,
            calculated_at=calculated_at
        )

    except Exception as e:
        logger.error(f"Failed to get PSI-10: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/indices/{index_type}", response_model=PSIIndex)
async def get_index_by_type(index_type: str):
    """
    Get any PSI index by type.

    Supported index types: PSI-10, PSI-25, PSI-50, PSI-CRYPTO, PSI-POLITICS, PSI-SPORTS
    """
    try:
        client = get_clickhouse_client()
        index_upper = index_type.upper()

        # Get index from aware_psi_index table
        # Table columns: index_type, username, proxy_address, weight, total_score,
        #                sharpe_ratio, strategy_type, created_at, rebalanced_at
        query = """
            SELECT
                proxy_address,
                username,
                weight,
                total_score,
                rebalanced_at
            FROM polybot.aware_psi_index FINAL
            WHERE index_type = %(index_type)s
            ORDER BY weight DESC
        """

        result = client.query(query, parameters={'index_type': index_upper})

        if not result.result_rows:
            raise HTTPException(status_code=404, detail=f"Index '{index_type}' not found")

        composition = []
        for i, row in enumerate(result.result_rows):
            composition.append(IndexComposition(
                rank=i + 1,
                username=row[1] or '',
                proxy_address=row[0],
                smart_money_score=row[3] or 0,  # total_score
                weight=float(row[2]) if row[2] else 0,
                total_pnl=0  # Not stored in index table
            ))

        # Get last calculation time
        calc_result = client.query(
            "SELECT max(rebalanced_at) FROM polybot.aware_psi_index WHERE index_type = %(index_type)s",
            parameters={'index_type': index_upper}
        )
        calculated_at = calc_result.result_rows[0][0] if calc_result.result_rows else datetime.utcnow()

        return PSIIndex(
            name=index_upper,
            description=f"PSI {index_upper} index composition",
            trader_count=len(composition),
            total_weight=sum(c.weight for c in composition),
            composition=composition,
            calculated_at=calculated_at
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get index {index_type}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# HIDDEN ALPHA ENDPOINTS
# ============================================================================

@app.get("/api/discovery/hidden-gems")
async def get_hidden_gems(limit: int = Query(default=10, ge=1, le=50)):
    """
    Find Hidden Gems: High quality traders with low visibility.

    These are traders with good scores but low volume - not yet on the public radar.
    """
    try:
        client = get_clickhouse_client()

        # Join scores with profiles to get all metrics
        query = f"""
        SELECT
            s.username,
            s.total_score,
            s.profitability_score,
            s.risk_adjusted_score,
            p.total_volume_usd,
            p.total_trades,
            p.days_active,
            p.total_pnl,
            s.strategy_type
        FROM (SELECT * FROM polybot.aware_smart_money_scores FINAL) AS s
        JOIN (SELECT * FROM polybot.aware_trader_profiles FINAL) AS p
            ON s.proxy_address = p.proxy_address
        WHERE
            s.total_score >= 40
            AND p.total_volume_usd <= 50000
            AND p.total_trades >= 20
            AND s.username != ''
        ORDER BY s.risk_adjusted_score DESC
        LIMIT {limit}
        """

        result = client.query(query)

        discoveries = []
        for row in result.result_rows:
            volume = row[4] or 0
            score = row[1] or 0
            risk_score = row[3] or 0
            visibility = min(100, (volume / 100000) * 100)
            discovery_score = min(100, score + (50 - visibility / 2))

            discoveries.append({
                'username': row[0],
                'discovery_type': 'HIDDEN_GEM',
                'discovery_score': round(discovery_score / 100, 2),
                'visibility_score': round(visibility, 1),
                'smart_money_score': score,
                'sharpe_ratio': round(risk_score / 30, 2),  # Approximate from risk score
                'win_rate': round(row[2] or 0, 1),  # Use profitability as proxy
                'volume_usd': round(volume, 0),
                'total_trades': row[5],
                'total_pnl': round(row[7] or 0, 2),
                'reason': f"Score {score} with only ${volume:,.0f} volume"
            })

        return {
            'discovery_type': 'HIDDEN_GEM',
            'count': len(discoveries),
            'discoveries': discoveries
        }

    except Exception as e:
        logger.error(f"Failed to find hidden gems: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/discovery/rising-stars")
async def get_rising_stars(
    max_days: int = Query(default=30, ge=1, le=90),
    limit: int = Query(default=10, ge=1, le=50)
):
    """
    Find Rising Stars: New traders with exceptional early performance.

    These traders have been active for less than 30 days but show
    exceptional metrics - potential future top performers.
    """
    try:
        client = get_clickhouse_client()

        query = f"""
        SELECT
            s.username,
            s.total_score,
            s.profitability_score,
            s.risk_adjusted_score,
            p.total_volume_usd,
            p.total_trades,
            p.days_active,
            p.total_pnl,
            s.strategy_type
        FROM (SELECT * FROM polybot.aware_smart_money_scores FINAL) AS s
        JOIN (SELECT * FROM polybot.aware_trader_profiles FINAL) AS p
            ON s.proxy_address = p.proxy_address
        WHERE
            p.days_active <= {max_days}
            AND s.profitability_score >= 10
            AND p.total_trades >= 10
            AND s.username != ''
        ORDER BY s.total_score DESC
        LIMIT {limit}
        """

        result = client.query(query)

        discoveries = []
        for row in result.result_rows:
            days_active = row[6] or 0
            score = row[1] or 0
            profit_score = row[2] or 0
            risk_score = row[3] or 0

            newness_score = max(0, 30 - days_active)
            discovery_score = min(100, newness_score + score)

            discoveries.append({
                'username': row[0],
                'discovery_type': 'RISING_STAR',
                'discovery_score': round(discovery_score / 100, 2),
                'days_active': days_active,
                'smart_money_score': score,
                'sharpe_ratio': round(risk_score / 30, 2),
                'win_rate': round(profit_score, 1),
                'total_trades': row[5],
                'total_pnl': round(row[7] or 0, 2),
                'reason': f"Only {days_active} days active with score {score}"
            })

        return {
            'discovery_type': 'RISING_STAR',
            'count': len(discoveries),
            'discoveries': discoveries
        }

    except Exception as e:
        logger.error(f"Failed to find rising stars: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/discovery/niche-specialists")
async def get_niche_specialists(limit: int = Query(default=10, ge=1, le=50)):
    """
    Find Niche Specialists: Traders who dominate specific market categories.

    These traders focus on one area and significantly outperform in that category.
    """
    try:
        client = get_clickhouse_client()

        query = f"""
        SELECT
            s.username,
            s.total_score,
            s.profitability_score,
            s.risk_adjusted_score,
            p.total_volume_usd,
            p.unique_markets,
            p.total_trades,
            s.strategy_type,
            p.total_pnl
        FROM (SELECT * FROM polybot.aware_smart_money_scores FINAL) AS s
        JOIN (SELECT * FROM polybot.aware_trader_profiles FINAL) AS p
            ON s.proxy_address = p.proxy_address
        WHERE
            p.unique_markets <= 5
            AND p.total_trades >= 20
            AND s.total_score >= 35
            AND s.username != ''
        ORDER BY s.risk_adjusted_score DESC
        LIMIT {limit}
        """

        result = client.query(query)

        discoveries = []
        for row in result.result_rows:
            unique_markets = row[5] or 1
            score = row[1] or 0
            risk_score = row[3] or 0
            concentration = 1.0 / max(1, unique_markets)
            discovery_score = min(100, score + concentration * 30)

            discoveries.append({
                'username': row[0],
                'discovery_type': 'NICHE_SPECIALIST',
                'discovery_score': round(discovery_score / 100, 2),
                'unique_markets': unique_markets,
                'market_concentration': round(concentration * 100, 1),
                'smart_money_score': score,
                'sharpe_ratio': round(risk_score / 30, 2),
                'win_rate': round(row[2] or 0, 1),
                'total_trades': row[6],
                'total_pnl': round(row[8] or 0, 2),
                'reason': f"Focused on {unique_markets} markets with score {score}"
            })

        return {
            'discovery_type': 'NICHE_SPECIALIST',
            'count': len(discoveries),
            'discoveries': discoveries
        }

    except Exception as e:
        logger.error(f"Failed to find niche specialists: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CONSENSUS SIGNAL ENDPOINTS
# ============================================================================

@app.get("/api/consensus/markets")
async def get_consensus_markets(
    min_traders: int = Query(default=3, ge=2, le=20),
    min_volume: float = Query(default=5000, ge=0),
    hours: int = Query(default=48, ge=1, le=168)
):
    """
    Get markets where smart money is forming consensus.

    Returns markets where multiple top traders are taking similar positions.
    """
    try:
        client = get_clickhouse_client()

        query = f"""
        WITH smart_traders AS (
            SELECT username
            FROM polybot.aware_smart_money_scores FINAL
            WHERE total_score >= 45
            LIMIT 100
        )
        SELECT
            market_slug,
            any(title) as title,
            outcome,
            count(DISTINCT username) as trader_count,
            sum(notional) as total_volume,
            avg(price) as avg_price
        FROM polybot.aware_global_trades
        WHERE
            username IN (SELECT username FROM smart_traders)
            AND ts >= now() - INTERVAL {hours} HOUR
        GROUP BY market_slug, outcome
        HAVING count(DISTINCT username) >= {min_traders}
           AND sum(notional) >= {min_volume}
        ORDER BY total_volume DESC
        LIMIT 20
        """

        result = client.query(query)

        signals = []
        for row in result.result_rows:
            signals.append({
                'market_slug': row[0],
                'title': row[1],
                'favored_outcome': row[2],
                'trader_count': row[3],
                'total_volume': round(row[4], 2),
                'avg_price': round(row[5], 3),
                'consensus_strength': 'STRONG' if row[3] >= 5 else 'MODERATE' if row[3] >= 3 else 'WEAK'
            })

        return {
            'lookback_hours': hours,
            'min_traders': min_traders,
            'signal_count': len(signals),
            'signals': signals
        }

    except Exception as e:
        logger.error(f"Failed to get consensus: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/consensus/market/{market_slug}")
async def get_market_consensus(market_slug: str, hours: int = Query(default=48, ge=1, le=168)):
    """
    Get detailed smart money analysis for a specific market.
    """
    try:
        client = get_clickhouse_client()

        # Sanitize market_slug to prevent SQL injection
        safe_market_slug = _sanitize_identifier(market_slug, max_length=200)
        if not safe_market_slug:
            raise HTTPException(status_code=400, detail="Invalid market slug")

        query = f"""
        WITH smart_traders AS (
            SELECT username, total_score as smart_money_score
            FROM polybot.aware_smart_money_scores FINAL
            WHERE total_score >= 45
        )
        SELECT
            t.username,
            s.smart_money_score,
            t.side,
            t.outcome,
            sum(t.notional) as total_notional,
            count() as trade_count,
            max(t.ts) as last_trade
        FROM polybot.aware_global_trades t
        JOIN smart_traders s ON t.username = s.username
        WHERE
            t.market_slug = '{safe_market_slug}'
            AND t.ts >= now() - INTERVAL {hours} HOUR
        GROUP BY t.username, s.smart_money_score, t.side, t.outcome
        ORDER BY total_notional DESC
        """

        result = client.query(query)

        traders = []
        yes_volume = 0
        no_volume = 0

        for row in result.result_rows:
            outcome = (row[3] or '').upper()
            side = (row[2] or '').upper()
            notional = row[4]

            # Determine direction
            if (side == 'BUY' and 'YES' in outcome) or (side == 'SELL' and 'NO' in outcome):
                direction = 'YES'
                yes_volume += notional
            else:
                direction = 'NO'
                no_volume += notional

            traders.append({
                'username': row[0],
                'smart_money_score': row[1],
                'direction': direction,
                'volume': round(notional, 2),
                'trade_count': row[5],
                'last_trade': row[6].isoformat() if row[6] else None
            })

        total_volume = yes_volume + no_volume

        return {
            'market_slug': market_slug,
            'lookback_hours': hours,
            'summary': {
                'total_smart_money_volume': round(total_volume, 2),
                'yes_volume': round(yes_volume, 2),
                'no_volume': round(no_volume, 2),
                'consensus_direction': 'YES' if yes_volume > no_volume else 'NO' if no_volume > yes_volume else 'SPLIT',
                'consensus_strength': round(max(yes_volume, no_volume) / total_volume * 100, 1) if total_volume > 0 else 0
            },
            'traders': traders
        }

    except Exception as e:
        logger.error(f"Failed to get market consensus: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# EDGE DECAY ENDPOINTS
# ============================================================================

@app.get("/api/edge/health/{username}")
async def get_trader_health(username: str):
    """
    Get edge health check for a trader.

    Compares recent vs historical performance to detect edge decay.
    """
    try:
        client = get_clickhouse_client()

        # Sanitize username to prevent SQL injection
        safe_username = _sanitize_identifier(username)
        if not safe_username:
            raise HTTPException(status_code=400, detail="Invalid username")

        # Get historical metrics (90 days)
        hist_query = f"""
        SELECT
            count() as trade_count,
            avg(notional) as avg_return,
            stddevPop(notional) as return_std,
            sum(notional) as total_pnl
        FROM polybot.aware_global_trades
        WHERE
            username = '{safe_username}'
            AND ts >= now() - INTERVAL 90 DAY
        """

        # Get recent metrics (30 days)
        recent_query = f"""
        SELECT
            count() as trade_count,
            avg(notional) as avg_return,
            stddevPop(notional) as return_std,
            sum(notional) as total_pnl
        FROM polybot.aware_global_trades
        WHERE
            username = '{safe_username}'
            AND ts >= now() - INTERVAL 30 DAY
        """

        hist_result = client.query(hist_query)
        recent_result = client.query(recent_query)

        if not hist_result.result_rows or hist_result.result_rows[0][0] < 20:
            return {
                'username': username,
                'status': 'INSUFFICIENT_DATA',
                'message': 'Not enough trading history for analysis'
            }

        hist = hist_result.result_rows[0]
        recent = recent_result.result_rows[0]

        hist_return = hist[1] or 0
        hist_std = hist[2] or 1
        hist_sharpe = hist_return / hist_std if hist_std > 0 else 0

        recent_return = recent[1] or 0
        recent_std = recent[2] or 1
        recent_sharpe = recent_return / recent_std if recent_std > 0 else 0

        # Calculate decay
        if hist_sharpe > 0:
            sharpe_change = (recent_sharpe - hist_sharpe) / hist_sharpe
        else:
            sharpe_change = 0

        # Determine status
        if sharpe_change < -0.40:
            status = 'CRITICAL'
            health_score = max(0, 100 + sharpe_change * 100)
        elif sharpe_change < -0.25:
            status = 'SEVERE'
            health_score = max(20, 100 + sharpe_change * 100)
        elif sharpe_change < -0.15:
            status = 'MODERATE'
            health_score = max(40, 100 + sharpe_change * 100)
        elif sharpe_change < 0:
            status = 'EARLY_WARNING'
            health_score = max(60, 100 + sharpe_change * 100)
        else:
            status = 'HEALTHY'
            health_score = min(100, 100 + sharpe_change * 50)

        return {
            'username': username,
            'status': status,
            'health_score': round(health_score, 1),
            'historical_sharpe': round(hist_sharpe, 2),
            'recent_sharpe': round(recent_sharpe, 2),
            'sharpe_change_pct': round(sharpe_change * 100, 1),
            'historical_trades': hist[0],
            'recent_trades': recent[0],
            'recommendation': _get_decay_recommendation(status) if status != 'HEALTHY' else 'Continue monitoring'
        }

    except Exception as e:
        logger.error(f"Failed to check trader health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _get_decay_recommendation(status: str) -> str:
    """Get recommendation based on decay status"""
    recommendations = {
        'EARLY_WARNING': 'Increase monitoring frequency',
        'MODERATE': 'Consider reducing index weight by 50%',
        'SEVERE': 'Remove from index consideration',
        'CRITICAL': 'Immediate removal from all indices'
    }
    return recommendations.get(status, 'Continue monitoring')


@app.get("/api/edge/alerts")
async def get_edge_alerts(
    min_decay: float = Query(default=15, ge=0, le=100),
    limit: int = Query(default=20, ge=1, le=100)
):
    """
    Get traders showing edge decay.

    Scans indexed traders and returns those with performance decline.
    Uses a single batch query instead of N+1 pattern for performance.
    """
    try:
        client = get_clickhouse_client()

        # OPTIMIZED: Single query calculates both historical (90d) and recent (30d) metrics
        # This replaces 1000+ individual queries with 1 batch query
        query = f"""
        WITH
        -- Historical metrics (90 days)
        hist AS (
            SELECT
                username,
                avg(notional) AS hist_avg,
                stddevPop(notional) AS hist_std,
                count() AS hist_count
            FROM polybot.aware_global_trades
            WHERE ts >= now() - INTERVAL 90 DAY
              AND username != ''
            GROUP BY username
            HAVING count() >= 30
        ),
        -- Recent metrics (30 days)
        recent AS (
            SELECT
                username,
                avg(notional) AS recent_avg,
                stddevPop(notional) AS recent_std,
                count() AS recent_count
            FROM polybot.aware_global_trades
            WHERE ts >= now() - INTERVAL 30 DAY
              AND username != ''
            GROUP BY username
            HAVING count() >= 10
        )
        SELECT
            h.username,
            h.hist_avg / nullIf(h.hist_std, 0) AS hist_sharpe,
            r.recent_avg / nullIf(r.recent_std, 0) AS recent_sharpe,
            h.hist_count,
            r.recent_count
        FROM hist h
        INNER JOIN recent r ON h.username = r.username
        WHERE h.hist_std > 0 AND r.recent_std > 0
          AND h.hist_avg / h.hist_std > 0  -- Only traders with positive historical Sharpe
        ORDER BY ((h.hist_avg / h.hist_std) - (r.recent_avg / r.recent_std)) / (h.hist_avg / h.hist_std) DESC
        LIMIT 500
        """

        result = client.query(query)

        alerts = []
        for row in result.result_rows:
            username = row[0]
            hist_sharpe = float(row[1]) if row[1] else 0
            recent_sharpe = float(row[2]) if row[2] else 0

            if hist_sharpe > 0:
                decline = ((hist_sharpe - recent_sharpe) / hist_sharpe) * 100
                if decline >= min_decay:
                    alerts.append({
                        'username': username,
                        'decline_pct': round(decline, 1),
                        'historical_sharpe': round(hist_sharpe, 2),
                        'recent_sharpe': round(recent_sharpe, 2)
                    })

        # Already sorted by decline in query, but ensure order
        alerts.sort(key=lambda x: x['decline_pct'], reverse=True)

        return {
            'min_decay_threshold': min_decay,
            'alert_count': len(alerts[:limit]),
            'alerts': alerts[:limit]
        }

    except Exception as e:
        logger.error(f"Failed to get edge alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ACTIVITY FEED ENDPOINT
# ============================================================================

@app.get("/api/activity/recent")
async def get_recent_activity(
    min_score: int = Query(default=60, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=200)
):
    """
    Get recent trades from smart money traders.

    Real-time feed of what top traders are doing.
    """
    try:
        client = get_clickhouse_client()

        query = f"""
        SELECT
            t.ts,
            t.username,
            s.total_score,
            t.market_slug,
            t.title,
            t.side,
            t.outcome,
            t.price,
            t.size,
            t.notional
        FROM polybot.aware_global_trades t
        JOIN (
            SELECT username, total_score
            FROM polybot.aware_smart_money_scores FINAL
            WHERE total_score >= {min_score}
        ) s ON t.username = s.username
        ORDER BY t.ts DESC
        LIMIT {limit}
        """

        result = client.query(query)

        trades = []
        for row in result.result_rows:
            trades.append({
                'timestamp': row[0].isoformat() if row[0] else None,
                'username': row[1],
                'smart_money_score': row[2],
                'market_slug': row[3],
                'title': row[4],
                'side': row[5],
                'outcome': row[6],
                'price': round(row[7], 3) if row[7] else None,
                'size': round(row[8], 2) if row[8] else None,
                'notional': round(row[9], 2) if row[9] else None
            })

        return {
            'min_smart_money_score': min_score,
            'trade_count': len(trades),
            'trades': trades
        }

    except Exception as e:
        logger.error(f"Failed to get recent activity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# FUND ENDPOINTS
# ============================================================================

class FundNAV(BaseModel):
    """Fund Net Asset Value"""
    fund_id: str
    nav: float
    capital: float
    position_value: float
    unrealized_pnl: float
    realized_pnl: float
    total_return: float
    open_positions: int
    last_updated: Optional[datetime]


class FundPosition(BaseModel):
    """A position held by the fund"""
    token_id: str
    market_slug: str
    outcome: str
    shares: float
    avg_entry_price: float
    current_price: float
    current_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float


class FundTrade(BaseModel):
    """A trade executed by the fund"""
    timestamp: datetime
    source_trader: str
    market_slug: str
    outcome: str
    side: str
    shares: float
    price: float
    notional_usd: float
    status: str


class FundPerformance(BaseModel):
    """Fund performance for a period"""
    period: str
    start_nav: float
    end_nav: float
    return_pct: float
    trades_count: int
    volume_traded: float
    sharpe_ratio: float


@app.get("/api/fund/nav", response_model=FundNAV)
async def get_fund_nav(fund_id: str = Query(default="PSI-10")):
    """
    Get current NAV (Net Asset Value) for a fund.

    Returns the fund's current value, positions, and P&L.
    Fund types: PSI-10, PSI-25, PSI-50, ALPHA-ARB, ALPHA-INSIDER, ALPHA-EDGE, ALPHA-CONSENSUS
    """
    try:
        client = get_clickhouse_client()

        # v_fund_nav_latest view uses fund_type column
        query = """
        SELECT
            fund_type,
            nav_per_share,
            capital,
            position_value,
            total_fund_value,
            total_pnl,
            daily_return_pct,
            num_positions,
            last_updated
        FROM polybot.v_fund_nav_latest
        WHERE fund_type = %(fund_type)s
        LIMIT 1
        """

        result = client.query(query, parameters={'fund_type': fund_id.upper()})

        if not result.result_rows:
            # Return default for new fund
            return FundNAV(
                fund_id=fund_id,
                nav=10000.0,
                capital=10000.0,
                position_value=0.0,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                total_return=0.0,
                open_positions=0,
                last_updated=None
            )

        row = result.result_rows[0]
        # View columns: fund_type(0), nav_per_share(1), capital(2), position_value(3),
        #               total_fund_value(4), total_pnl(5), daily_return_pct(6),
        #               num_positions(7), last_updated(8)
        return FundNAV(
            fund_id=row[0],
            nav=float(row[4]) if row[4] else 10000.0,  # total_fund_value
            capital=float(row[2]) if row[2] else 0.0,
            position_value=float(row[3]) if row[3] else 0.0,
            unrealized_pnl=float(row[5]) if row[5] else 0.0,  # total_pnl
            realized_pnl=0.0,  # Not tracked separately
            total_return=float(row[6]) if row[6] else 0.0,  # daily_return_pct
            open_positions=int(row[7]) if row[7] else 0,
            last_updated=row[8]
        )

    except Exception as e:
        logger.error(f"Failed to get fund NAV: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/fund/positions", response_model=list[FundPosition])
async def get_fund_positions(fund_id: str = Query(default="psi-10-main")):
    """
    Get current positions held by the fund.
    """
    try:
        client = get_clickhouse_client()

        query = """
        SELECT
            token_id,
            market_slug,
            outcome,
            shares,
            avg_entry_price,
            current_price,
            current_value,
            unrealized_pnl,
            unrealized_pnl_pct
        FROM polybot.v_fund_positions_valued
        WHERE fund_id = %(fund_id)s
        ORDER BY current_value DESC
        """

        result = client.query(query, parameters={'fund_id': fund_id})

        positions = []
        for row in result.result_rows:
            positions.append(FundPosition(
                token_id=row[0],
                market_slug=row[1],
                outcome=row[2],
                shares=float(row[3]),
                avg_entry_price=float(row[4]),
                current_price=float(row[5]),
                current_value=float(row[6]),
                unrealized_pnl=float(row[7]),
                unrealized_pnl_pct=float(row[8])
            ))

        return positions

    except Exception as e:
        logger.error(f"Failed to get fund positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/fund/trades", response_model=list[FundTrade])
async def get_fund_trades(
    fund_id: str = Query(default="psi-10-main"),
    limit: int = Query(default=50, ge=1, le=500)
):
    """
    Get recent trades executed by the fund.
    """
    try:
        client = get_clickhouse_client()

        query = f"""
        SELECT
            ts,
            source_trader,
            market_slug,
            outcome,
            side,
            shares,
            price,
            notional_usd,
            status
        FROM polybot.aware_fund_trades
        WHERE fund_id = %(fund_id)s
        ORDER BY ts DESC
        LIMIT {limit}
        """

        result = client.query(query, parameters={'fund_id': fund_id})

        trades = []
        for row in result.result_rows:
            trades.append(FundTrade(
                timestamp=row[0],
                source_trader=row[1],
                market_slug=row[2],
                outcome=row[3],
                side=row[4],
                shares=float(row[5]),
                price=float(row[6]),
                notional_usd=float(row[7]),
                status=row[8]
            ))

        return trades

    except Exception as e:
        logger.error(f"Failed to get fund trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/fund/performance", response_model=list[FundPerformance])
async def get_fund_performance(fund_id: str = Query(default="psi-10-main")):
    """
    Get fund performance across different time periods.
    """
    try:
        client = get_clickhouse_client()

        query = """
        SELECT
            period,
            start_nav,
            end_nav,
            return_pct,
            trades_count,
            volume_traded,
            sharpe_ratio
        FROM polybot.aware_fund_performance FINAL
        WHERE fund_id = %(fund_id)s
        ORDER BY
            CASE period
                WHEN 'daily' THEN 1
                WHEN 'weekly' THEN 2
                WHEN 'monthly' THEN 3
                WHEN 'all_time' THEN 4
            END
        """

        result = client.query(query, parameters={'fund_id': fund_id})

        performance = []
        for row in result.result_rows:
            performance.append(FundPerformance(
                period=row[0],
                start_nav=float(row[1]),
                end_nav=float(row[2]),
                return_pct=float(row[3]),
                trades_count=int(row[4]),
                volume_traded=float(row[5]),
                sharpe_ratio=float(row[6])
            ))

        return performance

    except Exception as e:
        logger.error(f"Failed to get fund performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/fund/index")
async def get_fund_index(index_type: str = Query(default="PSI-10")):
    """
    Get the current PSI index constituents and weights.

    Returns traders in the index with their weights.
    """
    try:
        client = get_clickhouse_client()

        query = """
        SELECT
            username,
            weight,
            total_score,
            sharpe_ratio,
            strategy_type,
            rebalanced_at
        FROM polybot.v_psi_index_current
        WHERE index_type = %(index_type)s
        """

        result = client.query(query, parameters={'index_type': index_type})

        constituents = []
        for i, row in enumerate(result.result_rows):
            constituents.append({
                'rank': i + 1,
                'username': row[0],
                'weight': round(float(row[1]) * 100, 2),  # As percentage
                'smart_money_score': float(row[2]),
                'sharpe_ratio': float(row[3]),
                'strategy_type': row[4],
                'rebalanced_at': row[5].isoformat() if row[5] else None
            })

        return {
            'index_type': index_type,
            'constituent_count': len(constituents),
            'total_weight': sum(c['weight'] for c in constituents),
            'constituents': constituents
        }

    except Exception as e:
        logger.error(f"Failed to get fund index: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class FundInfo(BaseModel):
    """Fund information"""
    fund_id: str
    fund_type: str  # MIRROR or ACTIVE
    description: str
    strategy: str
    capital_usd: Optional[float]
    is_active: bool


class FundExecution(BaseModel):
    """A signal execution by the fund"""
    signal_id: str
    fund_id: str
    trader_username: str
    market_slug: str
    outcome: str
    signal_type: str
    trader_shares: float
    fund_shares: float
    execution_price: float
    detected_at: datetime
    executed_at: datetime


@app.get("/api/fund/list", response_model=list[FundInfo])
async def list_funds():
    """
    List all available fund types.

    Returns both MIRROR funds (PSI indexes) and ACTIVE funds (ALPHA strategies).
    """
    # Static fund definitions - these match FundType.java
    funds = [
        # MIRROR funds (passive, mirror top traders)
        FundInfo(
            fund_id="PSI-10",
            fund_type="MIRROR",
            description="Top 10 Smart Money traders",
            strategy="Mirror positions of top 10 replicable traders by Smart Money Score",
            capital_usd=None,
            is_active=True
        ),
        FundInfo(
            fund_id="PSI-25",
            fund_type="MIRROR",
            description="Top 25 Smart Money traders",
            strategy="Broader index mirroring top 25 traders",
            capital_usd=None,
            is_active=False
        ),
        FundInfo(
            fund_id="PSI-SPORTS",
            fund_type="MIRROR",
            description="Top sports betting traders",
            strategy="Mirror top traders specializing in sports markets",
            capital_usd=None,
            is_active=False
        ),
        FundInfo(
            fund_id="PSI-CRYPTO",
            fund_type="MIRROR",
            description="Top crypto price traders",
            strategy="Mirror top traders in crypto price prediction markets",
            capital_usd=None,
            is_active=False
        ),
        FundInfo(
            fund_id="PSI-POLITICS",
            fund_type="MIRROR",
            description="Top political market traders",
            strategy="Mirror top traders in political prediction markets",
            capital_usd=None,
            is_active=False
        ),
        # ACTIVE funds (proprietary strategies)
        FundInfo(
            fund_id="ALPHA-ARB",
            fund_type="ACTIVE",
            description="Complete-set arbitrage strategy",
            strategy="Runs gabagool22-style arbitrage on Up/Down binary markets",
            capital_usd=None,
            is_active=True
        ),
        FundInfo(
            fund_id="ALPHA-INSIDER",
            fund_type="ACTIVE",
            description="Insider signal following",
            strategy="Trades based on insider detection signals",
            capital_usd=None,
            is_active=False
        ),
        FundInfo(
            fund_id="ALPHA-EDGE",
            fund_type="ACTIVE",
            description="Multi-strategy alpha fund",
            strategy="Combines arbitrage, insider signals, and momentum",
            capital_usd=None,
            is_active=False
        ),
    ]

    return funds


@app.get("/api/fund/executions", response_model=list[FundExecution])
async def get_fund_executions(
    fund_id: str = Query(default="PSI-10"),
    limit: int = Query(default=50, ge=1, le=500)
):
    """
    Get fund executions (signal mirrors).

    Shows the signals from tracked traders and how the fund executed them.
    """
    try:
        client = get_clickhouse_client()

        query = f"""
        SELECT
            signal_id,
            fund_id,
            trader_username,
            market_slug,
            outcome,
            signal_type,
            trader_shares,
            fund_shares,
            execution_price,
            detected_at,
            executed_at
        FROM polybot.aware_fund_executions
        WHERE fund_id = %(fund_id)s
        ORDER BY executed_at DESC
        LIMIT {limit}
        """

        result = client.query(query, parameters={'fund_id': fund_id})

        executions = []
        for row in result.result_rows:
            executions.append(FundExecution(
                signal_id=row[0],
                fund_id=row[1],
                trader_username=row[2],
                market_slug=row[3],
                outcome=row[4],
                signal_type=row[5],
                trader_shares=float(row[6]),
                fund_shares=float(row[7]),
                execution_price=float(row[8]),
                detected_at=row[9],
                executed_at=row[10]
            ))

        return executions

    except Exception as e:
        logger.error(f"Failed to get fund executions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# INSIDER ALERTS ENDPOINTS
# ============================================================================

class InsiderAlert(BaseModel):
    """An insider activity alert"""
    signal_type: str
    severity: str
    market_slug: str
    market_question: str
    description: str
    confidence: float
    direction: str
    total_volume_usd: float
    num_traders: int
    detected_at: datetime
    traders_involved: list[str]


class InsiderAlertsResponse(BaseModel):
    """Response containing insider alerts"""
    lookback_hours: int
    alert_count: int
    alerts: list[InsiderAlert]


@app.get("/api/insider/alerts", response_model=InsiderAlertsResponse)
@limiter.limit("30/minute")
async def get_insider_alerts(
    request: Request,
    hours: int = Query(default=48, ge=1, le=168),
    min_confidence: float = Query(default=0.3, ge=0.0, le=1.0),
    api_key: Optional[str] = Depends(optional_api_key)
):
    """
    Get insider activity alerts.

    Scans for suspicious trading patterns that may indicate insider knowledge:
    - NEW_ACCOUNT_WHALE: New accounts making large bets on obscure markets
    - VOLUME_SPIKE: Unusual volume spikes before news events
    - SMART_MONEY_DIVERGENCE: Top traders betting against market consensus
    - WHALE_ANOMALY: Known whales entering unusual market categories
    """
    try:
        client = get_clickhouse_client()

        # Check if the insider alerts table exists
        try:
            result = client.query(f"""
                SELECT
                    signal_type,
                    severity,
                    market_slug,
                    market_question,
                    description,
                    confidence,
                    direction,
                    total_volume_usd,
                    num_traders,
                    detected_at,
                    traders_involved
                FROM polybot.aware_insider_alerts FINAL
                WHERE detected_at >= now() - INTERVAL {hours} HOUR
                  AND confidence >= {min_confidence}
                ORDER BY detected_at DESC, severity DESC
                LIMIT 100
            """)

            alerts = []
            for row in result.result_rows:
                # Parse traders_involved (stored as comma-separated string)
                traders = row[10].split(',') if row[10] else []
                traders = [t.strip() for t in traders if t.strip()]

                alerts.append(InsiderAlert(
                    signal_type=row[0],
                    severity=row[1],
                    market_slug=row[2],
                    market_question=row[3] or '',
                    description=row[4] or '',
                    confidence=float(row[5]),
                    direction=row[6],
                    total_volume_usd=float(row[7]),
                    num_traders=int(row[8]),
                    detected_at=row[9],
                    traders_involved=traders
                ))

            return InsiderAlertsResponse(
                lookback_hours=hours,
                alert_count=len(alerts),
                alerts=alerts
            )

        except Exception as table_err:
            # Table doesn't exist yet - return empty response
            logger.warning(f"Insider alerts table may not exist: {table_err}")
            return InsiderAlertsResponse(
                lookback_hours=hours,
                alert_count=0,
                alerts=[]
            )

    except Exception as e:
        logger.error(f"Failed to get insider alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/insider/scan")
async def scan_for_insider_activity(hours: int = Query(default=24, ge=1, le=72)):
    """
    Trigger an insider activity scan.

    This endpoint runs the InsiderDetector to find new suspicious activity.
    Note: In production, this would be called by a scheduled job.
    """
    try:
        # Import the insider detector
        from insider_detector import InsiderDetector

        client = get_clickhouse_client()
        detector = InsiderDetector(client)

        # Run the scan
        alerts = detector.scan_for_insider_activity(lookback_hours=hours)

        return {
            'status': 'success',
            'alerts_found': len(alerts),
            'lookback_hours': hours,
            'alerts': [
                {
                    'signal_type': a.signal_type.value,
                    'severity': a.severity.value,
                    'market_slug': a.market_slug,
                    'confidence': a.confidence,
                    'direction': a.direction
                }
                for a in alerts
            ]
        }

    except ImportError:
        return {
            'status': 'error',
            'message': 'InsiderDetector module not available'
        }
    except Exception as e:
        logger.error(f"Failed to scan for insider activity: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ML ENRICHMENT ENDPOINTS
# ============================================================================

class MLClusterSummary(BaseModel):
    """Summary of a Strategy DNA cluster"""
    cluster_id: int
    strategy_cluster: str
    trader_count: int
    anomaly_count: int
    avg_anomaly_score: float


class MLTraderEnrichment(BaseModel):
    """ML enrichment data for a trader"""
    proxy_address: str
    username: str
    cluster_id: int
    strategy_cluster: str
    cluster_description: str
    is_anomaly: bool
    anomaly_score: float
    anomaly_type: str
    updated_at: Optional[datetime]


class MLAnomalyEntry(BaseModel):
    """An anomalous trader entry"""
    proxy_address: str
    username: str
    strategy_cluster: str
    anomaly_score: float
    anomaly_type: str
    smart_money_score: Optional[float]
    total_volume: Optional[float]


@app.get("/api/ml/clusters", response_model=list[MLClusterSummary])
async def get_ml_clusters():
    """
    Get Strategy DNA cluster distribution.

    Shows how traders are grouped by behavioral patterns.
    """
    try:
        client = get_clickhouse_client()

        result = client.query("""
            SELECT
                cluster_id,
                strategy_cluster,
                count() AS trader_count,
                sum(is_anomaly) AS anomaly_count,
                avg(anomaly_score) AS avg_anomaly_score
            FROM polybot.aware_ml_enrichment FINAL
            GROUP BY cluster_id, strategy_cluster
            ORDER BY trader_count DESC
        """)

        clusters = []
        for row in result.result_rows:
            clusters.append(MLClusterSummary(
                cluster_id=int(row[0]),
                strategy_cluster=row[1] or 'UNKNOWN',
                trader_count=int(row[2]),
                anomaly_count=int(row[3]),
                avg_anomaly_score=float(row[4]) if row[4] else 0.0
            ))

        return clusters

    except Exception as e:
        logger.error(f"Failed to get ML clusters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ml/anomalies", response_model=list[MLAnomalyEntry])
async def get_ml_anomalies(
    limit: int = Query(default=50, ge=1, le=200),
    anomaly_type: Optional[str] = Query(default=None)
):
    """
    Get traders flagged as anomalous by ML models.

    Anomaly types:
    - ISOLATION: Detected by Isolation Forest (global outlier)
    - RECONSTRUCTION: Detected by Autoencoder (behavioral anomaly)
    - BOTH: Flagged by both models (high confidence anomaly)
    """
    try:
        client = get_clickhouse_client()

        where_clause = "is_anomaly = 1"
        if anomaly_type:
            safe_type = anomaly_type.upper()
            if safe_type in ('ISOLATION', 'RECONSTRUCTION', 'BOTH'):
                where_clause += f" AND anomaly_type = '{safe_type}'"

        query = f"""
            SELECT
                ml.proxy_address,
                ml.username,
                ml.strategy_cluster,
                ml.anomaly_score,
                ml.anomaly_type,
                s.total_score AS smart_money_score,
                p.total_volume_usd AS total_volume
            FROM (SELECT * FROM polybot.aware_ml_enrichment FINAL) AS ml
            LEFT JOIN (SELECT * FROM polybot.aware_smart_money_scores FINAL) AS s
                ON ml.proxy_address = s.proxy_address
            LEFT JOIN (SELECT * FROM polybot.aware_trader_profiles FINAL) AS p
                ON ml.proxy_address = p.proxy_address
            WHERE {where_clause}
            ORDER BY ml.anomaly_score ASC
            LIMIT {limit}
        """

        result = client.query(query)

        anomalies = []
        for row in result.result_rows:
            anomalies.append(MLAnomalyEntry(
                proxy_address=row[0],
                username=row[1] or '',
                strategy_cluster=row[2] or 'UNKNOWN',
                anomaly_score=float(row[3]) if row[3] else 0.0,
                anomaly_type=row[4] or 'UNKNOWN',
                smart_money_score=float(row[5]) if row[5] else None,
                total_volume=float(row[6]) if row[6] else None
            ))

        return anomalies

    except Exception as e:
        logger.error(f"Failed to get ML anomalies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ml/trader/{identifier}", response_model=MLTraderEnrichment)
async def get_trader_ml_enrichment(identifier: str):
    """
    Get ML enrichment data for a specific trader.

    Looks up by username or proxy_address.
    """
    try:
        client = get_clickhouse_client()

        result = client.query("""
            SELECT
                proxy_address,
                username,
                cluster_id,
                strategy_cluster,
                cluster_description,
                is_anomaly,
                anomaly_score,
                anomaly_type,
                updated_at
            FROM polybot.aware_ml_enrichment FINAL
            WHERE lower(username) = lower(%(identifier)s)
               OR lower(proxy_address) = lower(%(identifier)s)
            LIMIT 1
        """, parameters={'identifier': identifier})

        if not result.result_rows:
            raise HTTPException(status_code=404, detail=f"ML enrichment not found for '{identifier}'")

        row = result.result_rows[0]
        return MLTraderEnrichment(
            proxy_address=row[0],
            username=row[1] or '',
            cluster_id=int(row[2]),
            strategy_cluster=row[3] or 'UNKNOWN',
            cluster_description=row[4] or '',
            is_anomaly=bool(row[5]),
            anomaly_score=float(row[6]) if row[6] else 0.0,
            anomaly_type=row[7] or 'NORMAL',
            updated_at=row[8]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get trader ML enrichment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ml/health")
async def get_ml_health():
    """
    Get ML pipeline health status.

    Returns status matching MLHealthResponse interface:
    - status: 'healthy' | 'degraded' | 'unhealthy'
    - model_version: string
    - scoring_method: 'ml_ensemble' | 'rule_based'
    - traders_scored: number
    - tier_distribution: Record<string, number>
    - drift_status: 'normal' | 'warning' | 'critical'
    - drift_ratio: number
    - drifted_features: string[]
    """
    try:
        client = get_clickhouse_client()

        # Get ML enrichment stats
        enrichment_result = client.query("""
            SELECT
                count() AS total_enriched,
                countIf(is_anomaly = 1) AS anomalies,
                uniqExact(strategy_cluster) AS num_clusters,
                max(updated_at) AS last_update,
                dateDiff('minute', max(updated_at), now()) AS minutes_ago
            FROM polybot.aware_ml_enrichment FINAL
        """)

        # Get scoring stats and model version from ML scores
        scores_result = client.query("""
            SELECT
                count() AS traders_scored,
                max(model_version) AS model_version,
                max(calculated_at) AS last_scoring_at
            FROM polybot.aware_ml_scores FINAL
        """)

        # Get tier distribution from smart money scores
        tier_result = client.query("""
            SELECT
                tier,
                count() AS count
            FROM polybot.aware_smart_money_scores FINAL
            WHERE tier != ''
            GROUP BY tier
        """)

        tier_distribution = {}
        for row in tier_result.result_rows:
            tier_distribution[row[0]] = int(row[1])

        # Ensure all tiers are present
        for tier in ['DIAMOND', 'GOLD', 'SILVER', 'BRONZE']:
            if tier not in tier_distribution:
                tier_distribution[tier] = 0

        # Parse enrichment stats
        if enrichment_result.result_rows:
            e_row = enrichment_result.result_rows[0]
            minutes_ago = e_row[4] if e_row[4] else 9999
        else:
            minutes_ago = 9999

        # Parse scoring stats
        traders_scored = 0
        model_version = 'rule_based_v1'
        last_scoring_at = None
        if scores_result.result_rows:
            s_row = scores_result.result_rows[0]
            traders_scored = int(s_row[0]) if s_row[0] else 0
            model_version = s_row[1] if s_row[1] else 'rule_based_v1'
            last_scoring_at = s_row[2].isoformat() if s_row[2] else None

        # Determine scoring method from model version
        scoring_method = 'ml_ensemble' if 'ensemble' in model_version.lower() else 'rule_based'

        # Compute overall status
        if minutes_ago < 120 and traders_scored > 0:
            status = 'healthy'
        elif minutes_ago < 360 or traders_scored > 0:
            status = 'degraded'
        else:
            status = 'unhealthy'

        # Compute drift status (based on data freshness for now)
        if minutes_ago < 60:
            drift_status = 'normal'
            drift_ratio = 0.0
        elif minutes_ago < 240:
            drift_status = 'warning'
            drift_ratio = min(0.3, minutes_ago / 800)
        else:
            drift_status = 'critical'
            drift_ratio = min(0.8, minutes_ago / 500)

        return {
            'status': status,
            'model_version': model_version,
            'last_scoring_at': last_scoring_at,
            'traders_scored': traders_scored,
            'scoring_method': scoring_method,
            'tier_distribution': tier_distribution,
            'drift_status': drift_status,
            'drift_ratio': drift_ratio,
            'drifted_features': [] if drift_status == 'normal' else ['data_freshness']
        }

    except Exception as e:
        logger.error(f"Failed to get ML health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# FUND MANAGEMENT ENDPOINTS (Proxy to Java strategy-service)
# ============================================================================

import requests as http_requests

STRATEGY_SERVICE_URL = os.getenv('STRATEGY_SERVICE_URL', 'http://localhost:8081')


class FundStatus(BaseModel):
    """Fund operational status from Java service."""
    fund_id: str
    fund_type: str
    is_active: bool
    capital_usd: float
    position_count: int
    pending_signals: int
    last_trade_at: Optional[datetime]
    daily_trades: int
    daily_notional_usd: float
    error_message: Optional[str]


class FundActivateRequest(BaseModel):
    """Request to activate a fund."""
    fund_type: str
    capital_usd: float = 10000.0


class FundActivateResponse(BaseModel):
    """Response after activating a fund."""
    success: bool
    fund_type: str
    message: str


@app.get("/api/fund/status")
async def get_fund_operational_status(fund_type: str = Query(default="PSI-10")):
    """
    Get operational status of a fund from the Java strategy service.

    Returns real-time status including active positions, pending signals, etc.
    """
    try:
        # Try to fetch from Java strategy-service
        response = http_requests.get(
            f"{STRATEGY_SERVICE_URL}/api/strategy/fund/status",
            params={'fundType': fund_type},
            timeout=5
        )

        if response.ok:
            data = response.json()
            return {
                'fund_type': fund_type,
                'source': 'strategy_service',
                'status': data
            }

        # Fallback to database if service unavailable
        return await _get_fund_status_from_db(fund_type)

    except http_requests.exceptions.RequestException:
        # Strategy service not available, return DB status
        return await _get_fund_status_from_db(fund_type)
    except Exception as e:
        logger.error(f"Failed to get fund status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _get_fund_status_from_db(fund_type: str) -> dict:
    """Get fund status from database when strategy service is unavailable."""
    try:
        client = get_clickhouse_client()

        # Get fund summary
        result = client.query("""
            SELECT
                fund_type,
                status,
                total_aum,
                nav_per_share,
                num_depositors
            FROM polybot.aware_fund_summary FINAL
            WHERE fund_type = %(fund_type)s
        """, parameters={'fund_type': fund_type})

        if result.result_rows:
            row = result.result_rows[0]
            return {
                'fund_type': row[0],
                'source': 'database',
                'status': {
                    'is_active': row[1] == 'active',
                    'total_aum': float(row[2]),
                    'nav_per_share': float(row[3]),
                    'num_depositors': int(row[4]),
                    'strategy_service': 'unavailable'
                }
            }

        return {
            'fund_type': fund_type,
            'source': 'database',
            'status': {
                'is_active': False,
                'message': 'Fund not found'
            }
        }

    except Exception as e:
        logger.error(f"Failed to get fund status from DB: {e}")
        return {
            'fund_type': fund_type,
            'source': 'error',
            'status': {'error': str(e)}
        }


@app.post("/api/fund/activate")
async def activate_fund(request: FundActivateRequest):
    """
    Activate a fund in the Java strategy service.

    This starts the fund's trading logic (paper trading by default).
    """
    try:
        response = http_requests.post(
            f"{STRATEGY_SERVICE_URL}/api/strategy/fund/activate",
            json={
                'fundType': request.fund_type,
                'capitalUsd': request.capital_usd
            },
            timeout=10
        )

        if response.ok:
            data = response.json()
            return FundActivateResponse(
                success=True,
                fund_type=request.fund_type,
                message=data.get('message', 'Fund activated successfully')
            )

        return FundActivateResponse(
            success=False,
            fund_type=request.fund_type,
            message=f"Strategy service returned: {response.status_code}"
        )

    except http_requests.exceptions.RequestException as e:
        return FundActivateResponse(
            success=False,
            fund_type=request.fund_type,
            message=f"Strategy service unavailable: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to activate fund: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/fund/pause")
async def pause_fund(fund_type: str = Query(...)):
    """
    Pause trading for a fund.

    The fund will stop taking new positions but will manage existing ones.
    """
    try:
        response = http_requests.post(
            f"{STRATEGY_SERVICE_URL}/api/strategy/fund/pause",
            params={'fundType': fund_type},
            timeout=10
        )

        if response.ok:
            return {
                'success': True,
                'fund_type': fund_type,
                'message': 'Fund paused successfully'
            }

        return {
            'success': False,
            'fund_type': fund_type,
            'message': f"Strategy service returned: {response.status_code}"
        }

    except http_requests.exceptions.RequestException as e:
        return {
            'success': False,
            'fund_type': fund_type,
            'message': f"Strategy service unavailable: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Failed to pause fund: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/fund/metrics")
async def get_fund_metrics(fund_type: str = Query(default="PSI-10")):
    """
    Get Prometheus-style metrics for a fund.

    Returns metrics suitable for monitoring dashboards.
    """
    try:
        client = get_clickhouse_client()

        # Get fund metrics from multiple sources
        metrics = {}

        # NAV metrics
        nav_result = client.query("""
            SELECT nav_per_share, total_fund_value, total_pnl, num_positions
            FROM polybot.v_fund_nav_latest
            WHERE fund_type = %(fund_type)s
        """, parameters={'fund_type': fund_type})

        if nav_result.result_rows:
            row = nav_result.result_rows[0]
            metrics['aware_fund_nav_per_share'] = float(row[0])
            metrics['aware_fund_total_value_usd'] = float(row[1])
            metrics['aware_fund_total_pnl_usd'] = float(row[2])
            metrics['aware_fund_position_count'] = int(row[3])

        # Trade metrics (24h)
        trade_result = client.query("""
            SELECT
                count() as trade_count,
                sum(notional_usd) as total_notional
            FROM polybot.aware_fund_trades
            WHERE fund_id = %(fund_type)s
              AND ts >= now() - INTERVAL 24 HOUR
        """, parameters={'fund_type': fund_type})

        if trade_result.result_rows:
            row = trade_result.result_rows[0]
            metrics['aware_fund_trades_24h'] = int(row[0])
            metrics['aware_fund_volume_24h_usd'] = float(row[1] or 0)

        # Execution metrics
        exec_result = client.query("""
            SELECT count() as signal_count
            FROM polybot.aware_fund_executions
            WHERE fund_id = %(fund_type)s
              AND executed_at >= now() - INTERVAL 24 HOUR
        """, parameters={'fund_type': fund_type})

        if exec_result.result_rows:
            metrics['aware_fund_signals_24h'] = int(exec_result.result_rows[0][0])

        return {
            'fund_type': fund_type,
            'timestamp': datetime.utcnow().isoformat(),
            'metrics': metrics
        }

    except Exception as e:
        logger.error(f"Failed to get fund metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/fund/nav-history")
async def get_fund_nav_history(
    fund_type: str = Query(default="PSI-10"),
    days: int = Query(default=30, ge=1, le=365)
):
    """
    Get NAV history for a fund.

    Returns time series data for charting NAV over time.
    """
    try:
        client = get_clickhouse_client()

        result = client.query(f"""
            SELECT
                calculated_at,
                nav_per_share,
                total_fund_value,
                total_pnl,
                daily_return_pct
            FROM polybot.aware_fund_nav
            WHERE fund_type = %(fund_type)s
              AND calculated_at >= now() - INTERVAL {days} DAY
            ORDER BY calculated_at ASC
        """, parameters={'fund_type': fund_type})

        data_points = []
        for row in result.result_rows:
            data_points.append({
                'timestamp': row[0].isoformat() if row[0] else None,
                'nav_per_share': float(row[1]),
                'total_aum': float(row[2]),
                'daily_return': float(row[4]) if row[4] else 0
            })

        return {
            'fund_type': fund_type,
            'days': days,
            'data_points': data_points
        }

    except Exception as e:
        logger.error(f"Failed to get NAV history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ML MODEL ENDPOINTS
# ============================================================================


class TraderEnrichmentFull(BaseModel):
    """Extended trader enrichment with ML scores."""
    proxy_address: str
    username: str
    # ML Enrichment
    cluster_id: int
    strategy_cluster: str
    cluster_description: str
    is_anomaly: bool
    anomaly_score: float
    anomaly_type: str
    # ML Scores
    ml_score: float
    ml_tier: str
    tier_confidence: float
    predicted_sharpe: float
    sharpe_lower: Optional[float] = None
    sharpe_upper: Optional[float] = None
    # Profile
    total_volume: float
    total_pnl: float
    updated_at: Optional[datetime] = None


class FeatureImportance(BaseModel):
    """Feature importance entry."""
    name: str
    importance: float
    rank: int


class TierBoundary(BaseModel):
    """Tier boundary definition."""
    tier: str
    min_score: float
    max_score: float
    description: str


class ModelInfo(BaseModel):
    """ML model metadata."""
    model_version: str
    trained_at: Optional[datetime] = None
    n_traders_trained: int
    tier_accuracy: float
    sharpe_mae: float
    top_features: list[dict]
    tier_boundaries: list[dict]


class DriftedFeature(BaseModel):
    """Drifted feature info."""
    name: str
    severity: str
    ks_stat: float


class DriftStatus(BaseModel):
    """Current drift monitoring status."""
    status: str
    drift_ratio: float
    n_drifted_features: int
    n_total_features: int
    drifted_features: list[dict]
    last_checked: Optional[datetime] = None
    baseline_date: Optional[str] = None
    retrain_recommended: bool


@app.get("/api/traders/{address}/enrichment", response_model=TraderEnrichmentFull)
@limiter.limit("60/minute")
async def get_trader_enrichment_full(request: Request, address: str):
    """
    Get complete ML enrichment for a trader.

    Includes clustering, anomaly detection, and ML scores.
    """
    try:
        client = get_clickhouse_client()

        result = client.query("""
            SELECT
                ml.proxy_address, ml.username,
                ml.cluster_id, ml.strategy_cluster, ml.cluster_description,
                ml.is_anomaly, ml.anomaly_score, ml.anomaly_type,
                s.ml_score, s.ml_tier, s.tier_confidence,
                s.predicted_sharpe_30d,
                p.total_volume_usd, p.total_pnl,
                ml.updated_at
            FROM (SELECT * FROM polybot.aware_ml_enrichment FINAL) AS ml
            LEFT JOIN (SELECT * FROM polybot.aware_ml_scores FINAL) AS s
                ON ml.proxy_address = s.proxy_address
            LEFT JOIN (SELECT * FROM polybot.aware_trader_profiles FINAL) AS p
                ON ml.proxy_address = p.proxy_address
            WHERE lower(ml.proxy_address) = lower(%(addr)s)
               OR lower(ml.username) = lower(%(addr)s)
            LIMIT 1
        """, parameters={'addr': address})

        if not result.result_rows:
            raise HTTPException(404, "Trader enrichment not found")

        row = result.result_rows[0]
        return TraderEnrichmentFull(
            proxy_address=row[0],
            username=row[1] or '',
            cluster_id=int(row[2]) if row[2] is not None else 0,
            strategy_cluster=row[3] or 'UNKNOWN',
            cluster_description=row[4] or '',
            is_anomaly=bool(row[5]) if row[5] is not None else False,
            anomaly_score=float(row[6]) if row[6] else 0.0,
            anomaly_type=row[7] or '',
            ml_score=float(row[8]) if row[8] else 0.0,
            ml_tier=row[9] or 'UNKNOWN',
            tier_confidence=float(row[10]) if row[10] else 0.0,
            predicted_sharpe=float(row[11]) if row[11] else 0.0,
            total_volume=float(row[12]) if row[12] else 0.0,
            total_pnl=float(row[13]) if row[13] else 0.0,
            updated_at=row[14]
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get trader enrichment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models/ensemble/info", response_model=ModelInfo)
@limiter.limit("30/minute")
async def get_model_info(request: Request):
    """
    Get current ML model metadata and feature importance.

    Returns model version, training date, accuracy metrics, and top features.
    """
    try:
        client = get_clickhouse_client()

        # Get latest training run
        training_result = client.query("""
            SELECT model_version, completed_at, n_traders,
                   tier_accuracy, sharpe_mae
            FROM polybot.aware_ml_training_runs
            WHERE status = 'success'
            ORDER BY completed_at DESC
            LIMIT 1
        """)

        # Get feature importance
        importance_result = client.query("""
            SELECT feature_name, importance_score, importance_rank
            FROM polybot.aware_ml_feature_importance FINAL
            ORDER BY importance_rank
            LIMIT 15
        """)

        # Get tier boundaries
        tier_result = client.query("""
            SELECT tier_name, score_min, score_max, description
            FROM polybot.aware_ml_tier_boundaries FINAL
            ORDER BY score_min
        """)

        training = training_result.result_rows[0] if training_result.result_rows else None

        return ModelInfo(
            model_version=training[0] if training else 'unknown',
            trained_at=training[1] if training else None,
            n_traders_trained=int(training[2]) if training and training[2] else 0,
            tier_accuracy=float(training[3]) if training and training[3] else 0.0,
            sharpe_mae=float(training[4]) if training and training[4] else 0.0,
            top_features=[
                {'name': r[0], 'importance': float(r[1]), 'rank': int(r[2])}
                for r in importance_result.result_rows
            ],
            tier_boundaries=[
                {'tier': r[0], 'min': float(r[1]), 'max': float(r[2]), 'desc': r[3]}
                for r in tier_result.result_rows
            ]
        )

    except Exception as e:
        logger.error(f"Failed to get model info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models/drift-status", response_model=DriftStatus)
@limiter.limit("30/minute")
async def get_drift_status(request: Request):
    """
    Get current drift monitoring status.

    Shows if model features are drifting from training distribution
    and whether retraining is recommended.
    """
    try:
        import json
        from pathlib import Path

        # Load latest drift report from file
        # Check multiple locations (Docker mount vs local dev)
        possible_paths = [
            Path("/app/ml/checkpoints/latest_drift_report.json"),  # Docker
            Path(__file__).parent.parent / "analytics" / "ml" / "checkpoints" / "latest_drift_report.json",  # Local dev
            Path("ml/checkpoints/latest_drift_report.json"),  # Relative
        ]
        drift_path = None
        for p in possible_paths:
            if p.exists():
                drift_path = p
                break

        if drift_path is None:
            return DriftStatus(
                status='unknown',
                drift_ratio=0.0,
                n_drifted_features=0,
                n_total_features=35,
                drifted_features=[],
                last_checked=None,
                baseline_date=None,
                retrain_recommended=False
            )

        with open(drift_path) as f:
            report = json.load(f)

        return DriftStatus(
            status=report.get('alert_level', 'unknown'),
            drift_ratio=report.get('drift_ratio', 0.0),
            n_drifted_features=report.get('n_drifted', 0),
            n_total_features=report.get('n_features', 35),
            drifted_features=[
                {'name': f['feature'], 'severity': f['severity'], 'ks_stat': f['ks_statistic']}
                for f in report.get('drifted_features', [])
            ],
            last_checked=datetime.fromisoformat(report['checked_at']) if 'checked_at' in report else None,
            baseline_date=report.get('baseline_date'),
            retrain_recommended=report.get('drift_ratio', 0) >= 0.3
        )

    except Exception as e:
        logger.error(f"Failed to get drift status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models/training-history")
@limiter.limit("30/minute")
async def get_training_history(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50)
):
    """
    Get recent model training runs.

    Shows history of training runs with metrics and status.
    """
    try:
        client = get_clickhouse_client()

        result = client.query(f"""
            SELECT
                toString(run_id) as run_id,
                model_version,
                started_at,
                completed_at,
                duration_seconds,
                status,
                n_traders,
                tier_accuracy,
                sharpe_mae,
                trigger_reason
            FROM polybot.aware_ml_training_runs
            ORDER BY started_at DESC
            LIMIT {limit}
        """)

        return {
            'count': len(result.result_rows),
            'runs': [
                {
                    'run_id': row[0],
                    'model_version': row[1],
                    'started_at': row[2].isoformat() if row[2] else None,
                    'completed_at': row[3].isoformat() if row[3] else None,
                    'duration_seconds': int(row[4]) if row[4] else 0,
                    'status': row[5],
                    'n_traders': int(row[6]) if row[6] else 0,
                    'tier_accuracy': float(row[7]) if row[7] else 0.0,
                    'sharpe_mae': float(row[8]) if row[8] else 0.0,
                    'trigger_reason': row[9]
                }
                for row in result.result_rows
            ]
        }

    except Exception as e:
        logger.error(f"Failed to get training history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models/feature-importance")
@limiter.limit("30/minute")
async def get_feature_importance(
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    importance_type: str = Query(default="weight")
):
    """
    Get feature importance rankings from the ML model.

    Returns top features ranked by importance score.
    """
    try:
        client = get_clickhouse_client()

        result = client.query(f"""
            SELECT
                feature_name,
                importance_score,
                importance_rank,
                model_version,
                importance_type
            FROM polybot.aware_ml_feature_importance FINAL
            WHERE importance_type = %(imp_type)s
            ORDER BY importance_rank
            LIMIT {limit}
        """, parameters={'imp_type': importance_type})

        return {
            'importance_type': importance_type,
            'count': len(result.result_rows),
            'features': [
                {
                    'rank': int(row[2]),
                    'name': row[0],
                    'importance': float(row[1]),
                    'model_version': row[3]
                }
                for row in result.result_rows
            ]
        }

    except Exception as e:
        logger.error(f"Failed to get feature importance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ml/tier-distribution")
@limiter.limit("60/minute")
async def get_tier_distribution(request: Request):
    """
    Get distribution of traders across ML tiers.

    Shows how many traders are in each tier (BRONZE, SILVER, GOLD, DIAMOND).
    """
    try:
        client = get_clickhouse_client()

        result = client.query("""
            SELECT
                ml_tier,
                count() as trader_count,
                avg(ml_score) as avg_score,
                avg(predicted_sharpe_30d) as avg_sharpe
            FROM polybot.aware_ml_scores FINAL
            WHERE ml_tier != ''
            GROUP BY ml_tier
            ORDER BY
                CASE ml_tier
                    WHEN 'DIAMOND' THEN 1
                    WHEN 'GOLD' THEN 2
                    WHEN 'SILVER' THEN 3
                    WHEN 'BRONZE' THEN 4
                    ELSE 5
                END
        """)

        tiers = []
        total = 0
        for row in result.result_rows:
            count = int(row[1])
            total += count
            tiers.append({
                'tier': row[0],
                'count': count,
                'avg_score': round(float(row[2]) if row[2] else 0, 2),
                'avg_sharpe': round(float(row[3]) if row[3] else 0, 3)
            })

        # Add percentages
        for tier in tiers:
            tier['percentage'] = round(tier['count'] / total * 100, 1) if total > 0 else 0

        return {
            'total_traders': total,
            'tiers': tiers
        }

    except Exception as e:
        logger.error(f"Failed to get tier distribution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Entry point"""
    host = os.getenv('API_HOST', '0.0.0.0')
    port = int(os.getenv('API_PORT', '8000'))

    logger.info("=" * 60)
    logger.info("  AWARE API - Starting")
    logger.info("=" * 60)
    logger.info(f"  Host: {host}:{port}")
    logger.info("=" * 60)

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
