#!/usr/bin/env python3
"""
Tier-1 window selector: scan minute bars and emit candidate windows for tick fetch/decoding.

Heuristics (configurable):
- Return z-score vs rolling mean/std
- Volume z-score vs rolling mean/std
- Gap detection (abs return vs previous close)

Outputs a JSON list of window specs: symbol, date, start, end, scores, triggers.
"""

import argparse
import json
from pathlib import Path
from typing import List, Dict

import pandas as pd


def compute_zscores(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window, min_periods=window // 2).mean()
    std = series.rolling(window, min_periods=window // 2).std()
    return (series - mean) / std


def load_bars(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if not {"timestamp", "open", "high", "low", "close", "volume"}.issubset(df.columns):
        raise ValueError(f"{path} must have timestamp, open, high, low, close, volume columns")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp")
    return df


def select_windows(
    df: pd.DataFrame,
    symbol: str,
    ret_thresh: float,
    vol_thresh: float,
    gap_thresh: float,
    window_minutes: int,
    halo_minutes: int,
    top_n: int,
) -> List[Dict]:
    df = df.copy()
    df["return"] = df["close"].pct_change()
    df["gap"] = df["close"].pct_change().abs()
    df["range"] = (df["high"] - df["low"]).abs()
    df["vol_z"] = compute_zscores(df["volume"], window_minutes)
    df["ret_z"] = compute_zscores(df["return"], window_minutes)

    triggers = (
        (df["ret_z"].abs() >= ret_thresh)
        | (df["vol_z"].abs() >= vol_thresh)
        | (df["gap"].abs() >= gap_thresh)
    )
    candidates = df[triggers].copy()
    if candidates.empty:
        return []

    candidates["score"] = candidates[["ret_z", "vol_z"]].abs().max(axis=1).fillna(0)
    candidates = candidates.sort_values("score", ascending=False)
    if top_n > 0:
        candidates = candidates.head(top_n)

    windows: List[Dict] = []
    for _, row in candidates.iterrows():
        ts = row["timestamp"]
        start = ts - pd.Timedelta(minutes=halo_minutes)
        end = ts + pd.Timedelta(minutes=halo_minutes)
        windows.append(
            {
                "symbol": symbol,
                "date": ts.date().isoformat(),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "score": float(row["score"]),
                "ret_z": float(row["ret_z"]) if pd.notna(row["ret_z"]) else 0.0,
                "vol_z": float(row["vol_z"]) if pd.notna(row["vol_z"]) else 0.0,
                "gap": float(row["gap"]) if pd.notna(row["gap"]) else 0.0,
                "reason": "ret_z/vol_z/gap",
            }
        )
    return windows


def main():
    parser = argparse.ArgumentParser(description="Select candidate tick windows from minute bars.")
    parser.add_argument("--input", required=True, nargs="+", type=Path, help="Input minute-bar CSV(s)")
    parser.add_argument("--symbol", required=True, help="Symbol")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON for windows")
    parser.add_argument("--ret-thresh", type=float, default=3.0, help="Return z-score threshold")
    parser.add_argument("--vol-thresh", type=float, default=3.0, help="Volume z-score threshold")
    parser.add_argument("--gap-thresh", type=float, default=0.02, help="Absolute gap threshold (fraction)")
    parser.add_argument("--window-minutes", type=int, default=60, help="Rolling window for z-scores (minutes)")
    parser.add_argument("--halo-minutes", type=int, default=5, help="Pad before/after trigger (minutes)")
    parser.add_argument("--top-n", type=int, default=50, help="Keep top-N windows by score (0 = keep all)")
    args = parser.parse_args()

    all_windows: List[Dict] = []
    for path in args.input:
        df = load_bars(path)
        windows = select_windows(
            df,
            symbol=args.symbol,
            ret_thresh=args.ret_thresh,
            vol_thresh=args.vol_thresh,
            gap_thresh=args.gap_thresh,
            window_minutes=args.window_minutes,
            halo_minutes=args.halo_minutes,
            top_n=args.top_n,
        )
        all_windows.extend(windows)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(all_windows, f, indent=2)
    print(f"Wrote {len(all_windows)} windows to {args.output}")


if __name__ == "__main__":
    main()
