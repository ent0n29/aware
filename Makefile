# ═══════════════════════════════════════════════════════════════════════════════
# AWARE Fund - Makefile
# ═══════════════════════════════════════════════════════════════════════════════
# The Vanguard of Prediction Markets
#
# Usage: make <target>
# Run 'make help' to see all available targets
# ═══════════════════════════════════════════════════════════════════════════════

.PHONY: help local up down build logs status clean deploy-dev deploy-prod test

# Default target
.DEFAULT_GOAL := help

# Colors
GREEN  := $(shell tput -Txterm setaf 2)
YELLOW := $(shell tput -Txterm setaf 3)
BLUE   := $(shell tput -Txterm setaf 4)
RESET  := $(shell tput -Txterm sgr0)

# ═══════════════════════════════════════════════════════════════════════════════
# HELP
# ═══════════════════════════════════════════════════════════════════════════════

help: ## Show this help
	@echo ''
	@echo '${GREEN}AWARE Fund${RESET} - The Vanguard of Prediction Markets'
	@echo ''
	@echo '${YELLOW}Local Development:${RESET}'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E 'local|up|down|build|logs|status|clean' | awk 'BEGIN {FS = ":.*?## "}; {printf "  ${BLUE}%-15s${RESET} %s\n", $$1, $$2}'
	@echo ''
	@echo '${YELLOW}Server Deployment:${RESET}'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E 'deploy|server' | awk 'BEGIN {FS = ":.*?## "}; {printf "  ${BLUE}%-15s${RESET} %s\n", $$1, $$2}'
	@echo ''
	@echo '${YELLOW}Development:${RESET}'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E 'test|lint|java|python' | awk 'BEGIN {FS = ":.*?## "}; {printf "  ${BLUE}%-15s${RESET} %s\n", $$1, $$2}'
	@echo ''

# ═══════════════════════════════════════════════════════════════════════════════
# LOCAL DEVELOPMENT
# ═══════════════════════════════════════════════════════════════════════════════

local: docker-check ## Start full local stack (all services)
	@echo '${GREEN}Starting AWARE Fund local stack...${RESET}'
	docker compose -f docker-compose.local.yaml up -d
	@echo ''
	@echo '${GREEN}Services starting. Access:${RESET}'
	@echo '  Web Dashboard:     http://localhost:3000'
	@echo '  Python API:        http://localhost:8000'
	@echo '  Strategy Service:  http://localhost:8081'
	@echo '  Executor Service:  http://localhost:8080'
	@echo '  ClickHouse:        http://localhost:8123'
	@echo ''
	@echo 'Run ${BLUE}make logs${RESET} to view logs'
	@echo 'Run ${BLUE}make status${RESET} to check health'

up: local ## Alias for 'make local'

down: ## Stop all local services
	@echo '${YELLOW}Stopping all services...${RESET}'
	docker compose -f docker-compose.local.yaml down
	@echo '${GREEN}Done!${RESET}'

build: docker-check ## Rebuild and start local stack
	@echo '${GREEN}Rebuilding AWARE Fund...${RESET}'
	docker compose -f docker-compose.local.yaml build
	docker compose -f docker-compose.local.yaml up -d

logs: ## View logs (usage: make logs or make logs SERVICE=strategy)
	@if [ -z "$(SERVICE)" ]; then \
		docker compose -f docker-compose.local.yaml logs -f --tail=100; \
	else \
		docker compose -f docker-compose.local.yaml logs -f --tail=100 $(SERVICE); \
	fi

status: ## Check service health status
	@echo '${GREEN}Service Status:${RESET}'
	@echo ''
	@docker compose -f docker-compose.local.yaml ps
	@echo ''
	@echo '${GREEN}Health Checks:${RESET}'
	@curl -s http://localhost:8080/api/polymarket/health > /dev/null 2>&1 && echo '  ✓ Executor (8080)' || echo '  ✗ Executor (8080)'
	@curl -s http://localhost:8081/api/strategy/status > /dev/null 2>&1 && echo '  ✓ Strategy (8081)' || echo '  ✗ Strategy (8081)'
	@curl -s http://localhost:8000/health > /dev/null 2>&1 && echo '  ✓ API (8000)' || echo '  ✗ API (8000)'
	@curl -s http://localhost:3000 > /dev/null 2>&1 && echo '  ✓ Web (3000)' || echo '  ✗ Web (3000)'
	@curl -s http://localhost:8123 > /dev/null 2>&1 && echo '  ✓ ClickHouse (8123)' || echo '  ✗ ClickHouse (8123)'

clean: ## Stop all services and remove volumes
	@echo '${YELLOW}Stopping and removing all containers and volumes...${RESET}'
	docker compose -f docker-compose.local.yaml down -v
	@echo '${GREEN}Cleaned!${RESET}'

monitor: docker-check ## Start with Prometheus + Grafana monitoring
	docker compose -f docker-compose.local.yaml --profile monitoring up -d
	@echo ''
	@echo '${GREEN}Monitoring started:${RESET}'
	@echo '  Grafana:    http://localhost:3001 (admin/admin)'
	@echo '  Prometheus: http://localhost:9090'

