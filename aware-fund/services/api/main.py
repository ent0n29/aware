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

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

import clickhouse_connect

# Add analytics to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'analytics'))

# Configure logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('aware-api')

# Initialize FastAPI
app = FastAPI(
    title="AWARE FUND API",
    description="The Smart Money Index for Prediction Markets",
    version="1.0.0"
)

# Add CORS middleware
# Note: In production, replace "*" with specific allowed origins
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3002",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3002",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if os.getenv('ENV', 'development') == 'production' else ["*"],
    allow_credentials=False,  # Don't allow credentials with wildcard origins
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


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
async def get_leaderboard(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    tier: Optional[str] = Query(default=None),
    strategy: Optional[str] = Query(default=None)
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
                coalesce(p.total_trades, 0) AS total_trades
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
                total_trades=row[13] or 0
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
async def get_fund_nav(fund_id: str = Query(default="psi-10-main")):
    """
    Get current NAV (Net Asset Value) for a fund.

    Returns the fund's current value, positions, and P&L.
    """
    try:
        client = get_clickhouse_client()

        query = """
        SELECT
            fund_id,
            nav,
            capital,
            position_value,
            unrealized_pnl,
            realized_pnl,
            total_return,
            open_positions,
            ts
        FROM polybot.v_fund_nav_latest
        WHERE fund_id = %(fund_id)s
        LIMIT 1
        """

        result = client.query(query, parameters={'fund_id': fund_id})

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
        return FundNAV(
            fund_id=row[0],
            nav=float(row[1]),
            capital=float(row[2]),
            position_value=float(row[3]),
            unrealized_pnl=float(row[4]),
            realized_pnl=float(row[5]),
            total_return=float(row[6]),
            open_positions=int(row[7]),
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
async def get_insider_alerts(
    hours: int = Query(default=48, ge=1, le=168),
    min_confidence: float = Query(default=0.3, ge=0.0, le=1.0)
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
