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
from sdwsn_controller.result_analysis import run_analysis

from rich.logging import RichHandler

import pandas as pd
import numpy as np

import logging
from logging.handlers import TimedRotatingFileHandler

import logging.config
import shutil
import sys
import os


CONFIG_FILE = "native_controller_approx_model.json"

PROFILE_CATALOG = [
    (0.4, 0.3, 0.3),  # balanced
    (0.8, 0.1, 0.1),  # energy-focused
    (0.1, 0.8, 0.1),  # delay-focused
    (0.1, 0.1, 0.8),  # reliability-focused
]

PROFILE_NAMES = {
    (0.4, 0.3, 0.3): "balanced",
    (0.8, 0.1, 0.1): "energy",
    (0.1, 0.8, 0.1): "delay",
    (0.1, 0.1, 0.8): "reliability",
}


def profile_name(alpha, beta, delta):
    key = (round(float(alpha), 1), round(float(beta), 1), round(float(delta), 1))
    return PROFILE_NAMES.get(key, f"({alpha:.2f},{beta:.2f},{delta:.2f})")


def metric_row_is_valid(info):
    if bool(info.get("wait_timeout", False)):
        return False
    metric_keys = ("power_normalized", "delay_normalized", "pdr_mean")
    values = []
    for key in metric_keys:
        value = info.get(key)
        if value is None:
            return False
        try:
            value = float(value)
        except (TypeError, ValueError):
            return False
        if not np.isfinite(value):
            return False
        values.append(value)
    return any(value != 0.0 for value in values)


