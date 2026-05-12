from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.ml.hybrid_pipeline import HybridPipeline


@pytest.fixture
def pipeline(tmp_path, mocker, mock_model, mock_scaler):
    features_path = tmp_path / "features.txt"
    features_path.write_text("status_code\nresponse_time_ms\nendpoint_entropy\n", encoding="utf-8")

    cursor = mocker.Mock()
    cursor.fetchall.return_value = []
    conn = mocker.Mock()
    conn.cursor.return_value = cursor

    bundle = {"model": mock_model, "scaler": mock_scaler}
    mocker.patch("src.ml.hybrid_pipeline._safe_load_pickle", return_value=bundle)
    mocker.patch("src.ml.hybrid_pipeline.psycopg2.connect", return_value=conn)

    return HybridPipeline(
        model_path="models/model.pkl",
        scaler_path="models/scaler.pkl",
        features_path=str(features_path),
    )


class TestHybridPipelineScoring:
    def test_weights_sum_validation(self, tmp_path, mocker):
        features_path = tmp_path / "features.txt"
        features_path.write_text("feature1\n", encoding="utf-8")

        bundle = {"model": MagicMock(), "scaler": MagicMock()}
        mocker.patch("src.ml.hybrid_pipeline._safe_load_pickle", return_value=bundle)
        mocker.patch("src.ml.hybrid_pipeline.psycopg2.connect", return_value=mocker.Mock())

        with pytest.raises(ValueError):
            HybridPipeline(
                model_path="models/model.pkl",
                scaler_path="models/scaler.pkl",
                features_path=str(features_path),
                rule_weight=0.6,
                ml_weight=0.6,
            )

    def test_get_rule_score_prefers_highest_severity(self, pipeline):
        cursor = pipeline.conn.cursor.return_value
        cursor.fetchall.return_value = [
            ("port_scanning", "LOW"),
            ("sql_injection", "CRITICAL"),
        ]

        score, rule_ids = pipeline.get_rule_score(123)

        assert score == 1.0
        assert rule_ids == ["port_scanning", "sql_injection"]

    def test_get_ml_score_clamps_to_expected_range(self, pipeline, mock_model):
        mock_model.decision_function.return_value = [-1.0]

        score, confidence = pipeline.get_ml_score(
            {"status_code": 401.0, "response_time_ms": 50.0, "endpoint_entropy": 1.2}
        )

        assert 0.99 <= score <= 1.0
        assert 0.0 <= confidence <= 1.0

    def test_combine_scores_applies_critical_override(self, pipeline):
        result = pipeline.combine_scores(rule_score=1.0, ml_score=0.0)
        assert result >= 0.75

    @pytest.mark.parametrize(
        "score,expected",
        [
            (0.95, "CRITICAL"),
            (0.80, "CRITICAL"),
            (0.79, "HIGH"),
            (0.60, "HIGH"),
            (0.59, "MEDIUM"),
            (0.40, "MEDIUM"),
            (0.39, "NORMAL"),
        ],
    )
    def test_classify_severity_thresholds(self, pipeline, score, expected):
        assert pipeline.classify_severity(score) == expected

    def test_evaluate_log_returns_expected_payload(self, pipeline, mocker):
        persist_mock = mocker.patch.object(pipeline, "_persist")
        mocker.patch.object(pipeline, "get_rule_score", return_value=(0.75, ["brute_force"]))
        mocker.patch.object(pipeline, "get_ml_score", return_value=(0.50, 0.40))

        result = pipeline.evaluate_log(
            99,
            {"status_code": 401.0, "response_time_ms": 50.0, "endpoint_entropy": 1.1},
        )

        assert result["log_id"] == 99
        assert result["severity"] == "HIGH"
        assert result["is_anomaly"] is True
        persist_mock.assert_called_once_with(result)

    def test_persist_inserts_row(self, pipeline):
        result = {
            "log_id": 5,
            "rule_score": 0.75,
            "ml_score": 0.25,
            "final_score": 0.525,
            "severity": "MEDIUM",
            "triggered_rules": ["brute_force"],
            "ml_confidence": 0.5,
            "is_anomaly": True,
        }

        pipeline._persist(result)

        cursor = pipeline.conn.cursor.return_value
        cursor.execute.assert_called_once()
        pipeline.conn.commit.assert_called_once()
