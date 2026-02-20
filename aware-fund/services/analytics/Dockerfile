FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for ML
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY *.py ./
COPY ml/ ./ml/
COPY notifications/ ./notifications/

# Environment defaults
ENV CLICKHOUSE_HOST=clickhouse
ENV CLICKHOUSE_PORT=8123
ENV CLICKHOUSE_DATABASE=polybot
ENV SCORING_INTERVAL_SECONDS=3600
ENV MIN_TRADES=10
ENV MAX_TRADERS=10000
ENV LOG_LEVEL=INFO
ENV PYTHONUNBUFFERED=1

# Default: run ML analytics continuously (hourly scoring + drift monitoring)
CMD ["python", "run_all.py", "--continuous", "--interval", "3600"]
