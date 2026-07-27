# GNN Observation Prototype

This directory documents the isolated GNN-PPO prototype on the
`experiment/gnn-ppo` branch. It does not change the observation space, policy,
training configuration, or results of the baseline PPO implementation unless
the graph wrapper and custom extractor are selected explicitly.

## Graph Definition

- One graph represents the latest complete SDWSN controller snapshot.
- Mote `0` is the virtual controller and is excluded.
- Mote `1` is the sink and is retained.
- Every remaining known mote is represented, including isolated motes.
- A directed edge `u -> v` exists when mote `u` reports mote `v` in its
  neighbor table.
- Node IDs are sorted and exposed separately for traceability. They are not
  used as learnable features.
- Edges are sorted by source ID and then destination ID.

The framework-neutral builder returns dynamic arrays instead of assuming the
current ten-mote Cooja topology.

For Stable-Baselines3, `PaddedGraphObservationAdapter` converts this dynamic
representation to a fixed-capacity dictionary. It adds `node_mask` and
`edge_mask`, and raises an error on capacity overflow instead of truncating the
graph. The default edge capacity is `max_nodes * max_nodes`.

## Feature Schema

Node features, in order:

1. `is_sink`
2. `rank_normalized`
3. `rank_available`
4. `neighbor_degree_normalized`
5. `energy_normalized`
6. `delay_normalized`
7. `pdr`
8. `energy_available`
9. `delay_available`
10. `pdr_available`
11. `tx_cell_count_normalized`
12. `rx_cell_count_normalized`

Edge features, in order:

1. `rssi_strength`
2. `rssi_available`
3. `etx_quality`
4. `etx_available`
5. `selected_route`
6. `tsch_scheduled`

Global features, in order:

1. `alpha`
2. `beta`
3. `delta`
4. `slotframe_size_normalized`
5. `last_active_timeslot_normalized`

## Normalization

- Energy uses the existing long-run interval `[0, 5000]`.
- Delay uses the existing long-run interval `[10, 15000]`.
- PDR is clipped to `[0, 1]`.
- Rank is divided by `254`; rank `255` is the protocol's unknown value.
- Neighbor degree is divided by `N - 1`.
- TX and RX cell counts are divided by the maximum slotframe size.
- RSSI is clipped to `[-100, 0]` dBm and mapped to `[0, 1]`.
- Raw ETX uses Contiki-NG's fixed-point divisor `128`. The learnable quality is
  `1 / max(ETX, 1)`, so a higher value consistently means a better link.
- Slotframe size and the last active timeslot are divided by the maximum
  slotframe size.

All normalized features are clipped to `[0, 1]`.

## Missing Data

The inherited metric classes return zero when no sample exists, and neighbor
advertisements can use zero for unknown link statistics. Each affected value
therefore has a separate availability feature. This lets the model distinguish
an unavailable measurement from a genuine low value.

Queue occupancy, offered traffic, retransmission count, and packet-drop count
are intentionally absent because the current Python controller does not expose
them. They should only be added after instrumenting the Contiki-NG data plane
and packet format.

## GNN Feature Extractor

`EdgeAwareGraphFeaturesExtractor` is a pure-PyTorch message-passing network:

1. Encode node and edge features independently.
2. Send edge-conditioned messages in the reported neighbor direction.
3. Mean-aggregate incoming messages at each destination node.
4. Update node states with residual connections and layer normalization.
5. Apply masked mean and max pooling over nodes.
6. Combine the pooled graph state with encoded global features.

The output is a fixed-size vector consumed by the standard PPO actor and critic.
The implementation is invariant to node ordering and ignores masked padding.
It does not require PyTorch Geometric.

## Stable-Baselines3 Integration

For an environment backed by a live network:

```python
from stable_baselines3 import PPO

from sdwsn_controller.reinforcement_learning.gnn_policy import (
    EdgeAwareGraphFeaturesExtractor,
)
from sdwsn_controller.reinforcement_learning.graph_env import (
    GraphObservationWrapper,
)

graph_env = GraphObservationWrapper(
    controller.reinforcement_learning.env,
    max_nodes=10,
)
model = PPO(
    "MultiInputPolicy",
    graph_env,
    policy_kwargs={
        "features_extractor_class": EdgeAwareGraphFeaturesExtractor,
        "features_extractor_kwargs": {
            "features_dim": 64,
            "hidden_dim": 64,
            "message_passing_steps": 2,
        },
    },
)
```

`max_nodes=10` matches the current Cooja scenario. Increase it explicitly for a
larger topology. Capacity overflow is treated as an error so that an experiment
cannot silently lose nodes or edges.

## Current Boundary

The existing numerical training environment only models aggregate energy,
delay, and PDR as functions of slotframe size. It has no per-node topology,
link metrics, routes, or schedules. Wrapping it with a fabricated constant
graph would let code run but would not train a meaningful GNN.

The trend collector can now record topology-aware transitions directly from
Cooja. Recording is optional and does not alter action selection, reward
calculation, retries, or the existing CSV output. Each record contains:

1. Graph state before the action.
2. Requested and applied action and slotframe size.
3. Graph state after the action.
4. Environment and returned rewards.
5. Valid-cycle, stall, termination, and truncation flags.

The compressed dataset and its integrity summary are published atomically as:

```text
graph_transitions.jsonl.gz
graph_transitions_summary.json
```

Runs write to `.part` files and replace final artifacts only on normal close.
A checksum, record counts, feature schemas, normalization parameters, action
counts, profile counts, and slotframe coverage are validated before a seed is
considered complete. Any interrupted or mismatched artifact pair is rerun.

### Dataset smoke run

From the repository root:

```bash
python run_trend_sweep.py \
  --seeds 1 \
  --output-base "$PWD/smoke/gnn_graph/output" \
  --log-base "$PWD/smoke/gnn_graph/logs" \
  --max-cycles 40 \
  --min-valid-rows 20 \
  --min-slotframes 0 \
  --explore-prob 0.35 \
  --hold-prob 0.15 \
  --record-graphs \
  --rerun-completed
```

### Full graph collection

The policy must see all requirement profiles during training. Use profile
cycling for the GNN dataset even though balanced-only collection remains valid
for fitting physical metric trends:

```bash
GRAPH_OUT="$PWD/runs/gnn_graph_collection/output"
GRAPH_LOG="$PWD/runs/gnn_graph_collection/logs"

python run_trend_sweep.py \
  --start 1 \
  --count 20 \
  --output-base "$GRAPH_OUT" \
  --log-base "$GRAPH_LOG" \
  --cycle-profiles \
  --requirements-refresh-every 300 \
  --explore-prob 0.35 \
  --hold-prob 0.15 \
  --max-wait-retries 3 \
  --record-graphs
```

Invalid/stalled transitions remain in the dataset for diagnostics and are
marked with `valid_cycle=false`. They must be excluded from model fitting.

The next implementation step is to build and validate a graph-aware surrogate
environment from these transitions. Online PPO training against Cooja remains
correct but is substantially slower.
