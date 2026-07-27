#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${1:-${SCRIPT_DIR}/.venv-rl}"
CONTROLLER_ROOT="${SCRIPT_DIR}/SDWSN-controller"

echo "Creating RL virtual environment at: ${VENV_DIR}"
python3 -m venv "${VENV_DIR}"

PYTHON_BIN="${VENV_DIR}/bin/python"
PIP_BIN="${VENV_DIR}/bin/pip"

"${PIP_BIN}" install --upgrade pip setuptools wheel

# GPU-enabled PyTorch for the local RTX 5070 Ti / CUDA 12.8 stack.
"${PIP_BIN}" install \
  --index-url https://download.pytorch.org/whl/cu128 \
  torch==2.8.0

# Project runtime dependencies. TensorFlow is intentionally excluded: the RL
# workflow here uses PyTorch/SB3/TensorBoard only.
"${PIP_BIN}" install \
  stable-baselines3[extra]==2.0.0a5 \
  docker \
  networkx \
  pandas \
  pyserial \
  paho-mqtt \
  pyfiglet \
  python-daemon \
  rich \
  tomli

"${PIP_BIN}" install -e "${CONTROLLER_ROOT}"

echo
echo "RL environment is ready."
echo "Activate with:"
echo "  source ${VENV_DIR}/bin/activate"
