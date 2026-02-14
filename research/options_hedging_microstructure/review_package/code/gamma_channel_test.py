#!/usr/bin/env python3
"""
Gamma Channel Predictor: Floor/Ceiling Price Range Prediction
==============================================================
Reframes the meteorology test: instead of predicting DIRECTION of price
movement, predicts the BOUNDS — where price CANNOT go.

The insight: gamma walls define tradeable price channels. If dense options
energy sits at $25 and $22, price is structurally constrained to that range
by the hedging machinery. The "tornado can't hit the neighboring town"
principle — knowing where destructive forces are blocked is as valuable
as knowing where they'll strike.

Tests:
  1. Channel Extraction — find floors/ceilings from gamma energy walls
  2. Containment Backtest — did price stay within the predicted channel?
  3. Channel Width vs Realized Range — does channel width predict volatility?
  4. Floor/Ceiling Accuracy — which bound is more reliable?
  5. Breach Analysis — what happens when price breaks through a gamma wall?

Usage:
    python gamma_channel_test.py --ticker GME
    python gamma_channel_test.py --ticker GME --lookback 6
"""

import argparse
import json
import sys
import warnings
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "phase98_cluster_bridge"))

from panel_scan import POLYGON_DIR
try:
    from temporal_convolution_engine import load_equity_day
except ImportError:
    from panel_scan import load_equity_day  # type: ignore

from phase5_paradigm import _load_options_day

THETA_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw" / "thetadata" / "trades"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ===========================================================================
# Helpers (reused from meteorology)
# ===========================================================================

def get_equity_dates(ticker: str) -> list[str]:
    for prefix in [f"symbol={ticker}", f"symbol={ticker.upper()}"]:
        sym_path = POLYGON_DIR / prefix
        if sym_path.exists():
            return sorted(d.name.split("=")[1] for d in sym_path.glob("date=*"))
    return []


def get_options_dates(ticker: str) -> list[str]:
    opts_dir = THETA_ROOT / f"root={ticker}"
    if not opts_dir.exists():
        return []
    return sorted(d.name.replace("date=", "") for d in opts_dir.iterdir() if d.is_dir())


def get_overlap_dates(ticker: str) -> list[str]:
    eq = set(get_equity_dates(ticker))
    opts_raw = get_options_dates(ticker)
    opts = {f"{d[:4]}-{d[4:6]}-{d[6:8]}" for d in opts_raw if len(d) == 8}
    return sorted(eq & opts)


def get_daily_ohlc(ticker: str, date_str: str) -> dict | None:
    """Get OHLC for a trading day from tick data."""
    eq = load_equity_day(ticker, date_str)
    if eq.empty or len(eq) < 10:
        return None
    return {
        "open": float(eq["price"].iloc[0]),
        "high": float(eq["price"].max()),
        "low": float(eq["price"].min()),
        "close": float(eq["price"].iloc[-1]),
    }


# ===========================================================================
# Step 1: Build Gamma Topography → Extract Channel
# ===========================================================================

def build_strike_energy(ticker: str, date_str: str, lookback_days: int = 30) -> dict | None:
    """Build aggregate gamma energy by strike over a lookback window."""
    target_dt = pd.Timestamp(date_str)
    start_dt = target_dt - timedelta(days=lookback_days + 15)

    opts_dates = get_options_dates(ticker)
    window_dates = []
    for d in opts_dates:
        dt = pd.Timestamp(f"{d[:4]}-{d[4:6]}-{d[6:8]}")
        if start_dt <= dt <= target_dt:
            window_dates.append(f"{d[:4]}-{d[4:6]}-{d[6:8]}")

    if len(window_dates) < 5:
        return None

    ohlc = get_daily_ohlc(ticker, date_str)
    if ohlc is None:
        return None

    price = ohlc["close"]
    if price <= 0:
        return None

    strike_energy = defaultdict(float)

    for trade_date in window_dates:
        try:
            opts = _load_options_day(ticker, trade_date)
        except (FileNotFoundError, Exception):
            continue

        if opts.empty or "expiration" not in opts.columns:
            continue

        # Vectorized computation
        exp_dts = pd.to_datetime(opts["expiration"])
        dte_remaining = (exp_dts - target_dt).dt.days
        mask = dte_remaining > 0

        if not mask.any():
            continue

        valid = opts[mask]
        valid_dte = dte_remaining[mask].values

        energy = valid["size"].values * np.sqrt(valid_dte)
        strikes_arr = valid["strike"].values.astype(float)

        # Aggregate by strike
        for k, e in zip(strikes_arr, energy):
            strike_energy[k] += e

    if not strike_energy:
        return None

    return {"strike_energy": dict(strike_energy), "price": price, "ohlc": ohlc}


