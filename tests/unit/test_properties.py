from __future__ import annotations

from datetime import timezone

from hypothesis import given
from hypothesis import strategies as st

from src.log_processor.ingester import prepare_log_for_insert
from src.ml.hybrid_pipeline import HybridPipeline


def _pipeline() -> HybridPipeline:
    pipeline = object.__new__(HybridPipeline)
    pipeline.rule_weight = 0.55
    pipeline.ml_weight = 0.45
    return pipeline


class TestHybridPipelineProperties:
    @given(
        rule_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        ml_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_final_score_always_in_0_1(self, rule_score, ml_score):
        result = _pipeline().combine_scores(rule_score, ml_score)
        assert 0.0 <= result <= 1.0

    @given(
        score_a=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        score_b=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    def test_higher_score_never_lower_severity(self, score_a, score_b):
        order = {"NORMAL": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        pipeline = _pipeline()

        if score_a >= score_b:
            assert order[pipeline.classify_severity(score_a)] >= order[pipeline.classify_severity(score_b)]

    @given(score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
    def test_classify_always_returns_valid_severity(self, score):
        assert _pipeline().classify_severity(score) in {"NORMAL", "MEDIUM", "HIGH", "CRITICAL"}


class TestIngestionProperties:
    @given(st.datetimes(timezones=st.just(timezone.utc)).map(lambda dt: dt.isoformat()))
    def test_prepare_log_for_insert_preserves_valid_iso_timestamps(self, timestamp):
        row = prepare_log_for_insert(
            {
                "timestamp": timestamp,
                "ip": "127.0.0.1",
                "method": "GET",
                "endpoint": "/health",
                "status": 200,
                "response_time_ms": 15,
                "user_agent": "hypothesis",
            }
        )
        assert row[1] is not None
        assert len(row) == 9
