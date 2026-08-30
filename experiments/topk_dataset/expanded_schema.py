"""Integrity validation for multi-context expanded collection output."""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sdwsn_controller.tsch.contention_free_scheduler import schedule_sha256

from .csc import parse_csc
from .protocol import sha256_file, sha256_json
from .schema import (
    REJECTION_REASONS,
    SchemaError,
    _as_bool,
    _audit_source_counters,
    _require,
    _unique,
)
from .storage import read_csv, write_json_atomic


def _app_interval_from_csc(path: Path) -> int:
    simulation = ET.parse(path).getroot().find("simulation")
    _require(simulation is not None, f"CSC has no simulation: {path}")
    for mote_type in simulation.findall("motetype"):
        source = (mote_type.findtext("source") or "").strip()
        if "sdn-tsch-node" not in source:
            continue
        commands = mote_type.findtext("commands") or ""
        marker = "SDN_CONF_DATA_PACKET_INTERVAL="
        _require(marker in commands, f"CSC does not freeze traffic interval: {path}")
        return int(commands.split(marker, 1)[1].split(",", 1)[0].split()[0])
    raise SchemaError(f"CSC has no source mote type: {path}")


def validate_expanded_dataset(
    output_dir: Path,
    *,
    require_complete: bool,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    required = (
        "manifest.json", "config_snapshot.json", "execution_plan.json",
        "frozen_contexts.json", "schedules.json", "topologies.csv", "nodes.csv",
        "edges.csv", "contexts.csv", "raw_cycles.csv", "warmup_cycles.csv",
        "rejected_cycles.csv", "run_summary.csv",
    )
    missing = [name for name in required if not (output_dir / name).is_file()]
    _require(not missing, "Missing expanded files: " + ", ".join(missing))
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest_body = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    _require(
        manifest["manifest_sha256"] == sha256_json(manifest_body),
        "Expanded manifest hash is invalid",
    )
    config = json.loads((output_dir / "config_snapshot.json").read_text(encoding="utf-8"))
    frozen = json.loads((output_dir / "frozen_contexts.json").read_text(encoding="utf-8"))
    schedules = json.loads((output_dir / "schedules.json").read_text(encoding="utf-8"))
    _require(
        manifest["config_snapshot_sha256"] == sha256_json(config),
        "Expanded config hash is invalid",
    )
    _require(
        manifest["frozen_contexts_sha256"] == sha256_json(frozen),
        "Frozen context hash is invalid",
    )
    _require(
        manifest["schedules_sha256"] == sha256_json(schedules),
        "Expanded schedules hash is invalid",
    )
    _require(
        manifest["template_csc_sha256"] == sha256_file(Path(config["template_csc"])),
        "Source CSC template changed",
    )

    plan = json.loads((output_dir / "execution_plan.json").read_text(encoding="utf-8"))
    plan_body = {
        key: value for key, value in plan.items()
        if key not in {"created_at", "execution_plan_sha256"}
    }
    _require(
        plan["execution_plan_sha256"] == sha256_json(plan_body),
        "Expanded execution plan hash is invalid",
    )
    topologies = read_csv(output_dir / "topologies.csv")
    nodes = read_csv(output_dir / "nodes.csv")
    edges = read_csv(output_dir / "edges.csv")
    contexts = read_csv(output_dir / "contexts.csv")
    _require(len(topologies) == manifest["topology_count"], "Topology count changed")
    _require(len(contexts) == manifest["context_count"], "Context count changed")
    _unique(topologies, ("topology_id",), "topologies.csv")
    _unique(nodes, ("topology_id", "node_id"), "nodes.csv")
    _unique(edges, ("topology_id", "u", "v"), "edges.csv")
    _unique(contexts, ("context_id",), "contexts.csv")
    _require(
        {row["topology_family"] for row in topologies}
        == {"chain", "grid", "random_geometric"},
        "Expanded topology family set is wrong",
    )
    _require(
        all(2 <= int(row["node_count"]) < 50 for row in topologies),
        "Expanded dataset contains a node count outside [2, 49]",
    )
    _require(
        {row["sink_placement"] for row in topologies} == {"center", "edge"},
        "Expanded dataset must exercise center and edge sinks",
    )
    topology_by_id = {row["topology_id"]: row for row in topologies}
    nodes_by_topology: dict[str, list[dict[str, str]]] = defaultdict(list)
    edges_by_topology: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in nodes:
        nodes_by_topology[row["topology_id"]].append(row)
    for row in edges:
        edges_by_topology[row["topology_id"]].append(row)
    for topology_id, topology in topology_by_id.items():
        topology_nodes = nodes_by_topology[topology_id]
        topology_edges = edges_by_topology[topology_id]
        node_count = int(topology["node_count"])
        _require(len(topology_nodes) == node_count, f"Node count mismatch: {topology_id}")
        _require(
            sum(_as_bool(row["is_sink"]) for row in topology_nodes) == 1,
            f"Topology must have one sink: {topology_id}",
        )
        _require(
            sum(_as_bool(row["in_routing_tree"]) for row in topology_edges)
            == node_count - 1,
            f"Routing tree size mismatch: {topology_id}",
        )
        routing_link_range = float(topology["routing_link_range"])
        _require(
            all(
                not _as_bool(row["in_routing_tree"])
                or float(row["distance"]) <= routing_link_range + 1e-9
                for row in topology_edges
            ),
            f"Routing tree exceeds the planning range: {topology_id}",
        )
        cells = schedules[topology_id]
        _require(len(cells) == node_count - 1, f"L0 mismatch: {topology_id}")
        _require(
            sorted(int(cell["timeslot"]) for cell in cells) == list(range(node_count - 1)),
            f"Schedule is not contiguous: {topology_id}",
        )

    frozen_by_id = {row["context_id"]: row for row in frozen}
    context_by_id = {row["context_id"]: row for row in contexts}
    _require(set(frozen_by_id) == set(context_by_id), "Frozen/context IDs differ")
    profiles_by_topology: dict[str, set[str]] = defaultdict(set)
    for context_id, context in frozen_by_id.items():
        row = context_by_id[context_id]
        topology = topology_by_id[context["topology_id"]]
        profiles_by_topology[context["topology_id"]].add(context["profile_id"])
        _require(context["split"] == topology["split"], "Context split mismatch")
        _require(
            math.isclose(
                float(context["routing_link_range"]),
                float(topology["routing_link_range"]),
            ),
            "Context routing range mismatch",
        )
        _require(int(context["L0"]) == int(topology["node_count"]) - 1, "Context L0 mismatch")
        expected_window = (
            int(config["collection"]["processing_window_per_node"])
            * int(topology["node_count"])
        )
        _require(
            int(context["processing_window_packets"]) == expected_window,
            f"Processing window is not scaled by node count: {context_id}",
        )
        _require(
            int(row["processing_window_packets"]) == expected_window,
            f"CSV processing window differs from frozen context: {context_id}",
        )
        candidates = [int(value) for value in context["candidates"]]
        _require(len(candidates) == 15, "Expanded context must have 15 candidates")
        _require(candidates == sorted(set(candidates)), "Candidates are not unique/sorted")
        _require(min(candidates) >= int(context["L0"]), "Candidate below L0")
        _require(max(candidates) <= 255, "Candidate exceeds uint8 wire format")
        _require(schedule_sha256(context["cells"]) == context["schedule_sha256"], "Schedule hash mismatch")
        csc = Path(context["csc_path"])
        _require(csc.is_file(), f"Missing context CSC: {context_id}")
        _require(sha256_file(csc) == context["csc_sha256"], f"Context CSC changed: {context_id}")
        parsed = parse_csc(csc)
        _require(len(parsed.nodes) == int(topology["node_count"]), "CSC node count mismatch")
        _require(math.isclose(parsed.success_ratio_tx, float(context["success_ratio_tx"])), "CSC TX ratio mismatch")
        _require(math.isclose(parsed.success_ratio_rx, float(context["success_ratio_rx"])), "CSC RX ratio mismatch")
        _require(
            _app_interval_from_csc(csc) * 1000 == int(context["app_interval_ms"]),
            "CSC traffic interval mismatch",
        )
        _require(
            json.loads(row["candidate_list_json"]) == candidates,
            "CSV candidate list differs from frozen context",
        )
    _require(
        all(profiles == {"normal", "stress"} for profiles in profiles_by_topology.values()),
        "Each topology must contain normal and stress profiles",
    )

    selected_contexts = list(plan["context_ids"])
    _require(set(selected_contexts).issubset(frozen_by_id), "Plan has unknown context")
    selected_seeds = [int(seed) for seed in plan["seeds"]]
    candidate_map = {
        context_id: [int(value) for value in values]
        for context_id, values in plan["candidate_map"].items()
    }
    _require(set(candidate_map) == set(selected_contexts), "Candidate map/context mismatch")
    for context_id, candidates in candidate_map.items():
        _require(
            set(candidates).issubset(frozen_by_id[context_id]["candidates"]),
            f"Plan has an unfrozen candidate: {context_id}",
        )

    raw = read_csv(output_dir / "raw_cycles.csv")
    warmup = read_csv(output_dir / "warmup_cycles.csv")
    rejected = read_csv(output_dir / "rejected_cycles.csv")
    summaries = read_csv(output_dir / "run_summary.csv")
    _unique(raw, ("run_id", "candidate_index", "cycle_index"), "raw_cycles.csv")
    _unique(warmup, ("run_id", "candidate_index", "cycle_index"), "warmup_cycles.csv")
    _unique(rejected, ("run_id", "candidate_index", "attempt_index"), "rejected_cycles.csv")
    _unique(summaries, ("run_id", "candidate_index"), "run_summary.csv")
    for row in raw + warmup:
        expected = int(row["expected_packets"])
        received = int(row["received_packets"])
        duration_seconds = float(row["cycle_duration_sim_ms"]) / 1000.0
        _require(expected > 0 and 0 <= received <= expected, "Packet counters invalid")
        _require(
            math.isclose(float(row["pdr"]), received / expected, rel_tol=1e-9),
            "PDR equation failed",
        )
        _require(
            math.isclose(float(row["throughput_pps"]), received / duration_seconds, rel_tol=1e-9),
            "Throughput equation failed",
        )
        _require(
            int(row["reporting_source_count"]) == int(row["expected_source_count"]),
            "Accepted cycle lacks full source coverage",
        )
        _require(int(row["current_sf_len"]) == int(row["slotframe"]), "Applied slotframe mismatch")
    _require(
        all(row["reason_code"] in REJECTION_REASONS for row in rejected),
        "Unknown expanded rejection reason",
    )

    summaries_by_run: dict[str, set[int]] = defaultdict(set)
    for row in summaries:
        summaries_by_run[row["run_id"]].add(int(row["slotframe"]))
        context = frozen_by_id[row["context_id"]]
        _require(
            int(row["slotframe"]) in candidate_map[row["context_id"]],
            "Summary contains an unplanned candidate",
        )
        _require(bool(row["mote_binary_sha256"]), "Summary lacks binary hash")
        _require(
            int(row["accepted_cycles"]) == int(plan["accepted_cycles"]),
            "Summary accepted-cycle count is wrong",
        )
        _require(
            int(row["warmup_cycles"]) == int(plan["warmup_cycles"]),
            "Summary warm-up count is wrong",
        )
        run_dir = output_dir / "runs" / row["run_id"]
        _require((run_dir / "done.json").is_file(), "Summary run lacks done.json")
        _require(not (run_dir / "failure.json").exists(), "Completed run retains failure.json")
        _require(row["schedule_sha256"] == context["schedule_sha256"], "Run schedule changed")
        run_csc = run_dir / "cooja" / "run.csc"
        _require(row["csc_sha256"] == sha256_file(run_csc), "Run CSC hash mismatch")

    expected_runs = len(selected_contexts) * len(selected_seeds)
    done_files = list((output_dir / "runs").glob("*/done.json"))
    if require_complete:
        _require(len(done_files) == expected_runs, "Expanded run count is incomplete")
        expected_summaries = sum(len(candidate_map[context]) for context in selected_contexts) * len(selected_seeds)
        _require(len(summaries) == expected_summaries, "Expanded summaries are incomplete")
        _require(
            len(raw) == expected_summaries * int(plan["accepted_cycles"]),
            "Expanded accepted cycles are incomplete",
        )
        _require(
            len(warmup) == expected_summaries * int(plan["warmup_cycles"]),
            "Expanded warm-up cycles are incomplete",
        )
        for context_id in selected_contexts:
            expected_candidates = set(candidate_map[context_id])
            for seed in selected_seeds:
                run_id = f"{context_id}__cooja_seed_{seed}"
                _require(
                    summaries_by_run[run_id] == expected_candidates,
                    f"Incomplete candidate set for {run_id}",
                )

    audited = _audit_source_counters(output_dir, raw + warmup)
    total_attempts = len(raw) + len(warmup) + len(rejected)
    report = {
        "valid": True,
        "require_complete": require_complete,
        "frozen_topologies": len(topologies),
        "frozen_contexts": len(contexts),
        "planned_contexts": len(selected_contexts),
        "planned_runs": expected_runs,
        "completed_runs": len(done_files),
        "candidate_summaries": len(summaries),
        "accepted_cycles": len(raw),
        "warmup_cycles": len(warmup),
        "rejected_cycles": len(rejected),
        "attempt_coverage": (
            (len(raw) + len(warmup)) / total_attempts if total_attempts else 1.0
        ),
        "source_counter_audited_cycles": audited,
    }
    write_json_atomic(output_dir / "validation_report.json", report)
    return report
