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

import os

# Default values
DEFAULT_SCRIPT_FOLDER = "examples/elise"
DEFAULT_SIM_SCRIPT = "cooja-orchestra.csc"
DEFAULT_PORT = 60001

# Keys in the JSON configuration file
SCRIPT_FOLDER = "script_folder"
SOURCE = "source"
SIMULATION_SCRIPT = "simulation_script"
PORT = "port"


class CONTIKIConfig:
    """This class represents the authentication settings for a connection to an
    MQTT broker.

    Attributes:
        username (str): The username to authenticate to the MQTT broker. `None`
            if there's no authentication.
        password (str): The password to authenticate to the MQTT broker. Can be
            `None`.
    """

    def __init__(self, script_folder=None, source=None,
                 simulation_script=None, port=None):
        """Initialize a :class:`.MQTTAuthConfig` object.

        Args:
            username (str, optional): The username to authenticate to the MQTT
                broker. `None` if there's no authentication.
            password (str, optional): The password to authenticate to the MQTT
                broker. Can be `None`.

        All arguments are optional.
        """
        self.script_folder = script_folder
        self.source = source
        self.simulation_script = simulation_script
        self.port = port

    @classmethod
    def from_json(cls, json_object=None):
        """Initialize a :class:`.MQTTAuthConfig` object with settings from a
        JSON object.

        Args:
            json_object (optional): The JSON object with the MQTT
                authentication settings. Defaults to {}.

        Returns:
            :class:`.MQTTAuthConfig`: An object with the MQTT authentication
            settings.

        The JSON object should have the following format:

        {
            "scheduler": "Contention Free Scheduler",
            "max_channel": 3,
            "max_slotframe": 500,
            "slot_duration": 10
        }
        """
        if json_object is None:
            json_object = {}

        def _expand(value):
            if isinstance(value, str):
                return os.path.expanduser(os.path.expandvars(value))
            return value

        # Expand env/user in provided values
        script_folder = json_object.get(SCRIPT_FOLDER, DEFAULT_SCRIPT_FOLDER)
        source = _expand(json_object.get(SOURCE))
        simulation_script = json_object.get(SIMULATION_SCRIPT, DEFAULT_SIM_SCRIPT)
        port = json_object.get(PORT, DEFAULT_PORT)

        # Fallbacks for Contiki source
        if not source or (isinstance(source, str) and len(source.strip()) == 0):
            source = os.environ.get('CONTIKI_NG') or os.environ.get('CNG_PATH')

        if not source:
            # Try to infer from repository layout
            here = os.path.dirname(os.path.abspath(__file__))
            repo_path = os.path.normpath(os.path.join(here, '..', '..'))
            candidates = [
                os.path.join(repo_path, 'contiki-ng'),
                os.path.normpath(os.path.join(repo_path, '..', 'contiki-ng')),
            ]
            for c in candidates:
                if os.path.isdir(c):
                    source = c
                    break

        return cls(script_folder=script_folder,
                   source=source,
                   simulation_script=simulation_script,
                   port=port)
