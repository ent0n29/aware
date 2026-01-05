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
    """Run Smart Money Score calculation"""
    logger.info("Running Smart Money Score calculation...")
    start = time.time()

    try:
        from scoring_job import ScoringJob
        from clickhouse_client import ClickHouseClient

        # Use our ClickHouseClient wrapper
        aware_client = ClickHouseClient()
        job = ScoringJob(aware_client)
        scored_count = job.run(min_trades=5, max_traders=10000)

        elapsed = time.time() - start
        logger.info(f"Scored {scored_count} traders in {elapsed:.1f}s")

        return {
            'status': 'success',
            'traders_scored': scored_count,
            'elapsed_seconds': elapsed
        }

    except Exception as e:
        logger.error(f"Smart Money Scoring failed: {e}")
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


def run_all_jobs(ch_client) -> dict:
    """Run all analytics jobs"""
    logger.info("=" * 60)
    logger.info("  AWARE Analytics - Running All Jobs")
    logger.info("=" * 60)
    logger.info(f"  Started at: {datetime.utcnow().isoformat()}")
    logger.info("=" * 60)

    start = time.time()
    results = {}

    # 0. Resolution Tracking (must run before P&L)
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

    # 8. ML Enrichment (Strategy DNA clustering + ML-based anomaly detection)
    results['ml_enrichment'] = run_ml_enrichment(ch_client)

    # 9. Edge Persistence Prediction
    results['edge_persistence'] = run_edge_persistence(ch_client)

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
