import os
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

import gymnasium as gym
import numpy as np

from sdwsn_controller.reinforcement_learning.env import Env
from sdwsn_controller.reinforcement_learning.wrappers import (
    SaveOnBestTrainingRewardCallback,
)


class FakeController:
    def __init__(self):
        self.network = None
        self.packet_dissector = SimpleNamespace(sequence=0)
        self.user_requirements = (0.4, 0.3, 0.3)
        self.current_slotframe_size = 10
        self.last_tsch_link = 5

    @property
    def alpha(self):
        return self.user_requirements[0]

    @property
    def beta(self):
        return self.user_requirements[1]

    @property
    def delta(self):
        return self.user_requirements[2]

    def reset(self):
        pass

    def wait(self):
        return True

    def get_network_links(self):
        return None

    def compute_routes(self, _graph):
        return None

    def compute_tsch_schedule(self, _path, slotframe_size):
        self.current_slotframe_size = slotframe_size

    def send_routes(self):
        pass

    def send_tsch_schedules(self):
        pass

    def get_state(self):
        return {
            "user_requirements": self.user_requirements,
            "last_ts_in_schedule": self.last_tsch_link,
            "current_sf_len": self.current_slotframe_size,
        }

    def calculate_reward(self, alpha, beta, delta, slotframe_size):
        return {
            "reward": 2.0,
            "power_normalized": slotframe_size / 100.0,
            "delay_normalized": slotframe_size / 200.0,
            "pdr_mean": 0.9,
            "current_sf_len": slotframe_size,
            "last_ts_in_schedule": self.last_tsch_link,
        }


class EnvSlotframeControlsTest(unittest.TestCase):
    def setUp(self):
        settings = {
            "ELISE_MIN_SLOTFRAME_SIZE": "10",
            "ELISE_MAX_SLOTFRAME_SIZE": "68",
            "ELISE_INITIAL_SF_MODE": "random",
            "ELISE_INITIAL_SF_MIN": "10",
            "ELISE_INITIAL_SF_MAX": "68",
            "ELISE_REQUIREMENTS_MODE": "profiles",
            "ELISE_REQUIREMENTS_CYCLE": "1",
        }
        self.environment_patch = mock.patch.dict(os.environ, settings)
        self.environment_patch.start()
        self.addCleanup(self.environment_patch.stop)

    def test_random_initial_slotframes_are_seeded_and_cover_the_domain(self):
        first = Env(FakeController(), max_slotframe_size=70)
        second = Env(FakeController(), max_slotframe_size=70)
        gym.Env.reset(first, seed=123)
        gym.Env.reset(second, seed=123)

        first_sequence = [first._select_initial_slotframe() for _ in range(100)]
        second_sequence = [second._select_initial_slotframe() for _ in range(100)]

        self.assertEqual(first_sequence, second_sequence)
        self.assertLess(min(first_sequence), 25)
        self.assertGreater(max(first_sequence), 55)
        self.assertTrue(all(10 <= sf_len <= 68 for sf_len in first_sequence))
        self.assertTrue(all(
            first._valid_slotframe_sizes(sf_len, sf_len)
            for sf_len in first_sequence
        ))

    def test_reset_uses_requested_profile_and_recomputes_observation(self):
        controller = FakeController()
        env = Env(controller, max_slotframe_size=70)

        observation, info = env.reset(
            seed=7,
            options={"profile": "delay", "initial_sf": 40},
        )

        self.assertEqual(controller.user_requirements, (0.1, 0.8, 0.1))
        self.assertEqual(controller.current_slotframe_size, 40)
        self.assertAlmostEqual(float(observation[-1]), 40 / 70)
        self.assertEqual(info["episode_initial_sf_len"], 40)
        self.assertEqual(info["episode_profile"], "delay")

    def test_reset_rejects_out_of_domain_or_non_coprime_slotframes(self):
        env = Env(FakeController(), max_slotframe_size=70)

        for invalid_sf in (9, 31, 69):
            with self.subTest(initial_sf=invalid_sf):
                with self.assertRaises(ValueError):
                    env.reset(options={"initial_sf": invalid_sf})

    def test_actions_are_held_at_the_training_domain_boundaries(self):
        controller = FakeController()
        env = Env(controller, max_slotframe_size=70)
        env.reset(options={"profile": "delay", "initial_sf": 10})

        observation, _, _, _, lower_info = env.step(1)
        self.assertEqual(controller.current_slotframe_size, 10)
        self.assertAlmostEqual(float(observation[-1]), 10 / 70)
        self.assertTrue(lower_info["action_overridden"])
        self.assertEqual(lower_info["applied_action"], 2)

        controller.current_slotframe_size = 68
        observation, _, _, _, upper_info = env.step(np.array(0))
        self.assertEqual(controller.current_slotframe_size, 68)
        self.assertAlmostEqual(float(observation[-1]), 68 / 70)
        self.assertTrue(upper_info["action_overridden"])
        self.assertEqual(upper_info["applied_action"], 2)

    def test_training_reward_callback_uses_a_separate_save_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            monitor_dir = os.path.join(directory, "monitor")
            save_dir = os.path.join(directory, "training_best")
            os.makedirs(monitor_dir)
            callback = SaveOnBestTrainingRewardCallback(
                check_freq=100,
                log_dir=monitor_dir,
                save_dir=save_dir,
                verbose=0,
            )

            callback._init_callback()

            self.assertEqual(callback.log_dir, monitor_dir)
            self.assertEqual(
                callback.save_path,
                os.path.join(save_dir, "best_model"),
            )
            self.assertTrue(os.path.isdir(save_dir))
            self.assertFalse(os.path.isdir(callback.save_path))


if __name__ == "__main__":
    unittest.main()
