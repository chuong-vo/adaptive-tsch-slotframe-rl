# Top-K Slotframe Dataset Collectors

This package collects exhaustive slotframe measurements without using an RL
policy to choose the evaluated actions. It contains two separate protocols:

- `G0`: the immutable 10-mote thesis baseline.
- `EXPANDED`: fixed chain, grid, and random-geometric topologies for training,
  validation, interpolation testing, and scale testing of a Top-K model.

Both collectors freeze their topology, candidate list, schedule, seeds, source
provenance, and execution plan before Cooja starts. A failed measurement is
recorded in `rejected_cycles.csv`; it is never silently treated as a sample.

## Prerequisites

Use Python 3.10, a JDK compatible with the bundled Cooja version, and the
standard native build tools. From the repository root:

```bash
python3.10 -m venv .venv-rl
source .venv-rl/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ./SDWSN-controller
export CONTIKI_NG="$PWD/contiki-ng"
```

Do not run a collector with `sudo`. The user running Python must own the
repository and output directory. Only one Cooja process may use TCP port
`60001` at a time.

## G0 Baseline

G0 reproduces the fixed 10-mote thesis environment. It measures every valid
slotframe in `10..68` that is coprime with TSCH periods `397`, `31`, and `27`.
The completed baseline is stored in `runs/topk_dataset/g0/` and must not be
overwritten by expanded experiments.

```bash
python -m experiments.topk_dataset.collect_g0 --prepare-only
python -m experiments.topk_dataset.collect_g0 --smoke
python -m experiments.topk_dataset.collect_g0
```

## Expanded Protocol

The expanded protocol is defined in `config/expanded.json`. All topologies are
fixed during a run and contain fewer than 50 motes. The frozen matrix contains:

- chain, grid, and random-geometric topology families;
- center and edge sink placements;
- node counts `8, 10, 12, 16, 20` for training, held-out layouts for
  validation, `14, 18` for interpolation tests, and `25, 32` for scale tests;
- normal traffic at 40 seconds and stress traffic at 10 seconds;
- 15 slotframe candidates spanning approximately `1.0 L0` to `4.0 L0`, where
  `L0 = N - 1` is the routing-tree schedule size;
- 10 independent Cooja seeds per context.

Prepare all CSC files and validate the frozen metadata without starting Cooja:

```bash
python -m experiments.topk_dataset.collect_expanded --prepare-only
```

Run a short smoke test or the six-context pilot matrix:

```bash
python -m experiments.topk_dataset.collect_expanded --smoke
python -m experiments.topk_dataset.collect_expanded --pilot
```

Run or resume the complete sequential collection:

```bash
python -m experiments.topk_dataset.collect_expanded
```

For a long unattended run, use the bounded supervisor from the repository
root. It resumes completed seed-context checkpoints and restarts an incomplete
seed-context from the beginning after a process failure:

```bash
nohup scripts/run_topk_expanded_collection.sh >/dev/null 2>&1 &
```

An existing output directory is accepted only when its manifest and execution
plan exactly match the current command. Smoke, pilot, and full outputs therefore
cannot be mixed accidentally.

## Output Contract

The main output files are:

- `manifest.json`, `config_snapshot.json`, and `execution_plan.json`: frozen
  protocol, source provenance, and planned independent runs.
- `topologies.csv`, `nodes.csv`, `edges.csv`, and `contexts.csv`: topology and
  simulation metadata.
- `schedules.json`: deterministic routing-tree schedules.
- `raw_cycles.csv`: accepted measurement cycles only.
- `warmup_cycles.csv`: valid transition cycles excluded from labels.
- `rejected_cycles.csv`: failed attempts and explicit reason codes.
- `run_summary.csv`: one row per context, Cooja seed, and slotframe.
- `context_action_labels.csv`: seed-level aggregate labels for Top-K training.
- `validation_report.json`: structural, metric-equation, source-counter, and
  completion checks.
- `runs/<run_id>/`: exact CSC, binaries, logs, counters, and completion marker
  for one independent seed-context run.

PDR is `received / source-transmitted` for the same measurement window.
Throughput is `received / simulated-duration`, delay is packet-weighted, and
power is reported both as total source power and power per source. A cycle is
accepted only when every expected source reports transmission and power data.
The final validator independently recounts source transmissions from the
preserved Cooja test log.
