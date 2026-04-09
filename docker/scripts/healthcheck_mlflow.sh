#!/bin/sh
set -e

python - <<'PY'
import sys
import urllib.request

try:
    with urllib.request.urlopen('http://127.0.0.1:5000/', timeout=5) as response:
        sys.exit(0 if 200 <= response.status < 400 else 1)
except Exception:
    sys.exit(1)
PY

echo 'MLflow OK'
exit 0
