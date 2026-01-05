"""
AWARE Analytics - Insider Detection System

Detects potential insider trading activity on Polymarket.

Unlike traditional markets, prediction markets have NO insider trading laws.
This creates an opportunity: detect "someone knows something" signals
BEFORE news breaks, and trade alongside them.

Detection Signals:
1. NEW_ACCOUNT_WHALE: New account + big bet + rare market
2. VOLUME_SPIKE: Unusual volume increase before news
3. SMART_MONEY_DIVERGENCE: Top traders betting against consensus
4. WHALE_ANOMALY: Known whale changes typical behavior

Example (real case):
    "New account created, bets $50k on Maduro capture.
     No public news. 24 hours later: Maduro captured."

Usage:
    detector = InsiderDetector(ch_client)
    alerts = detector.scan_for_insider_activity()
    for alert in alerts:
        print(f"ALERT: {alert.signal_type} - {alert.description}")
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import math

logger = logging.getLogger(__name__)


class InsiderSignalType(Enum):
    """Types of insider activity signals"""
    NEW_ACCOUNT_WHALE = "NEW_ACCOUNT_WHALE"       # New account, big bet, unusual market
    VOLUME_SPIKE = "VOLUME_SPIKE"                 # Sudden volume increase
    SMART_MONEY_DIVERGENCE = "SMART_MONEY_DIVERGENCE"  # Top traders vs consensus
    WHALE_ANOMALY = "WHALE_ANOMALY"               # Known whale unusual behavior
    COORDINATED_ENTRY = "COORDINATED_ENTRY"       # Multiple accounts, same direction
    LATE_ENTRY_CONVICTION = "LATE_ENTRY_CONVICTION"  # Big bet close to resolution


class AlertSeverity(Enum):
    """Alert severity levels"""
    LOW = "LOW"           # Interesting but not actionable
    MEDIUM = "MEDIUM"     # Worth monitoring
    HIGH = "HIGH"         # Consider following
    CRITICAL = "CRITICAL"  # Strong signal, act quickly


@dataclass
class InsiderAlert:
    """A detected insider activity alert"""
    signal_type: InsiderSignalType
    severity: AlertSeverity
    market_slug: str
    market_question: str

    # Signal details
    description: str
    confidence: float  # 0.0 to 1.0

    # Trade details
    direction: str  # "YES" or "NO"
    total_volume_usd: float
    num_traders: int

    # Timing
    detected_at: datetime
    trade_timestamps: list[datetime] = field(default_factory=list)

    # Traders involved (for WHALE signals)
    traders_involved: list[str] = field(default_factory=list)

    def __repr__(self):
        return f"InsiderAlert({self.signal_type.value}, {self.severity.value}, {self.market_slug})"


@dataclass
class InsiderDetectorConfig:
    """Configuration for insider detection thresholds"""
    # NEW_ACCOUNT_WHALE thresholds
    new_account_max_days: int = 7           # Account age considered "new"
    new_account_min_bet_usd: float = 5000   # Minimum bet size to flag
    new_account_min_concentration: float = 0.8  # 80%+ of volume in single market

    # VOLUME_SPIKE thresholds
    volume_spike_ratio: float = 10.0        # 10x normal volume
    volume_spike_lookback_days: int = 30    # Days to calculate normal volume
    volume_spike_window_hours: int = 6      # Window for spike detection

    # SMART_MONEY_DIVERGENCE thresholds
    smart_money_top_n: int = 100            # Top N traders to watch
    smart_money_min_traders: int = 3        # Min traders betting same direction
    smart_money_min_divergence: float = 0.2  # 20%+ against consensus

    # WHALE_ANOMALY thresholds
    whale_min_volume_usd: float = 100000    # Min volume to be considered whale
    whale_category_threshold: float = 0.1   # Max normal % in a category

    # General
    min_market_liquidity: float = 1000      # Ignore low-liquidity markets
    lookback_hours: int = 24                # Hours to look back for signals

    # Market exclusions - markets where insider trading is impossible
    # Price prediction markets resolve based on public price data
    excluded_market_patterns: tuple[str, ...] = (
        # Generic short-term patterns
        '%-15m-%',              # Any 15-minute market
        '%-1h-%',               # Any 1-hour market
        '%-hourly%',            # Hourly markets
        '%updown%15m%',         # Updown 15-min patterns
        # ALL crypto up/down markets (no insider info for price moves)
        '%up-or-down%',         # Any "up or down" market (SOL, XRP, BTC, etc.)
        '%up-down%',            # Up-down markets
        '%updown%',             # Updown patterns
        # BTC/Bitcoin price markets
        'btc-updown%',
        'bitcoin-above-%',
        'will-bitcoin-%',
        '%btc%above%',
        '%bitcoin%reach%',
        '%bitcoin%dip%',
        # ETH/Ethereum price markets
        'eth-updown%',
        'ethereum-above-%',
        'will-ethereum-%',
        '%eth%above%',
        '%ethereum%reach%',
        '%ethereum%dip%',
        # Other crypto price markets
        'solana%up%down%',
        'xrp%up%down%',
        'doge%up%down%',
        '%sol%above%',
        '%xrp%above%',
        '%solana%reach%',
        '%xrp%reach%',
    )


class InsiderDetector:
    """
    Main insider detection engine.

    Scans trade data for suspicious patterns that might indicate
    someone has non-public information.
    """

    def __init__(
        self,
        clickhouse_client,
        config: Optional[InsiderDetectorConfig] = None
    ):
        self.ch = clickhouse_client
        self.config = config or InsiderDetectorConfig()

    def _get_market_exclusion_sql(self, column: str = 'market_slug') -> str:
        """
        Generate SQL WHERE clause to exclude price prediction markets.

        These markets (BTC/ETH up/down, 15m markets) cannot have insider trading
        because they resolve based on public price data.
        """
        if not self.config.excluded_market_patterns:
            return ""

        conditions = []
        for pattern in self.config.excluded_market_patterns:
            conditions.append(f"{column} NOT LIKE '{pattern}'")

        return " AND " + " AND ".join(conditions)

    def scan_for_insider_activity(
        self,
        lookback_hours: Optional[int] = None
    ) -> list[InsiderAlert]:
        """
        Run all detection algorithms and return alerts.

        Args:
            lookback_hours: Hours to look back (default: config value)

        Returns:
            List of InsiderAlert objects, sorted by severity
        """
        hours = lookback_hours or self.config.lookback_hours
        logger.info(f"Scanning for insider activity (last {hours} hours)...")

        alerts = []

        # Run each detector
        alerts.extend(self._detect_new_account_whales(hours))
        alerts.extend(self._detect_volume_spikes(hours))
        alerts.extend(self._detect_smart_money_divergence(hours))
        alerts.extend(self._detect_whale_anomalies(hours))
        alerts.extend(self._detect_coordinated_entry(hours))
        alerts.extend(self._detect_late_entry_conviction(hours))

        # Sort by severity (CRITICAL first)
        severity_order = {
            AlertSeverity.CRITICAL: 0,
            AlertSeverity.HIGH: 1,
            AlertSeverity.MEDIUM: 2,
            AlertSeverity.LOW: 3,
        }
        alerts.sort(key=lambda a: (severity_order[a.severity], -a.confidence))

        logger.info(f"Found {len(alerts)} insider alerts")
        return alerts

    def _detect_new_account_whales(self, hours: int) -> list[InsiderAlert]:
        """
        Detect new accounts making large bets in single markets.

        Signal: Account created recently, bets big, concentrated in one market.
        """
        market_exclusion = self._get_market_exclusion_sql('market_slug')
        query = f"""
        WITH
        recent_trades AS (
            SELECT
                proxy_address,
                username,
                market_slug,
                side,
                sum(notional) as total_bet,
                count() as trade_count,
                min(ts) as first_trade,
                max(ts) as last_trade
            FROM polybot.aware_global_trades_dedup
            WHERE ts >= now() - INTERVAL {hours} HOUR
              AND proxy_address != ''
              {market_exclusion}
            GROUP BY proxy_address, username, market_slug, side
        ),
        trader_stats AS (
            SELECT
                proxy_address,
                username,
                sum(total_bet) as total_volume,
                count(DISTINCT market_slug) as unique_markets,
                argMax(market_slug, total_bet) as main_market,
                argMax(side, total_bet) as main_direction,
                max(total_bet) as max_market_bet
            FROM recent_trades
            GROUP BY proxy_address, username
        ),
        account_age AS (
            SELECT
                proxy_address,
                min(ts) as first_ever_trade
            FROM polybot.aware_global_trades_dedup
            WHERE proxy_address != ''
            GROUP BY proxy_address
        )
        SELECT
            ts.proxy_address,
            ts.username,
            ts.main_market,
            ts.main_direction,
            ts.max_market_bet,
            ts.total_volume,
            ts.unique_markets,
            dateDiff('day', aa.first_ever_trade, now()) as account_age_days,
            ts.max_market_bet / ts.total_volume as concentration
        FROM trader_stats ts
        JOIN account_age aa ON ts.proxy_address = aa.proxy_address
        WHERE
            account_age_days <= {self.config.new_account_max_days}
            AND ts.max_market_bet >= {self.config.new_account_min_bet_usd}
            AND ts.max_market_bet / ts.total_volume >= {self.config.new_account_min_concentration}
        ORDER BY ts.max_market_bet DESC
        LIMIT 50
        """

        alerts = []
        try:
            result = self.ch.query(query)

            for row in result.result_rows:
                proxy_address = row[0]
                username = row[1] or "anonymous"
                market_slug = row[2]
                direction = row[3]
                bet_size = float(row[4])
                total_volume = float(row[5])
                unique_markets = int(row[6])
                account_age = int(row[7])
                concentration = float(row[8])

                # Calculate confidence based on signals
                confidence = 0.5
                if account_age <= 3:
                    confidence += 0.2
                if bet_size >= 10000:
                    confidence += 0.15
                if bet_size >= 50000:
                    confidence += 0.15
                if concentration >= 0.95:
                    confidence += 0.1

                # Determine severity
                if bet_size >= 50000 and account_age <= 3:
                    severity = AlertSeverity.CRITICAL
                elif bet_size >= 20000 and account_age <= 5:
                    severity = AlertSeverity.HIGH
                elif bet_size >= 10000:
                    severity = AlertSeverity.MEDIUM
                else:
                    severity = AlertSeverity.LOW

                alerts.append(InsiderAlert(
                    signal_type=InsiderSignalType.NEW_ACCOUNT_WHALE,
                    severity=severity,
                    market_slug=market_slug,
                    market_question="",  # Could fetch from API
                    description=f"{account_age}-day-old account '{username}' bet ${bet_size:,.0f} on {direction}",
                    confidence=min(1.0, confidence),
                    direction=direction,
                    total_volume_usd=bet_size,
                    num_traders=1,
                    detected_at=datetime.utcnow(),
                    traders_involved=[username],
                ))

        except Exception as e:
            logger.error(f"New account whale detection failed: {e}")

        return alerts

    def _detect_volume_spikes(self, hours: int) -> list[InsiderAlert]:
        """
        Detect markets with unusual volume increases.

        Signal: Volume 10x normal in short period, before any news.
        """
        market_exclusion = self._get_market_exclusion_sql('market_slug')
        query = f"""
        WITH
        -- Recent volume by market
        recent_volume AS (
            SELECT
                market_slug,
                sum(notional) as recent_vol,
                sumIf(notional, side = 'BUY' AND outcome_index = 0) as yes_vol,
                sumIf(notional, side = 'BUY' AND outcome_index = 1) as no_vol,
                count(DISTINCT proxy_address) as unique_traders
            FROM polybot.aware_global_trades_dedup
            WHERE ts >= now() - INTERVAL {hours} HOUR
              AND market_slug != ''
              {market_exclusion}
            GROUP BY market_slug
            HAVING recent_vol >= {self.config.min_market_liquidity}
        ),
        -- Historical average volume
        historical_volume AS (
            SELECT
                market_slug,
                sum(notional) / {self.config.volume_spike_lookback_days} as avg_daily_vol
            FROM polybot.aware_global_trades_dedup
            WHERE ts >= now() - INTERVAL {self.config.volume_spike_lookback_days} DAY
              AND ts < now() - INTERVAL {hours} HOUR
              AND market_slug != ''
              {market_exclusion}
            GROUP BY market_slug
        )
        SELECT
            rv.market_slug,
            rv.recent_vol,
            hv.avg_daily_vol,
            rv.recent_vol / nullIf(hv.avg_daily_vol * ({hours} / 24.0), 0) as spike_ratio,
            rv.yes_vol,
            rv.no_vol,
            rv.unique_traders,
            if(rv.yes_vol > rv.no_vol, 'YES', 'NO') as dominant_direction
        FROM recent_volume rv
        LEFT JOIN historical_volume hv ON rv.market_slug = hv.market_slug
        WHERE spike_ratio >= {self.config.volume_spike_ratio}
        ORDER BY spike_ratio DESC
        LIMIT 50
        """

        alerts = []
        try:
            result = self.ch.query(query)

            for row in result.result_rows:
                market_slug = row[0]
                recent_vol = float(row[1])
                avg_daily = float(row[2] or 1)
                spike_ratio = float(row[3] or 0)
                yes_vol = float(row[4])
                no_vol = float(row[5])
                unique_traders = int(row[6])
                direction = row[7]

                # Calculate directional imbalance
                total_directional = yes_vol + no_vol
                if total_directional > 0:
                    imbalance = abs(yes_vol - no_vol) / total_directional
                else:
                    imbalance = 0

                # Confidence based on spike magnitude and imbalance
                confidence = min(1.0, 0.3 + (spike_ratio / 50) + (imbalance * 0.3))

                # Severity based on spike ratio
                if spike_ratio >= 50 and imbalance >= 0.7:
                    severity = AlertSeverity.CRITICAL
                elif spike_ratio >= 20:
                    severity = AlertSeverity.HIGH
                elif spike_ratio >= 10:
                    severity = AlertSeverity.MEDIUM
                else:
                    severity = AlertSeverity.LOW

                alerts.append(InsiderAlert(
                    signal_type=InsiderSignalType.VOLUME_SPIKE,
                    severity=severity,
                    market_slug=market_slug,
                    market_question="",
                    description=f"{spike_ratio:.1f}x normal volume, {imbalance:.0%} toward {direction}",
                    confidence=confidence,
                    direction=direction,
                    total_volume_usd=recent_vol,
                    num_traders=unique_traders,
                    detected_at=datetime.utcnow(),
                ))

        except Exception as e:
            logger.error(f"Volume spike detection failed: {e}")

        return alerts

    def _detect_smart_money_divergence(self, hours: int) -> list[InsiderAlert]:
        """
        Detect when top traders bet against market consensus.

        Signal: Multiple top-100 traders betting same direction, against consensus.
        """
        market_exclusion = self._get_market_exclusion_sql('t.market_slug')
        market_exclusion_ms = self._get_market_exclusion_sql('market_slug')
        query = f"""
        WITH
        -- Get top 100 traders by P&L
        top_traders AS (
            SELECT proxy_address, username
            FROM polybot.aware_smart_money_scores FINAL
            ORDER BY total_score DESC
            LIMIT {self.config.smart_money_top_n}
        ),
        -- Get their recent bets
        smart_money_bets AS (
            SELECT
                t.market_slug,
                t.side,
                t.outcome_index,
                sum(t.notional) as smart_money_vol,
                count(DISTINCT t.proxy_address) as num_smart_traders
            FROM polybot.aware_global_trades_dedup t
            INNER JOIN top_traders tt ON t.proxy_address = tt.proxy_address
            WHERE t.ts >= now() - INTERVAL {hours} HOUR
              {market_exclusion}
            GROUP BY t.market_slug, t.side, t.outcome_index
        ),
        -- Get overall market sentiment
        market_sentiment AS (
            SELECT
                market_slug,
                sumIf(notional, outcome_index = 0) as yes_volume,
                sumIf(notional, outcome_index = 1) as no_volume,
                if(yes_volume > no_volume, 0, 1) as consensus_outcome
            FROM polybot.aware_global_trades_dedup
            WHERE ts >= now() - INTERVAL 7 DAY
              {market_exclusion_ms}
            GROUP BY market_slug
        )
        SELECT
            smb.market_slug,
            smb.outcome_index,
            smb.smart_money_vol,
            smb.num_smart_traders,
            ms.consensus_outcome,
            ms.yes_volume,
            ms.no_volume,
            if(smb.outcome_index = 0, 'YES', 'NO') as smart_money_direction
        FROM smart_money_bets smb
        JOIN market_sentiment ms ON smb.market_slug = ms.market_slug
        WHERE
            smb.num_smart_traders >= {self.config.smart_money_min_traders}
            AND smb.outcome_index != ms.consensus_outcome  -- Betting against consensus
            AND smb.side = 'BUY'
        ORDER BY smb.smart_money_vol DESC
        LIMIT 30
        """

        alerts = []
        try:
            result = self.ch.query(query)

            for row in result.result_rows:
                market_slug = row[0]
                outcome_index = int(row[1])
                smart_money_vol = float(row[2])
                num_traders = int(row[3])
                consensus_outcome = int(row[4])
                yes_vol = float(row[5])
                no_vol = float(row[6])
                direction = row[7]

                # Calculate how contrarian this is
                total_vol = yes_vol + no_vol
                consensus_pct = (yes_vol if consensus_outcome == 0 else no_vol) / total_vol if total_vol > 0 else 0.5

                # Confidence based on number of smart traders and volume
                confidence = min(1.0, 0.4 + (num_traders * 0.1) + (smart_money_vol / 50000))

                # Severity based on divergence
                if num_traders >= 5 and consensus_pct >= 0.7:
                    severity = AlertSeverity.CRITICAL
                elif num_traders >= 3 and consensus_pct >= 0.6:
                    severity = AlertSeverity.HIGH
                else:
                    severity = AlertSeverity.MEDIUM

                alerts.append(InsiderAlert(
                    signal_type=InsiderSignalType.SMART_MONEY_DIVERGENCE,
                    severity=severity,
                    market_slug=market_slug,
                    market_question="",
                    description=f"{num_traders} top traders bet ${smart_money_vol:,.0f} on {direction} vs {consensus_pct:.0%} consensus",
                    confidence=confidence,
                    direction=direction,
                    total_volume_usd=smart_money_vol,
                    num_traders=num_traders,
                    detected_at=datetime.utcnow(),
                ))

        except Exception as e:
            logger.error(f"Smart money divergence detection failed: {e}")

        return alerts

    def _detect_coordinated_entry(self, hours: int) -> list[InsiderAlert]:
        """
        Detect coordinated trading across multiple accounts.

        Signal: Multiple accounts entering same market in same direction within
        a short time window, suggesting coordination or shared information.
        """
        market_exclusion = self._get_market_exclusion_sql('market_slug')
        query = f"""
        WITH
        -- Get trades in recent window
        recent_trades AS (
            SELECT
                market_slug,
                proxy_address,
                username,
                side,
                outcome_index,
                sum(notional) as total_bet,
                min(ts) as first_trade_ts,
                max(ts) as last_trade_ts
            FROM polybot.aware_global_trades_dedup
            WHERE ts >= now() - INTERVAL {hours} HOUR
              AND proxy_address != ''
              {market_exclusion}
            GROUP BY market_slug, proxy_address, username, side, outcome_index
        ),
        -- Find markets with clustered entries (multiple traders in short window)
        clustered_markets AS (
            SELECT
                market_slug,
                outcome_index,
                count(DISTINCT proxy_address) as num_traders,
                sum(total_bet) as total_volume,
                min(first_trade_ts) as cluster_start,
                max(last_trade_ts) as cluster_end,
                dateDiff('minute', min(first_trade_ts), max(last_trade_ts)) as window_minutes,
                groupArray(username) as traders
            FROM recent_trades
            WHERE side = 'BUY'
            GROUP BY market_slug, outcome_index
            HAVING
                num_traders >= 3
                AND window_minutes <= 120  -- Within 2 hours
                AND total_volume >= 10000  -- At least $10K total
        )
        SELECT
            market_slug,
            outcome_index,
            num_traders,
            total_volume,
            cluster_start,
            cluster_end,
            window_minutes,
            traders
        FROM clustered_markets
        ORDER BY num_traders DESC, total_volume DESC
        LIMIT 30
        """

        alerts = []
        try:
            result = self.ch.query(query)

            for row in result.result_rows:
                market_slug = row[0]
                outcome_index = int(row[1])
                num_traders = int(row[2])
                total_volume = float(row[3])
                cluster_start = row[4]
                cluster_end = row[5]
                window_minutes = int(row[6])
                traders = row[7] if isinstance(row[7], list) else []

                direction = "YES" if outcome_index == 0 else "NO"

                # Calculate coordination score
                # More traders in shorter window = higher score
                traders_per_minute = num_traders / max(1, window_minutes)
                volume_per_trader = total_volume / num_traders

                confidence = min(1.0, 0.3 + (num_traders * 0.1) + (traders_per_minute * 0.2))

                # Severity based on coordination strength
                if num_traders >= 5 and window_minutes <= 30:
                    severity = AlertSeverity.CRITICAL
                elif num_traders >= 4 and window_minutes <= 60:
                    severity = AlertSeverity.HIGH
                elif num_traders >= 3:
                    severity = AlertSeverity.MEDIUM
                else:
                    severity = AlertSeverity.LOW

                alerts.append(InsiderAlert(
                    signal_type=InsiderSignalType.COORDINATED_ENTRY,
                    severity=severity,
                    market_slug=market_slug,
                    market_question="",
                    description=f"{num_traders} traders entered {direction} within {window_minutes} min, total ${total_volume:,.0f}",
                    confidence=confidence,
                    direction=direction,
                    total_volume_usd=total_volume,
                    num_traders=num_traders,
                    detected_at=datetime.utcnow(),
                    trade_timestamps=[cluster_start, cluster_end] if cluster_start else [],
                    traders_involved=traders[:10],  # Limit to first 10
                ))

        except Exception as e:
            logger.error(f"Coordinated entry detection failed: {e}")

        return alerts

    def _detect_late_entry_conviction(self, hours: int) -> list[InsiderAlert]:
        """
        Detect large bets placed close to market resolution.

        Signal: Big bet when market is about to resolve, suggesting
        high conviction from information advantage.
        """
        market_exclusion = self._get_market_exclusion_sql('t.market_slug')
        query = f"""
        WITH
        -- Markets resolving soon (within 7 days) - approximated by recent activity pattern
        -- Since we don't have end_date, look for markets with declining activity suggesting near resolution
        active_markets AS (
            SELECT
                market_slug,
                count() as recent_trades,
                sum(notional) as recent_volume
            FROM polybot.aware_global_trades_dedup
            WHERE ts >= now() - INTERVAL 7 DAY
              AND market_slug != ''
            GROUP BY market_slug
            HAVING recent_volume >= 5000
        ),
        -- Large recent bets in these markets
        large_bets AS (
            SELECT
                t.proxy_address,
                t.username,
                t.market_slug,
                t.side,
                t.outcome_index,
                sum(t.notional) as bet_size,
                min(t.ts) as first_bet,
                count() as num_bets
            FROM polybot.aware_global_trades_dedup t
            INNER JOIN active_markets am ON t.market_slug = am.market_slug
            WHERE t.ts >= now() - INTERVAL {hours} HOUR
              AND t.proxy_address != ''
              {market_exclusion}
            GROUP BY t.proxy_address, t.username, t.market_slug, t.side, t.outcome_index
            HAVING bet_size >= 10000  -- Large bets only
        ),
        -- Check if this is unusual for the trader (first time in market or much larger than usual)
        trader_history AS (
            SELECT
                proxy_address,
                market_slug,
                sum(notional) as historical_volume
            FROM polybot.aware_global_trades_dedup
            WHERE ts < now() - INTERVAL {hours} HOUR
              AND proxy_address != ''
            GROUP BY proxy_address, market_slug
        )
        SELECT
            lb.proxy_address,
            lb.username,
            lb.market_slug,
            lb.side,
            lb.outcome_index,
            lb.bet_size,
            lb.first_bet,
            lb.num_bets,
            th.historical_volume
        FROM large_bets lb
        LEFT JOIN trader_history th ON lb.proxy_address = th.proxy_address AND lb.market_slug = th.market_slug
        WHERE
            -- Either never traded this market or betting much more than before
            th.historical_volume IS NULL OR lb.bet_size > th.historical_volume * 2
        ORDER BY lb.bet_size DESC
        LIMIT 30
        """

        alerts = []
        try:
            result = self.ch.query(query)

            for row in result.result_rows:
                proxy_address = row[0]
                username = row[1] or "anonymous"
                market_slug = row[2]
                side = row[3]
                outcome_index = int(row[4])
                bet_size = float(row[5])
                first_bet = row[6]
                num_bets = int(row[7])
                historical_volume = float(row[8]) if row[8] else 0

                direction = "YES" if outcome_index == 0 else "NO"

                # First time in market is more suspicious
                is_new_to_market = historical_volume == 0

                # Calculate conviction score
                confidence = 0.4
                if is_new_to_market:
                    confidence += 0.25
                if bet_size >= 25000:
                    confidence += 0.2
                if bet_size >= 50000:
                    confidence += 0.15
                confidence = min(1.0, confidence)

                # Severity
                if bet_size >= 50000 and is_new_to_market:
                    severity = AlertSeverity.CRITICAL
                elif bet_size >= 25000 and is_new_to_market:
                    severity = AlertSeverity.HIGH
                elif bet_size >= 10000:
                    severity = AlertSeverity.MEDIUM
                else:
                    severity = AlertSeverity.LOW

                reason = "first entry" if is_new_to_market else f"{bet_size/historical_volume:.1f}x historical"
                alerts.append(InsiderAlert(
                    signal_type=InsiderSignalType.LATE_ENTRY_CONVICTION,
                    severity=severity,
                    market_slug=market_slug,
                    market_question="",
                    description=f"'{username}' bet ${bet_size:,.0f} on {direction} ({reason})",
                    confidence=confidence,
                    direction=direction,
                    total_volume_usd=bet_size,
                    num_traders=1,
                    detected_at=datetime.utcnow(),
                    trade_timestamps=[first_bet] if first_bet else [],
                    traders_involved=[username],
                ))

        except Exception as e:
            logger.error(f"Late entry conviction detection failed: {e}")

        return alerts

    def _detect_whale_anomalies(self, hours: int) -> list[InsiderAlert]:
        """
        Detect when known whales deviate from their typical behavior.

        Signal: Whale enters category they don't normally trade.
        """
        # This requires market category data from TraderCategoryProfiler
        # For now, simplified version based on unusual market entry
        market_exclusion = self._get_market_exclusion_sql('t.market_slug')
        query = f"""
        WITH
        -- Identify whales (high volume traders)
        whales AS (
            SELECT
                proxy_address,
                username,
                sum(notional) as total_volume
            FROM polybot.aware_global_trades_dedup
            WHERE proxy_address != ''
            GROUP BY proxy_address, username
            HAVING total_volume >= {self.config.whale_min_volume_usd}
        ),
        -- Whale's typical markets (top 90% of their volume)
        whale_typical AS (
            SELECT
                t.proxy_address,
                t.market_slug,
                sum(t.notional) as market_vol
            FROM polybot.aware_global_trades_dedup t
            INNER JOIN whales w ON t.proxy_address = w.proxy_address
            WHERE t.ts < now() - INTERVAL {hours} HOUR  -- Historical only
              {market_exclusion}
            GROUP BY t.proxy_address, t.market_slug
        ),
        -- Whale's recent activity
        whale_recent AS (
            SELECT
                t.proxy_address AS proxy_address,
                w.username AS username,
                t.market_slug AS market_slug,
                t.side AS side,
                t.outcome_index AS outcome_index,
                sum(t.notional) as recent_bet,
                count() as trade_count
            FROM polybot.aware_global_trades_dedup t
            INNER JOIN whales w ON t.proxy_address = w.proxy_address
            WHERE t.ts >= now() - INTERVAL {hours} HOUR
              {market_exclusion}
            GROUP BY t.proxy_address, w.username, t.market_slug, t.side, t.outcome_index
        )
        SELECT
            wr.proxy_address,
            wr.username,
            wr.market_slug,
            if(wr.outcome_index = 0, 'YES', 'NO') as direction,
            wr.recent_bet,
            wt.market_vol as historical_vol
        FROM whale_recent wr
        LEFT JOIN whale_typical wt ON wr.proxy_address = wt.proxy_address AND wr.market_slug = wt.market_slug
        WHERE
            wt.market_vol IS NULL  -- Never traded this market before
            AND wr.recent_bet >= 5000  -- Significant bet
        ORDER BY wr.recent_bet DESC
        LIMIT 30
        """

        alerts = []
        try:
            result = self.ch.query(query)

            for row in result.result_rows:
                proxy_address = row[0]
                username = row[1] or "whale"
                market_slug = row[2]
                direction = row[3]
                bet_size = float(row[4])

                # Confidence based on bet size
                confidence = min(1.0, 0.4 + (bet_size / 50000))

                # Severity based on bet size
                if bet_size >= 50000:
                    severity = AlertSeverity.HIGH
                elif bet_size >= 20000:
                    severity = AlertSeverity.MEDIUM
                else:
                    severity = AlertSeverity.LOW

                alerts.append(InsiderAlert(
                    signal_type=InsiderSignalType.WHALE_ANOMALY,
                    severity=severity,
                    market_slug=market_slug,
                    market_question="",
                    description=f"Whale '{username}' first time in market, bet ${bet_size:,.0f} on {direction}",
                    confidence=confidence,
                    direction=direction,
                    total_volume_usd=bet_size,
                    num_traders=1,
                    detected_at=datetime.utcnow(),
                    traders_involved=[username],
                ))

        except Exception as e:
            logger.error(f"Whale anomaly detection failed: {e}")

        return alerts

    def save_alerts(self, alerts: list[InsiderAlert]) -> int:
        """
        Save alerts to ClickHouse for historical tracking.

        Args:
            alerts: List of InsiderAlert objects

        Returns:
            Number of alerts saved
        """
        if not alerts:
            return 0

        # Prepare data for insert
        data = []
        for alert in alerts:
            data.append([
                alert.signal_type.value,
                alert.severity.value,
                alert.market_slug,
                alert.market_question,
                alert.description,
                alert.confidence,
                alert.direction,
                alert.total_volume_usd,
                alert.num_traders,
                alert.detected_at,
                ','.join(alert.traders_involved),
            ])

        columns = [
            'signal_type', 'severity', 'market_slug', 'market_question',
            'description', 'confidence', 'direction', 'total_volume_usd',
            'num_traders', 'detected_at', 'traders_involved'
        ]

        try:
            self.ch.insert(
                'polybot.aware_insider_alerts',
                data,
                column_names=columns
            )
            logger.info(f"Saved {len(alerts)} insider alerts")
            return len(alerts)
        except Exception as e:
            logger.error(f"Failed to save alerts: {e}")
            return 0


def get_detector(ch_client=None):
    """Get InsiderDetector with default config."""
    if ch_client is None:
        import os
        from clickhouse_client import ClickHouseClient
        ch_client = ClickHouseClient(
            host=os.getenv('CLICKHOUSE_HOST', 'localhost')
        )
    return InsiderDetector(ch_client)


def main():
    """Run insider detection scan."""
    import os
    logging.basicConfig(
        level=os.getenv('LOG_LEVEL', 'INFO'),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    from clickhouse_client import ClickHouseClient

    ch = ClickHouseClient(
        host=os.getenv('CLICKHOUSE_HOST', 'localhost')
    )

    detector = InsiderDetector(ch)

    print("=" * 70)
    print("  AWARE Insider Detection Scan")
    print("=" * 70)

    alerts = detector.scan_for_insider_activity(lookback_hours=24)

    if not alerts:
        print("\nNo insider activity detected in the last 24 hours.")
        return

    print(f"\nFound {len(alerts)} potential insider signals:\n")

    for alert in alerts:
        emoji = {
            AlertSeverity.CRITICAL: "🚨",
            AlertSeverity.HIGH: "⚠️",
            AlertSeverity.MEDIUM: "📊",
            AlertSeverity.LOW: "📝",
        }[alert.severity]

        print(f"{emoji} [{alert.severity.value:8}] {alert.signal_type.value}")
        print(f"   Market: {alert.market_slug}")
        print(f"   {alert.description}")
        print(f"   Direction: {alert.direction}, Volume: ${alert.total_volume_usd:,.0f}")
        print(f"   Confidence: {alert.confidence:.0%}")
        print()


if __name__ == "__main__":
    main()
