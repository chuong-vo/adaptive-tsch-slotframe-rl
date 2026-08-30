from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from experiments.topk_dataset import REPO_ROOT
from experiments.topk_dataset.collector import (
    build_runtime_config,
    candidate_order,
)
from experiments.topk_dataset.csc import parse_csc, render_run_csc
from experiments.topk_dataset.measurement import CoojaLogCursor, snapshot_cycle
from experiments.topk_dataset.prepare import (
    freeze_execution_plan,
    prepare_dataset,
)
from experiments.topk_dataset.protocol import load_protocol, sha256_file
from experiments.topk_dataset.schema import validate_dataset
from experiments.topk_dataset.storage import aggregate_completed_runs
from experiments.topk_dataset.topology import prepare_topology
from sdwsn_controller.exceptions import (
    PacketEncodingError,
    SchedulingInfeasibleError,
)
from sdwsn_controller.node.node import Node
from sdwsn_controller.packet.packet import Cell_Packet, Cell_Packet_Payload
from sdwsn_controller.tsch.contention_free_scheduler import (
    ContentionFreeScheduler,
    schedule_sha256,
)


CONFIG = REPO_ROOT / "experiments" / "topk_dataset" / "config" / "g0.json"


class FakeScheduleNetwork:
    def __init__(self, max_channels: int = 16):
        self.nodes = {}
        self.tsch_max_ch = max_channels
        self.tsch_slotframe_size = 0

    def nodes_add(self, node_id):
        return self.nodes.setdefault(int(node_id), Node(int(node_id), sid=None))

    def tsch_clear(self):
        for node in self.nodes.values():
            node.tsch_clear()

    def tsch_print(self):
        return None


class FakeMetricNetwork:
    def __init__(self, nodes, slotframe=10, last_ts=8):
        self.nodes = {node.id: node for node in nodes}
        self.tsch_slotframe_size = slotframe
        self._last_ts = last_ts

    def nodes_get(self, node_id):
        return self.nodes.get(node_id)

    def nodes_size(self):
        return len(self.nodes)

    def tsch_last_ts(self):
        return self._last_ts


def test_g0_protocol_has_original_38_slotframes():
    protocol = load_protocol(CONFIG)
    assert protocol["slotframe"]["candidates"] == [
        10, 11, 13, 14, 16, 17, 19, 20, 22, 23, 25, 26, 28,
        29, 32, 34, 35, 37, 38, 40, 41, 43, 44, 46, 47, 49,
        50, 52, 53, 55, 56, 58, 59, 61, 64, 65, 67, 68,
    ]


def test_run_csc_is_generated_without_mutating_template(tmp_path):
    protocol = load_protocol(CONFIG)
    template = Path(protocol["topology"]["template_csc"])
    before = sha256_file(template)
    destination = tmp_path / "seed.csc"
    run_hash = render_run_csc(
        template,
        destination,
        cooja_seed=1001,
        port=60002,
        title="test",
    )
    assert sha256_file(template) == before
    assert run_hash == sha256_file(destination)
    rendered = destination.read_text(encoding="utf-8")
    assert "<randomseed>1001</randomseed>" in rendered
    assert "<port>60002</port>" in rendered
    assert "[CONTIKI_DIR]/examples/elise/coojalogger.js" in rendered
    parsed = parse_csc(destination)
    assert len(parsed.nodes) == 10


def test_frozen_topology_and_schedule_are_deterministic():
    topology = prepare_topology(load_protocol(CONFIG))
    repeated = prepare_topology(load_protocol(CONFIG))
    assert topology["L0"] == 9
    assert topology["expected_source_ids"] == list(range(2, 11))
    assert topology["cells"] == repeated["cells"]
    assert topology["schedule_sha256"] == schedule_sha256(topology["cells"])
    assert sorted(cell["timeslot"] for cell in topology["cells"]) == list(range(9))


def test_deterministic_scheduler_fails_fast_when_infeasible():
    paths = {2: [2, 1], 3: [3, 1]}
    network = FakeScheduleNetwork()
    scheduler = ContentionFreeScheduler(network)
    cells = scheduler.run(paths, 2, schedule_seed=42, deterministic=True)
    assert len(cells) == 2
    with pytest.raises(SchedulingInfeasibleError):
        scheduler.run(paths, 1, schedule_seed=42, deterministic=True)
    with pytest.raises(SchedulingInfeasibleError):
        scheduler.run(paths, 2)


