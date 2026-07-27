#!/usr/bin/env python3
"""
Aggregate long-run results across multiple seeds and plot per-profile statistics.

Reads all `example.csv` files under `output/seed_*/` and computes, for each
profile (balanced, delay, energy, reliability), the mean and standard deviation
of key metrics, then saves a summary table and bar plots.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Tuple

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

PROFILE_LABELS: Dict[Tuple[float, float, float], str] = {
    (0.4, 0.3, 0.3): "balanced",
    (0.1, 0.8, 0.1): "delay",
    (0.8, 0.1, 0.1): "energy",
    (0.1, 0.1, 0.8): "reliability",
}

PROFILE_ORDER = ["balanced", "delay", "energy", "reliability"]
PROFILE_COLORS: Dict[str, str] = {
    "balanced": "tab:blue",
    "delay": "tab:orange",
    "energy": "tab:green",
    "reliability": "tab:red",
}


def profile_name(alpha: float, beta: float, delta: float) -> str:
    key = (round(alpha, 1), round(beta, 1), round(delta, 1))
    return PROFILE_LABELS.get(key, f"({alpha:.1f},{beta:.1f},{delta:.1f})")


def load_all_runs(base_output: Path) -> pd.DataFrame:
    """Load all example.csv files under seed_* folders and tag them with seed."""
    rows = []
    for seed_dir in sorted(base_output.glob("seed_*")):
        if not seed_dir.is_dir():
            continue
        csv_path = seed_dir / "example.csv"
        if not csv_path.is_file():
            continue
        seed_name = seed_dir.name.split("_", 1)[-1]
        df = pd.read_csv(csv_path)
        df["seed"] = seed_name
        rows.append(df)
    if not rows:
        raise SystemExit(f"No seed_*/example.csv found under {base_output}")
    return pd.concat(rows, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate long-run results across seeds."
    )
    parser.add_argument(
        "--output-dir",
        default="SDWSN-controller/tutorials/reinforcement-learning/long-run/output",
        help="Base output directory containing seed_* folders",
    )
    parser.add_argument(
        "--summary-csv",
        default="long_run_aggregate_summary.csv",
        help="Filename for aggregated CSV (inside output-dir)",
    )
    parser.add_argument(
        "--summary-fig",
        default="long_run_aggregate_summary.png",
        help="Filename for aggregate plot (inside output-dir)",
    )
    parser.add_argument(
        "--timeseries-fig",
        default="long_run_aggregate_timeseries.png",
        help="Filename for a representative timeseries plot (inside output-dir)",
    )
    parser.add_argument(
        "--timeseries-csv",
        default="",
        help="Optional path to a specific CSV to plot timeseries; if empty, pick the first seed_* run or fallback to output/example.csv",
    )
    parser.add_argument(
        "--min-valid-per-profile",
        type=int,
        default=250,
        help="Minimum valid cycles required for a seed/profile to enter aggregate stats",
    )
    args = parser.parse_args()

    base_output = Path(args.output_dir).resolve()
    df = load_all_runs(base_output)

    # Derive profile name
    if "profile" not in df.columns:
        df["profile"] = [
            profile_name(a, b, d) for a, b, d in zip(df["alpha"], df["beta"], df["delta"])
        ]

    raw_rows = len(df)
    if "valid_cycle" in df.columns:
        valid_mask = df["valid_cycle"].astype(str).str.lower().isin(["true", "1"])
        df = df[valid_mask].copy()
    valid_rows = len(df)
    print(f"Loaded {raw_rows} rows, using {valid_rows} valid rows.")

    # For each seed+profile, compute per-run averages
    metrics = ["reward", "power_normalized", "delay_normalized", "pdr_mean"]
    profile_counts = (
        df.groupby(["seed", "profile"], as_index=False)
        .size()
        .rename(columns={"size": "valid_count"})
    )
    counts_csv_path = base_output / "long_run_profile_counts.csv"
    profile_counts.to_csv(counts_csv_path, index=False)
    print(f"Saved profile counts to {counts_csv_path}")

    eligible = profile_counts[
        profile_counts["valid_count"] >= int(args.min_valid_per_profile)
    ][["seed", "profile"]]
    df = df.merge(eligible, on=["seed", "profile"], how="inner")
    if df.empty:
        raise SystemExit(
            "No seed/profile group has enough valid cycles. "
            f"Lower --min-valid-per-profile or rerun failed seeds."
        )

    grouped = (
        df.groupby(["seed", "profile"], as_index=False)[metrics + ["current_sf_len"]]
        .mean()
        .rename(columns={"current_sf_len": "sf_len_mean"})
    )

    # Then aggregate across seeds for each profile (exclude non-numeric 'seed')
    grouped_numeric = grouped.drop(columns=["seed"])
    agg = grouped_numeric.groupby("profile").agg(["mean", "std"])
    # Flatten columns
    agg.columns = ["_".join(col).strip() for col in agg.columns.values]
    agg = agg.reset_index()

    # Reorder profiles
    agg["profile"] = pd.Categorical(agg["profile"], PROFILE_ORDER, ordered=True)
    agg = agg.sort_values("profile")

    # Save CSV
    summary_csv_path = base_output / args.summary_csv
    agg.to_csv(summary_csv_path, index=False)
    print(f"Saved aggregate summary to {summary_csv_path}")

    # Plot bar charts with error bars for each metric
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    axes = axes.ravel()

    plot_specs = [
        ("reward", "Reward"),
        ("power_normalized", "Power (normalized)"),
        ("delay_normalized", "Delay (normalized)"),
        ("pdr_mean", "Reliability (PDR)"),
    ]

    x = range(len(PROFILE_ORDER))
    bar_colors = [PROFILE_COLORS.get(p, "gray") for p in agg["profile"]]

    for ax, (metric, title) in zip(axes, plot_specs):
        mean_col = f"{metric}_mean"
        std_col = f"{metric}_std"
        y = agg[mean_col].to_numpy()
        std = agg[std_col].to_numpy()
        # Clip nhánh dưới của error bar để không đi xuống <0 (nhất là các metric chuẩn hóa)
        yerr_lower = np.minimum(std, y)
        yerr = [yerr_lower, std]
        ax.bar(x, y, yerr=yerr, capsize=4, color=bar_colors, edgecolor="black", linewidth=0.5)
        ax.set_xticks(list(x))
        ax.set_xticklabels(list(agg["profile"]))
        ax.set_title(title)
        ax.grid(True, axis="y", linestyle="--", linewidth=0.3, alpha=0.6)

    fig.tight_layout()
    summary_fig_path = base_output / args.summary_fig
    fig.savefig(summary_fig_path, dpi=150)
    print(f"Saved aggregate plot to {summary_fig_path}")

    # ------------------------------------------------------------------
    # Optional: produce a timeseries plot similar to example_summary_new.png
    # using a representative CSV (first seed_* or provided).
    # ------------------------------------------------------------------
    ts_csv = Path(args.timeseries_csv) if args.timeseries_csv else None
    if ts_csv is None or not ts_csv.is_file():
        # pick first seed_* example.csv
        candidates = sorted(base_output.glob("seed_*/example.csv"))
        if candidates:
            ts_csv = candidates[0]
        else:
            # fallback to top-level example.csv
            candidate = base_output / "example.csv"
            ts_csv = candidate if candidate.is_file() else None

    if ts_csv is None or not ts_csv.is_file():
        print("No suitable CSV found for timeseries plot; skipping.")
        return

    df_ts = pd.read_csv(ts_csv)
    if df_ts.empty:
        print("Timeseries CSV is empty; skipping.")
        return
    if "valid_cycle" in df_ts.columns:
        df_ts = df_ts[df_ts["valid_cycle"].astype(str).str.lower().isin(["true", "1"])].copy()
    if df_ts.empty:
        print("Timeseries CSV has no valid cycles after filtering; skipping.")
        return
    df_ts = df_ts.reset_index(drop=True)
    df_ts["cycle"] = df_ts.index
    if "profile" not in df_ts.columns:
        df_ts["profile"] = [
            profile_name(a, b, d)
            for a, b, d in zip(df_ts["alpha"], df_ts["beta"], df_ts["delta"])
        ]

    # Determine contiguous runs of the same profile
    segments = []  # (start_idx, end_idx, profile)
    start = 0
    current_profile = df_ts.loc[0, "profile"]
    for idx in range(1, len(df_ts)):
        prof = df_ts.loc[idx, "profile"]
        if prof != current_profile:
            segments.append((start, idx - 1, current_profile))
            start = idx
            current_profile = prof
    segments.append((start, len(df_ts) - 1, current_profile))

    metrics_ts = [
        ("current_sf_len", "Slotframe size |C|"),
        ("reward", "Immediate reward"),
        ("power_normalized", "Power (normalized)"),
        ("delay_normalized", "Delay (normalized)"),
        ("pdr_mean", "Reliability (PDR)"),
    ]

    fig2, axes2 = plt.subplots(len(metrics_ts), 1, figsize=(10, 12), sharex=True)
    for ax, (col, title) in zip(axes2, metrics_ts):
        ax.set_ylabel(title)
        for start_idx, end_idx, prof in segments:
            seg = df_ts.loc[start_idx:end_idx]
            color = PROFILE_COLORS.get(prof, "gray")
            ax.plot(seg["cycle"], seg[col], color=color, linewidth=1.2)
            ax.axvspan(seg["cycle"].iloc[0], seg["cycle"].iloc[-1], color=color, alpha=0.06)
        ax.grid(True, linestyle="--", linewidth=0.3, alpha=0.6)
    axes2[-1].set_xlabel("Cycle index")

    # Legend
    handles = [
        plt.Line2D([0], [0], color=PROFILE_COLORS.get(p, "gray"), lw=2, label=p)
        for p in PROFILE_ORDER
    ]
    axes2[0].legend(handles=handles, loc="upper right")

    fig2.tight_layout()
    ts_fig_path = base_output / args.timeseries_fig
    fig2.savefig(ts_fig_path, dpi=150)
    print(f"Saved timeseries plot to {ts_fig_path}")


if __name__ == "__main__":
    main()
