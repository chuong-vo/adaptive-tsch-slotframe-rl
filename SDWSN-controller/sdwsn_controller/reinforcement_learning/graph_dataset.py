"""Versioned storage for graph transitions collected from Cooja."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping

import numpy as np

from sdwsn_controller.reinforcement_learning.graph_observation import (
    EDGE_FEATURE_NAMES,
    GLOBAL_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    GraphObservation,
)


GRAPH_DATASET_SCHEMA_VERSION = 1
GRAPH_DATASET_FILENAME = "graph_transitions.jsonl.gz"
GRAPH_DATASET_SUMMARY_FILENAME = "graph_transitions_summary.json"


def _graph_to_dict(graph: GraphObservation) -> Dict[str, Any]:
    if not isinstance(graph, GraphObservation):
        raise TypeError("graph must be a GraphObservation")
    return {
        "node_ids": graph.node_ids.tolist(),
        "node_features": graph.node_features.tolist(),
        "edge_index": graph.edge_index.tolist(),
        "edge_features": graph.edge_features.tolist(),
        "global_features": graph.global_features.tolist(),
    }


def _graph_from_dict(value: Any) -> GraphObservation:
    if not isinstance(value, dict):
        raise ValueError("graph value must be an object")
    required = {
        "node_ids",
        "node_features",
        "edge_index",
        "edge_features",
        "global_features",
    }
    missing = required.difference(value)
    if missing:
        raise ValueError(f"graph value is missing keys: {sorted(missing)}")

    node_ids = np.asarray(value["node_ids"], dtype=np.int64)
    if node_ids.size == 0:
        raise ValueError("graph must contain at least one node")
    return GraphObservation(
        node_ids=node_ids,
        node_features=np.asarray(value["node_features"], dtype=np.float32),
        edge_index=np.asarray(value["edge_index"], dtype=np.int64),
        edge_features=np.asarray(value["edge_features"], dtype=np.float32),
        global_features=np.asarray(
            value["global_features"],
            dtype=np.float32,
        ),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class GraphTransitionDatasetWriter:
    """Stream graph transitions and publish the dataset atomically."""

    def __init__(
        self,
        output_dir: str | os.PathLike,
        seed: int | None,
        collection_metadata: Mapping[str, Any],
    ) -> None:
        if not isinstance(collection_metadata, Mapping):
            raise TypeError("collection_metadata must be a mapping")
        try:
            metadata_json = json.dumps(
                dict(collection_metadata),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "collection_metadata must be JSON serializable"
            ) from exc
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.seed = seed
        self.collection_metadata = json.loads(metadata_json)
        self.dataset_path = self.output_dir / GRAPH_DATASET_FILENAME
        self.summary_path = self.output_dir / GRAPH_DATASET_SUMMARY_FILENAME
        self.part_path = self.dataset_path.with_suffix(
            self.dataset_path.suffix + ".part"
        )
        self.summary_part_path = self.summary_path.with_suffix(
            self.summary_path.suffix + ".part"
        )
        self._stream = None
        self._record_count = 0
        self._valid_count = 0
        self._first_cycle = None
        self._last_cycle = 0
        self._action_counts = Counter()
        self._slotframe_counts = Counter()
        self._profile_counts = Counter()

    def __enter__(self) -> "GraphTransitionDatasetWriter":
        if self._stream is not None:
            raise RuntimeError("graph dataset writer is already open")
        self.part_path.unlink(missing_ok=True)
        self.summary_part_path.unlink(missing_ok=True)
        self._stream = gzip.open(
            self.part_path,
            mode="wt",
            encoding="utf-8",
            newline="\n",
        )
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close(commit=exc_type is None)

    def write_transition(
        self,
        *,
        cycle_idx: int,
        action: int,
        returned_reward: float,
        valid_cycle: bool,
        before: GraphObservation,
        after: GraphObservation,
        applied_action: int | None = None,
        requested_sf_len: int | None = None,
        applied_sf_len: int | None = None,
        environment_reward: float | None = None,
        profile: str | None = None,
        terminated: bool = False,
        truncated: bool = False,
        wait_timeout: bool = False,
        wait_attempts: int = 0,
    ) -> None:
        if self._stream is None:
            raise RuntimeError("graph dataset writer is not open")
        if isinstance(cycle_idx, bool) or not isinstance(cycle_idx, int):
            raise TypeError("cycle_idx must be an integer")
        if cycle_idx <= self._last_cycle:
            raise ValueError("cycle_idx must increase strictly")
        if action not in (0, 1, 2):
            raise ValueError("action must be 0, 1, or 2")
        if applied_action is not None and applied_action not in (0, 1, 2):
            raise ValueError("applied_action must be 0, 1, 2, or None")
        returned_reward = float(returned_reward)
        if not np.isfinite(returned_reward):
            raise ValueError("returned_reward must be finite")
        if environment_reward is not None:
            environment_reward = float(environment_reward)
            if not np.isfinite(environment_reward):
                raise ValueError("environment_reward must be finite")
        for name, value in (
            ("requested_sf_len", requested_sf_len),
            ("applied_sf_len", applied_sf_len),
        ):
            if value is not None:
                if isinstance(value, bool):
                    raise TypeError(f"{name} must be an integer or None")
                try:
                    value = int(value)
                except (TypeError, ValueError) as exc:
                    raise TypeError(
                        f"{name} must be an integer or None"
                    ) from exc
                if name == "requested_sf_len":
                    requested_sf_len = value
                else:
                    applied_sf_len = value
        if profile is not None:
            profile = str(profile)

        record = {
            "schema_version": GRAPH_DATASET_SCHEMA_VERSION,
            "seed": self.seed,
            "cycle_idx": cycle_idx,
            "action": int(action),
            "applied_action": (
                int(applied_action) if applied_action is not None else None
            ),
            "requested_sf_len": requested_sf_len,
            "applied_sf_len": applied_sf_len,
            "returned_reward": returned_reward,
            "environment_reward": environment_reward,
            "profile": profile,
            "terminated": bool(terminated),
            "truncated": bool(truncated),
            "wait_timeout": bool(wait_timeout),
            "wait_attempts": int(wait_attempts),
            "valid_cycle": bool(valid_cycle),
            "before": _graph_to_dict(before),
            "after": _graph_to_dict(after),
        }
        line = json.dumps(
            record,
            allow_nan=False,
            separators=(",", ":"),
        )
        self._stream.write(line + "\n")
        self._stream.flush()

        self._record_count += 1
        self._valid_count += int(valid_cycle)
        if self._first_cycle is None:
            self._first_cycle = cycle_idx
        self._last_cycle = cycle_idx
        self._action_counts[str(action)] += 1
        if applied_sf_len is not None:
            self._slotframe_counts[str(int(applied_sf_len))] += 1
        if profile is not None:
            self._profile_counts[str(profile)] += 1

    def close(self, commit: bool) -> None:
        if self._stream is None:
            return
        self._stream.close()
        self._stream = None

        if not commit:
            self.part_path.unlink(missing_ok=True)
            return
        if self._record_count == 0:
            self.part_path.unlink(missing_ok=True)
            raise RuntimeError("refusing to publish an empty graph dataset")

        os.replace(self.part_path, self.dataset_path)
        summary = {
            "schema_version": GRAPH_DATASET_SCHEMA_VERSION,
            "seed": self.seed,
            "records": self._record_count,
            "valid_records": self._valid_count,
            "invalid_records": self._record_count - self._valid_count,
            "first_cycle": self._first_cycle,
            "last_cycle": self._last_cycle,
            "action_counts": dict(sorted(self._action_counts.items())),
            "slotframe_counts": dict(
                sorted(
                    self._slotframe_counts.items(),
                    key=lambda item: int(item[0]),
                )
            ),
            "profile_counts": dict(sorted(self._profile_counts.items())),
            "collection_metadata": self.collection_metadata,
            "node_feature_names": list(NODE_FEATURE_NAMES),
            "edge_feature_names": list(EDGE_FEATURE_NAMES),
            "global_feature_names": list(GLOBAL_FEATURE_NAMES),
            "dataset_file": self.dataset_path.name,
            "sha256": _sha256(self.dataset_path),
        }
        self.summary_part_path.write_text(
            json.dumps(summary, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(self.summary_part_path, self.summary_path)


def iter_graph_transitions(
    dataset_path: str | os.PathLike,
) -> Iterator[Dict[str, Any]]:
    """Yield validated transition records from a compressed dataset."""
    path = Path(dataset_path)
    with gzip.open(path, mode="rt", encoding="utf-8") as stream:
        last_cycle = 0
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid JSON at line {line_number}: {exc}"
                ) from exc
            if not isinstance(record, dict):
                raise ValueError(f"line {line_number} must contain an object")
            if record.get("schema_version") != GRAPH_DATASET_SCHEMA_VERSION:
                raise ValueError(
                    f"unsupported schema version at line {line_number}"
                )
            cycle_idx = record.get("cycle_idx")
            if (
                isinstance(cycle_idx, bool)
                or not isinstance(cycle_idx, int)
                or cycle_idx <= last_cycle
            ):
                raise ValueError(
                    f"non-increasing cycle_idx at line {line_number}"
                )
            action = record.get("action")
            if action not in (0, 1, 2):
                raise ValueError(f"invalid action at line {line_number}")
            reward = record.get("returned_reward")
            if not isinstance(reward, (int, float)) or not np.isfinite(reward):
                raise ValueError(f"invalid reward at line {line_number}")
            if not isinstance(record.get("valid_cycle"), bool):
                raise ValueError(
                    f"invalid valid_cycle flag at line {line_number}"
                )

            record["before"] = _graph_from_dict(record.get("before"))
            record["after"] = _graph_from_dict(record.get("after"))
            last_cycle = cycle_idx
            yield record


def graph_dataset_completion_issue(
    output_dir: str | os.PathLike,
    min_valid_records: int = 1,
) -> str | None:
    """Return why a graph dataset is incomplete, or ``None`` when valid."""
    output_dir = Path(output_dir)
    dataset_path = output_dir / GRAPH_DATASET_FILENAME
    summary_path = output_dir / GRAPH_DATASET_SUMMARY_FILENAME
    missing = [
        path.name
        for path in (dataset_path, summary_path)
        if not path.is_file()
    ]
    if missing:
        return f"missing graph files: {', '.join(missing)}"

    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"unreadable graph summary: {exc}"
    if not isinstance(summary, dict):
        return "graph summary must contain an object"
    if summary.get("schema_version") != GRAPH_DATASET_SCHEMA_VERSION:
        return "unsupported graph dataset schema version"
    try:
        checksum = _sha256(dataset_path)
    except OSError as exc:
        return f"unreadable graph dataset: {exc}"
    if summary.get("sha256") != checksum:
        return "graph dataset checksum mismatch"

    try:
        record_count = 0
        valid_records = 0
        first_cycle = None
        last_cycle = None
        action_counts = Counter()
        slotframe_counts = Counter()
        profile_counts = Counter()
        for record in iter_graph_transitions(dataset_path):
            record_count += 1
            valid_records += int(bool(record.get("valid_cycle")))
            if first_cycle is None:
                first_cycle = record["cycle_idx"]
            last_cycle = record["cycle_idx"]
            action_counts[str(record["action"])] += 1
            if record.get("applied_sf_len") is not None:
                slotframe_counts[str(int(record["applied_sf_len"]))] += 1
            if record.get("profile") is not None:
                profile_counts[str(record["profile"])] += 1
    except (OSError, EOFError, UnicodeError, ValueError) as exc:
        return f"invalid graph dataset: {exc}"
    if summary.get("records") != record_count:
        return "graph dataset record count does not match summary"
    if summary.get("valid_records") != valid_records:
        return "graph dataset valid count does not match summary"
    if summary.get("invalid_records") != record_count - valid_records:
        return "graph dataset invalid count does not match summary"
    if summary.get("first_cycle") != first_cycle:
        return "graph dataset first cycle does not match summary"
    if summary.get("last_cycle") != last_cycle:
        return "graph dataset last cycle does not match summary"
    if summary.get("action_counts") != dict(sorted(action_counts.items())):
        return "graph dataset action counts do not match summary"
    expected_slotframes = dict(
        sorted(slotframe_counts.items(), key=lambda item: int(item[0]))
    )
    if summary.get("slotframe_counts") != expected_slotframes:
        return "graph dataset slotframe counts do not match summary"
    if summary.get("profile_counts") != dict(sorted(profile_counts.items())):
        return "graph dataset profile counts do not match summary"
    expected_schemas = {
        "node_feature_names": list(NODE_FEATURE_NAMES),
        "edge_feature_names": list(EDGE_FEATURE_NAMES),
        "global_feature_names": list(GLOBAL_FEATURE_NAMES),
    }
    for key, expected in expected_schemas.items():
        if summary.get(key) != expected:
            return f"graph dataset {key} does not match code schema"
    if not isinstance(summary.get("collection_metadata"), dict):
        return "graph dataset collection_metadata must contain an object"
    if valid_records < min_valid_records:
        return (
            f"graph valid_records={valid_records} < "
            f"{min_valid_records}"
        )
    return None
