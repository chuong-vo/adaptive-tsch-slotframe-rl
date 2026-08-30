"""Atomic CSV/JSON storage and completed-run aggregation."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Iterable


TOPOLOGY_FIELDS = [
    "topology_id", "coords_hash", "topology_family", "topology_seed",
    "layout_instance",
    "sink_placement", "dataset_group", "split", "node_count",
    "source_node_count", "edge_count", "average_degree", "degree_std",
    "graph_density", "max_hops", "mean_hops_to_sink", "diameter",
    "sink_degree", "bridge_count", "area_width", "area_height",
    "transmission_range", "interference_range", "routing_link_range",
    "routing_edge_count", "routing_average_degree", "reroll_count",
    "reroll_reasons", "connected", "csc_path", "csc_sha256",
    "manifest_frozen_at", "protocol_version",
]
NODE_FIELDS = [
    "topology_id", "node_id", "is_sink", "x", "y", "z", "degree",
    "hops_to_sink", "betweenness", "clustering_coeff", "is_source",
    "mote_type",
]
EDGE_FIELDS = [
    "topology_id", "u", "v", "distance", "in_routing_tree",
    "expected_link_quality", "is_bridge",
]
CONTEXT_FIELDS = [
    "context_id", "topology_id", "dataset_group", "split", "profile_id",
    "traffic_mode",
    "app_interval_ms", "aggregate_offered_load", "radio_model",
    "success_ratio_tx", "success_ratio_rx", "interference_profile",
    "routing_link_range", "processing_window_packets",
    "schedule_seed", "schedule_sha256", "L0", "scheduled_link_count",
    "candidate_count_M", "candidate_list_json", "r_min", "r_max",
    "min_gap", "frozen_at", "config_snapshot_sha256",
]
RAW_CYCLE_FIELDS = [
    "run_id", "context_id", "cooja_seed", "candidate_index", "slotframe",
    "cycle_index", "is_warmup", "cycle_sequence", "cycle_start_sim_ms",
    "cycle_duration_sim_ms", "cycle_duration_wall_s", "power_total_mw",
    "power_per_source_mw", "power_legacy_wam", "delay_sum_ms",
    "delivered_packets", "expected_packets", "received_packets",
    "throughput_pps", "delay_mean_packet_weighted_ms", "pdr",
    "reporting_source_count",
    "expected_source_count", "last_ts_in_schedule", "current_sf_len",
    "attempt_index", "expected_by_source_json", "received_by_source_json",
    "power_by_source_mw_json",
]
REJECTED_CYCLE_FIELDS = [
    "run_id", "context_id", "cooja_seed", "candidate_index", "slotframe",
    "cycle_index", "is_warmup", "attempt_index", "cycle_sequence",
    "reason_code", "missing_node_ids", "reporting_source_count",
    "expected_source_count", "stall_detected", "wait_attempts",
    "wall_seconds", "raw_note",
]
RUN_SUMMARY_FIELDS = [
    "run_id", "context_id", "cooja_seed", "schedule_seed",
    "schedule_sha256", "candidate_index", "slotframe",
    "candidate_order_json", "run_mean_power_total",
    "run_mean_power_per_source", "run_mean_throughput_pps",
    "run_mean_delay_packet_weighted", "run_pdr",
    "run_sd_power", "run_sd_delay", "accepted_cycles", "rejected_cycles",
    "warmup_cycles", "started_at", "ended_at", "wall_seconds",
    "csc_sha256", "contiki_commit", "source_dirty", "mote_binary_sha256",
    "mote_binary_hashes_json", "config_snapshot_sha256",
    "runtime_config_sha256", "protocol_version", "runner_version", "hostname",
]


def _serializable(value):
    if isinstance(value, (dict, list, tuple, set)):
        if isinstance(value, set):
            value = sorted(value)
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return value


def write_csv_atomic(path: Path, fieldnames: list[str], rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _serializable(row.get(key, "")) for key in fieldnames})
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(value, output, indent=2, sort_keys=True, ensure_ascii=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


def aggregate_completed_runs(output_dir: Path) -> dict[str, int]:
    raw_rows = []
    warmup_rows = []
    rejected_rows = []
    summary_rows = []
    completed_runs = 0
    runs_dir = output_dir / "runs"
    for done_path in sorted(runs_dir.glob("*/done.json")):
        run_dir = done_path.parent
        raw_rows.extend(read_csv(run_dir / "raw_cycles.csv"))
        warmup_rows.extend(read_csv(run_dir / "warmup_cycles.csv"))
        rejected_rows.extend(read_csv(run_dir / "rejected_cycles.csv"))
        summary_rows.extend(read_csv(run_dir / "run_summary.csv"))
        completed_runs += 1

    raw_rows.sort(key=lambda row: (
        row.get("context_id", ""), int(row.get("cooja_seed", 0)),
        int(row.get("candidate_index", 0)), int(row.get("cycle_index", 0)),
    ))
    warmup_rows.sort(key=lambda row: (
        row.get("run_id", ""), int(row.get("candidate_index", 0)),
        int(row.get("cycle_index", 0)),
    ))
    rejected_rows.sort(key=lambda row: (
        row.get("run_id", ""), int(row.get("candidate_index", 0)),
        int(row.get("attempt_index", 0)),
    ))
    summary_rows.sort(key=lambda row: (
        row.get("context_id", ""), int(row.get("cooja_seed", 0)),
        int(row.get("candidate_index", 0)),
    ))

    write_csv_atomic(output_dir / "raw_cycles.csv", RAW_CYCLE_FIELDS, raw_rows)
    write_csv_atomic(
        output_dir / "warmup_cycles.csv",
        RAW_CYCLE_FIELDS,
        warmup_rows,
    )
    write_csv_atomic(
        output_dir / "rejected_cycles.csv",
        REJECTED_CYCLE_FIELDS,
        rejected_rows,
    )
    write_csv_atomic(
        output_dir / "run_summary.csv",
        RUN_SUMMARY_FIELDS,
        summary_rows,
    )
    counts = {
        "completed_runs": completed_runs,
        "raw_cycles": len(raw_rows),
        "warmup_cycles": len(warmup_rows),
        "rejected_cycles": len(rejected_rows),
        "candidate_summaries": len(summary_rows),
    }
    write_json_atomic(output_dir / "collection_state.json", counts)
    return counts
