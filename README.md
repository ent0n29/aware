# AWARE

AWARE is a combined codebase for:
- **Polybot core infrastructure** (Java execution/strategy/ingestion services)
- **AWARE Fund product layer** (Python analytics, API, and web dashboard)

The project focuses on trader intelligence and index-style exposure for Polymarket data.

## Repository Map

```text
aware/
├── executor-service/                    # Java executor (orders, portfolio, settlement)
├── strategy-service/                    # Java strategy + fund mirroring logic
├── ingestor-service/                    # Java ingestion pipelines
├── analytics-service/                   # ClickHouse schema/init + analytics service
├── infrastructure-orchestrator-service/ # Java orchestrator for Docker stacks
├── polybot-core/                        # Shared Java components
├── aware-fund/
│   ├── services/analytics/              # Python scoring, PSI indices, ML jobs
│   ├── services/api/                    # FastAPI service
│   └── services/web/                    # Next.js dashboard
├── research/                            # Research and replication scripts
├── docker-compose.local.yaml            # Full local stack
└── Makefile                             # Main development entrypoint
```

## Quick Start (Recommended)

Use the Docker-based local stack.

### Prerequisites

- Docker Engine/Desktop with Compose plugin
- `make`

### Start

```bash
make local
```

### Check health

```bash
make status
```

### View logs

```bash
make logs
# or: make logs SERVICE=strategy
```

### Stop

```bash
make down
```

## Service Endpoints (Local Stack)

| Component | URL |
|---|---|
| Web dashboard | http://localhost:3000 |
| API | http://localhost:8000 |
| Executor | http://localhost:8080 |
| Strategy | http://localhost:8081 |
| Ingestor | http://localhost:8083 |
| ClickHouse | http://localhost:8123 |
| Redpanda admin | http://localhost:9644 |
| Prometheus (optional profile) | http://localhost:9090 |
| Grafana (optional profile) | http://localhost:3001 |

## Alternative Workflow (Run Services From Host)

If you want to run Java/Python services outside Docker:

```bash
# Infra only (ClickHouse + Kafka)
make infra

# Java
make java-build
make executor
make strategy
make ingestor

# Python
make python-setup
make python-analytics
make python-api

# Web
make web-install
make web-dev
```

## Useful Make Targets

```bash
make help
make build
make local
make status
make logs
make train
make train-all
make analytics
make down
make clean
```

## API Examples

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/leaderboard
curl http://localhost:8000/api/indices/PSI-10
curl http://localhost:8000/api/fund/nav
curl http://localhost:8000/api/insider/alerts
```

## Testing

```bash
# Java tests
mvn test

# Module-level example
mvn test -pl strategy-service
```

## Documentation

- Product vision: `aware-fund/VISION.md`
- Execution roadmap: `aware-fund/ACTION_PLAN.md`
- Strategy and product choices: `aware-fund/DESIGN_DECISIONS.md`
- ML strategy notes: `aware-fund/ML_AI_STRATEGY.md`
- Research usage: `research/README.md`
- Deployment notes: `DEPLOYMENT.md`

## Current State

- Core ingestion/execution/scoring stack is operational.
- Fund mirror engine is implemented in Java strategy service.
- API and dashboard are functional for local/dev usage.
- Smart-contract-based custody/deposit flows are still pending for a full public fund launch.

## Security

- Do not commit credentials, private keys, or real `.env` values.
- Use `.env.example` as template only.
- Run secret scanning before public releases (for example, `gitleaks`).

## ARM / Apple Silicon

The stack is compatible with ARM64 local environments (Docker/Colima or Docker Desktop on Apple Silicon).

## License

MIT
