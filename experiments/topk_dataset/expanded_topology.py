"""Deterministic fixed-topology generation for expanded Top-K data."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np

from sdwsn_controller.tsch.contention_free_scheduler import (
    deterministic_cells,
    routing_links,
    schedule_sha256,
)

from .csc import CscNode, CscTopology, parse_csc, render_topology_csc
from .expanded_protocol import candidates_for_l0
from .protocol import canonical_json, deterministic_seed, sha256_bytes
from .topology import geometric_graph, routing_paths


SINK_SOURCE = "[CONTIKI_DIR]/examples/sdn-tsch-sink/sdn-tsch-sink.c"
NODE_SOURCE = "[CONTIKI_DIR]/examples/sdn-tsch-node/sdn-tsch-node.c"


def _point_graph(points: list[tuple[float, float]], radius: float) -> nx.Graph:
    graph = nx.Graph()
    graph.add_nodes_from(range(len(points)))
    for left in range(len(points)):
        for right in range(left + 1, len(points)):
            if math.dist(points[left], points[right]) <= radius + 1e-9:
                graph.add_edge(
                    left,
                    right,
                    distance=math.dist(points[left], points[right]),
                )
    return graph


def _jittered(
    points: list[tuple[float, float]],
    *,
    seed: int,
    jitter: float,
) -> list[tuple[float, float]]:
    rng = np.random.default_rng(seed)
    return [
        (
            float(x + rng.uniform(-jitter, jitter)),
            float(y + rng.uniform(-jitter, jitter)),
        )
        for x, y in points
    ]


def _chain_positions(spec: dict[str, Any], config: dict[str, Any]):
    spacing = float(config["chain_spacing"])
    points = [(index * spacing, 0.0) for index in range(spec["node_count"])]
    return _jittered(
        points,
        seed=spec["topology_seed"],
        jitter=float(config["jitter"]),
    ), 0, []


def _grid_positions(spec: dict[str, Any], config: dict[str, Any]):
    node_count = int(spec["node_count"])
    columns = math.ceil(math.sqrt(node_count))
    spacing = float(config["grid_spacing"])
    points = [
        ((index % columns) * spacing, (index // columns) * spacing)
        for index in range(node_count)
    ]
    return _jittered(
        points,
        seed=spec["topology_seed"],
        jitter=float(config["jitter"]),
    ), 0, []


def _random_positions(spec: dict[str, Any], config: dict[str, Any]):
    node_count = int(spec["node_count"])
    radius = float(config["transmission_range"])
    target_degree = float(config["random_target_degree"])
    minimum_connectivity = int(config["random_min_node_connectivity"])
    route_edge_limit = (
        float(config["random_max_route_edge_fraction"]) * radius
    )
    max_rerolls = int(config["random_max_rerolls"])
    side = math.sqrt(max(1.0, (node_count - 1) * math.pi * radius**2 / target_degree))
    reasons = []
    for attempt in range(max_rerolls + 1):
        rng = np.random.default_rng(
            deterministic_seed(spec["topology_seed"], attempt, "random-layout")
        )
        points = [
            (float(rng.uniform(0.0, side)), float(rng.uniform(0.0, side)))
            for _ in range(node_count)
        ]
        routing_graph = _point_graph(points, route_edge_limit)
        if not nx.is_connected(routing_graph):
            reasons.append("disconnected")
            continue
        if nx.node_connectivity(routing_graph) < minimum_connectivity:
            reasons.append("insufficient_node_connectivity")
            continue
        return points, attempt, reasons
    raise ValueError(
        f"Could not generate connected random topology after {max_rerolls} rerolls"
    )


def _select_sink(
    points: list[tuple[float, float]],
    placement: str,
) -> int:
    centroid = (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )
    distances = [math.dist(point, centroid) for point in points]
    if placement == "center":
        return min(range(len(points)), key=lambda index: (distances[index], index))
    if placement == "edge":
        return max(range(len(points)), key=lambda index: (distances[index], -index))
    raise ValueError(f"Unsupported sink placement: {placement}")


def _ordered_nodes(
    points: list[tuple[float, float]],
    *,
    sink_index: int,
) -> list[CscNode]:
    order = [sink_index] + [index for index in range(len(points)) if index != sink_index]
    return [
        CscNode(
            node_id=output_index + 1,
            x=points[source_index][0],
            y=points[source_index][1],
            z=0.0,
            mote_type=SINK_SOURCE if output_index == 0 else NODE_SOURCE,
        )
        for output_index, source_index in enumerate(order)
    ]


def _coords_hash(nodes: list[CscNode]) -> str:
    payload = [
        {
            "node_id": node.node_id,
            "is_sink": node.node_id == 1,
            "x": round(node.x, 9),
            "y": round(node.y, 9),
            "z": round(node.z, 9),
        }
        for node in nodes
    ]
    return sha256_bytes(canonical_json(payload).encode("ascii"))


def build_frozen_topology(
    protocol: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    config = protocol["topology"]
    generators = {
        "chain": _chain_positions,
        "grid": _grid_positions,
        "random_geometric": _random_positions,
    }
    points, reroll_count, reroll_reasons = generators[spec["family"]](spec, config)
    sink_index = _select_sink(points, spec["sink_placement"])
    nodes = _ordered_nodes(points, sink_index=sink_index)
    reference_profile = protocol["profiles"][0]
    topology = CscTopology(
        nodes=tuple(nodes),
        radio_model="UDGM",
        transmission_range=float(config["transmission_range"]),
        interference_range=float(config["interference_range"]),
        success_ratio_tx=float(reference_profile["success_ratio_tx"]),
        success_ratio_rx=float(reference_profile["success_ratio_rx"]),
    )
    graph = geometric_graph(topology)
    if not nx.is_connected(graph):
        raise ValueError(f"Generated {spec['family']} topology is disconnected")
    routing_link_range = (
        float(config["random_max_route_edge_fraction"])
        * topology.transmission_range
        if spec["family"] == "random_geometric"
        else topology.transmission_range
    )
    routing_graph = nx.Graph()
    routing_graph.add_nodes_from(graph.nodes(data=True))
    routing_graph.add_edges_from(
        (left, right, attrs)
        for left, right, attrs in graph.edges(data=True)
        if float(attrs["distance"]) <= routing_link_range + 1e-9
    )
    if not nx.is_connected(routing_graph):
        raise ValueError(f"Generated {spec['family']} routing graph is disconnected")
    paths = routing_paths(routing_graph, 1)
    links = routing_links(paths)
    if len(links) != int(spec["node_count"]) - 1:
        raise ValueError("Routing tree does not contain N-1 links")
    l0 = len(links)
    coords_hash = _coords_hash(nodes)
    topology_id = (
        f"exp_{spec['split']}_{spec['family']}_n{spec['node_count']}_"
        f"{spec['sink_placement']}_i{spec['layout_instance']}_{coords_hash[:12]}"
    )
    schedule_seed = deterministic_seed(topology_id, "schedule")
    cells = deterministic_cells(
        paths,
        schedule_seed,
        int(protocol["controller"]["max_channel"]),
    )
    candidates = candidates_for_l0(protocol, l0)
    degrees = dict(graph.degree())
    bridges = {tuple(sorted(edge)) for edge in nx.bridges(graph)}
    route_edges = {tuple(sorted(edge)) for edge in links}
    hops = {1: 0}
    hops.update({node_id: len(path) - 1 for node_id, path in paths.items()})
    betweenness = nx.betweenness_centrality(graph, normalized=True)
    clustering = nx.clustering(graph)
    frozen_at = datetime.now(timezone.utc).isoformat()
    xs = [node.x for node in nodes]
    ys = [node.y for node in nodes]

    topology_row = {
        "topology_id": topology_id,
        "coords_hash": coords_hash,
        "topology_family": spec["family"],
        "topology_seed": int(spec["topology_seed"]),
        "layout_instance": int(spec["layout_instance"]),
        "sink_placement": spec["sink_placement"],
        "dataset_group": protocol["dataset_group"],
        "split": spec["split"],
        "node_count": int(spec["node_count"]),
        "source_node_count": int(spec["node_count"]) - 1,
        "edge_count": graph.number_of_edges(),
        "average_degree": sum(degrees.values()) / len(nodes),
        "degree_std": float(np.std(list(degrees.values()), ddof=0)),
        "graph_density": nx.density(graph),
        "max_hops": max(hops.values()),
        "mean_hops_to_sink": sum(hops[node] for node in paths) / len(paths),
        "diameter": nx.diameter(graph),
        "sink_degree": degrees[1],
        "bridge_count": len(bridges),
        "area_width": max(xs) - min(xs),
        "area_height": max(ys) - min(ys),
        "transmission_range": topology.transmission_range,
        "interference_range": topology.interference_range,
        "routing_link_range": routing_link_range,
        "routing_edge_count": routing_graph.number_of_edges(),
        "routing_average_degree": (
            sum(dict(routing_graph.degree()).values()) / len(nodes)
        ),
        "reroll_count": reroll_count,
        "reroll_reasons": reroll_reasons,
        "connected": True,
        "csc_path": "",
        "csc_sha256": "",
        "manifest_frozen_at": frozen_at,
        "protocol_version": protocol["protocol_version"],
    }
    node_rows = [
        {
            "topology_id": topology_id,
            "node_id": node.node_id,
            "is_sink": node.node_id == 1,
            "x": node.x,
            "y": node.y,
            "z": node.z,
            "degree": degrees[node.node_id],
            "hops_to_sink": hops[node.node_id],
            "betweenness": betweenness[node.node_id],
            "clustering_coeff": clustering[node.node_id],
            "is_source": node.node_id != 1,
            "mote_type": node.mote_type,
        }
        for node in nodes
    ]
    edge_rows = [
        {
            "topology_id": topology_id,
            "u": min(left, right),
            "v": max(left, right),
            "distance": attrs["distance"],
            "in_routing_tree": tuple(sorted((left, right))) in route_edges,
            "expected_link_quality": "varies_by_context",
            "is_bridge": tuple(sorted((left, right))) in bridges,
        }
        for left, right, attrs in sorted(graph.edges(data=True))
    ]
    directed = nx.DiGraph()
    for node_id, attrs in routing_graph.nodes(data=True):
        directed.add_node(node_id, **attrs)
    for left, right, attrs in routing_graph.edges(data=True):
        directed.add_edge(
            left, right, weight=attrs["distance"], distance=attrs["distance"]
        )
        directed.add_edge(
            right, left, weight=attrs["distance"], distance=attrs["distance"]
        )
    return {
        "spec": spec,
        "topology": topology,
        "nodes": nodes,
        "graph": directed,
        "paths": paths,
        "cells": cells,
        "topology_id": topology_id,
        "schedule_seed": schedule_seed,
        "schedule_sha256": schedule_sha256(cells),
        "L0": l0,
        "candidates": candidates,
        "expected_source_ids": list(range(2, len(nodes) + 1)),
        "topology_row": topology_row,
        "node_rows": node_rows,
        "edge_rows": edge_rows,
        "frozen_at": frozen_at,
    }


def render_context(
    protocol: dict[str, Any],
    frozen: dict[str, Any],
    profile: dict[str, Any],
    output_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    context_id = f"{frozen['topology_id']}__{profile['profile_id']}"
    csc_path = output_dir / "generated_csc" / f"{context_id}.csc"
    csc_sha256 = render_topology_csc(
        Path(protocol["template_csc"]),
        csc_path,
        nodes=frozen["nodes"],
        sink_id=1,
        title=context_id,
        transmission_range=float(protocol["topology"]["transmission_range"]),
        interference_range=float(protocol["topology"]["interference_range"]),
        success_ratio_tx=float(profile["success_ratio_tx"]),
        success_ratio_rx=float(profile["success_ratio_rx"]),
        app_interval_seconds=int(profile["app_interval_seconds"]),
    )
    candidates = frozen["candidates"]
    context = {
        "context_id": context_id,
        "topology_id": frozen["topology_id"],
        "dataset_group": protocol["dataset_group"],
        "split": frozen["spec"]["split"],
        "profile_id": profile["profile_id"],
        "traffic_mode": profile["traffic_mode"],
        "app_interval_ms": int(profile["app_interval_seconds"]) * 1000,
        "aggregate_offered_load": (
            (int(frozen["spec"]["node_count"]) - 1)
            / int(profile["app_interval_seconds"])
        ),
        "radio_model": "UDGM",
        "success_ratio_tx": float(profile["success_ratio_tx"]),
        "success_ratio_rx": float(profile["success_ratio_rx"]),
        "interference_profile": profile["profile_id"],
        "routing_link_range": frozen["topology_row"]["routing_link_range"],
        "processing_window_packets": (
            int(protocol["collection"]["processing_window_per_node"])
            * int(frozen["spec"]["node_count"])
        ),
        "schedule_seed": frozen["schedule_seed"],
        "schedule_sha256": frozen["schedule_sha256"],
        "L0": frozen["L0"],
        "scheduled_link_count": len(frozen["cells"]),
        "candidate_count_M": len(candidates),
        "candidate_list_json": candidates,
        "r_min": min(candidates) / frozen["L0"],
        "r_max": max(candidates) / frozen["L0"],
        "min_gap": min(
            right - left for left, right in zip(candidates, candidates[1:])
        ),
        "frozen_at": frozen["frozen_at"],
        "config_snapshot_sha256": "",
    }
    runtime_record = {
        **context,
        "topology_family": frozen["spec"]["family"],
        "topology_seed": int(frozen["spec"]["topology_seed"]),
        "sink_placement": frozen["spec"]["sink_placement"],
        "layout_instance": int(frozen["spec"]["layout_instance"]),
        "node_count": int(frozen["spec"]["node_count"]),
        "transmission_range": float(protocol["topology"]["transmission_range"]),
        "interference_range": float(protocol["topology"]["interference_range"]),
        "routing_link_range": frozen["topology_row"]["routing_link_range"],
        "candidates": candidates,
        "csc_path": str(csc_path.resolve()),
        "csc_sha256": csc_sha256,
        "cells": frozen["cells"],
    }
    return context, runtime_record


def load_runtime_topology(context: dict[str, Any]) -> dict[str, Any]:
    topology = parse_csc(Path(context["csc_path"]))
    physical_graph = geometric_graph(topology)
    routing_link_range = float(context["routing_link_range"])
    graph = nx.Graph()
    graph.add_nodes_from(physical_graph.nodes(data=True))
    graph.add_edges_from(
        (left, right, attrs)
        for left, right, attrs in physical_graph.edges(data=True)
        if float(attrs["distance"]) <= routing_link_range + 1e-9
    )
    paths = routing_paths(graph, 1)
    cells = deterministic_cells(
        paths,
        int(context["schedule_seed"]),
        16,
    )
    if schedule_sha256(cells) != context["schedule_sha256"]:
        raise ValueError(f"Schedule changed for {context['context_id']}")
    directed = nx.DiGraph()
    for node_id, attrs in graph.nodes(data=True):
        directed.add_node(node_id, **attrs)
    for left, right, attrs in graph.edges(data=True):
        directed.add_edge(
            left, right, weight=attrs["distance"], distance=attrs["distance"]
        )
        directed.add_edge(
            right, left, weight=attrs["distance"], distance=attrs["distance"]
        )
    return {
        "topology": topology,
        "graph": directed,
        "paths": paths,
        "cells": cells,
        "topology_id": context["topology_id"],
        "context_id": context["context_id"],
        "schedule_seed": int(context["schedule_seed"]),
        "schedule_sha256": context["schedule_sha256"],
        "L0": int(context["L0"]),
        "expected_source_ids": list(range(2, int(context["node_count"]) + 1)),
    }
