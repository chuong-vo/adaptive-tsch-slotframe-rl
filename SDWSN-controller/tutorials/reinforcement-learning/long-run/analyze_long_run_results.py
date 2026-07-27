#!/usr/bin/env python3
"""Validate, aggregate, and plot ELISE long-run experiments.

The independent experimental unit is a Cooja seed. Cycle-level observations
are first averaged within each seed/profile, then aggregated across seeds.
This avoids treating correlated cycles from one simulation as independent
replicates.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PROFILE_ORDER = ["balanced", "delay", "energy", "reliability"]
PROFILE_LABELS = {
    "balanced": "Balanced",
    "delay": "Delay",
    "energy": "Energy",
    "reliability": "Reliability",
}
PROFILE_COLORS = {
    "balanced": "#2878B5",
    "delay": "#F28E2B",
    "energy": "#3A923A",
    "reliability": "#C73E3A",
}
EXPECTED_WEIGHTS = {
    "balanced": (0.4, 0.3, 0.3),
    "delay": (0.1, 0.8, 0.1),
    "energy": (0.8, 0.1, 0.1),
    "reliability": (0.1, 0.1, 0.8),
}
PRIMARY_METRICS = [
    "sf_len",
    "power_normalized",
    "delay_normalized",
    "pdr",
    "reward",
]
ALL_MEAN_METRICS = [
    "sf_len",
    "power_normalized",
    "power_raw",
    "delay_normalized",
    "delay_ms",
    "pdr",
    "reward",
]
METRIC_LABELS = {
    "sf_len": "Slotframe size |C|",
    "power_normalized": "Power (normalized)",
    "power_raw": "Power (raw)",
    "delay_normalized": "Delay (normalized)",
    "delay_ms": "Delay (ms)",
    "pdr": "Packet delivery ratio",
    "reward": "Immediate reward",
}
SOURCE_COLUMNS = {
    "sf_len": "current_sf_len",
    "power_normalized": "power_normalized",
    "power_raw": "power_mean",
    "delay_normalized": "delay_normalized",
    "delay_ms": "delay_mean",
    "pdr": "pdr_mean",
    "reward": "reward",
}

# Two-sided Student-t 97.5% quantiles. Runs normally have n=8 (df=7).
T_CRITICAL_975 = {
    1: 12.7062,
    2: 4.3027,
    3: 3.1824,
    4: 2.7764,
    5: 2.5706,
    6: 2.4469,
    7: 2.3646,
    8: 2.3060,
    9: 2.2622,
    10: 2.2281,
    11: 2.2010,
    12: 2.1788,
    13: 2.1604,
    14: 2.1448,
    15: 2.1314,
    16: 2.1199,
    17: 2.1098,
    18: 2.1009,
    19: 2.0930,
    20: 2.0860,
    21: 2.0796,
    22: 2.0739,
    23: 2.0687,
    24: 2.0639,
    25: 2.0595,
    26: 2.0555,
    27: 2.0518,
    28: 2.0484,
    29: 2.0452,
    30: 2.0423,
}


def as_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin(["true", "1"])


def t_critical(n: int) -> float:
    if n < 2:
        return math.nan
    return T_CRITICAL_975.get(n - 1, 1.96)


def mean_ci(values: Iterable[float]) -> tuple[float, float, float, int]:
    values_array = np.asarray(list(values), dtype=float)
    values_array = values_array[np.isfinite(values_array)]
    n = len(values_array)
    if n == 0:
        return math.nan, math.nan, math.nan, 0
    mean = float(np.mean(values_array))
    if n == 1:
        return mean, math.nan, math.nan, n
    sd = float(np.std(values_array, ddof=1))
    ci = t_critical(n) * sd / math.sqrt(n)
    return mean, sd, ci, n


def exact_sign_flip_pvalue(differences: Iterable[float]) -> float:
    """Exact two-sided paired randomization p-value for a mean difference."""
    diff = np.asarray(list(differences), dtype=float)
    diff = diff[np.isfinite(diff)]
    if len(diff) == 0:
        return math.nan
    observed = abs(float(np.mean(diff)))
    permuted = []
    for signs in itertools.product((-1.0, 1.0), repeat=len(diff)):
        permuted.append(abs(float(np.mean(diff * np.asarray(signs)))))
    return float(np.mean(np.asarray(permuted) >= observed - 1e-12))


def load_runs(input_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    quality_rows: list[dict[str, object]] = []
    required = {
        "cycle_idx",
        "profile",
        "alpha",
        "beta",
        "delta",
        "valid_cycle",
        "wait_timeout",
        "current_sf_len",
        "power_normalized",
        "power_mean",
        "delay_normalized",
        "delay_mean",
        "pdr_mean",
        "reward",
        "action",
        "applied_action",
        "action_overridden",
    }

    for csv_path in sorted(input_dir.glob("seed_*/example.csv")):
        seed_from_dir = int(csv_path.parent.name.split("_", 1)[1])
        frame = pd.read_csv(csv_path)
        missing = sorted(required.difference(frame.columns))
        if missing:
            raise ValueError(f"{csv_path} is missing columns: {', '.join(missing)}")
        frame["seed"] = seed_from_dir
        frame["valid_cycle_bool"] = as_bool(frame["valid_cycle"])
        frame["wait_timeout_bool"] = as_bool(frame["wait_timeout"])
        frame["action_overridden_bool"] = as_bool(frame["action_overridden"])

        cycle_values = frame["cycle_idx"].astype(int).tolist()
        expected_cycles = list(range(1, len(frame) + 1))
        profile_counts = frame["profile"].value_counts().to_dict()
        weights_ok = True
        for profile, weights in EXPECTED_WEIGHTS.items():
            subset = frame[frame["profile"] == profile]
            if subset.empty:
                weights_ok = False
                continue
            observed = subset[["alpha", "beta", "delta"]].drop_duplicates().to_numpy()
            if len(observed) != 1 or not np.allclose(observed[0], weights):
                weights_ok = False

        quality_rows.append(
            {
                "seed": seed_from_dir,
                "rows": len(frame),
                "cycle_min": min(cycle_values) if cycle_values else math.nan,
                "cycle_max": max(cycle_values) if cycle_values else math.nan,
                "cycles_contiguous": cycle_values == expected_cycles,
                "duplicate_cycles": int(frame["cycle_idx"].duplicated().sum()),
                "valid_cycles": int(frame["valid_cycle_bool"].sum()),
                "invalid_cycles": int((~frame["valid_cycle_bool"]).sum()),
                "wait_timeouts": int(frame["wait_timeout_bool"].sum()),
                "profile_counts_ok": profile_counts
                == {profile: 300 for profile in PROFILE_ORDER},
                "profile_weights_ok": weights_ok,
                **{
                    f"{profile}_cycles": int(profile_counts.get(profile, 0))
                    for profile in PROFILE_ORDER
                },
            }
        )
        frames.append(frame)

    if not frames:
        raise FileNotFoundError(f"No seed_*/example.csv files found under {input_dir}")

    data = pd.concat(frames, ignore_index=True)
    data = data.sort_values(["seed", "cycle_idx"]).reset_index(drop=True)
    data["profile"] = pd.Categorical(data["profile"], PROFILE_ORDER, ordered=True)
    data["profile_cycle"] = data.groupby(["seed", "profile"], observed=True).cumcount() + 1
    for output_name, source_name in SOURCE_COLUMNS.items():
        data[output_name] = pd.to_numeric(data[source_name], errors="coerce")
    return data, pd.DataFrame(quality_rows).sort_values("seed")


def seed_profile_means(data: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (seed, profile), group in data.groupby(["seed", "profile"], observed=True):
        row: dict[str, object] = {
            "seed": int(seed),
            "profile": str(profile),
            "cycles": len(group),
        }
        for metric in ALL_MEAN_METRICS:
            row[metric] = float(group[metric].mean())
        row["delay_ms_median"] = float(group["delay_ms"].median())
        row["delay_ms_p95"] = float(group["delay_ms"].quantile(0.95))
        row["pdr_p05"] = float(group["pdr"].quantile(0.05))
        row["sf_terminal_mode"] = int(group.tail(100)["sf_len"].mode().iloc[0])
        row["sf_terminal_median"] = float(group.tail(100)["sf_len"].median())
        row["sf_start"] = int(group.iloc[0]["sf_len"])
        row["sf_end"] = int(group.iloc[-1]["sf_len"])
        rows.append(row)
    result = pd.DataFrame(rows)
    result["profile"] = pd.Categorical(result["profile"], PROFILE_ORDER, ordered=True)
    return result.sort_values(["seed", "profile"]).reset_index(drop=True)


def aggregate_profiles(per_seed: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    value_columns = [
        *ALL_MEAN_METRICS,
        "delay_ms_median",
        "delay_ms_p95",
        "pdr_p05",
        "sf_terminal_mode",
        "sf_terminal_median",
        "sf_start",
        "sf_end",
    ]
    for profile in PROFILE_ORDER:
        subset = per_seed[per_seed["profile"] == profile]
        row: dict[str, object] = {"profile": profile}
        for column in value_columns:
            mean, sd, ci, n = mean_ci(subset[column])
            row[f"{column}_mean"] = mean
            row[f"{column}_sd"] = sd
            row[f"{column}_ci95"] = ci
            row[f"{column}_n"] = n
        rows.append(row)
    return pd.DataFrame(rows)


def paired_comparisons(per_seed: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    balanced = per_seed[per_seed["profile"] == "balanced"].set_index("seed")
    for profile in PROFILE_ORDER[1:]:
        candidate = per_seed[per_seed["profile"] == profile].set_index("seed")
        common_seeds = sorted(set(balanced.index).intersection(candidate.index))
        for metric in ALL_MEAN_METRICS:
            base_values = balanced.loc[common_seeds, metric].to_numpy(dtype=float)
            profile_values = candidate.loc[common_seeds, metric].to_numpy(dtype=float)
            differences = profile_values - base_values
            diff_mean, diff_sd, diff_ci, n = mean_ci(differences)
            base_mean = float(np.mean(base_values))
            percent = 100.0 * diff_mean / base_mean if base_mean else math.nan
            rows.append(
                {
                    "profile": profile,
                    "reference": "balanced",
                    "metric": metric,
                    "n_seed_pairs": n,
                    "balanced_mean": base_mean,
                    "profile_mean": float(np.mean(profile_values)),
                    "mean_difference": diff_mean,
                    "difference_sd": diff_sd,
                    "difference_ci95": diff_ci,
                    "percent_change_vs_balanced": percent,
                    "exact_sign_flip_p": exact_sign_flip_pvalue(differences),
                }
            )
    return pd.DataFrame(rows)


def all_paired_comparisons(per_seed: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    indexed = {
        profile: per_seed[per_seed["profile"] == profile].set_index("seed")
        for profile in PROFILE_ORDER
    }
    for reference, candidate_name in itertools.combinations(PROFILE_ORDER, 2):
        reference_data = indexed[reference]
        candidate_data = indexed[candidate_name]
        common_seeds = sorted(set(reference_data.index).intersection(candidate_data.index))
        for metric in ALL_MEAN_METRICS:
            reference_values = reference_data.loc[common_seeds, metric].to_numpy(dtype=float)
            candidate_values = candidate_data.loc[common_seeds, metric].to_numpy(dtype=float)
            differences = candidate_values - reference_values
            diff_mean, diff_sd, diff_ci, n = mean_ci(differences)
            reference_mean = float(np.mean(reference_values))
            rows.append(
                {
                    "reference": reference,
                    "candidate": candidate_name,
                    "metric": metric,
                    "n_seed_pairs": n,
                    "reference_mean": reference_mean,
                    "candidate_mean": float(np.mean(candidate_values)),
                    "mean_difference_candidate_minus_reference": diff_mean,
                    "difference_sd": diff_sd,
                    "difference_ci95": diff_ci,
                    "percent_change_vs_reference": (
                        100.0 * diff_mean / reference_mean if reference_mean else math.nan
                    ),
                    "exact_sign_flip_p": exact_sign_flip_pvalue(differences),
                }
            )
    return pd.DataFrame(rows)


def transition_summary(data: pd.DataFrame, min_sf: int, max_sf: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for (seed, profile), group in data.groupby(["seed", "profile"], observed=True):
        group = group.sort_values("profile_cycle")

        def first_cycle_at(target: int) -> float:
            hits = group.loc[group["sf_len"] == target, "profile_cycle"]
            return float(hits.iloc[0]) if not hits.empty else math.nan

        rows.append(
            {
                "seed": int(seed),
                "profile": str(profile),
                "start_sf": int(group.iloc[0]["sf_len"]),
                "end_sf": int(group.iloc[-1]["sf_len"]),
                "first_cycle_at_min_sf": first_cycle_at(min_sf),
                "first_cycle_at_max_sf": first_cycle_at(max_sf),
                "last_100_sf_mean": float(group.tail(100)["sf_len"].mean()),
                "last_100_sf_median": float(group.tail(100)["sf_len"].median()),
                "last_100_sf_mode": int(group.tail(100)["sf_len"].mode().iloc[0]),
                "last_100_sf_min": int(group.tail(100)["sf_len"].min()),
                "last_100_sf_max": int(group.tail(100)["sf_len"].max()),
            }
        )
    result = pd.DataFrame(rows)
    result["profile"] = pd.Categorical(result["profile"], PROFILE_ORDER, ordered=True)
    return result.sort_values(["seed", "profile"]).reset_index(drop=True)


def action_summary(data: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for profile in PROFILE_ORDER:
        group = data[data["profile"] == profile]
        raw = group["action"].value_counts().to_dict()
        applied = group["applied_action"].value_counts().to_dict()
        rows.append(
            {
                "profile": profile,
                "cycles": len(group),
                "raw_increase": int(raw.get(0, 0)),
                "raw_decrease": int(raw.get(1, 0)),
                "raw_hold": int(raw.get(2, 0)),
                "applied_increase": int(applied.get(0, 0)),
                "applied_decrease": int(applied.get(1, 0)),
                "applied_hold": int(applied.get(2, 0)),
                "overrides": int(group["action_overridden_bool"].sum()),
                "override_rate_percent": 100.0 * group["action_overridden_bool"].mean(),
                "cycles_at_min_sf": int((group["sf_len"] == group["sf_len"].min()).sum()),
                "cycles_at_max_sf": int((group["sf_len"] == group["sf_len"].max()).sum()),
            }
        )
    return pd.DataFrame(rows)


def tail_summary(data: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for profile in PROFILE_ORDER:
        group = data[data["profile"] == profile]
        rows.append(
            {
                "profile": profile,
                "cycles": len(group),
                "delay_ms_p50": float(group["delay_ms"].quantile(0.50)),
                "delay_ms_p90": float(group["delay_ms"].quantile(0.90)),
                "delay_ms_p95": float(group["delay_ms"].quantile(0.95)),
                "delay_ms_p99": float(group["delay_ms"].quantile(0.99)),
                "delay_ms_max": float(group["delay_ms"].max()),
                "cycles_delay_over_1s": int((group["delay_ms"] > 1000).sum()),
                "cycles_delay_over_5s": int((group["delay_ms"] > 5000).sum()),
                "pdr_p01": float(group["pdr"].quantile(0.01)),
                "pdr_p05": float(group["pdr"].quantile(0.05)),
                "cycles_pdr_below_0_9": int((group["pdr"] < 0.9).sum()),
            }
        )
    return pd.DataFrame(rows)


def style_axes(ax: plt.Axes) -> None:
    ax.grid(axis="y", color="#D9D9D9", linewidth=0.6, alpha=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def save_profile_figure(summary: pd.DataFrame, output_dir: Path) -> None:
    specs = [
        ("sf_len", "Slotframe size |C|"),
        ("power_normalized", "Normalized power"),
        ("delay_normalized", "Normalized delay"),
        ("pdr", "Packet delivery ratio"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11.2, 7.4))
    x = np.arange(len(PROFILE_ORDER))
    colors = [PROFILE_COLORS[p] for p in PROFILE_ORDER]
    for ax, (metric, label) in zip(axes.ravel(), specs):
        means = summary[f"{metric}_mean"].to_numpy(dtype=float)
        errors = summary[f"{metric}_ci95"].to_numpy(dtype=float)
        ax.errorbar(
            x,
            means,
            yerr=errors,
            fmt="none",
            ecolor="#202020",
            elinewidth=1.2,
            capsize=4,
            zorder=2,
        )
        ax.scatter(x, means, s=72, c=colors, edgecolor="white", linewidth=0.8, zorder=3)
        for xpos, value in zip(x, means):
            fmt = ".2f" if metric == "sf_len" else ".4f"
            ax.annotate(
                format(value, fmt),
                (xpos, value),
                xytext=(0, 9),
                textcoords="offset points",
                ha="center",
                fontsize=8.5,
            )
        ax.set_xticks(x, [PROFILE_LABELS[p] for p in PROFILE_ORDER])
        ax.set_ylabel(label)
        style_axes(ax)
    fig.suptitle("Long-run steady-state performance (mean and 95% CI across 8 seeds)", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"longrun_profile_summary.{suffix}", dpi=220, bbox_inches="tight")
    plt.close(fig)


def save_tradeoff_figure(summary: pd.DataFrame, output_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(10.6, 6.8))
    annotation_offsets = {
        "balanced": (12, 12),
        "delay": (-14, 18),
        "energy": (12, 10),
        "reliability": (-14, -26),
    }
    annotation_align = {
        "balanced": "left",
        "delay": "right",
        "energy": "left",
        "reliability": "right",
    }
    markers = {
        "balanced": "o",
        "delay": "s",
        "energy": "^",
        "reliability": "D",
    }
    legend_handles = []
    for profile in PROFILE_ORDER:
        row = summary.loc[summary["profile"] == profile].iloc[0]
        x = float(row["power_normalized_mean"])
        y = float(row["delay_normalized_mean"])
        ax.errorbar(
            x,
            y,
            xerr=float(row["power_normalized_ci95"]),
            yerr=float(row["delay_normalized_ci95"]),
            fmt=markers[profile],
            markersize=10,
            markerfacecolor=PROFILE_COLORS[profile],
            markeredgecolor="white",
            markeredgewidth=0.9,
            ecolor=PROFILE_COLORS[profile],
            elinewidth=1.3,
            capsize=4,
            zorder=3,
        )
        ax.annotate(
            PROFILE_LABELS[profile],
            (x, y),
            xytext=annotation_offsets[profile],
            textcoords="offset points",
            ha=annotation_align[profile],
            fontsize=10.5,
            color=PROFILE_COLORS[profile],
            fontweight="bold",
        )
        legend_handles.append(
            plt.Line2D(
                [0],
                [0],
                marker=markers[profile],
                color="none",
                markerfacecolor=PROFILE_COLORS[profile],
                markeredgecolor="white",
                markersize=9,
                label=(
                    f"{PROFILE_LABELS[profile]}  "
                    f"(SF {row['sf_len_mean']:.1f}, PDR {row['pdr_mean']:.4f})"
                ),
            )
        )

    ax.text(
        0.02,
        0.035,
        "Preferred direction: lower-left",
        transform=ax.transAxes,
        fontsize=9,
        color="#555555",
    )
    ax.set_xlabel("Normalized power  (lower is better)", labelpad=9)
    ax.set_ylabel("Normalized delay  (lower is better)", labelpad=9)
    ax.set_title("Steady-state power-delay trade-off", pad=15, fontsize=15)
    ax.set_xlim(0.108, 0.164)
    ax.set_ylim(0.006, 0.053)
    style_axes(ax)
    ax.tick_params(labelsize=10)
    ax.legend(
        handles=legend_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.16),
        ncol=2,
        frameon=False,
        columnspacing=2.4,
        handletextpad=0.5,
        fontsize=9.5,
    )
    fig.text(
        0.5,
        0.925,
        "Points show the mean across 8 seeds; error bars show 95% confidence intervals.",
        ha="center",
        fontsize=9.5,
        color="#555555",
    )
    fig.subplots_adjust(left=0.11, right=0.98, top=0.86, bottom=0.23)
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"longrun_power_delay_tradeoff.{suffix}", dpi=220, bbox_inches="tight")
    plt.close(fig)


def save_pdr_by_seed_figure(per_seed: pd.DataFrame, output_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.8, 5.9))
    x = np.arange(len(PROFILE_ORDER))
    pivot = per_seed.pivot(index="seed", columns="profile", values="pdr")
    pivot = pivot.reindex(columns=PROFILE_ORDER)
    jitter = np.linspace(-0.13, 0.13, len(pivot))
    for profile_index, profile in enumerate(PROFILE_ORDER):
        values = pivot[profile].to_numpy(dtype=float)
        ax.scatter(
            profile_index + jitter,
            values,
            color="#8F8F8F",
            s=34,
            alpha=0.72,
            edgecolor="white",
            linewidth=0.45,
            zorder=2,
        )

    means = pivot.mean(axis=0).to_numpy(dtype=float)
    ci_values = np.asarray([mean_ci(pivot[profile])[2] for profile in PROFILE_ORDER])
    ax.errorbar(
        x,
        means,
        yerr=ci_values,
        fmt="none",
        ecolor="#202020",
        elinewidth=1.4,
        capsize=4,
        zorder=3,
    )
    for xpos, profile, mean in zip(x, PROFILE_ORDER, means):
        ax.scatter(
            xpos,
            mean,
            marker="D",
            s=82,
            color=PROFILE_COLORS[profile],
            edgecolor="white",
            linewidth=0.8,
            zorder=4,
        )
        ax.annotate(
            f"{mean:.4f}",
            (xpos, mean),
            xytext=(0, 10),
            textcoords="offset points",
            ha="center",
            fontsize=8.5,
            fontweight="bold",
            color=PROFILE_COLORS[profile],
        )

    ax.set_xticks(x, [PROFILE_LABELS[p] for p in PROFILE_ORDER])
    ax.set_ylabel("Packet delivery ratio")
    ax.set_title("Steady-state packet delivery ratio by profile", pad=15, fontsize=15)
    data_min = float(np.nanmin(pivot.to_numpy(dtype=float)))
    data_max = float(np.nanmax(pivot.to_numpy(dtype=float)))
    margin = max(0.003, (data_max - data_min) * 0.15)
    ax.set_ylim(max(0.0, data_min - margin), min(1.002, data_max + margin))
    ax.tick_params(labelsize=10)
    ax.text(
        0.02,
        0.035,
        "Gray circles: seed means    Colored diamonds: overall mean",
        transform=ax.transAxes,
        fontsize=9,
        color="#555555",
    )
    style_axes(ax)
    fig.text(
        0.5,
        0.925,
        "Each seed mean uses 250 steady-state cycles; error bars show 95% confidence intervals.",
        ha="center",
        fontsize=9.5,
        color="#555555",
    )
    fig.subplots_adjust(left=0.11, right=0.98, top=0.86, bottom=0.13)
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"longrun_pdr_by_seed.{suffix}", dpi=220, bbox_inches="tight")
    plt.close(fig)


def profile_spans(data: pd.DataFrame) -> list[tuple[int, int, str]]:
    representative = data[data["seed"] == data["seed"].min()].sort_values("cycle_idx")
    spans: list[tuple[int, int, str]] = []
    for profile in PROFILE_ORDER:
        subset = representative[representative["profile"] == profile]
        spans.append((int(subset["cycle_idx"].min()), int(subset["cycle_idx"].max()), profile))
    return spans


def timeline_statistics(data: pd.DataFrame, window: int) -> pd.DataFrame:
    smoothed_frames: list[pd.DataFrame] = []
    columns = ["sf_len", "power_normalized", "delay_normalized", "pdr"]
    for (_, _), group in data.groupby(["seed", "profile"], observed=True):
        group = group.sort_values("cycle_idx").copy()
        for column in columns:
            if column == "sf_len":
                group[f"{column}_plot"] = group[column]
            else:
                group[f"{column}_plot"] = group[column].rolling(
                    window=window, center=True, min_periods=1
                ).mean()
        smoothed_frames.append(group)
    smoothed = pd.concat(smoothed_frames, ignore_index=True)

    rows: list[dict[str, object]] = []
    for cycle_idx, group in smoothed.groupby("cycle_idx"):
        row: dict[str, object] = {"cycle_idx": int(cycle_idx)}
        for column in columns:
            mean, sd, ci, n = mean_ci(group[f"{column}_plot"])
            row[f"{column}_mean"] = mean
            row[f"{column}_sd"] = sd
            row[f"{column}_ci95"] = ci
            row[f"{column}_n"] = n
        rows.append(row)
    return pd.DataFrame(rows).sort_values("cycle_idx")


def add_profile_background(ax: plt.Axes, spans: list[tuple[int, int, str]]) -> None:
    for start, end, profile in spans:
        ax.axvspan(start - 0.5, end + 0.5, color=PROFILE_COLORS[profile], alpha=0.07, linewidth=0)
    for boundary in [span[1] + 0.5 for span in spans[:-1]]:
        ax.axvline(boundary, color="#707070", linestyle="--", linewidth=0.8)


def save_timeline_figures(
    data: pd.DataFrame,
    timeline: pd.DataFrame,
    output_dir: Path,
    window: int,
) -> None:
    spans = profile_spans(data)
    x = timeline["cycle_idx"].to_numpy(dtype=float)
    specs = [
        ("sf_len", "Slotframe size |C|"),
        ("power_normalized", "Normalized power"),
        ("delay_normalized", "Normalized delay"),
        ("pdr", "Packet delivery ratio"),
    ]
    fig, axes = plt.subplots(4, 1, figsize=(12.4, 9.4), sharex=True)
    for ax, (metric, label) in zip(axes, specs):
        mean = timeline[f"{metric}_mean"].to_numpy(dtype=float)
        ci = timeline[f"{metric}_ci95"].to_numpy(dtype=float)
        add_profile_background(ax, spans)
        ax.fill_between(x, mean - ci, mean + ci, color="#4D4D4D", alpha=0.15, linewidth=0)
        ax.plot(x, mean, color="#202020", linewidth=1.15)
        ax.set_ylabel(label)
        style_axes(ax)
    axes[-1].set_xlabel("Long-run cycle")
    axes[-1].set_xlim(1, int(x.max()))
    legend_handles = [
        plt.Line2D([0], [0], color=PROFILE_COLORS[p], linewidth=8, alpha=0.35, label=PROFILE_LABELS[p])
        for p in PROFILE_ORDER
    ]
    axes[0].legend(handles=legend_handles, ncol=4, loc="upper center", frameon=False)
    fig.suptitle(
        f"Long-run response across 8 seeds (mean and 95% CI; metrics use {window}-cycle moving means)",
        fontsize=13,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"longrun_mean_timeline.{suffix}", dpi=220, bbox_inches="tight")
    plt.close(fig)

    sf_mean = timeline["sf_len_mean"].to_numpy(dtype=float)
    sf_ci = timeline["sf_len_ci95"].to_numpy(dtype=float)
    fig, ax = plt.subplots(figsize=(12.4, 4.4))
    add_profile_background(ax, spans)
    ax.fill_between(x, sf_mean - sf_ci, sf_mean + sf_ci, color="#202020", alpha=0.16, linewidth=0)
    ax.plot(x, sf_mean, color="#202020", linewidth=1.5)
    for start, end, profile in spans:
        ax.text(
            (start + end) / 2,
            0.97,
            PROFILE_LABELS[profile],
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="top",
            color=PROFILE_COLORS[profile],
            fontweight="bold",
        )
    ax.set_xlabel("Long-run cycle")
    ax.set_ylabel("Slotframe size |C|")
    ax.set_xlim(1, int(x.max()))
    ax.set_ylim(7, 72)
    style_axes(ax)
    ax.set_title("Slotframe adaptation under changing user requirements (8-seed mean and 95% CI)")
    fig.tight_layout()
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / f"longrun_slotframe_timeline.{suffix}", dpi=220, bbox_inches="tight")
    plt.close(fig)


def fmt_ci(summary: pd.DataFrame, profile: str, metric: str, decimals: int = 4) -> str:
    row = summary.loc[summary["profile"] == profile].iloc[0]
    return f"{row[f'{metric}_mean']:.{decimals}f} +/- {row[f'{metric}_ci95']:.{decimals}f}"


def write_report(
    output_dir: Path,
    input_dir: Path,
    quality: pd.DataFrame,
    full_summary: pd.DataFrame,
    steady_summary: pd.DataFrame,
    comparisons: pd.DataFrame,
    all_comparisons: pd.DataFrame,
    transitions: pd.DataFrame,
    actions: pd.DataFrame,
    tails_steady: pd.DataFrame,
    transition_cycles: int,
) -> None:
    def comparison(profile: str, metric: str) -> pd.Series:
        return comparisons[(comparisons["profile"] == profile) & (comparisons["metric"] == metric)].iloc[0]

    def pair(reference: str, candidate: str, metric: str) -> pd.Series:
        return all_comparisons[
            (all_comparisons["reference"] == reference)
            & (all_comparisons["candidate"] == candidate)
            & (all_comparisons["metric"] == metric)
        ].iloc[0]

    lines = [
        "# Tong hop ket qua long-run moi nhat",
        "",
        f"- Nguon du lieu: `{input_dir}`",
        f"- So seed: {len(quality)} ({int(quality.seed.min())}-{int(quality.seed.max())})",
        f"- Tong so cycle hop le: {int(quality.valid_cycles.sum())}/{int(quality.rows.sum())}",
        "- Don vi lap doc lap trong thong ke: seed, khong phai tung cycle.",
        f"- Trang thai on dinh: bo {transition_cycles} cycle dau cua moi profile, dung {300-transition_cycles} cycle/profile/seed.",
        "- Khoang tin cay: 95% Student-t tren trung binh cua cac seed.",
        "",
        "## Ket qua trang thai on dinh",
        "",
        "| Profile | Slotframe | Power norm. | Delay norm. | PDR | Reward |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for profile in PROFILE_ORDER:
        lines.append(
            "| "
            + PROFILE_LABELS[profile]
            + " | "
            + fmt_ci(steady_summary, profile, "sf_len", 2)
            + " | "
            + fmt_ci(steady_summary, profile, "power_normalized", 4)
            + " | "
            + fmt_ci(steady_summary, profile, "delay_normalized", 4)
            + " | "
            + fmt_ci(steady_summary, profile, "pdr", 4)
            + " | "
            + fmt_ci(steady_summary, profile, "reward", 4)
            + " |"
        )

    energy_power = comparison("energy", "power_normalized")
    delay_delay = comparison("delay", "delay_normalized")
    reliability_pdr = comparison("reliability", "pdr")
    reliability_vs_delay_pdr = pair("delay", "reliability", "pdr")
    energy_pdr = comparison("energy", "pdr")
    lines.extend(
        [
            "",
            "## Doi chieu muc tieu",
            "",
            f"- Energy: power chuan hoa thay doi {energy_power.percent_change_vs_balanced:+.2f}% so voi Balanced "
            f"(p exact={energy_power.exact_sign_flip_p:.4f}).",
            f"- Delay: delay chuan hoa thay doi {delay_delay.percent_change_vs_balanced:+.2f}% so voi Balanced "
            f"(p exact={delay_delay.exact_sign_flip_p:.4f}).",
            f"- Reliability: PDR thay doi {reliability_pdr.percent_change_vs_balanced:+.2f}% so voi Balanced "
            f"(p exact={reliability_pdr.exact_sign_flip_p:.4f}).",
            f"- Reliability so voi Delay: cung SF=10 nhung PDR thay doi "
            f"{reliability_vs_delay_pdr.percent_change_vs_reference:+.2f}% "
            f"(p exact={reliability_vs_delay_pdr.exact_sign_flip_p:.4f}); Reliability khong tao PDR cao hon Delay.",
            f"- Energy co PDR thay doi {energy_pdr.percent_change_vs_balanced:+.2f}% so voi Balanced "
            f"(p exact={energy_pdr.exact_sign_flip_p:.4f}), nhung chenh lech nay chua du manh va khong nen dien giai la SF lon lam tang PDR.",
            "- Dau am nghia la metric giam; voi power va delay day la cai thien, voi PDR thi dau duong moi la cai thien.",
            "",
            "## Hanh vi slotframe",
            "",
        ]
    )
    for profile in PROFILE_ORDER:
        subset = transitions[transitions["profile"] == profile]
        terminal_mean, _, terminal_ci, _ = mean_ci(subset["last_100_sf_mean"])
        if profile in ("delay", "reliability"):
            hit_mean, _, hit_ci, _ = mean_ci(subset["first_cycle_at_min_sf"])
            transition_note = f"dat SF toi thieu sau {hit_mean:.1f} +/- {hit_ci:.1f} cycle"
        elif profile == "energy":
            hit_mean, _, hit_ci, _ = mean_ci(subset["first_cycle_at_max_sf"])
            transition_note = f"dat SF toi da sau {hit_mean:.1f} +/- {hit_ci:.1f} cycle"
        else:
            transition_note = "hoi tu ve vung trung gian"
        lines.append(
            f"- {PROFILE_LABELS[profile]}: SF trung binh 100 cycle cuoi = {terminal_mean:.2f} +/- {terminal_ci:.2f}; {transition_note}."
        )

    lines.extend(
        [
            "",
            "## Dien giai",
            "",
            "1. Delay va Reliability deu dua slotframe ve bien duoi. Day la ket qua mong doi khi chi co mot bien dieu khien: slotframe nho vua rut ngan thoi gian cho, vua ho tro truyen lai som hon.",
            "2. Delay nhay cam voi slotframe hon PDR. PDR da o vung cao va bi nhieu manh, nen loi ich cua profile Reliability nho hon va co the khong tach ro khoi Delay.",
            "3. Energy dua slotframe ve bien tren, giam tan suat radio hoat dong nhung doi lai delay tang. Day la trade-off ro nhat cua thi nghiem.",
            "4. Trung binh toan bo 300 cycle bao gom chuyen tiep, dac biet Reliability bat dau tu SF cao cua Energy. Vi vay ket luan ve chinh sach nen dung bang steady-state; bang full-period chi dung mo ta toan dien bien long-run.",
            "5. Action bi override tai bien khong lam sai metric: action vuot bien duoc ap dung thanh hold. Tuy nhien raw action va applied action phai duoc giu rieng khi bao cao tinh minh bach cua policy.",
            "6. Thu tu profile luon co dinh Balanced -> Delay -> Energy -> Reliability trong ca 8 seed. Vi vay profile bi confound voi thoi gian chay; dac biet chenh lech PDR nho khong duoc dien giai nhu quan he nhan qua hoan toan.",
            "7. Reward cua cac profile dung bo trong so khac nhau, nen gia tri reward tuyet doi giua cac profile khong phai bang xep hang chat luong chung.",
            "",
            "## Duoi phan phoi",
            "",
            "| Profile | Delay p50 (ms) | Delay p95 (ms) | Delay p99 (ms) | >1 s | PDR <0.9 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in tails_steady.iterrows():
        lines.append(
            f"| {PROFILE_LABELS[str(row.profile)]} | {row.delay_ms_p50:.1f} | {row.delay_ms_p95:.1f} | "
            f"{row.delay_ms_p99:.1f} | {int(row.cycles_delay_over_1s)} | {int(row.cycles_pdr_below_0_9)} |"
        )

    lines.extend(
        [
            "",
            "## File minh hoa",
            "",
            "- `longrun_slotframe_timeline.png`: SF theo thoi gian va bon profile.",
            "- `longrun_mean_timeline.png`: SF, power, delay va PDR tren cung truc long-run.",
            "- `longrun_profile_summary.png`: so sanh steady-state kem CI 95%.",
            "- `longrun_power_delay_tradeoff.png`: trade-off power-delay, kem SF va PDR.",
            "- `longrun_pdr_by_seed.png`: PDR steady-state cua tung seed va trung binh.",
        ]
    )
    (output_dir / "analysis_report_vi.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    machine_summary = {
        "input_dir": str(input_dir),
        "seed_count": int(len(quality)),
        "seeds": [int(value) for value in quality.seed.tolist()],
        "total_rows": int(quality.rows.sum()),
        "valid_cycles": int(quality.valid_cycles.sum()),
        "invalid_cycles": int(quality.invalid_cycles.sum()),
        "wait_timeouts": int(quality.wait_timeouts.sum()),
        "transition_cycles_excluded": transition_cycles,
        "steady_cycles_per_profile_per_seed": 300 - transition_cycles,
        "all_runs_complete": bool(
            (quality.rows == 1200).all()
            and quality.cycles_contiguous.all()
            and quality.profile_counts_ok.all()
            and quality.profile_weights_ok.all()
            and (quality.invalid_cycles == 0).all()
        ),
    }
    (output_dir / "quality_summary.json").write_text(
        json.dumps(machine_summary, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--transition-cycles",
        type=int,
        default=50,
        help="Cycles excluded from the start of each 300-cycle profile segment",
    )
    parser.add_argument(
        "--timeline-window",
        type=int,
        default=15,
        help="Centered moving-average window for noisy timeline metrics",
    )
    args = parser.parse_args()
    input_dir = args.input_dir.resolve()
    output_dir = (args.output_dir or input_dir / "analysis").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    data, quality = load_runs(input_dir)
    valid = data[data["valid_cycle_bool"] & ~data["wait_timeout_bool"]].copy()
    steady = valid[valid["profile_cycle"] > args.transition_cycles].copy()
    if steady.empty:
        raise ValueError("Steady-state selection is empty; reduce --transition-cycles")

    quality.to_csv(output_dir / "data_quality_by_seed.csv", index=False)
    per_seed_full = seed_profile_means(valid)
    per_seed_steady = seed_profile_means(steady)
    per_seed_full.to_csv(output_dir / "seed_profile_means_full.csv", index=False)
    per_seed_steady.to_csv(output_dir / "seed_profile_means_steady.csv", index=False)

    summary_full = aggregate_profiles(per_seed_full)
    summary_steady = aggregate_profiles(per_seed_steady)
    summary_full.to_csv(output_dir / "profile_summary_full.csv", index=False)
    summary_steady.to_csv(output_dir / "profile_summary_steady.csv", index=False)

    comparisons = paired_comparisons(per_seed_steady)
    comparisons.to_csv(output_dir / "paired_comparisons_vs_balanced_steady.csv", index=False)
    all_comparisons = all_paired_comparisons(per_seed_steady)
    all_comparisons.to_csv(output_dir / "paired_profile_comparisons_steady.csv", index=False)
    transitions = transition_summary(valid, int(valid.sf_len.min()), int(valid.sf_len.max()))
    transitions.to_csv(output_dir / "slotframe_transitions_by_seed.csv", index=False)
    actions = action_summary(valid)
    actions.to_csv(output_dir / "action_summary.csv", index=False)
    tails_full = tail_summary(valid)
    tails_steady = tail_summary(steady)
    tails_full.to_csv(output_dir / "metric_tails_full.csv", index=False)
    tails_steady.to_csv(output_dir / "metric_tails_steady.csv", index=False)

    timeline = timeline_statistics(valid, args.timeline_window)
    timeline.to_csv(output_dir / "timeline_mean_ci.csv", index=False)
    save_profile_figure(summary_steady, output_dir)
    save_tradeoff_figure(summary_steady, output_dir)
    save_pdr_by_seed_figure(per_seed_steady, output_dir)
    save_timeline_figures(valid, timeline, output_dir, args.timeline_window)
    write_report(
        output_dir,
        input_dir,
        quality,
        summary_full,
        summary_steady,
        comparisons,
        all_comparisons,
        transitions,
        actions,
        tails_steady,
        args.transition_cycles,
    )
    print(f"Analysis complete: {output_dir}")


if __name__ == "__main__":
    main()
