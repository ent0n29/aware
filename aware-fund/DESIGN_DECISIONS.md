# AWARE FUND - Design Decisions

## Strategic Choices & Rationale

**Version:** 0.1
**Status:** Living Document
**Last Updated:** December 2024

---

## Decision Log

| # | Decision | Choice | Status |
|---|----------|--------|--------|
| 1 | Open Protocol vs Managed | **Managed** (open-source intelligence layer later) | ✅ Decided |
| 2 | Revenue sharing with traders | **Yes** - 20% of allocation mgmt fee | ✅ Decided |
| 3 | MVP strategy | **Analytics first**, then fund | ✅ Decided |
| 4 | Front-running mitigation | Revenue sharing + diverse allocation | ✅ Decided |
| 5 | Pricing tiers | Free / Pro / Fund / Whale | ✅ Decided |

---

## 1. Open Protocol vs Managed Product

### The Question

Should AWARE be:
- **(A) Open Protocol** - Decentralized, permissionless, anyone can create indices
- **(B) Managed Product** - We control the indices, curate traders, charge fees
- **(C) Hybrid** - Open data/analytics, managed fund

### Decision: **B → C (Managed first, then Hybrid)**

### Rationale

| Approach | Pros | Cons |
|----------|------|------|
| **A) Open Protocol** | Decentralized, permissionless, community-driven, harder to shut down | Harder to monetize, quality control issues, competitors fork it |
| **B) Managed Product** | Control quality, clear monetization, brand trust, can iterate fast | Centralized risk, regulatory target, limited scale |
| **C) Hybrid** | Best of both - open data/analytics, managed fund | Complex to build, unclear boundaries |

**Strategy:**
1. **Phase 1:** Managed product to prove the model and establish trust
2. **Phase 2:** Open-source the Trader Intelligence layer once we have data moat
3. **Phase 3:** Keep fund operations managed for regulatory clarity

This gives us speed-to-market while preserving optionality.

---

## 2. The Front-Running Problem

### The Problem

If top traders know they're in the index, they could:
- **Exploit it:** Trade ahead of the fund's mirroring
- **Poison it:** Intentionally lose to hurt the index
- **Demand payment:** "Pay me or I'll sabotage"

### Decision: **Multi-Layered Defense**

| Strategy | Implementation | Priority |
|----------|----------------|----------|
| **Revenue sharing** | Pay top traders 20% of their allocation's mgmt fee | ✅ Primary |
| **Diverse allocation** | 50 traders at 2% each vs 10 at 10% | ✅ Primary |
| **Anti-gaming detection** | Flag unusual behavior changes after inclusion | 🟡 Secondary |
| **Delayed signals** | 5-15 min delay on position updates | 🟡 Optional |
| **Stealth mode** | Don't publish exact weights publicly | ⚪ Future |

**Key Insight:** Revenue sharing transforms the adversarial dynamic into an aligned one. When traders earn more if the fund succeeds, they're incentivized to perform, not sabotage.

---

## 3. Revenue Sharing with Top Traders

### Decision: **Yes - The Trader Incentive Program**

See `docs/TRADER_INCENTIVE_PROGRAM.md` for full specification.

### Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                     TRADER INCENTIVE FLYWHEEL                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Top Trader gets included in PSI-10                            │
│           ↓                                                      │
│   AWARE mirrors their trades with $10M AUM                      │
│           ↓                                                      │
│   Trader receives 20% of management fee on their allocation     │
│   = 10% weight × $10M × 0.5% × 20% = $1,000/year               │
│           ↓                                                      │
│   Trader is INCENTIVIZED to:                                    │
│   • Stay in the index (keep performing)                         │
│   • NOT front-run (they benefit from fund success)              │
│   • Promote AWARE (more AUM = more income)                      │
│           ↓                                                      │
│   More traders want to be included → Better competition         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Revenue Share Structure

| Index | Trader Revenue Share | Example (at $100M AUM) |
|-------|---------------------|------------------------|
| PSI-10 | 20% of allocation's mgmt fee | ~$10,000/year per trader |
| PSI-CRYPTO | 15% | ~$3,000/year |
| PSI-POLITICS | 15% | ~$3,000/year |
| PSI-ALPHA | 25% | Premium for edge traders |

---

## 4. MVP Strategy

### Decision: **Analytics First, Then Fund**

### Rationale

| Approach | Pros | Cons |
|----------|------|------|
| **Fund first** | Immediate revenue, proves core value | Higher regulatory risk, harder to iterate |
| **Analytics first** | Build audience, validate data, lower risk | Delayed revenue, users may not convert |

**We chose Analytics First because:**
1. Builds trust and audience before asking for money
2. Validates the Trader Intelligence engine
3. Lower regulatory complexity initially
4. Creates content marketing flywheel (leaderboard data)
5. Traders can see value before joining program

### MVP Timeline

| Tier | Features | Timeline |
|------|----------|----------|
| **Alpha (Internal)** | Global ingestion, basic leaderboard, manual curation | 4-6 weeks |
| **Beta (Invite-only)** | Smart Money Score, public profiles, Pro subscriptions | 8-12 weeks |
| **V1 (Public)** | PSI-10 fund, deposits/withdrawals, auto-mirroring | 16-20 weeks |

---

## 5. Killer Features to Differentiate

### Prioritized Feature List

