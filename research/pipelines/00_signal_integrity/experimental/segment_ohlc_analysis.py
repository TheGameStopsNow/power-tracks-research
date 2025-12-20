#!/usr/bin/env python3
"""
Experimental: segment-level mapping of decoded price paths to future OHLC components.

For each day:
  - Build a 1-minute decoded price series.
  - Split it into N equal segments.
  - For each segment and each future window (e.g. 60-70, 70-80 days), compare the segment shape
    to future close/high/low/range/body series using z-RMSE with shuffle-based p-values.

Outputs: reports/segment_ohlc_YYYY-MM-DD.json
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


def load_signals(path: Path, date: str) -> pd.Series:
    df = pd.read_csv(path)
    day_start = pd.Timestamp(f"{date}T00:00:00Z")
    df["timestamp"] = day_start + pd.to_timedelta(df["timestamp_ms"], unit="ms")
    return df.set_index("timestamp")["price"].sort_index()


def load_bars_span(symbol: str, start_date: str, end_date: str, bars_dir: Path) -> pd.DataFrame:
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    frames = []
    cur = start
    while cur <= end:
        fname = bars_dir / f"{symbol}_{cur.isoformat()}_minute.csv"
        if fname.exists():
            df = pd.read_csv(fname)
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            frames.append(df[["timestamp", "open", "high", "low", "close"]])
        cur += timedelta(days=1)
    if not frames:
        raise FileNotFoundError(f"No bars in {bars_dir} for {symbol} {start_date}..{end_date}")
    df = pd.concat(frames, ignore_index=True).sort_values("timestamp")
    return df.set_index("timestamp")


def resample_signals(series: pd.Series, freq: str = "1min") -> pd.Series:
    return series.resample(freq).last().dropna()


def resample_to_length(series: pd.Series | np.ndarray, target_len: int) -> np.ndarray:
    arr = np.asarray(series, dtype=np.float64)
    if len(arr) == target_len:
        return arr
    x_old = np.linspace(0, 1, len(arr))
    x_new = np.linspace(0, 1, target_len)
    return np.interp(x_new, x_old, arr)


def zscore(arr: np.ndarray) -> np.ndarray:
    mu = arr.mean()
    sigma = arr.std()
    if sigma == 0:
        return arr - mu
    return (arr - mu) / sigma


def z_rmse(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sqrt(np.mean((zscore(a) - zscore(b)) ** 2)))


def make_segments(series: pd.Series, n_segments: int):
    n = len(series)
    seg_len = max(1, n // n_segments)
    segments = []
    for i in range(n_segments):
        start = i * seg_len
        end = (i + 1) * seg_len if i < n_segments - 1 else n
        if start >= n:
            break
        seg = series.iloc[start:end]
        if len(seg) >= 5:
            segments.append((i, seg))
    return segments


def analyze_day(signals_path: Path, bars_dir: Path, symbol: str, date: str, windows, shuffles: int, segments: int) -> dict:
    price = resample_signals(load_signals(signals_path, date))
    segs = make_segments(price, segments)
    start_ts = price.index.min()

    max_end = max(int(w.split("-")[1]) for w in windows)
    bars = load_bars_span(symbol, date, (datetime.strptime(date, "%Y-%m-%d").date() + timedelta(days=max_end)).isoformat(), bars_dir)

    rng = np.random.default_rng(777)
    report = {"date": date, "windows": {}, "segments": segments}

    for w in windows:
        w_start, w_end = map(int, w.split("-"))
        win_bars = bars[(bars.index >= start_ts + pd.Timedelta(days=w_start)) & (bars.index <= start_ts + pd.Timedelta(days=w_end))]
        if win_bars.empty:
            report["windows"][w] = {"note": "no bars"}
            continue
        win_series = {
            "close": win_bars["close"],
            "high": win_bars["high"],
            "low": win_bars["low"],
            "range": win_bars["high"] - win_bars["low"],
            "body": win_bars["close"] - win_bars["open"],
        }
        w_res = {}
        for seg_idx, seg in segs:
            seg_key = f"segment_{seg_idx}"
            s_arr = seg.to_numpy(dtype=np.float64)
            seg_metrics = {}
            for name, target in win_series.items():
                t_arr = target.to_numpy(dtype=np.float64)
                s_aligned = resample_to_length(s_arr, len(t_arr))
                real = z_rmse(s_aligned, t_arr)
                shuf_vals = []
                for _ in range(shuffles):
                    sh = rng.permutation(s_aligned)
                    shuf_vals.append(z_rmse(sh, t_arr))
                shuf_vals = np.asarray(shuf_vals)
                pval = float(np.mean(shuf_vals <= real))
                seg_metrics[name] = {
                    "real_z_rmse": real,
                    "shuffled_mean": float(shuf_vals.mean()),
                    "shuffled_p10": float(np.percentile(shuf_vals, 10)),
                    "shuffled_p90": float(np.percentile(shuf_vals, 90)),
                    "pvalue_real_vs_shuffled": pval,
                }
            w_res[seg_key] = seg_metrics
        report["windows"][w] = w_res
    return report


def main():
    parser = argparse.ArgumentParser(description="Segment vs OHLC mapping (experimental).")
    parser.add_argument("--signals", required=True, type=Path)
    parser.add_argument("--bars-dir", required=True, type=Path)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--windows", nargs="+", default=["60-70", "70-80"])
    parser.add_argument("--shuffles", type=int, default=20)
    parser.add_argument("--segments", type=int, default=4)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    report = analyze_day(args.signals, args.bars_dir, args.symbol, args.date, args.windows, args.shuffles, args.segments)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()

