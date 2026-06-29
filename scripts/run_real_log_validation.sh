#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="docker/docker-compose.yml"
VALIDATION_URL="${REAL_LOG_VALIDATION_URL:-http://localhost:8088}"
LOG_DIR="${REAL_LOG_LOG_DIR:-logs/real}"
RAW_ACCESS_LOG="$LOG_DIR/validation_access.log"
BENIGN_LOG="$LOG_DIR/access_benign.log"
ATTACK_LOG="$LOG_DIR/access_attack.log"
RESULTS_MD="${REAL_LOG_RESULTS_PATH:-docs/REAL_LOGS_VALIDATION_RESULTS.md}"
PYTHON_BIN="${PYTHON_BIN:-./venv/bin/python}"
PGUSER="${POSTGRES_USER:-postgres}"
PGDB="${POSTGRES_DB:-logmonitor}"
ML_WAIT_ATTEMPTS="${REAL_LOG_ML_WAIT_ATTEMPTS:-6}"
ML_WAIT_SECONDS="${REAL_LOG_ML_WAIT_SECONDS:-5}"
INTERNAL_ACCESS_LOG="/tmp/validation_access.log"
INTERNAL_ERROR_LOG="/tmp/validation_error.log"
RUN_SEED="${REAL_LOG_RUN_SEED:-$(( ($(date +%s) + $$) % 200 + 10 ))}"
BENIGN_SOURCE_IP="${REAL_LOG_BENIGN_IP:-198.51.100.${RUN_SEED}}"
ATTACK_SOURCE_IP="${REAL_LOG_ATTACK_IP:-203.0.113.${RUN_SEED}}"

mkdir -p "$LOG_DIR" "$(dirname "$RESULTS_MD")"

psql_scalar() {
  docker compose -f "$COMPOSE_FILE" exec -T postgres \
    psql -U "$PGUSER" -d "$PGDB" -At -c "$1" | tr -d '[:space:]'
}

psql_query() {
  docker compose -f "$COMPOSE_FILE" exec -T postgres \
    psql -U "$PGUSER" -d "$PGDB" -P pager=off -c "$1"
}

wait_for_http() {
  local attempts=30
  for ((i=1; i<=attempts; i++)); do
    if curl -fsS "$VALIDATION_URL/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "Timed out waiting for $VALIDATION_URL/health" >&2
  return 1
}

request() {
  local method="$1"
  local path="$2"
  local user_agent="$3"
  local source_ip="$4"
  local body="${5:-}"
  local content_type="${6:-}"

  local args=(-sS -o /dev/null -A "$user_agent" -X "$method" -H "X-Forwarded-For: $source_ip")
  if [[ -n "$content_type" ]]; then
    args+=(-H "Content-Type: $content_type")
  fi
  if [[ -n "$body" ]]; then
    args+=(-d "$body")
  fi

  curl "${args[@]}" "$VALIDATION_URL$path" >/dev/null 2>&1 || true
}

fetch_access_log() {
  docker compose -f "$COMPOSE_FILE" exec -T nginx-validation sh -c "cat '$INTERNAL_ACCESS_LOG'" > "$RAW_ACCESS_LOG"
}

count_phase_hybrid_scores() {
  local lower_bound="$1"
  local upper_bound="$2"
  psql_scalar "SELECT COUNT(*) FROM hybrid_scores hs JOIN raw_logs rl ON rl.id = hs.log_id WHERE rl.id > $lower_bound AND rl.id <= $upper_bound AND rl.log_type = 'apache_access';"
}

wait_for_phase_hybrid_scores() {
  local lower_bound="$1"
  local upper_bound="$2"
  local count="0"
  for ((i=1; i<=ML_WAIT_ATTEMPTS; i++)); do
    count="$(count_phase_hybrid_scores "$lower_bound" "$upper_bound")"
    if [[ -n "$count" && "$count" != "0" ]]; then
      echo "$count"
      return 0
    fi
    sleep "$ML_WAIT_SECONDS"
  done
  echo "$count"
}

count_phase_access_rows() {
  local lower_bound="$1"
  local upper_bound="$2"
  psql_scalar "SELECT COUNT(*) FROM raw_logs WHERE id > $lower_bound AND id <= $upper_bound AND log_type = 'apache_access';"
}

count_phase_alerts() {
  local alert_lower="$1"
  local alert_upper="$2"
  local source_ip="$3"
  psql_scalar "SELECT COUNT(*) FROM alerts WHERE id > $alert_lower AND id <= $alert_upper AND ip = '$source_ip';"
}

