#!/usr/bin/env python3
"""
Generate quick-look charts from existing reports:
- TISA distance vs horizon per day.
- Predictiveness hit rates vs horizon.

Outputs PNGs under reports/plots/.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def plot_tisa(tisa_summary: Path, outdir: Path) -> None:
    data = json.loads(tisa_summary.read_text())
    horizons = [int(h) for h in data["horizons"]]
    # Plot best-distance
    plt.figure(figsize=(8, 5))
    for date in data["dates"]:
        distances = [data["data"][date][str(h)]["best_distance"] for h in horizons]
        plt.plot(horizons, distances, marker="o", label=date)
    plt.xlabel("Horizon (days)")
    plt.ylabel("TISA distance (lower is closer)")
    plt.title("TISA best-distance by horizon")
    plt.grid(True, alpha=0.3)
    plt.legend(title="Date")
    out = outdir / "tisa_distance.png"
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Wrote {out}")

    # Plot z-score RMSE (adds horizon sensitivity)
    plt.figure(figsize=(8, 5))
    for date in data["dates"]:
        rmses = [data["data"][date][str(h)].get("rmse_zscore") for h in horizons]
        plt.plot(horizons, rmses, marker="o", label=date)
    plt.xlabel("Horizon (days)")
    plt.ylabel("RMSE (z-scored)")
    plt.title("Signal vs future (z-RMSE) by horizon")
    plt.grid(True, alpha=0.3)
    plt.legend(title="Date")
    out = outdir / "tisa_rmse.png"
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Wrote {out}")


def plot_predictiveness(pred_path: Path, outdir: Path) -> None:
    data = json.loads(pred_path.read_text())
    horizons = [int(h) for h in data["aggregate"].keys()]
    horizons = sorted(horizons)
    agg = data["aggregate"]
    series = {
        "hit_rate_mean": "signal hit rate",
        "baseline_majority_mean": "baseline: majority",
        "baseline_momentum_mean": "baseline: momentum",
        "control_shuffled_mean": "control: shuffled",
    }
    plt.figure(figsize=(8, 5))
    for key, label in series.items():
        vals = [agg[str(h)].get(key, 0.0) for h in horizons]
        plt.plot(horizons, vals, marker="o", label=label)
    plt.xlabel("Horizon (minutes)")
    plt.ylabel("Hit rate")
    plt.title("Predictiveness vs horizon")
    plt.ylim(0, 1)
    plt.grid(True, alpha=0.3)
    plt.legend()
    out = outdir / "predictiveness_hit_rate.png"
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Wrote {out}")


def main():
    root = Path(__file__).resolve().parent.parent
    reports = root / "reports"
    outdir = reports / "plots"
    ensure_dir(outdir)

    tisa_summary = reports / "tisa_summary.json"
    pred = reports / "predictiveness.json"

    if tisa_summary.exists():
        plot_tisa(tisa_summary, outdir)
    else:
        print(f"[skip] missing {tisa_summary}")

    if pred.exists():
        plot_predictiveness(pred, outdir)
    else:
        print(f"[skip] missing {pred}")


if __name__ == "__main__":
    main()
