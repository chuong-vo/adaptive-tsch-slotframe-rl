"""Configuration expansion for the adviser/Minh Anh dataset matrix."""

from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path
from typing import Any

from . import REPO_ROOT
from .protocol import deterministic_seed


class ExpandedProtocolError(ValueError):
    """Raised when the expanded collection matrix is ambiguous or unsafe."""


def load_expanded_protocol(path: Path) -> dict[str, Any]:
    protocol = json.loads(Path(path).read_text(encoding="utf-8"))
    if protocol.get("protocol_version") != "expanded-v1":
        raise ExpandedProtocolError("Expected protocol_version='expanded-v1'")
    template = Path(protocol["template_csc"])
    if not template.is_absolute():
        template = REPO_ROOT / template
    if not template.is_file():
        raise ExpandedProtocolError(f"Template CSC does not exist: {template}")
    protocol["template_csc"] = str(template.resolve())

    families = protocol["topology"]["families"]
    allowed_families = {"chain", "grid", "random_geometric"}
    if not families or set(families) != allowed_families:
        raise ExpandedProtocolError(
            "Expanded families must be chain, grid, and random_geometric"
        )
    seen_splits = set()
    for split in protocol["topology"]["splits"]:
        name = str(split["name"])
        if name in seen_splits:
            raise ExpandedProtocolError(f"Duplicate split: {name}")
        seen_splits.add(name)
        counts = [int(value) for value in split["node_counts"]]
        if not counts or min(counts) < 2 or max(counts) >= 50:
            raise ExpandedProtocolError("All node counts must be in [2, 49]")
        if len(counts) != len(set(counts)):
            raise ExpandedProtocolError(f"Duplicate node count in {name}")
        split["node_counts"] = counts
        if int(split["layout_instances"]) < 1:
            raise ExpandedProtocolError("layout_instances must be positive")
        placements = split["sink_placements"]
        if not placements or not set(placements).issubset(
            {"center", "edge", "alternate"}
        ):
            raise ExpandedProtocolError(f"Invalid sink placement in {name}")
    random_connectivity = int(
        protocol["topology"]["random_min_node_connectivity"]
    )
    if random_connectivity < 2:
        raise ExpandedProtocolError(
            "random_min_node_connectivity must be at least two"
        )
    route_edge_fraction = float(
        protocol["topology"]["random_max_route_edge_fraction"]
    )
    if not 0.0 < route_edge_fraction < 1.0:
        raise ExpandedProtocolError(
            "random_max_route_edge_fraction must be in (0, 1)"
        )

    profiles = protocol["profiles"]
    profile_ids = [str(profile["profile_id"]) for profile in profiles]
    if len(profile_ids) != len(set(profile_ids)) or not profile_ids:
        raise ExpandedProtocolError("Profile IDs must be non-empty and unique")
    for profile in profiles:
        if int(profile["app_interval_seconds"]) < 1:
            raise ExpandedProtocolError("Application intervals must be positive")
        for field in ("success_ratio_tx", "success_ratio_rx"):
            value = float(profile[field])
            if not 0.0 < value <= 1.0:
                raise ExpandedProtocolError(f"{field} must be in (0, 1]")

    collection = protocol["collection"]
    seeds = [int(value) for value in collection["cooja_seeds"]]
    if not seeds or len(seeds) != len(set(seeds)):
        raise ExpandedProtocolError("Cooja seeds must be non-empty and unique")
    collection["cooja_seeds"] = seeds
    for field in (
        "warmup_cycles", "accepted_cycles", "max_attempts_per_cycle",
        "processing_window_per_node", "control_flood_repetitions",
    ):
        if int(collection[field]) < 1:
            raise ExpandedProtocolError(f"collection.{field} must be positive")
    if float(collection["discovery_stability_seconds"]) <= 0:
        raise ExpandedProtocolError(
            "collection.discovery_stability_seconds must be positive"
        )

    slotframe = protocol["slotframe"]
    if int(slotframe["candidate_count"]) < 6:
        raise ExpandedProtocolError("Top-K collection needs at least six candidates")
    if float(slotframe["ratio_min"]) < 1.0:
        raise ExpandedProtocolError("ratio_min cannot be below one")
    if float(slotframe["ratio_max"]) <= float(slotframe["ratio_min"]):
        raise ExpandedProtocolError("ratio_max must exceed ratio_min")
    return protocol


def topology_specs(protocol: dict[str, Any]) -> list[dict[str, Any]]:
    specs = []
    families = protocol["topology"]["families"]
    for split_index, split in enumerate(protocol["topology"]["splits"]):
        for size_index, node_count in enumerate(split["node_counts"]):
            for family_index, family in enumerate(families):
                for layout_instance in range(int(split["layout_instances"])):
                    configured = split["sink_placements"]
                    if configured == ["alternate"]:
                        placements = [
                            "center"
                            if (split_index + size_index + family_index + layout_instance) % 2 == 0
                            else "edge"
                        ]
                    else:
                        placements = list(configured)
                    topology_seed = deterministic_seed(
                        protocol["protocol_version"], split["name"], family,
                        node_count, layout_instance, "topology",
                    ) % (2**31 - 1)
                    for placement in placements:
                        specs.append({
                            "split": split["name"],
                            "family": family,
                            "node_count": int(node_count),
                            "layout_instance": layout_instance,
                            "sink_placement": placement,
                            "topology_seed": topology_seed,
                        })
    return specs


def candidates_for_l0(protocol: dict[str, Any], l0: int) -> list[int]:
    slotframe = protocol["slotframe"]
    count = int(slotframe["candidate_count"])
    ratio_min = float(slotframe["ratio_min"])
    ratio_max = float(slotframe["ratio_max"])
    minimum_gap = max(1, math.ceil(float(slotframe["min_gap_fraction"]) * l0))
    factors = [int(value) for value in slotframe["coprime_with"]]
    wire_maximum = int(slotframe["wire_maximum"])
    candidates = []
    for index in range(count):
        fraction = index / (count - 1)
        ratio = ratio_min * (ratio_max / ratio_min) ** fraction
        candidate = max(
            int(l0),
            math.ceil(ratio * l0),
            candidates[-1] + minimum_gap if candidates else int(l0),
        )
        while any(math.gcd(candidate, factor) != 1 for factor in factors):
            candidate += 1
        if candidate > wire_maximum:
            raise ExpandedProtocolError(
                f"Cannot place {count} candidates for L0={l0} below {wire_maximum}"
            )
        candidates.append(candidate)
    if len(candidates) != len(set(candidates)):
        raise AssertionError("Candidate generation produced duplicates")
    return candidates


def context_protocol(
    protocol: dict[str, Any],
    *,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Build the G0-compatible runtime dictionary for one frozen context."""
    result = deepcopy(protocol)
    result["topology"] = {
        "family": context["topology_family"],
        "template_csc": context["csc_path"],
        "sink_id": 1,
        "expected_node_count": int(context["node_count"]),
        "topology_seed": int(context["topology_seed"]),
    }
    result["traffic"] = {
        "mode": context["traffic_mode"],
        "app_interval_ms": int(context["app_interval_ms"]),
    }
    result["radio"] = {
        "model": "UDGM",
        "transmission_range": float(context["transmission_range"]),
        "interference_range": float(context["interference_range"]),
        "success_ratio_tx": float(context["success_ratio_tx"]),
        "success_ratio_rx": float(context["success_ratio_rx"]),
    }
    result["collection"]["processing_window"] = int(
        context["processing_window_packets"]
    )
    result["slotframe"]["candidates"] = [int(value) for value in context["candidates"]]
    return result