summarize_range() {
  local lower_bound="$1"
  local upper_bound="$2"
  local alert_lower="$3"
  local alert_upper="$4"
  local source_ip="$5"
  local label="$6"

  local ingest_stats alert_stats hybrid_stats status_stats
  ingest_stats="$(psql_query "SELECT COUNT(*) AS total_logs, COUNT(*) FILTER (WHERE ip IS NULL) AS missing_ip, COUNT(*) FILTER (WHERE method IS NULL) AS missing_method, COUNT(*) FILTER (WHERE endpoint IS NULL) AS missing_endpoint, COUNT(*) FILTER (WHERE status IS NULL) AS missing_status, COUNT(*) FILTER (WHERE response_time_ms IS NULL) AS missing_response_time FROM raw_logs WHERE id > $lower_bound AND id <= $upper_bound AND log_type = 'apache_access';")"
  alert_stats="$(psql_query "SELECT alert_type, severity, COUNT(*) AS total FROM alerts WHERE id > $alert_lower AND id <= $alert_upper AND ip = '$source_ip' GROUP BY alert_type, severity ORDER BY total DESC, alert_type;")"
  hybrid_stats="$(psql_query "SELECT COUNT(*) AS scored_logs, COUNT(*) FILTER (WHERE hs.is_anomaly) AS ml_anomalies, ROUND(AVG(hs.final_score)::numeric, 4) AS avg_final_score FROM hybrid_scores hs JOIN raw_logs rl ON rl.id = hs.log_id WHERE rl.id > $lower_bound AND rl.id <= $upper_bound AND rl.log_type = 'apache_access';")"
  status_stats="$(psql_query "SELECT status, COUNT(*) AS total FROM raw_logs WHERE id > $lower_bound AND id <= $upper_bound AND log_type = 'apache_access' GROUP BY status ORDER BY total DESC, status;")"

  cat <<EOF
## $label

### Ingestao

~~~text
$ingest_stats
~~~

### Alertas associados ao intervalo

~~~text
$alert_stats
~~~

### Scoring hibrido

~~~text
$hybrid_stats
~~~

### Distribuicao de status codes

~~~text
$status_stats
~~~

EOF
}

echo "[1/8] Starting nginx validation service..."
docker compose -f "$COMPOSE_FILE" up -d --force-recreate nginx-validation >/dev/null
wait_for_http

echo "[2/8] Preparing validation log files..."
rm -f "$RAW_ACCESS_LOG" "$BENIGN_LOG" "$ATTACK_LOG"
docker compose -f "$COMPOSE_FILE" exec -T nginx-validation sh -c ": > '$INTERNAL_ACCESS_LOG' && : > '$INTERNAL_ERROR_LOG' && chmod 666 '$INTERNAL_ACCESS_LOG' '$INTERNAL_ERROR_LOG'" >/dev/null
: > "$BENIGN_LOG"
: > "$ATTACK_LOG"

validation_started_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
before_raw="$(psql_scalar "SELECT COALESCE(MAX(id), 0) FROM raw_logs;")"
before_alert="$(psql_scalar "SELECT COALESCE(MAX(id), 0) FROM alerts;")"

echo "[3/8] Generating benign traffic through nginx..."
BROWSER_UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
request GET "/" "$BROWSER_UA" "$BENIGN_SOURCE_IP"
request GET "/api/data?page=1&per_page=5" "$BROWSER_UA" "$BENIGN_SOURCE_IP"
request GET "/api/users" "$BROWSER_UA" "$BENIGN_SOURCE_IP"
request GET "/search?q=normal" "$BROWSER_UA" "$BENIGN_SOURCE_IP"
request GET "/api/data?page=1&per_page=5" "$BROWSER_UA" "$BENIGN_SOURCE_IP"
request GET "/" "$BROWSER_UA" "$BENIGN_SOURCE_IP"
request GET "/search?q=normal" "$BROWSER_UA" "$BENIGN_SOURCE_IP"
request GET "/api/users" "$BROWSER_UA" "$BENIGN_SOURCE_IP"
sleep 2
fetch_access_log

if [[ ! -s "$RAW_ACCESS_LOG" ]]; then
  echo "No nginx access logs were generated for the benign phase." >&2
  exit 1
fi

cp "$RAW_ACCESS_LOG" "$BENIGN_LOG"
benign_line_count="$(wc -l < "$RAW_ACCESS_LOG" | tr -d '[:space:]')"

echo "[4/8] Ingesting benign access log and running rules..."
"$PYTHON_BIN" src/log_processor/ingester.py "$BENIGN_LOG" --format apache_combined --batch-size 500 >/tmp/logmonitor_real_logs_benign_ingest.txt
"$PYTHON_BIN" src/detection/rule_engine.py --mode historical --days 1 >/tmp/logmonitor_real_logs_benign_rules.txt
sleep 3

after_benign_raw="$(psql_scalar "SELECT COALESCE(MAX(id), 0) FROM raw_logs;")"
after_benign_alert="$(psql_scalar "SELECT COALESCE(MAX(id), 0) FROM alerts;")"
benign_access_rows="$(count_phase_access_rows "$before_raw" "$after_benign_raw")"
benign_ml_count="$(wait_for_phase_hybrid_scores "$before_raw" "$after_benign_raw")"
benign_alerts_created="$(count_phase_alerts "$before_alert" "$after_benign_alert" "$BENIGN_SOURCE_IP")"

echo "[5/8] Generating controlled malicious traffic through nginx..."
ATTACK_UA="python-requests/2.31.0"
for _ in {1..6}; do
  request POST "/login" "$ATTACK_UA" "$ATTACK_SOURCE_IP" '{"username":"user1","password":"wrong-password"}' 'application/json'
