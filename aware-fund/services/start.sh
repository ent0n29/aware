#!/bin/bash
#
# AWARE FUND - Start All Services
#
# This script starts the full AWARE stack including:
#   - Redpanda (Kafka)
#   - ClickHouse
#   - AWARE Analytics (scoring jobs)
#   - AWARE API
#
# Note: Global trade ingestion is handled by the Java ingestor-service.
#       Enable with: AWARE_GLOBAL_TRADES_ENABLED=true
#
# Usage:
#   ./start.sh        # Start all services
#   ./start.sh stop   # Stop all services
#   ./start.sh logs   # View logs
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AWARE_DIR="$(dirname "$SCRIPT_DIR")"
POLYBOT_DIR="$(dirname "$AWARE_DIR")"

cd "$POLYBOT_DIR"

case "${1:-start}" in
    start)
        echo "=============================================="
        echo "  AWARE FUND - Starting Services"
        echo "=============================================="
        echo ""

        # Start infrastructure first
        echo "📦 Starting infrastructure (Redpanda, ClickHouse)..."
        docker compose -f docker-compose.analytics.yaml up -d

        # Wait for infrastructure
        echo "⏳ Waiting for infrastructure to be ready..."
        sleep 10

        # Start AWARE services
        echo "🚀 Starting AWARE services..."
        docker compose -f aware-fund/docker-compose.yaml up -d

        echo ""
        echo "=============================================="
        echo "  AWARE FUND - Services Started"
        echo "=============================================="
        echo ""
        echo "  Services:"
        echo "    - Redpanda (Kafka): localhost:9092"
        echo "    - ClickHouse:       localhost:8123"
        echo "    - AWARE API:        http://localhost:8088"
        echo ""
        echo "  API Endpoints:"
        echo "    - Health:       GET http://localhost:8088/api/health"
        echo "    - Stats:        GET http://localhost:8088/api/stats"
        echo "    - Leaderboard:  GET http://localhost:8088/api/leaderboard"
        echo "    - Trader:       GET http://localhost:8088/api/traders/{username}"
        echo "    - PSI-10:       GET http://localhost:8088/api/index/psi-10"
        echo ""
        echo "  Note: Run Java ingestor with AWARE_GLOBAL_TRADES_ENABLED=true"
        echo ""
        echo "  Logs: ./start.sh logs"
        echo "  Stop: ./start.sh stop"
        echo "=============================================="
        ;;

    stop)
        echo "🛑 Stopping AWARE services..."
        docker compose -f aware-fund/docker-compose.yaml down

        echo "🛑 Stopping infrastructure..."
        docker compose -f docker-compose.analytics.yaml down

        echo "✅ All services stopped"
        ;;

    logs)
        echo "📋 Showing logs (Ctrl+C to exit)..."
        docker compose -f aware-fund/docker-compose.yaml logs -f
        ;;

    status)
        echo "📊 Service Status:"
        docker compose -f docker-compose.analytics.yaml ps
        docker compose -f aware-fund/docker-compose.yaml ps
        ;;

    rebuild)
        echo "🔨 Rebuilding AWARE services..."
        docker compose -f aware-fund/docker-compose.yaml build --no-cache
        echo "✅ Rebuild complete. Run './start.sh start' to restart."
        ;;

    *)
        echo "Usage: $0 {start|stop|logs|status|rebuild}"
        exit 1
        ;;
esac