def test_wire_fields_reject_values_above_uint8():
    payload = Cell_Packet_Payload(
        payload=None,
        type=1,
        channel=0,
        timeslot=256,
        scr=2,
        dst=1,
    )
    with pytest.raises(PacketEncodingError):
        payload.pack()


def test_schedule_packet_separates_control_and_measurement_sequences():
    packet = Cell_Packet(
        b"",
        payload_len=0,
        sf_len=38,
        seq=17,
        cycle_seq=4,
    )
    packed = packet.pack()
    payload_len, sf_len, control_seq, cycle_seq, _checksum = struct.unpack(
        "!BBHHH", packed
    )
    assert len(packed) == 8
    assert payload_len == 0
    assert sf_len == 38
    assert control_seq == 17
    assert cycle_seq == 4


def test_exact_tx_counter_and_packet_weighted_metrics(tmp_path):
    log_path = tmp_path / "COOJA.testlog"
    log_path.write_text(
        "1000 2 [INFO: DATA] TX_DATA cycle=7 seq=1\n"
        "2000 2 [INFO: DATA] TX_DATA cycle=7 seq=2\n"
        "3000 3 [INFO: DATA] TX_DATA cycle=7 seq=1\n",
        encoding="utf-8",
    )
    cursor = CoojaLogCursor(log_path)
    cursor.poll()
    expected = cursor.expected_by_source(7, [2, 3])
    assert expected == {2: 2, 3: 1}

    node2 = Node(2, sid=None, rank=1)
    node3 = Node(3, sid=None, rank=1)
    node2.energy_add(1, 100)
    node3.energy_add(1, 200)
    node2.pdr_add(1)
    node2.pdr_add(2)
    node3.pdr_add(1)
    node2.delay_add(1, 10)
    node2.delay_add(2, 20)
    node3.delay_add(1, 30)
    network = FakeMetricNetwork([node2, node3])
    metrics = snapshot_cycle(
        network,
        expected_source_ids=[2, 3],
        expected_by_source=expected,
        slotframe=10,
        cycle_start_sim_us=1000,
        cycle_end_sim_us=4000,
        cycle_duration_wall_s=0.5,
    )
    assert metrics["expected_packets"] == 3
    assert metrics["received_packets"] == 3
    assert metrics["pdr"] == 1.0
    assert metrics["delay_mean_packet_weighted_ms"] == 20.0
    assert metrics["power_total_mw"] == pytest.approx(0.3)
    assert metrics["power_per_source_mw"] == pytest.approx(0.15)


def test_tx_counter_waits_for_complete_appended_line(tmp_path):
    log_path = tmp_path / "COOJA.testlog"
    log_path.write_bytes(b"1000 2 [INFO: DATA] TX_DATA cycle=7")
    cursor = CoojaLogCursor(log_path)

    cursor.poll()
    assert cursor.last_sim_time_us is None
    assert cursor.expected_by_source(7, [2]) == {}

    with log_path.open("ab") as output:
        output.write(b" seq=1\n")
    cursor.poll()

    assert cursor.last_sim_time_us == 1000
    assert cursor.expected_by_source(7, [2]) == {2: 1}


def test_prepare_and_validate_empty_collection(tmp_path):
    protocol = load_protocol(CONFIG)
    topology = prepare_dataset(protocol, tmp_path)
    freeze_execution_plan(
        tmp_path,
        seeds=[1001],
        candidates=[10, 40, 68],
        warmup_cycles=1,
        accepted_cycles=2,
        max_attempts_per_cycle=3,
        mode="smoke",
        port=60001,
    )
    aggregate_completed_runs(tmp_path)
    report = validate_dataset(tmp_path, require_complete=False)
    assert report["valid"] is True
    assert report["completed_runs"] == 0
    runtime = build_runtime_config(
        protocol,
        run_csc=tmp_path / "run.csc",
        log_dir=tmp_path,
        port=60001,
    )
    assert runtime["contiki"]["preserve_logs"] is True
    assert topology["L0"] == 9


def test_candidate_order_is_reproducible_and_seed_specific():
    candidates = [10, 40, 68]
    first = candidate_order("context", 1001, candidates)
    assert first == candidate_order("context", 1001, candidates)
    assert sorted(first) == candidates
    assert first != candidate_order("context", 1002, candidates)
