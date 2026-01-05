# CLAUDE.md

Context for Claude Code when working in this repository.

## Repository Structure

**AWARE** is the company. This repo contains:

1. **Polybot** - Java trading infrastructure (internal naming: `polybot`, `com.polybot.*`)
2. **AWARE Fund** - Python analytics platform for the Smart Money Index product

```
aware/
├── polybot-core/           # Shared Java SDK
├── executor-service/       # Order execution (port 8080)
├── strategy-service/       # Strategies + Fund engine (port 8081)
├── ingestor-service/       # Data ingestion (port 8082)
├── analytics-service/      # ClickHouse schemas
├── research/               # Python analysis tools
└── aware-fund/             # AWARE Fund product
    ├── services/analytics/ # Scoring, indices, detection
    ├── services/api/       # FastAPI server (port 8000)
    └── services/web/       # Next.js dashboard (port 3000)
```

---

## Commands

### Build & Test

```bash
mvn clean package -DskipTests
mvn test
mvn test -pl strategy-service -Dtest=GabagoolDirectionalEngineTest
```

### Run Services

```bash
# Infrastructure
docker-compose -f docker-compose.analytics.yaml up -d

# Java services
cd executor-service && mvn spring-boot:run -Dspring-boot.run.profiles=develop
cd strategy-service && mvn spring-boot:run -Dspring-boot.run.profiles=develop
cd ingestor-service && mvn spring-boot:run -Dspring-boot.run.profiles=develop

# AWARE Fund
cd aware-fund/services/api && CLICKHOUSE_HOST=localhost uvicorn main:app --reload
cd aware-fund/services/web && npm run dev
```

### Research Tools

```bash
cd research && source .venv/bin/activate
python snapshot_report.py
python deep_analysis.py
python sim_trade_match_report.py
```

### ClickHouse Schema

```bash
scripts/clickhouse/apply-init.sh
```

---

## Key Components

### Java Services

**executor-service**
- `PaperExchangeSimulator` - simulates fills against live book
- `PolymarketTradingService` - submits to CLOB API
- `PolymarketSettlementService` - on-chain redemption

**strategy-service**
- `GabagoolDirectionalEngine` - complete-set arbitrage strategy
- `FundPositionMirror` - mirrors PSI index trader positions
- `FundTradeListener` - polls ClickHouse for trader activity

**ingestor-service**
- `PolymarketUserIngestor` - target user trades
- `PolymarketGlobalTradesIngestor` - all Polymarket trades
- WebSocket ingestors for TOB data

### Python Analytics (`aware-fund/services/analytics/`)

| File | Purpose |
|------|---------|
| `run_all.py` | Main entry - runs all jobs |
| `scoring_job.py` | Smart Money Score calculation |
| `psi_index.py` | PSI index construction |
| `insider_detector.py` | Insider activity detection |
| `hidden_alpha.py` | Undiscovered trader discovery |
| `consensus.py` | Smart money consensus signals |

### ClickHouse Schema

**Core (001-009)**: Raw events, positions, TOB data
**AWARE (100-202)**: Trader profiles, scores, PSI indices, fund tables, alerts

---

## API Endpoints

```bash
# Java - Executor
curl localhost:8080/api/polymarket/health
curl localhost:8080/api/polymarket/positions

# Java - Strategy
curl localhost:8081/api/strategy/status

# Python - AWARE Fund
curl localhost:8000/api/leaderboard
curl localhost:8000/api/indices/PSI-10
curl localhost:8000/api/fund/nav
curl localhost:8000/api/discovery/hidden-gems
curl localhost:8000/api/insider/alerts
```

---

## Configuration

**Trading modes**: `hft.mode: PAPER` (default) or `LIVE`
**Spring profiles**: `develop` (local) or `live` (production)
**Environment**: Variables in `.env`, loaded via spring-dotenv

---

## Documentation

| Document | Purpose |
|----------|---------|
| `aware-fund/VISION.md` | Product architecture & roadmap |
| `aware-fund/ACTION_PLAN.md` | Implementation checklist |
| `aware-fund/DESIGN_DECISIONS.md` | Strategic choices |
| `docs/EXAMPLE_STRATEGY_SPEC.md` | Strategy implementation guide |
