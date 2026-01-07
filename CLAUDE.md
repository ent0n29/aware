# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

**AWARE** is the company. This repo contains:

1. **Polybot** - Java trading infrastructure for Polymarket (internal naming: `polybot`, `com.polybot.*`)
2. **AWARE Fund** - Python analytics platform for the Smart Money Index product

```
aware/
├── polybot-core/           # Shared Java SDK (APIs, WebSocket, events)
├── executor-service/       # Order execution (port 8080)
├── strategy-service/       # Strategies + Fund engine (port 8081)
├── ingestor-service/       # Data ingestion (port 8083)
├── analytics-service/      # ClickHouse schemas only (init/*.sql)
├── deploy/                 # Docker Compose configs & deployment scripts
├── research/               # Python analysis & research tools
└── aware-fund/             # AWARE Fund product
    ├── services/analytics/ # Scoring, indices, detection jobs
    ├── services/api/       # FastAPI server (port 8000)
    └── services/web/       # Next.js dashboard (port 3000)
```

---

## Commands

### Build & Test

```bash
mvn clean package -DskipTests    # Build all Java services
mvn test                          # Run all tests
mvn test -pl strategy-service -Dtest=GabagoolDirectionalEngineTest  # Single test
```

### Start Everything (Recommended)

```bash
./start-all-services.sh   # Builds if needed, starts infra + all Java services
./stop-all-services.sh    # Stops all services
```

### Start Individual Services

```bash
# Infrastructure first
docker-compose -f docker-compose.analytics.yaml up -d

# Java services (each in separate terminal)
cd executor-service && mvn spring-boot:run -Dspring-boot.run.profiles=develop
cd strategy-service && mvn spring-boot:run -Dspring-boot.run.profiles=develop
cd ingestor-service && mvn spring-boot:run -Dspring-boot.run.profiles=develop

# Python analytics jobs
cd aware-fund/services/analytics && source .venv/bin/activate
CLICKHOUSE_HOST=localhost python run_all.py

# Python API
cd aware-fund/services/api && source .venv/bin/activate
CLICKHOUSE_HOST=localhost uvicorn main:app --reload

# Web dashboard
cd aware-fund/services/web && npm run dev
```

### Python Environment Setup

```bash
cd aware-fund/services/analytics
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cd aware-fund/services/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### ClickHouse Schema

```bash
scripts/clickhouse/apply-init.sh   # Apply all init/*.sql files
```

### Research Tools

```bash
cd research && source .venv/bin/activate
python snapshot_report.py          # Data snapshots
python deep_analysis.py            # Strategy analysis
python sim_trade_match_report.py   # Replication scoring
```

---

## Data Flow Architecture

```
Polymarket API ──► ingestor-service ──► Kafka ──► ClickHouse
                                                       │
                   ┌───────────────────────────────────┤
                   │                                   │
                   ▼                                   ▼
            Python Analytics                    Java Fund Engine
            (scoring, indices)                  (position mirroring)
                   │                                   │
                   ▼                                   │
            ClickHouse Tables                          │
            (aware_smart_money_scores,                 │
             aware_psi_index, etc.)                    │
                   │                                   │
                   ▼                                   ▼
            Python API ◄────────────────────► executor-service
            (FastAPI)                          (trade execution)
                   │
                   ▼
            Next.js Dashboard
```

---

## Key Components

### Java Services

**executor-service (8080)**
- `PaperExchangeSimulator` - simulates fills against live order book
- `PolymarketTradingService` - submits orders to CLOB API
- `PolymarketSettlementService` - on-chain redemption

**strategy-service (8081)**
- `GabagoolDirectionalEngine` - complete-set arbitrage strategy
- `FundPositionMirror` - mirrors PSI index trader positions
- `FundTradeListener` - polls ClickHouse for trader activity
- `FundRegistry` - manages multiple fund instances

**ingestor-service (8083)**
- `PolymarketUserIngestor` - target user trades
- `PolymarketGlobalTradesIngestor` - all Polymarket trades (AWARE data)
- WebSocket ingestors for TOB data

### Python Analytics (`aware-fund/services/analytics/`)

| File | Purpose |
|------|---------|
| `run_all.py` | Main entry - orchestrates all jobs |
| `scoring_job.py` | Smart Money Score (0-100) calculation |
| `psi_index.py` | PSI index construction (PSI-10, CRYPTO, POLITICS, SPORTS) |
| `insider_detector.py` | Insider/unusual activity detection |
| `hidden_alpha.py` | Undiscovered trader discovery |
| `consensus.py` | Smart money consensus signals |
| `strategy_dna.py` | Trader strategy classification |
| `market_classifier.py` | Market category tagging |
| `ml/` | ML feature extraction and training |

### ClickHouse Schema (`analytics-service/clickhouse/init/`)

**Core (001-009)**: Raw events, positions, TOB data, order lifecycle
**AWARE (100-102)**: `aware_global_trades`, `aware_smart_money_scores`, `aware_psi_index`
**Fund (200-201)**: `aware_fund_positions`, `aware_fund_nav_history`, `aware_alerts`

---

## API Endpoints

```bash
# Java - Executor
curl localhost:8080/api/polymarket/health
curl localhost:8080/api/polymarket/positions

# Java - Strategy
curl localhost:8081/api/strategy/status
curl localhost:8081/api/fund/positions

# Python - AWARE Fund API (40+ endpoints)
curl localhost:8000/api/leaderboard
curl localhost:8000/api/indices/PSI-10
curl localhost:8000/api/fund/nav
curl localhost:8000/api/discovery/hidden-gems
curl localhost:8000/api/insider/alerts
curl localhost:8000/api/monitoring          # Pipeline health
```

---

## Configuration

**Trading modes**: `hft.mode: PAPER` (default) or `LIVE`
**Spring profiles**: `develop` (local) or `live` (production)
**Environment**: Variables in `.env`, loaded via spring-dotenv

Key environment variables:
- `CLICKHOUSE_HOST` - ClickHouse server (default: localhost)
- `KAFKA_BOOTSTRAP_SERVERS` - Kafka/Redpanda (default: localhost:9092)
- `POLYMARKET_API_KEY`, `POLYMARKET_API_SECRET` - API credentials

---

## Service Ports

| Service | Port | Purpose |
|---------|------|---------|
| executor-service | 8080 | Order execution |
| strategy-service | 8081 | Trading strategies |
| ingestor-service | 8083 | Data ingestion |
| Python API | 8000 | AWARE Fund REST API |
| Next.js Dashboard | 3000 | Web UI |
| ClickHouse HTTP | 8123 | Database queries |
| ClickHouse TCP | 9000 | Database native |
| Redpanda/Kafka | 9092 | Event streaming |
| Grafana | 3001 | Monitoring dashboards |
| Prometheus | 9090 | Metrics |

---

## Documentation

| Document | Purpose |
|----------|---------|
| `aware-fund/VISION.md` | Product architecture & roadmap |
| `aware-fund/ACTION_PLAN.md` | Implementation checklist |
| `aware-fund/DESIGN_DECISIONS.md` | Strategic choices |
