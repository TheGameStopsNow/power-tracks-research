#!/usr/bin/env python3
"""Spike-signature multi-scale search with simple null baseline.

For a given symbol+date, treat each decoded price_path as a template,
extract a K-spike signature (positions + heights), and search forward
over future minute bars for the best matching spike pattern across a
grid of lags and time scales.

All data is real:
  - Templates: data/power_tracks/<SYMBOL>/<trackId>/price_path.json
  - Future:   data/minute_bars/<SYMBOL>_YYYY-MM-DD_minute.csv

We also build a simple null by shuffling the template values and
repeating the same search, then report a per-burst p-value.
"""

import argparse
import json
import os
import random
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib import parse, request

import numpy as np


def load_price_path(track_dir: str) -> List[Tuple[int, float]]:
    path = os.path.join(track_dir, "price_path.json")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        series = json.load(f)
    out: List[Tuple[int, float]] = []
    for pt in series:
        try:
            ts = int(pt["ts"])
            price = float(pt["price"])
        except Exception:
            continue
        out.append((ts, price))
    out.sort(key=lambda x: x[0])
    return out


def load_summary(track_dir: str) -> Dict[str, Any]:
    path = os.path.join(track_dir, "summary.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def resample_values(values: List[float], length: int) -> np.ndarray:
    if not values:
        return None  # type: ignore[return-value]
    arr = np.asarray(values, dtype=float)
    if len(arr) == length:
        return arr
    if len(arr) < 2:
        return None  # type: ignore[return-value]
    idx = np.linspace(0, len(arr) - 1, num=length)
    return np.interp(idx, np.arange(len(arr)), arr)


def load_minute_bars_for_range(
    bars_dir: str, symbol: str, start_date: date, end_date: date
) -> Tuple[np.ndarray, np.ndarray]:
    rows: List[Tuple[datetime, float]] = []
    cur = start_date
    while cur <= end_date:
        fname = f"{symbol}_{cur.isoformat()}_minute.csv"
        path = os.path.join(bars_dir, fname)
        if not os.path.exists(path):
            cur += timedelta(days=1)
            continue
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().strip().split("\n")
        if len(lines) <= 1:
            cur += timedelta(days=1)
            continue
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) < 5:
                continue
            ts_str = parts[0]
            close_str = parts[4]
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                close = float(close_str)
            except Exception:
                continue
            rows.append((ts, close))
        cur += timedelta(days=1)
    rows.sort(key=lambda x: x[0])
    if not rows:
        return np.array([]), np.array([])
    times = np.array([r[0].timestamp() for r in rows], dtype=float)
    prices = np.array([r[1] for r in rows], dtype=float)
    return times, prices


