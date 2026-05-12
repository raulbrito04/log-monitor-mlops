# Week 12 Testing & QA Results

Date: 2026-04-15  
Branch: semana12-testing-qa

## Scope Implemented
- `pytest.ini` with global pytest and coverage configuration
- shared fixtures in `tests/conftest.py`
- unit tests for rule engine, hybrid pipeline, ingester, monitoring metrics, and property-based checks
- integration tests against a dedicated PostgreSQL test database
- stress test for 50,000 log ingestions
- headless Locust load test and HTML report generation
- JUnit XML and HTML coverage artifacts for later CI/CD work

## Final Validation Results
### 1. Main pytest suite
Command:
```bash
./venv/bin/python -m pytest tests -q -m 'not slow' --junitxml=reports/pytest_results.xml
```
Result:
- `81 passed`
- `1 skipped`
- `1 deselected`
- coverage: `71.15%`

Notes:
- the skipped test is the MLflow smoke test when `localhost:5000` is unavailable
- coverage target `>= 70%` was reached

### 2. Stress test
Command:
```bash
./venv/bin/python -m pytest tests/test_stress.py -q -m slow -s --cov-fail-under=0
```
Result:
- passed
- validates ingestion of `50,000` logs without crashes
- query checks stayed below the configured threshold

### 3. Load test
Command:
```bash
./venv/bin/locust -f tests/load/locustfile.py \
  --host=http://localhost:5001 \
  --users=50 \
  --spawn-rate=5 \
  --run-time=30s \
  --headless \
  --html=reports/load_test_report.html
```
Result summary:
- total requests: `499`
- failures: `0`
- requests/s: `19.0`
- median latency: `3ms`
- p95 latency: `10ms`
- p99 latency: `25ms`
- max latency: `34ms`

Conclusion:
- the tutorial target `p99 < 100ms` was achieved comfortably

## Important Code Changes
- added test tooling dependencies to `requirements.txt`
- added `pytest.ini`
- added `.coveragerc`
- added `tests/unit/`, `tests/integration/`, `tests/load/`
- hardened `src/log_processor/ingester.py` so missing timestamps fall back safely instead of propagating invalid values
- converted `tests/test_mlflow.py` into a proper pytest smoke test with graceful skip behavior
- adjusted `tests/test_flask_app.py` to isolate Prometheus registration during tests

## Generated Artifacts
- coverage HTML: `reports/coverage_html/index.html`
- JUnit XML: `reports/pytest_results.xml`
- Locust HTML report: `reports/load_test_report.html`

## Tutorial Goals Status
- unit tests with coverage >= 70%: achieved
- integration tests against separate PostgreSQL test DB: achieved
- stress test 50k logs: achieved
- property-based testing with Hypothesis: achieved
- load testing with Locust: achieved