def extract_channel(strike_energy: dict, price: float, energy_threshold_pct: float = 0.05) -> dict:
    """
    Extract floor and ceiling from gamma energy distribution.

    Method:
    - Find all strikes within ±30% of current price with significant energy
    - The ceiling is the nearest significant energy wall ABOVE price
    - The floor is the nearest significant energy wall BELOW price
    - "Significant" = energy > threshold_pct of total energy
    """
    strikes = sorted(strike_energy.keys())
    energies = [strike_energy[k] for k in strikes]
    total_energy = sum(energies)

    if total_energy < 1:
        return {"floor": None, "ceiling": None, "channel_width": None}

    threshold = total_energy * energy_threshold_pct

    # Find walls: strikes with energy above threshold, within ±30%
    walls_above = []
    walls_below = []

    for k in strikes:
        if strike_energy[k] < threshold:
            continue
        moneyness = (k - price) / price
        if abs(moneyness) > 0.30:
            continue

        if k > price:
            walls_above.append((k, strike_energy[k]))
        else:
            walls_below.append((k, strike_energy[k]))

    # Ceiling = nearest significant wall above
    ceiling = None
    ceiling_energy = 0
    if walls_above:
        # Take nearest, but also consider strongest within 5%
        walls_above.sort(key=lambda x: x[0])  # by strike ascending
        ceiling = walls_above[0][0]
        ceiling_energy = walls_above[0][1]

        # If there's a much stronger wall within 5%, prefer it
        for k, e in walls_above[:5]:
            if e > ceiling_energy * 2 and (k - price) / price < 0.10:
                ceiling = k
                ceiling_energy = e

    # Floor = nearest significant wall below
    floor = None
    floor_energy = 0
    if walls_below:
        walls_below.sort(key=lambda x: -x[0])  # by strike descending (nearest first)
        floor = walls_below[0][0]
        floor_energy = walls_below[0][1]

        for k, e in walls_below[:5]:
            if e > floor_energy * 2 and (price - k) / price < 0.10:
                floor = k
                floor_energy = e

    channel_width = None
    channel_width_pct = None
    if floor and ceiling:
        channel_width = ceiling - floor
        channel_width_pct = channel_width / price * 100

    return {
        "floor": round(floor, 2) if floor else None,
        "ceiling": round(ceiling, 2) if ceiling else None,
        "floor_energy": round(floor_energy, 0) if floor else None,
        "ceiling_energy": round(ceiling_energy, 0) if ceiling else None,
        "channel_width": round(channel_width, 2) if channel_width else None,
        "channel_width_pct": round(channel_width_pct, 2) if channel_width_pct else None,
        "n_walls_above": len(walls_above),
        "n_walls_below": len(walls_below),
    }


# ===========================================================================
# Step 2: Backtest Channel Containment
# ===========================================================================

