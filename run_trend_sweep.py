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
import fcntl
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List

from sdwsn_controller.reinforcement_learning.graph_dataset import (
    graph_dataset_completion_issue,
)


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


def _seed_completion_issue(
    output_dir: Path,
    min_valid_rows: int,
    min_slotframes: int,
    required_profile: str,
    require_graph_dataset: bool = False,
) -> str | None:
    required = ("example.csv", "coverage_summary.json", "trend_vectors.json")
    missing = [name for name in required if not (output_dir / name).is_file()]
    if missing:
        return f"missing files: {', '.join(missing)}"

    try:
        with (output_dir / "coverage_summary.json").open(encoding="utf-8") as stream:
            coverage = json.load(stream)
        with (output_dir / "trend_vectors.json").open(encoding="utf-8") as stream:
            trends = json.load(stream)
    except (OSError, json.JSONDecodeError) as exc:
        return f"unreadable JSON: {exc}"

    if not isinstance(coverage, dict):
        return "coverage_summary.json must contain an object"
    if not isinstance(trends, dict):
        return "trend_vectors.json must contain an object"

    try:
        valid_rows = int(coverage.get("valid_rows", 0) or 0)
    except (TypeError, ValueError):
        return "valid_rows is not an integer"
    if valid_rows < min_valid_rows:
        return f"valid_rows={valid_rows} < {min_valid_rows}"

    slotframes = coverage.get("slotframe_counts", {}) or {}
    if not isinstance(slotframes, dict) or len(slotframes) < min_slotframes:
        count = len(slotframes) if isinstance(slotframes, dict) else 0
        return f"slotframes={count} < {min_slotframes}"

    if required_profile:
        profile_counts = coverage.get("profile_counts", {}) or {}
        if not isinstance(profile_counts, dict):
            return "profile_counts must contain an object"
        try:
            nonzero_profiles = {
                str(name): int(count)
                for name, count in profile_counts.items()
                if int(count or 0) > 0
            }
        except (TypeError, ValueError):
            return "profile_counts contains a non-integer count"
        expected = {required_profile: valid_rows}
        if nonzero_profiles != expected:
            return f"profile_counts={nonzero_profiles}, expected {expected}"

    for metric in ("power", "delay", "reliability"):
        metric_data = trends.get(metric)
        if not isinstance(metric_data, dict):
            return f"missing trend metric: {metric}"
        coefficients = metric_data.get("coefficients")
        if not isinstance(coefficients, list) or not coefficients:
            return f"missing coefficients for trend metric: {metric}"
        try:
            if not all(math.isfinite(float(value)) for value in coefficients):
                return f"non-finite coefficients for trend metric: {metric}"
        except (TypeError, ValueError):
            return f"non-numeric coefficients for trend metric: {metric}"

    if require_graph_dataset:
        graph_issue = graph_dataset_completion_issue(
            output_dir,
            min_valid_records=min_valid_rows,
        )
        if graph_issue is not None:
            return graph_issue

    return None


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
        help="Rerun seeds even when all requested artifacts already validate.",
    )
    parser.add_argument(
        "--record-graphs",
        action="store_true",
        help="Record graph_before/action/graph_after transitions for GNN training.",
    )
    args = parser.parse_args(argv)

    seeds = _derive_seeds(args)
    if not seeds:
        print("No seeds specified, nothing to do.", file=sys.stderr)
        return 1

    output_base = Path(args.output_base).resolve()
    log_base = Path(args.log_base).resolve()
    lock_path = WORKSPACE / ".cooja_controller.lock"
    lock_stream = lock_path.open("a+")
    try:
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_stream.close()
        print(
            f"Another Cooja experiment holds {lock_path}; "
            "trend collection will not start.",
            file=sys.stderr,
        )
        return 2

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
        "ELISE_RECORD_GRAPH_TRANSITIONS": "1" if args.record_graphs else "0",
    }

    try:
        for seed in seeds:
            csc_text = _update_cooja_seed(original_csc, seed)
            COOJA_CSC.write_text(csc_text)

            run_name = f"cycle_r500_s{seed}"
            output_dir = output_base / run_name
            log_dir = log_base / run_name
            completion_issue = _seed_completion_issue(
                output_dir,
                min_valid_rows=max(0, args.min_valid_rows),
                min_slotframes=max(0, args.min_slotframes),
                required_profile="" if args.cycle_profiles else "balanced",
                require_graph_dataset=args.record_graphs,
            )
            if not args.rerun_completed:
                if completion_issue is None:
                    print(f"[seed={seed}] Skipping validated output at {output_dir}")
                    continue
                if output_dir.exists():
                    print(
                        f"[seed={seed}] Existing output is not complete "
                        f"({completion_issue}); rerunning."
                    )
            _run_command(seed, cmd_env, output_dir, log_dir)
            completion_issue = _seed_completion_issue(
                output_dir,
                min_valid_rows=max(0, args.min_valid_rows),
                min_slotframes=max(0, args.min_slotframes),
                required_profile="" if args.cycle_profiles else "balanced",
                require_graph_dataset=args.record_graphs,
            )
            if completion_issue is not None:
                raise RuntimeError(
                    f"seed {seed} finished with invalid output: "
                    f"{completion_issue}"
                )
    finally:
        # Restore the CSC file to its original content.
        COOJA_CSC.write_text(original_csc)
        fcntl.flock(lock_stream.fileno(), fcntl.LOCK_UN)
        lock_stream.close()

    print("All seeds completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
