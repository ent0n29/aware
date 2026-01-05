# AWARE Fund: Prioritized Action Plan

**Created:** December 27, 2024
**Last Updated:** January 2025
**Current Status:** Core infrastructure complete, fund mechanics in progress

---

## Executive Summary

We have built **~80% of the infrastructure**:
- ✅ Data ingestion & accumulation (global trades in ClickHouse)
- ✅ Real metrics calculation (P&L, Sharpe, win rates, Smart Money Scores)
- ✅ PSI Index construction (PSI-10, PSI-SPORTS, PSI-CRYPTO)
- ✅ Insider detection system
- 🟡 Fund mechanics (Java engine built, smart contracts pending)

---

## Phase 0: Immediate ✅ COMPLETE
> **Goal:** Start collecting real data NOW

### 0.1 Deploy Java Ingestor ✅
- [x] Ensure `AWARE_GLOBAL_TRADES_ENABLED=true` in Java config
- [x] Run ingestor-service 24/7
- [x] Monitor `aware_global_trades` table growth
- [x] Deduplication via ReplacingMergeTree

### 0.2 Verify Data Pipeline ✅
- [x] Polymarket API → Kafka → ClickHouse flow works
- [x] Deduplication working (aware_global_trades_dedup view)
- [x] All fields populated (username, notional, outcome, etc.)

### 0.3 Schedule Scoring Jobs ✅
- [x] `scoring_job.py` calculates Smart Money Scores
- [x] `psi_index.py` builds PSI indices
- [x] Monitoring via `/api/monitoring` endpoint

**Status:** Data accumulating, scores updating

---

## Phase 1: Data Foundation ✅ COMPLETE
> **Goal:** Calculate REAL metrics from accumulated data

### 1.1 P&L Calculation Pipeline ✅
- [x] Market resolutions tracked in `101_resolutions.sql`
- [x] P&L calculation in `aware_trader_pnl` table
- [x] Realized P&L per trader calculated
- [x] `scoring_job.py` integrates P&L into Smart Money Score

### 1.2 Real Sharpe Ratio Calculation ✅
- [x] Daily returns calculated per trader
- [x] Sharpe ratio in `aware_trader_pnl.sharpe_ratio`
- [x] Used in Smart Money Score weighting

### 1.3 Win Rate Calculation ✅
- [x] Tracks trades where trader was right vs wrong
- [x] `win_rate = winning_trades / total_resolved_trades`
- [x] Available in API `/api/leaderboard`

### 1.4 Data Quality Monitoring ✅
- [x] `/api/monitoring` endpoint for pipeline health
- [x] `/api/monitoring/daily` for daily stats
- [x] Ingestion metrics tracked in `aware_ingestion_metrics`

**Status:** Real P&L, Sharpe, win rates in dashboard

---

## Phase 2: Intelligence Layer ✅ MOSTLY COMPLETE
> **Goal:** Meaningful trader classification and ML

### 2.1 Category Classification ✅
- [x] `market_classifier.py` tags markets (CRYPTO, POLITICS, SPORTS, etc.)
- [x] Per-category performance tracked
- [x] Category-specific indices enabled (PSI-SPORTS, PSI-CRYPTO)

### 2.2 Strategy DNA Classification ✅
- [x] Arbitrageurs detected (complete-set ratio in `scoring_job.py`)
- [x] Strategy types: ARBITRAGEUR, MARKET_MAKER, DIRECTIONAL, HYBRID
- [x] Strategy confidence scoring
- [x] Stored in `aware_smart_money_scores.strategy_type`

### 2.3 Train ML Models 🟡 PARTIAL
- [x] Feature extraction pipeline (`ml/features/`)
- [x] Model training code (`ml/training/trainer.py`)
- [ ] Train XGBoost on production data (needs more data)
- [ ] Validate ML vs rule-based

### 2.4 Build Specialized Indices ✅
- [x] PSI-10: Top 10 overall (equal weight)
- [x] PSI-CRYPTO: Top crypto traders
- [x] PSI-POLITICS: Top political traders
- [x] PSI-SPORTS: Top sports traders
- [x] Excludes non-replicable strategies (ARBITRAGEUR, MARKET_MAKER)

**Status:** Indices built, ML infrastructure ready (needs training data)

---

## Phase 3: Product Polish 🟡 IN PROGRESS
> **Goal:** Production-ready public platform

### 3.1 Dashboard Enhancements 🟡
- [x] Next.js dashboard exists (`aware-fund/services/web/`)
- [x] Leaderboard display
- [x] Fund NAV visualization
- [ ] Trader detail pages with full history
- [ ] Performance charts (P&L over time)

### 3.2 Real-time Updates ⚪ NOT STARTED
- [ ] WebSocket for live trade feed
- [ ] Live score updates
- [ ] Push notifications for consensus signals

