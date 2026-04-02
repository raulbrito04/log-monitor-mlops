#!/bin/bash
set -e

LOG_FILE=${1:-logs/app.log}
BATCH_SIZE=${2:-500}

echo "=== Ingesting logs from $LOG_FILE ==="
python src/log_processor/ingester.py "$LOG_FILE" --batch-size "$BATCH_SIZE"

echo ""
echo "=== Verification ==="
docker compose -f docker/docker-compose.yml exec postgres psql -U postgres -d logmonitor -c "SELECT COUNT(*) FROM raw_logs;"

echo ""
echo "=== Done! ==="
