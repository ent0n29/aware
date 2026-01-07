"""
NAV Calculator - Net Asset Value calculation for AWARE Funds.

Calculates NAV per share for each fund by:
1. Fetching fund cash balance (USDC holdings)
2. Valuing open positions at current market prices
3. Computing total_fund_value = cash + position_value
4. Computing nav_per_share = total_fund_value / total_shares

Runs as a scheduled job every 5 minutes.
"""

import os
import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import requests

from clickhouse_driver import Client

logger = logging.getLogger(__name__)

# Fund types we track
FUND_TYPES = [
    "PSI-10",
    "PSI-SPORTS",
    "PSI-CRYPTO",
    "PSI-POLITICS",
    "ALPHA-INSIDER",
    "ALPHA-EDGE",
    "ALPHA-ARB"
]


@dataclass
class FundValuation:
    """Represents a point-in-time valuation of a fund."""
    fund_type: str
    total_usdc_balance: Decimal
    total_position_value: Decimal
    total_fund_value: Decimal
    total_shares: Decimal
    nav_per_share: Decimal
    num_positions: int
    num_depositors: int
    total_pnl: Decimal
    calculated_at: datetime


class NAVCalculator:
    """
    Calculates Net Asset Value for all AWARE funds.

    NAV = (Cash + Position Value) / Total Shares Outstanding

    For MVP (custodial model), we track:
    - Cash: USDC balance per fund (from aware_user_transactions)
    - Positions: Open positions valued at current market prices
    - Shares: Total shares issued per fund (from aware_user_shares)
    """

    def __init__(self, clickhouse_client: Client, executor_api_url: str = None):
        self.client = clickhouse_client
        self.executor_api_url = executor_api_url or os.getenv(
            'EXECUTOR_API_URL', 'http://localhost:8080'
        )

    def calculate_all_funds(self) -> List[FundValuation]:
        """Calculate NAV for all funds and persist results."""
        valuations = []

        for fund_type in FUND_TYPES:
            try:
                valuation = self.calculate_fund_nav(fund_type)
                if valuation:
                    valuations.append(valuation)
                    self._persist_nav(valuation)
                    self._update_fund_summary(valuation)
            except Exception as e:
                logger.error(f"Failed to calculate NAV for {fund_type}: {e}")

        return valuations

    def calculate_fund_nav(self, fund_type: str) -> Optional[FundValuation]:
        """
        Calculate NAV for a single fund.

        NAV per share = Total Fund Value / Total Shares Outstanding

        If no shares exist yet, NAV defaults to $1.00 (initial offering price).
        """
        now = datetime.utcnow()

        # Get cash balance (net deposits - withdrawals)
        cash_balance = self._get_fund_cash_balance(fund_type)

        # Get position value
        position_value, num_positions = self._get_position_value(fund_type)

        # Total fund value
        total_value = cash_balance + position_value

        # Get total shares outstanding
        total_shares = self._get_total_shares(fund_type)

        # Calculate NAV per share
        if total_shares > Decimal('0'):
            nav_per_share = (total_value / total_shares).quantize(
                Decimal('0.00000001'), rounding=ROUND_HALF_UP
            )
        else:
            # No shares yet - use initial offering price
            nav_per_share = Decimal('1.00000000')

        # Get depositor count
        num_depositors = self._get_depositor_count(fund_type)

        # Calculate total P&L
        total_pnl = self._calculate_total_pnl(fund_type, total_value)

        valuation = FundValuation(
            fund_type=fund_type,
            total_usdc_balance=cash_balance,
            total_position_value=position_value,
            total_fund_value=total_value,
            total_shares=total_shares,
            nav_per_share=nav_per_share,
            num_positions=num_positions,
            num_depositors=num_depositors,
            total_pnl=total_pnl,
            calculated_at=now
        )

        logger.info(
            f"Fund {fund_type}: NAV=${nav_per_share:.4f}, "
            f"AUM=${total_value:.2f}, Shares={total_shares:.4f}, "
            f"Depositors={num_depositors}"
        )

        return valuation

    def _get_fund_cash_balance(self, fund_type: str) -> Decimal:
        """
        Get fund's current USDC balance.

        This is the sum of all confirmed deposits minus confirmed withdrawals.
        In a real system, this would also be reconciled against on-chain balances.
        """
        query = """
            SELECT
                coalesce(sum(
                    CASE
                        WHEN tx_type = 'DEPOSIT' THEN usdc_amount
                        WHEN tx_type = 'WITHDRAW' THEN -usdc_amount
                        WHEN tx_type = 'FEE' THEN -usdc_amount
                        ELSE 0
                    END
                ), 0) as net_balance
            FROM polybot.aware_user_transactions
            WHERE fund_type = %(fund_type)s
            AND status = 'confirmed'
        """

        result = self.client.execute(
            query,
            {'fund_type': fund_type}
        )

        if result and result[0]:
            return Decimal(str(result[0][0]))
        return Decimal('0')

    def _get_position_value(self, fund_type: str) -> Tuple[Decimal, int]:
        """
        Get total value of open positions for the fund.

        Queries the Java strategy service for current position values.
        Falls back to ClickHouse aware_fund_positions if API unavailable.
        """
        # Try to get from Java API first (more accurate real-time value)
        try:
            response = requests.get(
                f"{self.executor_api_url}/api/fund/{fund_type}/positions",
                timeout=5
            )
            if response.ok:
                data = response.json()
                return (
                    Decimal(str(data.get('totalValue', 0))),
                    data.get('positionCount', 0)
                )
        except Exception as e:
            logger.debug(f"Could not fetch positions from API: {e}")

        # Fallback: query ClickHouse for position values
        # Note: aware_fund_positions uses fund_id, shares (not fund_type, position_size)
        # and has no status column - all positions are considered open
        query = """
            SELECT
                sum(shares * current_price) as total_value,
                count(*) as num_positions
            FROM polybot.aware_fund_positions FINAL
            WHERE fund_id = %(fund_type)s
            AND shares > 0
        """

        try:
            result = self.client.execute(
                query,
                {'fund_type': fund_type}
            )

            if result and result[0]:
                value = Decimal(str(result[0][0] or 0))
                count = int(result[0][1] or 0)
                return (value, count)
        except Exception as e:
            logger.warning(f"Could not query positions: {e}")

        return (Decimal('0'), 0)

    def _get_total_shares(self, fund_type: str) -> Decimal:
        """Get total shares outstanding for the fund."""
        query = """
            SELECT coalesce(sum(shares_balance), 0) as total_shares
            FROM polybot.aware_user_shares FINAL
            WHERE fund_type = %(fund_type)s
            AND shares_balance > 0
        """

        result = self.client.execute(
            query,
            {'fund_type': fund_type}
        )

        if result and result[0]:
            return Decimal(str(result[0][0]))
        return Decimal('0')

    def _get_depositor_count(self, fund_type: str) -> int:
        """Get number of unique depositors with positive balance."""
        query = """
            SELECT count(DISTINCT user_id) as num_depositors
            FROM polybot.aware_user_shares FINAL
            WHERE fund_type = %(fund_type)s
            AND shares_balance > 0
        """

        result = self.client.execute(
            query,
            {'fund_type': fund_type}
        )

        if result and result[0]:
            return int(result[0][0])
        return 0

    def _calculate_total_pnl(self, fund_type: str, current_value: Decimal) -> Decimal:
        """
        Calculate total P&L (profit/loss) for the fund.

        P&L = Current Fund Value - Total Cost Basis (all deposits minus withdrawals)
        """
        query = """
            SELECT coalesce(sum(cost_basis_usdc), 0) as total_cost_basis
            FROM polybot.aware_user_shares FINAL
            WHERE fund_type = %(fund_type)s
        """

        result = self.client.execute(
            query,
            {'fund_type': fund_type}
        )

        total_cost_basis = Decimal('0')
        if result and result[0]:
            total_cost_basis = Decimal(str(result[0][0]))

        return current_value - total_cost_basis

    def _persist_nav(self, valuation: FundValuation):
        """
        Persist NAV calculation to history table.

        This creates a time series of NAV values for historical analysis.
        """
        # Calculate daily return
        daily_return = self._calculate_daily_return(
            valuation.fund_type,
            valuation.nav_per_share
        )

        query = """
            INSERT INTO polybot.aware_fund_nav (
                fund_type, calculated_at,
                total_usdc_balance, total_position_value, total_fund_value,
                total_shares, nav_per_share,
                total_pnl, total_fees_collected,
                daily_return_pct, num_depositors, num_positions
            ) VALUES
        """

        self.client.execute(
            query,
            [{
                'fund_type': valuation.fund_type,
                'calculated_at': valuation.calculated_at,
                'total_usdc_balance': float(valuation.total_usdc_balance),
                'total_position_value': float(valuation.total_position_value),
                'total_fund_value': float(valuation.total_fund_value),
                'total_shares': float(valuation.total_shares),
                'nav_per_share': float(valuation.nav_per_share),
                'total_pnl': float(valuation.total_pnl),
                'total_fees_collected': 0,  # TODO: Track fees
                'daily_return_pct': float(daily_return),
                'num_depositors': valuation.num_depositors,
                'num_positions': valuation.num_positions
            }]
        )

    def _update_fund_summary(self, valuation: FundValuation):
        """
        Update the current fund summary (replaces existing row).

        This is the "live" view of each fund's status.
        """
        # Calculate performance metrics
        returns = self._calculate_returns(valuation.fund_type, valuation.nav_per_share)

        query = """
            INSERT INTO polybot.aware_fund_summary (
                fund_type, updated_at, status,
                total_aum, total_shares, nav_per_share, num_depositors,
                return_24h_pct, return_7d_pct, return_30d_pct, return_inception_pct,
                sharpe_ratio, max_drawdown_pct
            ) VALUES (
                %(fund_type)s, %(updated_at)s, 'active',
                %(total_aum)s, %(total_shares)s, %(nav_per_share)s, %(num_depositors)s,
                %(return_24h)s, %(return_7d)s, %(return_30d)s, %(return_inception)s,
                %(sharpe_ratio)s, %(max_drawdown)s
            )
        """

        self.client.execute(
            query,
            {
                'fund_type': valuation.fund_type,
                'updated_at': valuation.calculated_at,
                'total_aum': float(valuation.total_fund_value),
                'total_shares': float(valuation.total_shares),
                'nav_per_share': float(valuation.nav_per_share),
                'num_depositors': valuation.num_depositors,
                'return_24h': float(returns['return_24h']),
                'return_7d': float(returns['return_7d']),
                'return_30d': float(returns['return_30d']),
                'return_inception': float(returns['return_inception']),
                'sharpe_ratio': float(returns['sharpe_ratio']),
                'max_drawdown': float(returns['max_drawdown'])
            }
        )

    def _calculate_daily_return(self, fund_type: str, current_nav: Decimal) -> Decimal:
        """Calculate 24h return percentage."""
        yesterday = datetime.utcnow() - timedelta(days=1)

        query = """
            SELECT nav_per_share
            FROM polybot.aware_fund_nav
            WHERE fund_type = %(fund_type)s
            AND calculated_at <= %(cutoff)s
            ORDER BY calculated_at DESC
            LIMIT 1
        """

        result = self.client.execute(
            query,
            {'fund_type': fund_type, 'cutoff': yesterday}
        )

        if result and result[0]:
            prev_nav = Decimal(str(result[0][0]))
            if prev_nav > 0:
                return ((current_nav - prev_nav) / prev_nav * 100).quantize(
                    Decimal('0.0001'), rounding=ROUND_HALF_UP
                )
        return Decimal('0')

    def _calculate_returns(self, fund_type: str, current_nav: Decimal) -> Dict[str, Decimal]:
        """
        Calculate various return metrics.

        Returns dict with:
        - return_24h: 24-hour return %
        - return_7d: 7-day return %
        - return_30d: 30-day return %
        - return_inception: Since inception return %
        - sharpe_ratio: Risk-adjusted return (annualized)
        - max_drawdown: Maximum peak-to-trough decline %
        """
        now = datetime.utcnow()

        # Query historical NAV data
        query = """
            SELECT
                calculated_at,
                nav_per_share
            FROM polybot.aware_fund_nav
            WHERE fund_type = %(fund_type)s
            ORDER BY calculated_at ASC
        """

        result = self.client.execute(query, {'fund_type': fund_type})

        returns = {
            'return_24h': Decimal('0'),
            'return_7d': Decimal('0'),
            'return_30d': Decimal('0'),
            'return_inception': Decimal('0'),
            'sharpe_ratio': Decimal('0'),
            'max_drawdown': Decimal('0')
        }

        if not result:
            return returns

        # Convert to list of (timestamp, nav) tuples
        nav_history = [(row[0], Decimal(str(row[1]))) for row in result]

        # Calculate period returns
        cutoffs = {
            'return_24h': now - timedelta(days=1),
            'return_7d': now - timedelta(days=7),
            'return_30d': now - timedelta(days=30),
        }

        for key, cutoff in cutoffs.items():
            # Find NAV closest to cutoff
            prev_navs = [(ts, nav) for ts, nav in nav_history if ts <= cutoff]
            if prev_navs:
                prev_nav = prev_navs[-1][1]
                if prev_nav > 0:
                    returns[key] = ((current_nav - prev_nav) / prev_nav * 100).quantize(
                        Decimal('0.0001'), rounding=ROUND_HALF_UP
                    )

        # Inception return (from first NAV)
        if nav_history:
            inception_nav = nav_history[0][1]
            if inception_nav > 0:
                returns['return_inception'] = (
                    (current_nav - inception_nav) / inception_nav * 100
                ).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

        # Calculate Sharpe ratio (simplified - assumes risk-free rate = 0)
        if len(nav_history) >= 7:
            daily_returns = []
            for i in range(1, len(nav_history)):
                prev = nav_history[i-1][1]
                curr = nav_history[i][1]
                if prev > 0:
                    daily_returns.append(float((curr - prev) / prev))

            if daily_returns:
                import statistics
                mean_return = statistics.mean(daily_returns)
                std_return = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0.01

                # Annualize (252 trading days)
                if std_return > 0:
                    sharpe = (mean_return * 252**0.5) / (std_return * 252**0.5)
                    returns['sharpe_ratio'] = Decimal(str(sharpe)).quantize(
                        Decimal('0.0001'), rounding=ROUND_HALF_UP
                    )

        # Calculate max drawdown
        peak = Decimal('0')
        max_dd = Decimal('0')

        for _, nav in nav_history:
            if nav > peak:
                peak = nav
            if peak > 0:
                dd = (peak - nav) / peak * 100
                if dd > max_dd:
                    max_dd = dd

        returns['max_drawdown'] = max_dd.quantize(
            Decimal('0.0001'), rounding=ROUND_HALF_UP
        )

        return returns


def run_nav_calculation():
    """
    Main entry point for NAV calculation job.

    Called by scheduler or run_all.py every 5 minutes.
    """
    ch_host = os.getenv('CLICKHOUSE_HOST', 'localhost')
    ch_port = int(os.getenv('CLICKHOUSE_PORT', '9000'))

    logger.info("Starting NAV calculation...")

    client = Client(host=ch_host, port=ch_port)
    calculator = NAVCalculator(client)

    valuations = calculator.calculate_all_funds()

    logger.info(f"Completed NAV calculation for {len(valuations)} funds")

    return valuations


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    run_nav_calculation()
