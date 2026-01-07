"""
AWARE API - User Investment Module (Custodial MVP)

Handles user deposits, withdrawals, and portfolio management.
This is a custodial model where AWARE tracks ownership in the database.

Endpoints:
    POST /api/invest/deposit     - Deposit USDC into a fund
    POST /api/invest/withdraw    - Withdraw from a fund
    GET  /api/invest/portfolio   - Get user's portfolio across all funds
    GET  /api/invest/transactions - Get user's transaction history
    GET  /api/funds              - List all available funds
    GET  /api/funds/{fund_type}  - Get detailed fund info

Migration Path:
    This module will be replaced by smart contract interactions in V1.
    The database schema and share calculations remain the same.
"""

import os
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends, Query

import clickhouse_connect

# Create router
router = APIRouter(prefix="/api/invest", tags=["investments"])
funds_router = APIRouter(prefix="/api/funds", tags=["funds"])


# ============================================================================
# MODELS
# ============================================================================

class DepositRequest(BaseModel):
    """Request to deposit USDC into a fund."""
    wallet_address: str = Field(..., description="User's wallet address")
    fund_type: str = Field(..., description="Fund to deposit into (e.g., PSI-10)")
    usdc_amount: Decimal = Field(..., gt=0, description="Amount of USDC to deposit")
    tx_hash: Optional[str] = Field(None, description="On-chain transaction hash")


class DepositResponse(BaseModel):
    """Response after processing a deposit."""
    tx_id: str
    fund_type: str
    usdc_amount: Decimal
    shares_received: Decimal
    nav_per_share: Decimal
    new_share_balance: Decimal
    status: str


class WithdrawRequest(BaseModel):
    """Request to withdraw from a fund."""
    wallet_address: str
    fund_type: str
    shares_amount: Optional[Decimal] = Field(None, description="Shares to redeem (or use usdc_amount)")
    usdc_amount: Optional[Decimal] = Field(None, description="USDC to withdraw (or use shares_amount)")
    withdraw_all: bool = Field(False, description="Withdraw entire balance")


class WithdrawResponse(BaseModel):
    """Response after processing a withdrawal."""
    request_id: str
    fund_type: str
    shares_redeemed: Decimal
    usdc_amount: Decimal
    nav_per_share: Decimal
    remaining_shares: Decimal
    status: str
    estimated_arrival: datetime


class UserHolding(BaseModel):
    """User's holding in a single fund."""
    fund_type: str
    shares_balance: Decimal
    current_value_usdc: Decimal
    cost_basis_usdc: Decimal
    pnl_usdc: Decimal
    pnl_pct: float
    nav_per_share: Decimal


class PortfolioResponse(BaseModel):
    """User's complete portfolio."""
    wallet_address: str
    total_value_usdc: Decimal
    total_cost_basis: Decimal
    total_pnl_usdc: Decimal
    total_pnl_pct: float
    holdings: List[UserHolding]


class FundInfo(BaseModel):
    """Public information about a fund."""
    fund_type: str
    status: str
    description: str
    total_aum: Decimal
    nav_per_share: Decimal
    num_depositors: int
    return_24h_pct: float
    return_7d_pct: float
    return_30d_pct: float
    return_inception_pct: float
    sharpe_ratio: float
    management_fee_pct: float
    performance_fee_pct: float
    min_deposit_usdc: Decimal
    inception_date: str


class TransactionRecord(BaseModel):
    """A single transaction record."""
    tx_id: str
    fund_type: str
    tx_type: str
    usdc_amount: Decimal
    shares_amount: Decimal
    nav_per_share: Decimal
    status: str
    created_at: datetime


# ============================================================================
# DATABASE
# ============================================================================

def get_client():
    """Get ClickHouse client."""
    return clickhouse_connect.get_client(
        host=os.getenv('CLICKHOUSE_HOST', 'localhost'),
        port=int(os.getenv('CLICKHOUSE_PORT', '8123')),
        database='polybot'
    )


