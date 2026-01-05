# AWARE FUND - ML/AI Strategy

## Where Machine Learning Creates Value

**Version:** 0.1
**Status:** Design Draft

---

## Overview

AWARE FUND has **7 core ML/AI opportunities**, ranging from essential (must-have for differentiation) to advanced (future competitive moat).

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      ML/AI OPPORTUNITY MAP                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  PRIORITY: ESSENTIAL (Differentiation)                                  │
│  ══════════════════════════════════════                                 │
│  1. Strategy DNA / Trader Fingerprinting                                │
│  2. Smart Money Score (ML-enhanced)                                     │
│  3. Anomaly & Gaming Detection                                          │
│                                                                          │
│  PRIORITY: HIGH VALUE (Competitive Edge)                                │
│  ═══════════════════════════════════════                                │
│  4. Edge Persistence Prediction                                         │
│  5. Optimal Portfolio Construction                                      │
│                                                                          │
│  PRIORITY: ADVANCED (Future Moat)                                       │
│  ════════════════════════════════                                       │
│  6. Consensus Signal Detection                                          │
│  7. Market Context Understanding (NLP)                                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Strategy DNA / Trader Fingerprinting

### What It Does
Automatically classify each trader's strategy type and create a unique "fingerprint" of their trading behavior.

### Why It Matters
- Users want to know WHO they're investing in
- Enables strategy-specific indices (PSI-ARBITRAGE, PSI-DIRECTIONAL)
- Detects style drift (trader changing behavior)
- Marketing gold: "Invest in 3 market-makers, 4 directional traders, 3 arbitrageurs"

### ML Approach

```
INPUT FEATURES (per trader)
═══════════════════════════
Temporal:
├── Avg hold time (minutes/hours/days)
├── Trading frequency (trades/day)
├── Time-of-day patterns
└── Response to market events

Position:
├── Avg position size
├── Position concentration (few markets vs many)
├── Long/short bias
└── Complete-set ratio (hedged vs directional)

Execution:
├── Maker vs taker ratio
├── Spread capture (entry vs mid)
├── Slippage patterns
└── Order-to-fill latency

Market Selection:
├── Category preference (crypto/politics/sports)
├── Volatility preference
├── Liquidity preference
└── Time-to-expiry preference

CLUSTERING ALGORITHM
════════════════════
• K-means or HDBSCAN for initial clustering
• Soft clustering (GMM) for traders with mixed styles
• Hierarchical for nested categories

OUTPUT: STRATEGY TYPES
══════════════════════
├── ARBITRAGEUR
│   └── Complete-set, cross-market, statistical arb
├── MARKET_MAKER
│   └── Two-sided quotes, inventory management
├── DIRECTIONAL_FUNDAMENTAL
│   └── Long holds, research-driven
├── DIRECTIONAL_MOMENTUM
│   └── Trend following, technical
├── EVENT_DRIVEN
│   └── News trading, catalyst-focused
├── SCALPER
│   └── High frequency, small edge
└── HYBRID
    └── Multiple strategies combined
```

### Implementation

```python
class TraderFingerprint:
    """
    ML model to classify trader strategies
    """

    def extract_features(self, trader_id: str) -> pd.DataFrame:
        """Extract behavioral features from trade history"""
        trades = self.get_trades(trader_id)

        return {
            # Temporal
            'avg_hold_minutes': trades.hold_time.mean(),
            'trades_per_day': len(trades) / trades.days_active,
            'night_trading_ratio': trades[trades.hour < 6].count() / len(trades),

            # Position
            'avg_position_usd': trades.notional.mean(),
            'market_concentration': trades.market_id.nunique() / len(trades),
            'complete_set_ratio': self.calculate_complete_set_ratio(trades),

            # Execution
            'maker_ratio': trades[trades.is_maker].count() / len(trades),
            'avg_spread_capture': (trades.mid - trades.price).mean(),

            # Market selection
            'crypto_ratio': trades[trades.category == 'crypto'].count() / len(trades),
            'avg_time_to_expiry': trades.seconds_to_end.mean(),
        }

    def classify(self, features: pd.DataFrame) -> dict:
        """Classify trader into strategy type"""
        # Trained clustering model
        cluster = self.model.predict(features)
        confidence = self.model.predict_proba(features).max()

        return {
            'strategy_type': self.cluster_labels[cluster],
            'confidence': confidence,
            'sub_strategies': self.get_sub_strategies(features),
            'fingerprint_vector': self.model.transform(features)  # For similarity
        }
```

