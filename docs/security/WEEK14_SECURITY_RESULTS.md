# Week 14 Security Results

Date: 2026-04-19
Branch: week14-SecurityHardening

## Scope
- secrets and auth hardening
- HTTP security headers
- rate limiting on sensitive Flask routes
- input validation for login, pagination, search, and upload paths
- ML pickle trust-boundary guard
- non-root hardening for runtime Dockerfiles
- security-focused tests and supporting documentation

## Implemented
- Moved Flask secret and demo credentials out of source code and into env-driven config.
- Added centralized app config helpers in `src/flask_app/config.py`.
- Added security headers and cache controls in `src/flask_app/security.py`.
- Added route-level rate limiting in `src/flask_app/limiter.py`.
- Added request validation helpers in `src/flask_app/validators.py`.
- Hardened `src/flask_app/app.py` for validated login, pagination, search, and upload handling.
- Added trust-boundary checks for local pickle loading in `src/ml/hybrid_pipeline.py`.
- Switched runtime Dockerfiles to non-root execution with `appuser`.
- Added security-focused tests in `tests/unit/test_security.py` and updated Flask tests accordingly.

## Validation Commands
```bash
./venv/bin/python -m py_compile src/flask_app/config.py src/flask_app/security.py src/flask_app/limiter.py src/flask_app/validators.py src/flask_app/app.py src/ml/hybrid_pipeline.py tests/test_flask_app.py tests/unit/test_security.py
wsl bash -lc "cd /home/raulb/projects/log-monitor-mlops && ./venv/bin/python -m pytest tests/unit/test_security.py tests/test_flask_app.py -q --no-cov"
wsl bash -lc "cd /home/raulb/projects/log-monitor-mlops && docker compose -f docker/docker-compose.yml config"
wsl bash -lc "cd /home/raulb/projects/log-monitor-mlops && ./venv/bin/python -m bandit -r src/flask_app src/ml/hybrid_pipeline.py -f txt"
```

## Latest Validation Results
- `py_compile`: passed.
- Targeted security test suite: passed with `54 passed in 3.65s`.
- `docker compose config`: passed.
- Focused Bandit scan: `14 low`, `0 medium`, `0 high` findings.
- Non-root Docker hardening verified in all runtime Dockerfiles:
  - `Dockerfile.flask`
  - `Dockerfile.dashboard`
  - `Dockerfile.ingester`
  - `Dockerfile.ml-pipeline`
  - `Dockerfile.rule-engine`

## Bandit Summary
Focused Bandit scan on `src/flask_app` and `src/ml/hybrid_pipeline.py` still reports low-severity residual findings in `src/flask_app/traffic_generator.py`.

Residual findings observed:
- `B311` on pseudo-random usage in the traffic generator.

Interpretation:
- These findings are in the log and attack simulation utility, not in the hardened Flask request path or the ML pickle trust-boundary code.
- The Week 14 Flask surface and `hybrid_pipeline.py` changes introduced in this branch did not produce remaining medium or high findings in the focused scan.

## Notes
- The repository-wide coverage gate is still higher-level than this Week 14 slice because the repo includes other modules such as dashboard and ingestion code that are outside this security-only validation run.
- Unrelated existing untracked content remains outside the Week 14 scope:
  - `apps/`
  - `docs/WEEK14_PLAN.md`
