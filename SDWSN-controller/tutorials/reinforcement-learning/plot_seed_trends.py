#!/usr/bin/env python3
import os
import json
import glob
import argparse
import numpy as np
import matplotlib.pyplot as plt


BASE_OUT = os.path.join(
    os.path.dirname(__file__), "output"
)  # default relative to this folder when run from project root


def _safe_float(value, default=0.0):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if np.isfinite(value) else default


def _coverage_reason(seed_dir, min_valid_rows, min_slotframes, required_profile):
    coverage_path = os.path.join(seed_dir, "coverage_summary.json")
    if not os.path.isfile(coverage_path):
        return "missing coverage_summary.json"
    with open(coverage_path) as f:
        coverage = json.load(f)

    valid_rows = int(coverage.get("valid_rows", 0) or 0)
    if valid_rows < min_valid_rows:
        return f"valid_rows={valid_rows} < {min_valid_rows}"

    slotframes = coverage.get("slotframe_counts", {}) or {}
    if len(slotframes) < min_slotframes:
        return f"slotframes={len(slotframes)} < {min_slotframes}"

    required_profile = (required_profile or "").strip()
    if required_profile:
        profile_counts = coverage.get("profile_counts", {}) or {}
        nonzero_profiles = {
            str(k): int(v)
            for k, v in profile_counts.items()
            if int(v or 0) > 0
        }
        if nonzero_profiles != {required_profile: valid_rows}:
            return f"profile_counts={nonzero_profiles}, expected only {required_profile}"

    return None


def load_seed_trends(base_dir, min_valid_rows, min_slotframes, required_profile):
    paths = sorted(glob.glob(os.path.join(base_dir, "cycle_r500_s*", "trend_vectors.json")))
    seeds = []
    data = []
    skipped = []
    for p in paths:
        seed_dir = os.path.dirname(p)
        seed_name = os.path.basename(seed_dir)
        reason = _coverage_reason(seed_dir, min_valid_rows, min_slotframes, required_profile)
        if reason:
            skipped.append({"seed": seed_name, "reason": reason})
            continue
        with open(p) as f:
            trend = json.load(f)
        missing = [m for m in ("power", "delay", "reliability") if m not in trend]
        if missing:
            skipped.append({"seed": seed_name, "reason": f"missing metrics: {missing}"})
            continue
        seeds.append(seed_name)
        data.append(trend)
    return seeds, data, skipped


def eval_poly(coeffs, x):
    coeffs = np.array(coeffs, dtype=float)
    return np.polyval(coeffs, x)


def _monotonic_rate(coeffs, x_min, x_max, direction):
    xd = np.linspace(x_min, x_max, 500)
    dy = np.diff(np.polyval(coeffs, xd))
    tol = 1e-12
    if direction == "increasing":
        return float((dy >= -tol).mean())
    if direction == "decreasing":
        return float((dy <= tol).mean())
    return float(max((dy >= -tol).mean(), (dy <= tol).mean()))


