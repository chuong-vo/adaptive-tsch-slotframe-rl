"""Freeze G0 metadata before any performance result is collected."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import REPO_ROOT, RUNNER_VERSION
from .protocol import sha256_bytes, sha256_file, sha256_json
from .storage import (
    CONTEXT_FIELDS,
    EDGE_FIELDS,
    NODE_FIELDS,
    TOPOLOGY_FIELDS,
    write_csv_atomic,
    write_json_atomic,
)
from .topology import prepare_topology


def _git_value(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
    ).strip()


def source_provenance() -> dict[str, Any]:
    status = _git_value("status", "--porcelain=v1")
    tracked_diff = subprocess.check_output(
        ["git", "diff", "--binary", "HEAD"],
        cwd=REPO_ROOT,
    )
    untracked_output = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=REPO_ROOT,
    )
    untracked_files = [
        Path(item.decode("utf-8"))
        for item in untracked_output.split(b"\0")
        if item
    ]
    untracked_manifest = [
        {
            "path": path.as_posix(),
            "sha256": sha256_file(REPO_ROOT / path),
        }
        for path in sorted(untracked_files)
        if (REPO_ROOT / path).is_file()
    ]
    snapshot = tracked_diff + json.dumps(
        untracked_manifest,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "commit": _git_value("rev-parse", "HEAD"),
        "branch": _git_value("branch", "--show-current"),
        "dirty": bool(status),
        "working_tree_sha256": sha256_bytes(snapshot),
        "untracked_files": untracked_manifest,
    }


def prepare_dataset(
    protocol: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    topology = prepare_topology(protocol)

    config_snapshot = json.loads(json.dumps(protocol))
    config_snapshot_sha256 = sha256_json(config_snapshot)
    topology["contexts_rows"][0]["config_snapshot_sha256"] = (
        config_snapshot_sha256
    )

    manifest = {
        "protocol_version": protocol["protocol_version"],
        "runner_version": RUNNER_VERSION,
        "dataset_group": protocol["dataset_group"],
        "split": protocol["split"],
        "frozen_at": topology["contexts_rows"][0]["frozen_at"],
        "topology_id": topology["topology_id"],
        "context_id": topology["context_id"],
        "coords_hash": topology["topologies_rows"][0]["coords_hash"],
        "schedule_seed": topology["schedule_seed"],
        "schedule_sha256": topology["schedule_sha256"],
        "L0": topology["L0"],
        "candidate_list": protocol["slotframe"]["candidates"],
        "cooja_seeds": protocol["collection"]["cooja_seeds"],
        "config_snapshot_sha256": config_snapshot_sha256,
        "template_csc_sha256": sha256_file(
            Path(protocol["topology"]["template_csc"])
        ),
        "source": source_provenance(),
    }
    manifest["manifest_sha256"] = sha256_json(manifest)

    manifest_path = output_dir / "manifest.json"
    if manifest_path.is_file():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        immutable_keys = (
            "protocol_version", "runner_version", "topology_id", "context_id", "coords_hash",
            "schedule_seed", "schedule_sha256", "L0", "candidate_list",
            "cooja_seeds", "config_snapshot_sha256", "template_csc_sha256",
            "source",
        )
        mismatches = [
            key for key in immutable_keys if existing.get(key) != manifest.get(key)
        ]
        if mismatches:
            raise RuntimeError(
                "Existing dataset manifest conflicts on: " + ", ".join(mismatches)
            )
        return topology

    write_json_atomic(output_dir / "config_snapshot.json", config_snapshot)
    write_csv_atomic(
        output_dir / "topologies.csv",
        TOPOLOGY_FIELDS,
        topology["topologies_rows"],
    )
    write_csv_atomic(output_dir / "nodes.csv", NODE_FIELDS, topology["nodes_rows"])
    write_csv_atomic(output_dir / "edges.csv", EDGE_FIELDS, topology["edges_rows"])
    write_csv_atomic(
        output_dir / "contexts.csv",
        CONTEXT_FIELDS,
        topology["contexts_rows"],
    )
    write_json_atomic(output_dir / "schedule.json", topology["cells"])
    write_json_atomic(manifest_path, manifest)
    return topology


def freeze_execution_plan(
    output_dir: Path,
    *,
    seeds: list[int],
    candidates: list[int],
    warmup_cycles: int,
    accepted_cycles: int,
    max_attempts_per_cycle: int,
    mode: str,
    port: int,
) -> dict[str, Any]:
    plan = {
        "mode": mode,
        "seeds": seeds,
        "candidates": candidates,
        "warmup_cycles": warmup_cycles,
        "accepted_cycles": accepted_cycles,
        "max_attempts_per_cycle": max_attempts_per_cycle,
        "port": int(port),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    comparable = {key: value for key, value in plan.items() if key != "created_at"}
    plan["execution_plan_sha256"] = sha256_json(comparable)
    path = output_dir / "execution_plan.json"
    if path.is_file():
        existing = json.loads(path.read_text(encoding="utf-8"))
        existing_comparable = {
            key: value for key, value in existing.items()
            if key not in {"created_at", "execution_plan_sha256"}
        }
        if existing_comparable != comparable:
            raise RuntimeError(
                "The output directory is already frozen with another execution plan"
            )
        return existing
    write_json_atomic(path, plan)
    return plan
