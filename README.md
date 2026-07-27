# Adaptive TSCH Slotframe Optimization with Reinforcement Learning

Source code and final experimental artifacts for adaptive TSCH slotframe-size
optimization using reinforcement learning in an SDWSN architecture.

## Repository layout

- `SDWSN-controller/`: Python control plane, numerical RL environment, PPO
  training code, long-run evaluation, and analysis scripts.
- `contiki-ng/`: Contiki-NG data plane and the Cooja scenario used by the
  experiments.
- `results/trend/`: final 20-seed Cooja trend dataset and pooled trend models.
- `results/training/`: selected PPO model, configuration snapshot, evaluation
  metrics, and final training plots.
- `results/long_run/`: final 8-seed long-run raw data and aggregated analysis.
- `run_trend_sweep.py`: sequential multi-seed trend collection.
- `run_long_run_seed_range.sh`: sequential multi-seed long-run evaluation.
- `setup_rl_env.sh`: Python environment setup.

Intermediate logs, checkpoints, caches, local paths, and thesis/report files are
not included.

## Environment

The experiments were run with Python 3.10, Contiki-NG/Cooja, Java, and the
packages installed by:

```bash
./setup_rl_env.sh
source .venv-rl/bin/activate
export CONTIKI_NG="$PWD/contiki-ng"
```

The setup script installs the CUDA 12.8 build of PyTorch. Change its PyTorch
index URL when running on a CPU-only machine or a different CUDA stack.

## 1. Collect trend data

Trend collection keeps the balanced requirement profile fixed while exploring
the valid slotframe domain:

```bash
TREND_OUT="$PWD/SDWSN-controller/tutorials/reinforcement-learning/output/trend"
TREND_LOG="$PWD/SDWSN-controller/tutorials/reinforcement-learning/tensorlog/trend"

python run_trend_sweep.py \
  --start 1 --count 20 \
  --output-base "$TREND_OUT" \
  --log-base "$TREND_LOG" \
  --explore-prob 0.35 \
  --hold-prob 0.15 \
  --max-wait-retries 3
```

Pool the accepted seeds and write the fitted coefficients to the training
configuration:

```bash
python SDWSN-controller/tutorials/reinforcement-learning/plot_seed_trends.py \
  --base-dir "$TREND_OUT" \
  --config SDWSN-controller/tutorials/reinforcement-learning/training/numerical_controller_rl.json \
  --min-valid-rows 1000 \
  --min-slotframes 30 \
  --required-profile balanced \
  --min-seeds 20 \
  --write-config
```

## 2. Train PPO

Training rotates the four requirement profiles and initializes each episode
from a random valid slotframe:

```bash
export RL_RUN_DIR="$PWD/SDWSN-controller/tutorials/reinforcement-learning/training/runs"
export RL_SEED=123
export RL_TOTAL_STEPS=5996544

python SDWSN-controller/tutorials/reinforcement-learning/training/test_numerical_reinforcement_learning.py
```

The canonical selected model is written to
`<run>/trained_model/best_model.zip`.

## 3. Run long-run evaluation

```bash
MODEL="$PWD/results/training/trained_model/best_model.zip"
export ELISE_OUTPUT_BASE="$PWD/SDWSN-controller/tutorials/reinforcement-learning/long-run/output"
export ELISE_LOG_BASE="$PWD/SDWSN-controller/tutorials/reinforcement-learning/long-run/logs"

./run_long_run_seed_range.sh 43 50 "$MODEL"
```

Each seed runs 1,200 cycles. The requirement profile changes every 300 cycles
in the order balanced, delay, energy, and reliability.

## Final artifacts

The committed `results/` directory contains only the final run:

- trend data: 20 seeds, 1,200 valid cycles per seed;
- PPO: seed 123, 5,996,544 training steps, selected model and grid evaluation;
- long-run: seeds 43-50, 1,200 valid cycles per seed.

See `results/MANIFEST.sha256` for artifact checksums.
