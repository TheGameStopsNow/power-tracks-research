#!/usr/bin/env python3
"""
Score tracks (frames) and evaluate filtered vs full performance using feature CSVs.

Heuristic score (per frame aggregated to minute alignment):
  score = w1*crc_valid + w2*varint_density + w3*abs(delta_close)

This is a lightweight selector to show lift vs full set.
"""

import argparse
import json
from pathlib import Path
import pandas as pd
import numpy as np


def load_features(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    return df


def add_score(df: pd.DataFrame) -> pd.DataFrame:
    # Composite score: |delta_close| + 0.01*frame_count + payload_mean/1000
    df = df.copy()
    base = df["delta_close"].abs()
    frame_boost = df["frame_count"] if "frame_count" in df.columns else 0
    payload_boost = df["payload_mean"] / 1000.0 if "payload_mean" in df.columns else 0
    df["score"] = base + 0.01 * frame_boost + payload_boost
    return df


def evaluate(df: pd.DataFrame, horizons: list[int], top_frac: float) -> dict:
    results = {}
    filtered = df.sort_values("score", ascending=False)
    cutoff = max(1, int(len(filtered) * top_frac))
    filt = filtered.head(cutoff)

    strata = ["all"]
    if "track_type" in df.columns:
        strata += sorted(df["track_type"].dropna().unique().tolist())

    for h in horizons:
        results[h] = {}
        for stratum in strata:
            if stratum == "all":
                df_slice = df
                filt_slice = filt
            else:
                df_slice = df[df["track_type"] == stratum]
                filt_slice = filt[filt["track_type"] == stratum]
            if df_slice.empty:
                results[h][stratum] = {"rows_full": 0, "rows_filtered": 0, "hit_full": 0.0, "hit_filtered": 0.0, "lift": 0.0}
                continue
            label = (df_slice[f"fwd_ret_{h}m"] > 0).astype(int)
            signal = (np.sign(df_slice["delta_close"]) > 0).astype(int)
            hit_full = (signal == label).mean()

            if filt_slice.empty:
                hit_filt = 0.0
            else:
                label_f = (filt_slice[f"fwd_ret_{h}m"] > 0).astype(int)
                signal_f = (np.sign(filt_slice["delta_close"]) > 0).astype(int)
                hit_filt = (signal_f == label_f).mean()

            results[h][stratum] = {
                "rows_full": int(len(df_slice)),
                "rows_filtered": int(len(filt_slice)),
                "hit_full": float(hit_full),
                "hit_filtered": float(hit_filt),
                "lift": float(hit_filt - hit_full),
            }
    return results


def main():
    parser = argparse.ArgumentParser(description="Score tracks and evaluate filtered performance.")
    parser.add_argument("--features", nargs="+", required=True, type=Path)
    parser.add_argument("--horizons", nargs="+", type=int, default=[1, 5, 15, 60])
    parser.add_argument("--top-frac", type=float, default=0.25, help="Top fraction to keep (0-1)")
    parser.add_argument("--output", required=True, type=Path, help="JSON report")
    args = parser.parse_args()

    report = {"per_day": {}, "aggregate": {}}
    agg = {h: [] for h in args.horizons}

    for path in args.features:
        df = load_features(path)
        df = add_score(df)
        res = evaluate(df, args.horizons, args.top_frac)
        report["per_day"][path.stem] = res
        for h in args.horizons:
            agg[h].append(res[h]["all"])

    for h in args.horizons:
        if not agg[h]:
            continue
        lift = [x["lift"] for x in agg[h]]
        hit_full = [x["hit_full"] for x in agg[h]]
        hit_f = [x["hit_filtered"] for x in agg[h]]
        report["aggregate"][h] = {
            "lift_mean": float(np.mean(lift)),
            "hit_full_mean": float(np.mean(hit_full)),
            "hit_filtered_mean": float(np.mean(hit_f)),
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(f"Wrote selector report: {args.output}")


if __name__ == "__main__":
    main()
