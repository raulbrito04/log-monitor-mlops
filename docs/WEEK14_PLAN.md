# Week 14 Plan — Security Hardening

## Summary
Week 14 should convert the visibility gained in Week 13 into concrete hardening of the running stack. The project already has Docker orchestration, monitoring, a Streamlit dashboard, automated tests, and a CI/CD pipeline with Pylint, Bandit, Trivy, and Dependabot. The next step is not “add more tooling”, but reduce real attack surface in the application, containers, and configuration.

This week should focus on high-ROI hardening of the existing system:
- remove or isolate insecure defaults
- reduce abuse potential on exposed routes
- make request handling stricter
- improve container runtime posture
- turn current security findings into tracked remediation

This is a hardening week, not a feature week.

## Current State Driving Week 14
Based on the project state at the end of Week 13:
- CI/CD is configured locally in `.github/workflows/ci.yml`
- Bandit already reports meaningful findings in the codebase
- Trivy is integrated in the planned GitHub workflow
- the Flask app still includes demo credentials and a development-style secret fallback
- the Flask service exposes login, admin, upload, search, and API routes that should now be treated as attack surface
- the codebase uses pickle-backed ML artifacts, which is acceptable only under controlled trust boundaries and needs explicit safeguards
- Dockerfiles currently run as root and do not yet reflect a hardened runtime posture
- the project is already strong enough to benefit from targeted security work without destabilizing its architecture

## Week 14 Goal
Deliver a secure-by-default baseline for the current stack without changing the overall product architecture.

Success means:
- the app is harder to abuse from unauthenticated traffic
- container runtime risk is reduced
- insecure defaults are removed or clearly confined to development mode
- the most important Bandit/Trivy findings are either mitigated or explicitly documented with rationale
- new tests prove the hardening behavior

## Scope Choice
Recommended scope: High-ROI implementation with clear security value and low architecture churn.

Include this week:
- authentication and secret hardening
- security headers
- rate limiting on sensitive routes
- request/input validation and upload constraints
- SQL/query audit and trust-boundary documentation
- container hardening for runtime users and image hygiene
- security-focused tests and documentation

Defer to later unless already trivial:
- full RBAC redesign
- OAuth or external identity provider integration
- WAF integration
- mTLS or service mesh
- secret manager integration (Vault, AWS Secrets Manager, etc.)
- replacing pickle-based ML artifacts with a new serialization format across the whole ML stack

## Workstreams

### 1. Application Secrets and Authentication Hardening
#### Objective
Stop shipping weak or ambiguous security defaults in the Flask application.

#### Why this matters
Week 13 Bandit output already points at hardcoded/demo credentials and development-style secret handling. These are acceptable for local simulation, but not acceptable as the default behavior of the app once CI/CD and monitoring are in place.

#### Planned changes
- move demo users behind an explicit development-only guard, or externalize them into environment-driven test fixtures
- require `FLASK_SECRET_KEY` in non-development environments
- fail fast when secure configuration is missing instead of silently falling back to insecure defaults
- separate “simulated attack surface” behavior from “operator/runtime configuration” more clearly
- review token generation and admin-route authorization flow for predictable weaknesses
- ensure password-like values are never logged, echoed, or surfaced in error payloads

#### Acceptance criteria
- no insecure production fallback for Flask secret key
- demo credentials are not the default runtime auth mechanism outside development/test
- auth-related configuration is explicit in docs and environment examples
- security scanning no longer reports trivial hardcoded credential debt in the main runtime path

### 2. HTTP Security Headers
#### Objective
Harden browser-facing responses from the Flask service with standard protective headers.

#### Planned changes
- add `X-Content-Type-Options: nosniff`
- add `X-Frame-Options: DENY` or `SAMEORIGIN` based on dashboard embedding needs
- add `Referrer-Policy: no-referrer` or a similarly restrictive policy
- add a baseline `Content-Security-Policy` suitable for this app’s actual frontend behavior
- add `Cache-Control: no-store` on authentication-sensitive responses where appropriate
- evaluate HSTS policy design, but only enable strict HSTS automatically if the deployment assumption is HTTPS termination in front of the app

#### Acceptance criteria
- headers applied centrally through middleware or a shared response hook
- tests verify headers on representative endpoints
- policy choices documented with rationale, especially CSP and HSTS

### 3. Rate Limiting and Abuse Controls
#### Objective
Reduce brute-force and burst abuse risk on sensitive routes.

