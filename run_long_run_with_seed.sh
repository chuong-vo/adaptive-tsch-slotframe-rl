#!/bin/bash
set -euo pipefail
# Script để chạy long_run với seed khác nhau

# Usage: ./run_long_run_with_seed.sh [SEED] [MODEL_PATH]
# Example: ./run_long_run_with_seed.sh 999999 /path/to/best_model.zip

SEED=${1:-123456}  # Default = 123456, hoặc lấy từ argument $1
MODEL_PATH=${2:-${ELISE_TRAINED_MODEL:-}}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONTROLLER_ROOT="${SCRIPT_DIR}/SDWSN-controller"
DEFAULT_VENV_DIR="${SCRIPT_DIR}/.venv-rl"

CONTIKI_NG="${CONTIKI_NG:-${SCRIPT_DIR}/contiki-ng}"
PROFILE_ORDER="${ELISE_PROFILE_ORDER:-balanced,delay,energy,pdr}"
INITIAL_PROFILE="${ELISE_INITIAL_PROFILE:-balanced}"
PROFILE_SWITCH_MODE="${ELISE_PROFILE_SWITCH_MODE:-roundrobin}"
PROFILE_SWITCH_EVERY="${ELISE_PROFILE_SWITCH_EVERY:-300}"
MAX_CYCLES="${ELISE_MAX_CYCLES:-1200}"
MAX_WAIT_RETRIES="${ELISE_MAX_WAIT_RETRIES:-3}"
RESET_GRAPH_RETRIES="${ELISE_RESET_GRAPH_RETRIES:-5}"
RESET_GRAPH_RETRY_SLEEP="${ELISE_RESET_GRAPH_RETRY_SLEEP:-1.0}"
MIN_SLOTFRAME_SIZE="${ELISE_MIN_SLOTFRAME_SIZE:-10}"
MAX_SLOTFRAME_SIZE="${ELISE_MAX_SLOTFRAME_SIZE:-68}"
INITIAL_SF_MODE="${ELISE_INITIAL_SF_MODE:-fixed}"
INITIAL_SF="${ELISE_INITIAL_SF:-10}"

PYTHON_BIN="${ELISE_PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
  if [ -x "${DEFAULT_VENV_DIR}/bin/python" ]; then
    PYTHON_BIN="${DEFAULT_VENV_DIR}/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

PYTHONPATH_VALUE="${CONTROLLER_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

COOJA_FILE="${CONTIKI_NG}/examples/elise/cooja-elise.csc"
BACKUP_FILE="${COOJA_FILE}.bak"
OUTPUT_BASE="${ELISE_OUTPUT_BASE:-SDWSN-controller/tutorials/reinforcement-learning/long-run/output}"
LOG_BASE="${ELISE_LOG_BASE:-SDWSN-controller/tutorials/reinforcement-learning/long-run/logs}"
OUTPUT_DIR="${ELISE_OUTPUT_DIR:-${OUTPUT_BASE}/seed_${SEED}}"
LOG_DIR="${ELISE_LOG_DIR:-${LOG_BASE}/seed_${SEED}}"

echo "=========================================="
echo "Running long_run with seed: $SEED"
echo "=========================================="

# Backup file gốc
cp "$COOJA_FILE" "$BACKUP_FILE"
restore_cooja_file() {
  if [ -f "$BACKUP_FILE" ]; then
    cp "$BACKUP_FILE" "$COOJA_FILE"
    rm -f "$BACKUP_FILE"
  fi
}
trap restore_cooja_file EXIT

# Set seed trong cooja-elise.csc
sed -i "s/<randomseed>[0-9]*<\/randomseed>/<randomseed>${SEED}<\/randomseed>/" \
    "$COOJA_FILE"

# Tạo output directory
mkdir -p "$OUTPUT_DIR"
mkdir -p "$LOG_DIR"

# Chạy long_run
if [ -n "$MODEL_PATH" ]; then
  export ELISE_TRAINED_MODEL="$MODEL_PATH"
fi

CONTIKI_NG="$CONTIKI_NG" \
PYTHONPATH="$PYTHONPATH_VALUE" \
ELISE_COOJA_SEED="$SEED" \
ELISE_INITIAL_PROFILE="$INITIAL_PROFILE" \
ELISE_PROFILE_SWITCH_MODE="$PROFILE_SWITCH_MODE" \
ELISE_PROFILE_SWITCH_EVERY="$PROFILE_SWITCH_EVERY" \
ELISE_PROFILE_ORDER="$PROFILE_ORDER" \
ELISE_MAX_CYCLES="$MAX_CYCLES" \
ELISE_MAX_WAIT_RETRIES="$MAX_WAIT_RETRIES" \
ELISE_RESET_GRAPH_RETRIES="$RESET_GRAPH_RETRIES" \
ELISE_RESET_GRAPH_RETRY_SLEEP="$RESET_GRAPH_RETRY_SLEEP" \
ELISE_MIN_SLOTFRAME_SIZE="$MIN_SLOTFRAME_SIZE" \
ELISE_MAX_SLOTFRAME_SIZE="$MAX_SLOTFRAME_SIZE" \
ELISE_INITIAL_SF_MODE="$INITIAL_SF_MODE" \
ELISE_INITIAL_SF="$INITIAL_SF" \
ELISE_RESET_RETRIES="${ELISE_RESET_RETRIES:-3}" \
ELISE_MAX_STEP_EXCEPTIONS="${ELISE_MAX_STEP_EXCEPTIONS:-3}" \
ELISE_RESET_BACKOFF_SECONDS="${ELISE_RESET_BACKOFF_SECONDS:-5}" \
ELISE_FLUSH_EVERY="${ELISE_FLUSH_EVERY:-1}" \
ELISE_RESET_EVERY="${ELISE_RESET_EVERY:-0}" \
ELISE_OUTPUT_DIR="$OUTPUT_DIR/" \
ELISE_LOG_DIR="$LOG_DIR/" \
"$PYTHON_BIN" "${CONTROLLER_ROOT}/tutorials/reinforcement-learning/long-run/long_run.py"

echo "=========================================="
echo "Completed! Output: $OUTPUT_DIR"
echo "=========================================="
