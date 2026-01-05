# AWARE

**Polymarket trading infrastructure and the AWARE Fund platform.**

This repository contains two integrated components:

1. **Polybot** - Java trading infrastructure for Polymarket (order execution, strategies, data ingestion)
2. **AWARE Fund** - Python analytics platform for the "Smart Money Index" product

---

## Quick Start

### Prerequisites
- Java 21+ / Maven 3.8+
- Python 3.11+
- Docker & Docker Compose

### 1. Start Infrastructure

```bash
docker-compose -f docker-compose.analytics.yaml up -d
```

### 2. Run Services

```bash
# Java services (each in separate terminal)
cd executor-service && mvn spring-boot:run -Dspring-boot.run.profiles=develop
cd strategy-service && mvn spring-boot:run -Dspring-boot.run.profiles=develop
cd ingestor-service && mvn spring-boot:run -Dspring-boot.run.profiles=develop

# AWARE Fund API
cd aware-fund/services/api
CLICKHOUSE_HOST=localhost uvicorn main:app --reload

# AWARE Fund Dashboard
cd aware-fund/services/web && npm install && npm run dev
```

---

## Architecture

```
aware/
├── polybot-core/           # Shared Java library (APIs, WebSocket, events)
├── executor-service/       # Order execution, paper trading, settlement
├── strategy-service/       # Trading strategies + Fund mirror engine
├── ingestor-service/       # Market data & trade ingestion
├── analytics-service/      # ClickHouse schemas
├── research/               # Python research & analysis tools
└── aware-fund/             # AWARE Fund product
    ├── services/analytics/ # Smart Money scoring, PSI indices
    ├── services/api/       # FastAPI (40+ endpoints)
    └── services/web/       # Next.js dashboard
```

---

## Components

### Polybot (Trading Infrastructure)

| Service | Port | Purpose |
|---------|------|---------|
| executor-service | 8080 | Order execution, simulation, settlement |
| strategy-service | 8081 | Trading strategies, fund mirroring |
| ingestor-service | 8082 | Market data ingestion |

### AWARE Fund (Analytics Platform)

| Service | Port | Purpose |
|---------|------|---------|
| Python API | 8000 | Leaderboard, indices, alerts, fund data |
| Next.js Dashboard | 3000 | Visualization UI |

---

## AWARE Fund Product

> *"Don't bet on outcomes. Bet on the best traders being right."*

The AWARE Fund is a "Smart Money Index" for Polymarket - passive investment products that mirror top traders.

### PSI Indices (Polymarket Smart Index)

| Index | Description |
|-------|-------------|
| PSI-10 | Top 10 traders by Smart Money Score |
| PSI-CRYPTO | Top crypto market specialists |
| PSI-POLITICS | Top political forecasters |
| PSI-SPORTS | Top sports bettors |

### Smart Money Score (0-100)

```
Score = 0.40 × Profitability     (P&L percentile)
      + 0.30 × Risk-Adjusted     (Sharpe ratio)
      + 0.20 × Consistency       (win rate - variance)
      + 0.10 × Track Record      (days active + trades)
```

### API Endpoints

```bash
# Leaderboard
curl localhost:8000/api/leaderboard

# PSI Index
curl localhost:8000/api/indices/PSI-10

# Fund NAV
curl localhost:8000/api/fund/nav

# Discovery
curl localhost:8000/api/discovery/hidden-gems

# Insider Alerts
curl localhost:8000/api/insider/alerts
```

---

## Documentation

| Document | Purpose |
|----------|---------|
| [CLAUDE.md](CLAUDE.md) | AI assistant context & commands |
| [aware-fund/VISION.md](aware-fund/VISION.md) | Product vision & architecture |
| [aware-fund/ACTION_PLAN.md](aware-fund/ACTION_PLAN.md) | Implementation progress |
| [docs/EXAMPLE_STRATEGY_SPEC.md](docs/EXAMPLE_STRATEGY_SPEC.md) | Strategy implementation guide |

---

## Development

### Build

```bash
mvn clean package -DskipTests
```

### Test

```bash
mvn test
mvn test -pl strategy-service -Dtest=GabagoolDirectionalEngineTest
```

### Research Tools

```bash
cd research && source .venv/bin/activate
python snapshot_report.py          # Data snapshots
python deep_analysis.py            # Strategy analysis
python sim_trade_match_report.py   # Replication scoring
```

---

## Status

| Component | Status |
|-----------|--------|
| Trading Infrastructure | Production |
| Data Ingestion | Production |
| Smart Money Scoring | Complete |
| PSI Indices | Complete |
| Fund Mirror Engine | Complete |
| Dashboard | Basic |
| Smart Contracts | Pending |

---

## License

Proprietary - All rights reserved.