def _env_flag(key, default=False):
    value = os.environ.get(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key, default=0):
    value = os.environ.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(key, default=0.0):
    value = os.environ.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def run(
    env,
    controller,
    output_folder,
    simulation_name,
    randomize_requirements=False,
    requirements_mode="dirichlet",
    requirements_refresh_every=0,
    exploration_prob=0.0,
    hold_prob=0.0,
    cycle_profiles=False,
    seed=None,
):
    """
    Collect trajectories from the environment so the post-processing step can
    fit reliable trend vectors. Optional knobs randomise user requirements and
    slotframe exploration to widen the coverage of collected samples.
    """
    # Collect per-cycle info dicts before building the final DataFrame.
    records = []
    rng = np.random.default_rng(seed)
    # Reset environment
    obs, _ = env.reset()
    assert np.all(obs)
    # Get last observations (not normalized) including the SF size
    observations = controller.get_state()
    assert 0 <= observations["alpha"] <= 1
    assert 0 <= observations["beta"] <= 1
    assert 0 <= observations["delta"] <= 1
    assert observations["last_ts_in_schedule"] > 1
    # Current SF size
    sf_size = observations["current_sf_len"]
    last_ts_in_schedule = observations["last_ts_in_schedule"]

    requirements_refresh_every = max(0, int(requirements_refresh_every))
    exploration_prob = max(0.0, min(1.0, float(exploration_prob)))
    hold_prob = max(0.0, min(1.0, float(hold_prob)))
    max_cycles = max(0, _env_int("ELISE_TREND_MAX_CYCLES", default=0))
    randomize_requirements = bool(randomize_requirements)
    requirements_mode = (requirements_mode or "dirichlet").lower()

    def sample_requirements():
        """Select a new (alpha, beta, delta) triple according to the configured mode."""
        if requirements_mode == "profiles":
            return tuple(float(v) for v in rng.choice(PROFILE_CATALOG))
        weights = rng.dirichlet(np.ones(3))
        return tuple(float(w) for w in weights)

    # Initialize user requirements
    # Prepare round-robin state to avoid unbound warnings
    seq = None
    current_idx = None
    if randomize_requirements:
        if requirements_mode == "profiles" and cycle_profiles:
            seq = list(PROFILE_CATALOG)
            start_idx = 0 if seed is None else (int(seed) % len(seq))
            current_idx = start_idx
            controller.user_requirements = seq[current_idx]
        else:
            controller.user_requirements = sample_requirements()
    else:
        controller.user_requirements = (0.4, 0.3, 0.3)

    steps_since_refresh = 0
    increase = 1
    logger = logging.getLogger("main")
    for cycle_idx in range(1, 1_000_001):
        steps_since_refresh += 1

        action = None
        if exploration_prob > 0 and rng.random() < exploration_prob:
            valid_actions = []
            if sf_size < env.max_slotframe_size - 2:
                valid_actions.append(0)
            if sf_size > last_ts_in_schedule + 2:
                valid_actions.append(1)
            # allow occasional holds to gather repeated samples for CI
            if hold_prob > 0 and rng.random() < hold_prob:
                valid_actions.append(2)
            if valid_actions:
                action = int(rng.choice(valid_actions))

        if action is None:
            if increase and sf_size < env.max_slotframe_size - 2:
                action = 0
            elif not increase and sf_size > last_ts_in_schedule + 2:
                action = 1
            else:
                increase = 1 if sf_size <= last_ts_in_schedule + 2 else 0
                action = 0 if increase else 1

        _, returned_reward, terminated, truncated, info = env.step(action)
        # Get last observations non normalized
        observations = controller.get_state()
        assert 0 <= observations["alpha"] <= 1
        assert 0 <= observations["beta"] <= 1
        assert 0 <= observations["delta"] <= 1
        assert observations["last_ts_in_schedule"] > 1
        # Current SF size
        sf_size = observations["current_sf_len"]
        last_ts_in_schedule = observations["last_ts_in_schedule"]
        assert 1 < sf_size <= env.max_slotframe_size

        if sf_size >= env.max_slotframe_size - 2:
            increase = 0
        elif sf_size <= last_ts_in_schedule + 2:
            increase = 1

        record = dict(info)
        record["cycle_idx"] = cycle_idx
        # Some info dicts omit the instantaneous slotframe length; add it explicitly.
        record.setdefault("current_sf_len", sf_size)
        record["action"] = action
        record["returned_reward"] = returned_reward
        record["terminated"] = bool(terminated)
        record["truncated"] = bool(truncated)
        record["wait_timeout"] = bool(info.get("wait_timeout", False))
        record["valid_cycle"] = bool(info.get("valid_cycle", True)) and metric_row_is_valid(info)
        record["seed"] = os.environ.get("ELISE_COOJA_SEED", seed)
        if hasattr(controller, "user_requirements"):
            alpha, beta, delta = controller.user_requirements
            record["alpha_weight"] = alpha
            record["beta_weight"] = beta
            record["delta_weight"] = delta
            record["profile"] = profile_name(alpha, beta, delta)
        records.append(record)
        logger.info(
            "Cycle %d | sf_len=%d | reward=%.3f | power=%.3f | delay=%.3f | pdr=%.3f",
            cycle_idx,
            sf_size,
            info.get("reward", float("nan")),
            info.get("power_normalized", float("nan")),
            info.get("delay_normalized", float("nan")),
            info.get("pdr_mean", float("nan")),
        )
        if truncated:
            if record["wait_timeout"]:
                logger.warning("Stopping trend run after wait timeout at cycle %d", cycle_idx)
            else:
                logger.info("Number of max episodes reached at cycle %d", cycle_idx)
            break
        if max_cycles and cycle_idx >= max_cycles:
            logger.info(
                "Reached ELISE_TREND_MAX_CYCLES=%d, stopping trend run.",
                max_cycles,
            )
            break
        if (
            randomize_requirements
            and requirements_refresh_every > 0
            and steps_since_refresh >= requirements_refresh_every
        ):
            if (
                requirements_mode == "profiles"
                and cycle_profiles
                and seq is not None
                and current_idx is not None
            ):
                current_idx = (current_idx + 1) % len(seq)
                controller.user_requirements = seq[current_idx]
            else:
                controller.user_requirements = sample_requirements()
            steps_since_refresh = 0
    df = pd.DataFrame.from_records(records)
    df.to_csv(os.path.join(output_folder, simulation_name + ".csv"), index=False)
    # env.render()
    # env.close()


