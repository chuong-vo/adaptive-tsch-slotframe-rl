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
from sdwsn_controller.tsch.scheduler import TSCHScheduler
import random
from sdwsn_controller.tsch.schedule import cell_type
from sdwsn_controller.exceptions import SchedulingInfeasibleError
import logging
import hashlib
import json

logger = logging.getLogger(f'main.{__name__}')


def routing_links(path):
    """Return each directed routing-tree link exactly once."""
    links = set()
    for node_path in path.values():
        for index in range(len(node_path) - 1):
            links.add((int(node_path[index]), int(node_path[index + 1])))
    return sorted(links)


def deterministic_cells(path, schedule_seed, max_channels):
    """Build a schedule that is stable across slotframe candidates."""
    if max_channels < 1:
        raise SchedulingInfeasibleError("At least one TSCH channel is required")

    links = routing_links(path)
    rng = random.Random(int(schedule_seed))
    rng.shuffle(links)
    cells = []
    for timeslot, (tx, rx) in enumerate(links):
        cells.append({
            "tx": tx,
            "rx": rx,
            "timeslot": timeslot,
            "channel": rng.randrange(max_channels),
        })
    return cells


def schedule_sha256(cells):
    canonical = json.dumps(
        sorted(cells, key=lambda cell: (cell["timeslot"], cell["tx"], cell["rx"])),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


class ContentionFreeScheduler(TSCHScheduler):
    def __init__(
            self,
            network
    ) -> None:
        self.__name = "Contention Free Scheduler"
        super().__init__(
            network=network
        )

    @property
    def name(self):
        return self.__name

    def run(self, path, current_sf_size, schedule_seed=None, deterministic=False):
        logger.debug(
            f"running contention free scheduler for sf size {current_sf_size}")
        self.network.tsch_clear()
        self.network.tsch_slotframe_size = current_sf_size
        if deterministic or schedule_seed is not None:
            cells = deterministic_cells(
                path,
                0 if schedule_seed is None else schedule_seed,
                self.network.tsch_max_ch,
            )
            if len(cells) > current_sf_size:
                raise SchedulingInfeasibleError(
                    f"{len(cells)} routing links do not fit in slotframe "
                    f"{current_sf_size}"
                )
            for cell in cells:
                tx_node = self.network.nodes_add(cell["tx"])
                rx_node = self.network.nodes_add(cell["rx"])
                tx_node.tsch_add_link(
                    cell_type.UC_TX,
                    cell["channel"],
                    cell["timeslot"],
                    rx_node.id,
                )
                rx_node.tsch_add_link(
                    cell_type.UC_RX,
                    cell["channel"],
                    cell["timeslot"],
                )
            self.network.tsch_print()
            return cells

        links = routing_links(path)
        # Keep the legacy convention of leaving the last offset unused, but
        # allocate from a finite pool so an infeasible request cannot spin.
        available_timeslots = list(range(max(0, int(current_sf_size) - 1)))
        if len(links) > len(available_timeslots):
            raise SchedulingInfeasibleError(
                f"{len(links)} routing links do not fit in the legacy "
                f"slotframe allocation of size {current_sf_size}"
            )
        if self.network.tsch_max_ch < 1:
            raise SchedulingInfeasibleError("At least one TSCH channel is required")
        random.shuffle(available_timeslots)
        for (tx_id, rx_id), ts in zip(links, available_timeslots):
            tx_node = self.network.nodes_add(tx_id)
            rx_node = self.network.nodes_add(rx_id)
            ch = random.randrange(self.network.tsch_max_ch)
            tx_node.tsch_add_link(cell_type.UC_TX, ch, ts, rx_node.id)
            rx_node.tsch_add_link(cell_type.UC_RX, ch, ts)
        # Print the schedule
        self.network.tsch_print()
        return None
