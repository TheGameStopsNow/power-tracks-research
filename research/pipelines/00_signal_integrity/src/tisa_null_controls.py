#!/usr/bin/env python3
"""
Null/contrast TISA-style analysis.

For each day, compare real decoded pattern vs fake patterns:
  - shuffled (pattern permutation, multiple draws)
  - random walk (matching len and std)
  - bar-close pattern (minute closes from same day, resampled)

Metrics: z-RMSE and DTW vs future bars across windows/scales (same as tisa_extended).
Also computes a p-value for the real best z-RMSE vs the distribution of shuffled minima.
Outputs: reports/tisa_null_controls_YYYY-MM-DD.json
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


def load_bars_span(symbol: str, start_date: str, end_date: str, bars_dir: Path) -> pd.Series:
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
    return df.set_index("timestamp")["close"]


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
    m, n = len(a), len(b)
    dp = np.full((m + 1, n + 1), np.inf, dtype=np.float64)
    dp[0, 0] = 0.0
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = abs(a[i - 1] - b[j - 1])
            dp[i, j] = cost + min(dp[i - 1, j], dp[i, j - 1], dp[i - 1, j - 1])
    return float(dp[m, n] / (m + n))


def analyze(pattern: pd.Series, future: pd.Series, scales: list[float], dtw_cap: int = 1200) -> list[dict]:
    results = []
    for s in scales:
        p_scaled = rescale(pattern, s)
        p_aligned = resample_to_length(p_scaled, len(future))
        f_aligned = resample_to_length(future, len(future))
        p_z = zscore(p_aligned)
        f_z = zscore(f_aligned)
        z_rmse = float(np.sqrt(np.mean((p_z - f_z) ** 2)))
        if len(p_z) > dtw_cap:
            p_d = resample_to_length(p_z, dtw_cap)
            f_d = resample_to_length(f_z, dtw_cap)
        else:
            p_d, f_d = p_z, f_z
        dtw = dtw_distance(p_d, f_d)
        results.append({"scale": s, "z_rmse": z_rmse, "dtw": dtw})
    return results


def main():
    parser = argparse.ArgumentParser(description="Null/contrast TISA controls")
    parser.add_argument("--signals", required=True, type=Path)
    parser.add_argument("--bars-dir", required=True, type=Path)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--windows", nargs="+", default=["60-70", "70-80", "80-90", "150-180"])
    parser.add_argument("--scales", nargs="+", type=float, default=[0.5, 0.75, 1.0, 1.25, 2.0, 4.0])
    parser.add_argument("--shuffles", type=int, default=20, help="Number of shuffled draws for p-value")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    base = resample_signals(load_signals(args.signals, args.date))
    start_ts = base.index.min()
    max_end = max(int(w.split("-")[1]) for w in args.windows)
    future_bars = load_bars_span(args.symbol, args.date, (datetime.strptime(args.date, "%Y-%m-%d").date() + timedelta(days=max_end)).isoformat(), args.bars_dir)

    rng = np.random.default_rng(123)
    fake_rw = pd.Series(np.cumsum(rng.normal(scale=base.std(), size=len(base))), index=base.index)
    # Bar-close pattern from same day (normalized to base length)
    same_day_bars = future_bars[(future_bars.index >= start_ts) & (future_bars.index <= start_ts + pd.Timedelta(days=1))]
    bar_pattern = resample_to_length(same_day_bars, len(base)) if len(same_day_bars) > 0 else np.array([])

    report = {"date": args.date, "windows": {}, "scales": args.scales}
    for w in args.windows:
        w_start, w_end = map(int, w.split("-"))
        window = future_bars[(future_bars.index >= start_ts + pd.Timedelta(days=w_start)) & (future_bars.index <= start_ts + pd.Timedelta(days=w_end))]
        if window.empty:
            report["windows"][w] = {"note": "no bars"}
            continue
        # real
        real_res = analyze(base, window, args.scales)
        real_min = min(real_res, key=lambda x: x["z_rmse"])["z_rmse"]
        # shuffles distribution of minima
        shuf_mins = []
        shuf_res = analyze(pd.Series(rng.permutation(base.values), index=base.index), window, args.scales)
        shuf_mins.append(min(shuf_res, key=lambda x: x["z_rmse"])["z_rmse"])
        for _ in range(args.shuffles - 1):
            res_tmp = analyze(pd.Series(rng.permutation(base.values), index=base.index), window, args.scales)
            shuf_mins.append(min(res_tmp, key=lambda x: x["z_rmse"])["z_rmse"])
        pval = float(np.mean(np.array(shuf_mins) <= real_min))
        res = {
            "real": real_res,
            "shuffled": shuf_res,
            "random_walk": analyze(fake_rw, window, args.scales),
            "bars_same_day": analyze(pd.Series(bar_pattern, index=base.index) if len(bar_pattern) else base, window, args.scales),
            "real_min_z_rmse": real_min,
            "shuffled_min_z_rmse_mean": float(np.mean(shuf_mins)),
            "shuffled_min_z_rmse_p10": float(np.percentile(shuf_mins, 10)),
            "shuffled_min_z_rmse_p90": float(np.percentile(shuf_mins, 90)),
            "pvalue_real_vs_shuffled_min": pval,
        }
        report["windows"][w] = res

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
