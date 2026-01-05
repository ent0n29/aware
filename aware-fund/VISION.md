# AWARE FUND

## The Smart Money Index for Prediction Markets

> **"Don't bet on outcomes. Bet on the best traders being right."**

---

## The Problem

Prediction markets are powerful but inaccessible:
- **Top 1% of traders** capture most profits; bottom 50% lose money
- Requires domain expertise, trading knowledge, time, emotional discipline
- **No passive investment option exists** (unlike ETFs for stocks)

## The Solution

AWARE FUND inverts prediction markets: instead of betting on outcomes, invest in traders who consistently predict outcomes correctly.

```
Traditional:  USER → Analyzes events → Makes bets → Wins/Loses
AWARE:        USER → Deposits USDC → AWARE mirrors top traders → Captures their edge
```

---

## Product Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           AWARE FUND PRODUCT SUITE                               │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  TIER 1: PASSIVE INDEX FUNDS (Mirror top traders)                               │
│  ─────────────────────────────────────────────────                              │
│    PSI-10         PSI-SPORTS      PSI-CRYPTO       PSI-POLITICS                 │
│    Top 10         Top sports      Top crypto       Top political                │
│    overall        bettors         traders          forecasters                  │
│                                                                                  │
│    [REPLICABLE STRATEGIES ONLY - Excludes HFT/Arb]                              │
│                                                                                  │
│  TIER 2: ALPHA FUNDS (Our proprietary strategies)                               │
│  ────────────────────────────────────────────────                               │
│    ALPHA-ARB           ALPHA-INSIDER         ALPHA-EDGE                         │
│    Reverse-engineered  Follow detected       ML-detected                        │
│    HFT strategies      insider activity      opportunities                      │
│                                                                                  │
│  TIER 3: INTELLIGENCE (Subscription signals)                                    │
│  ───────────────────────────────────────────                                    │
│    Insider Alerts      Hidden Gems           Consensus Signals                  │
│    Unusual activity    Undiscovered          Smart money                        │
│    detection           talented traders      agreement                          │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## How It Works

### User Flow
```
DEPOSIT $10,000 USDC → Select PSI-10 Index → AWARE allocates:
  ├── 12% to Trader A (crypto specialist)
  ├── 11% to Trader B (political forecaster)
  ├── 10% to Trader C (sports expert)
  └── ... weighted by Smart Money Score

When Trader A buys "BTC > $100k YES" → Your position updates proportionally
Markets resolve → Profits distributed → Withdraw anytime
```

### Smart Money Score (0-100)
```
Score = 0.40 × Profitability    (P&L percentile)
      + 0.30 × Risk-Adjusted    (Sharpe ratio)
      + 0.20 × Consistency      (win rate - variance)
      + 0.10 × Track Record     (days active + trades)
```

---

## Technical Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       DATA PIPELINE                              │
└─────────────────────────────────────────────────────────────────┘

Polymarket API ─► Kafka ─► ClickHouse
                              │
         ┌────────────────────┴────────────────────┐
         │                                          │
         ▼                                          ▼
   scoring_job.py                           insider_detector.py
   (Smart Money Scores)                     (Anomaly Detection)
         │                                          │
         ▼                                          ▼
   psi_index.py                             Alerts + Signals
   (Build PSI-10, etc.)
         │
         ▼
   FundPositionMirror.java
   (Execute mirror trades)
```

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| **Python Analytics** | `services/analytics/` | Scoring, indices, detection |
| **Python API** | `services/api/main.py` | FastAPI with 40+ endpoints |
| **Java Fund Engine** | `strategy-service/.../fund/` | Trade execution |
| **Next.js Dashboard** | `services/web/` | Visualization |
| **ClickHouse** | `analytics-service/clickhouse/` | Data storage |

---

## Current Status

| Component | Status | Notes |
|-----------|--------|-------|
| Data Ingestion | ✅ Complete | Global trades in ClickHouse |
| Smart Money Scoring | ✅ Complete | P&L, Sharpe, win rates |
| PSI Index Engine | ✅ Complete | PSI-10, SPORTS, CRYPTO, POLITICS |
| Insider Detection | ✅ Complete | 4 signal types |
| Fund Mirror Engine | ✅ Complete | Java implementation |
| Dashboard | 🟡 Basic | Needs polish |
| Smart Contracts | ⚪ Not Started | For deposits/withdrawals |
| User Auth | ⚪ Not Started | Wallet connect |

---

## Business Model

| Revenue Stream | Model |
|----------------|-------|
| Management Fee | 0.5% of AUM annually |
| Performance Fee | 10% of profits |
| Pro Subscription | $49-499/month for signals |
| API Access | Enterprise licensing |

---

## Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| **Foundation** | Data ingestion, trader profiling | ✅ Complete |
| **Intelligence** | Scoring, indices, detection | ✅ Complete |
| **Fund Engine** | Position mirroring, execution | ✅ Complete |
| **Product** | Dashboard, API, UX | 🟡 In Progress |
| **Launch** | Smart contracts, deposits, go-live | ⚪ Pending |

---

## What Makes This Defensible

1. **Data Moat** - Comprehensive trader profiles across all of Polymarket
2. **Execution Infrastructure** - Trading/settlement stack already built
3. **Network Effects** - More AUM → better execution → better returns → more AUM
4. **First Mover** - No ETF for prediction markets exists

---

*For implementation details, see [ACTION_PLAN.md](ACTION_PLAN.md)*
*For design rationale, see [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md)*
*For ML strategy, see [ML_AI_STRATEGY.md](ML_AI_STRATEGY.md)*
