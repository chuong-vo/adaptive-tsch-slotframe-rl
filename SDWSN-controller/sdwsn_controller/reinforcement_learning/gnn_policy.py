"""Edge-aware graph feature extraction for Stable-Baselines3 policies."""

from typing import Dict

import gymnasium as gym
import torch
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
from torch import nn


class _MessagePassingBlock(nn.Module):
    def __init__(self, hidden_dim: int) -> None:
        super().__init__()
        self.message_network = nn.Sequential(
            nn.Linear(hidden_dim * 3, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
        )
        self.update_network = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        self.normalization = nn.LayerNorm(hidden_dim)

    def forward(
        self,
        node_states: torch.Tensor,
        edge_states: torch.Tensor,
        edge_index: torch.Tensor,
        node_mask: torch.Tensor,
        edge_mask: torch.Tensor,
    ) -> torch.Tensor:
        batch_size, node_count, hidden_dim = node_states.shape
        source_index = edge_index[:, 0].long().clamp(0, node_count - 1)
        target_index = edge_index[:, 1].long().clamp(0, node_count - 1)
        gather_shape = (-1, -1, hidden_dim)
        source_states = torch.gather(
            node_states,
            dim=1,
            index=source_index.unsqueeze(-1).expand(*gather_shape),
        )
        target_states = torch.gather(
            node_states,
            dim=1,
            index=target_index.unsqueeze(-1).expand(*gather_shape),
        )

        valid_edges = edge_mask
        valid_edges = valid_edges * torch.gather(node_mask, 1, source_index)
        valid_edges = valid_edges * torch.gather(node_mask, 1, target_index)
        valid_edges = valid_edges.unsqueeze(-1)

        messages = self.message_network(
            torch.cat((source_states, target_states, edge_states), dim=-1)
        )
        messages = messages * valid_edges
        aggregate = node_states.new_zeros(
            (batch_size, node_count, hidden_dim)
        )
        aggregate.scatter_add_(
            1,
            target_index.unsqueeze(-1).expand(*gather_shape),
            messages,
        )
        message_count = node_states.new_zeros((batch_size, node_count, 1))
        message_count.scatter_add_(
            1,
            target_index.unsqueeze(-1),
            valid_edges,
        )
        aggregate = aggregate / message_count.clamp_min(1.0)

        update = self.update_network(
            torch.cat((node_states, aggregate), dim=-1)
        )
        node_states = self.normalization(node_states + update)
        return node_states * node_mask.unsqueeze(-1)


class EdgeAwareGraphFeaturesExtractor(BaseFeaturesExtractor):
    """Encode padded directed graphs into a permutation-invariant vector."""

    REQUIRED_KEYS = {
        "node_features",
        "node_mask",
        "edge_index",
        "edge_features",
        "edge_mask",
        "global_features",
    }

    def __init__(
        self,
        observation_space: gym.spaces.Dict,
        features_dim: int = 64,
        hidden_dim: int = 64,
        message_passing_steps: int = 2,
    ) -> None:
        if not isinstance(observation_space, gym.spaces.Dict):
            raise TypeError("GNN extractor requires a Dict observation space")
        missing_keys = self.REQUIRED_KEYS.difference(
            observation_space.spaces
        )
        if missing_keys:
            raise ValueError(
                f"graph observation space is missing keys: "
                f"{sorted(missing_keys)}"
            )
        for name, value in (
            ("features_dim", features_dim),
            ("hidden_dim", hidden_dim),
            ("message_passing_steps", message_passing_steps),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        if hidden_dim <= 0 or features_dim <= 0:
            raise ValueError("hidden_dim and features_dim must be positive")
        if message_passing_steps <= 0:
            raise ValueError("message_passing_steps must be positive")

        super().__init__(observation_space, features_dim)
        node_dim = observation_space["node_features"].shape[-1]
        edge_dim = observation_space["edge_features"].shape[-1]
        global_dim = observation_space["global_features"].shape[-1]

        self.node_encoder = nn.Sequential(
            nn.Linear(node_dim, hidden_dim),
            nn.ReLU(),
        )
        self.edge_encoder = nn.Sequential(
            nn.Linear(edge_dim, hidden_dim),
            nn.ReLU(),
        )
        self.message_passing = nn.ModuleList(
            _MessagePassingBlock(hidden_dim)
            for _ in range(message_passing_steps)
        )
        self.global_encoder = nn.Sequential(
            nn.Linear(global_dim, hidden_dim),
            nn.ReLU(),
        )
        self.output_network = nn.Sequential(
            nn.Linear(hidden_dim * 3, features_dim),
            nn.ReLU(),
        )

    def forward(self, observations: Dict[str, torch.Tensor]) -> torch.Tensor:
        node_mask = observations["node_mask"].float()
        edge_mask = observations["edge_mask"].float()
        node_states = self.node_encoder(
            observations["node_features"].float()
        )
        node_states = node_states * node_mask.unsqueeze(-1)
        edge_states = self.edge_encoder(
            observations["edge_features"].float()
        )
        edge_states = edge_states * edge_mask.unsqueeze(-1)
        edge_index = observations["edge_index"]

        for block in self.message_passing:
            node_states = block(
                node_states=node_states,
                edge_states=edge_states,
                edge_index=edge_index,
                node_mask=node_mask,
                edge_mask=edge_mask,
            )

        mask = node_mask.unsqueeze(-1)
        node_count = mask.sum(dim=1).clamp_min(1.0)
        mean_pool = (node_states * mask).sum(dim=1) / node_count
        minimum = torch.finfo(node_states.dtype).min
        max_pool = node_states.masked_fill(mask == 0, minimum).max(dim=1).values
        has_nodes = node_mask.sum(dim=1, keepdim=True) > 0
        max_pool = torch.where(has_nodes, max_pool, torch.zeros_like(max_pool))
        global_state = self.global_encoder(
            observations["global_features"].float()
        )
        return self.output_network(
            torch.cat((mean_pool, max_pool, global_state), dim=-1)
        )