def get_current_nav(client, fund_type: str) -> Decimal:
    """Get current NAV per share for a fund."""
    result = client.query(f"""
        SELECT nav_per_share
        FROM polybot.aware_fund_summary FINAL
        WHERE fund_type = '{fund_type}'
    """)
    if result.result_rows:
        return Decimal(str(result.result_rows[0][0]))
    return Decimal('1.0')  # Default NAV for new funds


def get_user_shares(client, wallet_address: str, fund_type: str) -> tuple[Decimal, Decimal]:
    """Get user's current share balance and cost basis."""
    result = client.query(f"""
        SELECT shares_balance, cost_basis_usdc
        FROM polybot.aware_user_shares FINAL
        WHERE wallet_address = '{wallet_address}'
          AND fund_type = '{fund_type}'
    """)
    if result.result_rows:
        return (
            Decimal(str(result.result_rows[0][0])),
            Decimal(str(result.result_rows[0][1]))
        )
    return Decimal('0'), Decimal('0')


def ensure_user_exists(client, wallet_address: str) -> str:
    """Ensure user exists, create if not. Returns user_id."""
    result = client.query(f"""
        SELECT user_id
        FROM polybot.aware_users FINAL
        WHERE wallet_address = '{wallet_address}'
    """)
    if result.result_rows:
        return str(result.result_rows[0][0])

    # Create new user
    user_id = str(uuid.uuid4())
    client.command(f"""
        INSERT INTO polybot.aware_users (user_id, wallet_address)
        VALUES ('{user_id}', '{wallet_address}')
    """)
    return user_id


# ============================================================================
# DEPOSIT ENDPOINT
# ============================================================================

@router.post("/deposit", response_model=DepositResponse)
async def deposit(request: DepositRequest):
    """
    Deposit USDC into a fund.

    Flow:
    1. Verify fund exists and is active
    2. Calculate shares based on current NAV
    3. Record transaction
    4. Update user's share balance
    5. Update fund totals

    Note: In MVP, we trust the tx_hash. In V1, we verify on-chain.
    """
    client = get_client()

    # Validate fund
    fund_result = client.query(f"""
        SELECT status, min_deposit_usdc, nav_per_share
        FROM polybot.aware_fund_summary FINAL
        WHERE fund_type = '{request.fund_type}'
    """)

    if not fund_result.result_rows:
        raise HTTPException(404, f"Fund not found: {request.fund_type}")

    status, min_deposit, nav = fund_result.result_rows[0]
    nav = Decimal(str(nav))

    if status != 'active':
        raise HTTPException(400, f"Fund is not accepting deposits: {status}")

    if request.usdc_amount < Decimal(str(min_deposit)):
        raise HTTPException(400, f"Minimum deposit is ${min_deposit}")

    # Ensure user exists
    user_id = ensure_user_exists(client, request.wallet_address)

    # Calculate shares
    shares = request.usdc_amount / nav

    # Get current balance
    current_shares, current_cost = get_user_shares(
        client, request.wallet_address, request.fund_type
    )

    new_shares = current_shares + shares
    new_cost = current_cost + request.usdc_amount

    # Record transaction
    tx_id = str(uuid.uuid4())
    client.command(f"""
        INSERT INTO polybot.aware_user_transactions
        (tx_id, user_id, wallet_address, fund_type, tx_type,
         usdc_amount, shares_amount, nav_per_share, status, tx_hash)
        VALUES
        ('{tx_id}', '{user_id}', '{request.wallet_address}', '{request.fund_type}',
         'DEPOSIT', {request.usdc_amount}, {shares}, {nav},
         'confirmed', {f"'{request.tx_hash}'" if request.tx_hash else 'NULL'})
    """)

    # Update share balance
    client.command(f"""
        INSERT INTO polybot.aware_user_shares
        (user_id, wallet_address, fund_type, shares_balance, cost_basis_usdc,
         first_deposit_at, last_activity_at)
        VALUES
        ('{user_id}', '{request.wallet_address}', '{request.fund_type}',
         {new_shares}, {new_cost}, now64(3), now64(3))
    """)

    # Update fund summary
    client.command(f"""
        INSERT INTO polybot.aware_fund_summary
        (fund_type, total_aum, total_shares, nav_per_share, num_depositors)
        SELECT
            '{request.fund_type}',
            total_aum + {request.usdc_amount},
            total_shares + {shares},
            nav_per_share,
            num_depositors + if({current_shares} = 0, 1, 0)
        FROM polybot.aware_fund_summary FINAL
        WHERE fund_type = '{request.fund_type}'
    """)

    return DepositResponse(
        tx_id=tx_id,
        fund_type=request.fund_type,
        usdc_amount=request.usdc_amount,
        shares_received=shares,
        nav_per_share=nav,
        new_share_balance=new_shares,
        status="confirmed"
    )


