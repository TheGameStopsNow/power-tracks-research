#!/usr/bin/env python3
"""
Experimental: compare an entropy-like envelope of decoded paths vs future realized volatility.

For each day:
  - Build a 1-minute decoded price series and a local entropy series based on sign of price changes.
  - Build a future realized volatility series (rolling window on minute bars).
  - For each window (e.g. 60-70, 70-80 days ahead), compare the entropy envelope to future volatility
    via z-RMSE, with a shuffle-based p-value.

Outputs: reports/entropy_vs_vol_YYYY-MM-DD.json
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
            frames.append(df[["timestamp", "close"]])
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


def entropy_from_signs(prices: pd.Series, window: int = 16) -> pd.Series:
    """Compute local entropy of sign of price changes in a rolling window."""
    deltas = prices.diff().dropna()
    signs = np.sign(deltas.to_numpy())

    def _entropy_block(block: np.ndarray) -> float:
        if len(block) == 0:
            return np.nan
        pos = np.sum(block > 0)
        neg = np.sum(block < 0)
        zero = len(block) - pos - neg
        probs = np.array([pos, neg, zero], dtype=np.float64)
        probs = probs[probs > 0]
        if probs.size == 0:
            return 0.0
        probs = probs / probs.sum()
        return float(-np.sum(probs * np.log2(probs)))

    ent = []
    for i in range(len(signs)):
        start = max(0, i - window + 1)
        block = signs[start : i + 1]
        ent.append(_entropy_block(block))
    ent_series = pd.Series(ent, index=deltas.index)
    return ent_series.dropna()


def realized_vol(close: pd.Series, window: int = 16) -> pd.Series:
    returns = close.pct_change().dropna()
    vol = returns.rolling(window).std()
    return vol.dropna()


def analyze_day(signals_path: Path, bars_dir: Path, symbol: str, date: str, windows, shuffles: int) -> dict:
    price = resample_signals(load_signals(signals_path, date))
    ent = entropy_from_signs(price, window=16)
    start_ts = ent.index.min()

    max_end = max(int(w.split("-")[1]) for w in windows)
    bars = load_bars_span(symbol, date, (datetime.strptime(date, "%Y-%m-%d").date() + timedelta(days=max_end)).isoformat(), bars_dir)
    vol_series = realized_vol(bars["close"], window=16)

    rng = np.random.default_rng(123)
    result = {"date": date, "windows": {}}

    for w in windows:
        w_start, w_end = map(int, w.split("-"))
        win_vol = vol_series[(vol_series.index >= start_ts + pd.Timedelta(days=w_start)) & (vol_series.index <= start_ts + pd.Timedelta(days=w_end))]
        if win_vol.empty:
            result["windows"][w] = {"note": "no vol data"}
            continue
        ent_aligned = resample_to_length(ent, len(win_vol))
        vol_arr = win_vol.to_numpy(dtype=np.float64)
        real = z_rmse(ent_aligned, vol_arr)
        shuf_vals = []
        for _ in range(shuffles):
            sh = rng.permutation(ent_aligned)
            shuf_vals.append(z_rmse(sh, vol_arr))
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
    parser = argparse.ArgumentParser(description="Entropy vs future volatility analysis (experimental).")
    parser.add_argument("--signals", required=True, type=Path)
    parser.add_argument("--bars-dir", required=True, type=Path)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--windows", nargs="+", default=["60-70", "70-80"])
    parser.add_argument("--shuffles", type=int, default=20)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    report = analyze_day(args.signals, args.bars_dir, args.symbol, args.date, args.windows, args.shuffles)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
