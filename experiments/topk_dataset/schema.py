"""Integrity checks for frozen G0 metadata and collected CSV files."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .measurement import TX_DATA_PATTERN
from .protocol import sha256_file, sha256_json
from .storage import read_csv, write_json_atomic


REJECTION_REASONS = {
    "MISSING_NODES",
    "STALL_TIMEOUT",
    "WAIT_RETRY_EXHAUSTED",
    "NON_FINITE_METRIC",
    "SCHEDULE_INFEASIBLE",
    "COOJA_CRASH",
    "ENCODING_ERROR",
}


class SchemaError(ValueError):
    """Raised when generated metadata or measurements violate the protocol."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SchemaError(message)


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def _unique(rows: list[dict[str, str]], keys: tuple[str, ...], label: str) -> None:
    values = [tuple(row[key] for key in keys) for row in rows]
    _require(len(values) == len(set(values)), f"Duplicate primary key in {label}")


def _audit_source_counters(
    output_dir: Path,
    accepted_rows: list[dict[str, str]],
) -> int:
    rows_by_run: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in accepted_rows:
        rows_by_run[row["run_id"]].append(row)

    audited = 0
    for run_id, rows in rows_by_run.items():
        testlog = output_dir / "runs" / run_id / "cooja" / "COOJA.testlog"
        _require(testlog.is_file(), f"Missing preserved Cooja test log for {run_id}")
        windows = {}
        for row in rows:
            cycle = int(row["cycle_sequence"])
            _require(cycle not in windows, f"Duplicate accepted cycle sequence in {run_id}")
            start_us = round(float(row["cycle_start_sim_ms"]) * 1000.0)
            end_us = round(
                (float(row["cycle_start_sim_ms"]) + float(row["cycle_duration_sim_ms"]))
                * 1000.0
            )
            windows[cycle] = (start_us, end_us, row, Counter())

        with testlog.open(encoding="utf-8", errors="replace") as source:
            for line in source:
                match = TX_DATA_PATTERN.search(line)
                if match is None:
                    continue
                cycle = int(match.group("cycle"))
                window = windows.get(cycle)
                if window is None:
                    continue
                sim_time = int(match.group("sim_time"))
                if window[0] <= sim_time <= window[1]:
                    window[3][int(match.group("node_id"))] += 1

        for cycle, (_start, _end, row, observed) in windows.items():
            expected = {
                int(node_id): int(count)
                for node_id, count in json.loads(
                    row["expected_by_source_json"]
                ).items()
            }
            _require(
                dict(sorted(observed.items())) == dict(sorted(expected.items())),
                f"Source TX audit failed for {run_id} cycle {cycle}",
            )
            audited += 1
    return audited


