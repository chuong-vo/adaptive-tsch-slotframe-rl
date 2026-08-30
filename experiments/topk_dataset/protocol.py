"""Protocol loading, validation, and deterministic identifiers."""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable

from . import PROTOCOL_VERSION, REPO_ROOT


class ProtocolError(ValueError):
    """Raised when a collection protocol is incomplete or inconsistent."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("ascii"))


def deterministic_seed(*parts: object) -> int:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def valid_slotframes(minimum: int, maximum: int, coprime_with: Iterable[int]) -> list[int]:
    factors = tuple(int(value) for value in coprime_with)
    return [
        value
        for value in range(int(minimum), int(maximum) + 1)
        if all(math.gcd(value, factor) == 1 for factor in factors)
    ]


def load_protocol(path: Path) -> dict[str, Any]:
    path = path.resolve()
    protocol = json.loads(path.read_text(encoding="utf-8"))
    if protocol.get("protocol_version") != PROTOCOL_VERSION:
        raise ProtocolError(
            f"Expected protocol_version={PROTOCOL_VERSION}, got "
            f"{protocol.get('protocol_version')!r}"
        )

    required_sections = {
        "topology",
        "radio",
        "traffic",
        "slotframe",
        "collection",
        "controller",
    }
    missing = sorted(required_sections.difference(protocol))
    if missing:
        raise ProtocolError(f"Missing protocol sections: {', '.join(missing)}")

    protocol = deepcopy(protocol)
    template = Path(protocol["topology"]["template_csc"])
    if not template.is_absolute():
        template = REPO_ROOT / template
    if not template.is_file():
        raise ProtocolError(f"Template CSC does not exist: {template}")
    protocol["topology"]["template_csc"] = str(template.resolve())

    slotframe = protocol["slotframe"]
    candidates = valid_slotframes(
        slotframe["minimum"],
        slotframe["maximum"],
        slotframe["coprime_with"],
    )
    if not candidates:
        raise ProtocolError("The configured slotframe domain is empty")
    if max(candidates) > int(slotframe["wire_maximum"]):
        raise ProtocolError("A slotframe candidate exceeds the wire-format limit")
    protocol["slotframe"]["candidates"] = candidates

    collection = protocol["collection"]
    seeds = [int(seed) for seed in collection["cooja_seeds"]]
    if len(seeds) != len(set(seeds)) or not seeds:
        raise ProtocolError("cooja_seeds must be a non-empty unique list")
    collection["cooja_seeds"] = seeds
    for key in (
        "warmup_cycles",
        "accepted_cycles",
        "max_attempts_per_cycle",
        "processing_window",
    ):
        if int(collection[key]) < 1:
            raise ProtocolError(f"collection.{key} must be positive")

    expected_nodes = int(protocol["topology"]["expected_node_count"])
    if expected_nodes < 2:
        raise ProtocolError("A topology needs one sink and at least one source")

    project_conf = REPO_ROOT / "contiki-ng" / "examples" / "sdn-tsch-node" / "project-conf.h"
    match = re.search(
        r"^\s*#define\s+SDN_CONF_DATA_PACKET_INTERVAL\s+(\d+)\s*$",
        project_conf.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    if match is None:
        raise ProtocolError("Cannot verify SDN_CONF_DATA_PACKET_INTERVAL")
    compiled_interval_ms = int(match.group(1)) * 1000
    if int(protocol["traffic"]["app_interval_ms"]) != compiled_interval_ms:
        raise ProtocolError(
            "traffic.app_interval_ms does not match the node firmware: "
            f"{protocol['traffic']['app_interval_ms']} != {compiled_interval_ms}"
        )
    return protocol
