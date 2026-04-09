#!/bin/bash
set -e

HOST_PORT="$1"
shift

HOST="${HOST_PORT%:*}"
PORT="${HOST_PORT#*:}"
TIMEOUT="${WAIT_FOR_IT_TIMEOUT:-30}"

for ((i=1; i<=TIMEOUT; i++)); do
    if (echo > "/dev/tcp/${HOST}/${PORT}") >/dev/null 2>&1; then
        exec "$@"
    fi
    sleep 1
done

echo "Timeout waiting for ${HOST}:${PORT}"
exit 1
