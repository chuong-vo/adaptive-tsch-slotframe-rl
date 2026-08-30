# Adaptive TSCH Slotframe Optimization with Reinforcement Learning in SDWSN

This repository contains the source code and final experimental artifacts for
adaptive TSCH slotframe-size optimization using Proximal Policy Optimization
(PPO) in a Software-Defined Wireless Sensor Network (SDWSN).

The experimental workflow has three stages:

1. Collect Cooja measurements and estimate metric trends over the valid
   slotframe-size domain.
2. Train a PPO policy in a numerical environment built from the fitted trends.
3. Deploy the selected policy in the Cooja control loop and evaluate it through
   multi-seed long-run experiments.

> Some environment variables retain the `ELISE_` prefix for compatibility with
> the inherited codebase. The experimental control variable in this work is the
> TSCH slotframe size.

## Repository Layout

```text
.
|-- SDWSN-controller/       # Control plane, RL environment, training, analysis
|-- contiki-ng/             # Contiki-NG data plane and Cooja scenario
|-- results/
|   |-- trend/              # Final trend dataset from 20 seeds
|   |-- training/           # Selected PPO model and evaluation results
|   `-- long_run/           # Final long-run results for seeds 43-50
|-- run_trend_sweep.py
|-- run_long_run_with_seed.sh
|-- run_long_run_seed_range.sh
`-- setup_rl_env.sh
```

Intermediate logs, unselected checkpoints, caches, virtual environments, and
thesis/report files are intentionally excluded.
Required Contiki-NG and Cooja dependency sources are vendored as regular files;
no `git submodule update` step is required.

## Workflow Index