# ============================================================================
# WITHDRAW ENDPOINT
# ============================================================================

@router.post("/withdraw", response_model=WithdrawResponse)
async def withdraw(request: WithdrawRequest):
    """
    Withdraw from a fund.

    Flow:
    1. Verify user has sufficient shares
    2. Calculate USDC based on current NAV
    3. Create withdrawal request
    4. Update user's share balance
    5. Queue for processing

    Note: Withdrawals may have a delay for liquidity management.
    """
    client = get_client()

    # Get current holdings
    current_shares, current_cost = get_user_shares(
        client, request.wallet_address, request.fund_type
    )

    if current_shares <= 0:
        raise HTTPException(400, "No shares to withdraw")

    # Get current NAV
    nav = get_current_nav(client, request.fund_type)

    # Calculate shares to redeem
    if request.withdraw_all:
        shares_to_redeem = current_shares
    elif request.shares_amount:
        shares_to_redeem = request.shares_amount
    elif request.usdc_amount:
        shares_to_redeem = request.usdc_amount / nav
    else:
        raise HTTPException(400, "Specify shares_amount, usdc_amount, or withdraw_all")

    if shares_to_redeem > current_shares:
        raise HTTPException(400, f"Insufficient shares. Have: {current_shares}, Want: {shares_to_redeem}")

    # Calculate USDC
    usdc_amount = shares_to_redeem * nav

    # Calculate new balances
    new_shares = current_shares - shares_to_redeem
    # Proportionally reduce cost basis
    cost_reduction = current_cost * (shares_to_redeem / current_shares) if current_shares > 0 else Decimal('0')
    new_cost = current_cost - cost_reduction

    # Get user_id
    user_result = client.query(f"""
        SELECT user_id FROM polybot.aware_users FINAL
        WHERE wallet_address = '{request.wallet_address}'
    """)
    user_id = str(user_result.result_rows[0][0]) if user_result.result_rows else str(uuid.uuid4())

    # Create withdrawal request
    request_id = str(uuid.uuid4())
    tx_id = str(uuid.uuid4())

    # Record transaction (pending)
    client.command(f"""
        INSERT INTO polybot.aware_user_transactions
        (tx_id, user_id, wallet_address, fund_type, tx_type,
         usdc_amount, shares_amount, nav_per_share, status)
        VALUES
        ('{tx_id}', '{user_id}', '{request.wallet_address}', '{request.fund_type}',
         'WITHDRAW', {usdc_amount}, {shares_to_redeem}, {nav}, 'pending')
    """)

    # Create withdrawal request (for processing queue)
    client.command(f"""
        INSERT INTO polybot.aware_withdrawal_requests
        (request_id, user_id, wallet_address, fund_type,
         shares_amount, estimated_usdc, nav_at_request, status, process_after)
        VALUES
        ('{request_id}', '{user_id}', '{request.wallet_address}', '{request.fund_type}',
         {shares_to_redeem}, {usdc_amount}, {nav}, 'pending',
         now64(3) + INTERVAL 1 HOUR)
    """)

    # Update share balance (immediately deduct shares)
    client.command(f"""
        INSERT INTO polybot.aware_user_shares
        (user_id, wallet_address, fund_type, shares_balance, cost_basis_usdc,
         first_deposit_at, last_activity_at)
        VALUES
        ('{user_id}', '{request.wallet_address}', '{request.fund_type}',
         {new_shares}, {new_cost}, now64(3), now64(3))
    """)

    # Update fund summary
    client.command(f"""
        INSERT INTO polybot.aware_fund_summary
        (fund_type, total_aum, total_shares, nav_per_share, num_depositors)
        SELECT
            '{request.fund_type}',
            total_aum - {usdc_amount},
            total_shares - {shares_to_redeem},
            nav_per_share,
            num_depositors - if({new_shares} = 0, 1, 0)
        FROM polybot.aware_fund_summary FINAL
        WHERE fund_type = '{request.fund_type}'
    """)

    return WithdrawResponse(
        request_id=request_id,
        fund_type=request.fund_type,
        shares_redeemed=shares_to_redeem,
        usdc_amount=usdc_amount,
        nav_per_share=nav,
        remaining_shares=new_shares,
        status="pending",
        estimated_arrival=datetime.utcnow()  # In MVP, process immediately
    )


