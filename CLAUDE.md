# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

```bash
# Build all modules
mvn clean package -DskipTests

# Run tests
mvn test

# Run a single test class
mvn test -pl strategy-service -Dtest=GabagoolDirectionalEngineTest

# Run a single test method
mvn test -pl strategy-service -Dtest=GabagoolDirectionalEngineTest#testQuoteCalculation
```

### Running Services (develop profile = paper trading)

```bash
# Start infrastructure first
docker-compose -f docker-compose.analytics.yaml up -d  # ClickHouse + Kafka

# Then run services (each in separate terminal, or use IntelliJ compound config)
cd executor-service && mvn spring-boot:run -Dspring-boot.run.profiles=develop
cd strategy-service && mvn spring-boot:run -Dspring-boot.run.profiles=develop
cd ingestor-service && mvn spring-boot:run -Dspring-boot.run.profiles=develop
```

### Research Tools (Python)

```bash
cd research
source .venv/bin/activate  # Python 3.11+
python snapshot_report.py              # Take data snapshot
python deep_analysis.py                # Strategy analysis
python sim_trade_match_report.py       # Compare sim vs target
python replication_score.py            # Score replication accuracy
```

### ClickHouse Schema Updates

```bash
# Apply all DDL migrations
scripts/clickhouse/apply-init.sh
```

## Project Vision: AWARE FUND (Polymarket Smart Index)

This project is evolving from "clone one trader" to become **the first ETF for prediction markets**.

> *"Don't bet on outcomes. Bet on the best traders being right."*

```
USER → $1,000 USDC → PSI FUND → Mirrors top 10-50 traders
                         │
                         ├── 12% gabagool22 (arbitrage specialist)
                         ├── 11% trader_alpha (crypto markets)
                         ├── 10% smart_whale (political markets)
                         └── ... weighted by Smart Money Score
```

### The Problem We're Solving

- Prediction markets are powerful but require expertise, time, and emotional discipline
- Top 1% of traders capture most profits; bottom 50% lose money
- No passive investment option exists (unlike ETFs for stocks)

### Product Layers (Bottom-Up)

| Layer | Description | Status |
|-------|-------------|--------|
| **1. Trader Intelligence** | Ingest ALL trades, profile every trader, real-time P&L | ✅ Complete |
| **2. Ranking & Classification** | Leaderboard, Sharpe ratios, strategy clustering | ✅ Complete |
| **3. Index Construction** | PSI-10, PSI-CRYPTO, PSI-POLITICS indices | ✅ Complete |
| **4. Fund Management** | User deposits, position mirroring, settlements | 🟡 In Progress |

### Index Family (PSI = Polymarket Smart Index)

| Index | Description | Weighting |
|-------|-------------|-----------|
| **PSI-10** | Top 10 traders by Smart Money Score | Equal weight (10% each) |
| **PSI-CRYPTO** | Top crypto price market traders | Sharpe-weighted |
| **PSI-POLITICS** | Top political market traders | Win-rate weighted |
| **PSI-ARBITRAGE** | Top arb/market-making traders | Daily rebalanced |
| **PSI-ALPHA** | ML-selected edge traders | Dynamic allocation |

### Smart Money Score (0-100)

```
Score = 0.40 × Profitability     (P&L percentile)
      + 0.30 × Risk-Adjusted     (Sharpe ratio, capped at 3.0)
      + 0.20 × Consistency       (win rate - variance penalty)
      + 0.10 × Track Record      (days active + trade count)
```

Inclusion criteria: 90+ days active, $50k+ volume, positive P&L, Sharpe > 1.0

### Business Model

| Revenue Stream | Target (Year 3) |
|----------------|-----------------|
| Management fees (0.5% AUM) | $500K |
| Performance fees (10% of profits) | $1.5M |
| Pro subscriptions ($49/mo) | $5.9M |
| API/Data licensing | $500K |
| **Total** | **$8.4M/year** |

### Roadmap

| Phase | Timeline | Deliverables |
|-------|----------|--------------|
| **1. Foundation** | Q1 2025 | Global trade ingestion, trader profiling, basic leaderboard |
| **2. Intelligence** | Q2 2025 | Strategy classification ML, Smart Money scoring, public API |
| **3. Index Launch** | Q3 2025 | PSI-10 construction, web platform beta, Pro tier |
| **4. Fund Launch** | Q4 2025 | Smart contracts, security audits, public launch |

