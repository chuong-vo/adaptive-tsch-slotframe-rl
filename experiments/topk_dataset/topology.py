"""Build frozen G0 topology, graph, routing, and schedule metadata."""

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

from .csc import CscTopology, parse_csc
from .protocol import canonical_json, deterministic_seed, sha256_bytes, sha256_file


def geometric_graph(topology: CscTopology) -> nx.Graph:
    graph = nx.Graph()
    for node in topology.nodes:
        graph.add_node(node.node_id, x=node.x, y=node.y, z=node.z)
    for index, left in enumerate(topology.nodes):
        for right in topology.nodes[index + 1:]:
            distance = math.dist(
                (left.x, left.y, left.z),
                (right.x, right.y, right.z),
            )
            if distance <= topology.transmission_range + 1e-9:
                graph.add_edge(left.node_id, right.node_id, distance=distance)
    return graph


def routing_paths(graph: nx.Graph, sink_id: int) -> dict[int, list[int]]:
    if sink_id not in graph:
        raise ValueError(f"Sink {sink_id} is not in the topology")
    if not nx.is_connected(graph):
        raise ValueError("The frozen geometric topology is not connected")
    directed = nx.DiGraph()
    for node_id, attrs in sorted(graph.nodes(data=True)):
        directed.add_node(node_id, **attrs)
    for left, right, attrs in sorted(graph.edges(data=True)):
        directed.add_edge(left, right, weight=attrs["distance"])
        directed.add_edge(right, left, weight=attrs["distance"])
    return {
        node_id: nx.dijkstra_path(directed, node_id, sink_id, weight="weight")
        for node_id in sorted(directed.nodes)
        if node_id != sink_id
    }


def _coords_hash(topology: CscTopology, sink_id: int) -> str:
    payload = [
        {
            "node_id": node.node_id,
            "is_sink": node.node_id == sink_id,
            "mote_type": node.mote_type,
            "x": round(node.x, 9),
            "y": round(node.y, 9),
            "z": round(node.z, 9),
        }
        for node in topology.nodes
    ]
    return sha256_bytes(canonical_json(payload).encode("ascii"))