# ============================================================================
# PORTFOLIO ENDPOINT
# ============================================================================

@router.get("/portfolio", response_model=PortfolioResponse)
async def get_portfolio(wallet_address: str = Query(..., description="User's wallet address")):
    """
    Get user's complete portfolio across all funds.
    """
    client = get_client()

    # Get all user holdings
    result = client.query(f"""
        SELECT
            s.fund_type,
            s.shares_balance,
            s.cost_basis_usdc,
            f.nav_per_share
        FROM polybot.aware_user_shares FINAL s
        LEFT JOIN polybot.aware_fund_summary FINAL f ON s.fund_type = f.fund_type
        WHERE s.wallet_address = '{wallet_address}'
          AND s.shares_balance > 0
    """)

    holdings = []
    total_value = Decimal('0')
    total_cost = Decimal('0')

    for row in result.result_rows:
        fund_type, shares, cost_basis, nav = row
        shares = Decimal(str(shares))
        cost_basis = Decimal(str(cost_basis))
        nav = Decimal(str(nav)) if nav else Decimal('1.0')

        current_value = shares * nav
        pnl = current_value - cost_basis
        pnl_pct = float(pnl / cost_basis * 100) if cost_basis > 0 else 0.0

        holdings.append(UserHolding(
            fund_type=fund_type,
            shares_balance=shares,
            current_value_usdc=current_value,
            cost_basis_usdc=cost_basis,
            pnl_usdc=pnl,
            pnl_pct=pnl_pct,
            nav_per_share=nav
        ))

        total_value += current_value
        total_cost += cost_basis

    total_pnl = total_value - total_cost
    total_pnl_pct = float(total_pnl / total_cost * 100) if total_cost > 0 else 0.0

    return PortfolioResponse(
        wallet_address=wallet_address,
        total_value_usdc=total_value,
        total_cost_basis=total_cost,
        total_pnl_usdc=total_pnl,
        total_pnl_pct=total_pnl_pct,
        holdings=holdings
    )


# ============================================================================
# TRANSACTION HISTORY
# ============================================================================

