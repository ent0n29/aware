# AWARE

**Don't bet on outcomes. Bet on the best traders being right.**

AWARE turns prediction-market intelligence into an investable product layer.
Instead of manually tracking markets, users can follow data-driven trader indices,
monitor conviction signals, and plug into fund-style execution workflows.

## What AWARE Does

- Builds **Smart Money Scores** from real trading behavior
- Creates **PSI indices** (PSI-10, category indices, etc.)
- Runs a **fund mirroring engine** on top of Polybot execution infrastructure
- Exposes everything via **API + web dashboard**

## Product Stack

```text
aware/
├── executor-service/        # Java: order execution
├── strategy-service/        # Java: strategies + fund mirroring
├── ingestor-service/        # Java: market/user trade ingestion
├── analytics-service/       # ClickHouse schema + analytics API service module
├── polybot-core/            # Shared Java core
├── aware-fund/
│   ├── services/analytics/  # Python scoring + ML jobs
│   ├── services/api/        # FastAPI product API
│   └── services/web/        # Next.js dashboard
├── docker-compose.local.yaml
└── Makefile
```

## Run It In One Command

```bash
make local
```

Then:

```bash
make status
make logs
make down
```

## Local Endpoints

| Component | URL |
|---|---|
| Dashboard | http://localhost:3000 |
| Product API | http://localhost:8000 |
| Executor | http://localhost:8080 |
| Strategy | http://localhost:8081 |
| Ingestor | http://localhost:8083 |
| ClickHouse | http://localhost:8123 |

## API Quick Hits

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/leaderboard
curl http://localhost:8000/api/indices/PSI-10
curl http://localhost:8000/api/fund/nav
curl http://localhost:8000/api/insider/alerts
```

## Developer Commands

```bash
make help
make build
make local
make train
make train-all
make analytics

mvn clean package -DskipTests
mvn test
```

## Documentation

- Product vision: `aware-fund/VISION.md`
- Execution roadmap: `aware-fund/ACTION_PLAN.md`
- Design rationale: `aware-fund/DESIGN_DECISIONS.md`
- ML strategy: `aware-fund/ML_AI_STRATEGY.md`
- Research workflows: `research/README.md`
- Deployment notes: `DEPLOYMENT.md`

## Current Reality

- Core ingestion/execution/scoring stack is operational.
- Fund mirror logic is implemented in strategy service.
- API + dashboard are working for local/dev operation.
- Smart-contract custody/deposit flows are still pending before full public fund launch.

## Security

- Never commit private keys, API secrets, or real `.env` values.
- Use `.env.example` as template only.
- Keep secret scanning in release workflow.

## License

MIT