done
for _ in {1..3}; do
  request GET "/search?q=%27%20OR%201%3D1%20--" "sqlmap/1.7" "$ATTACK_SOURCE_IP"
done
request GET "/../../etc/passwd" "sqlmap/1.7" "$ATTACK_SOURCE_IP"
request GET "/../../var/log/auth.log" "sqlmap/1.7" "$ATTACK_SOURCE_IP"
for i in $(seq 1 10); do
  request GET "/probe-$i" "masscan/1.3" "$ATTACK_SOURCE_IP"
done
sleep 2
fetch_access_log

tail -n +$((benign_line_count + 1)) "$RAW_ACCESS_LOG" > "$ATTACK_LOG"
if [[ ! -s "$ATTACK_LOG" ]]; then
  echo "No nginx access logs were generated for the attack phase." >&2
  exit 1
fi

echo "[6/8] Ingesting malicious access log and running rules..."
"$PYTHON_BIN" src/log_processor/ingester.py "$ATTACK_LOG" --format apache_combined --batch-size 500 >/tmp/logmonitor_real_logs_attack_ingest.txt
"$PYTHON_BIN" src/detection/rule_engine.py --mode historical --days 1 >/tmp/logmonitor_real_logs_attack_rules.txt
sleep 3

after_attack_raw="$(psql_scalar "SELECT COALESCE(MAX(id), 0) FROM raw_logs;")"
after_attack_alert="$(psql_scalar "SELECT COALESCE(MAX(id), 0) FROM alerts;")"
attack_access_rows="$(count_phase_access_rows "$after_benign_raw" "$after_attack_raw")"
attack_ml_count="$(wait_for_phase_hybrid_scores "$after_benign_raw" "$after_attack_raw")"
attack_alerts_created="$(count_phase_alerts "$after_benign_alert" "$after_attack_alert" "$ATTACK_SOURCE_IP")"

echo "[7/8] Collecting evaluation results..."
benign_log_lines="$(wc -l < "$BENIGN_LOG" | tr -d '[:space:]')"
attack_log_lines="$(wc -l < "$ATTACK_LOG" | tr -d '[:space:]')"

cat > "$RESULTS_MD" <<EOF
# Real Logs Validation Results

## Context

- Validation branch: \`week15-RealLogsValidation\`
- Validation started at: \`$validation_started_at\`
- Source type: \`Nginx access log (real server-generated log)\`
- Proxy URL used: \`$VALIDATION_URL\`
- Benign source IP used: \`$BENIGN_SOURCE_IP\`
- Attack source IP used: \`$ATTACK_SOURCE_IP\`
- Raw access log file: [validation_access.log](/home/raulb/projects/log-monitor-mlops/$RAW_ACCESS_LOG)
- Benign sample: [access_benign.log](/home/raulb/projects/log-monitor-mlops/$BENIGN_LOG)
- Malicious sample: [access_attack.log](/home/raulb/projects/log-monitor-mlops/$ATTACK_LOG)

## High-Level Summary

- Benign log lines captured: $benign_log_lines
- Benign \`apache_access\` rows ingested into \`raw_logs\`: $benign_access_rows
- Alerts created for benign phase source IP: $benign_alerts_created
- Hybrid scores observed for benign phase logs: ${benign_ml_count:-0}
- Attack log lines captured: $attack_log_lines
- Attack \`apache_access\` rows ingested into \`raw_logs\`: $attack_access_rows
- Alerts created for attack phase source IP: $attack_alerts_created
- Hybrid scores observed for attack phase logs: ${attack_ml_count:-0}

$(summarize_range "$before_raw" "$after_benign_raw" "$before_alert" "$after_benign_alert" "$BENIGN_SOURCE_IP" "Benign Baseline")
$(summarize_range "$after_benign_raw" "$after_attack_raw" "$after_benign_alert" "$after_attack_alert" "$ATTACK_SOURCE_IP" "Controlled Malicious Traffic")

## Notes

- The logs are **real Nginx access logs** generated by an actual Nginx proxy in front of the project Flask app.
- The validation uses explicit client IP headers so each run can be isolated from prior historical detections while still producing real Nginx-formatted access logs.
- The benign phase used browser-like traffic to reduce artificial false positives.
- The malicious phase used controlled requests to exercise brute-force, SQL injection, suspicious user-agent, path traversal and scanning patterns.
- This validates operational ingestion separately from external benchmark datasets such as CICIDS-2017.
EOF

echo "[8/8] Validation finished. Results written to $RESULTS_MD"
echo "Benign lines: $benign_log_lines | Attack lines: $attack_log_lines"
echo "Benign apache_access rows: $benign_access_rows | Attack apache_access rows: $attack_access_rows"
echo "Benign alerts for phase source IP: $benign_alerts_created | Attack alerts for phase source IP: $attack_alerts_created"
echo "Hybrid scores observed: benign=${benign_ml_count:-0}, attack=${attack_ml_count:-0}"