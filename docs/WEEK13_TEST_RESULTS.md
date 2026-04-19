# Week 13 CI/CD & Automation Results

Date: 2026-04-17  
Branch: CICDAutomation

## Scope Implemented
- GitHub Actions workflow in `.github/workflows/ci.yml`
- Dependabot configuration in `.github/dependabot.yml`
- development dependency split in `requirements-dev.txt`
- static analysis configuration with `.pylintrc` and `.bandit.yaml`
- README CI badge and project status refresh
- `.gitignore` updates for CI/test artifacts

## Validation Summary
The Week 13 implementation was validated locally as far as possible before any GitHub push.

Status breakdown:
- local quality gate: validated
- local pytest + coverage gate: validated
- local integration command used by CI: validated
- Docker Compose configuration: validated
- GitHub Actions execution on GitHub: pending first push
- Dependabot activation in repository settings: pending manual enablement on GitHub
- badge runtime status on GitHub: pending first workflow run

## Final Validation Results
### 1. Main CI-equivalent pytest suite
Command:
```bash
./venv/bin/python -m pytest tests/unit tests/test_flask_app.py tests/test_dashboard.py tests/test_mlflow.py \
  -q \
  --junitxml=reports/pytest_unit.xml \
  --cov=src \
  --cov-report=xml:reports/coverage.xml \
  --cov-report=html:reports/coverage_html \
  --cov-fail-under=70
```

Result:
- `79 passed`
- `1 skipped`
- coverage: `71.15%`

Notes:
- the skipped test is the MLflow smoke test when `localhost:5000` is unavailable
- the Week 13 CI threshold `>= 70%` is satisfied

### 2. Integration test command used by CI
Command:
```bash
./venv/bin/python -m pytest tests/integration -q -m integration \
  --junitxml=reports/pytest_integration.xml \
  --no-cov
```

Result:
- `2 passed`

Notes:
- `--no-cov` is intentional because the repository `pytest.ini` already enforces a global coverage threshold
- without this override, the integration-only step would inherit the `70%` gate and fail for the wrong reason

### 3. Pylint quality gate
Command:
```bash
./venv/bin/python -m pylint src --rcfile=.pylintrc --fail-under=7.0
```

Result:
- score: `9.18/10`
- quality gate `>= 7.0`: passed

Notes:
- the config was tuned to the current project layout so the gate is meaningful instead of noisy
- existing warnings remain visible, but they do not drag the project below the fail threshold

### 4. Bandit security scan
Command:
```bash
./venv/bin/python -m bandit -r src -c .bandit.yaml -f txt
```

Result summary:
- low severity issues: `8`
- medium severity issues: `5`
- high severity issues: `0`

Key findings observed locally:
- low severity hardcoded demo credentials in `src/flask_app/app.py`
- medium severity bind to `0.0.0.0` in the Flask entrypoint
- medium severity pickle deserialization findings in ML-related modules

Interpretation:
- the Bandit step is configured to report findings without blocking the pipeline
- this is deliberate for Week 13 so CI/CD becomes operational first while preserving visibility into security debt
- these findings are appropriate input for Week 14 security hardening

### 5. Docker Compose validation
Command:
```bash
docker compose -f docker/docker-compose.yml config
```

Result:
- passed

Note:
- Compose still emits a non-blocking warning that the `version` key is obsolete in `docker/docker-compose.yml`

## Generated / Referenced Artifacts
- workflow file: `.github/workflows/ci.yml`
- dependabot config: `.github/dependabot.yml`
- lint config: `.pylintrc`
- security config: `.bandit.yaml`
- dev dependencies: `requirements-dev.txt`
- test reports referenced by CI:
  - `reports/pytest_unit.xml`
  - `reports/pytest_integration.xml`
  - `reports/coverage.xml`
  - `reports/coverage_html/index.html`
  - `reports/bandit_report.json` (generated in CI)
  - `reports/trivy-flask.sarif` (generated in CI)

## Tutorial Goals Status
- GitHub Actions pipeline created: achieved
- quality job with pylint and bandit: achieved
- test job with PostgreSQL-backed integration tests: achieved
- Docker build job for project images: achieved in workflow config
- Trivy scan integrated: achieved in workflow config
- Dependabot configuration created: achieved
- README badge added: achieved
- first live GitHub Actions run after push: pending
- Dependabot enablement in GitHub repository settings: pending

## Follow-up Notes
To fully close Week 13 after this local validation, the remaining external checks are:
1. push branch `CICDAutomation` to GitHub
2. confirm the workflow runs in the GitHub Actions tab
3. confirm the CI badge turns green on a successful run
4. enable Dependabot alerts / security updates / version updates in GitHub repository settings
5. inspect Trivy SARIF output in the GitHub Security tab