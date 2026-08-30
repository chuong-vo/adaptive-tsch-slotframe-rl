"""Sequential, resumable collection across frozen expanded contexts."""

from __future__ import annotations

import json
import logging
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from .collector import collect_seed, run_id_for
from .expanded_protocol import context_protocol
from .expanded_topology import load_runtime_topology
from .protocol import sha256_file
from .storage import aggregate_completed_runs, read_csv, write_csv_atomic


LOGGER = logging.getLogger(__name__)


LABEL_FIELDS = [
    "context_id", "topology_id", "split", "profile_id", "candidate_index",
    "slotframe", "n_runs", "mean_power_total_mw", "mean_power_per_source_mw",
    "mean_throughput_pps", "mean_delay_packet_weighted_ms", "mean_pdr",
    "sd_power_per_source_mw", "sd_throughput_pps", "sd_delay_ms", "sd_pdr",
    "ci95_power_lo", "ci95_power_hi", "ci95_throughput_lo",
    "ci95_throughput_hi", "ci95_delay_lo", "ci95_delay_hi",
    "ci95_pdr_lo", "ci95_pdr_hi",
]


def _sample_sd(values: list[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def _ci95(values: list[float]) -> tuple[float | str, float | str]:
    if len(values) < 2:
        return "", ""
    # Student-t 0.975 critical values for df 1..30; normal tail thereafter.
    critical = {
        1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
        6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
        11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
        16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
        21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
        26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
    }.get(len(values) - 1, 1.96)
    mean = statistics.fmean(values)
    margin = critical * statistics.stdev(values) / len(values) ** 0.5
    return mean - margin, mean + margin


def write_context_action_labels(
    output_dir: Path,
    contexts_by_id: dict[str, dict[str, Any]],
) -> int:
    summaries = read_csv(output_dir / "run_summary.csv")
    grouped: dict[tuple[str, int, int], list[dict[str, str]]] = defaultdict(list)
    for row in summaries:
        grouped[
            (row["context_id"], int(row["candidate_index"]), int(row["slotframe"]))
        ].append(row)
    labels = []
    for (context_id, candidate_index, slotframe), rows in sorted(grouped.items()):
        context = contexts_by_id[context_id]
        power_total = [float(row["run_mean_power_total"]) for row in rows]
        power_source = [float(row["run_mean_power_per_source"]) for row in rows]
        throughput = [float(row["run_mean_throughput_pps"]) for row in rows]
        delay = [float(row["run_mean_delay_packet_weighted"]) for row in rows]
        pdr = [float(row["run_pdr"]) for row in rows]
        power_ci = _ci95(power_source)
        throughput_ci = _ci95(throughput)
        delay_ci = _ci95(delay)
        pdr_ci = _ci95(pdr)
        labels.append({
            "context_id": context_id,
            "topology_id": context["topology_id"],
            "split": context["split"],
            "profile_id": context["profile_id"],
            "candidate_index": candidate_index,
            "slotframe": slotframe,
            "n_runs": len(rows),
            "mean_power_total_mw": statistics.fmean(power_total),
            "mean_power_per_source_mw": statistics.fmean(power_source),
            "mean_throughput_pps": statistics.fmean(throughput),
            "mean_delay_packet_weighted_ms": statistics.fmean(delay),
            "mean_pdr": statistics.fmean(pdr),
            "sd_power_per_source_mw": _sample_sd(power_source),
            "sd_throughput_pps": _sample_sd(throughput),
            "sd_delay_ms": _sample_sd(delay),
            "sd_pdr": _sample_sd(pdr),
            "ci95_power_lo": power_ci[0],
            "ci95_power_hi": power_ci[1],
            "ci95_throughput_lo": throughput_ci[0],
            "ci95_throughput_hi": throughput_ci[1],
            "ci95_delay_lo": delay_ci[0],
            "ci95_delay_hi": delay_ci[1],
            "ci95_pdr_lo": pdr_ci[0],
            "ci95_pdr_hi": pdr_ci[1],
        })
    write_csv_atomic(output_dir / "context_action_labels.csv", LABEL_FIELDS, labels)
    return len(labels)


def collect_expanded_dataset(
    protocol: dict[str, Any],
    contexts: list[dict[str, Any]],
    output_dir: Path,
    *,
    context_ids: list[str],
    candidate_map: dict[str, list[int]],
    seeds: list[int],
    warmup_cycles: int,
    accepted_cycles: int,
    max_attempts_per_cycle: int,
    port: int,
) -> dict[str, int]:
    contexts_by_id = {context["context_id"]: context for context in contexts}
    selected = [contexts_by_id[context_id] for context_id in context_ids]
    total_runs = len(selected) * len(seeds)
    started = time.monotonic()
    processed = 0
    for context_position, context in enumerate(selected, start=1):
        if sha256_file(Path(context["csc_path"])) != context["csc_sha256"]:
            raise RuntimeError(f"Frozen CSC changed for {context['context_id']}")
        runtime_topology = load_runtime_topology(context)
        runtime_protocol = context_protocol(protocol, context=context)
        candidates = [int(value) for value in candidate_map[context["context_id"]]]
        LOGGER.info(
            "Expanded context %d/%d | %s | candidates=%d | seeds=%d",
            context_position,
            len(selected),
            context["context_id"],
            len(candidates),
            len(seeds),
        )
        for seed in seeds:
            collect_seed(
                runtime_protocol,
                runtime_topology,
                output_dir,
                cooja_seed=int(seed),
                candidates=candidates,
                warmup_cycles=warmup_cycles,
                accepted_cycles=accepted_cycles,
                max_attempts_per_cycle=max_attempts_per_cycle,
                port=port,
                aggregate_on_complete=False,
            )
            processed += 1
            elapsed = time.monotonic() - started
            remaining = (elapsed / processed) * (total_runs - processed) if processed else 0.0
            LOGGER.info(
                "Expanded run %d/%d complete | elapsed=%.1f min | ETA=%.1f h",
                processed,
                total_runs,
                elapsed / 60.0,
                remaining / 3600.0,
            )
        aggregate_completed_runs(output_dir)
        write_context_action_labels(output_dir, contexts_by_id)

    counts = aggregate_completed_runs(output_dir)
    counts["context_action_labels"] = write_context_action_labels(
        output_dir,
        contexts_by_id,
    )
    expected_runs = len(selected) * len(seeds)
    if counts["completed_runs"] != expected_runs:
        raise RuntimeError(
            f"Expected {expected_runs} completed runs, got {counts['completed_runs']}"
        )
    return counts
