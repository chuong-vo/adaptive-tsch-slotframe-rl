# GNN Observation Prototype

This directory documents the isolated graph-observation prototype on the
`experiment/gnn-ppo` branch. It does not change the observation space, policy,
training configuration, or results of the baseline PPO implementation.

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

The builder returns dynamic arrays instead of padding to the current ten-mote
Cooja topology. A later batching layer can concatenate graphs and provide a
batch vector without imposing a fixed network size.

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

## Current Boundary

`GraphObservationBuilder` produces framework-neutral NumPy arrays. The next
step is to add a GNN feature extractor and a Gymnasium-compatible observation
space, then train it as an alternative policy. No PyTorch Geometric dependency
is required for this first step.
