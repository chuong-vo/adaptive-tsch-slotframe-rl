"""Cooja CSC parsing and per-run rendering."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

from .protocol import sha256_file


@dataclass(frozen=True)
class CscNode:
    node_id: int
    x: float
    y: float
    z: float
    mote_type: str


@dataclass(frozen=True)
class CscTopology:
    nodes: tuple[CscNode, ...]
    radio_model: str
    transmission_range: float
    interference_range: float
    success_ratio_tx: float
    success_ratio_rx: float


def _required_text(parent: ET.Element, path: str) -> str:
    element = parent.find(path)
    if element is None or element.text is None:
        raise ValueError(f"CSC is missing {path}")
    return element.text.strip()


def parse_csc(path: Path) -> CscTopology:
    tree = ET.parse(path)
    simulation = tree.getroot().find("simulation")
    if simulation is None:
        raise ValueError("CSC is missing the simulation element")

    mote_sources = {}
    for mote_type in simulation.findall("motetype"):
        identifier = _required_text(mote_type, "identifier")
        mote_sources[identifier] = _required_text(mote_type, "source")

    nodes = []
    for mote in simulation.findall("mote"):
        position = None
        node_id = None
        for interface in mote.findall("interface_config"):
            interface_name = (interface.text or "").strip()
            if interface_name.endswith(".Position"):
                position = (
                    float(_required_text(interface, "x")),
                    float(_required_text(interface, "y")),
                    float(_required_text(interface, "z")),
                )
            elif interface_name.endswith(".ContikiMoteID"):
                node_id = int(_required_text(interface, "id"))
        mote_type = _required_text(mote, "motetype_identifier")
        if node_id is None or position is None:
            raise ValueError("Every mote must have an ID and position")
        nodes.append(CscNode(node_id, *position, mote_sources[mote_type]))

    radio = simulation.find("radiomedium")
    if radio is None:
        raise ValueError("CSC is missing radiomedium")
    return CscTopology(
        nodes=tuple(sorted(nodes, key=lambda node: node.node_id)),
        radio_model=(radio.text or "").strip().splitlines()[0].split(".")[-1],
        transmission_range=float(_required_text(radio, "transmitting_range")),
        interference_range=float(_required_text(radio, "interference_range")),
        success_ratio_tx=float(_required_text(radio, "success_ratio_tx")),
        success_ratio_rx=float(_required_text(radio, "success_ratio_rx")),
    )


def render_run_csc(
    template: Path,
    destination: Path,
    *,
    cooja_seed: int,
    port: int,
    title: str,
) -> str:
    tree = ET.parse(template)
    root = tree.getroot()
    simulation = root.find("simulation")
    if simulation is None:
        raise ValueError("CSC is missing the simulation element")
    simulation.find("title").text = title
    simulation.find("randomseed").text = str(int(cooja_seed))

    serial_plugins = [
        plugin
        for plugin in root.findall("plugin")
        if "SerialSocketServer" in (plugin.text or "")
    ]
    if len(serial_plugins) != 1:
        raise ValueError("CSC must contain exactly one SerialSocketServer plugin")
    port_element = serial_plugins[0].find("plugin_config/port")
    if port_element is None:
        raise ValueError("SerialSocketServer is missing its port")
    port_element.text = str(int(port))

    for script_file in root.findall("plugin/plugin_config/scriptfile"):
        if (script_file.text or "").strip().endswith("coojalogger.js"):
            script_file.text = "[CONTIKI_DIR]/examples/elise/coojalogger.js"

    destination.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space="  ")
    tree.write(destination, encoding="UTF-8", xml_declaration=True)
    return sha256_file(destination)


def render_topology_csc(
    template: Path,
    destination: Path,
    *,
    nodes: list[CscNode],
    sink_id: int,
    title: str,
    transmission_range: float,
    interference_range: float,
    success_ratio_tx: float,
    success_ratio_rx: float,
    app_interval_seconds: int,
    port: int = 60001,
    cooja_seed: int = 0,
) -> str:
    """Render a fixed topology/context without mutating the source CSC."""
    if not nodes or len({node.node_id for node in nodes}) != len(nodes):
        raise ValueError("Generated CSC nodes must have unique IDs")
    if sink_id not in {node.node_id for node in nodes}:
        raise ValueError("Generated CSC is missing its sink")
    if app_interval_seconds < 1:
        raise ValueError("Application interval must be positive")

    tree = ET.parse(template)
    root = tree.getroot()
    simulation = root.find("simulation")
    if simulation is None:
        raise ValueError("CSC is missing the simulation element")
    simulation.find("title").text = title
    simulation.find("randomseed").text = str(int(cooja_seed))

    radio = simulation.find("radiomedium")
    if radio is None:
        raise ValueError("CSC is missing radiomedium")
    radio.find("transmitting_range").text = str(float(transmission_range))
    radio.find("interference_range").text = str(float(interference_range))
    radio.find("success_ratio_tx").text = str(float(success_ratio_tx))
    radio.find("success_ratio_rx").text = str(float(success_ratio_rx))

    mote_types = simulation.findall("motetype")
    identifiers = {
        _required_text(mote_type, "source"): _required_text(mote_type, "identifier")
        for mote_type in mote_types
    }
    sink_identifier = next(
        (identifier for source, identifier in identifiers.items() if "sdn-tsch-sink" in source),
        None,
    )
    node_identifier = next(
        (identifier for source, identifier in identifiers.items() if "sdn-tsch-node" in source),
        None,
    )
    if sink_identifier is None or node_identifier is None:
        raise ValueError("CSC must define both sink and source mote types")

    defines = (
        f"SDN_CONF_DATA_PACKET_INTERVAL={int(app_interval_seconds)},"
        f"ORCHESTRA_CONF_UNICAST_PERIOD={len(nodes)}"
    )
    for mote_type in mote_types:
        source = _required_text(mote_type, "source")
        commands = mote_type.find("commands")
        if commands is None:
            raise ValueError("CSC mote type is missing build commands")
        if "sdn-tsch-node" in source:
            commands.text = (
                "make TARGET=cooja clean\n"
                "make -j$(CPUS) sdn-tsch-node.cooja TARGET=cooja "
                f"DEFINES={defines}"
            )
        elif "sdn-tsch-sink" in source:
            commands.text = (
                "make TARGET=cooja clean\n"
                "make -j$(CPUS) sdn-tsch-sink.cooja TARGET=cooja "
                "WITH_SERIAL_SDN_CONTROLLER=1 "
                f"DEFINES=ORCHESTRA_CONF_UNICAST_PERIOD={len(nodes)}"
            )

    existing_motes = simulation.findall("mote")
    sink_template = None
    source_template = None
    for mote in existing_motes:
        identifier = _required_text(mote, "motetype_identifier")
        if identifier == sink_identifier and sink_template is None:
            sink_template = deepcopy(mote)
        elif identifier == node_identifier and source_template is None:
            source_template = deepcopy(mote)
    if sink_template is None or source_template is None:
        raise ValueError("CSC must contain sink and source mote templates")
    for mote in existing_motes:
        simulation.remove(mote)

    for node in sorted(nodes, key=lambda value: value.node_id):
        mote = deepcopy(sink_template if node.node_id == sink_id else source_template)
        for interface in mote.findall("interface_config"):
            interface_name = (interface.text or "").strip()
            if interface_name.endswith(".Position"):
                interface.find("x").text = str(float(node.x))
                interface.find("y").text = str(float(node.y))
                interface.find("z").text = str(float(node.z))
            elif interface_name.endswith(".ContikiMoteID"):
                interface.find("id").text = str(int(node.node_id))
        mote.find("motetype_identifier").text = (
            sink_identifier if node.node_id == sink_id else node_identifier
        )
        simulation.append(mote)

    serial_plugins = [
        plugin for plugin in root.findall("plugin")
        if "SerialSocketServer" in (plugin.text or "")
    ]
    if len(serial_plugins) != 1:
        raise ValueError("CSC must contain exactly one SerialSocketServer plugin")
    serial_plugins[0].find("mote_arg").text = "0"
    serial_plugins[0].find("plugin_config/port").text = str(int(port))

    for plugin in root.findall("plugin"):
        if "TimeLine" not in (plugin.text or ""):
            continue
        plugin_config = plugin.find("plugin_config")
        if plugin_config is None:
            continue
        for mote_element in plugin_config.findall("mote"):
            plugin_config.remove(mote_element)
        for mote_index in reversed(range(len(nodes))):
            mote_element = ET.Element("mote")
            mote_element.text = str(mote_index)
            plugin_config.insert(0, mote_element)

    for script_file in root.findall("plugin/plugin_config/scriptfile"):
        if (script_file.text or "").strip().endswith("coojalogger.js"):
            script_file.text = "[CONTIKI_DIR]/examples/elise/coojalogger.js"

    destination.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space="  ")
    tree.write(destination, encoding="UTF-8", xml_declaration=True)
    return sha256_file(destination)
