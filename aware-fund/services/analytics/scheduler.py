#!/usr/bin/env python3
"""
AWARE Analytics - Production Scheduler

Runs analytics jobs on configurable schedules with health monitoring.
Supports cron-like scheduling or simple interval-based execution.

Usage:
    python scheduler.py --mode interval --interval 300   # Every 5 minutes
    python scheduler.py --mode cron                       # Uses built-in schedule
    python scheduler.py --once                            # Single run and exit
"""

import os
import sys
import time
import argparse
import logging
import signal
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional
import subprocess

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('scheduler')


class JobScheduler:
    """Production scheduler for AWARE analytics jobs."""

    def __init__(self):
        self.running = True
        self.jobs: list[dict] = []
        self.health_port = int(os.getenv('HEALTH_PORT', '8085'))

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def add_job(
        self,
        name: str,
        func: Callable,
        interval_seconds: int,
        run_on_startup: bool = True,
        enabled: bool = True,
    ):
        """Add a scheduled job."""
        self.jobs.append({
            'name': name,
            'func': func,
            'interval': interval_seconds,
            'last_run': None if run_on_startup else datetime.utcnow(),
            'next_run': datetime.utcnow() if run_on_startup else datetime.utcnow() + timedelta(seconds=interval_seconds),
            'enabled': enabled,
            'run_count': 0,
            'error_count': 0,
            'last_error': None,
            'last_duration': None,
        })
        logger.info(f"Added job '{name}' with interval {interval_seconds}s")

    def run_job(self, job: dict) -> bool:
        """Execute a single job with error handling."""
        name = job['name']
        logger.info(f"Starting job: {name}")
        start_time = time.time()

        try:
            job['func']()
            duration = time.time() - start_time
            job['last_run'] = datetime.utcnow()
            job['next_run'] = datetime.utcnow() + timedelta(seconds=job['interval'])
            job['run_count'] += 1
            job['last_duration'] = duration
            logger.info(f"Job '{name}' completed in {duration:.1f}s")
            return True

        except Exception as e:
            duration = time.time() - start_time
            job['error_count'] += 1
            job['last_error'] = str(e)
            job['last_duration'] = duration
            job['next_run'] = datetime.utcnow() + timedelta(seconds=job['interval'])
            logger.error(f"Job '{name}' failed after {duration:.1f}s: {e}")
            return False

    def get_status(self) -> dict:
        """Get scheduler status for health checks."""
        return {
            'running': self.running,
            'jobs': [
                {
                    'name': j['name'],
                    'enabled': j['enabled'],
                    'last_run': str(j['last_run']) if j['last_run'] else None,
                    'next_run': str(j['next_run']) if j['next_run'] else None,
                    'run_count': j['run_count'],
                    'error_count': j['error_count'],
                    'last_error': j['last_error'],
                    'last_duration_s': j['last_duration'],
                }
                for j in self.jobs
            ],
            'timestamp': datetime.utcnow().isoformat(),
        }

    def run(self):
        """Main scheduler loop."""
        logger.info(f"Scheduler started with {len(self.jobs)} jobs")

        while self.running:
            now = datetime.utcnow()

            for job in self.jobs:
                if not job['enabled']:
                    continue

                if job['next_run'] and now >= job['next_run']:
                    self.run_job(job)

            # Sleep briefly to avoid busy-waiting
            time.sleep(1)

        logger.info("Scheduler stopped")


# ============================================================================
# JOB DEFINITIONS
# ============================================================================

def run_analytics_pipeline():
    """Run the full analytics pipeline."""
    from run_all import main as run_all_main
    run_all_main()


def run_resolution_tracking():
    """Track market resolutions only."""
    from resolution_tracker import track_resolutions
    track_resolutions()


def run_pnl_calculation():
    """Calculate P&L for all traders."""
    from pnl_calculator import calculate_all_pnl
    calculate_all_pnl()


def run_scoring():
    """Run Smart Money Score calculation."""
    from scoring_job import run_scoring_job
    run_scoring_job()


def run_index_building():
    """Build all PSI indices."""
    from psi_index import build_all_indices
    build_all_indices()


def run_insider_detection():
    """Run insider detection scan."""
    from insider_detector import InsiderDetector
    detector = InsiderDetector()
    detector.scan_all()


def run_ml_enrichment():
    """Run ML feature enrichment (Strategy DNA clustering + Anomaly detection)."""
    from ml_enrichment_job import run_ml_enrichment as ml_enrichment_run
    ml_enrichment_run()


