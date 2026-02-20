#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")"

echo "=========================================="
echo "Starting AWARE Java + Infra Services"
echo "=========================================="
echo ""

needs_build=false
check_build() {
  local jar_path="$1"
  local src_path="$2"
  if [ ! -f "$jar_path" ]; then
    needs_build=true
    return
  fi
  if [ -d "$src_path" ] && find "$src_path" -type f -newer "$jar_path" -print -quit | grep -q .; then
    needs_build=true
  fi
}

check_build "executor-service/target/executor-service-0.0.1-SNAPSHOT.jar" "executor-service/src"
check_build "strategy-service/target/strategy-service-0.0.1-SNAPSHOT.jar" "strategy-service/src"
check_build "ingestor-service/target/ingestor-service-0.0.1-SNAPSHOT.jar" "ingestor-service/src"
check_build "analytics-service/target/analytics-service-0.0.1-SNAPSHOT.jar" "analytics-service/src"

if [ "$needs_build" = true ]; then
  echo "Building Java services..."
  mvn package -DskipTests
  echo ""
fi

mkdir -p logs

echo "1) Starting analytics infrastructure (Redpanda + ClickHouse)..."
docker compose -f docker-compose.analytics.yaml up -d

echo "2) Starting monitoring stack (if configured)..."
if [ -n "${GRAFANA_ADMIN_PASSWORD:-}" ]; then
  docker compose -f docker-compose.monitoring.yaml up -d
  echo "   Monitoring started on :3000/:9090/:9093"
else
  echo "   Skipped monitoring stack (set GRAFANA_ADMIN_PASSWORD to enable)"
fi

start_service() {
  local name="$1"
  local jar="$2"
  local port="$3"
  local pid_file="logs/${name}.pid"
  local log_file="logs/${name}.log"

  if [ -f "$pid_file" ] && ps -p "$(cat "$pid_file")" >/dev/null 2>&1; then
    echo "   ${name} already running (PID: $(cat "$pid_file"))"
    return
  fi

  echo "   Starting ${name} (port ${port})..."
  java -jar "$jar" --spring.profiles.active=develop >"$log_file" 2>&1 &
  echo $! >"$pid_file"
  echo "   PID: $(cat "$pid_file")"
}

echo "3) Starting Java services..."
start_service "executor-service" "executor-service/target/executor-service-0.0.1-SNAPSHOT.jar" "8080"
start_service "strategy-service" "strategy-service/target/strategy-service-0.0.1-SNAPSHOT.jar" "8081"
start_service "ingestor-service" "ingestor-service/target/ingestor-service-0.0.1-SNAPSHOT.jar" "8083"
start_service "analytics-service" "analytics-service/target/analytics-service-0.0.1-SNAPSHOT.jar" "8082"

echo ""
echo "=========================================="
echo "✓ AWARE Java + infra stack started"
echo "=========================================="
echo ""
echo "Service URLs:"
echo "  • Executor:    http://localhost:8080/actuator/health"
echo "  • Strategy:    http://localhost:8081/actuator/health"
echo "  • Analytics:   http://localhost:8082/actuator/health"
echo "  • Ingestor:    http://localhost:8083/actuator/health"
echo ""
echo "Infrastructure:"
echo "  • ClickHouse:  http://localhost:8123"
echo "  • Redpanda:    localhost:9092"
echo ""
echo "To stop all services:"
echo "  ./stop-all-services.sh"
