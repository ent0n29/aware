FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY *.py .

# Environment defaults
ENV CLICKHOUSE_HOST=clickhouse
ENV CLICKHOUSE_PORT=8123
ENV CLICKHOUSE_DATABASE=polybot
ENV SCORING_INTERVAL_SECONDS=3600
ENV MIN_TRADES=10
ENV MAX_TRADERS=10000
ENV LOG_LEVEL=INFO

# Default: run orchestrator
CMD ["python", "run_all.py"]
