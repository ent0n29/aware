#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# AWARE Fund Production Deployment Script
# ═══════════════════════════════════════════════════════════════════════════════
# Usage:
#   ./deploy.sh setup     - First-time server setup
#   ./deploy.sh deploy    - Deploy/update the application
#   ./deploy.sh ssl       - Setup SSL certificates
#   ./deploy.sh logs      - View service logs
#   ./deploy.sh status    - Check service status
#   ./deploy.sh stop      - Stop all services
# ═══════════════════════════════════════════════════════════════════════════════

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
DEPLOY_DIR="/opt/aware"
REPO_URL="git@github.com:ent0n29/aware.git"

log() {
    echo -e "${GREEN}[AWARE]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# ─────────────────────────────────────────────────────────────────────────────────
# First-time server setup
# ─────────────────────────────────────────────────────────────────────────────────
setup() {
    log "Setting up AWARE Fund production server..."

    # Update system
    log "Updating system packages..."
    apt-get update && apt-get upgrade -y

    # Install Docker
    if ! command -v docker &> /dev/null; then
        log "Installing Docker..."
        curl -fsSL https://get.docker.com | sh
        systemctl enable docker
        systemctl start docker
    else
        log "Docker already installed"
    fi

    # Install Docker Compose plugin
    if ! docker compose version &> /dev/null; then
        log "Installing Docker Compose plugin..."
        apt-get install -y docker-compose-plugin
    else
        log "Docker Compose already installed"
    fi

    # Install useful tools
    log "Installing utilities..."
    apt-get install -y git curl wget htop ncdu fail2ban ufw

    # Configure firewall
    log "Configuring firewall..."
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow ssh
    ufw allow http
    ufw allow https
    ufw --force enable

    # Configure fail2ban
    log "Configuring fail2ban..."
    systemctl enable fail2ban
    systemctl start fail2ban

    # Create deploy directory
    log "Creating deployment directory..."
    mkdir -p $DEPLOY_DIR
    cd $DEPLOY_DIR

    # Clone repository (if not exists)
    if [ ! -d "$DEPLOY_DIR/.git" ]; then
        log "Cloning repository..."
        git clone $REPO_URL .
    fi

    # Create .env file if not exists
    if [ ! -f "$DEPLOY_DIR/deploy/.env" ]; then
        log "Creating .env file from template..."
        cp $DEPLOY_DIR/deploy/.env.example $DEPLOY_DIR/deploy/.env
        warn "Please edit $DEPLOY_DIR/deploy/.env with your configuration!"
    fi

    log "✅ Server setup complete!"
    log ""
    log "Next steps:"
    log "  1. Edit $DEPLOY_DIR/deploy/.env with your configuration"
    log "  2. Run: ./deploy.sh ssl"
    log "  3. Run: ./deploy.sh deploy"
}

# ─────────────────────────────────────────────────────────────────────────────────
# Setup SSL certificates with Let's Encrypt
# ─────────────────────────────────────────────────────────────────────────────────
ssl() {
    log "Setting up SSL certificates..."

    # Check if .env exists
    if [ ! -f "$DEPLOY_DIR/deploy/.env" ]; then
        error ".env file not found. Run setup first."
    fi

    source $DEPLOY_DIR/deploy/.env

    if [ -z "$DOMAIN" ] || [ -z "$ADMIN_EMAIL" ]; then
        error "DOMAIN and ADMIN_EMAIL must be set in .env"
    fi

    # Create directories
    mkdir -p $DEPLOY_DIR/deploy/nginx/ssl
    mkdir -p /var/www/certbot

    # Start nginx with HTTP only (for certbot challenge)
    log "Starting nginx for certificate challenge..."

    # Create temporary nginx config for certbot
    cat > /tmp/nginx-certbot.conf << 'EOF'
events { worker_connections 1024; }
http {
    server {
        listen 80;
        server_name _;
        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }
        location / {
            return 200 "Certbot challenge server";
        }
    }
}
EOF

    docker run -d --name certbot-nginx \
        -p 80:80 \
        -v /tmp/nginx-certbot.conf:/etc/nginx/nginx.conf:ro \
        -v /var/www/certbot:/var/www/certbot \
        nginx:alpine

    # Get certificate
    log "Requesting certificate for $DOMAIN..."
    docker run --rm \
        -v /etc/letsencrypt:/etc/letsencrypt \
        -v /var/www/certbot:/var/www/certbot \
        certbot/certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        -d $DOMAIN \
        --email $ADMIN_EMAIL \
        --agree-tos \
        --no-eff-email

    # Stop temporary nginx
    docker stop certbot-nginx && docker rm certbot-nginx

    log "✅ SSL certificate obtained!"
    log "Certificate location: /etc/letsencrypt/live/$DOMAIN/"
}