### 3.3 API Productization ✅ MOSTLY DONE
- [x] FastAPI with 40+ endpoints
- [x] OpenAPI/Swagger auto-generated
- [ ] Rate limiting
- [ ] API keys for pro users

### 3.4 User Accounts ⚪ NOT STARTED
- [ ] Authentication (wallet connect?)
- [ ] Saved watchlists
- [ ] Custom alerts
- [ ] Pro tier features

**Status:** API ready, dashboard basic, auth pending

---

## Phase 4: Fund Mechanics 🟡 IN PROGRESS
> **Goal:** Actually mirror trades and manage capital

### 4.1 Position Mirroring Engine ✅ BUILT
- [x] `FundTradeListener.java` - polls ClickHouse for trader trades
- [x] `FundPositionMirror.java` - executes scaled mirror trades
- [x] `IndexWeightProvider.java` - loads PSI index weights
- [x] Anti-front-running delay (configurable)
- [x] `FundRegistry.java` - manages multiple fund instances

### 4.2 Smart Contracts ⚪ NOT STARTED
- [ ] Fund deposit/withdrawal contract
- [ ] LP token (PSI-10 shares)
- [ ] Fee distribution
- [ ] Emergency withdrawal

### 4.3 Execution Infrastructure ✅ BUILT
- [x] Polymarket CLOB integration (executor-service)
- [x] Order routing via `ExecutorApiClient`
- [x] Paper trading simulation (`PaperExchangeSimulator`)
- [x] Position tracking in ClickHouse

### 4.4 Fund Operations ✅ MOSTLY DONE
- [x] NAV calculation (`/api/fund/nav`)
- [x] Performance tracking (`aware_fund_nav_history` table)
- [x] Execution logging (`aware_fund_executions` table)
- [ ] Rebalancing schedule automation
- [ ] Fee collection

**Status:** Java engine built, needs smart contracts

---

## Phase 5: Scale & Launch (Weeks 20+)
> **Goal:** Public launch

### 5.1 Security & Audits
- [ ] Smart contract audit
- [ ] Penetration testing
- [ ] Bug bounty program

### 5.2 Legal & Compliance
- [ ] Legal structure (offshore fund?)
- [ ] Terms of service
- [ ] Risk disclosures
- [ ] KYC requirements?

### 5.3 Go-to-Market
- [ ] Landing page
- [ ] Documentation
- [ ] Marketing content
- [ ] Community building

---

## Critical Path

```
NOW ──────────────────────────────────────────────────────────────> FUND LAUNCH

[Week 0]        [Week 4]         [Week 8]         [Week 12]        [Week 20]
    │               │                │                │                │
    ▼               ▼                ▼                ▼                ▼
Start           Real P&L         ML Models       Public API       Fund Live
Ingestion       Sharpe/Win       Trained         User Accounts    Deposits
    │               │                │                │                │
    └───────────────┴────────────────┴────────────────┴────────────────┘
         DATA ACCUMULATION              INTELLIGENCE            FUND OPS
```

---

## Resource Requirements

| Phase | Duration | Effort | Dependencies |
|-------|----------|--------|--------------|
| Phase 0 | 1 week | Low | None |
| Phase 1 | 4 weeks | Medium | TIME (data accumulation) |
| Phase 2 | 4 weeks | High | Phase 1 complete |
| Phase 3 | 4 weeks | Medium | Phase 2 complete |
| Phase 4 | 8 weeks | Very High | Phase 3 + smart contract expertise |
| Phase 5 | 4+ weeks | High | Phase 4 + legal/audit |

**Total estimated timeline: 5-6 months to fund launch**

---

## Quick Wins (Can Do Today)

1. **Start the ingestor** - Every day counts
2. **Research Polymarket market resolution API** - Needed for P&L
3. **Set up monitoring** - Know when things break
4. **Backfill historical data** - If API allows

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Polymarket API changes | High | Abstract client, monitor changes |
| Insufficient data quality | High | Data validation, alerts |
| ML doesn't beat rule-based | Medium | Rule-based is good enough MVP |
| Smart contract risk | Critical | Audits, gradual rollout |
| Regulatory issues | Critical | Legal consultation early |

---

## Next Immediate Action

**RIGHT NOW:**
```bash
# Ensure Java ingestor is running
cd /path/to/ingestor-service
mvn spring-boot:run -Dspring-boot.run.profiles=develop

# Or via Docker
docker-compose up -d ingestor
```

**Then monitor:**
```sql
SELECT
  toDate(ts) as date,
  count() as trades,
  uniqExact(username) as traders,
  sum(notional) as volume
FROM polybot.aware_global_trades
GROUP BY date
ORDER BY date DESC
```

---

*The gap between POC and real product is mostly TIME + fund mechanics engineering.*