def prepare_topology(protocol: dict[str, Any]) -> dict[str, Any]:
    topology_config = protocol["topology"]
    template = Path(topology_config["template_csc"])
    topology = parse_csc(template)
    sink_id = int(topology_config["sink_id"])
    expected_nodes = int(topology_config["expected_node_count"])
    if len(topology.nodes) != expected_nodes:
        raise ValueError(
            f"CSC has {len(topology.nodes)} motes; expected {expected_nodes}"
        )

    radio = protocol["radio"]
    observed_radio = (
        topology.transmission_range,
        topology.interference_range,
        topology.success_ratio_tx,
        topology.success_ratio_rx,
    )
    configured_radio = (
        float(radio["transmission_range"]),
        float(radio["interference_range"]),
        float(radio["success_ratio_tx"]),
        float(radio["success_ratio_rx"]),
    )
    if observed_radio != configured_radio:
        raise ValueError(
            f"CSC radio parameters {observed_radio} do not match protocol "
            f"{configured_radio}"
        )
    if topology.radio_model != str(radio["model"]):
        raise ValueError(
            f"CSC radio model {topology.radio_model!r} does not match protocol "
            f"{radio['model']!r}"
        )

    graph = geometric_graph(topology)
    paths = routing_paths(graph, sink_id)
    coords_hash = _coords_hash(topology, sink_id)
    topology_id = (
        f"g0_{topology_config['family']}_n{expected_nodes}_sink{sink_id}_"
        f"{coords_hash[:16]}"
    )
    schedule_seed = deterministic_seed(topology_id, "schedule")
    cells = deterministic_cells(
        paths,
        schedule_seed,
        int(protocol["controller"]["max_channel"]),
    )
    links = routing_links(paths)
    if len(links) != expected_nodes - 1:
        raise ValueError(
            f"Expected a {expected_nodes - 1}-edge routing tree, got {len(links)}"
        )
    l0 = len(links)
    candidates = protocol["slotframe"]["candidates"]
    if min(candidates) < l0:
        raise ValueError(f"Candidate {min(candidates)} is below L0={l0}")

    hops = {sink_id: 0}
    hops.update({node_id: len(path) - 1 for node_id, path in paths.items()})
    degrees = dict(graph.degree())
    bridges = {tuple(sorted(edge)) for edge in nx.bridges(graph)}
    route_edges = {tuple(sorted(edge)) for edge in links}
    betweenness = nx.betweenness_centrality(graph, normalized=True)
    clustering = nx.clustering(graph)
    positions = {node.node_id: node for node in topology.nodes}
    xs = [node.x for node in topology.nodes]
    ys = [node.y for node in topology.nodes]

    frozen_at = datetime.now(timezone.utc).isoformat()
    topologies_row = {
        "topology_id": topology_id,
        "coords_hash": coords_hash,
        "topology_family": topology_config["family"],
        "topology_seed": int(topology_config["topology_seed"]),
        "sink_placement": "edge",
        "dataset_group": protocol["dataset_group"],
        "split": protocol["split"],
        "node_count": expected_nodes,
        "source_node_count": expected_nodes - 1,
        "edge_count": graph.number_of_edges(),
        "average_degree": sum(degrees.values()) / expected_nodes,
        "degree_std": float(np.std(list(degrees.values()), ddof=0)),
        "graph_density": nx.density(graph),
        "max_hops": max(hops.values()),
        "mean_hops_to_sink": sum(hops[node] for node in paths) / len(paths),
        "diameter": nx.diameter(graph),
        "sink_degree": degrees[sink_id],
        "bridge_count": len(bridges),
        "area_width": max(xs) - min(xs),
        "area_height": max(ys) - min(ys),
        "transmission_range": topology.transmission_range,
        "interference_range": topology.interference_range,
        "routing_link_range": topology.transmission_range,
        "routing_edge_count": graph.number_of_edges(),
        "routing_average_degree": sum(degrees.values()) / expected_nodes,
        "reroll_count": 0,
        "reroll_reasons": "[]",
        "connected": True,
        "csc_path": str(template),
        "csc_sha256": sha256_file(template),
        "manifest_frozen_at": frozen_at,
        "protocol_version": protocol["protocol_version"],
    }

    node_rows = []
    for node in topology.nodes:
        node_rows.append({
            "topology_id": topology_id,
            "node_id": node.node_id,
            "is_sink": node.node_id == sink_id,
            "x": node.x,
            "y": node.y,
            "z": node.z,
            "degree": degrees[node.node_id],
            "hops_to_sink": hops[node.node_id],
            "betweenness": betweenness[node.node_id],
            "clustering_coeff": clustering[node.node_id],
            "is_source": node.node_id != sink_id,
            "mote_type": node.mote_type,
        })

    edge_rows = []
    for left, right, attrs in sorted(graph.edges(data=True)):
        edge = tuple(sorted((left, right)))
        edge_rows.append({
            "topology_id": topology_id,
            "u": edge[0],
            "v": edge[1],
            "distance": attrs["distance"],
            "in_routing_tree": edge in route_edges,
            "expected_link_quality": (
                topology.success_ratio_tx * topology.success_ratio_rx
            ),
            "is_bridge": edge in bridges,
        })

    context_id = f"{topology_id}_normal_periodic"
    context_row = {
        "context_id": context_id,
        "topology_id": topology_id,
        "dataset_group": protocol["dataset_group"],
        "split": protocol["split"],
        "traffic_mode": protocol["traffic"]["mode"],
        "app_interval_ms": int(protocol["traffic"]["app_interval_ms"]),
        "aggregate_offered_load": (expected_nodes - 1) * 1000.0 /
        int(protocol["traffic"]["app_interval_ms"]),
        "radio_model": topology.radio_model,
        "success_ratio_tx": topology.success_ratio_tx,
        "success_ratio_rx": topology.success_ratio_rx,
        "interference_profile": "UDGM-default",
        "routing_link_range": topology.transmission_range,
        "schedule_seed": schedule_seed,
        "schedule_sha256": schedule_sha256(cells),
        "L0": l0,
        "scheduled_link_count": len(cells),
        "candidate_count_M": len(candidates),
        "candidate_list_json": json.dumps(candidates, separators=(",", ":")),
        "r_min": min(candidates) / l0,
        "r_max": max(candidates) / l0,
        "min_gap": min(
            right - left for left, right in zip(candidates, candidates[1:])
        ),
        "frozen_at": frozen_at,
        "config_snapshot_sha256": "",
    }

    directed_graph = nx.DiGraph()
    for node_id, attrs in graph.nodes(data=True):
        directed_graph.add_node(node_id, **attrs)
    for left, right, attrs in graph.edges(data=True):
        directed_graph.add_edge(left, right, weight=attrs["distance"])
        directed_graph.add_edge(right, left, weight=attrs["distance"])

    return {
        "topology": topology,
        "graph": directed_graph,
        "paths": paths,
        "cells": cells,
        "topology_id": topology_id,
        "context_id": context_id,
        "schedule_seed": schedule_seed,
        "schedule_sha256": schedule_sha256(cells),
        "L0": l0,
        "expected_source_ids": [
            node.node_id for node in topology.nodes if node.node_id != sink_id
        ],
        "topologies_rows": [topologies_row],
        "nodes_rows": node_rows,
        "edges_rows": edge_rows,
        "contexts_rows": [context_row],
        "positions": positions,
    }
