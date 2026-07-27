import tempfile
import unittest
from types import SimpleNamespace

import gymnasium as gym
import numpy as np
import torch
from stable_baselines3 import PPO

from sdwsn_controller.node.node import Node
from sdwsn_controller.reinforcement_learning.gnn_policy import (
    EdgeAwareGraphFeaturesExtractor,
)
from sdwsn_controller.reinforcement_learning.graph_env import (
    GraphObservationWrapper,
)
from sdwsn_controller.reinforcement_learning.graph_observation import (
    EDGE_FEATURE_NAMES,
    GLOBAL_FEATURE_NAMES,
    NODE_FEATURE_NAMES,
    GraphObservation,
)
from sdwsn_controller.reinforcement_learning.padded_graph_observation import (
    PaddedGraphObservationAdapter,
)


def make_graph() -> GraphObservation:
    node_features = np.zeros((3, len(NODE_FEATURE_NAMES)), dtype=np.float32)
    node_features[0, 0] = 1.0
    node_features[1, 1:5] = (0.1, 1.0, 1.0, 0.3)
    node_features[2, 1:5] = (0.2, 1.0, 0.5, 0.6)
    edge_features = np.zeros((3, len(EDGE_FEATURE_NAMES)), dtype=np.float32)
    edge_features[:, :4] = (
        (0.8, 1.0, 1.0, 1.0),
        (0.6, 1.0, 0.5, 1.0),
        (0.7, 1.0, 0.8, 1.0),
    )
    return GraphObservation(
        node_ids=np.asarray([1, 2, 3], dtype=np.int64),
        node_features=node_features,
        edge_index=np.asarray(
            [[1, 2, 2], [0, 0, 1]],
            dtype=np.int64,
        ),
        edge_features=edge_features,
        global_features=np.asarray(
            [0.4, 0.3, 0.3, 0.5, 0.1],
            dtype=np.float32,
        ),
    )


def to_tensor_batch(observation):
    return {
        key: torch.as_tensor(value).unsqueeze(0)
        for key, value in observation.items()
    }


class StaticGraphEnv(gym.Env):
    def __init__(self, adapter, observation):
        super().__init__()
        self.observation_space = adapter.observation_space
        self.action_space = gym.spaces.Discrete(3)
        self.observation_value = observation
        self.steps = 0

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.steps = 0
        return self.observation_value, {}

    def step(self, action):
        self.steps += 1
        terminated = self.steps >= 3
        return (
            self.observation_value,
            float(action == 2),
            terminated,
            False,
            {},
        )


class FakeNetwork:
    def __init__(self):
        sink = Node(1, sid=None, rank=0)
        sensor = Node(2, sid=None, rank=1)
        sensor.neighbor_add(1, rssi=-60, etx=128)
        self.nodes = {1: sink, 2: sensor}
        self.tsch_slotframe_size = 35

    def tsch_last_ts(self):
        return 7


class LiveGraphSourceEnv(gym.Env):
    def __init__(self, with_network=True):
        super().__init__()
        network = FakeNetwork() if with_network else None
        self.controller = SimpleNamespace(
            network=network,
            get_state=lambda: {
                "user_requirements": (0.4, 0.3, 0.3),
                "current_sf_len": 35,
                "last_ts_in_schedule": 7,
            },
        )
        self.max_slotframe_size = 70
        self.observation_space = gym.spaces.Box(
            low=-1.0,
            high=1.0,
            shape=(8,),
            dtype=np.float32,
        )
        self.action_space = gym.spaces.Discrete(3)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        return np.zeros(8, dtype=np.float32), {}

    def step(self, action):
        del action
        return np.zeros(8, dtype=np.float32), 0.0, False, False, {}


class PaddedGraphObservationTest(unittest.TestCase):
    def test_padding_masks_and_observation_space_are_consistent(self):
        adapter = PaddedGraphObservationAdapter(max_nodes=5, max_edges=6)
        observation = adapter.pad(make_graph())

        self.assertTrue(adapter.observation_space.contains(observation))
        np.testing.assert_array_equal(
            observation["node_mask"],
            [1.0, 1.0, 1.0, 0.0, 0.0],
        )
        np.testing.assert_array_equal(
            observation["edge_mask"],
            [1.0, 1.0, 1.0, 0.0, 0.0, 0.0],
        )
        self.assertEqual(observation["edge_index"].dtype, np.int64)

    def test_capacity_overflow_fails_instead_of_truncating_graph(self):
        with self.assertRaisesRegex(ValueError, "exceeding max_nodes"):
            PaddedGraphObservationAdapter(
                max_nodes=2,
                max_edges=3,
            ).pad(make_graph())

        with self.assertRaisesRegex(ValueError, "exceeding max_edges"):
            PaddedGraphObservationAdapter(
                max_nodes=3,
                max_edges=2,
            ).pad(make_graph())

    def test_wrapper_requires_and_exposes_a_live_topology(self):
        wrapped = GraphObservationWrapper(
            LiveGraphSourceEnv(),
            max_nodes=3,
            max_edges=4,
        )
        observation, _ = wrapped.reset()

        self.assertTrue(wrapped.observation_space.contains(observation))
        np.testing.assert_array_equal(
            wrapped.last_graph_observation.node_ids,
            [1, 2],
        )

        with self.assertRaisesRegex(ValueError, "live network topology"):
            GraphObservationWrapper(LiveGraphSourceEnv(with_network=False))


