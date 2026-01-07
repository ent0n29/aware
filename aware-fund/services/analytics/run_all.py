#!/usr/bin/env python3
"""
AWARE Analytics - Run All Jobs

Orchestrates running all analytics jobs in sequence:
1. Smart Money Score calculation
2. PSI Index construction
3. Hidden Alpha discovery
4. Consensus detection
5. Edge decay scanning
6. Alert generation

Usage:
    python run_all.py                  # Run once
    python run_all.py --continuous     # Run every hour

Environment Variables:
    CLICKHOUSE_HOST - ClickHouse host (default: localhost)
    CLICKHOUSE_PORT - ClickHouse port (default: 8123)
    CLICKHOUSE_DATABASE - Database name (default: polybot)
"""

import os
import sys
import time
import logging
import argparse
from datetime import datetime

import clickhouse_connect

# Configure logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('aware-analytics')


def get_clickhouse_client():
    """Get ClickHouse client"""
    return clickhouse_connect.get_client(
        host=os.getenv('CLICKHOUSE_HOST', 'localhost'),
        port=int(os.getenv('CLICKHOUSE_PORT', '8123')),
        database=os.getenv('CLICKHOUSE_DATABASE', 'polybot')
    )


def run_smart_money_scoring(ch_client) -> dict:
    """Run Smart Money Score calculation using ML ensemble with rule-based fallback."""
    logger.info("Running Smart Money Score calculation...")
    start = time.time()

    from clickhouse_client import ClickHouseClient
    aware_client = ClickHouseClient()

    # Try ML scoring first
    try:
        from ml_scoring_job import MLScoringJob
        import torch

        # Detect best device for inference
        device = 'cpu'
        if torch.cuda.is_available():
            device = 'cuda'
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            device = 'mps'

        job = MLScoringJob(
            aware_client,
            model_path="ml/checkpoints/aware_ensemble.pt",
            device=device
        )

        # Check if ML model is loaded
        if job.ensemble is not None:
            scored_count = job.run(min_trades=5, max_traders=10000)
            elapsed = time.time() - start
            logger.info(f"ML scored {scored_count} traders in {elapsed:.1f}s (device={device})")

            return {
                'status': 'success',
                'method': 'ml_ensemble',
                'traders_scored': scored_count,
                'device': device,
                'elapsed_seconds': elapsed
            }
        else:
            logger.warning("ML model not available, falling back to rule-based scoring")

    except ImportError as e:
        logger.warning(f"ML scoring import failed, using rule-based: {e}")
    except Exception as e:
        logger.warning(f"ML scoring failed, using rule-based fallback: {e}")
        import traceback
        traceback.print_exc()

    # Fallback to rule-based scoring
    try:
        from scoring_job import ScoringJob

        job = ScoringJob(aware_client)
        scored_count = job.run(min_trades=5, max_traders=10000)

        elapsed = time.time() - start
        logger.info(f"Rule-based scored {scored_count} traders in {elapsed:.1f}s")

        return {
            'status': 'success',
            'method': 'rule_based',
            'traders_scored': scored_count,
            'elapsed_seconds': elapsed
        }

    except Exception as e:
        logger.error(f"Smart Money Scoring failed completely: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'error': str(e)}


def run_psi_index_building(ch_client) -> dict:
    """Build all PSI indices"""
    logger.info("Building PSI indices...")
    start = time.time()

    try:
        from psi_index import PSIIndexBuilder, INDEX_CONFIGS

        builder = PSIIndexBuilder(ch_client)
        results = {}

        for index_type in INDEX_CONFIGS.keys():
            try:
                index = builder.build_index(index_type)
                results[index_type.value] = {
                    'status': 'success',
                    'constituents': index.num_constituents
                }
                logger.info(f"Built {index_type.value}: {index.num_constituents} constituents")
            except Exception as e:
                results[index_type.value] = {'status': 'error', 'error': str(e)}
                logger.warning(f"Failed to build {index_type.value}: {e}")

        elapsed = time.time() - start
        logger.info(f"Index building completed in {elapsed:.1f}s")

        return {
            'status': 'success',
            'indices': results,
            'elapsed_seconds': elapsed
        }

    except Exception as e:
        logger.error(f"PSI Index building failed: {e}")
        return {'status': 'error', 'error': str(e)}


def run_hidden_alpha_discovery(ch_client) -> dict:
    """Run hidden alpha trader discovery"""
    logger.info("Running hidden alpha discovery...")
    start = time.time()

    try:
        from hidden_alpha import HiddenAlphaDiscovery

        discovery = HiddenAlphaDiscovery(ch_client)
        traders = discovery.discover_all()

        by_type = {}
        for t in traders:
            type_name = t.discovery_type.value
            by_type[type_name] = by_type.get(type_name, 0) + 1

        elapsed = time.time() - start
        logger.info(f"Discovered {len(traders)} hidden alpha traders in {elapsed:.1f}s")

        return {
            'status': 'success',
            'total_discoveries': len(traders),
            'by_type': by_type,
            'elapsed_seconds': elapsed
        }

    except Exception as e:
        logger.error(f"Hidden alpha discovery failed: {e}")
        return {'status': 'error', 'error': str(e)}


def run_consensus_detection(ch_client) -> dict:
    """Run consensus signal detection"""
    logger.info("Running consensus detection...")
    start = time.time()

    try:
        from consensus import ConsensusDetector

        detector = ConsensusDetector(ch_client)
        signals = detector.scan_all_markets()

        by_strength = {}
        for s in signals:
            strength = s.strength.value
            by_strength[strength] = by_strength.get(strength, 0) + 1

        elapsed = time.time() - start
        logger.info(f"Found {len(signals)} consensus signals in {elapsed:.1f}s")

        return {
            'status': 'success',
            'total_signals': len(signals),
            'by_strength': by_strength,
            'elapsed_seconds': elapsed
        }

    except Exception as e:
        logger.error(f"Consensus detection failed: {e}")
        return {'status': 'error', 'error': str(e)}


def run_edge_decay_scan(ch_client) -> dict:
    """Run edge decay scanning"""
    logger.info("Running edge decay scan...")
    start = time.time()

    try:
        from edge_decay import EdgeDecayDetector

        detector = EdgeDecayDetector(ch_client)
        alerts = detector.scan_all_traders()

        by_signal = {}
        for a in alerts:
            sig = a.signal.value
            by_signal[sig] = by_signal.get(sig, 0) + 1

        elapsed = time.time() - start
        logger.info(f"Found {len(alerts)} edge decay alerts in {elapsed:.1f}s")

        return {
            'status': 'success',
            'total_alerts': len(alerts),
            'by_signal': by_signal,
            'elapsed_seconds': elapsed
        }

    except Exception as e:
        logger.error(f"Edge decay scan failed: {e}")
        return {'status': 'error', 'error': str(e)}


def run_anomaly_detection(ch_client) -> dict:
    """Run anomaly and gaming detection"""
    logger.info("Running anomaly detection...")
    start = time.time()

    try:
        from anomaly_detection import AnomalyDetector

        detector = AnomalyDetector(ch_client)
        alerts = detector.scan_all_traders()

        by_severity = {}
        for a in alerts:
            sev = a.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

        elapsed = time.time() - start
        logger.info(f"Found {len(alerts)} anomalies in {elapsed:.1f}s")

        return {
            'status': 'success',
            'total_anomalies': len(alerts),
            'by_severity': by_severity,
            'elapsed_seconds': elapsed
        }

    except Exception as e:
        logger.error(f"Anomaly detection failed: {e}")
        return {'status': 'error', 'error': str(e)}


def run_insider_detection(ch_client) -> dict:
    """Run insider trading pattern detection"""
    logger.info("Running insider detection...")
    start = time.time()

    try:
        from insider_detector import InsiderDetector

        detector = InsiderDetector(ch_client)
        alerts = detector.scan_for_insider_activity()

        by_severity = {}
        by_signal = {}
        for a in alerts:
            sev = a.severity.value
            sig = a.signal_type.value
            by_severity[sev] = by_severity.get(sev, 0) + 1
            by_signal[sig] = by_signal.get(sig, 0) + 1

        # Save alerts to aware_alerts table
        saved = 0
        if alerts:
            saved = detector.save_alerts(alerts)

        elapsed = time.time() - start
        logger.info(f"Found {len(alerts)} insider alerts, saved {saved} in {elapsed:.1f}s")

        return {
            'status': 'success',
            'total_alerts': len(alerts),
            'saved_alerts': saved,
            'by_severity': by_severity,
            'by_signal': by_signal,
            'elapsed_seconds': elapsed
        }

    except Exception as e:
        logger.error(f"Insider detection failed: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'error': str(e)}


def run_ml_enrichment(ch_client) -> dict:
    """Run ML enrichment (Strategy DNA clustering + Anomaly Detection)"""
    logger.info("Running ML enrichment...")
    start = time.time()

    try:
        from ml_enrichment_job import MLEnrichmentJob, MLEnrichmentConfig
        from clickhouse_client import ClickHouseClient

        # Use our ClickHouseClient wrapper
        aware_client = ClickHouseClient()
        config = MLEnrichmentConfig(n_clusters=8, max_traders=5000)
        job = MLEnrichmentJob(aware_client, config)
        stats = job.run()

        elapsed = time.time() - start
        logger.info(f"ML enrichment complete in {elapsed:.1f}s")

        return {
            'status': 'success',
            'traders_processed': stats.get('traders_processed', 0),
            'clusters_created': stats.get('clusters_created', 0),
            'anomalies_detected': stats.get('anomalies_detected', 0),
            'elapsed_seconds': elapsed
        }

    except Exception as e:
        logger.error(f"ML enrichment failed: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'error': str(e)}


def run_edge_persistence(ch_client) -> dict:
    """Run edge persistence prediction"""
    logger.info("Running edge persistence prediction...")
    start = time.time()

    try:
        from edge_persistence import EdgePersistencePredictor

        predictor = EdgePersistencePredictor(ch_client)
        predictions = predictor.predict_all()

        by_risk = {}
        for p in predictions:
            risk = p.persistence_risk.value
            by_risk[risk] = by_risk.get(risk, 0) + 1

        avg_prob = sum(p.persist_prob_30d for p in predictions) / len(predictions) if predictions else 0

        elapsed = time.time() - start
        logger.info(f"Generated {len(predictions)} persistence predictions in {elapsed:.1f}s")

        return {
            'status': 'success',
            'total_predictions': len(predictions),
            'avg_persistence_prob': round(avg_prob, 3),
            'by_risk': by_risk,
            'elapsed_seconds': elapsed
        }

    except Exception as e:
        logger.error(f"Edge persistence prediction failed: {e}")
        return {'status': 'error', 'error': str(e)}


def run_market_classification(ch_client) -> dict:
    """Run market category classification"""
    logger.info("Running market classification...")
    start = time.time()

    try:
        from market_classification_job import MarketClassificationJob

        job = MarketClassificationJob(ch_client)
        result = job.run(full_reclassify=False)  # Only classify new markets

        elapsed = time.time() - start
        classified = result.get('markets_classified', 0)
        logger.info(f"Classified {classified} markets in {elapsed:.1f}s")

        return {
            'status': 'success',
            'markets_classified': classified,
            'category_distribution': result.get('category_distribution', {}),
            'elapsed_seconds': elapsed
        }

    except Exception as e:
        logger.error(f"Market classification failed: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'error': str(e)}


def run_resolution_tracking(ch_client) -> dict:
    """Track market resolutions from Gamma API"""
    logger.info("Running resolution tracking...")
    start = time.time()

    try:
        from resolution_tracker import ResolutionTracker

        tracker = ResolutionTracker(ch_client)
        resolved_count = tracker.run()
        stats = tracker.get_resolution_stats()
        tracker.close()

        elapsed = time.time() - start
        logger.info(f"Tracked {resolved_count} resolutions in {elapsed:.1f}s")

        return {
            'status': 'success',
            'resolutions_stored': resolved_count,
            'stats': stats,
            'elapsed_seconds': elapsed
        }

    except Exception as e:
        logger.error(f"Resolution tracking failed: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'error': str(e)}


def run_pnl_calculation(ch_client) -> dict:
    """Calculate P&L from resolved positions"""
    logger.info("Running P&L calculation...")
    start = time.time()

    try:
        from pnl_calculator import PnLCalculator

        calculator = PnLCalculator(ch_client)
        traders_updated = calculator.run()
        summary = calculator.get_pnl_summary()

        elapsed = time.time() - start
        logger.info(f"Updated P&L for {traders_updated} traders in {elapsed:.1f}s")

        return {
            'status': 'success',
            'traders_updated': traders_updated,
            'summary': summary,
            'elapsed_seconds': elapsed
        }

    except Exception as e:
        logger.error(f"P&L calculation failed: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'error': str(e)}


def run_sharpe_calculation(ch_client) -> dict:
    """Calculate Sharpe ratios from daily P&L"""
    logger.info("Running Sharpe ratio calculation...")
    start = time.time()

    try:
        from sharpe_calculator import SharpeCalculator

        calculator = SharpeCalculator(ch_client)
        traders_with_sharpe = calculator.run(min_days=3)
        summary = calculator.get_sharpe_summary()

        elapsed = time.time() - start
        logger.info(f"Calculated Sharpe for {traders_with_sharpe} traders in {elapsed:.1f}s")

        return {
            'status': 'success',
            'traders_with_sharpe': traders_with_sharpe,
            'summary': summary,
            'elapsed_seconds': elapsed
        }

    except Exception as e:
        logger.error(f"Sharpe calculation failed: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'error': str(e)}


def run_drift_monitoring(ch_client) -> dict:
    """Run ML drift monitoring to detect feature distribution changes.

    Enhanced with:
    - Auto-create baseline if missing
    - Adaptive sample sizing
    - Auto-retraining triggers
    - JSON report export for API access
    """
    logger.info("Running drift monitoring...")
    start = time.time()

    try:
        from ml.monitoring.drift import DriftDetector
        from ml.monitoring.auto_retrain import RetrainTrigger, get_last_train_date, get_new_trade_count_since
        from ml.features import FeatureExtractor
        from clickhouse_client import ClickHouseClient
        from pathlib import Path
        import json as json_module
        import numpy as np

        baseline_path = Path("ml/checkpoints/drift_baseline.pkl")
        report_path = Path("ml/checkpoints/latest_drift_report.json")

        # Feature names for consistency
        feature_names = [
            'total_trades', 'win_rate', 'avg_trade_size', 'max_trade_size',
            'trade_frequency', 'avg_hold_hours', 'sharpe_ratio', 'sortino_ratio',
            'max_drawdown', 'profit_factor', 'avg_pnl', 'total_pnl',
            'unique_markets', 'market_concentration', 'active_days',
            'trades_per_day', 'morning_ratio', 'evening_ratio',
            'crypto_ratio', 'politics_ratio', 'sports_ratio',
            'avg_entry_odds', 'avg_exit_odds', 'maker_ratio',
            'price_improvement', 'execution_quality', 'slippage_avg',
            'streak_current', 'streak_max_win', 'streak_max_loss',
            'consecutive_wins', 'consecutive_losses', 'recovery_speed',
            'win_loss_ratio', 'risk_reward_ratio'
        ]

        # Initialize ClickHouse client and feature extractor
        aware_client = ClickHouseClient()
        feature_extractor = FeatureExtractor(aware_client)

        # Adaptive sample sizing: 10% of total or 5000-20000 range
        total_result = aware_client.query("""
            SELECT count(DISTINCT proxy_address)
            FROM polybot.aware_global_trades_dedup
            WHERE ts >= now() - INTERVAL 30 DAY
        """)
        total_traders = total_result.result_rows[0][0] if total_result.result_rows else 5000
        sample_size = min(20000, max(5000, int(total_traders * 0.1)))

        # Get recent traders for drift check
        result = aware_client.query(f"""
            SELECT DISTINCT proxy_address
            FROM polybot.aware_global_trades_dedup
            WHERE ts >= now() - INTERVAL 7 DAY
            ORDER BY rand()
            LIMIT {sample_size}
        """)
        addresses = [row[0] for row in result.result_rows]

        if len(addresses) < 100:
            logger.warning("Not enough recent traders for drift detection")
            return {
                'status': 'skipped',
                'reason': 'insufficient_samples',
                'sample_count': len(addresses),
                'elapsed_seconds': time.time() - start
            }

        # Extract features
        logger.info(f"Extracting features for {len(addresses)} traders (adaptive sample)...")
        features_list = feature_extractor.extract_batch(addresses)

        # Build feature matrix
        n_features = len(features_list[0].to_tabular_vector()) if features_list else 35
        feature_matrix = np.zeros((len(addresses), n_features), dtype=np.float32)

        for i, feat in enumerate(features_list):
            if feat is not None:
                feature_matrix[i] = feat.to_tabular_vector()

        # Auto-create baseline if missing
        if not baseline_path.exists():
            logger.warning("Drift baseline not found - creating from current data")
            baseline_path.parent.mkdir(parents=True, exist_ok=True)

            detector = DriftDetector()
            detector.fit_baseline(feature_matrix, feature_names[:n_features])
            detector.save_baseline(str(baseline_path))

            logger.info(f"Created drift baseline with {len(addresses)} samples")
            return {
                'status': 'baseline_created',
                'n_samples': len(addresses),
                'n_features': n_features,
                'elapsed_seconds': time.time() - start
            }

        # Load baseline and run detection
        detector = DriftDetector.load_baseline(baseline_path)
        report = detector.detect(feature_matrix, feature_names[:n_features])
        detector.log_report(report)

        # Save drift report to JSON for API access
        drift_report_data = {
            'checked_at': datetime.utcnow().isoformat(),
            'alert_level': report.alert_level,
            'drift_ratio': report.drift_ratio,
            'n_features': report.n_features,
            'n_drifted': report.n_drifted,
            'n_samples_current': len(addresses),
            'baseline_date': detector.baseline_date.isoformat() if hasattr(detector, 'baseline_date') else 'unknown',
            'drifted_features': [
                {
                    'feature': r.feature_name,
                    'severity': r.drift_severity,
                    'ks_statistic': r.ks_statistic,
                    'p_value': r.ks_pvalue
                }
                for r in report.feature_results if r.is_drifted
            ]
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json_module.dumps(drift_report_data, indent=2))

        # Check if retraining is needed
        retrain_triggered = False
        retrain_reason = ''

        trigger = RetrainTrigger()
        last_train = get_last_train_date()
        new_trades = get_new_trade_count_since(last_train, aware_client) if last_train else 0

        should_retrain, reason = trigger.should_retrain(
            drift_ratio=report.drift_ratio,
            last_train_date=last_train,
            new_trade_count=new_trades
        )

        if should_retrain:
            # Determine priority based on drift severity
            priority = 'high' if report.alert_level == 'critical' else 'normal'
            trigger_result = trigger.trigger_retrain(reason, priority=priority)
            retrain_triggered = trigger_result.get('status') in ('queued', 'already_queued')
            retrain_reason = reason
            logger.info(f"Retraining triggered: {reason}")

        elapsed = time.time() - start
        logger.info(f"Drift monitoring complete in {elapsed:.1f}s - Alert: {report.alert_level}")

        return {
            'status': 'success',
            'drift_ratio': report.drift_ratio,
            'n_drifted': report.n_drifted,
            'n_features': report.n_features,
            'alert_level': report.alert_level,
            'sample_count': len(addresses),
            'retrain_triggered': retrain_triggered,
            'retrain_reason': retrain_reason,
            'elapsed_seconds': elapsed
        }

    except FileNotFoundError as e:
        logger.warning(f"Drift monitoring skipped: {e}")
        return {'status': 'skipped', 'reason': str(e)}
    except Exception as e:
        logger.error(f"Drift monitoring failed: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'error': str(e)}


def run_nav_calculation_job(ch_client) -> dict:
    """Calculate NAV for all AWARE funds"""
    logger.info("Running NAV calculation...")
    start = time.time()

    try:
        from nav_calculator import NAVCalculator
        from clickhouse_driver import Client

        # NAVCalculator uses clickhouse_driver, not clickhouse_connect
        ch_host = os.getenv('CLICKHOUSE_HOST', 'localhost')
        ch_port = int(os.getenv('CLICKHOUSE_PORT', '9000'))
        driver_client = Client(host=ch_host, port=ch_port)

        calculator = NAVCalculator(driver_client)
        valuations = calculator.calculate_all_funds()

        elapsed = time.time() - start
        logger.info(f"Calculated NAV for {len(valuations)} funds in {elapsed:.1f}s")

        fund_navs = {v.fund_type: float(v.nav_per_share) for v in valuations}

        return {
            'status': 'success',
            'funds_calculated': len(valuations),
            'fund_navs': fund_navs,
            'elapsed_seconds': elapsed
        }

    except Exception as e:
        logger.error(f"NAV calculation failed: {e}")
        import traceback
        traceback.print_exc()
        return {'status': 'error', 'error': str(e)}


def run_notification_dispatch(ch_client) -> dict:
    """
    Dispatch pending alerts to notification channels.

    Sends alerts to configured Discord/Telegram/Webhook channels.
    Only dispatches alerts not yet delivered (status != 'DELIVERED').
    """
    logger.info("Running notification dispatch...")
    start = time.time()

    try:
        import asyncio
        from notifications import get_dispatcher

        dispatcher = get_dispatcher()

        # Check if any channels are configured
        if not dispatcher.has_channels:
            logger.info("No notification channels configured (set DISCORD_WEBHOOK_URL or TELEGRAM_BOT_TOKEN)")
            return {
                'status': 'skipped',
                'reason': 'no_channels_configured',
                'elapsed_seconds': time.time() - start
            }

        # Process pending alerts from ClickHouse
        # Run the async method synchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            alerts_sent = loop.run_until_complete(dispatcher.process_pending_alerts())
        finally:
            loop.close()

        elapsed = time.time() - start
        logger.info(f"Dispatched {alerts_sent} alerts in {elapsed:.1f}s")

        return {
            'status': 'success',
            'alerts_dispatched': alerts_sent,
            'channels': dispatcher.active_channels,
            'elapsed_seconds': elapsed
        }

    except ImportError as e:
        logger.warning(f"Notification dispatch not available: {e}")
        return {
            'status': 'skipped',
            'reason': f'import_error: {e}',
            'elapsed_seconds': time.time() - start
        }
    except Exception as e:
        logger.error(f"Notification dispatch failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            'status': 'error',
            'error': str(e),
            'elapsed_seconds': time.time() - start
        }


def run_all_jobs(ch_client) -> dict:
    """Run all analytics jobs"""
    logger.info("=" * 60)
    logger.info("  AWARE Analytics - Running All Jobs")
    logger.info("=" * 60)
    logger.info(f"  Started at: {datetime.utcnow().isoformat()}")
    logger.info("=" * 60)

    start = time.time()
    results = {}

    # 0. Market Classification (must run before PSI index building)
    # Classifies market slugs into categories (CRYPTO, POLITICS, SPORTS, etc.)
    # Required for PSI-POLITICS, PSI-SPORTS, PSI-CRYPTO sectorial indexes
    results['market_classification'] = run_market_classification(ch_client)

    # 1. Resolution Tracking (must run before P&L)
    results['resolution_tracking'] = run_resolution_tracking(ch_client)

    # 1. P&L Calculation (populates aware_trader_pnl table)
    # Must run BEFORE scoring so scoring can include P&L in profiles
    results['pnl_calculation'] = run_pnl_calculation(ch_client)

    # 1.5. Sharpe Ratio Calculation (populates aware_ml_scores table)
    # Uses daily P&L from aware_position_pnl to calculate risk-adjusted returns
    results['sharpe_calculation'] = run_sharpe_calculation(ch_client)

    # 2. Smart Money Scoring (creates profiles with trade metrics + P&L)
    # Scoring job includes P&L from aware_trader_pnl in profiles
    results['smart_money_scoring'] = run_smart_money_scoring(ch_client)

    # 3. PSI Index Building
    results['psi_indices'] = run_psi_index_building(ch_client)

    # 4. Hidden Alpha Discovery
    results['hidden_alpha'] = run_hidden_alpha_discovery(ch_client)

    # 5. Consensus Detection
    results['consensus'] = run_consensus_detection(ch_client)

    # 6. Edge Decay Scanning
    results['edge_decay'] = run_edge_decay_scan(ch_client)

    # 7. Anomaly Detection (rule-based)
    results['anomaly_detection'] = run_anomaly_detection(ch_client)

    # 7b. Insider Detection (pattern-based alert generation)
    results['insider_detection'] = run_insider_detection(ch_client)

    # 8. ML Enrichment (Strategy DNA clustering + ML-based anomaly detection)
    results['ml_enrichment'] = run_ml_enrichment(ch_client)

    # 9. Edge Persistence Prediction
    results['edge_persistence'] = run_edge_persistence(ch_client)

    # 10. ML Drift Monitoring (detect feature distribution changes)
    # Runs after scoring to monitor if production data is drifting from training baseline
    results['drift_monitoring'] = run_drift_monitoring(ch_client)

    # 11. NAV Calculation (calculates Net Asset Value for all AWARE funds)
    # Runs after all other jobs since NAV depends on positions and P&L
    results['nav_calculation'] = run_nav_calculation_job(ch_client)

    # 12. Notification Dispatch (send alerts to Discord/Telegram/Webhooks)
    # Processes alerts generated by previous jobs and sends to configured channels
    results['notification_dispatch'] = run_notification_dispatch(ch_client)

    total_elapsed = time.time() - start

    logger.info("=" * 60)
    logger.info("  AWARE Analytics - Complete")
    logger.info("=" * 60)
    logger.info(f"  Total time: {total_elapsed:.1f}s")
    logger.info("=" * 60)

    results['total_elapsed_seconds'] = total_elapsed
    results['completed_at'] = datetime.utcnow().isoformat()

    return results


def main():
    parser = argparse.ArgumentParser(description='AWARE Analytics Runner')
    parser.add_argument('--continuous', action='store_true',
                       help='Run continuously every hour')
    parser.add_argument('--interval', type=int, default=3600,
                       help='Interval in seconds for continuous mode (default: 3600)')
    args = parser.parse_args()

    ch_client = get_clickhouse_client()

    if args.continuous:
        logger.info(f"Starting continuous mode with {args.interval}s interval")
        while True:
            try:
                results = run_all_jobs(ch_client)
                logger.info(f"Next run in {args.interval}s")
                time.sleep(args.interval)
            except KeyboardInterrupt:
                logger.info("Shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in analytics run: {e}")
                time.sleep(60)  # Wait 1 minute before retrying
    else:
        results = run_all_jobs(ch_client)
        print("\nResults:")
        import json
        print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
