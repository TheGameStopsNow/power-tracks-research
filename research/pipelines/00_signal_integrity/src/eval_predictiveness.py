#!/usr/bin/env python3
"""
Evaluate predictiveness of decoded signals vs future returns (baseline vs signals).

Approach:
  - Load per-day feature CSVs (from build_features.py).
  - For each horizon, compute:
      * Hit rate of signal delta_close sign vs future return sign
      * Correlation between delta_close and future return
      * Baseline hit rate (majority class) and naive momentum (sign of current close diff)
      * Control: shuffled labels hit rate
"""

import argparse
import json
import random
from pathlib import Path
import pandas as pd
import numpy as np


def eval_day(df: pd.DataFrame, horizons: list[int]) -> dict:
    results = {}
    for h in horizons:
        fwd = df[f"fwd_ret_{h}m"]
        label = (fwd > 0).astype(int)
        signal = np.sign(df["delta_close"])
        signal_label = (signal > 0).astype(int)
        hit = (signal_label == label).mean()
        corr = np.corrcoef(df["delta_close"], fwd)[0, 1] if len(df) > 1 else 0.0
        majority = max(label.mean(), 1 - label.mean())
        # naive momentum: sign of current close vs previous close
        mom = np.sign(df["close"].diff()).fillna(0)
        mom_label = (mom > 0).astype(int)
        mom_hit = (mom_label == label).mean()
        shuffled = label.sample(frac=1.0, random_state=42).reset_index(drop=True)
        shuffled_hit = (signal_label.reset_index(drop=True) == shuffled).mean()
        results[h] = {
            "rows": int(len(df)),
            "hit_rate": float(hit),
            "corr": float(corr) if not np.isnan(corr) else 0.0,
            "baseline_majority": float(majority),
            "baseline_momentum": float(mom_hit),
            "control_shuffled": float(shuffled_hit),
            "mean_fwd_ret": float(fwd.mean()),
            "mean_delta_close": float(df["delta_close"].mean()),
        }
    return results


def main():
    parser = argparse.ArgumentParser(description="Evaluate predictiveness from feature CSVs.")
    parser.add_argument("--features", nargs="+", required=True, type=Path, help="Feature CSVs from build_features")
    parser.add_argument("--horizons", nargs="+", type=int, default=[1, 5, 15, 60])
    parser.add_argument("--output", required=True, type=Path, help="JSON report")
    args = parser.parse_args()

    report = {"per_day": {}, "aggregate": {}}
    agg_rows = {h: [] for h in args.horizons}

    for path in args.features:
        df = pd.read_csv(path)
        day = path.stem
        day_result = eval_day(df, args.horizons)
        report["per_day"][day] = day_result
        for h in args.horizons:
            agg_rows[h].append(day_result[h])

    for h in args.horizons:
        if not agg_rows[h]:
            continue
        hr = [x["hit_rate"] for x in agg_rows[h]]
        corr = [x["corr"] for x in agg_rows[h]]
        maj = [x["baseline_majority"] for x in agg_rows[h]]
        mom = [x["baseline_momentum"] for x in agg_rows[h]]
        shuf = [x["control_shuffled"] for x in agg_rows[h]]
        report["aggregate"][h] = {
            "hit_rate_mean": float(np.mean(hr)),
            "hit_rate_std": float(np.std(hr)),
            "corr_mean": float(np.mean(corr)),
            "baseline_majority_mean": float(np.mean(maj)),
            "baseline_momentum_mean": float(np.mean(mom)),
            "control_shuffled_mean": float(np.mean(shuf)),
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(f"Wrote predictiveness report: {args.output}")


if __name__ == "__main__":
    main()