@router.get("/transactions", response_model=List[TransactionRecord])
async def get_transactions(
    wallet_address: str = Query(...),
    fund_type: Optional[str] = Query(None),
    limit: int = Query(50, le=500)
):
    """Get user's transaction history."""
    client = get_client()

    fund_filter = f"AND fund_type = '{fund_type}'" if fund_type else ""

    result = client.query(f"""
        SELECT tx_id, fund_type, tx_type, usdc_amount, shares_amount,
               nav_per_share, status, created_at
        FROM polybot.aware_user_transactions
        WHERE wallet_address = '{wallet_address}'
        {fund_filter}
        ORDER BY created_at DESC
        LIMIT {limit}
    """)

    return [
        TransactionRecord(
            tx_id=str(row[0]),
            fund_type=row[1],
            tx_type=row[2],
            usdc_amount=Decimal(str(row[3])),
            shares_amount=Decimal(str(row[4])),
            nav_per_share=Decimal(str(row[5])),
            status=row[6],
            created_at=row[7]
        )
        for row in result.result_rows
    ]


# ============================================================================
# FUND LISTING
# ============================================================================

@funds_router.get("", response_model=List[FundInfo])
async def list_funds(status: str = Query("active")):
    """List all available funds."""
    client = get_client()

    result = client.query(f"""
        SELECT
            fund_type, status, description, total_aum, nav_per_share,
            num_depositors, return_24h_pct, return_7d_pct, return_30d_pct,
            return_inception_pct, sharpe_ratio, management_fee_pct,
            performance_fee_pct, min_deposit_usdc, inception_date
        FROM polybot.aware_fund_summary FINAL
        WHERE status = '{status}'
        ORDER BY total_aum DESC
    """)

    return [
        FundInfo(
            fund_type=row[0],
            status=row[1],
            description=row[2] or "",
            total_aum=Decimal(str(row[3])),
            nav_per_share=Decimal(str(row[4])),
            num_depositors=int(row[5]),
            return_24h_pct=float(row[6] or 0),
            return_7d_pct=float(row[7] or 0),
            return_30d_pct=float(row[8] or 0),
            return_inception_pct=float(row[9] or 0),
            sharpe_ratio=float(row[10] or 0),
            management_fee_pct=float(row[11] or 0),
            performance_fee_pct=float(row[12] or 0),
            min_deposit_usdc=Decimal(str(row[13])),
            inception_date=str(row[14])
        )
        for row in result.result_rows
    ]


# ============================================================================
# FUND COMPARISON (must be before /{fund_type} route)
# ============================================================================

class FundComparison(BaseModel):
    """Comparison of multiple funds."""
    funds: List[FundInfo]
    best_24h_return: str
    best_sharpe: str
    largest_aum: str


@funds_router.get("/compare", response_model=FundComparison)
async def compare_funds(
    fund_types: str = Query(..., description="Comma-separated fund types to compare")
):
    """
    Compare multiple funds side by side.

    Example: /api/funds/compare?fund_types=PSI-10,ALPHA-INSIDER,ALPHA-EDGE
    """
    client = get_client()

    funds_list = [f.strip() for f in fund_types.split(",")]
    funds_str = ",".join(f"'{f}'" for f in funds_list)

    result = client.query(f"""
        SELECT
            fund_type, status, description, total_aum, nav_per_share,
            num_depositors, return_24h_pct, return_7d_pct, return_30d_pct,
            return_inception_pct, sharpe_ratio, management_fee_pct,
            performance_fee_pct, min_deposit_usdc, inception_date
        FROM polybot.aware_fund_summary FINAL
        WHERE fund_type IN ({funds_str})
    """)

    funds = []
    best_24h = ("", float('-inf'))
    best_sharpe = ("", float('-inf'))
    largest_aum = ("", Decimal('0'))

    for row in result.result_rows:
        fund = FundInfo(
            fund_type=row[0],
            status=row[1],
            description=row[2] or "",
            total_aum=Decimal(str(row[3])),
            nav_per_share=Decimal(str(row[4])),
            num_depositors=int(row[5]),
            return_24h_pct=float(row[6] or 0),
            return_7d_pct=float(row[7] or 0),
            return_30d_pct=float(row[8] or 0),
            return_inception_pct=float(row[9] or 0),
            sharpe_ratio=float(row[10] or 0),
            management_fee_pct=float(row[11] or 0),
            performance_fee_pct=float(row[12] or 0),
            min_deposit_usdc=Decimal(str(row[13])),
            inception_date=str(row[14])
        )
        funds.append(fund)

        if fund.return_24h_pct > best_24h[1]:
            best_24h = (fund.fund_type, fund.return_24h_pct)
        if fund.sharpe_ratio > best_sharpe[1]:
            best_sharpe = (fund.fund_type, fund.sharpe_ratio)
        if fund.total_aum > largest_aum[1]:
            largest_aum = (fund.fund_type, fund.total_aum)

    return FundComparison(
        funds=funds,
        best_24h_return=best_24h[0],
        best_sharpe=best_sharpe[0],
        largest_aum=largest_aum[0]
    )