### Key Documents

All AWARE FUND documentation lives in `aware-fund/`:

| Document | Purpose |
|----------|---------|
| `aware-fund/README.md` | Quick start guide |
| `aware-fund/VISION.md` | **Start here** - Complete product vision, architecture, status |
| `aware-fund/ACTION_PLAN.md` | Implementation checklist with current progress |
| `aware-fund/DESIGN_DECISIONS.md` | Strategic choices & rationale |
| `aware-fund/ML_AI_STRATEGY.md` | Machine learning opportunities & roadmap |

### AWARE Fund Services (Built)

**Python Analytics** (`aware-fund/services/analytics/`):
- `run_all.py` - **Main entry point** - runs all analytics jobs
- `scoring_job.py` - Calculates Smart Money Scores
- `psi_index.py` - Builds PSI indices (PSI-10, PSI-SPORTS, PSI-CRYPTO)
- `insider_detector.py` - Detects insider activity
- `edge_decay.py` - Monitors performance decline
- `hidden_alpha.py` - Finds undiscovered traders
- `consensus.py` - Smart money consensus detection
- `anomaly_detection.py` - Gaming/manipulation detection
- `clickhouse_client.py` - Database queries

**Python API** (`aware-fund/services/api/main.py`):
- FastAPI server with 40+ endpoints
- `/api/leaderboard` - Smart Money rankings
- `/api/fund/*` - Fund NAV, positions, executions
- `/api/indices/*` - PSI index composition
- `/api/discovery/*` - Hidden gems, rising stars
- `/api/insider/*` - Insider alerts
- `/api/consensus/*` - Smart money consensus signals

**Java Fund Engine** (`strategy-service/.../fund/`):
- `FundConfiguration.java` - Spring wiring (enabled via `hft.fund.enabled=true`)
- `FundTradeListener.java` - Polls ClickHouse for indexed trader trades
- `FundPositionMirror.java` - Executes scaled mirror trades with delay
- `IndexWeightProvider.java` - Loads PSI index weights from ClickHouse
- `FundRegistry.java` - Manages multiple fund instances
- `FundType.java` - Enum: PSI-10, PSI-SPORTS, ALPHA-ARB, etc.

**Next.js Dashboard** (`aware-fund/services/web/`):
- Fund performance visualization
- Leaderboard display
- Index composition charts

### What Makes This Defensible

1. **Data moat** - First to collect comprehensive trader profiles across all of Polymarket
2. **Execution infrastructure** - Already built the trading/settlement stack
3. **Network effects** - More AUM → better execution → better returns → more AUM
4. **Brand** - "The Vanguard of prediction markets"

---

## Architecture Overview

Polybot is a multi-module Maven project for Polymarket prediction market trading. The core use case is **reverse-engineering successful traders** and replicating their strategies.

### Module Dependency Graph

```
polybot-core (shared SDK)
    ↓
┌───────────────┬───────────────┬───────────────┐
│  executor     │   strategy    │   ingestor    │
│  (port 8080)  │  (port 8081)  │  (port 8082)  │
└───────────────┴───────────────┴───────────────┘
                      │
               ClickHouse + Kafka
```

### Key Services

**executor-service** - Order execution and settlement
- `PolymarketTradingService` - submits orders to CLOB API
- `PaperExchangeSimulator` - simulates fills against live TOB
- `PolymarketSettlementService` - redeems resolved positions on-chain

**strategy-service** - Trading strategy engine
- `GabagoolDirectionalEngine` - main strategy loop (complete-set arbitrage)
- `GabagoolMarketDiscovery` - discovers active Up/Down markets
- `QuoteCalculator`, `OrderManager`, `BankrollService` - strategy components

**ingestor-service** - Data collection
- `PolymarketUserIngestor` - polls target user's trades
- `PolymarketUpDownMarketWsIngestor` - WebSocket TOB for active markets
- `PolygonTxReceiptIngestor` - on-chain transaction receipts

**polybot-core** - Shared library
- `ClobMarketWebSocketClient` - WebSocket for real-time order book
- `PolymarketClobClient` - CLOB REST API (orders, book, trades)
- `PolymarketGammaClient` - Gamma API (market metadata)
- `HftEventPublisher` - Kafka event publishing

### Data Flow

