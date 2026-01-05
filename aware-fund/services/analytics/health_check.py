#!/usr/bin/env python3
"""
AWARE Analytics - Health Check API

Provides health check endpoints for monitoring and orchestration.
Run standalone or import into Flask/FastAPI app.

Usage:
    python health_check.py --port 8085
"""

import os
import sys
import time
import argparse
import json
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional
import logging

import clickhouse_connect

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('health-check')


class HealthChecker:
    """Health check logic for AWARE Analytics components."""

    def __init__(self):
        self.ch_host = os.getenv('CLICKHOUSE_HOST', 'localhost')
        self.ch_port = int(os.getenv('CLICKHOUSE_PORT', '8123'))
        self._client: Optional[clickhouse_connect.driver.Client] = None

    @property
    def client(self):
        if self._client is None:
            self._client = clickhouse_connect.get_client(
                host=self.ch_host,
                port=self.ch_port,
                database='polybot'
            )
        return self._client

    def check_clickhouse(self) -> dict:
        """Check ClickHouse connectivity."""
        try:
            start = time.time()
            result = self.client.query("SELECT 1")
            latency_ms = (time.time() - start) * 1000
            return {
                'status': 'healthy',
                'latency_ms': round(latency_ms, 1),
            }
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}

    def check_data_freshness(self) -> dict:
        """Check if trade data is being ingested."""
        try:
            result = self.client.query("""
                SELECT
                    count() AS total_trades,
                    max(ts) AS latest_trade,
                    dateDiff('minute', max(ts), now()) AS minutes_ago
                FROM polybot.aware_global_trades_dedup
            """)
            if result.result_rows:
                row = result.result_rows[0]
                total_trades = row[0]
                latest_trade = row[1]
                minutes_ago = row[2]

                status = 'healthy' if minutes_ago < 60 else 'stale'
                return {
                    'status': status,
                    'total_trades': total_trades,
                    'latest_trade': str(latest_trade) if latest_trade else None,
                    'minutes_ago': minutes_ago,
                }
            return {'status': 'unknown', 'error': 'No data'}
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}

    def check_psi_indices(self) -> dict:
        """Check PSI index health."""
        try:
            result = self.client.query("""
                SELECT
                    index_type,
                    count() AS constituents,
                    max(rebalanced_at) AS last_rebalance
                FROM polybot.aware_psi_index
                GROUP BY index_type
            """)
            indices = {}
            for row in result.result_rows or []:
                indices[row[0]] = {
                    'constituents': row[1],
                    'last_rebalance': str(row[2]) if row[2] else None,
                }
            return {
                'status': 'healthy' if indices else 'empty',
                'indices': indices,
                'count': len(indices),
            }
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}

    def check_ml_enrichment(self) -> dict:
        """Check ML enrichment status."""
        try:
            result = self.client.query("""
                SELECT
                    count() AS total_enriched,
                    countIf(is_anomaly = 1) AS anomalies,
                    max(updated_at) AS last_update,
                    dateDiff('minute', max(updated_at), now()) AS minutes_ago
                FROM polybot.aware_ml_enrichment
            """)
            if result.result_rows:
                row = result.result_rows[0]
                minutes_ago = row[3] if row[3] else 9999
                status = 'healthy' if minutes_ago < 120 else 'stale'
                return {
                    'status': status,
                    'traders_enriched': row[0],
                    'anomalies_detected': row[1],
                    'last_update': str(row[2]) if row[2] else None,
                    'minutes_ago': minutes_ago,
                }
            return {'status': 'unknown', 'error': 'No data'}
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}

    def check_trader_profiles(self) -> dict:
        """Check trader profile status."""
        try:
            result = self.client.query("""
                SELECT
                    count() AS total_profiles,
                    countIf(smart_money_score >= 50) AS high_score,
                    max(updated_at) AS last_update
                FROM polybot.aware_trader_profiles FINAL
            """)
            if result.result_rows:
                row = result.result_rows[0]
                return {
                    'status': 'healthy' if row[0] > 0 else 'empty',
                    'total_profiles': row[0],
                    'high_score_traders': row[1],
                    'last_update': str(row[2]) if row[2] else None,
                }
            return {'status': 'unknown', 'error': 'No data'}
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}

    def get_full_health(self) -> dict:
        """Get comprehensive health status."""
        checks = {
            'clickhouse': self.check_clickhouse(),
            'data_freshness': self.check_data_freshness(),
            'psi_indices': self.check_psi_indices(),
            'ml_enrichment': self.check_ml_enrichment(),
            'trader_profiles': self.check_trader_profiles(),
        }

        # Overall status
        unhealthy = [k for k, v in checks.items() if v.get('status') == 'unhealthy']
        stale = [k for k, v in checks.items() if v.get('status') == 'stale']

        if unhealthy:
            overall = 'unhealthy'
        elif stale:
            overall = 'degraded'
        else:
            overall = 'healthy'

        return {
            'status': overall,
            'timestamp': datetime.utcnow().isoformat(),
            'checks': checks,
            'unhealthy_components': unhealthy,
            'stale_components': stale,
        }


class HealthHandler(BaseHTTPRequestHandler):
    """HTTP handler for health check endpoints."""

    checker = HealthChecker()

    def do_GET(self):
        if self.path == '/health' or self.path == '/':
            self._respond(self.checker.get_full_health())
        elif self.path == '/health/clickhouse':
            self._respond(self.checker.check_clickhouse())
        elif self.path == '/health/data':
            self._respond(self.checker.check_data_freshness())
        elif self.path == '/health/indices':
            self._respond(self.checker.check_psi_indices())
        elif self.path == '/health/ml':
            self._respond(self.checker.check_ml_enrichment())
        elif self.path == '/health/profiles':
            self._respond(self.checker.check_trader_profiles())
        elif self.path == '/ready':
            # Kubernetes readiness probe
            health = self.checker.get_full_health()
            if health['status'] == 'unhealthy':
                self._respond({'ready': False}, status=503)
            else:
                self._respond({'ready': True})
        elif self.path == '/live':
            # Kubernetes liveness probe
            self._respond({'alive': True})
        else:
            self._respond({'error': 'Not found'}, status=404)

    def _respond(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def log_message(self, format, *args):
        # Suppress default logging for cleaner output
        pass


def run_server(port: int = 8085):
    """Run the health check HTTP server."""
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    logger.info(f"Health check server running on http://0.0.0.0:{port}")
    logger.info("Endpoints:")
    logger.info("  GET /health          - Full health status")
    logger.info("  GET /health/clickhouse - ClickHouse status")
    logger.info("  GET /health/data     - Data freshness")
    logger.info("  GET /health/indices  - PSI indices status")
    logger.info("  GET /health/ml       - ML enrichment status")
    logger.info("  GET /health/profiles - Trader profiles status")
    logger.info("  GET /ready           - Kubernetes readiness probe")
    logger.info("  GET /live            - Kubernetes liveness probe")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='AWARE Analytics Health Check Server')
    parser.add_argument('--port', type=int, default=8085, help='Port to listen on')
    args = parser.parse_args()

    run_server(args.port)