1. [Install system dependencies](#2-install-system-dependencies)
2. [Create the Python environment](#3-create-the-python-environment)
3. [Validate the source](#4-validate-the-source-before-running)
4. [Run smoke tests](#5-smoke-tests)
5. [Collect and fit trend data](#6-stage-1-collect-trend-data)
6. [Train PPO](#8-stage-2-train-the-ppo-policy)
7. [Run and analyze long-run evaluation](#9-stage-3-long-run-evaluation)
8. [Collect the Top-K dataset](#top-k-dataset-collection)

## Top-K Dataset Collection

The immutable G0 baseline and the fixed multi-topology Top-K dataset collector
are documented in `experiments/topk_dataset/README.md`. Start with the relevant
`--prepare-only` and `--smoke` commands before launching a full matrix.

## Tested Environment

The final experiments were executed with:

- Ubuntu 22.04 under WSL2
- Python 3.10
- OpenJDK 17
- Contiki-NG and Cooja included in this repository
- PyTorch 2.8.0
- Stable-Baselines3 2.0.0a5
- NVIDIA CUDA 12.8 for PPO training

A GPU is optional. Trend collection and long-run evaluation are dominated by
Cooja simulation and run correctly on a CPU-only machine. For exact
reproduction, use Python 3.10 and the pinned direct dependencies in
`requirements-rl.txt`.

Recommended resources:

- 16 GB RAM or more
- 30 GB or more of free disk space

Cooja logs from a complete experiment can become large even though they are not
committed to Git.

## 1. Clone the Repository

The repository is currently private. A GitHub account must be granted access
before cloning.

```bash
git clone https://github.com/chuong-vo/adaptive-tsch-slotframe-rl.git
cd adaptive-tsch-slotframe-rl
```

Alternatively, use GitHub CLI:

```bash
gh auth login
gh repo clone chuong-vo/adaptive-tsch-slotframe-rl
cd adaptive-tsch-slotframe-rl
```

## 2. Install System Dependencies

Example for Ubuntu 22.04:

```bash
sudo apt update
sudo apt install -y \
  git \
  build-essential \
  python3 \
  python3-dev \
  python3-venv \
  openjdk-17-jdk \
  iproute2 \
  procps \
  psmisc \
  util-linux \
  mosquitto \
  mosquitto-clients
```

Verify the installations:

```bash
python3 --version
java -version
mosquitto -h | head -n 1
```

Start the local MQTT broker required by long-run profile switching:

```bash
sudo systemctl enable --now mosquitto
```

On a WSL installation without systemd:

```bash
sudo service mosquitto start
```

Verify that the broker is listening:

```bash
ss -ltn | grep ':1883'
```

Python 3.10 is the supported reproduction version. Newer Python releases may
work, but they were not used for the final experiment.
If `python3` does not point to Python 3.10, select it explicitly when running
the setup script:

```bash
RL_PYTHON=python3.10 ./setup_rl_env.sh .venv-rl auto
```

## 3. Create the Python Environment

The setup script accepts an environment directory and a PyTorch variant:

```text
./setup_rl_env.sh [VENV_DIR] [auto|cpu|cu128]
```

### Automatic selection

```bash
./setup_rl_env.sh .venv-rl auto
source .venv-rl/bin/activate
```

`auto` selects the CUDA 12.8 PyTorch build when `nvidia-smi` is available.
Otherwise, it installs the CPU build. Detection does not validate the NVIDIA
driver version. Use the explicit `cpu` option if CUDA initialization fails.

### CPU-only installation

```bash
./setup_rl_env.sh .venv-rl cpu
source .venv-rl/bin/activate
```

### CUDA 12.8 installation

```bash
./setup_rl_env.sh .venv-rl cu128
source .venv-rl/bin/activate
```

Export the workspace paths after activating the environment:

```bash
export CONTIKI_NG="$PWD/contiki-ng"
export PYTHONPATH="$PWD/SDWSN-controller${PYTHONPATH:+:$PYTHONPATH}"
```

Verify the Python environment:

```bash
python -c "import torch; print('torch=', torch.__version__, 'cuda=', torch.cuda.is_available())"
python -c "import sdwsn_controller; print('sdwsn_controller: OK')"
pip check
```

## 4. Validate the Source Before Running

### Slotframe-control unit tests

```bash
pytest -q \
  SDWSN-controller/tests/test_env_slotframe_controls.py \
  SDWSN-controller/tests/test_trend_sweep_completion.py
```

Expected result:

```text
........... [100%]
```

### Cooja/Gradle validation

```bash
cd contiki-ng/tools/cooja
./gradlew test
cd ../../..
```

The expected result is `BUILD SUCCESSFUL`. This validates the Cooja Java/Gradle
project; it does not compile or execute the experiment mote. The trend and
long-run smoke tests perform the complete Cooja startup and mote compilation
path. Do not run `make TARGET=cooja` directly in the mote application directory.

### Controller port

Cooja and the controller communicate through TCP port `60001` by default.
Long-run profile switching additionally requires the MQTT broker on port
`1883`.

```bash
ss -ltnp | grep ':60001' || true
ss -ltnp | grep ':1883'
```

If an old Cooja process is holding the port:

```bash
pkill -f 'org.contikios.cooja.Main' || true
fuser -k 60001/tcp || true
```

Only run these commands when no other experiment is active.

## 5. Smoke Tests

Run the smoke tests before starting a full experiment. Smoke outputs are written
under `smoke/` and are ignored by Git.

### 5.1 Trend smoke test

```bash
SMOKE_TREND_OUT="$PWD/smoke/trend/output"
SMOKE_TREND_LOG="$PWD/smoke/trend/logs"

python run_trend_sweep.py \
  --seeds 1 \
  --output-base "$SMOKE_TREND_OUT" \
  --log-base "$SMOKE_TREND_LOG" \
  --explore-prob 0.35 \
  --hold-prob 0.15 \
  --max-wait-retries 3 \
  --max-cycles 40 \
  --min-valid-rows 20 \
  --min-slotframes 15
```

Inspect the generated files:

```bash
find "$SMOKE_TREND_OUT/cycle_r500_s1" -maxdepth 1 -type f | sort
```

The output must include:

```text
example.csv
coverage_summary.json
trend_vectors.json
```

Do not use vectors from a smoke run to train the final model.

### 5.2 Training smoke test

This test runs one PPO rollout:

```bash
SMOKE_TRAIN="$PWD/smoke/training"

RL_RUN_DIR="$SMOKE_TRAIN" \
RL_SEED=123 \
RL_TOTAL_STEPS=4096 \
RL_EVAL_FREQ=4096 \
RL_N_EVAL_EPISODES=20 \
python SDWSN-controller/tutorials/reinforcement-learning/training/test_numerical_reinforcement_learning.py
```

### 5.3 Long-run smoke test

```bash
MODEL="$PWD/results/training/trained_model/best_model.zip"

ELISE_MAX_CYCLES=20 \
ELISE_OUTPUT_BASE="$PWD/smoke/long_run/output" \
ELISE_LOG_BASE="$PWD/smoke/long_run/logs" \
./run_long_run_with_seed.sh 43 "$MODEL"
```

Verify the output:

```bash
wc -l smoke/long_run/output/seed_43/example.csv
```

The file should contain one header row and 20 data rows.

## 6. Stage 1: Collect Trend Data

Trend data are collected in Cooja with the `balanced` requirement profile fixed.
The baseline action pattern alternates between increasing and decreasing the
slotframe size. Random exploration adds coverage across the valid slotframe
domain, while the hold probability adds repeated observations.

```bash
TREND_OUT="$PWD/SDWSN-controller/tutorials/reinforcement-learning/output/final_trend"
TREND_LOG="$PWD/SDWSN-controller/tutorials/reinforcement-learning/tensorlog/final_trend"

python run_trend_sweep.py \
  --start 1 --count 20 \
  --output-base "$TREND_OUT" \
  --log-base "$TREND_LOG" \
  --explore-prob 0.35 \
  --hold-prob 0.15 \
  --max-wait-retries 3
```

By default, each seed runs for `max_episode_steps=1200`, as configured in
`native_controller_approx_model.json`. A completed production seed requires at
least:

- 1,000 valid measurement rows
- 30 distinct slotframe sizes
- `example.csv`
- `coverage_summary.json`
- `trend_vectors.json`

### Resume behavior

Checkpointing is performed at seed granularity. Re-running the same command
skips a seed only after parsing its coverage summary and trend vectors,
confirming the requested row count, slotframe coverage, metric coefficients, and
fixed profile. Missing, malformed, interrupted, or insufficient output is
executed again.

Count completed seeds:

```bash
find "$TREND_OUT" -path '*/trend_vectors.json' | wc -l
```

Check the number of rows in each seed:

```bash
for csv in "$TREND_OUT"/cycle_r500_s*/example.csv; do
  printf '%s: ' "$(basename "$(dirname "$csv")")"
  awk 'END { print NR - 1 }' "$csv"
done
```

Run one failed seed again:

```bash
python run_trend_sweep.py \
  --seeds 7 \
  --output-base "$TREND_OUT" \
  --log-base "$TREND_LOG" \
  --explore-prob 0.35 \
  --hold-prob 0.15 \
  --max-wait-retries 3
```

Use `--rerun-completed` only when a completed seed must intentionally be
replaced.

## 7. Fit the Pooled Trend Vectors

Run the fitting stage only after all 20 seeds pass the coverage checks:

```bash
TRAIN_CONFIG="$PWD/SDWSN-controller/tutorials/reinforcement-learning/training/numerical_controller_rl.json"

python SDWSN-controller/tutorials/reinforcement-learning/plot_seed_trends.py \
  --base-dir "$TREND_OUT" \
  --config "$TRAIN_CONFIG" \
  --min-valid-rows 1000 \
  --min-slotframes 30 \
  --min-seeds 20 \
  --required-profile balanced \
  --write-config
```

The pooled outputs are written to:

```text
$TREND_OUT/summary/power_trends.png
$TREND_OUT/summary/delay_trends.png
$TREND_OUT/summary/reliability_trends.png
$TREND_OUT/summary/summary_fits.json
```

`--write-config` updates these coefficient arrays:

```text
performance_metrics.energy.weights
performance_metrics.delay.weights
performance_metrics.pdr.weights
```

Do not manually modify the fitted coefficients when reproducing the same
workflow.

## 8. Stage 2: Train the PPO Policy

The current training configuration uses:

- Four rotating profiles: `balanced`, `delay`, `energy`, and `reliability`
- A random initial slotframe size in the valid range 10-68
- Three actions: increase, decrease, and hold
- Training seed `123`
- `5,996,544` requested training steps
- Evaluation every `8,192` steps
- 20 evaluation episodes

Action mapping:

| Action | Meaning |
|---:|---|
| `0` | Increase to the next valid coprime slotframe size |
| `1` | Decrease to the previous valid coprime slotframe size |
| `2` | Hold the current slotframe size |

### Foreground training

```bash
TRAIN_ROOT="$PWD/SDWSN-controller/tutorials/reinforcement-learning/training/runs/final_train"
mkdir -p "$TRAIN_ROOT"

RL_RUN_DIR="$TRAIN_ROOT" \
RL_SEED=123 \
RL_TOTAL_STEPS=5996544 \
RL_EVAL_FREQ=8192 \
RL_N_EVAL_EPISODES=20 \
python SDWSN-controller/tutorials/reinforcement-learning/training/test_numerical_reinforcement_learning.py
```

### Background training with nohup

```bash
TRAIN_ROOT="$PWD/SDWSN-controller/tutorials/reinforcement-learning/training/runs/final_train"
mkdir -p "$TRAIN_ROOT"

nohup env \
  RL_RUN_DIR="$TRAIN_ROOT" \
  RL_SEED=123 \
  RL_TOTAL_STEPS=5996544 \
  RL_EVAL_FREQ=8192 \
  RL_N_EVAL_EPISODES=20 \
  python SDWSN-controller/tutorials/reinforcement-learning/training/test_numerical_reinforcement_learning.py \
  > "$TRAIN_ROOT/train.log" 2>&1 &

echo $! | tee "$TRAIN_ROOT/train.pid"
tail -f "$TRAIN_ROOT/train.log"
```

Check whether the process is still running:

```bash
ps -p "$(cat "$TRAIN_ROOT/train.pid")" -o pid,etime,cmd
```

Locate the canonical model after training:

```bash
MODEL="$(find "$TRAIN_ROOT" -path '*/trained_model/best_model.zip' -type f | sort | tail -n 1)"
test -n "$MODEL" && test -f "$MODEL"
echo "$MODEL"
```

Each execution creates a `ppo_run_<timestamp>` directory. The main artifacts
are:

```text
trained_model/best_model.zip
trained_model/model_selection.json
metrics/policy_grid_evaluation.csv
metrics/eval_metrics.csv
numerical_controller_rl.json
output/*.png
```

Proceed to long-run evaluation only after `policy_grid_evaluation.csv` contains
all 20 grid cases and every case has `direction_ok=True`.

Check this condition directly:

```bash
python - "$MODEL" <<'PY'
import csv
import sys
from pathlib import Path

model = Path(sys.argv[1]).resolve()
grid = model.parents[1] / "metrics" / "policy_grid_evaluation.csv"
with grid.open(newline="", encoding="utf-8") as stream:
    rows = list(csv.DictReader(stream))
passed = sum(row["direction_ok"].lower() == "true" for row in rows)
print(f"policy grid: {passed}/{len(rows)}")
raise SystemExit(0 if len(rows) == 20 and passed == 20 else 1)
PY
```

## 9. Stage 3: Long-Run Evaluation

Long-run seeds must execute sequentially because Cooja uses a single controller
port. The trend and long-run wrappers enforce this with a shared file lock. Each
seed contains 1,200 cycles divided into four 300-cycle profile periods:

| Profile | Weights `(alpha, beta, delta)` | Priority |
|---|---:|---|
| balanced | `(0.4, 0.3, 0.3)` | Balanced objectives |
| delay | `(0.1, 0.8, 0.1)` | End-to-end delay |
| energy | `(0.8, 0.1, 0.1)` | Power/energy consumption |
| reliability | `(0.1, 0.1, 0.8)` | Reliability/PDR |

Before starting, verify that Mosquitto is active and port `60001` is free:

```bash
ss -ltn | grep ':1883'
ss -ltn | grep ':60001' && echo "ERROR: port 60001 is busy" || true
```

Run seeds 43 through 50:

```bash
MODEL="/absolute/path/to/trained_model/best_model.zip"
LONG_OUT="$PWD/SDWSN-controller/tutorials/reinforcement-learning/long-run/output/final_long_run"
LONG_LOG="$PWD/SDWSN-controller/tutorials/reinforcement-learning/long-run/logs/final_long_run"

ELISE_OUTPUT_BASE="$LONG_OUT" \
ELISE_LOG_BASE="$LONG_LOG" \
ELISE_PROFILE_SWITCH_SOURCE=applayer \
ELISE_MAX_CYCLES=1200 \
./run_long_run_seed_range.sh 43 50 "$MODEL"
```

Check progress:

```bash
for csv in "$LONG_OUT"/seed_*/example.csv; do
  printf '%s: ' "$(basename "$(dirname "$csv")")"
  awk 'END { print NR - 1 }' "$csv"
done
```

Each completed seed must contain 1,200 data rows. Long-run evaluation does not
checkpoint within a seed. Before a seed starts, the wrapper moves any non-empty
output and log directories for that seed to
`<directory>.previous_<UTC timestamp>`. This prevents an interrupted new run
from being mistaken for an older completed run.

If a power failure or crash interrupts one seed, restart that seed from the
beginning:

```bash
ELISE_OUTPUT_BASE="$LONG_OUT" \
ELISE_LOG_BASE="$LONG_LOG" \
ELISE_PROFILE_SWITCH_SOURCE=applayer \
ELISE_MAX_CYCLES=1200 \
./run_long_run_with_seed.sh 47 "$MODEL"
```

Do not run multiple seeds concurrently on the same TCP port.

## 10. Analyze Long-Run Results

After all seeds have completed:

```bash
python SDWSN-controller/tutorials/reinforcement-learning/long-run/analyze_long_run_results.py \
  --input-dir "$LONG_OUT" \
  --output-dir "$LONG_OUT/analysis" \
  --transition-cycles 50 \
  --timeline-window 15
```

Inspect the quality summary:

```bash
cat "$LONG_OUT/analysis/quality_summary.json"
```

The final committed run satisfies:

```text
seed_count = 8
total_rows = 9600
valid_cycles = 9600
invalid_cycles = 0
wait_timeouts = 0
all_runs_complete = true
```

## 11. Observed Runtime

Runtime depends on CPU performance, Cooja stalls, storage, and GPU availability.
On the machine used for the final experiment:

| Stage | Observed elapsed time |
|---|---:|
| Trend collection, 20 sequential seeds | approximately 52 hours |
| PPO training, CUDA 12.8 | approximately 4 hours |
| Long-run evaluation, 8 sequential seeds | approximately 18 hours |

These values are planning references, not execution time limits. The scientific
stopping conditions remain the configured cycle or training-step counts.

## 12. Committed Final Artifacts

The final results can be inspected without re-running the experiments:

```text
results/trend/       20 seeds x 1,200 cycles
results/training/    PPO seed 123, 5,996,544 requested steps, grid 20/20
results/long_run/    seeds 43-50 x 1,200 cycles
```

Verify that the artifacts have not changed:

```bash
sha256sum --check results/MANIFEST.sha256
```

Load the selected model on a CPU:

```bash
python - <<'PY'
from stable_baselines3 import PPO

PPO.load("results/training/trained_model/best_model.zip", device="cpu")
print("model: OK")
PY
```

## 13. Main Data Fields

The primary CSV files are the trend and long-run `example.csv` files and the
training `eval_metrics.csv` file.

| Column | Description |
|---|---|
| `cycle_idx` | Cycle index within one seed |
| `seed` | Cooja random seed |
| `profile` | Active balanced/delay/energy/reliability profile |
| `alpha`, `beta`, `delta` | Objective weights |
| `current_sf_len` | Slotframe size used in the cycle |
| `last_ts_in_schedule` | Last active timeslot in the schedule |
| `power_normalized` | Normalized power metric |
| `delay_mean` | Raw network-wide mean delay |
| `delay_normalized` | Normalized delay metric |
| `pdr_mean` | Mean packet delivery ratio across nodes |
| `reward` | Reward computed from metrics and active weights |
| `action` | Action requested by the policy or sampler |
| `applied_action` | Action that was actually applied |
| `requested_sf_len` | Requested slotframe size |
| `applied_sf_len` | Slotframe size that was actually applied |
| `action_overridden` | Whether boundary handling replaced the action |
| `wait_timeout` | Whether the processing window timed out |
| `valid_cycle` | Whether the cycle is valid for analysis |

`delay_mean` is the network-wide mean for one cycle, not a list of per-packet
delays.

## 14. Stall and Retry Semantics

- The controller allows up to 30 seconds for one processing window.
- If the window stalls, the same pending configuration and action are retried up
  to three times.
- A cycle is recorded as valid only after successful processing.
- Failed observations are marked with `wait_timeout=True` and
  `valid_cycle=False`.
- The committed final long-run dataset has no wait timeouts and contains all
  9,600 expected valid cycles.

Do not reduce the timeout or disable retries merely to shorten execution time.
Doing so can change the resulting dataset.

## 15. Troubleshooting

### Stuck at `Waiting for Cooja to start`

1. Verify Java 17 with `java -version`.
2. Check whether port `60001` is occupied.
3. Stop stale Cooja processes using the commands in Section 4.
4. Run `./gradlew test` in `contiki-ng/tools/cooja`.
5. Inspect the log directory configured through `ELISE_LOG_BASE`.

### MQTT broker is not listening

```bash
sudo systemctl restart mosquitto 2>/dev/null || sudo service mosquitto restart
ss -ltn | grep ':1883'
```

### `ModuleNotFoundError`

```bash
source .venv-rl/bin/activate
export PYTHONPATH="$PWD/SDWSN-controller${PYTHONPATH:+:$PYTHONPATH}"
pip check
```

### CUDA is unavailable

GPU acceleration is optional. Create a CPU environment:

```bash
./setup_rl_env.sh .venv-rl-cpu cpu
source .venv-rl-cpu/bin/activate
```

### Permission denied while creating output

Do not run the pipeline with `sudo`. Repair ownership of directories previously
created by root:

```bash
sudo chown -R "$USER:$USER" \
  SDWSN-controller/tutorials/reinforcement-learning/output \
  SDWSN-controller/tutorials/reinforcement-learning/tensorlog \
  SDWSN-controller/tutorials/reinforcement-learning/training/runs \
  SDWSN-controller/tutorials/reinforcement-learning/long-run/output \
  SDWSN-controller/tutorials/reinforcement-learning/long-run/logs
```

### Power failure or interrupted process

- Trend collection: re-run the same command. Completed seeds are skipped.
- Training: use a run only after it produces `model_selection.json` and the
  policy-grid evaluation. An interrupted run is not a final model.
- Long-run evaluation: preserve completed seeds and restart the interrupted seed
  from its beginning.

## 16. Reproducibility Guidelines

- Create a new output directory for every experiment.
- Treat `results/` as the final reference baseline and do not overwrite it.
- Record the random seed, configuration, model path, and Git commit.
- Change one controlled group of parameters at a time.
- Perform statistical comparisons at seed level; cycles from one seed are not
  independent experimental replicates.
- Do not commit virtual environments, Cooja logs, intermediate checkpoints, or
  personal reports.

## 17. Upstream Source and Licenses

The control plane inherits components from SDWSN-controller/ELISE by Fernando
Jurado-Lasso. The data plane inherits Contiki-NG and its bundled dependencies.
See `LICENSES.md`, `SDWSN-controller/LICENSE`, `contiki-ng/LICENSE.md`, and the
license notices bundled with third-party components before redistributing the
project.
