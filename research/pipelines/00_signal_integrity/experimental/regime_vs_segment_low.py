#!/usr/bin/env python3
"""
Experimental: relate segment strength to future regime (volatility / trendiness).

For each anchor date with segment_ohlc_s8_YYYY-MM-DD.json:
  - For each requested window (e.g. 60-70, 70-80 days):
      * Find the segment whose LOW series has the smallest z-RMSE vs future lows
        (best_low_z_rmse) and similarly for HIGH (best_high_z_rmse).
      * Using minute bars, compute over that window:
          - realized_vol: std of log returns of close.
          - trend_return: close_last / close_first - 1.
          - trend_ratio: |trend_return| / (realized_vol + eps).

Summarizes, per window:
  - Correlation between -best_low_z_rmse and realized_vol / trend_ratio.
  - Correlation between -best_high_z_rmse and realized_vol / trend_ratio.
  - Mean realized_vol and trend_ratio by quartiles of best_low_z_rmse.

Outputs:
  - reports/regime_vs_segment_low.json
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


def load_segment_strength(
    reports_dir: Path, windows: List[str]
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """
    Returns mapping:
      {date: {window: {"low": best_low_z_rmse, "high": best_high_z_rmse}}}
    """
    out: Dict[str, Dict[str, Dict[str, float]]] = {}
    for path in sorted(reports_dir.glob("segment_ohlc_s8_*.json")):
        data = json.loads(path.read_text())
        date = data.get("date")
        if not date:
            continue
        per_win: Dict[str, Dict[str, float]] = {}
        for w, wres in data.get("windows", {}).items():
            if w not in windows or "note" in wres:
                continue
            best_low = None
            best_high = None
            for seg_key, comps in wres.items():
                if not seg_key.startswith("segment_"):
                    continue
                low_vals = comps.get("low")
                high_vals = comps.get("high")
                if low_vals:
                    z = float(low_vals["real_z_rmse"])
                    if best_low is None or z < best_low:
                        best_low = z
                if high_vals:
                    z = float(high_vals["real_z_rmse"])
                    if best_high is None or z < best_high:
                        best_high = z
            strength: Dict[str, float] = {}
            if best_low is not None:
                strength["low"] = best_low
            if best_high is not None:
                strength["high"] = best_high
            if strength:
                per_win[w] = strength
        if per_win:
            out[date] = per_win
    return out


def load_bars_span(symbol: str, start_date: str, end_date: str, bars_dir: Path) -> pd.DataFrame:
    """Load minute bars with close between start_date and end_date inclusive."""
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    frames: List[pd.DataFrame] = []
    cur = start
    while cur <= end:
        fname = bars_dir / f"{symbol}_{cur.isoformat()}_minute.csv"
        if fname.exists():
            df = pd.read_csv(fname)
            if "timestamp" not in df.columns or "close" not in df.columns:
                cur += timedelta(days=1)
                continue
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            frames.append(df[["timestamp", "close"]])
        cur += timedelta(days=1)
    if not frames:
        raise FileNotFoundError(f"No bars in {bars_dir} for {symbol} {start_date}..{end_date}")
    df_all = pd.concat(frames, ignore_index=True).sort_values("timestamp")
    return df_all.set_index("timestamp")


def compute_regime_metrics(
    symbol: str,
    date: str,
    window: str,
    bars_dir: Path,
) -> Tuple[float, float]:
    """
    Compute realized_vol and trend_ratio over the window.
      realized_vol = std of log returns of close.
      trend_ratio = |return| / (realized_vol + eps).
    """
    anchor = datetime.strptime(date, "%Y-%m-%d").date()
    w_start, w_end = map(int, window.split("-"))
    end_date = (anchor + timedelta(days=w_end))
    bars = load_bars_span(symbol, date, end_date.isoformat(), bars_dir)

    day_start = datetime(anchor.year, anchor.month, anchor.day, tzinfo=bars.index.tz)
    w_start_ts = day_start + timedelta(days=w_start)
    w_end_ts = day_start + timedelta(days=w_end + 1)
    win_bars = bars[(bars.index >= w_start_ts) & (bars.index < w_end_ts)]
    if win_bars.empty:
        raise ValueError(f"No bars in window {window} for {date}")
    closes = win_bars["close"].to_numpy(dtype=np.float64)
    if len(closes) < 2:
        raise ValueError("Not enough closes for vol computation")
    log_ret = np.diff(np.log(closes))
    realized_vol = float(np.std(log_ret))
    trend_ret = float(closes[-1] / closes[0] - 1.0)
    eps = 1e-8
    trend_ratio = float(abs(trend_ret) / (realized_vol + eps))
    return realized_vol, trend_ratio


def summarize(z_list: List[float], vols: List[float], trends: List[float]) -> Dict:
    if not z_list:
        return {"n": 0}
    z = np.asarray(z_list, dtype=np.float64)
    vols_arr = np.asarray(vols, dtype=np.float64)
    trends_arr = np.asarray(trends, dtype=np.float64)
    strength = -z  # higher = stronger match

    corr_vol = float(np.corrcoef(strength, vols_arr)[0, 1])
    corr_trend = float(np.corrcoef(strength, trends_arr)[0, 1])

    qs = np.quantile(z, [0.25, 0.5, 0.75])
    buckets = {"strongest_q1": [], "q2": [], "q3": [], "weakest_q4": []}
    buckets_trend = {"strongest_q1": [], "q2": [], "q3": [], "weakest_q4": []}
    for zi, vi, ti in zip(z, vols_arr, trends_arr):
        if zi <= qs[0]:
            key = "strongest_q1"
        elif zi <= qs[1]:
            key = "q2"
        elif zi <= qs[2]:
            key = "q3"
        else:
            key = "weakest_q4"
        buckets[key].append(vi)
        buckets_trend[key].append(ti)

    bucket_stats = {
        name: {
            "n": len(vs),
            "mean_realized_vol": float(np.mean(vs)) if vs else None,
            "mean_trend_ratio": float(np.mean(ts)) if ts else None,
        }
        for (name, vs), ts in zip(buckets.items(), buckets_trend.values())
    }

    return {
        "n": int(len(z)),
        "corr_strength_vs_vol": corr_vol,
        "corr_strength_vs_trend_ratio": corr_trend,
        "mean_realized_vol": float(np.mean(vols_arr)),
        "mean_trend_ratio": float(np.mean(trends_arr)),
        "bucket_stats": bucket_stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Relate segment strength to future volatility/trend regime.")
    parser.add_argument("--symbol", required=True, help="Symbol, e.g. GME")
    parser.add_argument(
        "--windows",
        nargs="+",
        default=["60-70", "70-80"],
        help="Windows in days, e.g. 60-70 70-80",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    reports_dir = root / "reports"
    bars_dir = root / "bars_range"

    strengths = load_segment_strength(reports_dir, args.windows)

    out: Dict[str, Dict] = {"windows": {}}
    for w in args.windows:
        low_z: List[float] = []
        low_vols: List[float] = []
        low_trends: List[float] = []
        high_z: List[float] = []
        high_vols: List[float] = []
        high_trends: List[float] = []

        for date, per_win in strengths.items():
            if w not in per_win:
                continue
            strength = per_win[w]
            try:
                vol, trend = compute_regime_metrics(args.symbol, date, w, bars_dir)
            except Exception:
                continue
            if "low" in strength:
                low_z.append(strength["low"])
                low_vols.append(vol)
                low_trends.append(trend)
            if "high" in strength:
                high_z.append(strength["high"])
                high_vols.append(vol)
                high_trends.append(trend)

        out["windows"][w] = {
            "low": summarize(low_z, low_vols, low_trends),
            "high": summarize(high_z, high_vols, high_trends),
        }

    out_path = reports_dir / "regime_vs_segment_low.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()

