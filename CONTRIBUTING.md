# Development Guide

Internal development guidelines for the AWARE repository.

## Setup

```bash
# Prerequisites
- Java 21+
- Maven 3.8+
- Python 3.11+
- Docker & Docker Compose

# Build
mvn clean package -DskipTests

# Infrastructure
docker-compose -f docker-compose.analytics.yaml up -d
```

## Code Style

### Java
- Use records for immutable data
- Use `@Slf4j` for logging
- Keep methods focused and small

### Python
- Follow PEP 8
- Use type hints
- Document with docstrings

## Git Workflow

```bash
# Feature branches
git checkout -b feature/description
git push origin feature/description

# Commits
git commit -m "Add/Fix/Update: description"
```

## Testing

```bash
# Java tests
mvn test

# Paper trading test
mvn spring-boot:run -Dspring-boot.run.profiles=develop

# Research validation
cd research && python sim_trade_match_report.py
```

## Security

Never commit:
- Private keys / API keys
- `.env` files with real credentials
- Wallet addresses with funds
