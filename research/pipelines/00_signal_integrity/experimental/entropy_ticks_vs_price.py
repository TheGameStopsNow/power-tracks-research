#!/usr/bin/env python3
"""
Experimental: entropy envelope from raw tick data vs future price paths.

For each day:
  - Build a per-minute entropy series from raw ticks (entropy of sign of price changes within each minute).
  - Compare that entropy envelope to future minute closes over windows (e.g. 60-70, 70-80 days ahead).
  - Metric: z-RMSE with shuffle-based p-value.

Outputs: reports/entropy_ticks_vs_price_YYYY-MM-DD.json
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


def load_ticks_entropy(path: Path) -> pd.Series:
    df = pd.read_csv(path)
    if "timestamp" not in df.columns or "price" not in df.columns:
        raise ValueError("raw_ticks must have timestamp and price columns")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="ISO8601")
    df = df.sort_values("timestamp")
    deltas = df["price"].diff().dropna()
    signs = np.sign(deltas.to_numpy())
    sign_series = pd.Series(signs, index=df["timestamp"].iloc[1:])

    def entropy_block(block: pd.Series) -> float:
        vals = block.to_numpy()
        if len(vals) == 0:
            return np.nan
        pos = np.sum(vals > 0)
        neg = np.sum(vals < 0)
        zero = len(vals) - pos - neg
        probs = np.array([pos, neg, zero], dtype=np.float64)
        probs = probs[probs > 0]
        if probs.size == 0:
            return 0.0
        probs = probs / probs.sum()
        return float(-np.sum(probs * np.log2(probs)))

    ent = sign_series.groupby(pd.Grouper(freq="1min")).apply(entropy_block)
    return ent.dropna()


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
            frames.append(df[["timestamp", "close"]])
        cur += timedelta(days=1)
    if not frames:
        raise FileNotFoundError(f"No bars in {bars_dir} for {symbol} {start_date}..{end_date}")
    df = pd.concat(frames, ignore_index=True).sort_values("timestamp")
    return df.set_index("timestamp")


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


def analyze_day(ticks_path: Path, bars_dir: Path, symbol: str, date: str, windows, shuffles: int) -> dict:
    ent = load_ticks_entropy(ticks_path)
    start_ts = ent.index.min()

    max_end = max(int(w.split("-")[1]) for w in windows)
    bars = load_bars_span(symbol, date, (datetime.strptime(date, "%Y-%m-%d").date() + timedelta(days=max_end)).isoformat(), bars_dir)
    close = bars["close"]

    rng = np.random.default_rng(321)
    result = {"date": date, "windows": {}}

    for w in windows:
        w_start, w_end = map(int, w.split("-"))
        win_close = close[(close.index >= start_ts + pd.Timedelta(days=w_start)) & (close.index <= start_ts + pd.Timedelta(days=w_end))]
        if win_close.empty:
            result["windows"][w] = {"note": "no bars"}
            continue
        ent_aligned = resample_to_length(ent, len(win_close))
        price_arr = win_close.to_numpy(dtype=np.float64)
        real = z_rmse(ent_aligned, price_arr)
        shuf_vals = []
        for _ in range(shuffles):
            sh = rng.permutation(ent_aligned)
            shuf_vals.append(z_rmse(sh, price_arr))
        shuf_vals = np.asarray(shuf_vals)
        pval = float(np.mean(shuf_vals <= real))
        result["windows"][w] = {
            "real_z_rmse": real,
            "shuffled_mean": float(shuf_vals.mean()),
            "shuffled_p10": float(np.percentile(shuf_vals, 10)),
            "shuffled_p90": float(np.percentile(shuf_vals, 90)),
            "pvalue_real_vs_shuffled": pval,
        }
    return result


def main():
    parser = argparse.ArgumentParser(description="Entropy envelope from raw ticks vs future price (experimental).")
    parser.add_argument("--ticks", required=True, type=Path)
    parser.add_argument("--bars-dir", required=True, type=Path)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--windows", nargs="+", default=["60-70", "70-80"])
    parser.add_argument("--shuffles", type=int, default=20)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    report = analyze_day(args.ticks, args.bars_dir, args.symbol, args.date, args.windows, args.shuffles)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
