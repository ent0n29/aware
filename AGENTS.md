# Repository Guidelines

## Project Structure & Module Organization
- This is a multi-module Maven repo (`pom.xml` at the root).
- Core modules:
  - `polybot-core/`: shared domain, events, WS clients, Polymarket/Gamma integrations.
  - `strategy-service/`: trading logic (gabagool replication), order lifecycle, sizing/risk gates.
  - `executor-service/`: order execution + PAPER simulator (`PaperExchangeSimulator`).
  - `ingestor-service/`: ingestion pipelines (WS/REST) into ClickHouse/Kafka.
  - `analytics-service/`: ClickHouse sinks + schema init SQL in `analytics-service/clickhouse/init/`.
- Supporting:
  - `research/`: Python reports/backtests (match %, coverage, calibration).
  - `logs/`: runtime logs + `.pid` files created by scripts.

## Build, Test, and Development Commands
- `./start-all-services.sh`: builds (if needed) and starts infra + services.
- `./stop-all-services.sh`: stops all services using PID files.
- `mvn -DskipTests package`: build all jars.
- `mvn test`: run unit tests.
- Health checks:
  - `curl http://localhost:8081/actuator/health` (strategy)
  - `curl http://localhost:8123 --data "SELECT 1"` (ClickHouse HTTP)

## Coding Style & Naming Conventions
- Java: keep existing formatting (4-space indent), `PascalCase` classes, `camelCase` methods/fields.
- Prices/sizes: prefer `BigDecimal` and explicit tick handling (typically `0.01` for up/down markets).
- YAML: 2-space indent; keep defaults in `*/src/main/resources/application-develop.yaml`.
- ClickHouse migrations: add new files as `analytics-service/clickhouse/init/00xx_description.sql` (append-only).
- Python in `research/`: prefer CLI scripts with clear flags; use stdlib where feasible to avoid arch issues.

## Testing Guidelines
- Tests live in `*/src/test/java` (JUnit). Run per-module: `mvn test -pl strategy-service`.
- Keep tests deterministic (inject clocks/randomness where possible) and avoid live network calls.

## Commit & Pull Request Guidelines
- History favors small, descriptive commits (e.g., “dynamic sizing”, “small fixes”). Use an imperative subject and mention the module when helpful.
- PRs should include: what changed, which services/modules are affected, how to reproduce (commands + expected output), and any config/SQL migration notes.

## Security & Configuration Tips
- Repo is public: never commit private keys, API credentials, or RPC tokens. Use `.env` locally and keep secrets out of YAML committed to git.