### Timeline
- **Phase 2 (Q2 2025)** - MVP with rule-based classification
- **Phase 3 (Q3 2025)** - Full ML clustering with confidence scores

---

## 2. Smart Money Score (ML-Enhanced)

### Current Design (Rule-Based)

```
Score = 0.40 × Profitability + 0.30 × Risk-Adjusted + 0.20 × Consistency + 0.10 × Track Record
```

### ML Enhancement

Instead of fixed weights, **learn optimal weights** from data:

```
APPROACH: Supervised Learning
═════════════════════════════

Target Variable:
• Future 90-day performance (Sharpe ratio)

Features:
• All components of current score
• Strategy fingerprint
• Market regime indicators
• Historical score trajectory

Model:
• Gradient Boosted Trees (XGBoost/LightGBM)
• Or Neural Network for non-linear patterns

Output:
• Predicted future Sharpe
• Confidence interval
• Feature importance (explainability)
```

### Why ML is Better

| Aspect | Rule-Based | ML-Enhanced |
|--------|------------|-------------|
| Weights | Fixed (0.4, 0.3, 0.2, 0.1) | Learned from data |
| Interactions | None | Captures feature interactions |
| Adaptation | Manual tuning | Retrains on new data |
| Non-linearity | Linear combination | Can model complex patterns |

### Implementation

```python
class SmartMoneyScoreML:
    """
    ML-enhanced Smart Money Score
    """

    def train(self, historical_data: pd.DataFrame):
        """Train on historical trader performance"""
        # Features: current metrics
        X = historical_data[[
            'pnl_percentile', 'sharpe_ratio', 'win_rate',
            'consistency_score', 'days_active', 'trade_count',
            'strategy_type', 'market_regime'
        ]]

        # Target: future 90-day Sharpe
        y = historical_data['future_90d_sharpe']

        self.model = LGBMRegressor(
            objective='regression',
            n_estimators=100,
            learning_rate=0.1
        )
        self.model.fit(X, y)

    def score(self, trader_features: dict) -> dict:
        """Predict Smart Money Score"""
        prediction = self.model.predict([trader_features])[0]

        # Convert to 0-100 scale
        score = self.normalize_to_100(prediction)

        return {
            'smart_money_score': score,
            'predicted_sharpe': prediction,
            'confidence': self.calculate_confidence(trader_features),
            'top_factors': self.get_feature_importance(trader_features)
        }
```

### Timeline
- **Phase 2** - Rule-based score (V1)
- **Phase 3** - ML-enhanced with learned weights (V2)

---

## 3. Anomaly & Gaming Detection

### What It Detects

```
ANOMALY TYPES
═════════════

1. WASH TRADING
   • Same entity trading with itself
   • Circular trades to inflate volume
   • Detection: Graph analysis of trade counterparties

2. INDEX GAMING
   • Behavior change after index inclusion
   • Intentional losses to manipulate
   • Detection: Pre/post inclusion behavioral comparison

3. FRONT-RUNNING
   • Trading ahead of known fund flows
   • Unusual timing patterns
   • Detection: Correlation with fund activity

4. PUMP & DUMP
   • Artificial volume spikes
   • Coordinated buying then selling
   • Detection: Volume/price pattern analysis

5. SYBIL ATTACKS
   • Multiple wallets controlled by same entity
   • Spread across to avoid detection
   • Detection: Behavioral clustering, timing analysis
```

### ML Approach

```
MODEL: Isolation Forest + Autoencoder Hybrid
═══════════════════════════════════════════

Isolation Forest:
• Unsupervised anomaly detection
• Flags statistically unusual behavior
• Fast, interpretable

Autoencoder:
• Learn "normal" trading patterns
• High reconstruction error = anomaly
• Catches subtle deviations

Ensemble:
• Combine both for robustness
• Different failure modes
• Reduces false positives
```

### Implementation

