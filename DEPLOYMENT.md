# AWARE Fund - Deployment Guide

The Vanguard of Prediction Markets

## Quick Start

### Local Development (One Command)

```bash
# Start everything
make local

# Check status
make status

# View logs
make logs

# Stop
make down
```

### What Gets Started

| Service | Port | Description |
|---------|------|-------------|
| Web Dashboard | 3000 | Next.js frontend |
| Python API | 8000 | FastAPI backend |
| Strategy Service | 8081 | Fund engine (Java) |
| Executor Service | 8080 | Order execution (Java) |
| Ingestor Service | 8083 | Data pipeline (Java) |
| Analytics | - | Scoring jobs (Python cron) |
| ClickHouse | 8123 | Time-series database |
| Kafka (Redpanda) | 9092 | Event streaming |

---

## Development Options

### Option 1: Full Docker Stack (Recommended for Testing)
```bash
make local          # Start all services in Docker
make status         # Verify everything is running
```

### Option 2: Infrastructure + IDE (For Java Development)
```bash
make infra          # Start only ClickHouse + Kafka

# In separate terminals, run from IDE or:
make executor       # Terminal 1: Start executor
make strategy       # Terminal 2: Start strategy (after executor is healthy)
make ingestor       # Terminal 3: Start ingestor
```

### Option 3: Hybrid (Python in Docker, Java in IDE)
```bash
make infra                    # Start infrastructure
make local SERVICE=analytics  # Start Python services
# Run Java services from IDE
```

---

## Server Deployment

### Prerequisites

1. **VPS Server** (Hetzner CAX31 recommended: €16/mo)
   - 8 ARM cores, 16GB RAM, 320GB NVMe
   - Ubuntu 22.04 LTS

2. **Domain** (e.g., `app.aware.fund`)

3. **SSH Access** configured in `~/.ssh/config`:
   ```
   Host aware-dev
       HostName your-dev-server-ip
       User root

   Host aware-prod
       HostName your-prod-server-ip
       User root
   ```

### First-Time Server Setup

```bash
# SSH into server
ssh aware-dev

# Clone repo
git clone git@github.com:YOUR_ORG/aware.git /opt/aware
cd /opt/aware

# Run setup script
./deploy/deploy.sh setup

# Configure environment
cp deploy/.env.example deploy/.env
nano deploy/.env  # Fill in your values

# Setup SSL (optional for dev)
./deploy/deploy.sh ssl

# Deploy
make server-restart ENV=dev
```

### Deploy Updates

```bash
# Deploy to dev server
make deploy-dev

# Deploy to production (requires confirmation)
make deploy-prod
```

### Server Commands

```bash
# On server, check status
make server-status ENV=dev

# View logs
make server-logs ENV=dev

# Restart services
make server-restart ENV=dev
```

---

## Environment Variables

### Required for LIVE Trading

```env
# Trading mode
HFT_MODE=LIVE  # or PAPER (default)

# Polymarket API (from https://polymarket.com/settings/api)
POLYMARKET_API_KEY=your_key
POLYMARKET_API_SECRET=your_secret
POLYMARKET_PASSPHRASE=your_passphrase
POLYMARKET_PRIVATE_KEY=your_wallet_private_key
```

### Optional (Notifications)

```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
TELEGRAM_BOT_TOKEN=<YOUR_TELEGRAM_BOT_TOKEN>
TELEGRAM_CHAT_ID=<YOUR_TELEGRAM_CHAT_ID>
```

---

## Directory Structure

```
aware/
├── Makefile                    # Main entry point
├── docker-compose.local.yaml   # Local development
├── docker-compose.analytics.yaml # Infrastructure only
├── deploy/
│   ├── docker-compose.dev.yaml  # Server dev environment
│   ├── docker-compose.prod.yaml # Server production
│   ├── Dockerfile.java          # Java services
│   ├── Dockerfile.web           # Next.js dashboard
│   ├── nginx/                   # Nginx config
│   ├── monitoring/              # Prometheus config
│   ├── deploy.sh                # Server deployment script
│   └── .env.example             # Environment template
├── executor-service/            # Java - Order execution
├── strategy-service/            # Java - Fund engine
├── ingestor-service/            # Java - Data pipeline
└── aware-fund/
    └── services/
        ├── analytics/           # Python - Scoring jobs
        ├── api/                 # Python - REST API
        └── web/                 # Next.js - Dashboard
```

---

## Useful Commands

```bash
# Makefile targets
make help           # Show all commands
make local          # Start local stack
make down           # Stop local stack
make logs           # View all logs
make logs SERVICE=strategy  # View specific service
make status         # Health check
make clean          # Remove all data
make monitor        # Start with Grafana/Prometheus

# Direct commands
make clickhouse-shell  # ClickHouse SQL shell
make fund-status       # Show fund metrics
make psi-rebuild       # Rebuild PSI indices

# Deployment
make deploy-dev     # Deploy to dev server
make deploy-prod    # Deploy to production
```

---

## Troubleshooting

### Services not starting
```bash
make logs SERVICE=strategy  # Check specific logs
docker compose -f docker-compose.local.yaml ps  # Check container status
```

### ClickHouse connection issues
```bash
curl http://localhost:8123  # Should return "Ok.\n"
make clickhouse-shell       # Try interactive shell
```

### Port conflicts
```bash
lsof -i :8080  # Check what's using port 8080
make down      # Stop all services
```

### Rebuild from scratch
```bash
make clean     # Remove all containers and volumes
make build     # Rebuild images
make local     # Start fresh
```

---

## Trading Modes

| Mode | Description | Risk |
|------|-------------|------|
| **PAPER** | Simulated execution against live order book | None (no real money) |
| **LIVE** | Real orders on Polymarket | Real capital at risk |

⚠️ **Always test thoroughly in PAPER mode before switching to LIVE**
