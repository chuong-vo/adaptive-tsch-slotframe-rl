"""Fixed-capacity graph observations for Gymnasium and Stable-Baselines3."""

from typing import Dict

import gymnasium as gym
import numpy as np

from sdwsn_controller.reinforcement_learning.graph_observation import (
    EDGE_FEATURE_NAMES,
    GLOBAL_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    GraphObservation,
)


class PaddedGraphObservationAdapter:
    """Pad a variable-size graph without silently dropping nodes or edges."""

    def __init__(self, max_nodes: int, max_edges: int | None = None) -> None:
        if isinstance(max_nodes, bool) or not isinstance(max_nodes, int):
            raise TypeError("max_nodes must be an integer")
        if max_nodes <= 0:
            raise ValueError("max_nodes must be positive")
        if max_edges is None:
            max_edges = max_nodes * max_nodes
        if isinstance(max_edges, bool) or not isinstance(max_edges, int):
            raise TypeError("max_edges must be an integer")
        if max_edges < 0:
            raise ValueError("max_edges cannot be negative")

        self.max_nodes = max_nodes
        self.max_edges = max_edges
        self.observation_space = gym.spaces.Dict(
            {
                "node_features": gym.spaces.Box(
                    low=0.0,
                    high=1.0,
                    shape=(self.max_nodes, len(NODE_FEATURE_NAMES)),
                    dtype=np.float32,
                ),
                "node_mask": gym.spaces.Box(
                    low=0.0,
                    high=1.0,
                    shape=(self.max_nodes,),
                    dtype=np.float32,
                ),
                "edge_index": gym.spaces.Box(
                    low=0,
                    high=self.max_nodes - 1,
                    shape=(2, self.max_edges),
                    dtype=np.int64,
                ),
                "edge_features": gym.spaces.Box(
                    low=0.0,
                    high=1.0,
                    shape=(self.max_edges, len(EDGE_FEATURE_NAMES)),
                    dtype=np.float32,
                ),
                "edge_mask": gym.spaces.Box(
                    low=0.0,
                    high=1.0,
                    shape=(self.max_edges,),
                    dtype=np.float32,
                ),
                "global_features": gym.spaces.Box(
                    low=0.0,
                    high=1.0,
                    shape=(len(GLOBAL_FEATURE_NAMES),),
                    dtype=np.float32,
                ),
            }
        )

    def pad(self, graph: GraphObservation) -> Dict[str, np.ndarray]:
        """Return a fixed-shape observation or fail on capacity overflow."""
        node_count = len(graph.node_ids)
        edge_count = graph.edge_index.shape[1]
        if node_count > self.max_nodes:
            raise ValueError(
                f"graph has {node_count} nodes, exceeding max_nodes="
                f"{self.max_nodes}"
            )
        if edge_count > self.max_edges:
            raise ValueError(
                f"graph has {edge_count} edges, exceeding max_edges="
                f"{self.max_edges}"
            )

        node_features = np.zeros(
            (self.max_nodes, len(NODE_FEATURE_NAMES)),
            dtype=np.float32,
        )
        node_mask = np.zeros(self.max_nodes, dtype=np.float32)
        edge_index = np.zeros((2, self.max_edges), dtype=np.int64)
        edge_features = np.zeros(
            (self.max_edges, len(EDGE_FEATURE_NAMES)),
            dtype=np.float32,
        )
        edge_mask = np.zeros(self.max_edges, dtype=np.float32)

        node_features[:node_count] = graph.node_features
        node_mask[:node_count] = 1.0
        edge_index[:, :edge_count] = graph.edge_index
        edge_features[:edge_count] = graph.edge_features
        edge_mask[:edge_count] = 1.0

        observation = {
            "node_features": node_features,
            "node_mask": node_mask,
            "edge_index": edge_index,
            "edge_features": edge_features,
            "edge_mask": edge_mask,
            "global_features": graph.global_features.copy(),
        }
        if not self.observation_space.contains(observation):
            raise ValueError("padded graph does not satisfy its observation space")
        return observation