```python
class AnomalyDetector:
    """
    Detect gaming, manipulation, and anomalies
    """

    def __init__(self):
        self.isolation_forest = IsolationForest(contamination=0.01)
        self.autoencoder = self.build_autoencoder()

    def detect_anomalies(self, trader_id: str) -> dict:
        """Run anomaly detection on trader"""
        features = self.extract_behavioral_features(trader_id)

        # Isolation Forest score
        if_score = self.isolation_forest.decision_function([features])[0]

        # Autoencoder reconstruction error
        reconstruction = self.autoencoder.predict([features])
        ae_error = np.mean((features - reconstruction) ** 2)

        # Combine scores
        anomaly_score = self.combine_scores(if_score, ae_error)

        return {
            'anomaly_score': anomaly_score,
            'is_anomalous': anomaly_score > self.threshold,
            'anomaly_type': self.classify_anomaly_type(features),
            'suspicious_patterns': self.get_suspicious_patterns(features)
        }

    def detect_index_gaming(self, trader_id: str, inclusion_date: datetime) -> dict:
        """Detect behavior change after index inclusion"""
        pre_features = self.extract_features(trader_id, end_date=inclusion_date)
        post_features = self.extract_features(trader_id, start_date=inclusion_date)

        # Statistical test for distribution shift
        drift_score = self.calculate_drift(pre_features, post_features)

        return {
            'behavior_drift_score': drift_score,
            'is_gaming': drift_score > self.gaming_threshold,
            'changed_dimensions': self.identify_changed_features(pre_features, post_features)
        }
```

### Timeline
- **Phase 2** - Rule-based flags (volume spikes, timing)
- **Phase 3** - Full ML anomaly detection
- **Phase 4** - Real-time monitoring with alerting

---

## 4. Edge Persistence Prediction

### The Problem
Past performance doesn't guarantee future results. Some traders have **persistent edge**, others got lucky.

### What It Predicts
- Probability that a trader's edge will persist
- Expected performance degradation over time
- Optimal "sell-by date" for index inclusion

### ML Approach

```
SURVIVAL ANALYSIS + CLASSIFICATION
══════════════════════════════════

Question: "How long will this trader remain profitable?"

Features:
├── Historical Sharpe trajectory (trend, volatility)
├── Strategy type (some decay faster)
├── Market concentration (niche vs broad)
├── Edge source (execution vs alpha)
├── Competitive dynamics (others copying?)
└── Market regime sensitivity

Models:
├── Cox Proportional Hazards (time-to-event)
├── Random Survival Forest
└── Gradient Boosted Survival

Output:
├── Survival curve (probability of staying profitable)
├── Median time-to-decay
├── Hazard ratio by feature
└── Confidence bands
```

### Implementation

```python
class EdgePersistenceModel:
    """
    Predict how long a trader's edge will persist
    """

    def train(self, historical_traders: pd.DataFrame):
        """Train on historical trader trajectories"""
        # Event: trader becomes unprofitable
        # Duration: months of profitability

        self.model = RandomSurvivalForest(
            n_estimators=100,
            min_samples_split=10
        )
        self.model.fit(
            X=historical_traders[self.feature_cols],
            y=historical_traders[['duration', 'event']]
        )

    def predict_persistence(self, trader_features: dict) -> dict:
        """Predict edge persistence for a trader"""
        survival_function = self.model.predict_survival_function([trader_features])

        return {
            'prob_profitable_6mo': survival_function(6),
            'prob_profitable_12mo': survival_function(12),
            'median_persistence_months': self.get_median_survival(survival_function),
            'risk_factors': self.get_risk_factors(trader_features),
            'confidence': self.calculate_confidence(trader_features)
        }
```

### Use Cases
- Weight traders by persistence probability in index
- Early warning for index rebalancing
- Premium feature for Pro users

### Timeline
- **Phase 3** - Basic persistence scoring
- **Phase 4** - Full survival analysis model

---

## 5. Optimal Portfolio Construction

### The Problem
How to optimally weight traders in an index? Equal weight is simple but suboptimal.

### ML Approach

