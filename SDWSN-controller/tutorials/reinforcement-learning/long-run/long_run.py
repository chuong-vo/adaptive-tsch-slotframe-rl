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
from sdwsn_controller.config import SDWSNControllerConfig, CONTROLLERS
from rich.logging import RichHandler
from stable_baselines3 import PPO

import pandas as pd

import logging.config
import shutil
import sys
import os
import time
from pathlib import Path


THIS_DIR = Path(__file__).resolve().parent
CONFIG_FILE = THIS_DIR / "long_run.json"
# Default deployed model path can be overridden via ELISE_TRAINED_MODEL.
DEFAULT_TRAINED_MODEL = str(THIS_DIR / "trained_model" / "best_model.zip")

PROFILE_LABELS = {
    (0.4, 0.3, 0.3): "balanced",
    (0.1, 0.8, 0.1): "delay",
    (0.8, 0.1, 0.1): "energy",
    (0.1, 0.1, 0.8): "reliability",
}


def profile_name(alpha, beta, delta):
    key = (round(float(alpha), 1), round(float(beta), 1), round(float(delta), 1))
    return PROFILE_LABELS.get(key, f"({alpha:.2f},{beta:.2f},{delta:.2f})")


def env_int(name, default, min_value=0):
    try:
        value = int(os.environ.get(name, str(default)))
    except Exception:
        value = default
    return max(min_value, value)


def env_float(name, default, min_value=0.0):
    try:
        value = float(os.environ.get(name, str(default)))
    except Exception:
        value = default
    return max(min_value, value)


def write_records_atomic(csv_path, records):
    tmp_path = f"{csv_path}.tmp"
    pd.DataFrame.from_records(records).to_csv(tmp_path, index=False)
    os.replace(tmp_path, csv_path)


def run(env, model_path, controller, output_folder, simulation_name, reset_every: int = 0):
    # Load model
    model = PPO.load(model_path)
    records = []
    logger = logging.getLogger('main')
    csv_path = os.path.join(output_folder, simulation_name + '.csv')

    # Optional hard stop after N recorded cycles (ELISE_MAX_CYCLES)
    max_cycles = env_int('ELISE_MAX_CYCLES', 0, min_value=0)
    reset_attempts = env_int('ELISE_RESET_RETRIES', 3, min_value=1)
    max_step_exceptions = env_int('ELISE_MAX_STEP_EXCEPTIONS', 3, min_value=1)
    reset_backoff = env_float('ELISE_RESET_BACKOFF_SECONDS', 5.0, min_value=0.0)
    flush_every = env_int('ELISE_FLUSH_EVERY', 1, min_value=1)
    if reset_every <= 0:
        reset_every = env_int('ELISE_RESET_EVERY', 0, min_value=0)

    reset_count = 0
    step_exception_count = 0
    consecutive_step_exceptions = 0

    def flush_records(force=False):
        if records and (force or len(records) % flush_every == 0):
            write_records_atomic(csv_path, records)

    def reset_with_retries(reason):
        nonlocal reset_count
        last_exc = None
        for attempt in range(1, reset_attempts + 1):
            try:
                logger.warning(
                    "Resetting environment (%s), attempt %d/%d",
                    reason,
                    attempt,
                    reset_attempts,
                )
                obs_reset, _ = env.reset()
                reset_count += 1
                return obs_reset
            except Exception as exc:
                last_exc = exc
                logger.exception(
                    "Environment reset failed (%s), attempt %d/%d",
                    reason,
                    attempt,
                    reset_attempts,
                )
                try:
                    controller.stop()
                except Exception:
                    logger.exception("Controller stop failed during reset recovery")
                if attempt < reset_attempts and reset_backoff > 0:
                    time.sleep(reset_backoff * attempt)
        raise RuntimeError(
            f"Unable to reset environment after {reset_attempts} attempts: {reason}"
        ) from last_exc

    # Reset environment before the first measured cycle. If this fails, no row is
    # written because no cycle has been measured.
    obs = reset_with_retries("initial start")

    while True:
        if max_cycles and len(records) >= max_cycles:
            logger.info("Reached ELISE_MAX_CYCLES=%d, stopping long-run.", max_cycles)
            break

        try:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, done, truncated, info = env.step(action)
            consecutive_step_exceptions = 0
        except Exception:
            step_exception_count += 1
            consecutive_step_exceptions += 1
            logger.exception(
                "env.step failed before producing a measured cycle; "
                "no synthetic data row will be recorded"
            )
            if consecutive_step_exceptions > max_step_exceptions:
                raise RuntimeError(
                    "Too many consecutive env.step exceptions "
                    f"({consecutive_step_exceptions})"
                )
            obs = reset_with_retries(
                f"step exception after {len(records)} recorded cycles"
            )
            continue

        cycle_idx = len(records) + 1
        # Publish RL info to MQTT so AppLayer can rotate user requirements
        # RL framework already pushes RL info to AppLayer via registered callbacks.
        record = dict(info)
        record["cycle_idx"] = cycle_idx
        record["returned_reward"] = reward
        record["terminated"] = bool(done)
        record["truncated"] = bool(truncated)
        record["wait_timeout"] = bool(info.get("wait_timeout", False))
        record["valid_cycle"] = bool(info.get("valid_cycle", True)) and not record["wait_timeout"]
        record["seed"] = os.environ.get("ELISE_COOJA_SEED", "")
        record["reset_count"] = reset_count
        record["step_exception_count"] = step_exception_count
        if all(k in record for k in ("alpha", "beta", "delta")):
            record["profile"] = profile_name(record["alpha"], record["beta"], record["delta"])
        records.append(record)
        flush_records()
        logger.info(
            "Cycle %d | sf_len=%s | reward=%.3f | power=%.3f | delay=%.3f | pdr=%.3f",
            cycle_idx,
            info.get('current_sf_len'),
            info.get('reward', float('nan')),
            info.get('power_normalized', float('nan')),
            info.get('delay_normalized', float('nan')),
            info.get('pdr_mean', float('nan'))
        )
        if reset_every and len(records) % reset_every == 0:
            obs = reset_with_retries(
                f"scheduled reset after {len(records)} recorded cycles"
            )
            continue
        # Profile switching is handled exclusively by AppLayer via MQTT.
        # Handle episode termination or time-limit/stall gracefully
        if done or truncated:
            logger.info(
                'Episode ended (%s) at cycle %d - resetting environment',
                'truncated' if truncated else 'done', cycle_idx
            )
            obs = reset_with_retries(
                f"{'truncated' if truncated else 'done'} at cycle {cycle_idx}"
            )
            continue
    flush_records(force=True)
    # env.render()
    # env.close()


