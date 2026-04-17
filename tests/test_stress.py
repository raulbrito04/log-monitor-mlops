from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time

import psycopg2
import pytest

from src.log_processor import ingester


@pytest.mark.slow
@pytest.mark.integration
def test_ingest_50k_logs_without_crash(test_db, clean_db):
    conn = psycopg2.connect(**test_db)
    cursor = conn.cursor()

    total = 50_000
    batch_size = 5_000
    base_time = datetime.now(timezone.utc) - timedelta(hours=2)

    started = time.time()
    for offset in range(0, total, batch_size):
        batch = []
        for index in range(offset, offset + batch_size):
            batch.append(
                {
                    "log_type": "web",
                    "timestamp": (base_time + timedelta(milliseconds=index)).isoformat(),
                    "ip": f"10.0.{(index // 255) % 255}.{index % 255}",
                    "method": "GET" if index % 5 else "POST",
                    "endpoint": f"/api/resource/{index % 25}",
                    "status": 200 if index % 17 else 500,
                    "response_time_ms": float(20 + (index % 120)),
                    "user_agent": "stress-test",
                }
            )
        inserted = ingester.insert_logs_batch(cursor, batch)
        conn.commit()
        assert inserted == len(batch)

    cursor.execute("SELECT COUNT(*) FROM raw_logs")
    assert cursor.fetchone()[0] == total

    queries = {
        "count_recent": "SELECT COUNT(*) FROM raw_logs WHERE timestamp > NOW() - INTERVAL '1 hour'",
        "top_ips": "SELECT ip, COUNT(*) AS req_count FROM raw_logs GROUP BY ip ORDER BY req_count DESC LIMIT 20",
        "avg_response_time": "SELECT AVG(response_time_ms) FROM raw_logs WHERE timestamp > NOW() - INTERVAL '1 hour'",
    }

    for name, query in queries.items():
        query_started = time.time()
        cursor.execute(query)
        cursor.fetchall()
        elapsed_ms = (time.time() - query_started) * 1000
        assert elapsed_ms < 1000, f"Query '{name}' demorou {elapsed_ms:.1f}ms"

    elapsed = time.time() - started
    assert elapsed < 120

    cursor.close()
    conn.close()
