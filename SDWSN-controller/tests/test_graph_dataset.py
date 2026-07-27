import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from sdwsn_controller.node.node import Node
from sdwsn_controller.reinforcement_learning.graph_dataset import (
    GRAPH_DATASET_FILENAME,
    GRAPH_DATASET_SUMMARY_FILENAME,
    GraphTransitionDatasetWriter,
    graph_dataset_completion_issue,
    iter_graph_transitions,
)
from sdwsn_controller.reinforcement_learning.graph_observation import (
    EDGE_FEATURE_NAMES,
    GLOBAL_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    GraphObservation,
    GraphObservationBuilder,
)


def make_graph(slotframe=10, energy=0.2):
    node_features = np.zeros((2, len(NODE_FEATURE_NAMES)), dtype=np.float32)
    node_features[0, 0] = 1.0
    node_features[1, 4] = energy
    edge_features = np.zeros((1, len(EDGE_FEATURE_NAMES)), dtype=np.float32)
    edge_features[0, :4] = (0.4, 1.0, 1.0, 1.0)
    return GraphObservation(
        node_ids=np.asarray([1, 2], dtype=np.int64),
        node_features=node_features,
        edge_index=np.asarray([[1], [0]], dtype=np.int64),
        edge_features=edge_features,
        global_features=np.asarray(
            [0.4, 0.3, 0.3, slotframe / 70.0, 0.1],
            dtype=np.float32,
        ),
    )


def write_transition(writer, cycle_idx, valid_cycle=True):
    writer.write_transition(
        cycle_idx=cycle_idx,
        action=0,
        applied_action=0,
        requested_sf_len=11,
        applied_sf_len=11,
        returned_reward=2.1,
        environment_reward=2.1,
        profile="balanced",
        valid_cycle=valid_cycle,
        before=make_graph(slotframe=10, energy=0.2),
        after=make_graph(slotframe=11, energy=0.4),
    )


def make_writer(output_dir, seed=7):
    builder = GraphObservationBuilder(max_slotframe_size=70)
    return GraphTransitionDatasetWriter(
        output_dir,
        seed=seed,
        collection_metadata=builder.normalization_metadata(),
    )


