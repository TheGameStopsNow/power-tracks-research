#!/usr/bin/env python3
"""
Experimental: relate segment-low strength to future drawdown.

For each anchor date with segment_ohlc_s8_YYYY-MM-DD.json:
  - For each requested window (e.g. 60-70, 70-80 days):
      * Find the segment whose LOW series has the smallest z-RMSE
        against future lows (best_low_z_rmse).
      * Compute future max drawdown over that window using minute bars:
          anchor_close = last close on anchor day
          future_min_low = min(low) over [start+w_start, start+w_end]
          drawdown = future_min_low / anchor_close - 1
Summarizes, per window:
  - Correlation between -best_low_z_rmse (stronger match) and drawdown.
  - Mean drawdown by quartiles of best_low_z_rmse (strongest .. weakest).

Outputs:
  - reports/drawdown_vs_segment_low.json
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


def load_segment_low_strength(reports_dir: Path, windows: List[str]) -> Dict[str, Dict[str, float]]:
    """Return {date: {window: best_low_z_rmse}}."""
    out: Dict[str, Dict[str, float]] = {}
    for path in sorted(reports_dir.glob("segment_ohlc_s8_*.json")):
        data = json.loads(path.read_text())
        date = data.get("date")
        if not date:
            continue
        per_win = {}
        for w, wres in data.get("windows", {}).items():
            if w not in windows:
                continue
            if "note" in wres:
                continue
            best_z = None
            for seg_key, comps in wres.items():
                if not seg_key.startswith("segment_"):
                    continue
                low_vals = comps.get("low")
                if not low_vals:
                    continue
                z = float(low_vals["real_z_rmse"])
                if best_z is None or z < best_z:
                    best_z = z
            if best_z is not None:
                per_win[w] = best_z
        if per_win:
            out[date] = per_win
    return out


def load_bars_span(symbol: str, start_date: str, end_date: str, bars_dir: Path) -> pd.DataFrame:
    """Load minute bars with low/close between start_date and end_date inclusive."""
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    frames: List[pd.DataFrame] = []
    cur = start
    while cur <= end:
        fname = bars_dir / f"{symbol}_{cur.isoformat()}_minute.csv"
        if fname.exists():
            df = pd.read_csv(fname)
            if "timestamp" not in df.columns or "low" not in df.columns or "close" not in df.columns:
                cur += timedelta(days=1)
                continue
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            frames.append(df[["timestamp", "low", "close"]])
        cur += timedelta(days=1)
    if not frames:
        raise FileNotFoundError(f"No bars in {bars_dir} for {symbol} {start_date}..{end_date}")
    df_all = pd.concat(frames, ignore_index=True).sort_values("timestamp")
    return df_all.set_index("timestamp")


def compute_drawdown(
    symbol: str,
    date: str,
    window: str,
    bars_dir: Path,
) -> float:
    """Compute future max drawdown over [w_start, w_end] days from anchor close."""
    anchor = datetime.strptime(date, "%Y-%m-%d").date()
    w_start, w_end = map(int, window.split("-"))
    end_date = (anchor + timedelta(days=w_end))
    bars = load_bars_span(symbol, date, end_date.isoformat(), bars_dir)

    day_start = datetime(anchor.year, anchor.month, anchor.day, tzinfo=bars.index.tz)
    next_day = day_start + timedelta(days=1)
    anchor_bars = bars[(bars.index >= day_start) & (bars.index < next_day)]
    if anchor_bars.empty:
        raise ValueError(f"No bars for anchor day {date}")
    anchor_close = float(anchor_bars["close"].iloc[-1])

    w_start_ts = day_start + timedelta(days=w_start)
    w_end_ts = day_start + timedelta(days=w_end + 1)
    win_bars = bars[(bars.index >= w_start_ts) & (bars.index < w_end_ts)]
    if win_bars.empty:
        raise ValueError(f"No bars in window {window} for {date}")
    future_min_low = float(win_bars["low"].min())

    if anchor_close <= 0:
        return 0.0
    return float(future_min_low / anchor_close - 1.0)


def summarize(z_list: List[float], dd_list: List[float]) -> Dict:
    z = np.asarray(z_list, dtype=np.float64)
    dd = np.asarray(dd_list, dtype=np.float64)
    if len(z) == 0:
        return {"n": 0}
    strength = -z  # higher is stronger low-match
    corr = float(np.corrcoef(strength, dd)[0, 1])
    # Quartiles on z (lower = stronger)
    qs = np.quantile(z, [0.25, 0.5, 0.75])
    buckets = {"strongest_q1": [], "q2": [], "q3": [], "weakest_q4": []}
    for zi, ddi in zip(z, dd):
        if zi <= qs[0]:
            buckets["strongest_q1"].append(ddi)
        elif zi <= qs[1]:
            buckets["q2"].append(ddi)
        elif zi <= qs[2]:
            buckets["q3"].append(ddi)
        else:
            buckets["weakest_q4"].append(ddi)
    bucket_stats = {
        name: {
            "n": len(vals),
            "mean_drawdown": float(np.mean(vals)) if vals else None,
        }
        for name, vals in buckets.items()
    }
    return {
        "n": int(len(z)),
        "corr_strength_vs_drawdown": corr,
        "mean_drawdown": float(np.mean(dd)),
        "bucket_stats": bucket_stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Relate segment-low strength to future drawdown.")
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

    strengths = load_segment_low_strength(reports_dir, args.windows)

    result: Dict[str, Dict] = {"windows": {}}
    for w in args.windows:
        z_list: List[float] = []
        dd_list: List[float] = []
        for date, per_win in strengths.items():
            if w not in per_win:
                continue
            try:
                dd = compute_drawdown(args.symbol, date, w, bars_dir)
            except Exception:
                continue
            z_list.append(per_win[w])
            dd_list.append(dd)
        result["windows"][w] = summarize(z_list, dd_list)

    out = reports_dir / "drawdown_vs_segment_low.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