```
PORTFOLIO OPTIMIZATION + REINFORCEMENT LEARNING
═══════════════════════════════════════════════

Classical Approach (Markowitz):
• Mean-variance optimization
• Maximize Sharpe ratio
• Constraint: weights sum to 1

ML Enhancement:
• Predict expected returns (not just historical)
• Predict covariance matrix (dynamic)
• Account for execution costs & capacity

Advanced (RL):
• Learn optimal rebalancing policy
• Account for market impact
• Adapt to regime changes
```

### Implementation

```python
class IndexOptimizer:
    """
    ML-enhanced portfolio optimization
    """

    def optimize_weights(self, traders: List[str]) -> dict:
        """Calculate optimal index weights"""
        # Predict expected returns
        expected_returns = self.return_model.predict(traders)

        # Predict covariance (dynamic)
        cov_matrix = self.covariance_model.predict(traders)

        # Optimize with constraints
        result = minimize(
            fun=lambda w: -self.sharpe_ratio(w, expected_returns, cov_matrix),
            x0=np.ones(len(traders)) / len(traders),  # Start equal weight
            constraints=[
                {'type': 'eq', 'fun': lambda w: np.sum(w) - 1},  # Sum to 1
                {'type': 'ineq', 'fun': lambda w: w - 0.02},     # Min 2%
                {'type': 'ineq', 'fun': lambda w: 0.15 - w},     # Max 15%
            ]
        )

        return {
            'weights': dict(zip(traders, result.x)),
            'expected_sharpe': -result.fun,
            'expected_return': np.dot(result.x, expected_returns),
            'expected_vol': np.sqrt(result.x @ cov_matrix @ result.x)
        }
```

### Timeline
- **Phase 3** - Rule-based weights (equal, Sharpe-weighted)
- **Phase 4** - Mean-variance optimization
- **2026** - Full ML portfolio optimization

---

## 6. Consensus Signal Detection

### What It Does
Detect when multiple top traders converge on the same position - "the wisdom of the best."

### Why It Matters
- High conviction signal when smart money agrees
- Marketing: "5 of top 10 traders just bought YES on X"
- Premium alert feature for Pro users

### ML Approach

```
SIGNAL DETECTION + PATTERN RECOGNITION
══════════════════════════════════════

Real-time Monitoring:
• Track all top-N trader positions
• Detect clustering in same market/direction
• Score by trader quality and timing

Historical Validation:
• Backtest: Do consensus signals predict outcomes?
• Measure: Win rate, edge, false positive rate

Alert Generation:
• Threshold: X traders with combined score > Y
• Urgency scoring based on time-to-event
• Smart batching to avoid alert fatigue
```

### Implementation

```python
class ConsensusDetector:
    """
    Detect smart money consensus signals
    """

    def detect_consensus(self, market_id: str) -> dict:
        """Check for consensus among top traders"""
        # Get positions of top 50 traders in this market
        positions = self.get_top_trader_positions(market_id, top_n=50)

        # Calculate weighted consensus
        yes_weight = sum(
            p.size * self.smart_money_score(p.trader_id)
            for p in positions if p.direction == 'YES'
        )
        no_weight = sum(
            p.size * self.smart_money_score(p.trader_id)
            for p in positions if p.direction == 'NO'
        )

        total_weight = yes_weight + no_weight
        if total_weight < self.min_weight_threshold:
            return {'has_consensus': False}

        consensus_ratio = max(yes_weight, no_weight) / total_weight
        consensus_direction = 'YES' if yes_weight > no_weight else 'NO'

        return {
            'has_consensus': consensus_ratio > 0.7,
            'direction': consensus_direction,
            'strength': consensus_ratio,
            'participating_traders': len(positions),
            'total_smart_money_weight': total_weight,
            'historical_accuracy': self.get_historical_accuracy(consensus_ratio)
        }
```

### Timeline
- **Phase 3** - Basic consensus detection
- **Phase 4** - ML-validated signals with accuracy tracking

---

## 7. Market Context Understanding (NLP)

### What It Does
Use NLP to understand market context, news, and event timing.

### Applications

