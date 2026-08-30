"""CLI for preparing, smoke-testing, and collecting the expanded dataset."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from . import REPO_ROOT
from .expanded_collector import collect_expanded_dataset
from .expanded_prepare import freeze_expanded_plan, prepare_expanded_dataset
from .expanded_protocol import load_expanded_protocol
from .expanded_schema import validate_expanded_dataset
from .storage import aggregate_completed_runs


DEFAULT_CONFIG = Path(__file__).resolve().parent / "config" / "expanded.json"


def _integer_list(raw: str) -> list[int]:
    values = [int(value.strip()) for value in raw.split(",") if value.strip()]
    if not values or len(values) != len(set(values)):
        raise argparse.ArgumentTypeError("Expected unique comma-separated integers")
    return values


def _string_list(raw: str) -> list[str]:
    values = [value.strip() for value in raw.split(",") if value.strip()]
    if not values or len(values) != len(set(values)):
        raise argparse.ArgumentTypeError("Expected unique comma-separated values")
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect fixed multi-topology data for slotframe Top-K",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--smoke", action="store_true")
    mode.add_argument("--pilot", action="store_true")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--contexts", type=_string_list)
    parser.add_argument("--seeds", type=_integer_list)
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO")
    return parser


def _matches(
    context: dict,
    *,
    family: str,
    node_count: int,
    profile: str,
    placement: str | None = None,
) -> bool:
    return (
        context["topology_family"] == family
        and int(context["node_count"]) == node_count
        and context["profile_id"] == profile
        and (placement is None or context["sink_placement"] == placement)
    )


def _first_matching(contexts: list[dict], **criteria) -> dict:
    try:
        return next(context for context in contexts if _matches(context, **criteria))
    except StopIteration as exc:
        raise RuntimeError(f"No frozen context matches {criteria}") from exc


def _select_mode(protocol: dict, contexts: list[dict], args):
    if args.contexts:
        context_ids = args.contexts
        mode = "custom"
    elif args.smoke:
        context_ids = [
            _first_matching(
                contexts,
                family="chain",
                node_count=8,
                profile="normal",
                placement="center",
            )["context_id"],
            _first_matching(
                contexts,
                family="random_geometric",
                node_count=20,
                profile="stress",
                placement="edge",
            )["context_id"],
        ]
        mode = "smoke"
    elif args.pilot:
        context_ids = []
        for family in protocol["topology"]["families"]:
            for profile in ("normal", "stress"):
                context_ids.append(
                    _first_matching(
                        contexts,
                        family=family,
                        node_count=20,
                        profile=profile,
                    )["context_id"]
                )
        mode = "pilot"
    else:
        context_ids = [context["context_id"] for context in contexts]
        mode = "full"

    contexts_by_id = {context["context_id"]: context for context in contexts}
    unknown = sorted(set(context_ids).difference(contexts_by_id))
    if unknown:
        raise SystemExit("Unknown context IDs: " + ", ".join(unknown))
    if args.seeds:
        seeds = args.seeds
    elif args.smoke:
        seeds = protocol["collection"]["cooja_seeds"][:1]
    elif args.pilot:
        seeds = protocol["collection"]["cooja_seeds"][:3]
    else:
        seeds = protocol["collection"]["cooja_seeds"]
    if not set(seeds).issubset(protocol["collection"]["cooja_seeds"]):
        raise SystemExit("Selected seeds are outside the frozen seed domain")

    candidate_map = {}
    for context_id in context_ids:
        candidates = [int(value) for value in contexts_by_id[context_id]["candidates"]]
        candidate_map[context_id] = (
            [candidates[0], candidates[len(candidates) // 2], candidates[-1]]
            if args.smoke else candidates
        )
    if args.smoke:
        warmup_cycles, accepted_cycles = 1, 2
    elif args.pilot:
        warmup_cycles, accepted_cycles = 2, 4
    else:
        warmup_cycles = int(protocol["collection"]["warmup_cycles"])
        accepted_cycles = int(protocol["collection"]["accepted_cycles"])
    return mode, context_ids, candidate_map, seeds, warmup_cycles, accepted_cycles


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    protocol = load_expanded_protocol(args.config)
    suffix = "expanded_smoke" if args.smoke else "expanded_pilot" if args.pilot else "expanded"
    output_dir = (args.output or REPO_ROOT / "runs" / "topk_dataset" / suffix).resolve()
    contexts = prepare_expanded_dataset(protocol, output_dir)
    mode, context_ids, candidate_map, seeds, warmup_cycles, accepted_cycles = _select_mode(
        protocol,
        contexts,
        args,
    )
    collection = protocol["collection"]
    freeze_expanded_plan(
        output_dir,
        context_ids=context_ids,
        candidate_map=candidate_map,
        seeds=seeds,
        warmup_cycles=warmup_cycles,
        accepted_cycles=accepted_cycles,
        max_attempts_per_cycle=int(collection["max_attempts_per_cycle"]),
        mode=mode,
        port=int(collection["port"]),
    )
    aggregate_completed_runs(output_dir)
    if args.prepare_only:
        report = validate_expanded_dataset(output_dir, require_complete=False)
        print(f"Prepared expanded metadata at {output_dir}")
        print(report)
        return 0
    if args.validate_only:
        print(validate_expanded_dataset(output_dir, require_complete=False))
        return 0

    counts = collect_expanded_dataset(
        protocol,
        contexts,
        output_dir,
        context_ids=context_ids,
        candidate_map=candidate_map,
        seeds=seeds,
        warmup_cycles=warmup_cycles,
        accepted_cycles=accepted_cycles,
        max_attempts_per_cycle=int(collection["max_attempts_per_cycle"]),
        port=int(collection["port"]),
    )
    report = validate_expanded_dataset(output_dir, require_complete=True)
    print(f"Expanded collection complete at {output_dir}")
    print(counts)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
