"""Freeze expanded topology, context, CSC, and execution metadata."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import RUNNER_VERSION
from .expanded_protocol import topology_specs
from .expanded_topology import build_frozen_topology, render_context
from .prepare import source_provenance
from .protocol import sha256_file, sha256_json
from .storage import (
    CONTEXT_FIELDS,
    EDGE_FIELDS,
    NODE_FIELDS,
    TOPOLOGY_FIELDS,
    aggregate_completed_runs,
    write_csv_atomic,
    write_json_atomic,
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_expanded_dataset(
    protocol: dict[str, Any],
    output_dir: Path,
) -> list[dict[str, Any]]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    config_hash = sha256_json(protocol)
    source = source_provenance()
    manifest_path = output_dir / "manifest.json"
    if manifest_path.is_file():
        manifest = _read_json(manifest_path)
        checks = {
            "protocol_version": protocol["protocol_version"],
            "config_snapshot_sha256": config_hash,
            "template_csc_sha256": sha256_file(Path(protocol["template_csc"])),
            "source": source,
        }
        mismatches = [key for key, value in checks.items() if manifest.get(key) != value]
        if mismatches:
            raise RuntimeError(
                "Existing expanded manifest conflicts on: " + ", ".join(mismatches)
            )
        return _read_json(output_dir / "frozen_contexts.json")

    topology_rows = []
    node_rows = []
    edge_rows = []
    context_rows = []
    runtime_contexts = []
    schedules = {}
    for spec in topology_specs(protocol):
        frozen = build_frozen_topology(protocol, spec)
        topology_row = dict(frozen["topology_row"])
        first_csc = None
        for profile in protocol["profiles"]:
            context_row, runtime_context = render_context(
                protocol,
                frozen,
                profile,
                output_dir,
            )
            if first_csc is None:
                first_csc = runtime_context
            context_rows.append(context_row)
            runtime_contexts.append(runtime_context)
        topology_row["csc_path"] = first_csc["csc_path"]
        topology_row["csc_sha256"] = first_csc["csc_sha256"]
        topology_rows.append(topology_row)
        node_rows.extend(frozen["node_rows"])
        edge_rows.extend(frozen["edge_rows"])
        schedules[frozen["topology_id"]] = frozen["cells"]

    topology_ids = [row["topology_id"] for row in topology_rows]
    context_ids = [row["context_id"] for row in context_rows]
    if len(topology_ids) != len(set(topology_ids)):
        raise RuntimeError("Generated topology IDs are not unique")
    if len(context_ids) != len(set(context_ids)):
        raise RuntimeError("Generated context IDs are not unique")

    for row in context_rows:
        row["config_snapshot_sha256"] = config_hash
    write_json_atomic(output_dir / "config_snapshot.json", protocol)
    write_csv_atomic(output_dir / "topologies.csv", TOPOLOGY_FIELDS, topology_rows)
    write_csv_atomic(output_dir / "nodes.csv", NODE_FIELDS, node_rows)
    write_csv_atomic(output_dir / "edges.csv", EDGE_FIELDS, edge_rows)
    write_csv_atomic(output_dir / "contexts.csv", CONTEXT_FIELDS, context_rows)
    write_json_atomic(output_dir / "schedules.json", schedules)
    write_json_atomic(output_dir / "frozen_contexts.json", runtime_contexts)

    manifest = {
        "protocol_version": protocol["protocol_version"],
        "runner_version": RUNNER_VERSION,
        "dataset_group": protocol["dataset_group"],
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "topology_count": len(topology_rows),
        "context_count": len(context_rows),
        "topology_ids_sha256": sha256_json(sorted(topology_ids)),
        "context_ids_sha256": sha256_json(sorted(context_ids)),
        "config_snapshot_sha256": config_hash,
        "template_csc_sha256": sha256_file(Path(protocol["template_csc"])),
        "frozen_contexts_sha256": sha256_json(runtime_contexts),
        "schedules_sha256": sha256_json(schedules),
        "source": source,
    }
    manifest["manifest_sha256"] = sha256_json(manifest)
    write_json_atomic(manifest_path, manifest)
    aggregate_completed_runs(output_dir)
    return runtime_contexts


def freeze_expanded_plan(
    output_dir: Path,
    *,
    context_ids: list[str],
    candidate_map: dict[str, list[int]],
    seeds: list[int],
    warmup_cycles: int,
    accepted_cycles: int,
    max_attempts_per_cycle: int,
    mode: str,
    port: int,
) -> dict[str, Any]:
    plan = {
        "mode": mode,
        "context_ids": context_ids,
        "candidate_map": candidate_map,
        "seeds": [int(seed) for seed in seeds],
        "warmup_cycles": int(warmup_cycles),
        "accepted_cycles": int(accepted_cycles),
        "max_attempts_per_cycle": int(max_attempts_per_cycle),
        "port": int(port),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    comparable = {key: value for key, value in plan.items() if key != "created_at"}
    plan["execution_plan_sha256"] = sha256_json(comparable)
    path = output_dir / "execution_plan.json"
    if path.is_file():
        existing = _read_json(path)
        existing_comparable = {
            key: value for key, value in existing.items()
            if key not in {"created_at", "execution_plan_sha256"}
        }
        if existing_comparable != comparable:
            raise RuntimeError(
                "Expanded output is already frozen with another execution plan"
            )
        return existing
    write_json_atomic(path, plan)
    return plan
