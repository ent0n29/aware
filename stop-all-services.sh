#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")"

echo "=========================================="
echo "Stopping AWARE Java + Infra Services"
echo "=========================================="
echo ""

stop_service() {
  local service_name="$1"
  local pid_file="logs/${service_name}.pid"

  if [ -f "$pid_file" ]; then
    local pid
    pid=$(cat "$pid_file")
    if ps -p "$pid" >/dev/null 2>&1; then
      echo "Stopping ${service_name} (PID: $pid)..."
      kill "$pid"
      sleep 2
      if ps -p "$pid" >/dev/null 2>&1; then
        echo "  Force stopping ${service_name}..."
        kill -9 "$pid"
      fi
      echo "  ✓ Stopped"
    else
      echo "${service_name} is not running (stale PID file)"
    fi
    rm -f "$pid_file"
  else
    echo "${service_name}: No PID file found"
  fi
}

# Stop Java services in reverse order
stop_service "analytics-service"
stop_service "ingestor-service"
stop_service "strategy-service"
stop_service "executor-service"

echo ""
echo "Stopping Docker infrastructure stacks..."

# Monitoring stack requires env interpolation; provide safe defaults for shutdown.
GRAFANA_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-admin}" \
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}" \
  docker compose -f docker-compose.monitoring.yaml down >/dev/null 2>&1 || true

docker compose -f docker-compose.analytics.yaml down >/dev/null 2>&1 || true

echo ""
echo "=========================================="
echo "✓ All services stopped"
echo "=========================================="
echo ""
