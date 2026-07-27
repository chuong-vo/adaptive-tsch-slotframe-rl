"""Gymnasium wrapper exposing live controller state as a padded graph."""

import gymnasium as gym

from sdwsn_controller.reinforcement_learning.graph_observation import (
    GraphObservationBuilder,
)
from sdwsn_controller.reinforcement_learning.padded_graph_observation import (
    PaddedGraphObservationAdapter,
)


class GraphObservationWrapper(gym.ObservationWrapper):
    """Replace the baseline vector observation with a live network graph."""

    def __init__(
        self,
        env: gym.Env,
        max_nodes: int = 10,
        max_edges: int | None = None,
        energy_bounds: tuple[float, float] = (0.0, 5000.0),
        delay_bounds: tuple[float, float] = (10.0, 15000.0),
    ) -> None:
        super().__init__(env)
        base_env = env.unwrapped
        controller = getattr(base_env, "controller", None)
        network = getattr(controller, "network", None)
        if network is None:
            raise ValueError(
                "GraphObservationWrapper requires a controller with a live "
                "network topology"
            )

        self.controller = controller
        self.network = network
        self.builder = GraphObservationBuilder(
            max_slotframe_size=base_env.max_slotframe_size,
            energy_bounds=energy_bounds,
            delay_bounds=delay_bounds,
        )
        self.adapter = PaddedGraphObservationAdapter(
            max_nodes=max_nodes,
            max_edges=max_edges,
        )
        self.observation_space = self.adapter.observation_space
        self.last_graph_observation = None

    def observation(self, observation):
        del observation
        state = self.controller.get_state()
        graph = self.builder.build(
            network=self.network,
            user_requirements=state["user_requirements"],
            current_slotframe_size=state["current_sf_len"],
            last_active_timeslot=state["last_ts_in_schedule"],
        )
        self.last_graph_observation = graph
        return self.adapter.pad(graph)
