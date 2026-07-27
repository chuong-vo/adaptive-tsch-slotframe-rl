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
from sdwsn_controller.mqtt.mqtt import MQTTClient

import logging
import json
import random
import os


logger = logging.getLogger(f'main.{__name__}')


def _profile_signature(profile):
    return (
        round(float(profile['alpha']), 6),
        round(float(profile['beta']), 6),
        round(float(profile['delta']), 6),
    )


# Topics
NETWORK_RECONFIG = "network/reconfiguration/+"
NEIGHBORS = "network/information/neighbors"
RL = "network/information/rl"
TSCH_SECHEDULES = "network/information/tsch/schedules"
ROUTES = "network/information/routing/routes"
DATA = "network/information/sensed_data"
ENERGY = "network/performance_metrics/energy"
LATENCY = "network/performance_metrics/latency"
PDR = "network/performance_metrics/pdr"
USER_REQ_GET = "network/user_requirements/get"
USER_REQ_SET = "network/user_requirements/set"
USER_REQ_CURRENT = "network/user_requirements/set"


class AppLayer(MQTTClient):
    def __init__(
            self,
            config,
            controller,
    ):
        self.name = "MQTT based application layer"
        self.controller = controller
        self._cycle_counter = 0
        self._last_profile = None
        # Profile switch configuration (env overrides)
        # Default per paper: switch every 40 iterations, round-robin
        try:
            self._profile_switch_every = int(os.environ.get('ELISE_PROFILE_SWITCH_EVERY', '40'))
            if self._profile_switch_every <= 0:
                self._profile_switch_every = 40
        except Exception:
            self._profile_switch_every = 40
        # Source of truth for switching: only AppLayer (default), can be disabled by setting to 'longrun'.
        self._profile_switch_source = os.environ.get('ELISE_PROFILE_SWITCH_SOURCE', 'applayer').strip().lower()
        self._profile_switch_mode = os.environ.get('ELISE_PROFILE_SWITCH_MODE', 'roundrobin').strip().lower()
        # Paper order: balanced -> delay -> energy -> pdr
        order_env = os.environ.get('ELISE_PROFILE_ORDER', 'balanced,delay,energy,pdr')
        name_to_profile = {
            'balanced': {"alpha": 0.4, "beta": 0.3, "delta": 0.3},
            'energy': {"alpha": 0.8, "beta": 0.1, "delta": 0.1},
            'delay': {"alpha": 0.1, "beta": 0.8, "delta": 0.1},
            'pdr': {"alpha": 0.1, "beta": 0.1, "delta": 0.8},
            'reliability': {"alpha": 0.1, "beta": 0.1, "delta": 0.8},
        }
        seq = []
        for token in order_env.split(','):
            prof = name_to_profile.get(token.strip().lower())
            if prof:
                seq.append(prof)
        self._profiles_seq = seq or [
            name_to_profile['balanced'],
            name_to_profile['delay'],
            name_to_profile['energy'],
            name_to_profile['pdr'],
        ]
        initial_profile_name = os.environ.get('ELISE_INITIAL_PROFILE', 'balanced').strip().lower()
        initial_profile = name_to_profile.get(initial_profile_name)
        self._rr_idx = -1
        if initial_profile is not None:
            self._last_profile = initial_profile
            initial_signature = _profile_signature(initial_profile)
            for idx, profile in enumerate(self._profiles_seq):
                if _profile_signature(profile) == initial_signature:
                    self._rr_idx = idx
                    self._last_profile = profile
                    break
        # Optional verbose cycle logging
        self._log_cycle_counter = (os.environ.get('ELISE_LOG_CYCLE_COUNTER', '0').strip().lower() in {'1','true','yes','on'})

        logger.info(
            "AppLayer profile switching | source=%s | every=%d | mode=%s | initial=%s | rr_idx=%d | order=%s",
            self._profile_switch_source,
            self._profile_switch_every,
            self._profile_switch_mode,
            initial_profile_name,
            self._rr_idx,
            ",".join([f"({p['alpha']},{p['beta']},{p['delta']})" for p in self._profiles_seq])
        )
        super().__init__(config)

    def initialize(self):
        return super().initialize()

    def on_connect(self, client, userdata, flags, result_code):
        """Callback that is called when the audio player connects to the MQTT
        broker."""
        super().on_connect(client, userdata, flags, result_code)
        self.mqtt.subscribe(NETWORK_RECONFIG)
        self.mqtt.subscribe(USER_REQ_SET)
        self.mqtt.subscribe(USER_REQ_GET)
        self.mqtt.message_callback_add(
            NETWORK_RECONFIG, self.network_reconfig_process)
        self.mqtt.message_callback_add(
            USER_REQ_SET, self.user_requirements_set)
        self.mqtt.message_callback_add(
            USER_REQ_GET, self.user_requirements_get)
        # logger.info('Subscribed to %s topic.', NETWORK_RECONFIG)

    def user_requirements_set(self, client, userdata, message):
        # print("user requirements received")
        data = dict(
            topic=message.topic,
            payload=message.payload.decode()
        )
        payload = json.loads(data['payload'])
        # print(payload)
        self.controller.alpha = payload['alpha']
        self.controller.beta = payload['beta']
        self.controller.delta = payload['delta']

    def user_requirements_get(self, client, userdata, message):
        # print("get requirements received")
        message = json.dumps({'alpha': self.controller.alpha,
                              'beta': self.controller.beta,
                              'delta': self.controller.delta})
        self.mqtt.publish(USER_REQ_CURRENT,
                          message)

    def network_reconfig_process(self):
        """ Callback that is called when the controller receives a
        NETWORK_RECONFIG message on MQTT.
        """
        pass

    def send_energy(self, id, seq, energy):
        # message = json.dumps({'id': id,
        #                       'seq': seq,
        #                       'energy': energy})

        # self.mqtt.publish(ENERGY,
        #                   message)
        # logger.debug('Published message on MQTT topic:')
        # logger.debug(f'Topic: {ENERGY}')
        # logger.debug(f'Message: {message}')
        pass

    def send_rl_info(self, data):
        message = json.dumps(data)
        self.mqtt.publish(RL,
                          message)
        # logger.debug('Published message on MQTT topic:')
        # logger.debug(f'Topic: {RL}')
        # logger.debug(f'Message: {message}')
        self._cycle_counter += 1
        if self._log_cycle_counter:
            logger.info(
                "AppLayer cycle_counter=%d (switch_every=%d)",
                self._cycle_counter,
                self._profile_switch_every,
            )
        if (
            self._profile_switch_source == 'applayer'
            and self._profile_switch_every > 0
            # The updated requirements are visible in the same env.step result,
            # so switch at N+1 to keep the first N recorded rows on the old profile.
            and self._cycle_counter > 1
            and ((self._cycle_counter - 1) % self._profile_switch_every == 0)
        ):
            self._publish_user_requirements_update()

    def send_latency(self, id, seq, delay):
        # message = json.dumps({'id': id,
        #                       'seq': seq,
        #                       'delay': delay})
        # self.mqtt.publish(LATENCY, message)
        # logger.debug('Published message on MQTT topic:')
        # logger.debug(f'Topic: {LATENCY}')
        # logger.debug(f'Message: {message}')
        pass

    def send_pdr(self, id, seq, pdr):
        # message = json.dumps({'id': id,
        #                       'seq': seq,
        #                       'pdr': pdr})
        # self.mqtt.publish(PDR, message)
        # logger.debug('Published message on MQTT topic:')
        # logger.debug(f'Topic: {PDR}')
        # logger.debug(f'Message: {message}')
        pass

    def _publish_user_requirements_update(self):
        """Publish a new user requirement profile on MQTT every N cycles."""
        if self._profile_switch_mode == 'roundrobin':
            self._rr_idx = (self._rr_idx + 1) % len(self._profiles_seq)
            next_profile = self._profiles_seq[self._rr_idx]
        else:
            candidates = [p for p in self._profiles_seq if p != self._last_profile] or self._profiles_seq
            next_profile = random.choice(candidates)
        self._last_profile = next_profile
        payload = json.dumps(next_profile)
        logger.info(
            "Publishing automatic user requirement update at AppLayer counter %d: %s",
            self._cycle_counter,
            payload
        )
        self.mqtt.publish(USER_REQ_SET, payload)
