"""Command-line entry point for freezing and collecting the G0 dataset."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from . import REPO_ROOT
from .collector import collect_dataset
from .prepare import freeze_execution_plan, prepare_dataset
from .protocol import load_protocol
from .schema import validate_dataset
from .storage import aggregate_completed_runs


DEFAULT_CONFIG = Path(__file__).resolve().parent / "config" / "g0.json"


def _integer_list(raw: str) -> list[int]:
    try:
        values = [int(item.strip()) for item in raw.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated integers") from exc
    if not values or len(values) != len(set(values)):
        raise argparse.ArgumentTypeError("values must be non-empty and unique")
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect fixed-topology G0 labels without invoking PPO or Gym Env",
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--seeds", type=_integer_list)
    parser.add_argument("--candidates", type=_integer_list)
    parser.add_argument("--warmup-cycles", type=int)
    parser.add_argument("--accepted-cycles", type=int)
    parser.add_argument("--max-attempts-per-cycle", type=int)
    parser.add_argument("--port", type=int)
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    protocol = load_protocol(args.config)
    default_output = (
        REPO_ROOT / "runs" / "topk_dataset" / ("g0_smoke" if args.smoke else "g0")
    )
    output_dir = (args.output or default_output).resolve()

    configured_seeds = protocol["collection"]["cooja_seeds"]
    configured_candidates = protocol["slotframe"]["candidates"]
    if args.smoke:
        seeds = args.seeds or [configured_seeds[0]]
        candidates = args.candidates or [10, 40, 68]
        warmup_cycles = 1 if args.warmup_cycles is None else args.warmup_cycles
        accepted_cycles = 2 if args.accepted_cycles is None else args.accepted_cycles
        mode = "smoke"
    else:
        seeds = args.seeds or configured_seeds
        candidates = args.candidates or configured_candidates
        warmup_cycles = (
            int(protocol["collection"]["warmup_cycles"])
            if args.warmup_cycles is None
            else args.warmup_cycles
        )
        accepted_cycles = (
            int(protocol["collection"]["accepted_cycles"])
            if args.accepted_cycles is None
            else args.accepted_cycles
        )
        mode = "full"
    max_attempts = (
        int(protocol["collection"]["max_attempts_per_cycle"])
        if args.max_attempts_per_cycle is None
        else args.max_attempts_per_cycle
    )
    port = int(protocol["collection"]["port"]) if args.port is None else args.port

    if not set(seeds).issubset(configured_seeds):
        raise SystemExit("Selected seeds must be a subset of the frozen G0 seeds")
    if not set(candidates).issubset(configured_candidates):
        raise SystemExit("Selected candidates must be a subset of the frozen G0 domain")
    if min(warmup_cycles, accepted_cycles, max_attempts) < 1:
        raise SystemExit("Cycle and attempt counts must be positive")
    if not 1 <= port <= 65535:
        raise SystemExit("Port must be in [1, 65535]")

    topology = prepare_dataset(protocol, output_dir)
    freeze_execution_plan(
        output_dir,
        seeds=seeds,
        candidates=candidates,
        warmup_cycles=warmup_cycles,
        accepted_cycles=accepted_cycles,
        max_attempts_per_cycle=max_attempts,
        mode=mode,
        port=port,
    )
    aggregate_completed_runs(output_dir)
    if args.validate_only:
        report = validate_dataset(output_dir, require_complete=False)
        print(report)
        return 0
    if args.prepare_only:
        report = validate_dataset(output_dir, require_complete=False)
        print(f"Prepared G0 metadata at {output_dir}")
        print(report)
        return 0

    counts = collect_dataset(
        protocol,
        topology,
        output_dir,
        seeds=seeds,
        candidates=candidates,
        warmup_cycles=warmup_cycles,
        accepted_cycles=accepted_cycles,
        max_attempts_per_cycle=max_attempts,
        port=port,
    )
    report = validate_dataset(output_dir, require_complete=True)
    print(f"G0 collection complete at {output_dir}")
    print(counts)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
