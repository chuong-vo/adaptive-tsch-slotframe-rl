"""Cycle-level source counters and packet-weighted network metrics."""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable


TX_DATA_PATTERN = re.compile(
    r"^\s*(?P<sim_time>\d+)\s+(?P<node_id>\d+)\s+.*"
    r"TX_DATA cycle=(?P<cycle>\d+) seq=(?P<seq>\d+)"
)
SIM_TIME_PATTERN = re.compile(r"^\s*(?P<sim_time>\d+)\s+")


class CycleRejected(RuntimeError):
    def __init__(self, reason_code: str, note: str, missing_node_ids=None):
        super().__init__(note)
        self.reason_code = reason_code
        self.note = note
        self.missing_node_ids = sorted(missing_node_ids or [])


class CoojaLogCursor:
    """Incrementally read exact source-side TX counters from COOJA.testlog."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.offset = 0
        self.last_sim_time_us = None
        self._sequences = defaultdict(lambda: defaultdict(list))

    def poll(self) -> None:
        if not self.path.exists():
            return
        size = self.path.stat().st_size
        if size < self.offset:
            self.offset = 0
            self.last_sim_time_us = None
            self._sequences.clear()
        with self.path.open("rb") as source:
            source.seek(self.offset)
            pending = source.read()
            complete_end = pending.rfind(b"\n") + 1
            if complete_end == 0:
                return
            self.offset += complete_end
            complete = pending[:complete_end].decode("utf-8", errors="replace")
            for line in complete.splitlines():
                sim_match = SIM_TIME_PATTERN.search(line)
                if sim_match:
                    self.last_sim_time_us = int(sim_match.group("sim_time"))
                tx_match = TX_DATA_PATTERN.search(line)
                if not tx_match:
                    continue
                cycle = int(tx_match.group("cycle"))
                node_id = int(tx_match.group("node_id"))
                sequence = int(tx_match.group("seq"))
                self._sequences[cycle][node_id].append(sequence)

    def expected_by_source(
        self,
        cycle_sequence: int,
        source_ids: Iterable[int],
    ) -> dict[int, int]:
        cycle = self._sequences.get(int(cycle_sequence), {})
        return {
            int(node_id): len(cycle[int(node_id)])
            for node_id in source_ids
            if cycle.get(int(node_id))
        }


def _latest_energy_uw(node):
    samples = node.energy.samples
    if not samples:
        return None
    latest_sequence = max(samples)
    return float(samples[latest_sequence].energy)


def _legacy_power_wam_uw(network, energy_by_source):
    if not energy_by_source:
        return math.nan
    nodes = [network.nodes_get(node_id) for node_id in sorted(energy_by_source)]
    last_rank = max((node.rank for node in nodes), default=1) or 1
    network_size = network.nodes_size() or 1
    weights = [
        0.9 * (node.rank / last_rank)
        + 0.1 * (node.neighbors_len() / network_size)
        for node in nodes
    ]
    weight_sum = sum(weights)
    if weight_sum <= 0:
        return math.nan
    return sum(
        weight * energy_by_source[node.id]
        for weight, node in zip(weights, nodes)
    ) / weight_sum


def snapshot_cycle(
    network,
    *,
    expected_source_ids: Iterable[int],
    expected_by_source: dict[int, int],
    slotframe: int,
    cycle_start_sim_us: int | None,
    cycle_end_sim_us: int | None,
    cycle_duration_wall_s: float,
) -> dict[str, object]:
    source_ids = sorted(int(node_id) for node_id in expected_source_ids)
    missing_nodes = [
        node_id for node_id in source_ids if network.nodes_get(node_id) is None
    ]
    missing_counters = [
        node_id for node_id in source_ids if node_id not in expected_by_source
    ]

    energy_by_source = {}
    received_by_source = {}
    delay_sum_by_source = {}
    for node_id in source_ids:
        node = network.nodes_get(node_id)
        if node is None:
            continue
        energy = _latest_energy_uw(node)
        if energy is not None:
            energy_by_source[node_id] = energy
        received_by_source[node_id] = len(node.pdr.samples)
        delay_sum_by_source[node_id] = sum(
            sample.delay for sample in node.delay.samples.values()
        )

    missing_energy = [
        node_id for node_id in source_ids if node_id not in energy_by_source
    ]
    missing = sorted(set(missing_nodes + missing_counters + missing_energy))
    if missing:
        raise CycleRejected(
            "MISSING_NODES",
            "Missing node, source TX counter, or power sample",
            missing,
        )

    expected_packets = sum(expected_by_source.values())
    if any(count > 255 for count in expected_by_source.values()):
        raise CycleRejected(
            "ENCODING_ERROR",
            "A source exceeded the uint8 packet-sequence domain in one cycle",
        )
    received_packets = sum(received_by_source.values())
    delivered_packets = sum(
        len(network.nodes_get(node_id).delay.samples) for node_id in source_ids
    )
    if expected_packets <= 0 or delivered_packets <= 0:
        raise CycleRejected(
            "NON_FINITE_METRIC",
            "Cycle has no expected or delivered data packets",
        )
    if received_packets != delivered_packets or received_packets > expected_packets:
        raise CycleRejected(
            "NON_FINITE_METRIC",
            "Packet counters are inconsistent: "
            f"received={received_packets}, delivered={delivered_packets}, "
            f"expected={expected_packets}",
        )
    if cycle_start_sim_us is None or cycle_end_sim_us is None:
        raise CycleRejected("NON_FINITE_METRIC", "Cooja simulation time is unavailable")

    duration_sim_ms = (cycle_end_sim_us - cycle_start_sim_us) / 1000.0
    delay_sum_ms = float(sum(delay_sum_by_source.values()))
    power_total_mw = sum(energy_by_source.values()) / 1000.0
    values = {
        "cycle_start_sim_ms": cycle_start_sim_us / 1000.0,
        "cycle_duration_sim_ms": duration_sim_ms,
        "cycle_duration_wall_s": float(cycle_duration_wall_s),
        "power_total_mw": power_total_mw,
        "power_per_source_mw": power_total_mw / len(source_ids),
        "power_legacy_wam": _legacy_power_wam_uw(
            network,
            energy_by_source,
        ) / 1000.0,
        "delay_sum_ms": delay_sum_ms,
        "delivered_packets": delivered_packets,
        "expected_packets": expected_packets,
        "received_packets": received_packets,
        "throughput_pps": received_packets / (duration_sim_ms / 1000.0),
        "delay_mean_packet_weighted_ms": delay_sum_ms / delivered_packets,
        "pdr": received_packets / expected_packets,
        "reporting_source_count": len(source_ids),
        "expected_source_count": len(source_ids),
        "last_ts_in_schedule": network.tsch_last_ts(),
        "current_sf_len": int(network.tsch_slotframe_size),
        "expected_by_source_json": json.dumps(expected_by_source, sort_keys=True),
        "received_by_source_json": json.dumps(received_by_source, sort_keys=True),
        "power_by_source_mw_json": json.dumps(
            {
                node_id: energy_uw / 1000.0
                for node_id, energy_uw in energy_by_source.items()
            },
            sort_keys=True,
        ),
    }
    finite_values = [
        value for value in values.values() if isinstance(value, (float, int))
    ]
    if duration_sim_ms <= 0 or cycle_duration_wall_s <= 0:
        raise CycleRejected("NON_FINITE_METRIC", "Cycle duration is not positive")
    if not all(math.isfinite(float(value)) for value in finite_values):
        raise CycleRejected("NON_FINITE_METRIC", "Cycle contains a non-finite metric")
    if not 0.0 <= float(values["pdr"]) <= 1.0:
        raise CycleRejected("NON_FINITE_METRIC", "PDR is outside [0, 1]")
    if int(values["current_sf_len"]) != int(slotframe):
        raise CycleRejected("NON_FINITE_METRIC", "Applied slotframe does not match candidate")
    if int(slotframe) <= int(values["last_ts_in_schedule"]):
        raise CycleRejected("SCHEDULE_INFEASIBLE", "Slotframe does not contain the schedule")
    return values
