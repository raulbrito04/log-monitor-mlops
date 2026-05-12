# Week 11 Plan — Streamlit Dashboard & UX (ROI MVP)

## Summary

Build a new Streamlit dashboard layer on top of the existing Week 9/10 stack in `codex/semana10-clean`. The project already has Docker orchestration, Prometheus, Grafana, Alertmanager, PostgreSQL, Flask routes, rule alerts, and ML monitoring, but it has no dashboard/UI code yet. Week 11 therefore focuses on a new read-only operator dashboard centered on visibility and investigation.

## Scope

- Add a Streamlit dashboard service on `localhost:8501`
- Use a multipage layout with `Home.py` and `pages/`
- Implement a read-only data layer for PostgreSQL and Prometheus
- Add basic session-based login with env credentials
- Deliver 4 MVP pages:
  - Overview
  - Alerts
  - Log Explorer
  - Model Monitoring

## Defaults

- Base branch: `codex/semana10-clean`
- Scope: ROI MVP only
- Dashboard remains read-only
- Existing Week 10 monitoring stack is reused as-is
- Rule tuning is deferred; Week 11 only exposes rule context and playbooks

## Validation Targets

- Dashboard container starts via Docker Compose
- Streamlit pages import and render without errors
- Login gate works before page access
- Overview and Alerts auto-refresh with a 30-second default interval
- Log Explorer stays manual-refresh
- Dashboard metrics match PostgreSQL and Prometheus sources