# ═══════════════════════════════════════════════════════════════════════════════
# INFRASTRUCTURE ONLY (for running Java services from IDE)
# ═══════════════════════════════════════════════════════════════════════════════

infra: docker-check ## Start only infrastructure (ClickHouse, Kafka) for IDE dev
	@echo '${GREEN}Starting infrastructure only...${RESET}'
	docker compose -f docker-compose.analytics.yaml up -d
	@echo ''
	@echo '${GREEN}Infrastructure ready:${RESET}'
	@echo '  ClickHouse: localhost:8123'
	@echo '  Kafka:      localhost:9092'

infra-down: ## Stop infrastructure
	docker compose -f docker-compose.analytics.yaml down

# ═══════════════════════════════════════════════════════════════════════════════
# JAVA SERVICES (run from Maven, not Docker)
# ═══════════════════════════════════════════════════════════════════════════════

java-build: ## Build all Java services
	@echo '${GREEN}Building Java services...${RESET}'
	mvn clean package -DskipTests

java-test: ## Run Java tests
	mvn test

executor: ## Start executor-service (requires infra)
	cd executor-service && mvn spring-boot:run -Dspring-boot.run.profiles=develop

strategy: ## Start strategy-service (requires infra + executor)
	cd strategy-service && mvn spring-boot:run -Dspring-boot.run.profiles=develop

ingestor: ## Start ingestor-service (requires infra)
	cd ingestor-service && mvn spring-boot:run -Dspring-boot.run.profiles=develop

# ═══════════════════════════════════════════════════════════════════════════════
# PYTHON SERVICES
# ═══════════════════════════════════════════════════════════════════════════════

python-setup: ## Setup Python virtual environments
	@echo '${GREEN}Setting up Python environments...${RESET}'
	cd aware-fund/services/analytics && python -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd aware-fund/services/api && python -m venv .venv && .venv/bin/pip install -r requirements.txt

python-analytics: ## Run analytics jobs (requires infra)
	cd aware-fund/services/analytics && source .venv/bin/activate && CLICKHOUSE_HOST=localhost python run_all.py

python-api: ## Start Python API (requires infra)
	cd aware-fund/services/api && source .venv/bin/activate && CLICKHOUSE_HOST=localhost uvicorn main:app --reload --host 0.0.0.0 --port 8000

# ═══════════════════════════════════════════════════════════════════════════════
# WEB DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

web-install: ## Install web dependencies
	cd aware-fund/services/web && npm install

web-dev: ## Start web dashboard in dev mode
	cd aware-fund/services/web && npm run dev

web-build: ## Build web dashboard for production
	cd aware-fund/services/web && npm run build

# ═══════════════════════════════════════════════════════════════════════════════
# SERVER DEPLOYMENT
# ═══════════════════════════════════════════════════════════════════════════════

deploy-dev: ## Deploy to development server
	@echo '${GREEN}Deploying to DEV server...${RESET}'
	ssh aware-dev 'cd /opt/aware && git pull && make server-restart ENV=dev'

deploy-prod: ## Deploy to production server (requires confirmation)
	@echo '${YELLOW}⚠️  You are about to deploy to PRODUCTION${RESET}'
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ] || exit 1
	@echo '${GREEN}Deploying to PROD server...${RESET}'
	ssh aware-prod 'cd /opt/aware && git pull && make server-restart ENV=prod'

server-restart: ## Restart services on server (used by deploy)
	docker compose -f deploy/docker-compose.$(ENV).yaml build
	docker compose -f deploy/docker-compose.$(ENV).yaml up -d

server-logs: ## View server logs
	docker compose -f deploy/docker-compose.$(ENV).yaml logs -f --tail=100

server-status: ## Check server status
	docker compose -f deploy/docker-compose.$(ENV).yaml ps

# ═══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

docker-check:
	@docker info > /dev/null 2>&1 || (echo '${YELLOW}Docker is not running. Please start Docker.${RESET}' && exit 1)

clickhouse-shell: ## Open ClickHouse SQL shell
	docker exec -it aware-clickhouse clickhouse-client

redpanda-shell: ## Open Redpanda/Kafka shell
	docker exec -it aware-redpanda rpk topic list

psql: ## Alias for clickhouse-shell
	$(MAKE) clickhouse-shell

# Show fund status
fund-status: ## Show all fund status
	@curl -s http://localhost:8081/api/strategy/funds/all | python3 -m json.tool

# Run PSI index rebuild
psi-rebuild: ## Rebuild all PSI indices
	cd aware-fund/services/analytics && source .venv/bin/activate && CLICKHOUSE_HOST=localhost python -c "from psi_index import *; import clickhouse_connect; c=clickhouse_connect.get_client(host='localhost',port=8123,database='polybot'); b=PSIIndexBuilder(c); [b.save_index(b.build_index(t)) for t in [IndexType.PSI_10, IndexType.PSI_25, IndexType.PSI_CRYPTO, IndexType.PSI_SPORTS, IndexType.PSI_ALPHA]]"