class EdgeAwareGraphFeaturesExtractorTest(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(7)
        self.adapter = PaddedGraphObservationAdapter(
            max_nodes=5,
            max_edges=6,
        )
        self.observation = self.adapter.pad(make_graph())
        self.extractor = EdgeAwareGraphFeaturesExtractor(
            self.adapter.observation_space,
            features_dim=32,
            hidden_dim=24,
            message_passing_steps=2,
        )
        self.extractor.eval()

    def test_forward_and_backward_are_finite(self):
        self.extractor.train()
        output = self.extractor(to_tensor_batch(self.observation))

        self.assertEqual(output.shape, (1, 32))
        self.assertTrue(torch.isfinite(output).all())
        output.sum().backward()
        gradients = [
            parameter.grad
            for parameter in self.extractor.parameters()
            if parameter.requires_grad
        ]
        self.assertTrue(all(gradient is not None for gradient in gradients))
        self.assertTrue(all(torch.isfinite(gradient).all() for gradient in gradients))

    def test_masked_padding_does_not_change_embedding(self):
        modified = {
            key: value.copy() for key, value in self.observation.items()
        }
        modified["node_features"][3:] = 1.0
        modified["edge_features"][3:] = 1.0
        modified["edge_index"][:, 3:] = np.asarray(
            [[4, 4, 4], [3, 3, 3]],
            dtype=np.int64,
        )

        with torch.no_grad():
            original_output = self.extractor(
                to_tensor_batch(self.observation)
            )
            modified_output = self.extractor(to_tensor_batch(modified))

        torch.testing.assert_close(original_output, modified_output)

    def test_node_permutation_does_not_change_embedding(self):
        original = self.observation
        permuted = {key: value.copy() for key, value in original.items()}
        permutation = np.asarray([2, 0, 1, 3, 4])
        inverse = np.empty_like(permutation)
        inverse[permutation] = np.arange(len(permutation))
        permuted["node_features"] = original["node_features"][permutation]
        permuted["node_mask"] = original["node_mask"][permutation]
        active_edges = original["edge_mask"].astype(bool)
        permuted["edge_index"][:, active_edges] = inverse[
            original["edge_index"][:, active_edges]
        ]

        with torch.no_grad():
            original_output = self.extractor(to_tensor_batch(original))
            permuted_output = self.extractor(to_tensor_batch(permuted))

        torch.testing.assert_close(
            original_output,
            permuted_output,
            rtol=1e-5,
            atol=1e-6,
        )

    def test_graph_without_edges_produces_finite_embedding(self):
        no_edges = {
            key: value.copy() for key, value in self.observation.items()
        }
        no_edges["edge_index"].fill(0)
        no_edges["edge_features"].fill(0.0)
        no_edges["edge_mask"].fill(0.0)

        with torch.no_grad():
            output = self.extractor(to_tensor_batch(no_edges))

        self.assertEqual(output.shape, (1, 32))
        self.assertTrue(torch.isfinite(output).all())

    def test_multi_input_ppo_can_complete_a_short_rollout(self):
        env = StaticGraphEnv(self.adapter, self.observation)
        model = PPO(
            "MultiInputPolicy",
            env,
            n_steps=4,
            batch_size=4,
            n_epochs=1,
            policy_kwargs={
                "features_extractor_class": EdgeAwareGraphFeaturesExtractor,
                "features_extractor_kwargs": {
                    "features_dim": 32,
                    "hidden_dim": 24,
                    "message_passing_steps": 2,
                },
            },
            seed=7,
            device="cpu",
            verbose=0,
        )

        model.learn(total_timesteps=8)
        action, _ = model.predict(self.observation, deterministic=True)

        self.assertIn(int(action), (0, 1, 2))
        with tempfile.TemporaryDirectory() as directory:
            model_path = f"{directory}/gnn_ppo"
            model.save(model_path)
            loaded_model = PPO.load(model_path, env=env, device="cpu")
            loaded_action, _ = loaded_model.predict(
                self.observation,
                deterministic=True,
            )

        self.assertEqual(int(action), int(loaded_action))


if __name__ == "__main__":
    unittest.main()
