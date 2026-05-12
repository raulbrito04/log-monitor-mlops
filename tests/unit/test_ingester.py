from __future__ import annotations

import json
from datetime import datetime

import psycopg2
import pytest

from src.log_processor import ingester


class TestLogParser:
    def test_parse_log_line_valid_json(self):
        line = json.dumps({"timestamp": "2025-01-01T12:00:00+00:00", "status": 200})
        assert ingester.parse_log_line(line)["status"] == 200

    def test_parse_log_line_invalid_json_returns_none(self):
        assert ingester.parse_log_line("{invalid json") is None


class TestPrepareLogForInsert:
    def test_prepare_log_for_insert_converts_iso_timestamp(self):
        row = ingester.prepare_log_for_insert(
            {
                "timestamp": "2025-01-01T12:00:00+00:00",
                "ip": "127.0.0.1",
                "method": "GET",
                "endpoint": "/health",
                "status": 200,
                "response_time_ms": 10,
                "user_agent": "pytest",
            }
        )

        assert isinstance(row[1], datetime)
        assert row[2] == "127.0.0.1"
        assert row[4] == "/health"

    def test_prepare_log_for_insert_defaults_missing_timestamp(self):
        row = ingester.prepare_log_for_insert(
            {
                "ip": "127.0.0.1",
                "method": "GET",
                "endpoint": "/health",
                "status": 200,
                "response_time_ms": 10,
                "user_agent": "pytest",
            }
        )

        assert isinstance(row[1], datetime)


class TestBatchInsert:
    def test_insert_logs_batch_uses_execute_values(self, mocker):
        execute_values = mocker.patch("src.log_processor.ingester.execute_values")
        cursor = mocker.Mock()
        logs = [
            {
                "timestamp": "2025-01-01T12:00:00+00:00",
                "ip": "127.0.0.1",
                "method": "GET",
                "endpoint": "/health",
                "status": 200,
                "response_time_ms": 10,
                "user_agent": "pytest",
            }
        ]

        inserted = ingester.insert_logs_batch(cursor, logs)

        assert inserted == 1
        execute_values.assert_called_once()

    def test_get_db_connection_retries_then_succeeds(self, mocker):
        conn = mocker.Mock()
        connect = mocker.patch(
            "src.log_processor.ingester.psycopg2.connect",
            side_effect=[psycopg2.OperationalError("down"), conn],
        )
        sleep = mocker.patch("src.log_processor.ingester.time.sleep")

        result = ingester.get_db_connection(max_retries=2)

        assert result is conn
        assert connect.call_count == 2
        sleep.assert_called_once()

    def test_ingest_from_file_processes_batches(self, tmp_path, mocker):
        logfile = tmp_path / "sample.log"
        logfile.write_text(
            "\n".join(
                [
                    json.dumps({"timestamp": "2025-01-01T12:00:00+00:00", "ip": "127.0.0.1", "method": "GET", "endpoint": "/health", "status": 200, "response_time_ms": 10, "user_agent": "pytest"}),
                    json.dumps({"timestamp": "2025-01-01T12:00:01+00:00", "ip": "127.0.0.2", "method": "GET", "endpoint": "/api/data", "status": 200, "response_time_ms": 11, "user_agent": "pytest"}),
                    "not-json",
                ]
            ),
            encoding="utf-8",
        )

        cursor = mocker.Mock()
        conn = mocker.Mock()
        conn.cursor.return_value = cursor
        mocker.patch("src.log_processor.ingester.get_db_connection", return_value=conn)
        insert_batch = mocker.patch(
            "src.log_processor.ingester.insert_logs_batch",
            side_effect=lambda _cursor, batch: len(batch),
        )

        ingester.ingest_from_file(str(logfile), batch_size=2)

        assert insert_batch.call_count == 1
        conn.commit.assert_called_once()

    def test_ingest_from_file_missing_path_exits(self):
        with pytest.raises(SystemExit):
            ingester.ingest_from_file("/tmp/does-not-exist.log")