| Feature | Description | Status | Differentiation |
|---------|-------------|--------|-----------------|
| **Smart Money Score** | Composite ranking algorithm | ✅ Built | Core product |
| **Strategy DNA** | ML-based fingerprinting of trader styles | ✅ Built | "Know WHO you're investing in" |
| **Consensus Signals** | When 5+ top traders agree on same position | ✅ Built | "The wisdom of the best" |
| **Insider Detection** | Flag unusual activity before news | ✅ Built | "See smart money first" |
| **Hidden Alpha Discovery** | Find undiscovered talented traders | ✅ Built | "Early edge" |
| **Edge Decay Monitoring** | Track when traders lose their edge | ✅ Built | "Know when to exit" |
| **Trader Revenue Share** | Pay traders for being in index | ⚪ Future | Unique in market |
| **Anti-Correlation Index** | Traders uncorrelated to each other | ⚪ Future | "True diversification" |
| **Hot Hand Alerts** | Real-time streak notifications | ⚪ Future | "Ride the momentum" |
| **Trader Tournaments** | Gamified competition for inclusion | ⚪ Future | "Become the next gabagool" |

---

## 6. Pricing Architecture

### Decision: Four-Tier Model

```
┌─────────────────────────────────────────────────────────────────┐
│                      PRICING TIERS                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  FREE                                                            │
│  ────                                                            │
│  • Top 25 leaderboard                                           │
│  • Basic trader stats (P&L, win rate)                           │
│  • 7-day delayed data                                           │
│                                                                  │
│  PRO ($49/month or $399/year)                                   │
│  ───                                                             │
│  • Full leaderboard (all traders)                               │
│  • Real-time trader alerts                                      │
│  • Strategy classification                                       │
│  • API access (1,000 calls/day)                                 │
│  • Export data                                                   │
│                                                                  │
│  FUND (0.5% AUM + 10% performance)                              │
│  ────                                                            │
│  • All Pro features                                              │
│  • Deposit into PSI indices                                     │
│  • Auto-mirror execution                                        │
│  • Priority support                                              │
│                                                                  │
│  WHALE ($5,000/year or $100k+ AUM)                              │
│  ─────                                                           │
│  • Custom index construction                                    │
│  • Direct trader introductions                                  │
│  • White-glove onboarding                                       │
│  • Dedicated Slack channel                                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Revenue Model (Year 3 Target)

| Revenue Stream | Target |
|----------------|--------|
| Management fees (0.5% AUM) | $500K |
| Performance fees (10% of profits) | $1.5M |
| Pro subscriptions ($49/mo × 10k users) | $5.9M |
| API/Data licensing | $500K |
| **Total** | **$8.4M/year** |

---

## 7. Partnership Strategy

### Priority Partners

| Partner | Value We Provide | Value They Provide | Priority |
|---------|------------------|-------------------|----------|
| **Polymarket** | Liquidity, new users, legitimization | Data access, promotion, trust | ✅ Critical |
| **Top Traders** | Revenue share, status, dashboard | Performance, promotion | ✅ Critical |
| **Crypto Media** | Exclusive leaderboard data, stories | Exposure, credibility | 🟡 High |
| **Trading Communities** | Early access, special features | Distribution, feedback | 🟡 High |
| **DeFi Protocols** | Integration opportunities | Yield, liquidity | ⚪ Future |

---

## 8. Competitive Moat

### What Makes AWARE Defensible

| Asset | Why It's Defensible |
|-------|---------------------|
| **Data** | First to collect comprehensive trader profiles at scale |
| **Algorithms** | Strategy classification, edge detection, Smart Money Score |
| **Execution** | Already built the trading infrastructure |
| **Network Effects** | More AUM → better execution → better returns → more AUM |
| **Brand** | "The Vanguard of prediction markets" |
| **Trader Relationships** | Revenue sharing creates loyalty |

### Competitive Comparison

| Platform | Tracks Traders? | Auto-Mirror? | Pays Traders? | Prediction Markets? |
|----------|-----------------|--------------|---------------|---------------------|
| eToro CopyTrader | ✅ | ✅ | ✅ (fixed fee) | ❌ |
| Collective2 | ✅ | ✅ | ✅ (subscription) | ❌ |
| Darwinex | ✅ | ✅ | ✅ (performance) | ❌ |
| **AWARE** | ✅ | ✅ | ✅ (AUM-based) | ✅ **First** |

---

## 9. The Vanguard Philosophy

> *"The most successful fintech products often win on trust and UX, not just features."*

Vanguard won by being:
- **Boringly reliable** - Not flashy, just works
- **Aligned with customers** - Low fees, index funds
- **Transparent** - Clear about what you're getting
- **Patient** - Long-term focus over short-term gains

AWARE should embody the same:
- "We just mirror the best, transparently, cheaply"
- No hidden fees, no complex strategies
- Trust through transparency
- Aligned incentives (revenue share with traders)

---

## Open Questions (To Be Decided)

| Question | Options | Notes |
|----------|---------|-------|
| Legal structure | LLC? DAO? Offshore? | Need legal counsel |
| Token economics | Native token? | Could enable governance |
| Multi-platform | Just Polymarket or others? | Kalshi, PredictIt, etc. |
| Mobile app | Web only or mobile? | Resource intensive |

---

*This document captures key strategic decisions for AWARE FUND. Decisions may evolve based on market feedback and legal review.*