#### Planned routes to protect first
- `/login`
- `/admin`
- `/search`
- `/api/upload`
- any expensive or state-sensitive API endpoints

#### Planned changes
- add lightweight route-aware rate limiting keyed by IP and possibly route pattern
- use stricter limits on `/login` and `/admin`
- return consistent `429 Too Many Requests` responses with a clear JSON error contract
- expose rate-limit events in logs and optionally Prometheus counters
- keep limits configurable via environment variables

#### Acceptance criteria
- repeated login attempts trigger rate limiting
- search/upload/admin paths have sensible default thresholds
- automated tests cover at least one blocked path and one allowed recovery path
- limits are documented in a security section or environment reference

### 4. Input Validation and Upload Hardening
#### Objective
Make request parsing stricter so malformed or malicious payloads fail safely.

#### Planned changes
- validate login payload shape and types explicitly
- validate query parameters for search/pagination endpoints with bounded ranges
- constrain upload content type, size, and accepted formats
- sanitize or reject suspicious free-text inputs where reflection/logging risk exists
- normalize error responses so validation failures return predictable JSON instead of broad exceptions
- ensure request-body logging remains redacted and bounded in size

#### Acceptance criteria
- invalid payloads fail with clear `400` responses and no stack trace leakage
- upload route enforces size/type constraints
- tests cover malformed JSON, oversize payloads, and boundary conditions

### 5. SQL Injection Review and Query Safety Audit
#### Objective
Confirm that real database interactions are parameterized and document intentional exceptions.

#### Why this matters
The rule engine intentionally contains SQL text because it is a detection engine that builds static rule queries, but other runtime data paths should still be audited carefully.

#### Planned changes
- review all direct `cursor.execute(...)` usage in Flask, ingestion, monitoring, and dashboard helpers
- confirm runtime user inputs are never interpolated into SQL statements
- document why rule-engine static SQL templates are not the same as runtime string interpolation from user input
- annotate false positives or add narrowly scoped comments only where needed
- identify any places where query parameters should be normalized before reaching DB code

#### Acceptance criteria
- no user-controlled SQL string interpolation remains in runtime paths
- known Bandit false positives are documented, not just ignored silently
- a small audit note exists in docs for future maintainers

### 6. ML Artifact Trust Boundary Hardening
#### Objective
Address the security implications of pickle-based model loading without destabilizing the ML system.

#### Why this matters
Bandit correctly flags pickle usage. Replacing the full artifact stack this week would create too much churn, but doing nothing would be irresponsible.

#### Planned changes
- explicitly define model artifact trust boundary: only load locally built, versioned, repository-controlled or registry-controlled artifacts
- validate expected artifact paths and filenames before loading
- prevent arbitrary user-provided file paths from driving deserialization
- document why pickle remains temporarily acceptable in this controlled ML pipeline
- if low-effort, add file existence and extension validation where artifacts are loaded

#### Acceptance criteria
- pickle loading is not reachable from arbitrary external input
- model loading assumptions are documented in code or docs
- Week 14 closes the ambiguity even if full serialization replacement is deferred

### 7. Container Runtime Hardening
#### Objective
Reduce container-level blast radius and improve base image hygiene.

#### Planned changes
- run application containers as non-root where feasible:
  - flask-app
  - dashboard
  - rule-engine
  - ingester
  - ml-pipeline if compatible with model/data paths
- set explicit working directories and ownership for copied files
- minimize writable paths to what is actually needed
- review apt/package usage in Dockerfiles and reduce unnecessary packages
- consider adding `PYTHONDONTWRITEBYTECODE=1` and similar runtime hardening defaults where useful
- review healthchecks so they still work under non-root execution
- assess whether volumes/log paths need permission adjustments

#### Acceptance criteria
- non-root runtime enabled for the main app containers, or documented exceptions where not yet possible
- images still build successfully after hardening
- healthchecks and service startup still work
- Trivy output should trend better over time, even if not all CVEs are fixed this week

### 8. Security Logging and Monitoring Alignment
#### Objective
Make hardening visible operationally rather than purely code-level.

#### Planned changes
- log rate-limit events and blocked auth attempts clearly
- add or extend Prometheus counters for security-relevant events if low-friction
- ensure sensitive data stays redacted in logs
- optionally add one or two Grafana/Alertmanager hooks for repeated blocked auth attempts or suspicious error spikes