@funds_router.get("/{fund_type}", response_model=FundInfo)
async def get_fund(fund_type: str):
    """Get detailed information about a specific fund."""
    client = get_client()

    result = client.query(f"""
        SELECT
            fund_type, status, description, total_aum, nav_per_share,
            num_depositors, return_24h_pct, return_7d_pct, return_30d_pct,
            return_inception_pct, sharpe_ratio, management_fee_pct,
            performance_fee_pct, min_deposit_usdc, inception_date
        FROM polybot.aware_fund_summary FINAL
        WHERE fund_type = '{fund_type}'
    """)

    if not result.result_rows:
        raise HTTPException(404, f"Fund not found: {fund_type}")

    row = result.result_rows[0]
    return FundInfo(
        fund_type=row[0],
        status=row[1],
        description=row[2] or "",
        total_aum=Decimal(str(row[3])),
        nav_per_share=Decimal(str(row[4])),
        num_depositors=int(row[5]),
        return_24h_pct=float(row[6] or 0),
        return_7d_pct=float(row[7] or 0),
        return_30d_pct=float(row[8] or 0),
        return_inception_pct=float(row[9] or 0),
        sharpe_ratio=float(row[10] or 0),
        management_fee_pct=float(row[11] or 0),
        performance_fee_pct=float(row[12] or 0),
        min_deposit_usdc=Decimal(str(row[13])),
        inception_date=str(row[14])
    )


# ============================================================================
# NAV HISTORY (for charting)
# ============================================================================

class NAVHistoryPoint(BaseModel):
    """A single NAV data point for charting."""
    timestamp: datetime
    nav_per_share: Decimal
    total_aum: Decimal
    daily_return_pct: float


@funds_router.get("/{fund_type}/nav-history", response_model=List[NAVHistoryPoint])
async def get_nav_history(
    fund_type: str,
    days: int = Query(30, ge=1, le=365, description="Number of days of history"),
    interval: str = Query("1h", description="Interval: 5m, 1h, 1d")
):
    """
    Get historical NAV data for a fund.

    Returns time-series data for charting fund performance.
    Intervals: 5m (5 minutes), 1h (hourly), 1d (daily)
    """
    client = get_client()

    # Map interval to ClickHouse function
    interval_map = {
        "5m": "toStartOfFiveMinutes",
        "1h": "toStartOfHour",
        "1d": "toStartOfDay"
    }

    time_fn = interval_map.get(interval, "toStartOfHour")

    result = client.query(f"""
        SELECT
            {time_fn}(calculated_at) as ts,
            argMax(nav_per_share, calculated_at) as nav,
            argMax(total_fund_value, calculated_at) as aum,
            argMax(daily_return_pct, calculated_at) as daily_ret
        FROM polybot.aware_fund_nav
        WHERE fund_type = '{fund_type}'
          AND calculated_at >= now() - INTERVAL {days} DAY
        GROUP BY ts
        ORDER BY ts ASC
    """)

    return [
        NAVHistoryPoint(
            timestamp=row[0],
            nav_per_share=Decimal(str(row[1])),
            total_aum=Decimal(str(row[2])),
            daily_return_pct=float(row[3] or 0)
        )
        for row in result.result_rows
    ]
