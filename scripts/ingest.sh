#!/bin/bash
set -e

LOG_FILE=${1:-logs/app.log}
BATCH_SIZE=${2:-500}
LOG_FORMAT=${3:-json}

echo "=== Ingesting logs from $LOG_FILE ==="
echo "=== Log format: $LOG_FORMAT ==="
python src/log_processor/ingester.py "$LOG_FILE" --batch-size "$BATCH_SIZE" --format "$LOG_FORMAT"

echo ""
echo "=== Verification ==="
docker compose -f docker/docker-compose.yml exec postgres psql -U postgres -d logmonitor -c "SELECT COUNT(*) FROM raw_logs;"

echo ""
echo "=== Done! ==="