def validate_dataset(output_dir: Path, *, require_complete: bool) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    required_files = (
        "manifest.json",
        "config_snapshot.json",
        "execution_plan.json",
        "schedule.json",
        "topologies.csv",
        "nodes.csv",
        "edges.csv",
        "contexts.csv",
    )
    missing = [name for name in required_files if not (output_dir / name).is_file()]
    _require(not missing, "Missing dataset files: " + ", ".join(missing))

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest_without_hash = {
        key: value for key, value in manifest.items() if key != "manifest_sha256"
    }
    _require(
        manifest["manifest_sha256"] == sha256_json(manifest_without_hash),
        "manifest_sha256 is invalid",
    )
    config_snapshot = json.loads(
        (output_dir / "config_snapshot.json").read_text(encoding="utf-8")
    )
    _require(
        manifest["config_snapshot_sha256"] == sha256_json(config_snapshot),
        "config_snapshot_sha256 is invalid",
    )
    plan = json.loads((output_dir / "execution_plan.json").read_text(encoding="utf-8"))
    plan_without_metadata = {
        key: value
        for key, value in plan.items()
        if key not in {"created_at", "execution_plan_sha256"}
    }
    _require(
        plan["execution_plan_sha256"] == sha256_json(plan_without_metadata),
        "execution_plan_sha256 is invalid",
    )
    schedule = json.loads((output_dir / "schedule.json").read_text(encoding="utf-8"))
    topologies = read_csv(output_dir / "topologies.csv")
    nodes = read_csv(output_dir / "nodes.csv")
    edges = read_csv(output_dir / "edges.csv")
    contexts = read_csv(output_dir / "contexts.csv")

    _require(len(topologies) == 1, "G0 must contain exactly one frozen topology")
    _require(len(contexts) == 1, "G0 must contain exactly one context")
    topology = topologies[0]
    context = contexts[0]
    node_count = int(topology["node_count"])
    l0 = int(context["L0"])
    _require(_as_bool(topology["connected"]), "The G0 topology is disconnected")
    _require(len(nodes) == node_count, "nodes.csv count differs from topology node_count")
    _require(
        sum(_as_bool(row["is_sink"]) for row in nodes) == 1,
        "G0 must have exactly one sink",
    )
    _require(
        sum(_as_bool(row["is_source"]) for row in nodes) == node_count - 1,
        "G0 source count is inconsistent",
    )
    _unique(nodes, ("topology_id", "node_id"), "nodes.csv")
    _unique(edges, ("topology_id", "u", "v"), "edges.csv")
    _require(all(int(row["u"]) < int(row["v"]) for row in edges), "edges must use u < v")
    _require(len(edges) == int(topology["edge_count"]), "edges.csv count is inconsistent")
    _require(
        sum(_as_bool(row["in_routing_tree"]) for row in edges) == node_count - 1,
        "The frozen routing tree must contain N-1 links",
    )
    _require(len(schedule) == l0, "L0 must equal the number of frozen links")
    timeslots = sorted(int(cell["timeslot"]) for cell in schedule)
    _require(timeslots == list(range(l0)), "Schedule timeslots must be exactly 0..L0-1")
    _require(
        context["schedule_sha256"] == manifest["schedule_sha256"],
        "Context and manifest schedule hashes differ",
    )
    _require(
        manifest["schedule_sha256"] == sha256_json(schedule),
        "schedule.json differs from the frozen schedule hash",
    )
    template_csc = Path(config_snapshot["topology"]["template_csc"])
    _require(template_csc.is_file(), "Frozen template CSC no longer exists")
    _require(
        manifest["template_csc_sha256"] == sha256_file(template_csc),
        "The template CSC changed after the manifest was frozen",
    )
    configured_candidates = json.loads(context["candidate_list_json"])
    _require(
        configured_candidates == manifest["candidate_list"],
        "Context and manifest candidate lists differ",
    )
    selected_candidates = [int(value) for value in plan["candidates"]]
    selected_seeds = [int(value) for value in plan["seeds"]]
    _require(
        set(selected_candidates).issubset(configured_candidates),
        "Execution plan contains an unfrozen candidate",
    )
    _require(
        set(selected_seeds).issubset(manifest["cooja_seeds"]),
        "Execution plan contains an unfrozen Cooja seed",
    )

    raw = read_csv(output_dir / "raw_cycles.csv")
    warmup = read_csv(output_dir / "warmup_cycles.csv")
    rejected = read_csv(output_dir / "rejected_cycles.csv")
    summaries = read_csv(output_dir / "run_summary.csv")
    done_files = sorted((output_dir / "runs").glob("*/done.json"))
    completed_runs = len(done_files)

    _unique(raw, ("run_id", "candidate_index", "cycle_index"), "raw_cycles.csv")
    _unique(
        warmup,
        ("run_id", "candidate_index", "cycle_index"),
        "warmup_cycles.csv",
    )
    _unique(
        rejected,
        ("run_id", "candidate_index", "attempt_index"),
        "rejected_cycles.csv",
    )
    _unique(summaries, ("run_id", "candidate_index"), "run_summary.csv")

    for row in raw + warmup:
        expected = int(row["expected_packets"])
        received = int(row["received_packets"])
        delivered = int(row["delivered_packets"])
        delay_sum = float(row["delay_sum_ms"])
        delay_mean = float(row["delay_mean_packet_weighted_ms"])
        pdr = float(row["pdr"])
        _require(expected > 0, "An accepted cycle has no expected packets")
        _require(received == delivered <= expected, "Accepted packet counters are inconsistent")
        _require(math.isclose(delay_mean, delay_sum / delivered, rel_tol=1e-9), "Delay equation failed")
        _require(math.isclose(pdr, received / expected, rel_tol=1e-9), "PDR equation failed")
        _require(
            int(row["reporting_source_count"]) == int(row["expected_source_count"]),
            "Accepted cycle does not have 100% source coverage",
        )
        _require(
            int(row["current_sf_len"]) == int(row["slotframe"]),
            "Applied slotframe differs from requested candidate",
        )
        _require(
            int(row["slotframe"]) > int(row["last_ts_in_schedule"]),
            "Accepted slotframe cannot contain the frozen schedule",
        )
    _require(all(not _as_bool(row["is_warmup"]) for row in raw), "raw_cycles contains warm-up data")
    _require(all(_as_bool(row["is_warmup"]) for row in warmup), "warmup_cycles contains measured data")
    _require(
        all(row["reason_code"] in REJECTION_REASONS for row in rejected),
        "rejected_cycles contains an unknown reason code",
    )

    attempt_rows = raw + warmup + rejected
    _unique(
        attempt_rows,
        ("run_id", "candidate_index", "attempt_index"),
        "combined cycle attempts",
    )
    attempts_by_candidate: dict[tuple[str, str], list[int]] = defaultdict(list)
    attempts_by_requested_cycle: Counter = Counter()
    for row in attempt_rows:
        candidate_key = (row["run_id"], row["candidate_index"])
        attempts_by_candidate[candidate_key].append(int(row["attempt_index"]))
        requested_key = (
            row["run_id"],
            row["candidate_index"],
            _as_bool(row["is_warmup"]),
            int(row["cycle_index"]),
        )
        attempts_by_requested_cycle[requested_key] += 1
    for key, attempts in attempts_by_candidate.items():
        _require(
            sorted(attempts) == list(range(1, max(attempts) + 1)),
            f"Cycle attempts are not contiguous for {key}",
        )
    _require(
        all(
            count <= int(plan["max_attempts_per_cycle"])
            for count in attempts_by_requested_cycle.values()
        ),
        "A requested cycle exceeded max_attempts_per_cycle",
    )

    per_candidate_raw = Counter((row["run_id"], int(row["slotframe"])) for row in raw)
    per_candidate_warmup = Counter((row["run_id"], int(row["slotframe"])) for row in warmup)
    summaries_by_run: dict[str, set[int]] = defaultdict(set)
    for row in summaries:
        summaries_by_run[row["run_id"]].add(int(row["slotframe"]))
        _require(int(row["accepted_cycles"]) == int(plan["accepted_cycles"]), "Summary accepted count is wrong")
        _require(int(row["warmup_cycles"]) == int(plan["warmup_cycles"]), "Summary warm-up count is wrong")
        _require(bool(row["mote_binary_sha256"]), "Summary is missing the mote binary hash")
        _require(
            row["config_snapshot_sha256"] == manifest["config_snapshot_sha256"],
            "Summary config hash differs from the frozen manifest",
        )
        run_dir = output_dir / "runs" / row["run_id"]
        run_csc = run_dir / "cooja" / "run.csc"
        runtime_config_path = run_dir / "controller.json"
        _require(run_csc.is_file(), f"Missing run CSC for {row['run_id']}")
        _require(
            row["csc_sha256"] == sha256_file(run_csc),
            f"Run CSC hash differs for {row['run_id']}",
        )
        _require(runtime_config_path.is_file(), f"Missing runtime config for {row['run_id']}")
        runtime_config = json.loads(runtime_config_path.read_text(encoding="utf-8"))
        _require(
            row["runtime_config_sha256"] == sha256_json(runtime_config),
            f"Runtime config hash differs for {row['run_id']}",
        )
        binary_hashes = json.loads(row["mote_binary_hashes_json"])
        _require(
            row["mote_binary_sha256"] == sha256_json(binary_hashes),
            f"Combined binary hash differs for {row['run_id']}",
        )
        for relative_path, expected_hash in binary_hashes.items():
            binary = run_dir / relative_path
            _require(binary.is_file(), f"Missing preserved binary {binary}")
            _require(
                sha256_file(binary) == expected_hash,
                f"Preserved binary hash differs for {binary}",
            )
    for key, count in per_candidate_raw.items():
        _require(count == int(plan["accepted_cycles"]), f"Wrong accepted count for {key}")
    for key, count in per_candidate_warmup.items():
        _require(count == int(plan["warmup_cycles"]), f"Wrong warm-up count for {key}")
    _require(
        all(values == set(selected_candidates) for values in summaries_by_run.values()),
        "A completed seed has a partial candidate set",
    )

    if require_complete:
        _require(completed_runs == len(selected_seeds), "Not all planned seeds are complete")
        expected_summaries = len(selected_seeds) * len(selected_candidates)
        _require(len(summaries) == expected_summaries, "run_summary row count is incomplete")
        _require(
            len(raw) == expected_summaries * int(plan["accepted_cycles"]),
            "raw_cycles row count is incomplete",
        )
        _require(
            len(warmup) == expected_summaries * int(plan["warmup_cycles"]),
            "warmup_cycles row count is incomplete",
        )
        _require(
            {int(row["cooja_seed"]) for row in summaries} == set(selected_seeds),
            "Completed summaries do not use the frozen seed set",
        )

    audited_cycles = _audit_source_counters(output_dir, raw + warmup)
    report = {
        "valid": True,
        "require_complete": require_complete,
        "completed_runs": completed_runs,
        "planned_runs": len(selected_seeds),
        "candidate_summaries": len(summaries),
        "accepted_cycles": len(raw),
        "warmup_cycles": len(warmup),
        "rejected_cycles": len(rejected),
        "source_counter_audited_cycles": audited_cycles,
    }
    write_json_atomic(output_dir / "validation_report.json", report)
    return report