#### Acceptance criteria
- at least one new observable signal exists for a hardening control
- security-related events can be inspected without exposing secrets

### 9. Testing and QA for Security Controls
#### Objective
Back the hardening with automated tests so it does not regress.

#### Planned tests
- unit tests for security header middleware
- unit/integration tests for rate limiting behavior
- tests for invalid login/search/upload payloads
- tests ensuring redaction remains in logs/responses where applicable
- container/compose smoke tests if Dockerfiles change materially
- local rerun of Bandit and CI-equivalent pytest suite after hardening

#### Acceptance criteria
- security behavior is covered by tests, not only manual checks
- no drop below the Week 13 quality threshold
- hardening changes are safe for CI/CD adoption

## Implementation Order
Recommended execution order for Week 14:
1. secret/auth hardening
2. security headers
3. rate limiting
4. input validation and upload constraints
5. SQL audit and ML trust-boundary safeguards
6. container hardening
7. security observability additions
8. security-focused test pass
9. documentation and residual risk notes

This order reduces the chance of rework because the app-level behavior stabilizes before container and observability updates.

## Deliverables
By the end of Week 14, the branch should ideally contain:
- hardened Flask runtime behavior
- updated Dockerfiles with safer runtime posture
- updated environment/config docs
- new or updated tests for security behavior
- a Week 14 security results document summarizing findings fixed vs deferred
- optional security-focused notes in README or a dedicated security markdown file

## Public Interfaces and Configuration to Add or Review
Likely environment/config knobs for this week:
- `FLASK_SECRET_KEY`
- `LOGMONITOR_ENV`
- rate limit settings per sensitive route
- upload max size / allowed content types
- optional CSP/HSTS/header toggles where deployment assumptions vary

Review existing defaults in:
- `.env.example`
- `docker/.env`
- Docker Compose environment blocks
- Flask app configuration bootstrap

## Test Plan
### Local validation
- rerun Week 13 pytest suite
- run integration tests with security controls enabled
- rerun `pylint`
- rerun `bandit`
- validate Docker Compose after Dockerfile/container changes
- smoke test critical routes manually with `curl`

### Security scenarios to validate
- repeated bad login attempts trigger `429`
- `/admin` remains protected and unauthorized requests are rejected consistently
- invalid JSON and malformed inputs return `400` safely
- security headers appear on representative responses
- uploads outside allowed policy are rejected
- logs keep sensitive values redacted
- model loading does not accept arbitrary user-controlled paths

### CI/CD validation
- existing Week 13 CI workflow still passes after hardening
- Bandit findings decrease or become better documented
- Trivy results are reviewed after Dockerfile changes

## Risks and Constraints
- over-hardening development flows can break the simulated attack surface if not separated cleanly from production-mode behavior
- HSTS must not be enabled blindly if local HTTP development is still the default path
- non-root containers can break file permissions for logs, models, and mounted volumes
- rate limiting must avoid blocking normal test/generator flows unintentionally
- aggressive CSP can break UI/dashboard behavior if not tuned to actual assets
- replacing pickle end-to-end in one week is likely too disruptive; trust-boundary mitigation is the responsible near-term step

## Out of Scope
Not for Week 14 unless unexpectedly trivial:
- full authentication redesign
- SSO/OAuth
- centralized secret manager integration
- full model artifact format migration away from pickle across the ML lifecycle
- end-user RBAC redesign
- infrastructure-level WAF/CDN controls

## Completion Checklist
- [ ] insecure runtime defaults removed or isolated to development mode
- [ ] Flask secret handling hardened
- [ ] security headers added and tested
- [ ] rate limiting on sensitive routes implemented and tested
- [ ] upload and input validation hardened
- [ ] database query safety reviewed and documented
- [ ] ML artifact trust boundary documented and guarded
- [ ] main containers run as non-root where feasible
- [ ] security-relevant events observable in logs/metrics
- [ ] Week 13 CI pipeline still passes after hardening
- [ ] Week 14 results documented with fixed vs deferred findings

## Recommended Closing Artifact
At the end of Week 14, create a result report such as `docs/WEEK14_SECURITY_RESULTS.md` containing:
- what findings were fixed
- what findings remain and why
- test evidence
- residual risks accepted for Week 15+

## Week 15 Preview
If Week 14 lands well, Week 15 should focus on final documentation and project packaging, using the hardened baseline and CI pipeline as the stable base for presentation and handoff.