def load_approximation_module():
    script = (
        Path(__file__).resolve().parents[1]
        / "tutorials"
        / "reinforcement-learning"
        / "approximation_model_cooja.py"
    )
    spec = importlib.util.spec_from_file_location(
        "approximation_model_cooja_for_test",
        script,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeNetwork:
    def __init__(self):
        sink = Node(1, sid=None, rank=0)
        sensor = Node(2, sid=None, rank=1)
        sensor.neighbor_add(1, rssi=-60, etx=128)
        sensor.energy_add(seq=1, energy=1000)
        self.nodes = {1: sink, 2: sensor}
        self.tsch_slotframe_size = 10

    def tsch_last_ts(self):
        return 7


class FakeController:
    def __init__(self):
        self.network = FakeNetwork()
        self.user_requirements = (0.4, 0.3, 0.3)

    def get_state(self):
        alpha, beta, delta = self.user_requirements
        return {
            "user_requirements": self.user_requirements,
            "alpha": alpha,
            "beta": beta,
            "delta": delta,
            "current_sf_len": self.network.tsch_slotframe_size,
            "last_ts_in_schedule": self.network.tsch_last_ts(),
        }


class OneCycleEnv:
    max_slotframe_size = 70

    def __init__(self, controller):
        self.controller = controller
        self.seen_actions = []

    def reset(self):
        return np.ones(8, dtype=np.float32), {}

    def step(self, action):
        self.seen_actions.append(action)
        self.controller.network.tsch_slotframe_size = 11
        self.controller.network.nodes[2].energy_add(seq=2, energy=2000)
        info = {
            "reward": 2.1,
            "power_normalized": 0.4,
            "delay_normalized": 0.1,
            "pdr_mean": 1.0,
            "current_sf_len": 11,
            "applied_action": action,
            "requested_sf_len": 11,
            "applied_sf_len": 11,
            "valid_cycle": True,
            "wait_timeout": False,
            "wait_attempts": 0,
        }
        return np.ones(8, dtype=np.float32), 2.1, False, True, info


def test_graph_dataset_round_trip_and_summary(tmp_path):
    with make_writer(tmp_path) as writer:
        write_transition(writer, cycle_idx=1, valid_cycle=True)
        write_transition(writer, cycle_idx=2, valid_cycle=False)

    assert graph_dataset_completion_issue(tmp_path) is None
    records = list(iter_graph_transitions(tmp_path / GRAPH_DATASET_FILENAME))
    assert len(records) == 2
    assert isinstance(records[0]["before"], GraphObservation)
    assert records[0]["before"].global_features[3] == pytest.approx(10 / 70)
    assert records[0]["after"].global_features[3] == pytest.approx(11 / 70)

    summary = json.loads(
        (tmp_path / GRAPH_DATASET_SUMMARY_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    assert summary["records"] == 2
    assert summary["valid_records"] == 1
    assert summary["invalid_records"] == 1
    assert summary["action_counts"] == {"0": 2}
    assert summary["collection_metadata"]["max_slotframe_size"] == 70
    assert summary["collection_metadata"]["etx_divisor"] == 128


def test_writer_rejects_non_increasing_cycles(tmp_path):
    with pytest.raises(ValueError, match="increase strictly"):
        with make_writer(tmp_path) as writer:
            write_transition(writer, cycle_idx=1)
            write_transition(writer, cycle_idx=1)

    assert not (tmp_path / GRAPH_DATASET_FILENAME).exists()
    assert not (tmp_path / GRAPH_DATASET_SUMMARY_FILENAME).exists()


def test_failed_rerun_preserves_previous_complete_dataset(tmp_path):
    with make_writer(tmp_path) as writer:
        write_transition(writer, cycle_idx=1)
    dataset_path = tmp_path / GRAPH_DATASET_FILENAME
    summary_path = tmp_path / GRAPH_DATASET_SUMMARY_FILENAME
    original_dataset = dataset_path.read_bytes()
    original_summary = summary_path.read_bytes()

    with pytest.raises(RuntimeError, match="stop rerun"):
        with make_writer(tmp_path) as writer:
            write_transition(writer, cycle_idx=1)
            raise RuntimeError("stop rerun")

    assert dataset_path.read_bytes() == original_dataset
    assert summary_path.read_bytes() == original_summary
    assert graph_dataset_completion_issue(tmp_path) is None


def test_checksum_mismatch_is_rejected(tmp_path):
    with make_writer(tmp_path) as writer:
        write_transition(writer, cycle_idx=1)

    summary_path = tmp_path / GRAPH_DATASET_SUMMARY_FILENAME
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["sha256"] = "invalid"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    assert graph_dataset_completion_issue(tmp_path) == (
        "graph dataset checksum mismatch"
    )


def test_trend_loop_records_before_and_after_same_action(tmp_path, monkeypatch):
    approximation = load_approximation_module()
    controller = FakeController()
    env = OneCycleEnv(controller)
    builder = GraphObservationBuilder(max_slotframe_size=70)
    monkeypatch.setenv("ELISE_TREND_MAX_CYCLES", "0")
    monkeypatch.setenv("ELISE_COOJA_SEED", "7")

    with GraphTransitionDatasetWriter(
        tmp_path,
        seed=7,
        collection_metadata=builder.normalization_metadata(),
    ) as writer:
        approximation.run(
            env,
            controller,
            str(tmp_path),
            "example",
            seed=7,
            graph_builder=builder,
            graph_writer=writer,
        )

    records = list(iter_graph_transitions(tmp_path / GRAPH_DATASET_FILENAME))
    assert env.seen_actions == [0]
    assert len(records) == 1
    transition = records[0]
    assert transition["action"] == 0
    assert transition["returned_reward"] == pytest.approx(2.1)
    assert transition["valid_cycle"] is True
    assert transition["before"].global_features[3] == pytest.approx(10 / 70)
    assert transition["after"].global_features[3] == pytest.approx(11 / 70)
    assert transition["before"].node_features[1, 4] == pytest.approx(0.2)
    assert transition["after"].node_features[1, 4] == pytest.approx(0.4)