def main():
    # Create output/log folders early so file logging always points to a writable path.
    output_folder = os.environ.get('ELISE_OUTPUT_DIR', './output/')
    os.makedirs(output_folder, exist_ok=True)

    default_log_dir = os.path.join(output_folder, 'logs')
    log_dir = os.environ.get('ELISE_LOG_DIR', default_log_dir)
    os.makedirs(log_dir, exist_ok=True)

    seed_label = os.environ.get("ELISE_COOJA_SEED", "").strip()
    default_log_name = f"long_run_seed_{seed_label}.log" if seed_label else "long_run.log"
    log_file_path = os.environ.get(
        "ELISE_LOG_FILE",
        os.path.join(log_dir, default_log_name),
    )

    # -------------------- Create logger --------------------
    logger = logging.getLogger('main')

    formatter = logging.Formatter(
        '%(asctime)s - %(message)s')
    logger.setLevel(logging.DEBUG)

    stream_handler = RichHandler(rich_tracebacks=True)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    formatter = logging.Formatter(
        '%(asctime)s | %(name)s |  %(levelname)s: %(message)s')
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_file_path, when='midnight', backupCount=30)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    # ----------------- RL environment, setup --------------------
    # -------------------- setup controller ---------------------
    config = SDWSNControllerConfig.from_json_file(CONFIG_FILE)
    controller_class = CONTROLLERS[config.controller_type]
    controller = controller_class(config)
    # Resolve trained model path (env override if set)
    trained_model = os.environ.get("ELISE_TRAINED_MODEL", DEFAULT_TRAINED_MODEL)
    if not Path(trained_model).is_file():
        logger.error("Trained model not found at '%s'", trained_model)
        sys.exit(1)
    # ----------------- Environment ----------------------------
    env = controller.reinforcement_learning.env
    # --------------------Start RL --------------------------------
    try:
        run(env, trained_model, controller, output_folder,
            controller.simulation_name)
    finally:
        controller.stop()

    # Keep output and logs for post-run analysis
    # (Remove these lines if you prefer automatic cleanup.)


if __name__ == '__main__':
    main()
    sys.exit(0)
