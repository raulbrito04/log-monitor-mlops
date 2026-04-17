from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.detection import rule_engine


class TestRuleDefinitions:
    def test_get_rules_returns_six_queries(self):
        rules = rule_engine.get_rules("7 days")
        assert len(rules) == 6
        assert all("7 days" in sql for _, sql in rules)

    def test_sql_injection_rule_contains_expected_patterns(self):
        rules = dict(rule_engine.get_rules("60 seconds"))
        sql = rules["SQL Injection Detection"]
        assert "union" in sql.lower()
        assert "or%1=1" in sql.lower()
        assert "drop%table" in sql.lower()


class TestRuleExecution:
    def test_execute_rule_returns_rowcount_on_success(self):
        cursor = MagicMock()
        cursor.rowcount = 3

        result = rule_engine.execute_rule(cursor, "Brute Force Detection", "SELECT 1")

        cursor.execute.assert_called_once_with("SELECT 1")
        assert result == 3

    def test_execute_rule_returns_zero_on_exception(self):
        cursor = MagicMock()
        cursor.execute.side_effect = RuntimeError("boom")

        result = rule_engine.execute_rule(cursor, "Brute Force Detection", "SELECT 1")

        assert result == 0

    def test_run_once_accumulates_alert_counts(self):
        cursor = MagicMock()
        with patch.object(rule_engine, "execute_rule", side_effect=[1, 2, 0, 1, 0, 4]):
            total = rule_engine.run_once(cursor, "7 days", "TEST")

        assert total == 8
