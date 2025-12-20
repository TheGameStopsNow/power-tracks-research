#!/usr/bin/env python3
"""
Summarize segment_ohlc_s8_* results across days.

Reads reports/segment_ohlc_s8_YYYY-MM-DD.json and produces a compact JSON summary:
  - For each window (60-70, 70-80) and component (close/high/low/range/body),
    records which segment index achieved the best (lowest) z-RMSE per day and its p-value.
  - Counts how often each segment/component pair is best with p <= 0.05.

Outputs: reports/segment_ohlc_summary.json
"""

import json
import glob
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    reports = sorted(glob.glob(str(root / "reports" / "segment_ohlc_s8_*.json")))
    if not reports:
        print("[warn] no segment_ohlc_s8_*.json found")
        return

    summary = {"per_day": {}, "counts": {}}

    for path in reports:
        data = json.loads(Path(path).read_text())
        date = data["date"]
        day_res = {}
        for window, wres in data["windows"].items():
            if "note" in wres:
                day_res[window] = {"note": wres["note"]}
                continue
            best = None
            best_key = None
            best_comp = None
            best_p = None
            for seg_key, comps in wres.items():
                for comp, vals in comps.items():
                    z = vals["real_z_rmse"]
                    if best is None or z < best:
                        best = z
                        best_key = seg_key
                        best_comp = comp
                        best_p = vals["pvalue_real_vs_shuffled"]
            day_res[window] = {
                "segment": best_key,
                "component": best_comp,
                "z_rmse": best,
                "pvalue": best_p,
            }
            # counts for p <= 0.05
            if best_p is not None and best_p <= 0.05:
                cnt_key = f"{window}:{best_comp}:{best_key}"
                summary["counts"].setdefault(cnt_key, 0)
                summary["counts"][cnt_key] += 1

        summary["per_day"][date] = day_res

    out = root / "reports" / "segment_ohlc_summary.json"
    out.write_text(json.dumps(summary, indent=2))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

