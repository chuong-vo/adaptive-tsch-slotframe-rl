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
import sys
import csv
import json
import shutil
import time

import numpy as np
import torch
import gymnasium as gym


from sdwsn_controller.config import SDWSNControllerConfig, CONTROLLERS
from sdwsn_controller.reinforcement_learning.wrappers import (
    SaveOnBestTrainingRewardCallback,
)

from stable_baselines3.common.monitor import Monitor


from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import EvalCallback


SELF_PATH = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SELF_PATH, "numerical_controller_rl.json")
PROFILE_WEIGHTS = {
    "balanced": (0.4, 0.3, 0.3),
    "delay": (0.1, 0.8, 0.1),
    "energy": (0.8, 0.1, 0.1),
    "reliability": (0.1, 0.1, 0.8),
}


def get_eval_initial_sfs():
    values = [
        int(value.strip())
        for value in os.environ.get(
            "RL_EVAL_INITIAL_SFS",
            "10,25,40,55,68",
        ).split(",")
        if value.strip()
    ]
    if not values:
        raise ValueError("RL_EVAL_INITIAL_SFS must contain at least one value")
    return values


def get_training_timesteps():
    requested_steps = int(os.environ.get("RL_TOTAL_STEPS", "5996544"))
    effective_steps = max(4096, ((requested_steps + 4095) // 4096) * 4096)
    return requested_steps, effective_steps


def configure_training_profiles():
    """Expose PPO to all objective profiles unless the caller overrides it."""
    os.environ.setdefault("ELISE_REQUIREMENTS_MODE", "profiles")
    os.environ.setdefault("ELISE_REQUIREMENTS_CYCLE", "1")
    os.environ.setdefault("ELISE_INITIAL_PROFILE", "balanced")
    os.environ.setdefault("ELISE_MIN_SLOTFRAME_SIZE", "10")
    os.environ.setdefault("ELISE_MAX_SLOTFRAME_SIZE", "68")
    os.environ.setdefault("ELISE_INITIAL_SF_MODE", "random")
    os.environ.setdefault("ELISE_INITIAL_SF_MIN", "10")
    os.environ.setdefault("ELISE_INITIAL_SF_MAX", "68")
    print(
        "Training profiles:",
        f"mode={os.environ.get('ELISE_REQUIREMENTS_MODE')},",
        f"cycle={os.environ.get('ELISE_REQUIREMENTS_CYCLE')},",
        f"initial={os.environ.get('ELISE_INITIAL_PROFILE')},",
        f"initial_sf_mode={os.environ.get('ELISE_INITIAL_SF_MODE')},",
        f"sf_range=[{os.environ.get('ELISE_INITIAL_SF_MIN')},",
        f"{os.environ.get('ELISE_INITIAL_SF_MAX')}]",
    )


class MetricsLoggerEnv(gym.Wrapper):
    """Wrap environment to log info metrics into a CSV file."""

    def __init__(self, env, csv_path, phase):
        super().__init__(env)
        self.csv_path = csv_path
        self.phase = phase
        self.step_idx = 0
        fieldnames = [
            "timestamp",
            "phase",
            "step",
            "alpha",
            "beta",
            "delta",
            "reward",
            "returned_reward",
            "terminated",
            "truncated",
            "wait_timeout",
            "valid_cycle",
            "power_normalized",
            "delay_normalized",
            "pdr_mean",
            "current_sf_len",
            "last_ts_in_schedule",
            "episode_index",
            "episode_initial_sf_len",
            "episode_profile",
            "action",
            "applied_action",
            "requested_sf_len",
            "applied_sf_len",
            "action_overridden",
            "action_override_reason",
        ]
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        self._log_file = open(csv_path, "a", newline="")
        self._writer = csv.DictWriter(self._log_file, fieldnames=fieldnames)
        if self._log_file.tell() == 0:
            self._writer.writeheader()

    def step(self, action):
        obs, reward, terminated, truncated, info = self.env.step(action)
        self.step_idx += 1
        controller = getattr(self.env.unwrapped, "controller", None)
        row = {
            "timestamp": time.time(),
            "phase": self.phase,
            "step": self.step_idx,
            "alpha": getattr(controller, "alpha", None),
            "beta": getattr(controller, "beta", None),
            "delta": getattr(controller, "delta", None),
            "reward": info.get("reward"),
            "returned_reward": reward,
            "terminated": terminated,
            "truncated": truncated,
            "wait_timeout": info.get("wait_timeout", False),
            "valid_cycle": info.get("valid_cycle", True),
            "power_normalized": info.get("power_normalized"),
            "delay_normalized": info.get("delay_normalized"),
            "pdr_mean": info.get("pdr_mean"),
            "current_sf_len": info.get("current_sf_len"),
            "last_ts_in_schedule": info.get("last_ts_in_schedule"),
            "episode_index": info.get("episode_index"),
            "episode_initial_sf_len": info.get("episode_initial_sf_len"),
            "episode_profile": info.get("episode_profile"),
            "action": (
                int(np.asarray(action).item())
                if action is not None
                else None
            ),
            "applied_action": info.get("applied_action"),
            "requested_sf_len": info.get("requested_sf_len"),
            "applied_sf_len": info.get("applied_sf_len"),
            "action_overridden": info.get("action_overridden", False),
            "action_override_reason": info.get("action_override_reason", ""),
        }
        self._writer.writerow(row)
        self._log_file.flush()
        return obs, reward, terminated, truncated, info

    def reset(self, **kwargs):
        return self.env.reset(**kwargs)

    def close(self):
        try:
            self._log_file.close()
        finally:
            super().close()


class EvaluationGridEnv(gym.Wrapper):
    """Reset eval episodes on a repeatable profile/slotframe grid."""

    def __init__(self, env, profiles, initial_sfs):
        super().__init__(env)
        self.cases = [
            (profile, initial_sf)
            for profile in profiles
            for initial_sf in initial_sfs
        ]
        self.case_index = 0

    def reset(self, *, seed=None, options=None):
        profile, initial_sf = self.cases[self.case_index % len(self.cases)]
        self.case_index += 1
        reset_options = dict(options or {})
        reset_options.setdefault("profile", profile)
        reset_options.setdefault("initial_sf", initial_sf)
        return self.env.reset(seed=seed, options=reset_options)


def train(env, log_dir, callback, seed=123):
    """
    Just use the PPO algorithm.
    """
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Training PPO on device: {device}")
    # Reproducibility
    np.random.seed(seed)
    torch.manual_seed(seed)
    env.action_space.seed(seed)
    # PPO with more stable defaults
    model = PPO(
        "MlpPolicy",
        env,
        n_steps=4096,
        batch_size=512,
        learning_rate=3e-4,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=0.01,
        vf_coef=0.5,
        max_grad_norm=0.5,
        tensorboard_log=log_dir,
        verbose=1,
        seed=seed,
        device=device,
    )

    # Use a multiple of n_steps for clean rollout cycles.
    requested_steps, total_steps = get_training_timesteps()
    print(
        f"Training for {total_steps} steps "
        f"(requested RL_TOTAL_STEPS={requested_steps})"
    )
    model.learn(total_timesteps=total_steps, tb_log_name="training", callback=callback)
    # Let's save the model
    base_path = os.path.join(log_dir, "ppo_sdwsn")
    model.save(base_path)

    del model  # remove to demonstrate saving and loading

    return base_path + ".zip"


def evaluation(env, model_path, summary_path=None):
    """Evaluate deterministic behavior from multiple initial slotframes."""
    model = PPO.load(model_path)
    base_env = env.unwrapped
    controller = base_env.controller
    reward_processor = controller.reinforcement_learning.reward_processor
    initial_sfs = get_eval_initial_sfs()
    horizon = max(1, int(os.environ.get("RL_EVAL_HORIZON", "128")))
    valid_sfs = base_env._valid_slotframe_sizes(
        base_env.min_slotframe_size,
        base_env.action_max_slotframe_size,
    )
    invalid_sfs = [sf_len for sf_len in initial_sfs if sf_len not in valid_sfs]
    if invalid_sfs:
        raise ValueError(
            f"RL_EVAL_INITIAL_SFS contains invalid values: {invalid_sfs}"
        )

    oracle_by_profile = {}
    for profile, weights in PROFILE_WEIGHTS.items():
        oracle_by_profile[profile] = max(
            valid_sfs,
            key=lambda sf_len: reward_processor.calculate_reward(
                *weights,
                sf_len,
            )["reward"],
        )

    rows = []
    print("Deterministic policy grid evaluation:")
    for profile in PROFILE_WEIGHTS:
        oracle_sf = oracle_by_profile[profile]
        for initial_sf in initial_sfs:
            obs, _ = env.reset(options={
                "profile": profile,
                "initial_sf": initial_sf,
            })
            total_reward = 0.0
            action_counts = {0: 0, 1: 0, 2: 0}
            steps = 0
            for _ in range(horizon):
                action, _ = model.predict(obs, deterministic=True)
                action_value = int(np.asarray(action).item())
                action_counts[action_value] += 1
                obs, reward, terminated, truncated, _ = env.step(action)
                total_reward += float(reward)
                steps += 1
                if terminated or truncated:
                    break

            final_sf = int(controller.get_state()["current_sf_len"])
            initial_distance = abs(initial_sf - oracle_sf)
            final_distance = abs(final_sf - oracle_sf)
            direction_ok = (
                final_distance == 0
                if initial_distance == 0
                else final_distance < initial_distance
            )
            row = {
                "profile": profile,
                "initial_sf_len": initial_sf,
                "final_sf_len": final_sf,
                "oracle_sf_len": oracle_sf,
                "initial_distance": initial_distance,
                "final_distance": final_distance,
                "direction_ok": direction_ok,
                "steps": steps,
                "mean_reward": total_reward / steps,
                "increase_actions": action_counts[0],
                "decrease_actions": action_counts[1],
                "hold_actions": action_counts[2],
            }
            rows.append(row)
            print(
                f"  {profile:11s} start={initial_sf:2d} final={final_sf:2d} "
                f"oracle={oracle_sf:2d} direction_ok={direction_ok} "
                f"actions={action_counts}"
            )

    if summary_path:
        os.makedirs(os.path.dirname(summary_path), exist_ok=True)
        with open(summary_path, "w", newline="") as summary_file:
            writer = csv.DictWriter(summary_file, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    passed = sum(bool(row["direction_ok"]) for row in rows)
    print(f"Policy grid result: {passed}/{len(rows)} cases move toward the oracle")
    return {
        "passed": passed,
        "total": len(rows),
        "rows": rows,
    }


def main():
    """
    This test the training, loading and testing of RL env.
    We dont use DB to avoid reducing the processing speed
    """
    configure_training_profiles()
    # ----------------- RL environment, setup --------------------
    # Base run folder for all artifacts
    run_root = os.environ.get("RL_RUN_DIR", "./runs/")
    os.makedirs(run_root, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    base_dir = os.path.join(run_root, f"ppo_run_{ts}")
    # Subfolders
    output_folder = os.path.join(base_dir, "output")
    log_dir = os.path.join(base_dir, "tensorlog")
    monitor_log_dir = os.path.join(base_dir, "trained_model")
    training_best_dir = os.path.join(monitor_log_dir, "training_reward_best")
    eval_best_dir = os.path.join(monitor_log_dir, "eval_best")
    eval_monitor_dir = os.path.join(base_dir, "eval_monitor")
    metrics_dir = os.path.join(base_dir, "metrics")
    for d in (
            output_folder,
            log_dir,
            monitor_log_dir,
            training_best_dir,
            eval_best_dir,
            eval_monitor_dir,
            metrics_dir):
        os.makedirs(d, exist_ok=True)
    config_snapshot_path = os.path.join(base_dir, "numerical_controller_rl.json")
    shutil.copy2(CONFIG_FILE, config_snapshot_path)
    train_metrics_file = os.path.join(metrics_dir, "train_metrics.csv")
    eval_metrics_file = os.path.join(metrics_dir, "eval_metrics.csv")
    for metrics_file in (train_metrics_file, eval_metrics_file):
        if os.path.exists(metrics_file):
            os.remove(metrics_file)
    # -------------------- setup controller ---------------------
    config = SDWSNControllerConfig.from_json_file(CONFIG_FILE)
    #
    ctype = getattr(config, "controller_type", None)

    if not ctype:
        raise ValueError("controller_type is missing in config")
    controller_class = CONTROLLERS.get(ctype)
    if controller_class is None:
        raise ValueError(f"Unknown controller_type: {ctype}")
    controller = controller_class(config)
    # ----------------- RL environment ----------------------------
    train_env = controller.reinforcement_learning.env
    train_env = MetricsLoggerEnv(train_env, train_metrics_file, phase="train")
    train_env = Monitor(train_env, monitor_log_dir)
    # Eval env (separate controller instance for isolation)
    eval_controller = controller_class(config)
    eval_env = eval_controller.reinforcement_learning.env
    eval_initial_sfs = get_eval_initial_sfs()
    valid_eval_sfs = eval_env.unwrapped._valid_slotframe_sizes(
        eval_env.unwrapped.min_slotframe_size,
        eval_env.unwrapped.action_max_slotframe_size,
    )
    invalid_eval_sfs = [
        sf_len for sf_len in eval_initial_sfs if sf_len not in valid_eval_sfs
    ]
    if invalid_eval_sfs:
        raise ValueError(
            f"RL_EVAL_INITIAL_SFS contains invalid values: {invalid_eval_sfs}"
        )
    eval_env = EvaluationGridEnv(
        eval_env,
        profiles=PROFILE_WEIGHTS.keys(),
        initial_sfs=eval_initial_sfs,
    )
    # write eval monitor logs to a separate folder to avoid mixing formats
    eval_env = Monitor(eval_env, eval_monitor_dir)
    eval_grid_size = len(PROFILE_WEIGHTS) * len(eval_initial_sfs)
    n_eval_episodes = int(
        os.environ.get("RL_N_EVAL_EPISODES", str(eval_grid_size))
    )
    if n_eval_episodes < eval_grid_size or n_eval_episodes % eval_grid_size != 0:
        raise ValueError(
            "RL_N_EVAL_EPISODES must be a positive multiple of the evaluation "
            f"grid size ({eval_grid_size})"
        )
    eval_freq = max(1, int(os.environ.get("RL_EVAL_FREQ", "8192")))
    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path=eval_best_dir,
        log_path=eval_monitor_dir,
        eval_freq=eval_freq,
        n_eval_episodes=n_eval_episodes,
        deterministic=True,
        render=False,
    )
    # Train the agent
    training_reward_callback = SaveOnBestTrainingRewardCallback(
        check_freq=1000,
        log_dir=monitor_log_dir,
        save_dir=training_best_dir,
    )
    # Optional seed override from environment (RL_SEED)
    seed_override = None
    seed_env = os.environ.get("RL_SEED")
    if seed_env:
        try:
            seed_override = int(seed_env)
        except ValueError:
            print(f"Invalid RL_SEED='{seed_env}', using default seed")

    if seed_override is not None:
        print(f"Using RL_SEED={seed_override}")
    else:
        print("RL_SEED not set; using default seed=123")
    training_seed = seed_override if seed_override is not None else 123

    final_model_path = train(
        train_env,
        log_dir,
        callback=[training_reward_callback, eval_callback],
        seed=training_seed,
    )
    train_env.close()

    model_candidates = [
        ("evaluation", os.path.join(eval_best_dir, "best_model.zip")),
        ("final", final_model_path),
        ("training_reward", os.path.join(training_best_dir, "best_model.zip")),
    ]
    selected_source, selected_model_path = next(
        (
            (source, path)
            for source, path in model_candidates
            if os.path.isfile(path)
        ),
        (None, None),
    )
    if selected_model_path is None:
        raise FileNotFoundError("Training completed without producing a model")
    canonical_model_path = os.path.join(monitor_log_dir, "best_model.zip")
    shutil.copy2(selected_model_path, canonical_model_path)
    requested_steps, effective_steps = get_training_timesteps()
    base_env = controller.reinforcement_learning.env.unwrapped
    selection_metadata = {
        "selected_by": selected_source,
        "selected_source_path": os.path.abspath(selected_model_path),
        "canonical_model_path": os.path.abspath(canonical_model_path),
        "seed": training_seed,
        "eval_frequency": eval_freq,
        "eval_episodes": n_eval_episodes,
        "eval_initial_slotframes": eval_initial_sfs,
        "profiles": list(PROFILE_WEIGHTS),
        "controller_config_snapshot": os.path.abspath(config_snapshot_path),
        "training": {
            "requested_timesteps": requested_steps,
            "effective_timesteps": effective_steps,
            "max_episode_steps": config.reinforcement_learning.max_episode_steps,
            "slotframe_min": base_env.min_slotframe_size,
            "slotframe_max": base_env.action_max_slotframe_size,
            "initial_slotframe_mode": base_env.initial_sf_mode,
            "initial_slotframe_min": base_env.initial_sf_min,
            "initial_slotframe_max": base_env.initial_sf_max,
        },
    }
    selection_path = os.path.join(monitor_log_dir, "model_selection.json")
    with open(selection_path, "w") as selection_file:
        json.dump(selection_metadata, selection_file, indent=2)
    print(
        f"Canonical model selected by {selected_source}: "
        f"{canonical_model_path}"
    )

    # ----------------- Test environment ----------------------------
    test_env = controller.reinforcement_learning.env
    test_env = MetricsLoggerEnv(test_env, eval_metrics_file, phase="eval")
    policy_grid_path = os.path.join(metrics_dir, "policy_grid_evaluation.csv")
    policy_grid_result = evaluation(
        test_env,
        canonical_model_path,
        summary_path=policy_grid_path,
    )
    selection_metadata["policy_grid_evaluation"] = {
        "passed": policy_grid_result["passed"],
        "total": policy_grid_result["total"],
        "summary_path": os.path.abspath(policy_grid_path),
    }
    with open(selection_path, "w") as selection_file:
        json.dump(selection_metadata, selection_file, indent=2)
    test_env.close()
    controller.stop()
    eval_controller.stop()
    # ----------------- Post-training analysis -----------------------
    try:
        from sdwsn_controller.result_analysis import run_analysis

        # Use eval metrics for clearer behavior plots
        df_path = eval_metrics_file
        import pandas as pd

        df = pd.read_csv(df_path)
        # Generate trend plots vs current_sf_len
        run_analysis.plot_fit_curves(
            df=df,
            title="power",
            path=output_folder + "/",
            x_axis="current_sf_len",
            y_axis="power_normalized",
            x_axis_name="|C|",
            y_axis_name="P~",
            degree=4,
            auto_degree=True,
            max_degree=10,
        )
        run_analysis.plot_fit_curves(
            df=df,
            title="delay",
            path=output_folder + "/",
            x_axis="current_sf_len",
            y_axis="delay_normalized",
            x_axis_name="|C|",
            y_axis_name="D~",
            degree=3,
            auto_degree=True,
            max_degree=10,
        )
        run_analysis.plot_fit_curves(
            df=df,
            title="reliability",
            path=output_folder + "/",
            x_axis="current_sf_len",
            y_axis="pdr_mean",
            x_axis_name="|C|",
            y_axis_name="R~",
            degree=1,
            auto_degree=False,
            max_degree=1,
        )
        run_analysis.plot_against_sf_size(
            df=df, title="slotframe_size", path=output_folder + "/"
        )
        print(f"Analysis plots saved to {output_folder}")
    except Exception as e:
        print("Post-training analysis skipped:", e)
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
