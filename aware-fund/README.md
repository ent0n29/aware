# AWARE Fund

AWARE Fund is the product layer on top of Polybot infrastructure:
- Smart Money scoring
- PSI index construction
- Fund analytics and intelligence APIs
- Dashboard for monitoring and exploration

## Key Docs

- Vision and architecture: `VISION.md`
- Action plan: `ACTION_PLAN.md`
- Design decisions: `DESIGN_DECISIONS.md`
- ML roadmap: `ML_AI_STRATEGY.md`

## Preferred Local Run

From repo root (`aware/`):

```bash
make local
make status
```

This starts the full stack (Java services, analytics, API, and web dashboard).

## Module-Level Run (If Needed)

### Analytics

```bash
cd services/analytics
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
CLICKHOUSE_HOST=localhost python run_all.py
```

### API

```bash
cd services/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
CLICKHOUSE_HOST=localhost uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Web

```bash
cd services/web
npm install
npm run dev
```

## Common API Endpoints

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/leaderboard
curl http://localhost:8000/api/indices/PSI-10
curl http://localhost:8000/api/fund/nav
curl http://localhost:8000/api/insider/alerts
curl http://localhost:8000/api/freshness
```

## Current Status (High Level)

- Data pipeline and scoring are active.
- PSI index generation is implemented.
- Insider/consensus/ML endpoints are available.
- Smart-contract fund custody flows are pending.

For full detail, use `ACTION_PLAN.md` as the execution checklist.
