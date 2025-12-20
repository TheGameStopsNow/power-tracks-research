#!/usr/bin/env python3
"""
Overlay decoded price path vs future bars for each window/day using the best_z_rmse scale
from tisa_extended_* reports. Produces z-scored overlays for shape comparison.

Inputs:
  - reports/tisa_extended_*.json (from scripts/tisa_extended.py)
  - sample_<date>/signals/price_paths.csv
  - bars_dir (per-day minute CSVs)

Outputs:
  - reports/plots/overlays/<date>_<window>.png
"""

import glob
import json
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
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
        raise FileNotFoundError(f"No bar files for {symbol} in {bars_dir}")
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


def main():
    root = Path(__file__).resolve().parent.parent
    reports = root / "reports"
    bars_dir = root / "bars_range"
    outdir = reports / "plots" / "overlays"
    outdir.mkdir(parents=True, exist_ok=True)

    for path in sorted(glob.glob(str(reports / "tisa_extended_*.json"))):
        data = json.loads(Path(path).read_text())
        date = data["date"]
        signals_path = root / f"sample_{date}/signals/price_paths.csv"
        if not signals_path.exists():
            print(f"[skip] missing signals for {date}")
            continue
        pattern = resample_signals(load_signals(signals_path, date))
        start_ts = pattern.index.min()

        # load bars up to max window end
        max_end = max(int(w.split('-')[1]) for w in data["windows"] if '-' in w)
        end_date = (datetime.strptime(date, "%Y-%m-%d").date() + timedelta(days=max_end)).isoformat()
        bars = load_bars_span("GME", date, end_date, bars_dir)

        for w, res in data["windows"].items():
            if "note" in res:
                continue
            best = res["best_z_rmse"]
            scale = best["scale"]
            # derive window slice
            w_start, w_end = map(int, w.split("-"))
            window = bars[(bars.index >= start_ts + pd.Timedelta(days=w_start)) & (bars.index <= start_ts + pd.Timedelta(days=w_end))]
            if window.empty:
                continue
            # align
            p_scaled = rescale(pattern, scale)
            p_aligned = resample_to_length(p_scaled, len(window))
            f_aligned = resample_to_length(window, len(window))
            p_z = zscore(p_aligned)
            f_z = zscore(f_aligned)
            x = np.arange(len(p_z))

            plt.figure(figsize=(8, 4))
            plt.plot(x, p_z, label="decoded (z)", alpha=0.8)
            plt.plot(x, f_z, label=f"future bars z ({w}d)", alpha=0.8)
            plt.title(f"{date} window {w} (scale {scale})")
            plt.xlabel("Aligned index")
            plt.ylabel("z-score")
            plt.grid(True, alpha=0.3)
            plt.legend()
            out = outdir / f"{date}_{w.replace('-','_')}.png"
            plt.tight_layout()
            plt.savefig(out, dpi=150)
            plt.close()
            print(f"Wrote {out}")


if __name__ == "__main__":
    main()