def backtest_channels(ticker: str, lookback_months: int = 6) -> dict:
    """
    For each trading day, build gamma channel and check if the next N days'
    price stayed within the predicted floor/ceiling.

    Tests:
    - 1-day containment
    - 5-day containment
    - 10-day containment
    - Floor accuracy (low > floor)
    - Ceiling accuracy (high < ceiling)
    """
    overlap = get_overlap_dates(ticker)
    lookback_days = lookback_months * 22

    if len(overlap) < lookback_days + 30:
        return {"status": "INSUFFICIENT_DATA"}

    start_idx = max(30, lookback_days)
    test_dates = overlap[start_idx:-10]  # leave 10 days for forward testing

    results = {
        "1d": {"contained": 0, "floor_held": 0, "ceiling_held": 0, "total": 0},
        "5d": {"contained": 0, "floor_held": 0, "ceiling_held": 0, "total": 0},
        "10d": {"contained": 0, "floor_held": 0, "ceiling_held": 0, "total": 0},
    }

    channel_widths = []
    realized_ranges = []
    floor_distances = []
    ceiling_distances = []
    breach_events = []

    print(f"  [{ticker}] Backtesting channels ({len(test_dates)} days, {lookback_months}m lookback)...")

    for i, date_str in enumerate(test_dates):
        if i > 0 and i % 50 == 0:
            rate_1d = results["1d"]["contained"] / max(results["1d"]["total"], 1) * 100
            rate_5d = results["5d"]["contained"] / max(results["5d"]["total"], 1) * 100
            print(f"    Day {i}/{len(test_dates)} — 1d contain: {rate_1d:.1f}%, 5d contain: {rate_5d:.1f}%")

        # Build channel
        se_data = build_strike_energy(ticker, date_str, lookback_days=lookback_days)
        if se_data is None:
            continue

        channel = extract_channel(se_data["strike_energy"], se_data["price"])
        if channel["floor"] is None or channel["ceiling"] is None:
            continue

        floor = channel["floor"]
        ceiling = channel["ceiling"]
        price = se_data["price"]

        channel_widths.append(channel["channel_width_pct"])

        # Test forward containment
        date_idx = overlap.index(date_str)
        for horizon_label, horizon_days in [("1d", 1), ("5d", 5), ("10d", 10)]:
            if date_idx + horizon_days >= len(overlap):
                continue

            forward_dates = overlap[date_idx + 1: date_idx + 1 + horizon_days]
            highs = []
            lows = []

            for fd in forward_dates:
                ohlc = get_daily_ohlc(ticker, fd)
                if ohlc:
                    highs.append(ohlc["high"])
                    lows.append(ohlc["low"])

            if not highs:
                continue

            max_high = max(highs)
            min_low = min(lows)
            realized_range = (max_high - min_low) / price * 100

            floor_held = min_low >= floor
            ceiling_held = max_high <= ceiling
            contained = floor_held and ceiling_held

            results[horizon_label]["total"] += 1
            if contained:
                results[horizon_label]["contained"] += 1
            if floor_held:
                results[horizon_label]["floor_held"] += 1
            if ceiling_held:
                results[horizon_label]["ceiling_held"] += 1

            if horizon_label == "5d":
                realized_ranges.append(realized_range)
                floor_distances.append((price - floor) / price * 100)
                ceiling_distances.append((ceiling - price) / price * 100)

                # Track breaches
                if not contained:
                    breach_events.append({
                        "date": date_str,
                        "floor": floor,
                        "ceiling": ceiling,
                        "min_low": min_low,
                        "max_high": max_high,
                        "breach_dir": "UP" if not ceiling_held else "DOWN",
                        "breach_pct": round(
                            (max_high - ceiling) / price * 100 if not ceiling_held
                            else (floor - min_low) / price * 100, 2
                        ),
                    })

    # Compile stats
    containment = {}
    for horizon, data in results.items():
        n = data["total"]
        if n == 0:
            continue
        containment[horizon] = {
            "total_predictions": n,
            "contained_pct": round(data["contained"] / n * 100, 1),
            "floor_held_pct": round(data["floor_held"] / n * 100, 1),
            "ceiling_held_pct": round(data["ceiling_held"] / n * 100, 1),
        }

    # Channel width vs realized range correlation
    if channel_widths and realized_ranges:
        cw = np.array(channel_widths)
        rr = np.array(realized_ranges)
        corr = np.corrcoef(cw, rr)[0, 1] if len(cw) > 5 else 0
        width_range_fit = {
            "correlation": round(float(corr), 3),
            "mean_channel_width_pct": round(float(np.mean(cw)), 2),
            "mean_realized_range_pct": round(float(np.mean(rr)), 2),
            "channel_wider_than_realized": round(float(np.mean(cw > rr)) * 100, 1),
        }
    else:
        width_range_fit = None

    # Breach analysis
    if breach_events:
        n_up_breach = sum(1 for b in breach_events if b["breach_dir"] == "UP")
        n_down_breach = sum(1 for b in breach_events if b["breach_dir"] == "DOWN")
        mean_breach_pct = np.mean([b["breach_pct"] for b in breach_events])
    else:
        n_up_breach = n_down_breach = 0
        mean_breach_pct = 0.0

    return {
        "status": "OK",
        "lookback_months": lookback_months,
        "containment": containment,
        "width_range_fit": width_range_fit,
        "breach_analysis": {
            "total_breaches_5d": len(breach_events),
            "up_breaches": n_up_breach,
            "down_breaches": n_down_breach,
            "mean_breach_pct": round(float(mean_breach_pct), 2),
        },
        "floor_stats": {
            "mean_distance_pct": round(float(np.mean(floor_distances)), 2) if floor_distances else None,
            "median_distance_pct": round(float(np.median(floor_distances)), 2) if floor_distances else None,
        },
        "ceiling_stats": {
            "mean_distance_pct": round(float(np.mean(ceiling_distances)), 2) if ceiling_distances else None,
            "median_distance_pct": round(float(np.median(ceiling_distances)), 2) if ceiling_distances else None,
        },
    }