```
NLP USE CASES
═════════════

1. MARKET CATEGORIZATION
   • Auto-tag markets by topic
   • Extract entities (people, companies, events)
   • Improve search and filtering

2. EVENT EXTRACTION
   • Identify resolution triggers from descriptions
   • Predict optimal trading windows
   • Alert: "This market resolves based on X announcement"

3. NEWS CORRELATION
   • Monitor news feeds for relevant events
   • Correlate trader activity with news timing
   • Detect informed trading

4. SENTIMENT ANALYSIS
   • Analyze market comments/discussion
   • Detect crowd sentiment vs smart money
   • Contrarian signals
```

### Implementation

```python
class MarketContextNLP:
    """
    NLP for market understanding
    """

    def __init__(self):
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.ner_model = pipeline('ner', model='dbmdz/bert-large-cased-finetuned-conll03-english')

    def analyze_market(self, market: dict) -> dict:
        """Extract context from market description"""
        description = market['description']

        # Categorize
        embedding = self.embedding_model.encode(description)
        category = self.classifier.predict(embedding)

        # Extract entities
        entities = self.ner_model(description)

        # Extract resolution trigger
        resolution_trigger = self.extract_resolution_trigger(description)

        return {
            'category': category,
            'sub_categories': self.get_sub_categories(embedding),
            'entities': {
                'people': [e for e in entities if e['entity'] == 'PER'],
                'organizations': [e for e in entities if e['entity'] == 'ORG'],
                'events': [e for e in entities if e['entity'] == 'EVENT']
            },
            'resolution_trigger': resolution_trigger,
            'related_markets': self.find_similar_markets(embedding)
        }
```

### Timeline
- **Phase 4** - Basic categorization
- **2026** - Full NLP pipeline with news integration

---

## ML Infrastructure Requirements

### Compute

| Component | Requirement | Phase |
|-----------|-------------|-------|
| Feature extraction | ClickHouse queries | Phase 2 |
| Model training | GPU (can use cloud) | Phase 2 |
| Batch inference | Daily job | Phase 2 |
| Real-time inference | Low-latency API | Phase 3 |

### Data Pipeline

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ML DATA PIPELINE                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ClickHouse ──▶ Feature Store ──▶ Training Pipeline ──▶ Model Registry │
│      │              │                    │                    │         │
│      │              ▼                    ▼                    ▼         │
│      │         Batch Features      MLflow/W&B           Model Serving  │
│      │              │                    │                    │         │
│      └──────────────┴────────────────────┴────────────────────┘         │
│                              │                                           │
│                              ▼                                           │
│                      Monitoring & Retraining                            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Tech Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Feature Store | Feast or custom | Consistent features |
| Training | Python + PyTorch/sklearn | Flexibility |
| Experiment Tracking | MLflow or W&B | Reproducibility |
| Model Serving | FastAPI or TensorFlow Serving | Low latency |
| Monitoring | Evidently AI | Drift detection |

---

## Priority Matrix

| ML Feature | Business Value | Technical Complexity | Priority |
|------------|----------------|---------------------|----------|
| Strategy Fingerprinting | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | **P0 - MVP** |
| Anomaly Detection | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | **P0 - MVP** |
| Smart Money Score ML | ⭐⭐⭐⭐ | ⭐⭐ | **P1 - V1** |
| Edge Persistence | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | **P1 - V1** |
| Consensus Signals | ⭐⭐⭐ | ⭐⭐ | **P2 - V2** |
| Portfolio Optimization | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | **P2 - V2** |
| NLP Context | ⭐⭐⭐ | ⭐⭐⭐⭐ | **P3 - Future** |

---

## Summary: Where AI Creates Moat

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                          │
│   WITHOUT ML:                                                           │
│   • Simple leaderboard (anyone can build)                               │
│   • Fixed scoring rules (easy to copy)                                  │
│   • No gaming protection (vulnerable)                                   │
│                                                                          │
│   WITH ML:                                                               │
│   • Deep trader understanding (Strategy DNA)                            │
│   • Predictive scoring (who WILL perform)                               │
│   • Gaming detection (protected)                                        │
│   • Optimal portfolios (better returns)                                 │
│   • Unique insights (consensus, edge decay)                             │
│                                                                          │
│   ML IS THE MOAT.                                                       │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

*This document outlines the ML/AI strategy for AWARE FUND. Implementation details will evolve based on data availability and model performance.*
