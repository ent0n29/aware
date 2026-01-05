"""
AWARE Analytics Package

Complete analytics suite for the AWARE Fund smart money index.

Modules:
- psi_index: PSI Index construction (PSI-10, PSI-25, PSI-CRYPTO, PSI-POLITICS)
- hidden_alpha: Hidden trader discovery (gems, rising stars, specialists)
- strategy_dna: Strategy fingerprinting and clustering
- consensus: Smart money consensus detection
- edge_decay: Edge decay monitoring and alerts
- alerts: Real-time alerting system
- scoring_job: Smart Money Score calculation

Usage:
    from analytics import (
        PSIIndexBuilder, IndexType,
        HiddenAlphaDiscovery, DiscoveryType,
        StrategyDNAAnalyzer,
        ConsensusDetector,
        EdgeDecayDetector,
        AlertManager,
    )
"""

# PSI Index Construction
from .psi_index import (
    PSIIndexBuilder,
    IndexType,
    WeightingMethod,
    RebalanceFrequency,
    PSIIndex,
    IndexConstituent,
    IndexConfig,
    INDEX_CONFIGS,
    build_all_indices,
)

# Hidden Alpha Discovery
from .hidden_alpha import (
    HiddenAlphaDiscovery,
    DiscoveryType,
    DiscoveryConfig,
    HiddenTrader,
)

# Strategy DNA / Fingerprinting
from .strategy_dna import (
    StrategyDNAAnalyzer,
    StrategyDNA,
    StrategyCluster,
    TimingStyle,
    SizingStyle,
    HoldingStyle,
    EntryStyle,
    RiskStyle,
)

# Consensus Signal Detection
from .consensus import (
    ConsensusDetector,
    ConsensusSignal,
    ConsensusStrength,
    ConsensusDirection,
    ConsensusConfig,
    run_consensus_scan,
)

# Edge Decay Monitoring
from .edge_decay import (
    EdgeDecayDetector,
    DecayAlert,
    DecaySignal,
    DecayType,
    DecayConfig,
    run_edge_decay_scan,
)

# Alerting System
from .alerts import (
    AlertManager,
    Alert,
    AlertType,
    AlertPriority,
    AlertChannel,
    AlertRule,
)

# Anomaly Detection
from .anomaly_detection import (
    AnomalyDetector,
    AnomalyAlert,
    AnomalyType,
    AnomalySeverity,
    IntegrityScore,
    AnomalyConfig,
    run_anomaly_scan,
)

# Edge Persistence Prediction
from .edge_persistence import (
    EdgePersistencePredictor,
    PersistencePrediction,
    PersistenceRisk,
    StrategyDurability,
    PersistenceConfig,
    run_persistence_prediction,
)

__version__ = "1.0.0"
__all__ = [
    # PSI Index
    "PSIIndexBuilder",
    "IndexType",
    "WeightingMethod",
    "RebalanceFrequency",
    "PSIIndex",
    "IndexConstituent",
    "IndexConfig",
    "INDEX_CONFIGS",
    "build_all_indices",
    # Hidden Alpha
    "HiddenAlphaDiscovery",
    "DiscoveryType",
    "DiscoveryConfig",
    "HiddenTrader",
    # Strategy DNA
    "StrategyDNAAnalyzer",
    "StrategyDNA",
    "StrategyCluster",
    "TimingStyle",
    "SizingStyle",
    "HoldingStyle",
    "EntryStyle",
    "RiskStyle",
    # Consensus
    "ConsensusDetector",
    "ConsensusSignal",
    "ConsensusStrength",
    "ConsensusDirection",
    "ConsensusConfig",
    "run_consensus_scan",
    # Edge Decay
    "EdgeDecayDetector",
    "DecayAlert",
    "DecaySignal",
    "DecayType",
    "DecayConfig",
    "run_edge_decay_scan",
    # Alerts
    "AlertManager",
    "Alert",
    "AlertType",
    "AlertPriority",
    "AlertChannel",
    "AlertRule",
    # Anomaly Detection
    "AnomalyDetector",
    "AnomalyAlert",
    "AnomalyType",
    "AnomalySeverity",
    "IntegrityScore",
    "AnomalyConfig",
    "run_anomaly_scan",
    # Edge Persistence
    "EdgePersistencePredictor",
    "PersistencePrediction",
    "PersistenceRisk",
    "StrategyDurability",
    "PersistenceConfig",
    "run_persistence_prediction",
]
