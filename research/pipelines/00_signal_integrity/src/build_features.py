#!/usr/bin/env python3
"""
Build features and labels from decoded signals and external minute bars.

Inputs:
  --signals  decoded price_paths.csv (timestamp_us relative to midnight)
  --bars     external minute bars CSV (timestamp, open, high, low, close, volume)
  --date     date string YYYY-MM-DD (anchors timestamp_us)
  --horizons list of forward-return horizons in minutes

Outputs:
  JSON with summary stats and a CSV with per-minute features/labels.
"""

import argparse
import json
from pathlib import Path
import pandas as pd
import numpy as np


def load_signals(path: Path, date: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "price" not in df.columns or "timestamp_us" not in df.columns:
        raise ValueError("signals must have price and timestamp_us")
    day_start = pd.Timestamp(f"{date}T00:00:00Z")
    # prefer timestamp_ms if present (avoids overflow ambiguity)
    if "timestamp_ms" in df.columns:
        df["timestamp"] = day_start + pd.to_timedelta(df["timestamp_ms"], unit="ms")
    else:
        df["timestamp"] = day_start + pd.to_timedelta(df["timestamp_us"], unit="us")
    return df


def load_frames(frames_path: Path, date: str) -> pd.DataFrame:
    df = pd.read_csv(frames_path)
    if "start_time_us" not in df.columns:
        raise ValueError("frames must include start_time_us")
    day_start = pd.Timestamp(f"{date}T00:00:00Z")
    df["timestamp"] = day_start + pd.to_timedelta(df["start_time_us"], unit="us")
    return df


def load_bars(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"timestamp", "open", "high", "low", "close"}
    if not required.issubset(df.columns):
        raise ValueError(f"bars must include {required}")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def resample_signals(signals: pd.DataFrame) -> pd.DataFrame:
    ohlc = signals.set_index("timestamp")["price"].resample("1min").ohlc()
    ohlc = ohlc.dropna()
    return ohlc.rename(columns={"open": "sig_open", "high": "sig_high", "low": "sig_low", "close": "sig_close"})


def frame_aggregates(frames: pd.DataFrame) -> pd.DataFrame:
    grouped = frames.resample("1min", on="timestamp").agg(
        frame_count=("frame_index", "count"),
        payload_mean=("payload_bytes", "mean"),
        sampled_mean=("sampled_points", "mean"),
    )
    return grouped.fillna(0)


def build_labels(bars: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    labels = bars.set_index("timestamp")[["close"]].copy()
    for h in horizons:
        future = labels["close"].shift(-h)
        labels[f"fwd_ret_{h}m"] = (future - labels["close"]) / labels["close"]
    return labels


def assemble_features(sig_ohlc: pd.DataFrame, bars: pd.DataFrame, frames_agg: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    merged = bars.set_index("timestamp").join(sig_ohlc, how="inner")
    merged = merged.join(frames_agg, how="left").fillna({"frame_count": 0, "payload_mean": 0, "sampled_mean": 0})
    merged["delta_close"] = merged["sig_close"] - merged["close"]
    merged["delta_high"] = merged["sig_high"] - merged["high"]
    merged["delta_low"] = merged["sig_low"] - merged["low"]
    merged["delta_range"] = (merged["sig_high"] - merged["sig_low"]) - (merged["high"] - merged["low"])
    # track-type proxy
    def bucket(row):
        if row["payload_mean"] >= 800:
            return "long"
        if row["payload_mean"] >= 400:
            return "medium"
        return "short"
    merged["track_type"] = merged.apply(bucket, axis=1)
    for h in horizons:
        merged[f"label_up_{h}m"] = (merged[f"fwd_ret_{h}m"] > 0).astype(int)
    return merged.dropna()


def summarize(df: pd.DataFrame, horizons: list[int]) -> dict:
    summary = {"rows": int(len(df))}
    for h in horizons:
        summary[f"mean_fwd_ret_{h}m"] = float(df[f"fwd_ret_{h}m"].mean())
        summary[f"mean_delta_close"] = float(df["delta_close"].mean())
    return summary


def main():
    parser = argparse.ArgumentParser(description="Build features/labels from decoded signals and bars.")
    parser.add_argument("--signals", required=True, type=Path)
    parser.add_argument("--bars", required=True, type=Path)
    parser.add_argument("--date", required=True)
    parser.add_argument("--frames", type=Path, help="Optional frames metadata CSV (decoded_frames/frames.csv)")
    parser.add_argument("--horizons", nargs="+", type=int, default=[1, 5, 15, 60])
    parser.add_argument("--output-csv", required=True, type=Path)
    parser.add_argument("--summary-json", required=True, type=Path)
    args = parser.parse_args()

    signals = load_signals(args.signals, args.date)
    bars = load_bars(args.bars)
    sig_ohlc = resample_signals(signals)
    labels = build_labels(bars, args.horizons)
    bars_labeled = bars.set_index("timestamp").join(labels, rsuffix="_lbl").reset_index()
    if args.frames and args.frames.exists():
        frames = load_frames(args.frames, args.date)
        frames_agg = frame_aggregates(frames)
    else:
        frames_agg = pd.DataFrame()
    features = assemble_features(sig_ohlc, bars_labeled, frames_agg, args.horizons)

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(args.output_csv)

    summary = summarize(features, args.horizons)
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(json.dumps(summary, indent=2))
    print(f"Wrote features: {args.output_csv} ({len(features)} rows)")
    print(f"Wrote summary: {args.summary_json}")


if __name__ == "__main__":
    main()
