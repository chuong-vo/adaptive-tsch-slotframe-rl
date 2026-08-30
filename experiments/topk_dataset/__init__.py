"""Controlled dataset collection for slotframe Top-K experiments."""

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROLLER_ROOT = REPO_ROOT / "SDWSN-controller"
if str(CONTROLLER_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROLLER_ROOT))

PROTOCOL_VERSION = "g0-v1"
RUNNER_VERSION = "0.1.0"
