#!/bin/sh
set -e

pg_isready -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-logmonitor}" >/dev/null 2>&1 || exit 1

TABLES=$(psql -U "${POSTGRES_USER:-postgres}" \
              -d "${POSTGRES_DB:-logmonitor}" \
              -tAc "SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_schema='public'
                    AND table_name IN ('raw_logs','alerts','ml_predictions','model_runs','feedback','hybrid_scores')")

if [ "$TABLES" -lt 4 ]; then
    echo "Schema nao inicializado ainda (so $TABLES tabelas encontradas)"
    exit 1
fi

echo "PostgreSQL OK - $TABLES tabelas encontradas"
exit 0
