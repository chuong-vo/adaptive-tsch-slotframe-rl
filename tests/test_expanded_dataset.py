from __future__ import annotations

from pathlib import Path

import networkx as nx

from experiments.topk_dataset import REPO_ROOT
from experiments.topk_dataset.csc import parse_csc, render_topology_csc
from experiments.topk_dataset.expanded_prepare import (
    freeze_expanded_plan,
    prepare_expanded_dataset,
)
from experiments.topk_dataset.expanded_protocol import (
    candidates_for_l0,
    context_protocol,
    load_expanded_protocol,
    topology_specs,
)
from experiments.topk_dataset.expanded_schema import validate_expanded_dataset
from experiments.topk_dataset.expanded_topology import build_frozen_topology
from experiments.topk_dataset.protocol import sha256_file
from experiments.topk_dataset.storage import aggregate_completed_runs
from experiments.topk_dataset.topology import geometric_graph


CONFIG = REPO_ROOT / "experiments" / "topk_dataset" / "config" / "expanded.json"


def test_expanded_matrix_follows_adviser_and_minh_requirements():
    protocol = load_expanded_protocol(CONFIG)
    specs = topology_specs(protocol)
    assert len(specs) == 57
    assert {spec["family"] for spec in specs} == {
        "chain", "grid", "random_geometric",
    }
    assert {spec["sink_placement"] for spec in specs} == {"center", "edge"}
    assert max(spec["node_count"] for spec in specs) == 32
    assert all(spec["node_count"] < 50 for spec in specs)
    assert sum(spec["split"] == "train" for spec in specs) == 30
    assert sum(spec["split"] == "validation" for spec in specs) == 15
    assert sum(spec["split"] == "test_interpolation" for spec in specs) == 6
    assert sum(spec["split"] == "test_scale" for spec in specs) == 6


def test_expanded_topologies_are_deterministic_connected_and_feasible():
    protocol = load_expanded_protocol(CONFIG)
    representatives = {}
    for spec in topology_specs(protocol):
        representatives.setdefault(spec["family"], spec)
    for spec in representatives.values():
        first = build_frozen_topology(protocol, spec)
        second = build_frozen_topology(protocol, spec)
        assert first["topology_id"] == second["topology_id"]
        assert first["cells"] == second["cells"]
        assert first["candidates"] == second["candidates"]
        assert nx.is_connected(geometric_graph(first["topology"]))
        if spec["family"] == "random_geometric":
            graph = first["graph"].to_undirected()
            assert nx.node_connectivity(graph) >= 2
            route_edges = {
                tuple(sorted((left, right)))
                for path in first["paths"].values()
                for left, right in zip(path, path[1:])
            }
            max_route_edge = max(
                graph.edges[edge]["distance"] for edge in route_edges
            )
            route_edge_limit = first["topology_row"]["routing_link_range"]
            assert max_route_edge <= route_edge_limit + 1e-9
        assert first["L0"] == spec["node_count"] - 1
        assert len(first["candidates"]) == 15
        assert first["candidates"] == sorted(set(first["candidates"]))
        assert min(first["candidates"]) >= first["L0"]
        assert max(first["candidates"]) <= 255


def test_candidate_domain_supports_largest_frozen_network():
    protocol = load_expanded_protocol(CONFIG)
    candidates = candidates_for_l0(protocol, 31)
    assert len(candidates) == 15
    assert candidates[0] >= 31
    assert candidates[-1] <= 255


def test_generated_csc_freezes_topology_radio_and_traffic(tmp_path):
    protocol = load_expanded_protocol(CONFIG)
    spec = next(
        spec for spec in topology_specs(protocol)
        if spec["family"] == "grid" and spec["node_count"] == 20
    )
    frozen = build_frozen_topology(protocol, spec)
    template = Path(protocol["template_csc"])
    template_hash = sha256_file(template)
    output = tmp_path / "generated.csc"
    render_topology_csc(
        template,
        output,
        nodes=frozen["nodes"],
        sink_id=1,
        title="test-expanded",
        transmission_range=50.0,
        interference_range=100.0,
        success_ratio_tx=0.8,
        success_ratio_rx=0.8,
        app_interval_seconds=5,
    )
    assert sha256_file(template) == template_hash
    parsed = parse_csc(output)
    assert len(parsed.nodes) == 20
    assert parsed.nodes[0].node_id == 1
    assert "sdn-tsch-sink" in parsed.nodes[0].mote_type
    assert parsed.success_ratio_tx == 0.8
    assert parsed.success_ratio_rx == 0.8
    contents = output.read_text(encoding="utf-8")
    assert "SDN_CONF_DATA_PACKET_INTERVAL=5" in contents
    assert "ORCHESTRA_CONF_UNICAST_PERIOD=20" in contents


def test_prepare_and_validate_empty_expanded_collection(tmp_path):
    protocol = load_expanded_protocol(CONFIG)
    contexts = prepare_expanded_dataset(protocol, tmp_path)
    assert len(contexts) == 114
    assert {context["profile_id"] for context in contexts} == {"normal", "stress"}
    assert all(
        context["processing_window_packets"] == 40 * context["node_count"]
        for context in contexts
    )
    stress = next(
        context for context in contexts
        if context["profile_id"] == "stress" and context["node_count"] == 20
    )
    runtime = context_protocol(protocol, context=stress)
    assert runtime["collection"]["processing_window"] == 800
    assert runtime["collection"]["control_flood_repetitions"] == 3
    assert stress["app_interval_ms"] == 10_000
    assert stress["success_ratio_tx"] == 1.0
    assert stress["success_ratio_rx"] == 1.0
    selected = contexts[:2]
    candidate_map = {
        context["context_id"]: [
            context["candidates"][0],
            context["candidates"][len(context["candidates"]) // 2],
            context["candidates"][-1],
        ]
        for context in selected
    }
    freeze_expanded_plan(
        tmp_path,
        context_ids=[context["context_id"] for context in selected],
        candidate_map=candidate_map,
        seeds=[1001],
        warmup_cycles=1,
        accepted_cycles=2,
        max_attempts_per_cycle=5,
        mode="smoke",
        port=60001,
    )
    aggregate_completed_runs(tmp_path)
    report = validate_expanded_dataset(tmp_path, require_complete=False)
    assert report["valid"] is True
    assert report["frozen_topologies"] == 57
    assert report["frozen_contexts"] == 114
    assert report["planned_contexts"] == 2
