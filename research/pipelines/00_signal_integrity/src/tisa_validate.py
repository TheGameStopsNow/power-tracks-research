#!/usr/bin/env python3
"""
TISA validation: compare decoded price paths to future market playouts across scales/horizons.

Inputs:
  --signals      decoded price_paths.csv
  --bars         minute bars CSV (timestamp, open, high, low, close) [legacy single-day mode]
  --bars-dir     directory of per-day minute CSVs (<SYMBOL>_YYYY-MM-DD_minute.csv)
  --symbol       ticker (required with --bars-dir)
  --date         anchor date YYYY-MM-DD
  --horizons     horizons in days (e.g., 1 4 7 30 90 180)
  --scales       scales to test (e.g., 0.5 0.75 1.0 1.25 2.0 4.0)
  --output       JSON report

Requires: tisa_finance
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import numpy as np

from tisa.distance import TISADistance


def load_signals(path: Path, date: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "price" not in df.columns or "timestamp_ms" not in df.columns:
        raise ValueError("signals must have price and timestamp_ms")
    day_start = pd.Timestamp(f"{date}T00:00:00Z")
    df["timestamp"] = day_start + pd.to_timedelta(df["timestamp_ms"], unit="ms")
    return df[["timestamp", "price"]]


def load_bars(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"timestamp", "close"}
    if not required.issubset(df.columns):
        raise ValueError(f"bars must include {required}")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def load_bars_span(symbol: str, start_date: str, end_date: str, bars_dir: Path) -> pd.DataFrame:
    """Concatenate per-day minute bars to cover [start_date, end_date]."""
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
    return (
        pd.concat(frames, ignore_index=True)
        .sort_values("timestamp")
        .reset_index(drop=True)
    )


def resample_signals(signals: pd.DataFrame, freq: str = "1min") -> pd.DataFrame:
    return signals.set_index("timestamp")["price"].resample(freq).last().dropna()


def extract_future(bars: pd.DataFrame, start: pd.Timestamp, horizon_days: int) -> pd.Series:
    end = start + pd.Timedelta(days=horizon_days)
    window = bars[(bars["timestamp"] >= start) & (bars["timestamp"] <= end)]
    return window.set_index("timestamp")["close"]


def rescale(series: pd.Series, scale: float) -> np.ndarray:
    arr = series.to_numpy(dtype=np.float64)
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


def tisa_compare(pattern: pd.Series, market: pd.Series, scales: list[float]) -> dict:
    tisa = TISADistance()
    results = []
    for s in scales:
        try:
            p_scaled = rescale(pattern, s)
            # Preserve full future window; resample both to a common length (max of both).
            target_len = max(len(p_scaled), len(market))
            p = resample_to_length(p_scaled, target_len)
            m = resample_to_length(market, target_len)
            dist = tisa.pairwise(p, m)
            results.append({"scale": s, "distance": float(dist)})
        except Exception:
            continue
    if not results:
        return {"best_scale": None, "best_distance": None, "scales": []}
    best = min(results, key=lambda x: x["distance"])
    return {"best_scale": best["scale"], "best_distance": best["distance"], "scales": results}


def zscore(arr: np.ndarray) -> np.ndarray:
    mu = arr.mean()
    sigma = arr.std()
    if sigma == 0:
        return arr - mu
    return (arr - mu) / sigma


def main():
    parser = argparse.ArgumentParser(description="Run TISA validation on decoded signals vs future bars.")
    parser.add_argument("--signals", required=True, type=Path)
    parser.add_argument("--bars", type=Path, help="Single CSV (legacy, one-day)")
    parser.add_argument("--bars-dir", type=Path, help="Directory of per-day minute CSVs (<SYMBOL>_YYYY-MM-DD_minute.csv)")
    parser.add_argument("--symbol", help="Ticker (required with --bars-dir)")
    parser.add_argument("--date", required=True)
    parser.add_argument("--horizons", nargs="+", type=int, default=[1, 4, 7, 30, 90])
    parser.add_argument("--scales", nargs="+", type=float, default=[0.5, 0.75, 1.0, 1.25, 2.0, 4.0])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    signals = load_signals(args.signals, args.date)
    if args.bars_dir:
        if not args.symbol:
            raise SystemExit("--symbol is required when using --bars-dir")
        max_h = max(args.horizons)
        end_date = (datetime.strptime(args.date, "%Y-%m-%d").date() + timedelta(days=max_h)).isoformat()
        bars = load_bars_span(args.symbol, args.date, end_date, args.bars_dir)
    else:
        if not args.bars:
            raise SystemExit("Provide --bars or --bars-dir")
        bars = load_bars(args.bars)

    pattern = resample_signals(signals)  # pattern series

    report = {"horizons": {}}
    start = pattern.index.min()
    for h in args.horizons:
        future = extract_future(bars, start, h)
        if future.empty:
            report["horizons"][h] = {"best_scale": None, "best_distance": None, "note": "insufficient future bars"}
            continue
        # clean NaN
        pattern_clean = pattern.dropna()
        future_clean = future.dropna()
        min_len = min(len(pattern_clean), len(future_clean))
        if min_len < 5:
            report["horizons"][h] = {"best_scale": None, "best_distance": None, "note": "too few points after alignment"}
            continue
        p = pattern_clean
        f = future_clean
        # z-score RMSE on aligned lengths to expose horizon-specific divergence
        f_aligned = resample_to_length(f, len(f))
        p_aligned = resample_to_length(p, len(f))
        rmse_z = float(np.sqrt(np.mean((zscore(p_aligned) - zscore(f_aligned)) ** 2)))

        result = tisa_compare(p, f, args.scales)
        if result["best_distance"] is None:
            # Fallback: use z-RMSE as the distance when TISA alignment fails.
            result["best_distance"] = rmse_z
            result["best_scale"] = "rmse_fallback"
        result["rmse_zscore"] = rmse_z
        report["horizons"][h] = result

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(f"Wrote TISA report: {args.output}")


if __name__ == "__main__":
    main()
