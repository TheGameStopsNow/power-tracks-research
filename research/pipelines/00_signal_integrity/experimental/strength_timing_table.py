#!/usr/bin/env python3
"""
Summarize signal strength vs timing across days.

Consumes:
  - reports/tisa_null_controls_YYYY-MM-DD.json
  - reports/segment_ohlc_summary.json  (from experimental/segment_ohlc_summary.py)

For each date it records:
  - The best (lowest) null-control z-RMSE window and its p-value.
  - Per-window null-control stats for 60-70 and 70-80 days.
  - The best segment/OHLC match for 60-70 and 70-80 days (z-RMSE, p-value).
  - Simple boolean flags for "strong" evidence:
      * strong_null: any window in {60-70, 70-80} with p <= 0.05.
      * strong_segment: 60-70 or 70-80 segment match with p <= 0.05.

Outputs:
  - reports/strength_timing_table.json
"""

import json
from pathlib import Path
from typing import Dict, Any


def load_null_controls(reports: Path) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for path in sorted(reports.glob("tisa_null_controls_*.json")):
        data = json.loads(path.read_text())
        date = data.get("date")
        if not date:
            continue
        wins: Dict[str, Any] = {}
        for w, wres in data.get("windows", {}).items():
            if "note" in wres:
                continue
            wins[w] = {
                "real_min_z_rmse": wres.get("real_min_z_rmse"),
                "pvalue": wres.get("pvalue_real_vs_shuffled_min"),
                "shuffled_min_z_rmse_mean": wres.get("shuffled_min_z_rmse_mean"),
            }
        if wins:
            out[date] = wins
    return out


def load_segment_summary(reports: Path) -> Dict[str, Dict[str, Any]]:
    path = reports / "segment_ohlc_summary.json"
    if not path.exists():
        raise SystemExit(f"missing {path}, run experimental/segment_ohlc_summary.py first")
    data = json.loads(path.read_text())
    return data.get("per_day", {})


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    reports = root / "reports"

    null_by_day = load_null_controls(reports)
    seg_by_day = load_segment_summary(reports)

    all_dates = sorted(set(null_by_day.keys()) | set(seg_by_day.keys()))
    result: Dict[str, Any] = {"per_day": {}}

    for date in all_dates:
        day: Dict[str, Any] = {}

        # Null-controls summary
        null_windows = null_by_day.get(date, {})
        if null_windows:
            best_w = None
            best_vals = None
            for w, vals in null_windows.items():
                z = vals.get("real_min_z_rmse")
                if z is None:
                    continue
                if best_vals is None or z < best_vals["real_min_z_rmse"]:
                    best_w = w
                    best_vals = vals
            day["null_best"] = {"window": best_w, **(best_vals or {})}
            day["null_windows"] = {
                w: vals
                for w, vals in null_windows.items()
                if w in {"60-70", "70-80", "80-90", "150-180"}
            }
        else:
            day["null_best"] = None
            day["null_windows"] = {}

        # Segment/OHLC summary for 60-70 and 70-80
        seg_windows = seg_by_day.get(date, {})
        seg_out = {}
        for w in ("60-70", "70-80"):
            if w in seg_windows:
                seg_out[w] = seg_windows[w]
        day["segments"] = seg_out

        # Simple strength flags
        strong_null = False
        for w in ("60-70", "70-80"):
            vals = null_windows.get(w)
            if vals and vals.get("pvalue") is not None and vals["pvalue"] <= 0.05:
                strong_null = True
                break

        strong_segment = False
        for w in ("60-70", "70-80"):
            wres = seg_windows.get(w)
            if not wres or "note" in wres:
                continue
            p = wres.get("pvalue")
            if p is not None and p <= 0.05:
                strong_segment = True
                break

        day["strong_null"] = strong_null
        day["strong_segment"] = strong_segment

        result["per_day"][date] = day

    out_path = reports / "strength_timing_table.json"
    out_path.write_text(json.dumps(result, indent=2))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

