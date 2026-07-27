#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${1:-${SCRIPT_DIR}/.venv-rl}"
TORCH_VARIANT="${2:-${RL_TORCH_VARIANT:-auto}}"
CONTROLLER_ROOT="${SCRIPT_DIR}/SDWSN-controller"
REQUIREMENTS_FILE="${SCRIPT_DIR}/requirements-rl.txt"
BOOTSTRAP_PYTHON="${RL_PYTHON:-python3}"

if [ ! -f "$REQUIREMENTS_FILE" ]; then
  echo "Error: dependency file not found: ${REQUIREMENTS_FILE}" >&2
  exit 2
fi

PYTHON_VERSION="$("$BOOTSTRAP_PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [ "$PYTHON_VERSION" != "3.10" ]; then
  echo "Warning: Python ${PYTHON_VERSION} is untested; Python 3.10 is recommended." >&2
fi

echo "Creating RL virtual environment at: ${VENV_DIR}"
"$BOOTSTRAP_PYTHON" -m venv "${VENV_DIR}"

PYTHON_BIN="${VENV_DIR}/bin/python"
PIP_BIN="${VENV_DIR}/bin/pip"

"${PIP_BIN}" install --upgrade pip setuptools wheel

# Select a portable default while preserving the CUDA 12.8 environment used
# for the final experiment.
if [ "$TORCH_VARIANT" = "auto" ]; then
  if command -v nvidia-smi >/dev/null 2>&1; then
    TORCH_VARIANT="cu128"
  else
    TORCH_VARIANT="cpu"
  fi
fi

case "$TORCH_VARIANT" in
  cpu)
    TORCH_INDEX_URL="https://download.pytorch.org/whl/cpu"
    ;;
  cu128)
    TORCH_INDEX_URL="https://download.pytorch.org/whl/cu128"
    ;;
  *)
    echo "Error: torch variant must be one of: auto, cpu, cu128" >&2
    exit 2
    ;;
esac

echo "Installing PyTorch variant: ${TORCH_VARIANT}"
"${PIP_BIN}" install \
  --index-url "$TORCH_INDEX_URL" \
  torch==2.8.0

# TensorFlow is intentionally excluded: this workflow uses PyTorch, SB3, and
# TensorBoard. Direct dependencies are pinned to the final tested environment.
"${PIP_BIN}" install -r "${REQUIREMENTS_FILE}"

"${PIP_BIN}" install -e "${CONTROLLER_ROOT}"

echo
echo "RL environment is ready."
echo "Activate with:"
echo "  source ${VENV_DIR}/bin/activate"