def spike_signature(values: np.ndarray, k: int) -> np.ndarray:
    """Return a richer K-spike signature (up + down spikes).

    Signature layout:
      [up_pos_1..k, up_height_1..k, down_pos_1..k, down_height_1..k]
    where positions are in [0,1] and heights are z-scored within each side.
    """

    if values.size < 4:
        return None  # type: ignore[return-value]
    diffs = np.diff(values)
    if diffs.size == 0:
        return None  # type: ignore[return-value]

    def side_signature(mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        idx = np.where(mask)[0]
        if idx.size == 0:
            return (
                np.full(k, 0.5, dtype=float),
                np.zeros(k, dtype=float),
            )
        mags = np.abs(diffs[idx])
        order = np.argsort(mags)[::-1]
        sel = idx[order][:k]
        sel = np.unique(sel)
        if sel.size < k:
            sel = np.pad(sel, (0, k - sel.size), mode="edge")
        sel.sort()
        positions = (sel + 1) / float(values.size)
        heights_raw = diffs[sel]
        mu = float(heights_raw.mean())
        sigma = float(heights_raw.std()) or 1.0
        heights = (heights_raw - mu) / sigma
        if heights.size < positions.size:
            heights = np.pad(heights, (0, positions.size - heights.size), mode="edge")
        return positions.astype(float), heights.astype(float)

    up_pos, up_h = side_signature(diffs > 0)
    down_pos, down_h = side_signature(diffs < 0)
    return np.concatenate([up_pos, up_h, down_pos, down_h])


def best_spike_distance(
    tmpl_vals: np.ndarray,
    detection_time: datetime,
    bar_times: np.ndarray,
    bar_prices: np.ndarray,
    base_window_minutes: int,
    horizon_days: int,
    step_lag_minutes: int,
    sample_step_minutes: int,
    scales: List[int],
    k_spikes: int,
    search_anchor: Optional[datetime] = None,
    search_end: Optional[datetime] = None,
) -> Tuple[float, Optional[str]]:
    tmpl_sig = spike_signature(tmpl_vals, k_spikes)
    if tmpl_sig is None:
        return float("inf")

    if search_anchor and search_end:
        max_lag_minutes = int((search_end - search_anchor).total_seconds() / 60.0)
        anchor_time = search_anchor
    else:
        horizon_end = detection_time + timedelta(days=horizon_days)
        max_lag_minutes = int((horizon_end - detection_time).total_seconds() / 60.0)
        anchor_time = detection_time
    best = None
    best_time = None

    for scale in scales:
        window_minutes = base_window_minutes * scale
        if window_minutes < sample_step_minutes * 2:
            continue
        lag = 0
        while lag + window_minutes <= max_lag_minutes:
            ws_dt = anchor_time + timedelta(minutes=lag)
            we_dt = ws_dt + timedelta(minutes=window_minutes)
            ws = ws_dt.timestamp()
            we = we_dt.timestamp()
            mask = (bar_times >= ws) & (bar_times <= we)
            if not mask.any():
                lag += step_lag_minutes
                continue
            seg_t = bar_times[mask]
            seg_p = bar_prices[mask]
            vals: List[float] = []
            step = sample_step_minutes * 60.0
            cur_ts = ws
            idx = 0
            n = len(seg_t)
            while cur_ts <= we and idx < n:
                while idx < n and seg_t[idx] < cur_ts:
                    idx += 1
                if idx >= n:
                    break
                vals.append(float(seg_p[idx]))
                cur_ts += step
            if len(vals) < 4:
                lag += step_lag_minutes
                continue
            cand = resample_values(vals, tmpl_vals.size)
            if cand is None:
                lag += step_lag_minutes
                continue
            sig = spike_signature(cand, k_spikes)
            if sig is None:
                lag += step_lag_minutes
                continue
            dist = float(np.linalg.norm(tmpl_sig - sig))
            if best is None or dist < best:
                best = dist
                best_time = ws_dt.isoformat()
            lag += step_lag_minutes

    return (best if best is not None else float("inf"), best_time)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="GME")
    parser.add_argument("--date", required=True)
    parser.add_argument("--bars-symbol", help="Symbol for bars if different from --symbol")
    base_dir = Path(__file__).resolve().parent.parent
    parser.add_argument("--root", default=str(base_dir / "data" / "power_tracks"))
    parser.add_argument("--bars", default=str(base_dir / "data" / "minute_bars"))
    parser.add_argument("--length", type=int, default=64)
    parser.add_argument("--horizon-days", type=int, default=360)
    parser.add_argument("--step-lag-minutes", type=int, default=2880)
    parser.add_argument("--sample-step-minutes", type=int, default=240)
    parser.add_argument(
        "--scales",
        type=int,
        nargs="+",
        default=[1440, 10080, 43200],
        help="window scales in minutes (e.g. 1440=1d,10080=7d,43200=30d)",
    )
    parser.add_argument("--max-tracks", type=int, default=5)
    parser.add_argument("--k-spikes", type=int, default=3)
    parser.add_argument("--null-shuffles", type=int, default=5)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--scan-start", help="YYYY-MM-DD start of scan range")
    parser.add_argument("--scan-end", help="YYYY-MM-DD end of scan range")
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    root_abs = os.path.abspath(args.root)
    bars_abs = os.path.abspath(args.bars)
    target_date = datetime.fromisoformat(args.date).date()
    
    bars_symbol = args.bars_symbol if args.bars_symbol else args.symbol

    symbol_dir = os.path.join(root_abs, args.symbol)
    if not os.path.isdir(symbol_dir):
        print(f"[spike-search] symbol dir missing: {symbol_dir}")
        return

    # Collect tracks for this date.
    track_ids: List[str] = []
    for entry in os.listdir(symbol_dir):
        track_dir = os.path.join(symbol_dir, entry)
        if not os.path.isdir(track_dir):
            continue
        summary = load_summary(track_dir)
        if not summary:
            continue
        if summary.get("date") != target_date.isoformat():
            continue
        track_ids.append(entry)
    if not track_ids:
        print(f"[spike-search] No tracks for {args.symbol} on {target_date}")
        return

    track_ids.sort()
    track_ids = track_ids[: args.max_tracks]

    # Load future minute bars once for this date.
    if args.scan_start and args.scan_end:
        start_date = datetime.strptime(args.scan_start, "%Y-%m-%d").date()
        end_date = datetime.strptime(args.scan_end, "%Y-%m-%d").date()
    else:
        start_date = target_date
        end_date = start_date + timedelta(days=args.horizon_days)

    all_bar_times, all_bar_prices = load_minute_bars_for_range(
        bars_abs, bars_symbol, start_date, end_date
    )
    if all_bar_times.size == 0:
        print(f"[spike-search] No bars for {bars_symbol} from {start_date} to {end_date}")
        return

    results: List[Dict[str, Any]] = []

    for track_id in track_ids:
        track_dir = os.path.join(symbol_dir, track_id)
        summary = load_summary(track_dir)
        series = load_price_path(track_dir)
        if not series or not summary:
            continue
        prices = [p for (_, p) in series]
        tmpl_vals = resample_values(prices, args.length)
        if tmpl_vals is None:
            continue

        det_str = summary.get("detection_time") or summary.get("detectionTime")
        if not det_str:
            continue
        try:
            detection_time = datetime.fromisoformat(det_str.replace("Z", "+00:00"))
        except Exception:
            continue

        window_info = summary.get("window") or {}
        ws_str = window_info.get("start")
        we_str = window_info.get("end")
        if ws_str and we_str:
            try:
                ws = datetime.fromisoformat(ws_str.replace("Z", "+00:00"))
                we = datetime.fromisoformat(we_str.replace("Z", "+00:00"))
                base_window_minutes = max(
                    1, int((we - ws).total_seconds() / 60.0)
                )
            except Exception:
                base_window_minutes = 30
        else:
            base_window_minutes = 30

        # Determine search range
        search_anchor = None
        search_end_dt = None
        if args.scan_start and args.scan_end:
            scan_start = datetime.strptime(args.scan_start, "%Y-%m-%d").date()
            scan_end = datetime.strptime(args.scan_end, "%Y-%m-%d").date()
            search_anchor = datetime(scan_start.year, scan_start.month, scan_start.day, tzinfo=timezone.utc)
            search_end_dt = datetime(scan_end.year, scan_end.month, scan_end.day, tzinfo=timezone.utc) + timedelta(days=1)

        real_best, real_best_time = best_spike_distance(
            tmpl_vals,
            detection_time,
            all_bar_times,
            all_bar_prices,
            base_window_minutes,
            args.horizon_days,
            args.step_lag_minutes,
            args.sample_step_minutes,
            args.scales,
            args.k_spikes,
            search_anchor=search_anchor,
            search_end=search_end_dt,
        )

        null_best: List[float] = []
        for _ in range(args.null_shuffles):
            perm = np.random.permutation(tmpl_vals.size)
            shuff = tmpl_vals[perm]
            nb, _ = best_spike_distance(
                shuff,
                detection_time,
                all_bar_times,
                all_bar_prices,
                base_window_minutes,
                args.horizon_days,
                args.step_lag_minutes,
                args.sample_step_minutes,
                args.scales,
                args.k_spikes,
                search_anchor=search_anchor,
                search_end=search_end_dt,
            )
            null_best.append(nb)

        null_arr = np.asarray(null_best)
        p = float((null_arr <= real_best).sum() / max(1, len(null_arr)))

        results.append(
            {
                "symbol": args.symbol,
                "date": target_date.isoformat(),
                "trackId": track_id,
                "realBest": real_best,
                "bestTime": real_best_time,
                "nullMean": float(null_arr.mean()),
                "nullMin": float(null_arr.min()),
                "nullMax": float(null_arr.max()),
                "pValue": p,
                "baseWindowMinutes": base_window_minutes,
            }
        )

    if not results:
        print(f"[spike-search] no results for {args.symbol} on {target_date}")
        return

    out_dir = Path(__file__).resolve().parent.parent / "output"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"tisa_spike_signatures_{args.symbol}_vs_{bars_symbol}_{target_date.isoformat()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(
        f"[spike-search] wrote {len(results)} records to {out_path} for {args.symbol} on {target_date}"
    )


if __name__ == "__main__":
    main()
