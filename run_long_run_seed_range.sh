#!/bin/bash
# Chạy long_run tuần tự cho dải seed.
#
# Usage:
#   ./run_long_run_seed_range.sh                  # mặc định từ 43 tới 50
#   ./run_long_run_seed_range.sh 10 20            # hoặc chỉ định START END
#   ./run_long_run_seed_range.sh 10 20 MODEL.zip  # chỉ định model mới
#
# Script này chỉ là wrapper, gọi lại ./run_long_run_with_seed.sh

set -euo pipefail

START_SEED=${1:-43}
END_SEED=${2:-50}
MODEL_PATH=${3:-${ELISE_TRAINED_MODEL:-}}

if ! command -v seq >/dev/null 2>&1; then
  echo "Error: lệnh 'seq' không có sẵn trên hệ thống." >&2
  exit 1
fi

if [ "$START_SEED" -gt "$END_SEED" ]; then
  echo "Error: START_SEED ($START_SEED) > END_SEED ($END_SEED)" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for SEED in $(seq "$START_SEED" "$END_SEED"); do
  echo "=========================================="
  echo ">>> Running long_run_with_seed.sh for seed ${SEED}"
  echo "=========================================="
  if [ -n "$MODEL_PATH" ]; then
    "${SCRIPT_DIR}/run_long_run_with_seed.sh" "$SEED" "$MODEL_PATH"
  else
    "${SCRIPT_DIR}/run_long_run_with_seed.sh" "$SEED"
  fi
done

echo "=========================================="
echo "All runs completed for seeds ${START_SEED}..${END_SEED}"
echo "=========================================="
