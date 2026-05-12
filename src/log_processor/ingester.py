"""
Log ingestion pipeline: reads JSON logs and inserts into PostgreSQL.

Usage:
    python src/log_processor/ingester.py logs/app.log
    python src/log_processor/ingester.py logs/app.log --batch-size 500
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Optional

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "database": os.getenv("POSTGRES_DB", "logmonitor"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "changeme"),
}


def get_db_connection(max_retries: int = 5):
    """Create database connection with retry logic."""
    for attempt in range(max_retries):
        try:
            return psycopg2.connect(**DB_CONFIG)
        except psycopg2.OperationalError:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"Connection failed (attempt {attempt + 1}/{max_retries})")
                print(f"Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"ERROR: Could not connect after {max_retries} attempts")
                raise


def parse_log_line(line: str) -> Optional[dict]:
    """Parse JSON log line into dict."""
    try:
        return json.loads(line.strip())
    except json.JSONDecodeError as e:
        print(f"WARNING: Failed to parse line: {line[:100]}... ({e})")
        return None


def prepare_log_for_insert(log: dict) -> tuple:
    """Extract fields from log dict for INSERT."""
    timestamp = log.get("timestamp")

    if timestamp is None:
        timestamp = datetime.now()

    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            try:
                timestamp = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                print(f"WARNING: Invalid timestamp format: {timestamp}")
                timestamp = datetime.now()
    elif not isinstance(timestamp, datetime):
        timestamp = datetime.now()

    return (
        log.get("log_type", "web"),
        timestamp,
        log.get("ip"),
        log.get("method"),
        log.get("endpoint"),
        log.get("status"),
        log.get("response_time_ms"),
        log.get("user_agent"),
        json.dumps(log),
    )


def insert_logs_batch(cursor, logs: list[dict]):
    """Insert batch of logs using execute_values (fast)."""
    if not logs:
        return 0

    query = """
        INSERT INTO raw_logs (
            log_type, timestamp, ip, method, endpoint,
            status, response_time_ms, user_agent, data
        ) VALUES %s
    """

    data = [prepare_log_for_insert(log) for log in logs]
    execute_values(cursor, query, data, page_size=len(data))
    return len(data)


def ingest_from_file(filepath: str, batch_size: int = 100):
    """Ingest logs from file in batches."""
    if not os.path.exists(filepath):
        print(f"ERROR: File not found: {filepath}")
        sys.exit(1)

    print(f"Starting ingestion from: {filepath}")
    print(f"Batch size: {batch_size}")
    print(f"Connecting to PostgreSQL at {DB_CONFIG['host']}:{DB_CONFIG['port']}")

    conn = get_db_connection()
    cursor = conn.cursor()

    batch = []
    total_ingested = 0
    total_failed = 0
    start_time = time.time()

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                log = parse_log_line(line)

                if log:
                    batch.append(log)
                else:
                    total_failed += 1

                if len(batch) >= batch_size:
                    try:
                        inserted = insert_logs_batch(cursor, batch)
                        conn.commit()
                        total_ingested += inserted
                        print(f"✓ Ingested {total_ingested} logs (line {line_num})")
                    except Exception as e:
                        conn.rollback()
                        print(f"ERROR inserting batch at line {line_num}: {e}")
                        total_failed += len(batch)
                    finally:
                        batch = []

        if batch:
            try:
                inserted = insert_logs_batch(cursor, batch)
                conn.commit()
                total_ingested += inserted
                print(f"✓ Ingested {total_ingested} logs (final batch)")
            except Exception as e:
                conn.rollback()
                print(f"ERROR inserting final batch: {e}")
                total_failed += len(batch)

        elapsed = time.time() - start_time
        rate = total_ingested / elapsed if elapsed > 0 else 0

        print("\n" + "=" * 50)
        print("INGESTION COMPLETE")
        print("=" * 50)
        print(f"Total ingested: {total_ingested}")
        print(f"Total failed:   {total_failed}")
        print(f"Time elapsed:   {elapsed:.2f}s")
        print(f"Ingestion rate: {rate:.0f} logs/second")

    except KeyboardInterrupt:
        print("\n\nIngestion interrupted by user")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Ingest JSON logs into PostgreSQL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ingester.py logs/app.log
  python ingester.py logs/app.log --batch-size 500
  python ingester.py logs/production.log --batch-size 1000
        """,
    )

    parser.add_argument("logfile", help="Path to JSON log file")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of logs to insert per batch (default: 100)",
    )

    args = parser.parse_args()
    ingest_from_file(args.logfile, args.batch_size)


if __name__ == "__main__":
    main()