# ─────────────────────────────────────────────────────────────────────────────────
# Deploy application
# ─────────────────────────────────────────────────────────────────────────────────
deploy() {
    log "Deploying AWARE Fund..."

    cd $DEPLOY_DIR

    # Pull latest code
    log "Pulling latest code..."
    git pull origin main

    # Load environment
    if [ -f "$DEPLOY_DIR/deploy/.env" ]; then
        export $(cat $DEPLOY_DIR/deploy/.env | grep -v '^#' | xargs)
    fi

    cd $DEPLOY_DIR/deploy

    # Build and start services
    log "Building and starting services..."
    docker compose -f docker-compose.production.yaml build
    docker compose -f docker-compose.production.yaml up -d

    # Wait for services to be healthy
    log "Waiting for services to start..."
    sleep 30

    # Check status
    status

    log "✅ Deployment complete!"
}

# ─────────────────────────────────────────────────────────────────────────────────
# View logs
# ─────────────────────────────────────────────────────────────────────────────────
logs() {
    SERVICE=${1:-}

    cd $DEPLOY_DIR/deploy

    if [ -z "$SERVICE" ]; then
        docker compose -f docker-compose.production.yaml logs -f --tail=100
    else
        docker compose -f docker-compose.production.yaml logs -f --tail=100 $SERVICE
    fi
}

# ─────────────────────────────────────────────────────────────────────────────────
# Check status
# ─────────────────────────────────────────────────────────────────────────────────
status() {
    log "Service Status:"

    cd $DEPLOY_DIR/deploy
    docker compose -f docker-compose.production.yaml ps

    echo ""
    log "Health Checks:"

    # Check each service
    services=("executor:8080" "strategy:8080" "api:8000" "web:3000")
    for svc in "${services[@]}"; do
        name=$(echo $svc | cut -d: -f1)
        port=$(echo $svc | cut -d: -f2)
        if docker exec aware-$name wget -q --spider http://localhost:$port/health 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} $name"
        else
            echo -e "  ${RED}✗${NC} $name"
        fi
    done
}

# ─────────────────────────────────────────────────────────────────────────────────
# Stop all services
# ─────────────────────────────────────────────────────────────────────────────────
stop() {
    log "Stopping all services..."

    cd $DEPLOY_DIR/deploy
    docker compose -f docker-compose.production.yaml down

    log "✅ All services stopped"
}

# ─────────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────────
case "${1:-help}" in
    setup)
        setup
        ;;
    ssl)
        ssl
        ;;
    deploy)
        deploy
        ;;
    logs)
        logs $2
        ;;
    status)
        status
        ;;
    stop)
        stop
        ;;
    *)
        echo "AWARE Fund Deployment Script"
        echo ""
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo "  setup   - First-time server setup"
        echo "  ssl     - Setup SSL certificates"
        echo "  deploy  - Deploy/update the application"
        echo "  logs    - View service logs (optionally: logs <service>)"
        echo "  status  - Check service status"
        echo "  stop    - Stop all services"
        ;;
esac
