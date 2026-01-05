# AWARE FUND

## The Smart Money Index for Prediction Markets

> **"Don't bet on outcomes. Bet on the best traders being right."**

---

## Documentation

| Document | Purpose |
|----------|---------|
| [VISION.md](VISION.md) | **Start here** - Product vision, architecture, status |
| [ACTION_PLAN.md](ACTION_PLAN.md) | Implementation checklist with current progress |
| [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md) | Key strategic decisions and rationale |
| [ML_AI_STRATEGY.md](ML_AI_STRATEGY.md) | Machine learning opportunities and roadmap |

---

## Quick Start

```bash
# Start infrastructure
docker-compose -f docker-compose.analytics.yaml up -d

# Run Python API
cd services/api && CLICKHOUSE_HOST=localhost uvicorn main:app --reload

# Run scoring (daily)
cd services/analytics && CLICKHOUSE_HOST=localhost python scoring_job.py
```

---

## Project Structure

```
aware-fund/
├── services/
│   ├── analytics/          # Python: scoring, indices, detection
│   │   ├── scoring_job.py  # Smart Money Score calculation
│   │   ├── psi_index.py    # PSI index construction
│   │   ├── insider_detector.py
│   │   ├── edge_decay.py
│   │   └── ml/             # ML training pipeline
│   ├── api/                # FastAPI server
│   │   └── main.py         # 40+ endpoints
│   └── web/                # Next.js dashboard
├── docs/
│   └── archive/            # Historical docs (for reference)
└── *.md                    # Active documentation
```

---

## Current Status

| Component | Status |
|-----------|--------|
| Data Pipeline | ✅ Complete |
| Smart Money Scoring | ✅ Complete |
| PSI Indices | ✅ Complete |
| Insider Detection | ✅ Complete |
| Fund Engine (Java) | ✅ Complete |
| Dashboard | 🟡 Basic |
| Smart Contracts | ⚪ Pending |

---

## API Endpoints

```bash
# Leaderboard
curl localhost:8000/api/leaderboard

# PSI Index
curl localhost:8000/api/indices/PSI-10

# Fund NAV
curl localhost:8000/api/fund/nav

# Insider Alerts
curl localhost:8000/api/insider/alerts

# Discovery
curl localhost:8000/api/discovery/hidden-gems
```

---

*See [VISION.md](VISION.md) for complete product details.*