def wls_fit(
    x,
    Ys,
    seed_weights,
    degrees,
    direction=None,
    mono_threshold=0.95,
    min_r2_gain=0.005,
):
    Xall = np.tile(x, Ys.shape[0])
    Yall = Ys.ravel()
    Wall = np.repeat(seed_weights, x.size)
    if not np.isfinite(Wall).all() or Wall.sum() <= 0:
        Wall = np.ones_like(Yall, dtype=float)

    best = None
    best_preferred = None
    candidates = []
    for deg in sorted(set(int(d) for d in degrees)):
        coeffs = np.polyfit(Xall, Yall, deg, w=Wall)
        yhat = np.polyval(coeffs, Xall)
        wmean = np.average(Yall, weights=Wall)
        ss_res = np.sum(Wall * (Yall - yhat) ** 2)
        ss_tot = np.sum(Wall * (Yall - wmean) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        mono = _monotonic_rate(coeffs, float(x.min()), float(x.max()), direction)
        cand = (deg, coeffs, r2, mono)
        candidates.append(cand)
        if best is None or r2 > best[2]:
            best = cand
        if mono >= mono_threshold:
            if best_preferred is None or r2 > best_preferred[2] + min_r2_gain:
                best_preferred = cand
    return best_preferred or best, candidates  # (deg, coeffs, r2, mono), candidates


def plot_metric(ax, x_grid, seed_curves, title, wls_curve=None, model_curve=None):
    for y in seed_curves:
        ax.plot(x_grid, y, color="#999999", alpha=0.35, linewidth=1)
    if wls_curve is not None:
        ax.plot(x_grid, wls_curve, color="#1f77b4", linewidth=2, label="WLS pooled fit")
    if model_curve is not None:
        ax.plot(x_grid, model_curve, color="#d62728", linestyle="--", linewidth=2, label="Config model")
    ax.set_title(title)
    ax.set_xlabel("Slotframe size |C|")
    ax.set_ylabel("Normalized value")
    ax.grid(True, alpha=0.2)
    ax.legend(loc="best")


def main():
    parser = argparse.ArgumentParser(
        description="Pool per-seed trend vectors and optionally update the training config."
    )
    parser.add_argument(
        "--base-dir",
        default=os.path.join(os.path.dirname(__file__), "output"),
        help="Directory containing cycle_r500_s*/trend_vectors.json",
    )
    parser.add_argument(
        "--config",
        default=os.path.join(
            os.path.dirname(__file__), "training", "numerical_controller_rl.json"
        ),
        help="Training config to read/update",
    )
    parser.add_argument(
        "--write-config",
        action="store_true",
        help="Write pooled coefficients back to the training config",
    )
    parser.add_argument(
        "--min-valid-rows",
        type=int,
        default=1000,
        help="Skip trend seeds with fewer valid rows than this",
    )
    parser.add_argument(
        "--min-slotframes",
        type=int,
        default=30,
        help="Skip trend seeds covering fewer distinct slotframe sizes than this",
    )
    parser.add_argument(
        "--required-profile",
        default="balanced",
        help="Require trend seeds to contain only this profile; use '' to disable",
    )
    parser.add_argument(
        "--min-seeds",
        type=int,
        default=1,
        help="Require at least this many accepted seeds before writing summaries/config",
    )
    args = parser.parse_args()

    # Resolve output base
    base_dir = args.base_dir
    if not os.path.isdir(base_dir):
        # fallback when running from project root where output is at tutorials/.../output
        base_dir = os.path.join(os.getcwd(), "SDWSN-controller", "tutorials", "reinforcement-learning", "output")
    seeds, seed_data, skipped = load_seed_trends(
        base_dir,
        min_valid_rows=max(0, int(args.min_valid_rows)),
        min_slotframes=max(0, int(args.min_slotframes)),
        required_profile=args.required_profile,
    )
    if len(seeds) < int(args.min_seeds):
        details = "\n".join(f" - {s['seed']}: {s['reason']}" for s in skipped)
        raise SystemExit(
            f"Only {len(seeds)} accepted seed(s) under {base_dir}; "
            f"need at least {args.min_seeds}.\nSkipped:\n{details}"
        )

    # Common x grid inferred from first seed
    x_min = float(seed_data[0]["power"]["x_min"])  # all consistent
    x_max = float(seed_data[0]["power"]["x_max"])  # all consistent
    x = np.linspace(x_min, x_max, int(seed_data[0]["power"]["points"]))
    x_dense = np.linspace(x_min, x_max, 400)

    # Load current model config for overlay
    cfg_path = args.config
    with open(cfg_path) as f:
        cfg = json.load(f)
    model_coeffs = {
        "power": cfg["performance_metrics"]["energy"]["weights"],
        "delay": cfg["performance_metrics"]["delay"]["weights"],
        "reliability": cfg["performance_metrics"]["pdr"]["weights"],
    }

    # Prepare seed curves and weights
    metrics = ["power", "delay", "reliability"]
    seed_curves = {m: [] for m in metrics}
    weights = {m: [] for m in metrics}
    for d in seed_data:
        for m in metrics:
            y = eval_poly(d[m]["coefficients"], x_dense)
            seed_curves[m].append(y)
            w = max(0.0, _safe_float(d[m].get("weighted_r2"))) * max(
                0.0,
                _safe_float(d[m].get("monotonic_rate")),
            )
            weights[m].append(w)
    for m in metrics:
        seed_curves[m] = np.vstack(seed_curves[m])
        weights[m] = np.array(weights[m], dtype=float)

    # Compute pooled WLS curves
    wls_specs = {
        "power": [1, 2, 3, 4],
        "delay": [1, 2, 3, 4],
        "reliability": [1, 2, 3],
    }
    directions = {
        "power": "decreasing",
        "delay": "increasing",
        "reliability": "decreasing",
    }
    wls_fits = {}
    wls_candidates = {}
    for m in metrics:
        (deg, coeffs, r2, mono), candidates = wls_fit(
            x_dense,
            seed_curves[m],
            weights[m],
            wls_specs[m],
            direction=directions[m],
        )
        wls_fits[m] = (deg, coeffs, r2, mono)
        wls_candidates[m] = candidates

    # Make summary plots
    summary_dir = os.path.join(base_dir, "summary")
    os.makedirs(summary_dir, exist_ok=True)

    # Power
    fig, ax = plt.subplots(figsize=(7, 4.2))
    plot_metric(
        ax,
        x_dense,
        seed_curves["power"],
        title="Power vs. slotframe size",
        wls_curve=eval_poly(wls_fits["power"][1], x_dense),
        model_curve=eval_poly(model_coeffs["power"], x_dense),
    )
    fig.tight_layout()
    fig.savefig(os.path.join(summary_dir, "power_trends.png"), dpi=150)
    plt.close(fig)

    # Delay
    fig, ax = plt.subplots(figsize=(7, 4.2))
    plot_metric(
        ax,
        x_dense,
        seed_curves["delay"],
        title="Delay vs. slotframe size",
        wls_curve=eval_poly(wls_fits["delay"][1], x_dense),
        model_curve=eval_poly(model_coeffs["delay"], x_dense),
    )
    fig.tight_layout()
    fig.savefig(os.path.join(summary_dir, "delay_trends.png"), dpi=150)
    plt.close(fig)

    # Reliability
    fig, ax = plt.subplots(figsize=(7, 4.2))
    plot_metric(
        ax,
        x_dense,
        seed_curves["reliability"],
        title="Reliability (PDR) vs. slotframe size",
        wls_curve=eval_poly(wls_fits["reliability"][1], x_dense),
        model_curve=eval_poly(model_coeffs["reliability"], x_dense),
    )
    fig.tight_layout()
    fig.savefig(os.path.join(summary_dir, "reliability_trends.png"), dpi=150)
    plt.close(fig)

    # Write a small JSON summary of fits used
    summary = {
        m: {
            "wls": {
                "degree": int(wls_fits[m][0]),
                "coefficients": [float(c) for c in wls_fits[m][1]],
                "pooled_weighted_r2": float(wls_fits[m][2]),
                "monotonic_rate": float(wls_fits[m][3]),
                "candidates": [
                    {
                        "degree": int(deg),
                        "pooled_weighted_r2": float(r2),
                        "monotonic_rate": float(mono),
                    }
                    for deg, _, r2, mono in wls_candidates[m]
                ],
            },
            "model": {
                "degree": len(model_coeffs[m]) - 1,
                "coefficients": [float(c) for c in model_coeffs[m]],
            },
        }
        for m in metrics
    }
    summary["included_seeds"] = seeds
    summary["skipped_seeds"] = skipped
    with open(os.path.join(summary_dir, "summary_fits.json"), "w") as f:
        json.dump(summary, f, indent=2)

    if args.write_config:
        cfg["performance_metrics"]["energy"]["weights"] = summary["power"]["wls"]["coefficients"]
        cfg["performance_metrics"]["delay"]["weights"] = summary["delay"]["wls"]["coefficients"]
        cfg["performance_metrics"]["pdr"]["weights"] = summary["reliability"]["wls"]["coefficients"]
        with open(cfg_path, "w") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
        print("Updated training config:", cfg_path)

    print("Accepted seeds:", ", ".join(seeds))
    if skipped:
        print("Skipped seeds:")
        for item in skipped:
            print(f" - {item['seed']}: {item['reason']}")
    print("Saved plots to:")
    print(" -", os.path.join(summary_dir, "power_trends.png"))
    print(" -", os.path.join(summary_dir, "delay_trends.png"))
    print(" -", os.path.join(summary_dir, "reliability_trends.png"))


if __name__ == "__main__":
    main()