1. **Ingestor** polls target user trades → Kafka → ClickHouse
2. **Ingestor** streams WebSocket TOB → Kafka → ClickHouse
3. **Strategy** reads TOB from WebSocket, generates signals
4. **Strategy** sends order requests to Executor via HTTP
5. **Executor** submits to Polymarket CLOB (or simulates in paper mode)
6. **Executor** publishes fills/status → Kafka → ClickHouse

### Trading Modes

- `hft.mode: PAPER` (default) - simulated execution against live book
- `hft.mode: LIVE` - real money trading (requires `send-live-ack: true`)

### Configuration

All services use Spring profiles:
- `develop` - local development (paper trading, localhost infra)
- `live` - production (requires credentials in `.env`)

Environment variables loaded from `.env` via spring-dotenv.

## Strategy Implementation

The included strategy (`GabagoolDirectionalEngine`) implements **complete-set arbitrage**:
- Trade BTC/ETH Up/Down binary markets
- When `bid_UP + bid_DOWN < 1.0`, there's arbitrage edge
- Quote both sides with inventory skewing
- Fast top-up mechanism completes pairs after partial fills

Key configuration in `application-develop.yaml`:
```yaml
hft.strategy.gabagool:
  complete-set-min-edge: 0.01      # 1% edge threshold
  complete-set-max-skew-ticks: 1   # Inventory skew adjustment
  quote-size: 10                   # Base shares per quote
  bankroll-usd: 500                # Total capital
```

See `docs/EXAMPLE_STRATEGY_SPEC.md` for full specification.

## ClickHouse Schema

Analytics tables in `analytics-service/clickhouse/init/`:

**Core Polybot (001-009)**:
- `001_init.sql` - raw events (trades, tob, positions)
- `002_canonical.sql` - deduplicated views
- `003_enriched.sql` - enriched trade data with TOB joins
- `005_position_ledger.sql` - position tracking
- `0080_polygon_*.sql` - on-chain transaction decoding
- `0090_enriched_ws.sql` - WebSocket TOB enrichment
- `0095_strategy_validation.sql` - replication scoring

**AWARE Fund (100-202)**:
- `100_aware_schema.sql` - Global trades, trader profiles, Smart Money Scores, ML scores
- `101_resolutions.sql` - Market resolution tracking for P&L calculation
- `102_psi_views.sql` - PSI index helper views
- `200_fund_schema.sql` - PSI index storage, fund positions, NAV history, executions
- `201_alerts_schema.sql` - Alerts, anomalies, consensus signals, edge decay, hidden alpha
- `202_insider_alerts_schema.sql` - Insider detection alerts and tracking

## Adding a New Strategy

1. Create class in `strategy-service/.../strategy/` implementing main loop
2. Add configuration properties class (see `GabagoolConfig.java`)
3. Wire as Spring bean with `@ConditionalOnProperty`
4. Add config section in `application-develop.yaml`
5. Use `ExecutorApiClient` to submit orders to executor

Reference implementation: `GabagoolDirectionalEngine.java`

## API Endpoints

```bash
# Executor health/status
curl http://localhost:8080/api/polymarket/health
curl http://localhost:8080/api/polymarket/positions
curl http://localhost:8080/api/polymarket/settlement/plan

# Strategy status
curl http://localhost:8081/api/strategy/status

# AWARE Fund API (Python FastAPI, default port 8000)
curl http://localhost:8000/api/leaderboard              # Smart Money rankings
curl http://localhost:8000/api/leaderboard/gabagool22   # Specific trader
curl http://localhost:8000/api/indices/PSI-10           # PSI-10 composition
curl http://localhost:8000/api/fund/nav                 # Fund NAV
curl http://localhost:8000/api/fund/positions           # Fund positions
curl http://localhost:8000/api/discovery/hidden-gems    # Undiscovered traders
curl http://localhost:8000/api/insider/alerts           # Insider activity alerts
curl http://localhost:8000/api/monitoring               # Data pipeline health
```

## Running AWARE Fund Services

```bash
# Start Python API
cd aware-fund/services/api
CLICKHOUSE_HOST=localhost uvicorn main:app --reload

# Run full analytics pipeline (all jobs)
cd aware-fund/services/analytics
CLICKHOUSE_HOST=localhost python run_all.py

# Or run continuously every hour
CLICKHOUSE_HOST=localhost python run_all.py --continuous

# Run individual jobs if needed
CLICKHOUSE_HOST=localhost python scoring_job.py
CLICKHOUSE_HOST=localhost python psi_index.py
```
