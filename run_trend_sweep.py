#!/usr/bin/env python3
"""
Helper script to collect approximation/trend data for multiple Cooja seeds.

It iterates over a list of seeds, updates the `randomseed` entry in the
`contiki-ng/examples/elise/cooja-elise.csc` file, and invokes
`approximation_model_cooja.py` with the environment settings that mirror the
manual command shared earlier. Each run stores its CSV/plots under a seed-
specific output directory so the results remain separated.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List


WORKSPACE = Path(__file__).resolve().parent
RL_DIR = WORKSPACE / "SDWSN-controller" / "tutorials" / "reinforcement-learning"
COOJA_CSC = WORKSPACE / "contiki-ng" / "examples" / "elise" / "cooja-elise.csc"

# Regular expression to capture the `<randomseed>...</randomseed>` block.
_RANDOMSEED_PATTERN = re.compile(
    r"(<randomseed>\s*)(-?\d+)(\s*</randomseed>)", re.IGNORECASE
)


def _derive_seeds(args) -> List[int]:
    """Return the list of seeds we want to sweep."""
    if args.seeds:
        return args.seeds
    return [args.start + i * args.step for i in range(args.count)]


def _update_cooja_seed(original_text: str, seed: int) -> str:
    """Inject a new random seed into the Cooja CSC file."""
    if not _RANDOMSEED_PATTERN.search(original_text):
        raise RuntimeError(
            f"Could not find <randomseed>...</randomseed> in {COOJA_CSC}"
        )
    return _RANDOMSEED_PATTERN.sub(
        lambda m: f"{m.group(1)}{seed}{m.group(3)}", original_text, count=1
    )


def _run_command(seed: int, cmd_env: dict, output_dir: Path, log_dir: Path) -> None:
    """Invoke approximation_model_cooja.py for a given seed."""
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update(cmd_env)
    env["ELISE_OUTPUT_DIR"] = str(output_dir)
    env["ELISE_LOG_DIR"] = str(log_dir)
    env["ELISE_COOJA_SEED"] = str(seed)
    env["ELISE_TREND_RANDOM_SEED"] = str(seed)

    print(f"[seed={seed}] Starting approximation_model_cooja.py")
    subprocess.run(
        ["python", "approximation_model_cooja.py"],
        cwd=RL_DIR,
        env=env,
        check=True,
    )
    print(f"[seed={seed}] Finished")


def _seed_is_complete(output_dir: Path) -> bool:
    required = ("example.csv", "coverage_summary.json", "trend_vectors.json")
    return all((output_dir / name).is_file() for name in required)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run approximation_model_cooja.py for multiple Cooja seeds."
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        help="Explicit list of Cooja random seeds to use.",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=1,
        help="First seed value (used when --seeds is not provided).",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=20,
        help="Number of seeds to run (used when --seeds is not provided).",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=1,
        help="Seed increment between consecutive runs (when --seeds absent).",
    )
    parser.add_argument(
        "--contiki-ng",
        type=str,
        default=str(WORKSPACE / "contiki-ng"),
        help="Path to the Contiki-NG tree (default: %(default)s).",
    )
    parser.add_argument(
        "--output-base",
        type=str,
        default=str(RL_DIR / "output"),
        help="Base directory where per-seed trend outputs are written.",
    )
    parser.add_argument(
        "--log-base",
        type=str,
        default=str(RL_DIR / "tensorlog"),
        help="Base directory where per-seed trend logs are written.",
    )
    parser.add_argument(
        "--cycle-profiles",
        action="store_true",
        help="Rotate balanced/delay/energy/reliability profiles during collection. "
        "By default trend collection keeps balanced fixed.",
    )
    parser.add_argument(
        "--requirements-refresh-every",
        type=int,
        default=300,
        help="Profile refresh interval when --cycle-profiles is enabled.",
    )
    parser.add_argument(
        "--explore-prob",
        type=float,
        default=0.35,
        help="Probability of random slotframe exploration at each cycle.",
    )
    parser.add_argument(
        "--hold-prob",
        type=float,
        default=0.15,
        help="Probability of including hold action during exploration.",
    )
    parser.add_argument(
        "--max-wait-retries",
        type=int,
        default=3,
        help="Maximum retries after a processing-window stall.",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=0,
        help="Stop each seed after this many cycles; 0 uses the configured episode limit.",
    )
    parser.add_argument(
        "--min-valid-rows",
        type=int,
        default=1000,
        help="Minimum valid rows required by per-seed trend analysis.",
    )
    parser.add_argument(
        "--min-slotframes",
        type=int,
        default=30,
        help="Minimum distinct slotframes required by per-seed trend analysis.",
    )
    parser.add_argument(
        "--rerun-completed",
        action="store_true",
        help="Rerun seeds even when example.csv, coverage_summary.json, and trend_vectors.json already exist.",
    )
    args = parser.parse_args(argv)

    seeds = _derive_seeds(args)
    if not seeds:
        print("No seeds specified, nothing to do.", file=sys.stderr)
        return 1

    output_base = Path(args.output_base).resolve()
    log_base = Path(args.log_base).resolve()
    original_csc = COOJA_CSC.read_text()
    cmd_env = {
        "CONTIKI_NG": args.contiki_ng,
        "ELISE_RANDOMIZE_REQUIREMENTS": "1" if args.cycle_profiles else "0",
        "ELISE_REQUIREMENTS_MODE": "profiles",
        "ELISE_REQUIREMENTS_CYCLE": "1" if args.cycle_profiles else "0",
        "ELISE_REQUIREMENTS_REFRESH_EVERY": str(args.requirements_refresh_every),
        "ELISE_SLOTFRAME_EXPLORE_PROB": str(args.explore_prob),
        "ELISE_SLOTFRAME_HOLD_PROB": str(args.hold_prob),
        "ELISE_MAX_WAIT_RETRIES": str(args.max_wait_retries),
        "ELISE_TREND_MAX_CYCLES": str(max(0, args.max_cycles)),
        "ELISE_MIN_TREND_VALID_ROWS": str(max(0, args.min_valid_rows)),
        "ELISE_MIN_TREND_SLOTFRAMES": str(max(0, args.min_slotframes)),
    }

    try:
        for seed in seeds:
            csc_text = _update_cooja_seed(original_csc, seed)
            COOJA_CSC.write_text(csc_text)

            run_name = f"cycle_r500_s{seed}"
            output_dir = output_base / run_name
            log_dir = log_base / run_name
            if _seed_is_complete(output_dir) and not args.rerun_completed:
                print(f"[seed={seed}] Skipping completed output at {output_dir}")
                continue
            _run_command(seed, cmd_env, output_dir, log_dir)
    finally:
        # Restore the CSC file to its original content.
        COOJA_CSC.write_text(original_csc)

    print("All seeds completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
