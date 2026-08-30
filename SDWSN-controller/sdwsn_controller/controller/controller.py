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

import logging

import os
import signal
from pathlib import Path

from rich.progress import Progress

from sdwsn_controller.controller.base_controller import BaseController
from subprocess import Popen, STDOUT, TimeoutExpired

from time import sleep


logger = logging.getLogger(f'main.{__name__}')


class Controller(BaseController):
    def __init__(
        self,
        config
    ):
        """
        This controller is intended to run run Cooja natively and without GUI.

        Args:
            contiki_source (str, optional): Path to the Contiki-NG source folder. Defaults to '/Users/fernando/contiki-ng'.
            simulation_folder (str, optional): Folder where the .csc file resides. Defaults to 'examples/elise'.
            simulation_script (str, optional): The .csc file to run. Defaults to 'cooja-elise.csc'.
            socket (SinkComm object, optional): Serial connection to the sink. Defaults to None.
            db (Database object, optional): Database. Defaults to None.
            reward_processing (RewardProcessing object, optional):Reward processing for RL. Defaults to None.
            packet_dissector (Dissector object, optional): Packet dissector. Defaults to None.
            processing_window (int, optional): Number of packets for a new cycle. Defaults to 200.
            routing (Router object, optional): Centralized routing algorithm. Defaults to None.
            tsch_scheduler (Scheduler object, optional): Centralized TSCH scheduler. Defaults to None.
        """

        # self.config = config

        # assert isinstance(contiki_source, str)
        # assert isinstance(simulation_folder, str)
        # assert isinstance(simulation_script, str)

        logger.info("Building native controller")

        # Controller related variables
        self.__proc = None
        self.__proc_output = None

        self.__contiki_source = config.contiki.source
        self.__simulation_folder = os.path.join(
            self.__contiki_source, config.contiki.script_folder)
        configured_log_dir = getattr(config.contiki, "log_dir", None)
        self.__log_dir = os.path.abspath(
            configured_log_dir or self.__simulation_folder
        )
        os.makedirs(self.__log_dir, exist_ok=True)
        self.__cooja_log = os.path.join(self.__log_dir, 'COOJA.log')
        self.__testlog = os.path.join(self.__log_dir, 'COOJA.testlog')
        self.__cooja_stdout_log = os.path.join(
            self.__log_dir, 'COOJA.stdout.log')
        self.__cooja_path = os.path.normpath(
            os.path.join(self.__contiki_source, "tools", "cooja"))
        configured_script = Path(config.contiki.simulation_script)
        if configured_script.is_absolute():
            self.__simulation_script = str(configured_script)
        else:
            self.__simulation_script = os.path.join(
                self.__simulation_folder,
                str(configured_script),
            )

        self.__new_simulation_script = None

        self.__port = config.contiki.port
        self.__preserve_logs = getattr(config.contiki, "preserve_logs", False)
        self.__startup_timeout = max(
            1,
            int(getattr(config.contiki, "startup_timeout", 300)),
        )

        logger.info(f"Contiki source: {self.__contiki_source}")
        logger.info(f"Cooja log: {self.__cooja_log}")
        logger.info(f"Cooja test log: {self.__testlog}")
        logger.info(f"Cooja path: {self.__cooja_path}")
        logger.info(f"Simulation folder: {self.__simulation_folder}")
        logger.info(f"Simulation script: {self.__simulation_script}")
        logger.info(f"Cooja runtime log folder: {self.__log_dir}")

        super().__init__(
            config
        )

    # Controller related functions

    def timeout(self):
        sleep(0.02)

    def __cooja_stdout_tail(self, lines=40):
        try:
            with open(self.__cooja_stdout_log, "r") as f:
                return "".join(f.readlines()[-lines:])
        except OSError:
            return ""

    @property
    def cooja_log_path(self):
        return self.__cooja_log

    @property
    def cooja_testlog_path(self):
        return self.__testlog

    @property
    def cooja_stdout_log_path(self):
        return self.__cooja_stdout_log

    @property
    def simulation_script_path(self):
        return self.__simulation_script

    def cooja_is_running(self):
        return self.__proc is not None and self.__proc.poll() is None

    def start_cooja(self):
        # cleanup
        try:
            os.remove(self.__testlog)
        except FileNotFoundError:
            pass
        except PermissionError as ex:
            raise PermissionError("Cannot remove previous Cooja output") from ex

        try:
            os.remove(self.__cooja_log)
        except FileNotFoundError:
            pass
        except PermissionError as ex:
            raise PermissionError("Cannot remove previous Cooja log") from ex

        if self.__proc_output is not None:
            try:
                self.__proc_output.close()
            except OSError:
                pass
            self.__proc_output = None

        # We need to overwrite the port of the serial socket in the
        # csc simulation file
        with open(self.__simulation_script, "r") as input_file:
            simulation_path = Path(self.__simulation_script)
            self.__new_simulation_script = str(
                simulation_path.with_name(
                    f"{simulation_path.stem}-port-{self.__port}.csc"
                )
            )
            filedata = input_file.read()
            # Replace the target string
            filedata = filedata.replace(str(60001), str(self.__port))
            with open(self.__new_simulation_script, "w") as new_tmp_file:
                new_tmp_file.write(filedata)

        cooja_args = " ".join([
            f"-nogui={self.__new_simulation_script}",
            f"-contiki={self.__contiki_source}",
            f"-logdir={self.__log_dir}",
            "-logname=COOJA",
        ])
        args = ["./gradlew", "run", f"--args={cooja_args}"]

        self.__proc_output = open(self.__cooja_stdout_log, "w")
        self.__proc = Popen(args, stdout=self.__proc_output, stderr=STDOUT,
                            cwd=self.__cooja_path, universal_newlines=True,
                            start_new_session=True)

        status = 0
        with Progress(transient=True) as progress:
            task1 = progress.add_task(
                "[red]Waiting for Cooja to start...", total=self.__startup_timeout)

            while not progress.finished:
                progress.update(task1, advance=1)
                if self.__proc.poll() is not None:
                    break
                if os.access(self.__cooja_log, os.R_OK):
                    status = 1
                    progress.update(task1, completed=self.__startup_timeout)
                sleep(1)

        if status == 0:
            output_tail = self.__cooja_stdout_tail()
            raise Exception(
                "Failed to start Cooja "
                f"(returncode={self.__proc.poll()}). "
                f"See {self.__cooja_stdout_log}\n{output_tail}"
            )

        self.__wait_socket_running()

    def __cooja_socket_status(self):
        # This method checks whether the socket is currently running in Cooja
        if not os.access(self.__cooja_log, os.R_OK):
            logger.warning(
                'The input file "{}" does not exist'.format(self.__cooja_log))

        is_listening = False
        is_fatal = False

        with open(self.__cooja_log, "r") as f:
            contents = f.read()
            read_line = "Listening on port: " + \
                str(self.__port)
            fatal_line = "Simulation not loaded"
            is_listening = read_line in contents
            # logger.info(f'listening result: {is_listening}')
            is_fatal = fatal_line in contents
        return is_listening, is_fatal

    def __wait_socket_running(self):
        cooja_socket_active, fatal_error = self.__cooja_socket_status()
        status = 0
        with Progress(transient=True) as progress:
            task1 = progress.add_task(
                "[red]Setting up Cooja simulation...", total=self.__startup_timeout)
            while not progress.finished:
                progress.update(task1, advance=1)
                if self.__proc.poll() is not None:
                    output_tail = self.__cooja_stdout_tail()
                    raise Exception(
                        "Cooja exited before the socket became active "
                        f"(returncode={self.__proc.poll()}). "
                        f"See {self.__cooja_stdout_log}\n{output_tail}"
                    )
                cooja_socket_active, fatal_error = self.__cooja_socket_status()
                if fatal_error:
                    output_tail = self.__cooja_stdout_tail()
                    raise Exception(
                        "Simulation compilation error. "
                        f"See {self.__cooja_stdout_log}\n{output_tail}"
                    )
                if cooja_socket_active:
                    status = 1
                    progress.update(task1, completed=self.__startup_timeout)

                sleep(1)

        if status == 0:
            raise Exception("Failed to start the simulation.")

        logger.info("Cooja socket interface is up and running")

    def start(self):
        # Get the simulation running
        self.start_cooja()
        super().start()

    def stop(self):
        if self.__proc:
            if self.__proc.poll() is None:
                try:
                    os.killpg(os.getpgid(self.__proc.pid), signal.SIGTERM)
                    self.__proc.wait(timeout=15)
                except TimeoutExpired:
                    os.killpg(os.getpgid(self.__proc.pid), signal.SIGKILL)
                    self.__proc.wait()
                except ProcessLookupError:
                    pass
            self.__proc = None
        if self.__proc_output is not None:
            try:
                self.__proc_output.close()
            except OSError:
                pass
            self.__proc_output = None
        # Delete the tmp simulation csc file if exists
        if self.__new_simulation_script is not None:
            if os.path.exists(self.__new_simulation_script):
                os.remove(self.__new_simulation_script)
        if not self.__preserve_logs:
            if os.path.exists(self.__cooja_log):
                os.remove(self.__cooja_log)
            if os.path.exists(self.__testlog):
                os.remove(self.__testlog)
        super().stop()

    def reset(self):
        # logger.info('Resetting controller, etc.')
        self.stop()
        self.start()
