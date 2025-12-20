#!/usr/bin/env python3
"""
Plot extended TISA results (z-RMSE vs scale) for each window across days.

Consumes: reports/tisa_extended_*.json (produced by scripts/tisa_extended.py)
Outputs: reports/plots/tisa_extended_<window>.png
"""

import json
import glob
from pathlib import Path

import matplotlib.pyplot as plt


def main():
    root = Path(__file__).resolve().parent.parent
    reports = root / "reports"
    outdir = reports / "plots"
    outdir.mkdir(parents=True, exist_ok=True)

    files = sorted(glob.glob(str(reports / "tisa_extended_*.json")))
    if not files:
        print("[warn] no tisa_extended_*.json found")
        return

    # Collect by window
    windows = {}
    for path in files:
        data = json.loads(Path(path).read_text())
        date = data["date"]
        for w, res in data["windows"].items():
            if "note" in res:
                continue
            windows.setdefault(w, {})[date] = res["scales"]

    for w, series_by_date in windows.items():
        plt.figure(figsize=(8, 5))
        for date, scales in series_by_date.items():
            xs = [s["scale"] for s in scales]
            ys = [s["z_rmse"] for s in scales]
            plt.plot(xs, ys, marker="o", label=date)
        plt.xlabel("Scale (time stretch, >1 = slower)")
        plt.ylabel("z-RMSE (lower is closer)")
        plt.title(f"TISA extended z-RMSE by scale (window {w} days)")
        plt.grid(True, alpha=0.3)
        plt.legend(title="Date")
        out = outdir / f"tisa_extended_{w.replace('-', '_')}.png"
        plt.tight_layout()
        plt.savefig(out, dpi=150)
        plt.close()
        print(f"Wrote {out}")


if __name__ == "__main__":
    main()