# ===========================================================================
# Orchestrator
# ===========================================================================

def run_channel_test(ticker: str, lookback: int = 6) -> dict:
    """Run the complete gamma channel prediction test."""
    print(f"\n{'='*70}")
    print(f"  GAMMA CHANNEL PREDICTOR — {ticker}")
    print(f"  Lookback: {lookback} months")
    print(f"{'='*70}")

    # Sample channel for latest date
    overlap = get_overlap_dates(ticker)
    if len(overlap) < 60:
        return {"ticker": ticker, "status": "INSUFFICIENT_DATA"}

    sample_date = overlap[-1]
    print(f"\n  Building sample channel for {sample_date}...")
    se_data = build_strike_energy(ticker, sample_date, lookback_days=lookback * 22)

    if se_data is None:
        return {"ticker": ticker, "status": "TOPO_FAILED"}

    channel = extract_channel(se_data["strike_energy"], se_data["price"])
    price = se_data["price"]

    print(f"\n  Current price: ${price:.2f}")
    if channel["floor"] and channel["ceiling"]:
        print(f"  ┌───────────────────────────────────┐")
        print(f"  │  PREDICTED CHANNEL                │")
        print(f"  │  Ceiling:  ${channel['ceiling']:7.2f}  (+{(channel['ceiling']-price)/price*100:.1f}%)  │")
        print(f"  │  Price:    ${price:7.2f}              │")
        print(f"  │  Floor:    ${channel['floor']:7.2f}  ({(channel['floor']-price)/price*100:.1f}%)  │")
        print(f"  │  Width:     {channel['channel_width_pct']:.1f}%               │")
        print(f"  │  Walls ↑:   {channel['n_walls_above']}                    │")
        print(f"  │  Walls ↓:   {channel['n_walls_below']}                    │")
        print(f"  └───────────────────────────────────┘")

        # Show top energy strikes
        sorted_strikes = sorted(se_data["strike_energy"].items(), key=lambda x: -x[1])
        near_strikes = [(k, e) for k, e in sorted_strikes if abs((k - price) / price) <= 0.15]
        print(f"\n  Top energy walls (±15% of price):")
        for k, e in near_strikes[:8]:
            moneyness = (k - price) / price * 100
            role = "CEILING" if k > price else "FLOOR"
            bar = "█" * min(50, int(e / max(1, near_strikes[0][1]) * 50))
            print(f"    ${k:7.2f} ({moneyness:+5.1f}%) {role:7s} {bar} {e:,.0f}")
    else:
        print(f"  ⚠ Could not extract channel (insufficient wall density)")

    # Backtest
    print(f"\n{'─'*70}")
    print(f"  CHANNEL CONTAINMENT BACKTEST")
    print(f"{'─'*70}")

    bt = backtest_channels(ticker, lookback_months=lookback)

    if bt["status"] == "OK" and bt["containment"]:
        print(f"\n  ┌──────────┬──────────┬──────────┬──────────┬──────────┐")
        print(f"  │ Horizon  │ N        │ Contained│ Floor OK │ Ceil OK  │")
        print(f"  ├──────────┼──────────┼──────────┼──────────┼──────────┤")
        for h, data in bt["containment"].items():
            print(f"  │ {h:8s} │ {data['total_predictions']:8d} │ {data['contained_pct']:7.1f}% │ "
                  f"{data['floor_held_pct']:7.1f}% │ {data['ceiling_held_pct']:7.1f}% │")
        print(f"  └──────────┴──────────┴──────────┴──────────┴──────────┘")

        if bt["width_range_fit"]:
            wrf = bt["width_range_fit"]
            print(f"\n  Channel Width vs Realized Range:")
            print(f"    Correlation: {wrf['correlation']:.3f}")
            print(f"    Mean channel width:    {wrf['mean_channel_width_pct']:.1f}%")
            print(f"    Mean realized range:   {wrf['mean_realized_range_pct']:.1f}%")
            print(f"    Channel wider than actual: {wrf['channel_wider_than_realized']:.1f}% of days")

        ba = bt["breach_analysis"]
        print(f"\n  Breach Analysis (5-day):")
        print(f"    Total breaches:  {ba['total_breaches_5d']}")
        print(f"    Up breaches:     {ba['up_breaches']} ({ba['up_breaches']/max(ba['total_breaches_5d'],1)*100:.0f}%)")
        print(f"    Down breaches:   {ba['down_breaches']} ({ba['down_breaches']/max(ba['total_breaches_5d'],1)*100:.0f}%)")
        print(f"    Mean breach size: {ba['mean_breach_pct']:.2f}%")

        fs = bt["floor_stats"]
        cs = bt["ceiling_stats"]
        if fs["mean_distance_pct"] and cs["mean_distance_pct"]:
            print(f"\n  Floor/Ceiling Asymmetry:")
            print(f"    Mean floor distance:   {fs['mean_distance_pct']:.2f}% below price")
            print(f"    Mean ceiling distance: {cs['mean_distance_pct']:.2f}% above price")
            if fs["mean_distance_pct"] < cs["mean_distance_pct"]:
                print(f"    → Floor is tighter (more constraining) — downside protection")
            else:
                print(f"    → Ceiling is tighter (more constraining) — upside resistance")

        # Summary interpretation
        cont_1d = bt["containment"].get("1d", {}).get("contained_pct", 0)
        cont_5d = bt["containment"].get("5d", {}).get("contained_pct", 0)
        floor_5d = bt["containment"].get("5d", {}).get("floor_held_pct", 0)
        ceil_5d = bt["containment"].get("5d", {}).get("ceiling_held_pct", 0)

        print(f"\n{'─'*70}")
        if cont_1d > 80:
            print(f"  ⚡ STRONG: {cont_1d:.0f}% 1-day containment — gamma walls define daily bounds!")
        elif cont_1d > 65:
            print(f"  ✓ MODERATE: {cont_1d:.0f}% 1-day containment — walls are meaningful constraints")
        else:
            print(f"  ✗ WEAK: {cont_1d:.0f}% 1-day containment — walls are too porous")

        if floor_5d > ceil_5d + 5:
            print(f"  📊 Floor is more reliable than ceiling ({floor_5d:.0f}% vs {ceil_5d:.0f}%)")
            print(f"     → Gamma provides stronger downside protection than upside resistance")
        elif ceil_5d > floor_5d + 5:
            print(f"  📊 Ceiling is more reliable than floor ({ceil_5d:.0f}% vs {floor_5d:.0f}%)")
            print(f"     → Gamma caps upside more effectively than it supports downside")
        else:
            print(f"  📊 Floor and ceiling equally reliable ({floor_5d:.0f}% vs {ceil_5d:.0f}%)")

    result = {
        "ticker": ticker,
        "status": "OK",
        "sample_channel": {
            "date": sample_date,
            "price": price,
            **channel,
        },
        "backtest": bt,
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="Gamma Channel Predictor")
    parser.add_argument("--ticker", type=str, required=True, help="Ticker symbol")
    parser.add_argument("--lookback", type=int, default=6,
                        help="Lookback in months (default: 6)")
    args = parser.parse_args()

    result = run_channel_test(args.ticker.upper(), lookback=args.lookback)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outpath = RESULTS_DIR / f"gamma_channel_{args.ticker.upper()}_{timestamp}.json"

    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean(v) for v in obj]
        elif isinstance(obj, (np.bool_,)):
            return bool(obj)
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (pd.Timestamp,)):
            return str(obj)
        return obj

    with open(outpath, "w") as f:
        json.dump(clean(result), f, indent=2)
    print(f"\n  Results saved to: {outpath.name}")


if __name__ == "__main__":
    main()
