#!/usr/bin/env python3
"""
Extended TISA-style analysis with multiple metrics and non-overlapping windows.

Metrics per window/scale:
  - z-RMSE between z-scored decoded path and future bars.
  - DTW distance (on z-scored series, resampled to a capped length to keep runtime reasonable).
  - Noise baselines using shuffled decoded path.

Windows are specified as day ranges (e.g., 0-30 means [anchor, anchor+30d]).
Bars are loaded from a bars_dir containing per-day minute CSVs named <SYMBOL>_YYYY-MM-DD_minute.csv.
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple

import numpy as np
import pandas as pd


# ---------- I/O helpers ----------
def load_signals(path: Path, date: str) -> pd.Series:
    df = pd.read_csv(path)
    if "price" not in df.columns or "timestamp_ms" not in df.columns:
        raise ValueError("signals must have price and timestamp_ms")
    day_start = pd.Timestamp(f"{date}T00:00:00Z")
    df["timestamp"] = day_start + pd.to_timedelta(df["timestamp_ms"], unit="ms")
    return df.set_index("timestamp")["price"].sort_index()


def load_bars(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"timestamp", "close"}
    if not required.issubset(df.columns):
        raise ValueError(f"bars must include {required}")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.sort_values("timestamp")


def load_bars_span(symbol: str, start_date: str, end_date: str, bars_dir: Path) -> pd.Series:
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    frames = []
    cur = start
    while cur <= end:
        fname = bars_dir / f"{symbol}_{cur.isoformat()}_minute.csv"
        if fname.exists():
            frames.append(load_bars(fname))
        cur += timedelta(days=1)
    if not frames:
        raise FileNotFoundError(f"No bar files found in {bars_dir} for {symbol} between {start_date} and {end_date}")
    df = pd.concat(frames, ignore_index=True).sort_values("timestamp")
    return df.set_index("timestamp")["close"]


# ---------- resampling / metrics ----------
def resample_signals(series: pd.Series, freq: str = "1min") -> pd.Series:
    return series.resample(freq).last().dropna()


def rescale(series: pd.Series | np.ndarray, scale: float) -> np.ndarray:
    arr = np.asarray(series, dtype=np.float64)
    if scale == 1.0:
        return arr
    new_len = max(5, int(len(arr) * scale))
    x_old = np.linspace(0, 1, len(arr))
    x_new = np.linspace(0, 1, new_len)
    return np.interp(x_new, x_old, arr)


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


def dtw_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Simple DTW (normalized by path length)."""
    m, n = len(a), len(b)
    dp = np.full((m + 1, n + 1), np.inf, dtype=np.float64)
    dp[0, 0] = 0.0
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = abs(a[i - 1] - b[j - 1])
            dp[i, j] = cost + min(dp[i - 1, j], dp[i, j - 1], dp[i - 1, j - 1])
    return float(dp[m, n] / (m + n))


# ---------- main computation ----------
def parse_windows(win_args: List[str]) -> List[Tuple[int, int]]:
    out = []
    for w in win_args:
        if "-" not in w:
            raise ValueError(f"Window must be start-end (days): {w}")
        a, b = w.split("-")
        out.append((int(a), int(b)))
    return out


def analyze_window(pattern: pd.Series, future: pd.Series, scales: List[float], dtw_cap: int = 1200) -> dict:
    rng = np.random.default_rng(42)
    results = []
    for s in scales:
        p_scaled = rescale(pattern, s)
        p_aligned = resample_to_length(p_scaled, len(future))
        f_aligned = resample_to_length(future, len(future))

        p_z = zscore(p_aligned)
        f_z = zscore(f_aligned)
        z_rmse = float(np.sqrt(np.mean((p_z - f_z) ** 2)))

        # Cap length for DTW to avoid O(n^2) blowups
        if len(p_z) > dtw_cap:
            p_d = resample_to_length(p_z, dtw_cap)
            f_d = resample_to_length(f_z, dtw_cap)
        else:
            p_d, f_d = p_z, f_z
        dtw = dtw_distance(p_d, f_d)

        # Noise baseline (shuffled) distribution
        shuff_z = []
        shuff_dtw = []
        for _ in range(5):
            p_shuff = rng.permutation(p_z)
            if len(p_shuff) > dtw_cap:
                p_shuff_d = resample_to_length(p_shuff, dtw_cap)
            else:
                p_shuff_d = p_shuff
            shuff_z.append(float(np.sqrt(np.mean((p_shuff - f_z) ** 2))))
            shuff_dtw.append(dtw_distance(p_shuff_d, f_d))

        results.append(
            {
                "scale": s,
                "z_rmse": z_rmse,
                "dtw": dtw,
                "z_rmse_shuffled_mean": float(np.mean(shuff_z)),
                "z_rmse_shuffled_p10": float(np.percentile(shuff_z, 10)),
                "z_rmse_shuffled_p90": float(np.percentile(shuff_z, 90)),
                "dtw_shuffled_mean": float(np.mean(shuff_dtw)),
                "dtw_shuffled_p10": float(np.percentile(shuff_dtw, 10)),
                "dtw_shuffled_p90": float(np.percentile(shuff_dtw, 90)),
            }
        )

    best_z = min(results, key=lambda x: x["z_rmse"])
    best_dtw = min(results, key=lambda x: x["dtw"])
    return {"best_z_rmse": best_z, "best_dtw": best_dtw, "scales": results}


def main():
    parser = argparse.ArgumentParser(description="Extended TISA-like analysis with z-RMSE, DTW, and noise baselines.")
    parser.add_argument("--signals", required=True, type=Path)
    parser.add_argument("--bars-dir", required=True, type=Path)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--date", required=True, help="Anchor date YYYY-MM-DD")
    parser.add_argument("--windows", nargs="+", default=["0-30", "60-90", "150-180"], help="Windows in days, e.g. 0-30 60-90")
    parser.add_argument("--scales", nargs="+", type=float, default=[0.5, 0.75, 1.0, 1.25, 2.0, 4.0])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    windows = parse_windows(args.windows)
    max_h = max(b for _, b in windows)

    pattern = resample_signals(load_signals(args.signals, args.date))
    end_date = (datetime.strptime(args.date, "%Y-%m-%d").date() + timedelta(days=max_h)).isoformat()
    future_bars = load_bars_span(args.symbol, args.date, end_date, args.bars_dir)

    start_ts = pattern.index.min()
    report = {"date": args.date, "windows": {}, "scales": args.scales}

    for w_start, w_end in windows:
        w_label = f"{w_start}-{w_end}"
        window = future_bars[
            (future_bars.index >= start_ts + pd.Timedelta(days=w_start))
            & (future_bars.index <= start_ts + pd.Timedelta(days=w_end))
        ]
        if window.empty:
            report["windows"][w_label] = {"note": "no bars in window"}
            continue
        result = analyze_window(pattern, window, args.scales)
        report["windows"][w_label] = result

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
