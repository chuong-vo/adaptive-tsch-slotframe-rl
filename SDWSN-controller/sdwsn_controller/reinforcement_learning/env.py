#!/usr/bin/python3
#
# Copyright (C) 2022  Fernando Jurado-Lasso <ffjla@dtu.dk>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

""" This is the implementation of the Software-Defined Wireless Sensor Network
environment """
import gymnasium as gym
import os
from gymnasium import spaces
import numpy as np
import time
import logging

from sdwsn_controller.common import common

# These are the size of other schedules in orchestra
eb_size = 397
common_size = 31
control_plane_size = 27


class Env(gym.Env):
    """Custom SDWSN Environment that follows gym interface"""
    metadata = {'render.modes': ['human']}

    def __init__(
            self,
            # simulation_name: str,
            controller: object,
            max_slotframe_size: None,
            # folder: str = './figures/'
    ):
        super(Env, self).__init__()
        # assert isinstance(simulation_name, str)
        # assert isinstance(folder, str)
        self.controller = controller
        self.logger = logging.getLogger('main.env')

        assert isinstance(max_slotframe_size, int)
        self.max_slotframe_size = max_slotframe_size
        try:
            self.min_slotframe_size = max(
                1,
                int(os.environ.get("ELISE_MIN_SLOTFRAME_SIZE", "1")),
            )
        except ValueError as exc:
            raise ValueError("ELISE_MIN_SLOTFRAME_SIZE must be an integer") from exc
        try:
            configured_max_sf = int(
                os.environ.get(
                    "ELISE_MAX_SLOTFRAME_SIZE",
                    str(self.max_slotframe_size),
                )
            )
        except ValueError as exc:
            raise ValueError("ELISE_MAX_SLOTFRAME_SIZE must be an integer") from exc
        self.action_max_slotframe_size = min(
            self.max_slotframe_size,
            configured_max_sf,
        )
        if self.min_slotframe_size > self.action_max_slotframe_size:
            raise ValueError(
                "Minimum slotframe size cannot exceed maximum slotframe size"
            )

        self.initial_sf_mode = os.environ.get(
            "ELISE_INITIAL_SF_MODE",
            "fixed",
        ).strip().lower()
        if self.initial_sf_mode not in {"fixed", "random"}:
            raise ValueError(
                "ELISE_INITIAL_SF_MODE must be either 'fixed' or 'random'"
            )
        try:
            self.initial_sf_fixed = int(
                os.environ.get("ELISE_INITIAL_SF", "10")
            )
            self.initial_sf_min = int(
                os.environ.get(
                    "ELISE_INITIAL_SF_MIN",
                    str(self.min_slotframe_size),
                )
            )
            self.initial_sf_max = int(
                os.environ.get(
                    "ELISE_INITIAL_SF_MAX",
                    str(self.action_max_slotframe_size),
                )
            )
        except ValueError as exc:
            raise ValueError("Initial slotframe settings must be integers") from exc
        self.initial_sf_min = max(
            self.min_slotframe_size,
            self.initial_sf_min,
        )
        self.initial_sf_max = min(
            self.action_max_slotframe_size,
            self.initial_sf_max,
        )
        if self.initial_sf_min > self.initial_sf_max:
            raise ValueError(
                "Initial slotframe minimum cannot exceed its maximum"
            )
        try:
            self.max_wait_retries = max(
                1,
                int(os.environ.get("ELISE_MAX_WAIT_RETRIES", "3")),
            )
        except ValueError:
            self.logger.warning(
                "Invalid ELISE_MAX_WAIT_RETRIES, using default value 3"
            )
            self.max_wait_retries = 3
        try:
            self.max_reset_graph_retries = max(
                1,
                int(os.environ.get("ELISE_RESET_GRAPH_RETRIES", "5")),
            )
        except ValueError:
            self.logger.warning(
                "Invalid ELISE_RESET_GRAPH_RETRIES, using default value 5"
            )
            self.max_reset_graph_retries = 5
        try:
            self.reset_graph_retry_sleep = max(
                0.0,
                float(os.environ.get("ELISE_RESET_GRAPH_RETRY_SLEEP", "1.0")),
            )
        except ValueError:
            self.logger.warning(
                "Invalid ELISE_RESET_GRAPH_RETRY_SLEEP, using default value 1.0"
            )
            self.reset_graph_retry_sleep = 1.0
        # self.folder = folder
        # self.simulation_name = simulation_name
        # We define the number of actions
        n_actions = 3  # increase and decrease slotframe size
        self.action_space = spaces.Discrete(n_actions)
        self._has_reset_once = False
        self._episode_index = 0
        self.episode_initial_sf_len = None
        self.episode_profile = None
        # We define the observation space
        # They will be the user requirements, power, delay, pdr, last ts active in schedule, and current slotframe size
        self.n_observations = 8
        self.observation_space = spaces.Box(low=-1, high=1,
                                            shape=(self.n_observations, ), dtype=np.float32)

    def _wait_for_processing_window(self, phase, on_retry=None):
        attempts = 0
        while not self.controller.wait():
            attempts += 1
            self.logger.warning(
                "%s wait failed on attempt %d/%d",
                phase,
                attempts,
                self.max_wait_retries,
            )
            if attempts >= self.max_wait_retries:
                raise TimeoutError(
                    f"{phase} processing window stalled after "
                    f"{self.max_wait_retries} attempts"
                )
            if on_retry is not None:
                on_retry()
            time.sleep(0.1)
        return attempts

    def _safe_slotframe_at_least(self, min_sf_len):
        sf_len = max(1, int(min_sf_len))
        if common.compare_coprime(sf_len):
            return sf_len
        return common.next_coprime(sf_len)

    def _valid_slotframe_sizes(self, lower, upper):
        lower = max(self.min_slotframe_size, int(lower))
        upper = min(self.action_max_slotframe_size, int(upper))
        return [
            sf_len
            for sf_len in range(lower, upper + 1)
            if common.compare_coprime(sf_len)
        ]

    def _select_initial_slotframe(self, options=None):
        options = options or {}
        explicit_sf = options.get("initial_sf")
        if explicit_sf is not None:
            try:
                explicit_sf = int(explicit_sf)
            except (TypeError, ValueError) as exc:
                raise ValueError("reset option initial_sf must be an integer") from exc
            if not self._valid_slotframe_sizes(explicit_sf, explicit_sf):
                raise ValueError(
                    "reset option initial_sf must be coprime and within "
                    f"[{self.min_slotframe_size}, "
                    f"{self.action_max_slotframe_size}]"
                )
            return explicit_sf

        mode = str(options.get("initial_sf_mode", self.initial_sf_mode)).lower()
        if mode == "fixed":
            if not self._valid_slotframe_sizes(
                    self.initial_sf_fixed, self.initial_sf_fixed):
                raise ValueError(
                    "ELISE_INITIAL_SF must be coprime and within the configured "
                    "slotframe bounds"
                )
            return self.initial_sf_fixed
        if mode != "random":
            raise ValueError("initial_sf_mode must be either 'fixed' or 'random'")

        valid_values = self._valid_slotframe_sizes(
            self.initial_sf_min,
            self.initial_sf_max,
        )
        if not valid_values:
            raise ValueError("No valid initial slotframe exists in the configured range")
        return int(self.np_random.choice(valid_values))

    """ Step action """

    def step(self, action):
        # We now get the last observations
        raw_action = int(np.asarray(action).item())
        state = self.controller.get_state()
        if raw_action == 0:
            # print("increasing slotframe size")
            sf_len = common.next_coprime(state['current_sf_len'])
        elif raw_action == 1:
            # print("decreasing slotframe size")
            sf_len = common.previous_coprime(state['current_sf_len'])
        elif raw_action == 2:
            # print("same slotframe size")
            sf_len = state['current_sf_len']
        else:
            raise ValueError(f"Unsupported action: {raw_action}")
        requested_sf_len = sf_len
        applied_action = raw_action
        action_overridden = False
        action_override_reason = ""
        current_sf_len = int(state['current_sf_len'])
        last_ts_in_schedule = int(state['last_ts_in_schedule'])
        minimum_allowed_sf = max(
            last_ts_in_schedule,
            self.min_slotframe_size,
        )
        if requested_sf_len < minimum_allowed_sf:
            sf_len = (
                current_sf_len
                if current_sf_len >= minimum_allowed_sf
                else self._safe_slotframe_at_least(minimum_allowed_sf)
            )
            applied_action = 2
            action_overridden = True
            action_override_reason = (
                "requested_slotframe_below_minimum "
                f"({requested_sf_len} < {minimum_allowed_sf})"
            )
            self.logger.debug(
                "Applying lower slotframe bound: action=%d requested_sf_len=%d "
                "minimum_allowed_sf=%d applied_sf_len=%d",
                raw_action,
                requested_sf_len,
                minimum_allowed_sf,
                sf_len,
            )
        elif requested_sf_len > self.action_max_slotframe_size:
            sf_len = current_sf_len
            applied_action = 2
            action_overridden = True
            action_override_reason = (
                "requested_slotframe_above_max "
                f"({requested_sf_len} > {self.action_max_slotframe_size})"
            )
            self.logger.debug(
                "Applying upper slotframe bound: action=%d requested_sf_len=%d "
                "max_slotframe_size=%d applied_sf_len=%d",
                raw_action,
                requested_sf_len,
                self.action_max_slotframe_size,
                current_sf_len,
            )
        # Set the SF size
        self.controller.current_slotframe_size = sf_len
        # Send the entire TSCH schedule
        self.controller.send_tsch_schedules()
        # We now wait until we reach the processing_window
        attempts = 0
        while (not self.controller.wait()):
            attempts += 1
            self.controller.send_tsch_schedules()
            if attempts % 10 == 0:
                seq = getattr(self.controller.packet_dissector, 'sequence', None)
                if seq is not None:
                    self.logger.info(
                        "Waiting for processing window: attempt %d, current sequence=%d",
                        attempts, seq
                    )
                else:
                    self.logger.info(
                        "Waiting for processing window: attempt %d",
                        attempts
                    )
            if attempts >= self.max_wait_retries:
                self.logger.warning(
                    "Processing window wait exceeded %d attempts, truncating episode",
                    self.max_wait_retries
                )
                observation, info = self._get_obs()
                info.update({
                    'action': raw_action,
                    'applied_action': applied_action,
                    'requested_sf_len': requested_sf_len,
                    'applied_sf_len': sf_len,
                    'action_overridden': action_overridden,
                    'action_override_reason': action_override_reason,
                    'returned_reward': 0.0,
                    'terminated': False,
                    'truncated': True,
                    'wait_timeout': True,
                    'valid_cycle': False,
                    'wait_attempts': attempts,
                })
                return observation, 0.0, False, True, info
            time.sleep(0.1)
        observation, info = self._get_obs()
        done = False
        reward = info['reward']
        # self.max_slotframe_size is the maximum slotframe size
        # TODO: Set the maximum slotframe size at the creation
        # of the environment
        if (sf_len < minimum_allowed_sf or
                sf_len > self.action_max_slotframe_size):
            done = True
            reward = -4

        info.update({
            'action': raw_action,
            'applied_action': applied_action,
            'requested_sf_len': requested_sf_len,
            'applied_sf_len': sf_len,
            'action_overridden': action_overridden,
            'action_override_reason': action_override_reason,
            'returned_reward': reward,
            'terminated': done,
            'truncated': False,
            'wait_timeout': False,
            'valid_cycle': not done,
            'wait_attempts': attempts,
        })
        return observation, reward, done, False, info

    def _get_obs(self):
        state = self.controller.get_state()
        metrics = self.controller.calculate_reward(
            self.controller.alpha, self.controller.beta, self.controller.delta,
            state['current_sf_len'])
        # Append to the observations
        user_requirements = np.array(
            state['user_requirements'], dtype=np.float32)
        power_normalized = np.array(
            metrics['power_normalized'], dtype=np.float32)
        observation = np.append(user_requirements, power_normalized)
        delay_normalized = np.array(
            metrics['delay_normalized'], dtype=np.float32)
        observation = np.append(observation, delay_normalized)
        pdr_mean = np.array(metrics['pdr_mean'], dtype=np.float32)
        observation = np.append(observation, pdr_mean)
        last_ts_in_schedule = np.array(
            state['last_ts_in_schedule']/self.max_slotframe_size, dtype=np.float32)
        observation = np.append(
            observation, last_ts_in_schedule)
        slotframe_size = np.array(
            state['current_sf_len']/self.max_slotframe_size, dtype=np.float32)
        observation = np.append(
            observation, slotframe_size)
        metrics["episode_index"] = self._episode_index
        metrics["episode_initial_sf_len"] = self.episode_initial_sf_len
        metrics["episode_profile"] = self.episode_profile
        return observation, metrics

    """ Reset the environment, reset the routing and the TSCH schedules """

    def reset(self, seed=None, options=None):
        # We need the following line to seed self.np_random
        super().reset(seed=seed)
        options = dict(options or {})
        slotframe_size = self._select_initial_slotframe(options)
        self._episode_index += 1
        self.episode_initial_sf_len = slotframe_size
        # Reset the container controller
        self.controller.reset()
        # We get the network links, useful when calculating the routing
        has_network = getattr(self.controller, "network", None) is not None
        if has_network:
            last_error = "reset bootstrap did not produce a usable network graph"
            G = None
            path = None
            for graph_attempt in range(1, self.max_reset_graph_retries + 1):
                self._wait_for_processing_window(
                    f"reset bootstrap graph {graph_attempt}/{self.max_reset_graph_retries}"
                )
                G = self.controller.get_network_links()
                graph_nodes = (
                    G.number_of_nodes()
                    if G is not None and hasattr(G, "number_of_nodes")
                    else 0
                )
                graph_edges = (
                    G.number_of_edges()
                    if G is not None and hasattr(G, "number_of_edges")
                    else 0
                )
                if G is None or graph_nodes == 0:
                    last_error = "reset bootstrap produced an empty network graph"
                    self.logger.warning(
                        "%s on graph attempt %d/%d (nodes=%d, edges=%d)",
                        last_error,
                        graph_attempt,
                        self.max_reset_graph_retries,
                        graph_nodes,
                        graph_edges,
                    )
                else:
                    # Run the dijkstra algorithm with the current links
                    path = self.controller.compute_routes(G)
                    if path is not None:
                        break
                    last_error = "reset failed to compute routes"
                    self.logger.warning(
                        "%s on graph attempt %d/%d (nodes=%d, edges=%d)",
                        last_error,
                        graph_attempt,
                        self.max_reset_graph_retries,
                        graph_nodes,
                        graph_edges,
                    )
                if graph_attempt < self.max_reset_graph_retries:
                    time.sleep(self.reset_graph_retry_sleep)
            else:
                raise RuntimeError(last_error)
        else:
            # We now wait until we reach the processing_window
            self._wait_for_processing_window("reset bootstrap")
            G = self.controller.get_network_links()
            path = self.controller.compute_routes(G)
        # We now set the TSCH schedules for the current routing
        self.controller.compute_tsch_schedule(path, slotframe_size)
        # We now set and save the user requirements
        balanced = (0.4, 0.3, 0.3)
        energy = (0.8, 0.1, 0.1)
        delay = (0.1, 0.8, 0.1)
        reliability = (0.1, 0.1, 0.8)
        # Honor an explicit initial profile on the first reset. Later resets keep
        # the current profile so AppLayer switches are not undone mid-run.
        name_map = {
            'balanced': balanced,
            'energy': energy,
            'delay': delay,
            'pdr': reliability,
            'reliability': reliability,
        }
        initial = (os.environ.get('ELISE_INITIAL_PROFILE') or '').strip().lower()
        requirements_mode = (os.environ.get('ELISE_REQUIREMENTS_MODE') or '').strip().lower()
        cycle_flag = (os.environ.get('ELISE_REQUIREMENTS_CYCLE') or '').strip().lower()
        cycle_enabled = cycle_flag in {'1', 'true', 'yes', 'on'}
        explicit_initial = initial in name_map
        requested_profile = str(options.get("profile", "")).strip().lower()
        if requested_profile and requested_profile not in name_map:
            raise ValueError(
                "reset option profile must be one of balanced, delay, energy, "
                "reliability, or pdr"
            )
        # Keep current user requirements across resets so profile switches driven
        # by the AppLayer are not undone by TimeLimit resets.
        already_set = (self.controller.alpha + self.controller.beta + self.controller.delta) > 0
        profile_name = None
        if requested_profile:
            profile_name = (
                "reliability" if requested_profile == "pdr" else requested_profile
            )
            select_user_req = name_map[requested_profile]
            self.controller.user_requirements = select_user_req
        elif cycle_enabled and requirements_mode in {'profiles', 'roundrobin', 'cycle'}:
            # Round-robin through the predefined profiles on every reset so PPO
            # observes all objectives within a single training run.
            if not hasattr(self, "_profile_rr_order"):
                self._profile_rr_order = ['balanced', 'delay', 'energy', 'reliability']
                self._profile_rr_idx = -1
            self._profile_rr_idx = (self._profile_rr_idx + 1) % len(self._profile_rr_order)
            profile_name = self._profile_rr_order[self._profile_rr_idx]
            select_user_req = name_map[profile_name]
            self.controller.user_requirements = select_user_req
        elif not self._has_reset_once and explicit_initial:
            select_user_req = name_map[initial]
            self.controller.user_requirements = select_user_req
        elif already_set:
            select_user_req = (self.controller.alpha, self.controller.beta, self.controller.delta)
        elif explicit_initial:
            select_user_req = name_map[initial]
            self.controller.user_requirements = select_user_req
        else:
            select_user_req = balanced
            self.controller.user_requirements = select_user_req
        if profile_name is None:
            profile_name = {
                balanced: "balanced",
                delay: "delay",
                energy: "energy",
                reliability: "reliability",
            }.get(tuple(select_user_req), "custom")
        self.episode_profile = profile_name
        print(
            "[Env reset] user requirements selected:",
            f"alpha={select_user_req[0]:.2f},",
            f"beta={select_user_req[1]:.2f},",
            f"delta={select_user_req[2]:.2f},",
            f"initial_sf={slotframe_size}"
        )
        # Send the entire routes
        self.controller.send_routes()
        # Send the entire TSCH schedule
        self.controller.send_tsch_schedules()
        # Wait for the network to settle
        self._wait_for_processing_window(
            "reset schedule settle",
            on_retry=lambda: (
                self.controller.send_routes(),
                self.controller.send_tsch_schedules(),
            ),
        )
        # We now save all the observations
        # This is done for the numerical environment.
        # Keep a sensible default last TS; do not exceed initial slotframe
        # to avoid immediate invalid states.
        self.controller.last_tsch_link = 5
        self.controller.current_slotframe_size = slotframe_size
        # We now save the user requirements
        observation, info = self._get_obs()
        self._has_reset_once = True
        return observation, info  # reward, done, info can't be included

    def render(self, mode='console'):
        pass

    def close(self):
        pass