def result_analysis(path, output_folder):
    df = pd.read_csv(path)
    raw_rows = len(df)
    invalid_rows = 0
    if "valid_cycle" in df.columns:
        valid_mask = df["valid_cycle"].astype(str).str.lower().isin(["true", "1"])
        invalid_rows = int((~valid_mask).sum())
        df = df[valid_mask].copy()
    if df.empty:
        raise RuntimeError("No valid trend rows available after filtering")

    coverage = {
        "raw_rows": int(raw_rows),
        "valid_rows": int(len(df)),
        "invalid_rows": int(invalid_rows),
        "slotframe_counts": {
            str(int(k)): int(v)
            for k, v in df.groupby("current_sf_len").size().sort_index().items()
        },
    }
    if "profile" in df.columns:
        coverage["profile_counts"] = {
            str(k): int(v)
            for k, v in df.groupby("profile").size().sort_index().items()
        }
    try:
        import json

        with open(os.path.join(output_folder, "coverage_summary.json"), "w") as f:
            json.dump(coverage, f, indent=2)
    except Exception as e:
        logging.getLogger("main").warning("Failed to write coverage summary: %s", e)
    min_valid_rows = _env_int("ELISE_MIN_TREND_VALID_ROWS", default=1000)
    min_slotframes = _env_int("ELISE_MIN_TREND_SLOTFRAMES", default=30)
    if min_valid_rows > 0 and len(df) < min_valid_rows:
        raise RuntimeError(
            f"Trend coverage too low: valid_rows={len(df)} < {min_valid_rows}"
        )
    if min_slotframes > 0 and len(coverage["slotframe_counts"]) < min_slotframes:
        raise RuntimeError(
            "Trend slotframe coverage too low: "
            f"{len(coverage['slotframe_counts'])} < {min_slotframes}"
        )

    # Normalized power
    power_res = run_analysis.plot_fit_curves(
        df=df,
        title="power",
        path=os.path.join(output_folder, ""),
        x_axis="current_sf_len",
        y_axis="power_normalized",
        x_axis_name=r"$|C|$",
        y_axis_name=r"$\widetilde{P}$",
        degree=4,
        auto_degree=True,
        max_degree=10,
        # txt_loc=[8, 0.89],
        # y_axis_limit=[0.86, 0.9]
    )
    # Normalized delay
    delay_res = run_analysis.plot_fit_curves(
        df=df,
        title="delay",
        path=os.path.join(output_folder, ""),
        x_axis="current_sf_len",
        y_axis="delay_normalized",
        x_axis_name=r"$|C|$",
        y_axis_name=r"$\widetilde{D}$",
        degree=3,
        auto_degree=True,
        max_degree=10,
        fit_center="trimmed_mean",
        trim_quantile=0.05,
        # txt_loc=[8, 0.045],
        # y_axis_limit=[0, 0.95]
    )
    reli_res = run_analysis.plot_fit_curves(
        df=df,
        title="reliability",
        path=os.path.join(output_folder, ""),
        x_axis="current_sf_len",
        y_axis="pdr_mean",
        x_axis_name=r"$|C|$",
        y_axis_name=r"$\widetilde{R}$",
        degree=1,
        auto_degree=False,
        max_degree=1,
        # txt_loc=[25, 0.7],
        # y_axis_limit=[0.65, 1]
    )
    # Export coefficients as JSON
    try:
        import json

        bundle = {"power": power_res, "delay": delay_res, "reliability": reli_res}
        json_path = os.path.join(output_folder, "trend_vectors.json")
        with open(json_path, "w") as f:
            json.dump(bundle, f, indent=2)
        # Also export candidates (degrees tried, R2 and monotonicity)
        cand = {
            "power": power_res.get("candidates") if isinstance(power_res, dict) else None,
            "delay": delay_res.get("candidates") if isinstance(delay_res, dict) else None,
            "reliability": reli_res.get("candidates") if isinstance(reli_res, dict) else None,
        }
        cand_path = os.path.join(output_folder, "trend_candidates.json")
        with open(cand_path, "w") as f:
            json.dump(cand, f, indent=2)
    except Exception as e:
        logging.getLogger("main").warning("Failed to write trend JSONs: %s", e)

    # Metrics vs. Slotframe Size
    run_analysis.plot_against_sf_size(
        df=df, title="slotframe_size", path=os.path.join(output_folder, "")
    )


