#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# AWARE Fund - Local Development Startup Script
# ═══════════════════════════════════════════════════════════════════════════════
# Usage:
#   ./start-local.sh          - Start all services
#   ./start-local.sh build    - Rebuild and start
#   ./start-local.sh down     - Stop all services
#   ./start-local.sh logs     - View logs
#   ./start-local.sh status   - Check service status
#   ./start-local.sh monitor  - Start with monitoring (Prometheus + Grafana)
# ═══════════════════════════════════════════════════════════════════════════════

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

COMPOSE_FILE="docker-compose.local.yaml"

log() {
    echo -e "${GREEN}[AWARE]${NC} $1"
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Check Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${YELLOW}Docker is not running. Starting Docker...${NC}"
    open -a Docker
    sleep 10
fi

case "${1:-up}" in
    up)
        log "Starting AWARE Fund local stack..."
        docker compose -f $COMPOSE_FILE up -d

        log "Waiting for services to start..."
        sleep 10

        echo ""
        log "Services starting up. Access points:"
        echo ""
        info "Web Dashboard:     http://localhost:3000"
        info "Python API:        http://localhost:8000"
        info "Strategy Service:  http://localhost:8081/api/strategy/status"
        info "Executor Service:  http://localhost:8080/api/polymarket/health"
        info "ClickHouse:        http://localhost:8123"
        echo ""
        log "View logs: ./start-local.sh logs"
        ;;

    build)
        log "Rebuilding and starting AWARE Fund..."
        docker compose -f $COMPOSE_FILE build
        docker compose -f $COMPOSE_FILE up -d
        ;;

    down)
        log "Stopping all services..."
        docker compose -f $COMPOSE_FILE down
        log "Done!"
        ;;

    logs)
        SERVICE=${2:-}
        if [ -z "$SERVICE" ]; then
            docker compose -f $COMPOSE_FILE logs -f --tail=100
        else
            docker compose -f $COMPOSE_FILE logs -f --tail=100 $SERVICE
        fi
        ;;

    status)
        log "Service Status:"
        echo ""
        docker compose -f $COMPOSE_FILE ps
        echo ""
        log "Health Checks:"

        # Check services
        curl -s http://localhost:8080/api/polymarket/health > /dev/null 2>&1 && \
            echo -e "  ${GREEN}✓${NC} Executor (8080)" || echo -e "  ❌ Executor (8080)"
        curl -s http://localhost:8081/api/strategy/status > /dev/null 2>&1 && \
            echo -e "  ${GREEN}✓${NC} Strategy (8081)" || echo -e "  ❌ Strategy (8081)"
        curl -s http://localhost:8000/health > /dev/null 2>&1 && \
            echo -e "  ${GREEN}✓${NC} API (8000)" || echo -e "  ❌ API (8000)"
        curl -s http://localhost:3000 > /dev/null 2>&1 && \
            echo -e "  ${GREEN}✓${NC} Web (3000)" || echo -e "  ❌ Web (3000)"
        curl -s http://localhost:8123 > /dev/null 2>&1 && \
            echo -e "  ${GREEN}✓${NC} ClickHouse (8123)" || echo -e "  ❌ ClickHouse (8123)"
        ;;

    monitor)
        log "Starting with monitoring..."
        docker compose -f $COMPOSE_FILE --profile monitoring up -d

        info "Grafana:    http://localhost:3001 (admin/admin)"
        info "Prometheus: http://localhost:9090"
        ;;

    clean)
        log "Stopping and removing all containers, volumes..."
        docker compose -f $COMPOSE_FILE down -v
        log "Cleaned!"
        ;;

    *)
        echo "AWARE Fund - Local Development"
        echo ""
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo "  up       - Start all services (default)"
        echo "  build    - Rebuild and start"
        echo "  down     - Stop all services"
        echo "  logs     - View logs (optionally: logs <service>)"
        echo "  status   - Check service status"
        echo "  monitor  - Start with Prometheus + Grafana"
        echo "  clean    - Stop and remove all data"
        ;;
esac
