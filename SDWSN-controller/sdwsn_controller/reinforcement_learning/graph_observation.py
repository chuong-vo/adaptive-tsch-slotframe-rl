"""Graph observations for topology-aware reinforcement learning policies.

This module is intentionally independent from the existing PPO environment.
It converts the controller's current network state into deterministic NumPy
arrays that can later be consumed by a GNN feature extractor.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

import numpy as np

from sdwsn_controller.tsch.schedule import cell_type


NODE_FEATURE_NAMES = (
    "is_sink",
    "rank_normalized",
    "rank_available",
    "neighbor_degree_normalized",
    "energy_normalized",
    "delay_normalized",
    "pdr",
    "energy_available",
    "delay_available",
    "pdr_available",
    "tx_cell_count_normalized",
    "rx_cell_count_normalized",
)

EDGE_FEATURE_NAMES = (
    "rssi_strength",
    "rssi_available",
    "etx_quality",
    "etx_available",
    "selected_route",
    "tsch_scheduled",
)

GLOBAL_FEATURE_NAMES = (
    "alpha",
    "beta",
    "delta",
    "slotframe_size_normalized",
    "last_active_timeslot_normalized",
)


@dataclass(frozen=True)
class GraphObservation:
    """A single variable-size network graph represented as NumPy arrays."""

    node_ids: np.ndarray
    node_features: np.ndarray
    edge_index: np.ndarray
    edge_features: np.ndarray
    global_features: np.ndarray

    def __post_init__(self) -> None:
        node_count = len(self.node_ids)

        if self.node_ids.dtype != np.int64 or self.node_ids.ndim != 1:
            raise ValueError("node_ids must be a one-dimensional int64 array")
        if self.node_features.shape != (node_count, len(NODE_FEATURE_NAMES)):
            raise ValueError("node_features has an invalid shape")
        if self.node_features.dtype != np.float32:
            raise ValueError("node_features must use float32")
        if not np.isfinite(self.node_features).all():
            raise ValueError("node_features must contain only finite values")
        if (
            self.edge_index.dtype != np.int64
            or self.edge_index.ndim != 2
            or self.edge_index.shape[0] != 2
        ):
            raise ValueError("edge_index must have int64 shape [2, E]")
        edge_count = self.edge_index.shape[1]
        if self.edge_features.shape != (edge_count, len(EDGE_FEATURE_NAMES)):
            raise ValueError("edge_features has an invalid shape")
        if self.edge_features.dtype != np.float32:
            raise ValueError("edge_features must use float32")
        if not np.isfinite(self.edge_features).all():
            raise ValueError("edge_features must contain only finite values")
        if self.global_features.shape != (len(GLOBAL_FEATURE_NAMES),):
            raise ValueError("global_features has an invalid shape")
        if self.global_features.dtype != np.float32:
            raise ValueError("global_features must use float32")
        if not np.isfinite(self.global_features).all():
            raise ValueError("global_features must contain only finite values")
        if edge_count and (
            self.edge_index.min() < 0 or self.edge_index.max() >= node_count
        ):
            raise ValueError("edge_index contains an invalid node index")

    def as_dict(self) -> Dict[str, np.ndarray]:
        """Return the observation in a framework-neutral mapping."""
        return {
            "node_ids": self.node_ids,
            "node_features": self.node_features,
            "edge_index": self.edge_index,
            "edge_features": self.edge_features,
            "global_features": self.global_features,
        }


class GraphObservationBuilder:
    """Build graph observations from a live ``Network`` instance."""

    ETX_DIVISOR = 128.0
    RANK_UNKNOWN = 0xFF
    RSSI_UNKNOWN = 0x7FFF

    def __init__(
        self,
        max_slotframe_size: int,
        energy_bounds: Tuple[float, float] = (0.0, 5000.0),
        delay_bounds: Tuple[float, float] = (10.0, 15000.0),
        sink_id: int = 1,
        excluded_node_ids: Iterable[int] = (0,),
        rssi_bounds: Tuple[float, float] = (-100.0, 0.0),
    ) -> None:
        if max_slotframe_size <= 0:
            raise ValueError("max_slotframe_size must be positive")
        self._validate_bounds("energy_bounds", energy_bounds)
        self._validate_bounds("delay_bounds", delay_bounds)
        self._validate_bounds("rssi_bounds", rssi_bounds)

        self.max_slotframe_size = float(max_slotframe_size)
        self.energy_bounds = energy_bounds
        self.delay_bounds = delay_bounds
        self.rssi_bounds = rssi_bounds
        self.sink_id = int(sink_id)
        self.excluded_node_ids = frozenset(
            int(node_id) for node_id in excluded_node_ids
        )

    @staticmethod
    def _validate_bounds(name: str, bounds: Tuple[float, float]) -> None:
        if len(bounds) != 2 or bounds[0] >= bounds[1]:
            raise ValueError(f"{name} must contain an increasing (min, max) pair")

    def normalization_metadata(self) -> Dict[str, object]:
        """Describe the normalization needed to interpret stored features."""
        return {
            "max_slotframe_size": self.max_slotframe_size,
            "energy_bounds": list(self.energy_bounds),
            "delay_bounds": list(self.delay_bounds),
            "rssi_bounds": list(self.rssi_bounds),
            "sink_id": self.sink_id,
            "excluded_node_ids": sorted(self.excluded_node_ids),
            "rank_unknown": self.RANK_UNKNOWN,
            "rssi_unknown": self.RSSI_UNKNOWN,
            "etx_divisor": self.ETX_DIVISOR,
        }

    @staticmethod
    def _clip_unit(value: float) -> float:
        return float(np.clip(value, 0.0, 1.0))

    @classmethod
    def _normalize(
        cls,
        value: float,
        bounds: Tuple[float, float],
    ) -> float:
        lower, upper = bounds
        return cls._clip_unit((float(value) - lower) / (upper - lower))

    def build(
        self,
        network: object,
        user_requirements: Tuple[float, float, float],
        current_slotframe_size: int | None = None,
        last_active_timeslot: int | None = None,
    ) -> GraphObservation:
        """Create an atomic graph snapshot when the network exposes a lock."""
        state_lock = getattr(network, "state_lock", None)
        if state_lock is None:
            return self._build_snapshot(
                network,
                user_requirements,
                current_slotframe_size,
                last_active_timeslot,
            )
        with state_lock:
            return self._build_snapshot(
                network,
                user_requirements,
                current_slotframe_size,
                last_active_timeslot,
            )

    def _build_snapshot(
        self,
        network: object,
        user_requirements: Tuple[float, float, float],
        current_slotframe_size: int | None = None,
        last_active_timeslot: int | None = None,
    ) -> GraphObservation:
        """Create a deterministic graph snapshot while network state is stable."""
        requirements = np.asarray(user_requirements, dtype=np.float32)
        if requirements.shape != (3,) or not np.isfinite(requirements).all():
            raise ValueError("user_requirements must contain alpha, beta, and delta")
        if np.any(requirements < 0.0) or np.any(requirements > 1.0):
            raise ValueError("user requirements must be within [0, 1]")

        nodes = {
            int(node_id): node
            for node_id, node in network.nodes.items()
            if int(node_id) not in self.excluded_node_ids
        }
        if not nodes:
            raise ValueError("network does not contain any observable nodes")

        node_ids = np.asarray(sorted(nodes), dtype=np.int64)
        node_indices = {
            int(node_id): index for index, node_id in enumerate(node_ids)
        }
        max_degree = max(len(node_ids) - 1, 1)

        observable_node_ids = frozenset(nodes)
        node_features = np.asarray(
            [
                self._node_features(
                    nodes[int(node_id)],
                    max_degree,
                    observable_node_ids,
                )
                for node_id in node_ids
            ],
            dtype=np.float32,
        )

        edge_records = []
        for src_id in node_ids:
            src_node = nodes[int(src_id)]
            for dst_id, neighbor in sorted(src_node.neighbors_get().items()):
                dst_id = int(dst_id)
                if dst_id not in node_indices:
                    continue
                edge_records.append(
                    (
                        node_indices[int(src_id)],
                        node_indices[dst_id],
                        self._edge_features(src_node, neighbor),
                    )
                )

        if edge_records:
            edge_index = np.asarray(
                [(src, dst) for src, dst, _ in edge_records],
                dtype=np.int64,
            ).T
            edge_features = np.asarray(
                [features for _, _, features in edge_records],
                dtype=np.float32,
            )
        else:
            edge_index = np.empty((2, 0), dtype=np.int64)
            edge_features = np.empty(
                (0, len(EDGE_FEATURE_NAMES)),
                dtype=np.float32,
            )

        if current_slotframe_size is None:
            current_slotframe_size = network.tsch_slotframe_size
        if last_active_timeslot is None:
            last_active_timeslot = network.tsch_last_ts()

        global_features = np.asarray(
            [
                requirements[0],
                requirements[1],
                requirements[2],
                self._clip_unit(
                    float(current_slotframe_size) / self.max_slotframe_size
                ),
                self._clip_unit(
                    float(last_active_timeslot) / self.max_slotframe_size
                ),
            ],
            dtype=np.float32,
        )

        return GraphObservation(
            node_ids=node_ids,
            node_features=node_features,
            edge_index=edge_index,
            edge_features=edge_features,
            global_features=global_features,
        )

    def _node_features(
        self,
        node: object,
        max_degree: int,
        observable_node_ids: frozenset[int],
    ) -> Tuple[float, ...]:
        rank_available = node.rank is not None and 0 <= node.rank < self.RANK_UNKNOWN
        rank_normalized = (
            self._clip_unit(float(node.rank) / (self.RANK_UNKNOWN - 1))
            if rank_available
            else 0.0
        )

        energy_available = node.energy.size() > 0
        delay_available = node.delay.size() > 0
        pdr_available = node.pdr.size() > 0
        schedules = tuple(node.tsch_get().values())
        tx_cells = sum(
            schedule.schedule_type == cell_type.UC_TX for schedule in schedules
        )
        rx_cells = sum(
            schedule.schedule_type == cell_type.UC_RX for schedule in schedules
        )
        observable_degree = sum(
            int(neighbor_id) in observable_node_ids
            for neighbor_id in node.neighbors_get()
        )

        return (
            float(node.id == self.sink_id),
            rank_normalized,
            float(rank_available),
            self._clip_unit(observable_degree / max_degree),
            (
                self._normalize(node.energy_get_last(), self.energy_bounds)
                if energy_available
                else 0.0
            ),
            (
                self._normalize(node.delay_get_average(), self.delay_bounds)
                if delay_available
                else 0.0
            ),
            self._clip_unit(node.pdr_get_average()) if pdr_available else 0.0,
            float(energy_available),
            float(delay_available),
            float(pdr_available),
            self._clip_unit(tx_cells / self.max_slotframe_size),
            self._clip_unit(rx_cells / self.max_slotframe_size),
        )

    def _edge_features(self, src_node: object, neighbor: object) -> Tuple[float, ...]:
        rssi = float(neighbor.rssi)
        rssi_available = rssi not in (0.0, float(self.RSSI_UNKNOWN))
        etx = float(neighbor.etx)
        etx_available = etx > 0.0
        etx_actual = etx / self.ETX_DIVISOR if etx_available else 0.0
        etx_quality = (
            self._clip_unit(1.0 / max(etx_actual, 1.0))
            if etx_available
            else 0.0
        )
        selected_route = any(
            route.nexthop_id == neighbor.neighbor_id
            for route in src_node.routes_get().values()
        )
        tsch_scheduled = any(
            schedule.schedule_type == cell_type.UC_TX
            and schedule.dst_id == neighbor.neighbor_id
            for schedule in src_node.tsch_get().values()
        )

        return (
            self._normalize(rssi, self.rssi_bounds) if rssi_available else 0.0,
            float(rssi_available),
            etx_quality,
            float(etx_available),
            float(selected_route),
            float(tsch_scheduled),
        )