# ============================================================================
# SCHEDULE CONFIGURATIONS
# ============================================================================

SCHEDULES = {
    # Production schedule - optimized for data freshness vs resource usage
    'production': [
        # ('job_name', job_func, interval_seconds, run_on_startup)
        ('resolution_tracking', run_resolution_tracking, 300, True),      # Every 5 min
        ('pnl_calculation', run_pnl_calculation, 300, True),              # Every 5 min
        ('scoring', run_scoring, 600, True),                              # Every 10 min
        ('index_building', run_index_building, 600, True),                # Every 10 min
        ('insider_detection', run_insider_detection, 180, True),          # Every 3 min
        ('ml_enrichment', run_ml_enrichment, 1800, True),                 # Every 30 min
    ],

    # Aggressive schedule - maximum data freshness
    'aggressive': [
        ('resolution_tracking', run_resolution_tracking, 60, True),       # Every 1 min
        ('pnl_calculation', run_pnl_calculation, 60, True),               # Every 1 min
        ('scoring', run_scoring, 120, True),                              # Every 2 min
        ('index_building', run_index_building, 120, True),                # Every 2 min
        ('insider_detection', run_insider_detection, 60, True),           # Every 1 min
        ('ml_enrichment', run_ml_enrichment, 300, True),                  # Every 5 min
    ],

    # Light schedule - minimal resource usage
    'light': [
        ('full_pipeline', run_analytics_pipeline, 3600, True),            # Every 1 hour
    ],

    # Development schedule - quick iteration
    'dev': [
        ('full_pipeline', run_analytics_pipeline, 120, True),             # Every 2 min
    ],
}


def start_health_server(scheduler: JobScheduler, port: int):
    """Start health check server in background thread."""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json

    class SchedulerHealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/scheduler/status':
                self._respond(scheduler.get_status())
            elif self.path == '/health':
                # Import health checker for full health
                try:
                    from health_check import HealthChecker
                    checker = HealthChecker()
                    health = checker.get_full_health()
                    health['scheduler'] = scheduler.get_status()
                    self._respond(health)
                except Exception as e:
                    self._respond({'status': 'error', 'error': str(e)}, status=500)
            elif self.path == '/live':
                self._respond({'alive': True, 'scheduler_running': scheduler.running})
            elif self.path == '/ready':
                ready = scheduler.running and len(scheduler.jobs) > 0
                self._respond({'ready': ready}, status=200 if ready else 503)
            else:
                self._respond({'error': 'Not found'}, status=404)

        def _respond(self, data: dict, status: int = 200):
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode())

        def log_message(self, format, *args):
            pass  # Suppress logging

    def run_server():
        server = HTTPServer(('0.0.0.0', port), SchedulerHealthHandler)
        logger.info(f"Health server running on http://0.0.0.0:{port}")
        while scheduler.running:
            server.handle_request()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    return thread


def main():
    parser = argparse.ArgumentParser(description='AWARE Analytics Scheduler')
    parser.add_argument(
        '--schedule',
        choices=list(SCHEDULES.keys()),
        default='production',
        help='Schedule configuration to use'
    )
    parser.add_argument(
        '--interval',
        type=int,
        help='Override: run full pipeline at this interval (seconds)'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Run full pipeline once and exit'
    )
    parser.add_argument(
        '--health-port',
        type=int,
        default=8085,
        help='Port for health check server'
    )
    parser.add_argument(
        '--no-health-server',
        action='store_true',
        help='Disable health check server'
    )

    args = parser.parse_args()

    # Single run mode
    if args.once:
        logger.info("Running full pipeline once...")
        run_analytics_pipeline()
        logger.info("Done")
        return

    # Create scheduler
    scheduler = JobScheduler()

    # Configure jobs
    if args.interval:
        # Simple interval mode
        scheduler.add_job('full_pipeline', run_analytics_pipeline, args.interval)
    else:
        # Use predefined schedule
        schedule = SCHEDULES[args.schedule]
        for name, func, interval, startup in schedule:
            scheduler.add_job(name, func, interval, run_on_startup=startup)

    # Start health server
    if not args.no_health_server:
        start_health_server(scheduler, args.health_port)

    # Run scheduler
    logger.info(f"Starting scheduler with '{args.schedule}' schedule")
    logger.info("Press Ctrl+C to stop")
    scheduler.run()


if __name__ == "__main__":
    main()
