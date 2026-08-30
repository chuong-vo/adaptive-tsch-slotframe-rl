#!/usr/bin/env bash

set -u

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PYTHON_BIN=${PYTHON_BIN:-python3}
OUTPUT=${TOPK_EXPANDED_OUTPUT:-$REPO/runs/topk_dataset/expanded}
CONFIG=${TOPK_EXPANDED_CONFIG:-$REPO/experiments/topk_dataset/config/expanded.json}
LOG=${TOPK_EXPANDED_LOG:-$REPO/runs/topk_dataset/expanded_full.log}
PID_FILE=${TOPK_EXPANDED_PID_FILE:-$REPO/runs/topk_dataset/expanded_full.pid}
LOCK_FILE=${TOPK_EXPANDED_LOCK_FILE:-$REPO/runs/topk_dataset/expanded_full.lock}
MAX_RESTARTS=${TOPK_EXPANDED_MAX_RESTARTS:-5}
PORT=${TOPK_EXPANDED_PORT:-60001}

mkdir -p "$(dirname "$LOG")" "$OUTPUT"
cd "$REPO" || exit 1

export PYTHONUNBUFFERED=1
export PYTHONPATH="$REPO:$REPO/SDWSN-controller${PYTHONPATH:+:$PYTHONPATH}"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    printf '%s | SUPERVISOR | Another expanded collector owns %s\n' \
        "$(date --iso-8601=seconds)" "$LOCK_FILE" >> "$LOG"
    exit 1
fi

printf '%s\n' "$$" > "$PID_FILE"
collector_pid=""
cleanup() {
    rm -f "$PID_FILE"
}
terminate() {
    trap - INT TERM
    if [[ -n "$collector_pid" ]] && kill -0 "$collector_pid" 2>/dev/null; then
        kill -TERM "$collector_pid" 2>/dev/null || true
        wait "$collector_pid" 2>/dev/null || true
    fi
    exit 130
}
trap cleanup EXIT
trap terminate INT TERM

port_is_free() {
    "$PYTHON_BIN" - "$PORT" <<'PY'
import socket
import sys

probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    probe.bind(("127.0.0.1", int(sys.argv[1])))
except OSError:
    raise SystemExit(1)
finally:
    probe.close()
PY
}

restart_count=0
while (( restart_count <= MAX_RESTARTS )); do
    printf '%s | SUPERVISOR | Starting/resuming expanded collection (restart=%d)\n' \
        "$(date --iso-8601=seconds)" "$restart_count" >> "$LOG"

    "$PYTHON_BIN" -m experiments.topk_dataset.collect_expanded \
        --config "$CONFIG" \
        --output "$OUTPUT" >> "$LOG" 2>&1 &
    collector_pid=$!
    wait "$collector_pid"
    status=$?
    collector_pid=""
    if (( status == 0 )); then
        printf '%s | SUPERVISOR | Expanded collection completed successfully\n' \
            "$(date --iso-8601=seconds)" >> "$LOG"
        exit 0
    fi

    restart_count=$((restart_count + 1))
    if (( restart_count > MAX_RESTARTS )); then
        break
    fi
    printf '%s | SUPERVISOR | Collector exited with status %d; retry %d/%d\n' \
        "$(date --iso-8601=seconds)" "$status" "$restart_count" \
        "$MAX_RESTARTS" >> "$LOG"
    until port_is_free; do
        sleep 2
    done
    sleep 5
done

printf '%s | SUPERVISOR | Restart limit exceeded\n' \
    "$(date --iso-8601=seconds)" >> "$LOG"
exit 1
