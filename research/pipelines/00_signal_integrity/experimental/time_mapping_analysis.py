#!/usr/bin/env python3
"""
Experimental: compare alternative time mappings for decoded paths vs future bars.

Mappings:
  - clock: current approach (uniform in index).
  - rth: regular-session-only bars (09:30–16:00 ET).
  - volume_time: align pattern to future bars parameterized by cumulative volume.

Metric: z-RMSE with simple shuffle-based p-value per mapping/window.
Outputs: reports/time_mapping_YYYY-MM-DD.json
"""

import argparse
import json
from datetime import datetime, timedelta, time
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
            frames.append(df[["timestamp", "close", "volume"]])
        cur += timedelta(days=1)
    if not frames:
        raise FileNotFoundError(f"No bars in {bars_dir} for {symbol} {start_date}..{end_date}")
    df = pd.concat(frames, ignore_index=True).sort_values("timestamp")
    df = df.set_index("timestamp")
    return df


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


def filter_rth(bars: pd.DataFrame) -> pd.DataFrame:
    # Regular session 09:30–16:00 US/Eastern approximated in UTC by wall-clock hour.
    # Assumes timestamps already UTC; this is rough but good enough for experiment.
    local = bars.index.tz_convert("US/Eastern")
    mask = (local.time >= time(9, 30)) & (local.time <= time(16, 0))
    return bars[mask]


def make_volume_time_series(bars: pd.DataFrame) -> pd.Series:
    vols = bars["volume"].fillna(0).to_numpy(dtype=np.float64)
    total = vols.sum()
    if total <= 0:
        x = np.linspace(0, 1, len(bars))
    else:
        cum = np.cumsum(vols)
        x = cum / cum[-1]
    return pd.Series(x, index=bars.index)


def analyze_mapping(pattern: pd.Series, window_bars: pd.DataFrame, mapping: str, rng: np.random.Generator, shuffles: int = 20) -> dict:
    if mapping == "clock":
        target = window_bars["close"]
        p = resample_to_length(pattern, len(target))
        t = target.to_numpy(dtype=np.float64)
    elif mapping == "rth":
        rth = filter_rth(window_bars)
        if rth.empty:
            return {"note": "no RTH bars"}
        target = rth["close"]
        p = resample_to_length(pattern, len(target))
        t = target.to_numpy(dtype=np.float64)
    elif mapping == "volume_time":
        vt = make_volume_time_series(window_bars)
        x_vt = vt.to_numpy(dtype=np.float64)
        target = window_bars["close"].to_numpy(dtype=np.float64)
        # pattern as function on [0,1]
        x_pat = np.linspace(0, 1, len(pattern))
        pat_arr = pattern.to_numpy(dtype=np.float64)
        p = np.interp(x_vt, x_pat, pat_arr)
        t = target
    else:
        raise ValueError(mapping)

    real = z_rmse(p, t)
    shuf_vals = []
    for _ in range(shuffles):
        shuf = rng.permutation(p)
        shuf_vals.append(z_rmse(shuf, t))
    shuf_vals = np.asarray(shuf_vals)
    pval = float(np.mean(shuf_vals <= real))
    return {
        "real_z_rmse": real,
        "shuffled_mean": float(shuf_vals.mean()),
        "shuffled_p10": float(np.percentile(shuf_vals, 10)),
        "shuffled_p90": float(np.percentile(shuf_vals, 90)),
        "pvalue_real_vs_shuffled": pval,
    }


def main():
    parser = argparse.ArgumentParser(description="Experimental time-mapping analysis for decoded paths.")
    parser.add_argument("--signals", required=True, type=Path)
    parser.add_argument("--bars-dir", required=True, type=Path)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--windows", nargs="+", default=["60-70", "70-80"])
    parser.add_argument("--shuffles", type=int, default=20)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    base = resample_signals(load_signals(args.signals, args.date))
    start_ts = base.index.min()
    max_end = max(int(w.split("-")[1]) for w in args.windows)
    bars = load_bars_span(args.symbol, args.date, (datetime.strptime(args.date, "%Y-%m-%d").date() + timedelta(days=max_end)).isoformat(), args.bars_dir)

    rng = np.random.default_rng(42)
    mappings = ["clock", "rth", "volume_time"]
    report = {"date": args.date, "windows": {}, "mappings": mappings}

    for w in args.windows:
        w_start, w_end = map(int, w.split("-"))
        window_bars = bars[(bars.index >= start_ts + pd.Timedelta(days=w_start)) & (bars.index <= start_ts + pd.Timedelta(days=w_end))]
        if window_bars.empty:
            report["windows"][w] = {"note": "no bars"}
            continue
        w_res = {}
        for m in mappings:
            try:
                w_res[m] = analyze_mapping(base, window_bars, m, rng, shuffles=args.shuffles)
            except Exception as exc:
                w_res[m] = {"error": str(exc)}
        report["windows"][w] = w_res

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()

