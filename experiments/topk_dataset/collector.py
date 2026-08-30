"""Direct-controller G0 collector with strict cycle acceptance gates."""

from __future__ import annotations

import json
import logging
import random
import shutil
import socket
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sdwsn_controller.config import CONTROLLERS, SDWSNControllerConfig
from sdwsn_controller.exceptions import (
    PacketEncodingError,
)
from sdwsn_controller.tsch.contention_free_scheduler import schedule_sha256

from . import REPO_ROOT, RUNNER_VERSION
from .csc import render_run_csc
from .measurement import CoojaLogCursor, CycleRejected, snapshot_cycle
from .prepare import source_provenance
from .protocol import deterministic_seed, sha256_file, sha256_json
from .storage import (
    RAW_CYCLE_FIELDS,
    REJECTED_CYCLE_FIELDS,
    RUN_SUMMARY_FIELDS,
    aggregate_completed_runs,
    write_csv_atomic,
    write_json_atomic,
)


LOGGER = logging.getLogger(__name__)


class CollectionError(RuntimeError):
    """Raised when a seed cannot be collected without weakening the protocol."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_id_for(context_id: str, cooja_seed: int) -> str:
    return f"{context_id}__cooja_seed_{int(cooja_seed)}"


def candidate_order(
    context_id: str,
    cooja_seed: int,
    candidates: list[int],
) -> list[int]:
    ordered = list(candidates)
    rng = random.Random(
        deterministic_seed(context_id, int(cooja_seed), "candidate-order")
    )
    rng.shuffle(ordered)
    return ordered


def build_runtime_config(
    protocol: dict[str, Any],
    *,
    run_csc: Path,
    log_dir: Path,
    port: int,
) -> dict[str, Any]:
    collection = protocol["collection"]
    controller = protocol["controller"]
    return {
        "my_example": "G0 deterministic slotframe collection",
        "controller_type": "native controller",
        "network": {
            "name": "Cooja",
            "processing_window": int(collection["processing_window"]),
            "stall_timeout": float(collection["stall_timeout_seconds"]),
            "control_flood_repetitions": int(
                collection.get("control_flood_repetitions", 1)
            ),
        },
        "sink_comm": {
            "name": "socket",
            "host_dev": "127.0.0.1",
            "port_baud": int(port),
        },
        "contiki": {
            "script_folder": "examples/elise",
            "source": str(REPO_ROOT / "contiki-ng"),
            "simulation_script": str(run_csc.resolve()),
            "port": int(port),
            "log_dir": str(log_dir.resolve()),
            "preserve_logs": True,
            "startup_timeout": int(collection["startup_timeout_seconds"]),
        },
        "tsch": {
            "scheduler": "Contention Free Scheduler",
            "max_channel": int(controller["max_channel"]),
            "max_slotframe": int(protocol["slotframe"]["wire_maximum"]),
            "slot_duration": int(controller["slot_duration_ms"]),
        },
        "routing": {"algo": "Dijkstra"},
        "reinforcement_learning": {
            "reward_processor": "EmulatedRewardProcessing",
            "max_episode_steps": 1,
        },
        "performance_metrics": {
            "energy": {"min": 0, "max": 5000, "norm_offset": 0.0},
            "delay": {"min": 0, "max": 15000, "norm_offset": 0.0},
            "pdr": {"min": 0, "max": 1, "norm_offset": 0.0},
        },
        "mqtt": {},
    }


def _assert_port_available(port: int, timeout_seconds: float = 90.0) -> None:
    deadline = time.monotonic() + float(timeout_seconds)
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(("127.0.0.1", int(port)))
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.5)
        finally:
            probe.close()
    raise CollectionError(
        f"TCP port {port} remained unavailable for {timeout_seconds:.1f}s; "
        "stop the old Cooja process first"
    ) from last_error


def _archive_incomplete_run(output_dir: Path, run_dir: Path) -> None:
    if not run_dir.exists() or (run_dir / "done.json").is_file():
        return
    archive_root = output_dir / "incomplete_attempts"
    archive_root.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = archive_root / f"{run_dir.name}__{suffix}"
    shutil.move(str(run_dir), str(destination))
    LOGGER.warning("Archived incomplete seed attempt at %s", destination)


def _wait_for_discovery_convergence(
    controller,
    expected_node_ids: list[int],
    timeout_seconds: float,
    stability_seconds: float,
) -> None:
    expected = set(int(node_id) for node_id in expected_node_ids)
    deadline = time.monotonic() + float(timeout_seconds)
    stable_since: float | None = None
    stable_ranks: tuple[tuple[int, int], ...] | None = None
    baseline_reports: dict[int, int] = {}
    while time.monotonic() < deadline:
        if not controller.cooja_is_running():
            raise CollectionError(
                "Cooja exited while waiting for topology discovery to converge"
            )
        joined = expected.intersection(controller.network.nodes)
        ranks = tuple(
            sorted(
                (node_id, int(controller.network.nodes[node_id].rank))
                for node_id in joined
            )
        )
        ranks_valid = (
            joined == expected
            and all(
                rank == 0 if node_id == 1 else 0 < rank < 255
                for node_id, rank in ranks
            )
        )
        if ranks_valid:
            now = time.monotonic()
            if ranks != stable_ranks:
                stable_ranks = ranks
                stable_since = now
                baseline_reports = {
                    node_id: int(
                        controller.network.nodes[node_id].na_report_count
                    )
                    for node_id in expected
                    if node_id != 1
                }
            fresh_reports = all(
                int(controller.network.nodes[node_id].na_report_count)
                > baseline_reports.get(node_id, 0)
                for node_id in expected
                if node_id != 1
            )
            if (
                fresh_reports
                and stable_since is not None
                and now - stable_since >= stability_seconds
            ):
                LOGGER.info(
                    "Topology discovery converged | nodes=%d | max_rank=%d | "
                    "stable=%.1fs",
                    len(ranks),
                    max(rank for _, rank in ranks),
                    stability_seconds,
                )
                return
        else:
            stable_ranks = None
            stable_since = None
            baseline_reports = {}
        time.sleep(0.1)
    missing = sorted(expected.difference(controller.network.nodes))
    unresolved = sorted(
        node_id
        for node_id in expected.intersection(controller.network.nodes)
        if (
            int(controller.network.nodes[node_id].rank) != 0
            if node_id == 1
            else not 0 < int(controller.network.nodes[node_id].rank) < 255
        )
    )
    raise CollectionError(
        "Timed out waiting for topology discovery convergence; "
        f"missing IDs: {missing}; unresolved-rank IDs: {unresolved}"
    )


def _send_with_retries(
    operation: Callable[[], bool],
    label: str,
    attempts: int = 3,
) -> None:
    for attempt in range(1, attempts + 1):
        if operation():
            return
        LOGGER.warning("%s failed on dissemination attempt %d/%d", label, attempt, attempts)
    raise CollectionError(f"{label} dissemination failed after {attempts} attempts")


def _preserve_mote_binaries(run_dir: Path) -> dict[str, str]:
    binary_paths: list[Path] = []
    for application in ("sdn-tsch-node", "sdn-tsch-sink"):
        app_dir = REPO_ROOT / "contiki-ng" / "examples" / application
        candidates = sorted(
            path for path in app_dir.rglob("*.cooja") if path.is_file()
        )
        if not candidates:
            raise CollectionError(
                f"Cooja did not produce a binary for {application}"
            )
        binary_paths.append(max(candidates, key=lambda path: path.stat().st_mtime_ns))
    destination_dir = run_dir / "binaries"
    destination_dir.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for source in binary_paths:
        application = source.parents[2].name
        destination = destination_dir / f"{application}.cooja"
        shutil.copy2(source, destination)
        hashes[str(destination.relative_to(run_dir))] = sha256_file(destination)
    return hashes


def _combined_binary_hash(binary_hashes: dict[str, str]) -> str:
    return sha256_json(binary_hashes)


def _write_run_checkpoints(
    run_dir: Path,
    accepted_rows: list[dict[str, Any]],
    warmup_rows: list[dict[str, Any]],
    rejected_rows: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]],
) -> None:
    write_csv_atomic(run_dir / "raw_cycles.csv", RAW_CYCLE_FIELDS, accepted_rows)
    write_csv_atomic(run_dir / "warmup_cycles.csv", RAW_CYCLE_FIELDS, warmup_rows)
    write_csv_atomic(
        run_dir / "rejected_cycles.csv",
        REJECTED_CYCLE_FIELDS,
        rejected_rows,
    )
    write_csv_atomic(
        run_dir / "run_summary.csv",
        RUN_SUMMARY_FIELDS,
        summary_rows,
    )


def _rejection_row(
    *,
    run_id: str,
    context_id: str,
    cooja_seed: int,
    candidate_index: int,
    slotframe: int,
    cycle_index: int,
    is_warmup: bool,
    attempt_index: int,
    cycle_sequence: int | str,
    reason_code: str,
    note: str,
    missing_node_ids: list[int],
    reporting_source_count: int,
    expected_source_count: int,
    wall_seconds: float,
    wait_attempts: int,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "context_id": context_id,
        "cooja_seed": int(cooja_seed),
        "candidate_index": candidate_index,
        "slotframe": slotframe,
        "cycle_index": cycle_index,
        "is_warmup": is_warmup,
        "attempt_index": attempt_index,
        "cycle_sequence": cycle_sequence,
        "reason_code": reason_code,
        "missing_node_ids": missing_node_ids,
        "reporting_source_count": reporting_source_count,
        "expected_source_count": expected_source_count,
        "stall_detected": reason_code == "STALL_TIMEOUT",
        "wait_attempts": wait_attempts,
        "wall_seconds": wall_seconds,
        "raw_note": note,
    }


def _collect_requested_cycle(
    controller,
    cursor: CoojaLogCursor,
    *,
    run_id: str,
    context_id: str,
    cooja_seed: int,
    candidate_index: int,
    slotframe: int,
    cycle_index: int,
    is_warmup: bool,
    attempt_index: int,
    expected_source_ids: list[int],
    install_schedule: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    network = controller.network
    expected_count = len(expected_source_ids)
    cycle_sequence: int | str = ""
    wait_attempts = 0
    cursor.poll()
    cycle_start_sim_us = cursor.last_sim_time_us
    started = time.monotonic()
    try:
        controller.current_slotframe_size = int(slotframe)
        if install_schedule and not controller.send_tsch_schedules():
            raise CycleRejected(
                "WAIT_RETRY_EXHAUSTED",
                "The TSCH schedule transaction was not acknowledged",
            )
        if not controller.send_tsch_cycle_marker():
            raise CycleRejected(
                "WAIT_RETRY_EXHAUSTED",
                "The TSCH measurement marker was not acknowledged",
            )
        cycle_sequence = network.cycle_sequence()
        wait_attempts = 1
        wait_ok = controller.wait()
        cursor.poll()
        wall_seconds = time.monotonic() - started
        expected_by_source = cursor.expected_by_source(
            int(cycle_sequence),
            expected_source_ids,
        )
        if not wait_ok:
            if not controller.cooja_is_running():
                reason = "COOJA_CRASH"
                note = "Cooja exited before the processing window completed"
            else:
                reason = "STALL_TIMEOUT"
                note = "The processing window made no progress before timeout"
            missing = sorted(set(expected_source_ids).difference(expected_by_source))
            return None, _rejection_row(
                run_id=run_id,
                context_id=context_id,
                cooja_seed=cooja_seed,
                candidate_index=candidate_index,
                slotframe=slotframe,
                cycle_index=cycle_index,
                is_warmup=is_warmup,
                attempt_index=attempt_index,
                cycle_sequence=cycle_sequence,
                reason_code=reason,
                note=note,
                missing_node_ids=missing,
                reporting_source_count=expected_count - len(missing),
                expected_source_count=expected_count,
                wall_seconds=wall_seconds,
                wait_attempts=wait_attempts,
            )

        metrics = snapshot_cycle(
            network,
            expected_source_ids=expected_source_ids,
            expected_by_source=expected_by_source,
            slotframe=slotframe,
            cycle_start_sim_us=cycle_start_sim_us,
            cycle_end_sim_us=cursor.last_sim_time_us,
            cycle_duration_wall_s=wall_seconds,
        )
        row = {
            "run_id": run_id,
            "context_id": context_id,
            "cooja_seed": int(cooja_seed),
            "candidate_index": candidate_index,
            "slotframe": slotframe,
            "cycle_index": cycle_index,
            "is_warmup": is_warmup,
            "cycle_sequence": cycle_sequence,
            "attempt_index": attempt_index,
            **metrics,
        }
        return row, None
    except CycleRejected as exc:
        cursor.poll()
        wall_seconds = time.monotonic() - started
        expected_by_source = (
            cursor.expected_by_source(int(cycle_sequence), expected_source_ids)
            if cycle_sequence != ""
            else {}
        )
        missing = exc.missing_node_ids or sorted(
            set(expected_source_ids).difference(expected_by_source)
        )
        return None, _rejection_row(
            run_id=run_id,
            context_id=context_id,
            cooja_seed=cooja_seed,
            candidate_index=candidate_index,
            slotframe=slotframe,
            cycle_index=cycle_index,
            is_warmup=is_warmup,
            attempt_index=attempt_index,
            cycle_sequence=cycle_sequence,
            reason_code=exc.reason_code,
            note=exc.note,
            missing_node_ids=missing,
            reporting_source_count=expected_count - len(missing),
            expected_source_count=expected_count,
            wall_seconds=wall_seconds,
            wait_attempts=wait_attempts,
        )
    except PacketEncodingError as exc:
        wall_seconds = time.monotonic() - started
        return None, _rejection_row(
            run_id=run_id,
            context_id=context_id,
            cooja_seed=cooja_seed,
            candidate_index=candidate_index,
            slotframe=slotframe,
            cycle_index=cycle_index,
            is_warmup=is_warmup,
            attempt_index=attempt_index,
            cycle_sequence=cycle_sequence,
            reason_code="ENCODING_ERROR",
            note=str(exc),
            missing_node_ids=[],
            reporting_source_count=0,
            expected_source_count=expected_count,
            wall_seconds=wall_seconds,
            wait_attempts=wait_attempts,
        )


def _sample_stdev(values: list[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def collect_seed(
    protocol: dict[str, Any],
    topology: dict[str, Any],
    output_dir: Path,
    *,
    cooja_seed: int,
    candidates: list[int],
    warmup_cycles: int,
    accepted_cycles: int,
    max_attempts_per_cycle: int,
    port: int,
    aggregate_on_complete: bool = True,
) -> str:
    context_id = topology["context_id"]
    run_id = run_id_for(context_id, cooja_seed)
    run_dir = output_dir / "runs" / run_id
    if (run_dir / "done.json").is_file():
        LOGGER.info("Skipping completed seed %s", cooja_seed)
        return "skipped"

    _archive_incomplete_run(output_dir, run_dir)
    _assert_port_available(
        port,
        float(protocol["collection"].get("port_release_timeout_seconds", 90.0)),
    )
    cooja_dir = run_dir / "cooja"
    cooja_dir.mkdir(parents=True, exist_ok=True)
    run_csc = cooja_dir / "run.csc"
    csc_sha256 = render_run_csc(
        Path(protocol["topology"]["template_csc"]),
        run_csc,
        cooja_seed=cooja_seed,
        port=port,
        title=f"G0 seed {cooja_seed}",
    )
    runtime_config = build_runtime_config(
        protocol,
        run_csc=run_csc,
        log_dir=cooja_dir,
        port=port,
    )
    runtime_config_path = run_dir / "controller.json"
    write_json_atomic(runtime_config_path, runtime_config)
    runtime_config_sha256 = sha256_json(runtime_config)

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    config_snapshot_sha256 = manifest["config_snapshot_sha256"]
    source = source_provenance()
    if source != manifest["source"]:
        raise CollectionError(
            "The working tree changed after the dataset manifest was frozen"
        )

    accepted_rows: list[dict[str, Any]] = []
    warmup_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    _write_run_checkpoints(
        run_dir,
        accepted_rows,
        warmup_rows,
        rejected_rows,
        summary_rows,
    )

    order = candidate_order(context_id, cooja_seed, candidates)
    canonical_indexes = {
        value: protocol["slotframe"]["candidates"].index(value)
        for value in candidates
    }
    run_started_at = utc_now()
    controller = None
    binary_hashes: dict[str, str] = {}
    failure: BaseException | None = None
    try:
        config = SDWSNControllerConfig.from_json_file(runtime_config_path)
        controller_class = CONTROLLERS[config.controller_type]
        controller = controller_class(config)
        controller.start()
        if not controller.network.network_running:
            raise CollectionError("The controller socket did not start")

        expected_physical_nodes = [
            node.node_id for node in topology["topology"].nodes
        ]
        _wait_for_discovery_convergence(
            controller,
            expected_physical_nodes,
            float(protocol["collection"]["startup_timeout_seconds"]),
            float(
                protocol["collection"].get("discovery_stability_seconds", 3.0)
            ),
        )
        computed_paths = controller.compute_routes(topology["graph"])
        if computed_paths != topology["paths"]:
            raise CollectionError("Runtime routing differs from the frozen routing tree")

        first_slotframe = min(candidates)
        runtime_cells = controller.compute_tsch_schedule(
            computed_paths,
            first_slotframe,
            schedule_seed=topology["schedule_seed"],
            deterministic=True,
        )
        if schedule_sha256(runtime_cells) != topology["schedule_sha256"]:
            raise CollectionError("Runtime schedule hash differs from the frozen schedule")
        if controller.network.tsch_last_ts() != topology["L0"] - 1:
            raise CollectionError("Frozen schedule does not occupy timeslots 0..L0-1")
        _send_with_retries(controller.send_routes, "Routing table")

        binary_hashes = _preserve_mote_binaries(run_dir)
        cursor = CoojaLogCursor(Path(controller.cooja_testlog_path))
        cursor.poll()
        expected_source_ids = topology["expected_source_ids"]

        for order_position, slotframe in enumerate(order, start=1):
            candidate_started_wall = time.monotonic()
            candidate_started_at = utc_now()
            candidate_index = canonical_indexes[slotframe]
            candidate_rejected_start = len(rejected_rows)
            accepted_for_candidate: list[dict[str, Any]] = []
            attempt_index = 0
            candidate_schedule_ready = False

            phases = ((True, warmup_cycles), (False, accepted_cycles))
            for is_warmup, requested_count in phases:
                for cycle_index in range(1, requested_count + 1):
                    accepted = False
                    for _local_attempt in range(1, max_attempts_per_cycle + 1):
                        attempt_index += 1
                        row, rejection = _collect_requested_cycle(
                            controller,
                            cursor,
                            run_id=run_id,
                            context_id=context_id,
                            cooja_seed=cooja_seed,
                            candidate_index=candidate_index,
                            slotframe=slotframe,
                            cycle_index=cycle_index,
                            is_warmup=is_warmup,
                            attempt_index=attempt_index,
                            expected_source_ids=expected_source_ids,
                            install_schedule=not candidate_schedule_ready,
                        )
                        if rejection is not None:
                            rejected_rows.append(rejection)
                            LOGGER.warning(
                                "seed=%d sf=%d %s=%d rejected attempt=%d reason=%s",
                                cooja_seed,
                                slotframe,
                                "warmup" if is_warmup else "cycle",
                                cycle_index,
                                attempt_index,
                                rejection["reason_code"],
                            )
                            _write_run_checkpoints(
                                run_dir,
                                accepted_rows,
                                warmup_rows,
                                rejected_rows,
                                summary_rows,
                            )
                            if rejection["reason_code"] == "COOJA_CRASH":
                                raise CollectionError("Cooja crashed during collection")
                            if rejection["reason_code"] == "MISSING_NODES":
                                _send_with_retries(
                                    controller.send_routes,
                                    "Routing table recovery",
                                )
                            continue

                        if row is None:
                            raise AssertionError("A cycle must be accepted or rejected")
                        if is_warmup:
                            warmup_rows.append(row)
                        else:
                            accepted_rows.append(row)
                            accepted_for_candidate.append(row)
                        candidate_schedule_ready = True
                        accepted = True
                        _write_run_checkpoints(
                            run_dir,
                            accepted_rows,
                            warmup_rows,
                            rejected_rows,
                            summary_rows,
                        )
                        break
                    if not accepted:
                        raise CollectionError(
                            f"seed={cooja_seed} sf={slotframe} cycle={cycle_index} "
                            f"failed after {max_attempts_per_cycle} attempts"
                        )

            if len(accepted_for_candidate) != accepted_cycles:
                raise AssertionError("Candidate accepted-cycle count is inconsistent")
            power_total = [
                float(row["power_total_mw"]) for row in accepted_for_candidate
            ]
            power_per_source = [
                float(row["power_per_source_mw"])
                for row in accepted_for_candidate
            ]
            delay_values = [
                float(row["delay_mean_packet_weighted_ms"])
                for row in accepted_for_candidate
            ]
            throughput_values = [
                float(row["throughput_pps"])
                for row in accepted_for_candidate
            ]
            total_delay = sum(float(row["delay_sum_ms"]) for row in accepted_for_candidate)
            total_delivered = sum(
                int(row["delivered_packets"]) for row in accepted_for_candidate
            )
            total_received = sum(
                int(row["received_packets"]) for row in accepted_for_candidate
            )
            total_expected = sum(
                int(row["expected_packets"]) for row in accepted_for_candidate
            )
            candidate_ended_at = utc_now()
            summary_rows.append({
                "run_id": run_id,
                "context_id": context_id,
                "cooja_seed": int(cooja_seed),
                "schedule_seed": topology["schedule_seed"],
                "schedule_sha256": topology["schedule_sha256"],
                "candidate_index": candidate_index,
                "slotframe": slotframe,
                "candidate_order_json": order,
                "run_mean_power_total": statistics.fmean(power_total),
                "run_mean_power_per_source": statistics.fmean(power_per_source),
                "run_mean_throughput_pps": statistics.fmean(throughput_values),
                "run_mean_delay_packet_weighted": total_delay / total_delivered,
                "run_pdr": total_received / total_expected,
                "run_sd_power": _sample_stdev(power_per_source),
                "run_sd_delay": _sample_stdev(delay_values),
                "accepted_cycles": accepted_cycles,
                "rejected_cycles": len(rejected_rows) - candidate_rejected_start,
                "warmup_cycles": warmup_cycles,
                "started_at": candidate_started_at,
                "ended_at": candidate_ended_at,
                "wall_seconds": time.monotonic() - candidate_started_wall,
                "csc_sha256": csc_sha256,
                "contiki_commit": source["commit"],
                "source_dirty": source["dirty"],
                "mote_binary_sha256": _combined_binary_hash(binary_hashes),
                "mote_binary_hashes_json": binary_hashes,
                "config_snapshot_sha256": config_snapshot_sha256,
                "runtime_config_sha256": runtime_config_sha256,
                "protocol_version": protocol["protocol_version"],
                "runner_version": RUNNER_VERSION,
                "hostname": socket.gethostname(),
            })
            _write_run_checkpoints(
                run_dir,
                accepted_rows,
                warmup_rows,
                rejected_rows,
                summary_rows,
            )
            write_json_atomic(run_dir / "in_progress.json", {
                "run_id": run_id,
                "cooja_seed": cooja_seed,
                "completed_candidates": order_position,
                "total_candidates": len(order),
                "last_slotframe": slotframe,
                "updated_at": candidate_ended_at,
            })
            LOGGER.info(
                "seed=%d candidate=%d/%d sf=%d complete",
                cooja_seed,
                order_position,
                len(order),
                slotframe,
            )
    except BaseException as exc:
        failure = exc
        write_json_atomic(run_dir / "failure.json", {
            "run_id": run_id,
            "cooja_seed": cooja_seed,
            "failed_at": utc_now(),
            "exception_type": type(exc).__name__,
            "message": str(exc),
        })
    finally:
        if controller is not None:
            try:
                controller.stop()
            except BaseException as stop_exc:
                if failure is None:
                    failure = stop_exc
                    write_json_atomic(run_dir / "failure.json", {
                        "run_id": run_id,
                        "cooja_seed": cooja_seed,
                        "failed_at": utc_now(),
                        "exception_type": type(stop_exc).__name__,
                        "message": str(stop_exc),
                    })

    if failure is not None:
        raise failure
    if len(summary_rows) != len(candidates):
        raise CollectionError("Seed ended without all candidate summaries")

    (run_dir / "in_progress.json").unlink(missing_ok=True)
    write_json_atomic(run_dir / "done.json", {
        "run_id": run_id,
        "cooja_seed": int(cooja_seed),
        "started_at": run_started_at,
        "ended_at": utc_now(),
        "candidate_count": len(candidates),
        "accepted_cycle_count": len(accepted_rows),
        "warmup_cycle_count": len(warmup_rows),
        "rejected_cycle_count": len(rejected_rows),
        "config_snapshot_sha256": config_snapshot_sha256,
        "runtime_config_sha256": runtime_config_sha256,
        "schedule_sha256": topology["schedule_sha256"],
        "mote_binary_sha256": _combined_binary_hash(binary_hashes),
    })
    if aggregate_on_complete:
        aggregate_completed_runs(output_dir)
    return "completed"


def collect_dataset(
    protocol: dict[str, Any],
    topology: dict[str, Any],
    output_dir: Path,
    *,
    seeds: list[int],
    candidates: list[int],
    warmup_cycles: int,
    accepted_cycles: int,
    max_attempts_per_cycle: int,
    port: int,
) -> dict[str, int]:
    output_dir = output_dir.resolve()
    for position, seed in enumerate(seeds, start=1):
        LOGGER.info("Starting G0 seed %d (%d/%d)", seed, position, len(seeds))
        collect_seed(
            protocol,
            topology,
            output_dir,
            cooja_seed=seed,
            candidates=candidates,
            warmup_cycles=warmup_cycles,
            accepted_cycles=accepted_cycles,
            max_attempts_per_cycle=max_attempts_per_cycle,
            port=port,
        )
    counts = aggregate_completed_runs(output_dir)
    if counts["completed_runs"] != len(seeds):
        raise CollectionError(
            f"Expected {len(seeds)} completed seeds, got {counts['completed_runs']}"
        )
    return counts
