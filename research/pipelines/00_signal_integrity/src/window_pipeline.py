#!/usr/bin/env python3
"""
Tier-2 window processor: takes candidate windows and runs tick -> frames -> signals pipeline.

Requirements:
- Tick CSV covering the requested windows (timestamp, price, volume, venue, conditions, symbol).
- windows.json produced by select_windows.py (list of {symbol, start, end, ...}).

Outputs per window:
  output_dir/<symbol>_<start>_<end>/
    raw_ticks.csv (window slice)
    frames.bin (length-prefixed frames)
    frames.csv (metadata)
    price_paths.csv / price_paths.parquet / price_paths.sqlite
"""

import argparse
import json
from pathlib import Path
from typing import List, Dict

import pandas as pd

from scripts.raw_to_signals import process_raw_ticks, decode_frames


def load_windows(path: Path) -> List[Dict]:
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError("windows JSON must be a list")
    return data


def slice_ticks(tick_path: Path, start: str, end: str) -> pd.DataFrame:
    df = pd.read_csv(tick_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    start_ts = pd.to_datetime(start, utc=True)
    end_ts = pd.to_datetime(end, utc=True)
    return df[(df["timestamp"] >= start_ts) & (df["timestamp"] <= end_ts)].copy()


def process_window(window: Dict, ticks_path: Path, out_root: Path, max_ticks: int, chunk_size: int):
    start = window["start"].replace(":", "").replace("-", "").replace("+00:00", "Z")
    end = window["end"].replace(":", "").replace("-", "").replace("+00:00", "Z")
    win_id = f"{window['symbol']}_{start}_{end}"
    out_dir = out_root / win_id
    out_dir.mkdir(parents=True, exist_ok=True)

    ticks_df = slice_ticks(ticks_path, window["start"], window["end"])
    if ticks_df.empty:
        print(f"[WARN] no ticks for window {win_id}")
        return
    tick_out = out_dir / "raw_ticks.csv"
    ticks_df.to_csv(tick_out, index=False)

    frames_out = out_dir / "frames.bin"
    process_raw_ticks(
        tick_out,
        frames_out,
        format_type="binary",
        detection_time=window["start"],
        max_ticks=max_ticks,
        chunk_size=chunk_size,
    )

    signals_out = out_dir / "price_paths.csv"
    decode_frames(frames_out, signals_out, None)


def main():
    parser = argparse.ArgumentParser(description="Process candidate windows into decoded frames/signals.")
    parser.add_argument("--windows", required=True, type=Path, help="windows.json from select_windows.py")
    parser.add_argument("--ticks", required=True, type=Path, help="Tick CSV covering requested windows")
    parser.add_argument("--output", required=True, type=Path, help="Output root directory for per-window artifacts")
    parser.add_argument("--max-ticks", type=int, default=0, help="Optional cap per window (0 = no cap)")
    parser.add_argument("--chunk-size", type=int, default=0, help="Ticks per frame (0 = all ticks in one frame)")
    args = parser.parse_args()

    windows = load_windows(args.windows)
    if not windows:
        print("No windows to process.")
        return

    out_root = args.output
    out_root.mkdir(parents=True, exist_ok=True)
    for window in windows:
        process_window(
            window,
            args.ticks,
            out_root,
            max_ticks=args.max_ticks if args.max_ticks > 0 else None,
            chunk_size=args.chunk_size if args.chunk_size > 0 else None,
        )


if __name__ == "__main__":
    main()