def main():
    # -------------------- Create logger --------------------
    logger = logging.getLogger("main")

    formatter = logging.Formatter("%(asctime)s - %(message)s")
    logger.setLevel(logging.DEBUG)

    stream_handler = RichHandler(rich_tracebacks=True)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    logFilePath = "my.log"
    formatter = logging.Formatter(
        "%(asctime)s | %(name)s |  %(levelname)s: %(message)s"
    )
    file_handler = TimedRotatingFileHandler(
        filename=logFilePath, when="midnight", backupCount=30
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    # ----------------- RL environment, setup --------------------
    # Create output folder (override with ELISE_OUTPUT_DIR)
    output_folder = os.environ.get("ELISE_OUTPUT_DIR", "./output/")
    os.makedirs(output_folder, exist_ok=True)

    # Monitor the environment (override with ELISE_LOG_DIR)
    log_dir = os.environ.get("ELISE_LOG_DIR", "./tensorlog/")
    os.makedirs(log_dir, exist_ok=True)
    # -------------------- setup controller ---------------------
    randomize_requirements = _env_flag("ELISE_RANDOMIZE_REQUIREMENTS", default=False)
    requirements_refresh_every = _env_int("ELISE_REQUIREMENTS_REFRESH_EVERY", default=0)
    exploration_prob = _env_float("ELISE_SLOTFRAME_EXPLORE_PROB", default=0.0)
    hold_prob = _env_float("ELISE_SLOTFRAME_HOLD_PROB", default=0.0)
    requirements_mode = os.environ.get("ELISE_REQUIREMENTS_MODE", "dirichlet")
    requirements_mode = (requirements_mode or "dirichlet").lower()
    cycle_profiles = _env_flag("ELISE_REQUIREMENTS_CYCLE", default=False)
    seed = None
    seed_env = os.environ.get("ELISE_TREND_RANDOM_SEED")
    if seed_env is not None:
        try:
            seed = int(seed_env)
        except ValueError:
            logger.warning(
                "Invalid ELISE_TREND_RANDOM_SEED '%s'; falling back to non-deterministic sampling.",
                seed_env,
            )
    logger.info(
        "Trend sampling | randomize_requirements=%s mode=%s refresh_every=%d exploration_prob=%.3f hold_prob=%.3f cycle_profiles=%s seed=%s",
        randomize_requirements,
        requirements_mode,
        requirements_refresh_every,
        exploration_prob,
        hold_prob,
        cycle_profiles,
        seed if seed is not None else "None",
    )
    config = SDWSNControllerConfig.from_json_file(CONFIG_FILE)
    #
    ctype = getattr(config, "controller_type", None)

    if not ctype:
        raise ValueError("controller_type is missing in config")
    controller_class = CONTROLLERS.get(ctype)
    if controller_class is None:
        raise ValueError(f"Unknown controller_type: {ctype}")
    # controller = controller_class(config)
    with controller_class(config) as controller:
        # ----------------- Environment ----------------------------
        env = controller.reinforcement_learning.env
        # --------------------Start RL --------------------------------
        run(
            env,
            controller,
            output_folder,
            controller.simulation_name,
            randomize_requirements=randomize_requirements,
            requirements_mode=requirements_mode,
            requirements_refresh_every=requirements_refresh_every,
            exploration_prob=exploration_prob,
            hold_prob=hold_prob,
            cycle_profiles=cycle_profiles,
            seed=seed,
        )

        result_analysis(
            os.path.join(output_folder, controller.simulation_name + ".csv"),
            output_folder,
        )

    # Delete folders
    # try:
    #     shutil.rmtree(output_folder)
    # except OSError as e:
    #     print("Error: %s - %s." % (e.filename, e.strerror))
    # try:
    #     shutil.rmtree(log_dir)
    # except OSError as e:
    #     print("Error: %s - %s." % (e.filename, e.strerror))


if __name__ == "__main__":
    main()
    sys.exit(0)
