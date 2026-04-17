from __future__ import annotations

import mlflow
import pytest
import requests

TRACKING_URI = "http://localhost:5000"


def _mlflow_available() -> bool:
    try:
        response = requests.get(TRACKING_URI, timeout=2)
        return response.status_code < 500
    except requests.RequestException:
        return False


@pytest.mark.integration
def test_mlflow_tracking_smoke():
    if not _mlflow_available():
        pytest.skip("MLflow server unavailable on localhost:5000")

    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment("test-experiment")

    with mlflow.start_run(run_name="test-run") as run:
        mlflow.log_param("test_param", 42)
        mlflow.log_metric("test_metric", 0.95)
        assert run.info.run_id