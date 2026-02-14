#!/usr/bin/env python3
"""
Multi-Event Wall Fatigue Analysis
===================================
Tests whether the wall-fatigue→cascade pattern discovered in GME
generalizes to other squeeze events.

Events analyzed:
  - GME: Jan 28, 2021 (benchmark — already analyzed)
  - DJT: Mar 26, 2024 peak (~$66 from ~$22)

For each event:
  1. Track gamma wall tests (approach + breach/hold)
  2. Measure number of tests before permanent failure
  3. Calculate energy at failure vs hold averages
  4. Detect cascade acceleration

Usage:
    python multi_event_wall_fatigue.py
"""

import json
import sys
import warnings
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)

sys.path.insert(0, str(Path(__file__).parent))
from phase5_paradigm import _load_options_day, _load_equity_day
from squeeze_mechanics_forensic import get_dates, get_equity_close, get_equity_ohlc

THETA_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw" / "thetadata" / "trades"
POLYGON_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw" / "polygon" / "trades"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# Define squeeze events with data availability
EVENTS = [
    {
        "ticker": "GME",
        "name": "GameStop Short Squeeze",
        "peak_date": "2021-01-28",
        "window_before": 90,
        "window_after": 20,
    },
    {
        "ticker": "DJT",
        "name": "DJT SPAC Merger Squeeze",
        "peak_date": "2024-03-26",
        "window_before": 30,  # DJT data starts Mar 26, so limited window
        "window_after": 30,
    },
]


def analyze_wall_fatigue(ticker, peak_date, window_before=90, window_after=20):
    """
    Full wall fatigue analysis for a single event.
    Returns comprehensive wall test data.
    """
    print(f"\n{'='*70}")
    print(f"  WALL FATIGUE ANALYSIS: {ticker} (peak: {peak_date})")
    print(f"{'='*70}")

    peak_dt = pd.Timestamp(peak_date)
    start_dt = peak_dt - timedelta(days=window_before)
    end_dt = peak_dt + timedelta(days=window_after)

    eq_dates = get_dates(ticker, "equity")
    opts_dates = get_dates(ticker, "options")

    # Build windows
    eq_window = []
    for d in eq_dates:
        ds = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if "-" not in d else d
        dt = pd.Timestamp(ds)
        if start_dt <= dt <= end_dt:
            eq_window.append(ds)

    opts_set = set()
    for d in opts_dates:
        ds = d.replace("-", "") if "-" in d else d
        opts_set.add(ds)

    print(f"  Equity days: {len(eq_window)}")
    if not eq_window:
        print("  ERROR: No equity data in window")
        return None

    # Build daily data
    daily_data = []
    for i, date_str in enumerate(eq_window):
        ohlc = get_equity_ohlc(ticker, date_str)
        if not ohlc:
            continue

        date_key = date_str.replace("-", "")
        call_vol = defaultdict(int)
        put_vol = defaultdict(int)
        call_energy = defaultdict(float)

        if date_key in opts_set:
            try:
                opts = _load_options_day(ticker, date_str)
                if not opts.empty:
                    for _, row in opts.iterrows():
                        strike = float(row["strike"])
                        vol = int(row["size"])
                        opt_price = float(row["price"]) if "price" in row and pd.notna(row["price"]) else 0
                        energy = vol * opt_price * 100
                        if row["right"] in ("C", "c"):
                            call_vol[strike] += vol
                            call_energy[strike] += energy
                        else:
                            put_vol[strike] += vol
            except Exception:
                pass

        price = ohlc["close"]

        # Find walls above price
        walls_above = []
        for strike in sorted(call_vol.keys()):
            if strike > price and call_vol[strike] > 50:
                walls_above.append({
                    "strike": strike,
                    "call_vol": call_vol[strike],
                    "energy": round(call_energy.get(strike, 0)),
                })
        walls_above.sort(key=lambda x: x["call_vol"], reverse=True)

        daily_data.append({
            "date": date_str, **ohlc,
            "days_to_peak": (peak_dt - pd.Timestamp(date_str)).days,
            "walls": walls_above[:10],
            "total_call_energy": round(sum(call_energy.values())),
        })

        if (i + 1) % 10 == 0:
            print(f"    {i+1}/{len(eq_window)}", end="", flush=True)

    print()

    # === WALL TEST ANALYSIS ===
    print(f"\n  --- Wall Test Results ---")

    wall_tests = []
    tracked_walls = {}  # strike → {first_seen, tests, held, breached}

    for i in range(len(daily_data)):
        day = daily_data[i]
        price = day["close"]
        high = day["high"]
        date = day["date"]

        # Register new walls
        for wall in day.get("walls", []):
            strike = wall["strike"]
            if strike not in tracked_walls:
                tracked_walls[strike] = {
                    "first_seen": date,
                    "tests": 0,
                    "holds": 0,
                    "breaches_recovered": 0,
                    "cascade": False,
                    "cascade_date": None,
                    "max_energy": wall["energy"],
                }
            tracked_walls[strike]["max_energy"] = max(
                tracked_walls[strike]["max_energy"], wall["energy"])

        # Find dominant wall above current price
        dominant = None
        dom_vol = 0
        for wall in day.get("walls", [])[:5]:
            if wall["strike"] > price and wall["call_vol"] > dom_vol:
                dominant = wall["strike"]
                dom_vol = wall["call_vol"]

        if dominant is None:
            continue

        # Was price within approach range (5% of wall)?
        approach = (dominant - price) / price * 100
        if approach > 10:
            continue

        # Did we breach?
        breached = high >= dominant
        held = price < dominant

        # Did we recover next day?
        recovered = False
        if breached and not held and i + 1 < len(daily_data):
            next_close = daily_data[i + 1]["close"]
            recovered = next_close < dominant

        # Track
        if dominant in tracked_walls:
            tracked_walls[dominant]["tests"] += 1
            if held or (breached and recovered):
                tracked_walls[dominant]["holds"] += 1
            elif breached and not recovered:
                if not tracked_walls[dominant]["cascade"]:
                    tracked_walls[dominant]["cascade"] = True
                    tracked_walls[dominant]["cascade_date"] = date

        # Determine energy at this strike
        energy_at_strike = 0
        for wall in day.get("walls", []):
            if wall["strike"] == dominant:
                energy_at_strike = wall["energy"]
                break

        result = "HELD" if held else ("RECOVERED" if recovered else "CASCADE")

        wall_tests.append({
            "date": date,
            "close": price,
            "high": high,
            "wall": dominant,
            "approach_pct": round(approach, 2),
            "breached": breached,
            "result": result,
            "energy": energy_at_strike,
            "days_to_peak": day["days_to_peak"],
        })

    # Display
    print(f"\n  {'Date':<12} {'Close':>8} {'Wall':>8} {'Approach':>10} {'Result':>12} {'Energy':>10}")
    print("  " + "-" * 64)

    hold_energies = []
    cascade_energies = []
    for wt in wall_tests:
        flag = "🟢" if wt["result"] == "HELD" else ("🔵" if wt["result"] == "RECOVERED" else "🔴")
        print(f"  {wt['date']:<12} ${wt['close']:>7.2f} ${wt['wall']:>6.0f} "
              f"{wt['approach_pct']:>8.2f}% {flag} {wt['result']:<10} {wt['energy']:>10,}")

        if wt["result"] == "HELD" or wt["result"] == "RECOVERED":
            hold_energies.append(wt["energy"])
        elif wt["result"] == "CASCADE":
            cascade_energies.append(wt["energy"])

    # Summary stats
    n_tests = len(wall_tests)
    n_held = sum(1 for w in wall_tests if w["result"] in ("HELD", "RECOVERED"))
    n_cascade = sum(1 for w in wall_tests if w["result"] == "CASCADE")

    print(f"\n  Total wall tests: {n_tests}")
    print(f"  Held/Recovered: {n_held} ({n_held/max(n_tests,1)*100:.0f}%)")
    print(f"  Cascades: {n_cascade} ({n_cascade/max(n_tests,1)*100:.0f}%)")

    if hold_energies and cascade_energies:
        hold_avg = np.mean(hold_energies)
        cascade_avg = np.mean(cascade_energies)
        ratio = cascade_avg / max(hold_avg, 1)
        print(f"\n  Energy at hold events: {hold_avg:,.0f} (avg)")
        print(f"  Energy at cascade events: {cascade_avg:,.0f} (avg)")
        print(f"  Cascade/Hold energy ratio: {ratio:.2f}×")
    else:
        ratio = None

    # Wall fatigue pattern: track sequential tests of the same wall
    fatigue_events = []
    for strike, info in tracked_walls.items():
        if info["tests"] >= 2:
            fatigue_events.append({
                "strike": strike,
                "first_seen": info["first_seen"],
                "total_tests": info["tests"],
                "holds_before_cascade": info["holds"],
                "cascade": info["cascade"],
                "cascade_date": info["cascade_date"],
            })

    if fatigue_events:
        print(f"\n  WALL FATIGUE EVENTS (walls tested ≥2 times):")
        print(f"  {'Strike':>8} {'First Seen':<12} {'Tests':>6} {'Holds':>6} {'Cascade?':>10}")
        print("  " + "-" * 48)
        for fe in sorted(fatigue_events, key=lambda x: x["strike"]):
            casc = f"YES ({fe['cascade_date']})" if fe["cascade"] else "No"
            print(f"  ${fe['strike']:>7.0f} {fe['first_seen']:<12} {fe['total_tests']:>6} "
                  f"{fe['holds_before_cascade']:>6} {casc:>10}")

    return {
        "ticker": ticker,
        "peak_date": peak_date,
        "n_trading_days": len(daily_data),
        "n_wall_tests": n_tests,
        "n_held": n_held,
        "n_cascade": n_cascade,
        "cascade_rate": round(n_cascade / max(n_tests, 1), 4),
        "energy_ratio": round(ratio, 2) if ratio else None,
        "wall_tests": wall_tests,
        "fatigue_events": fatigue_events,
    }


def cross_event_comparison(results):
    """Compare wall fatigue patterns across events."""
    print(f"\n\n{'='*70}")
    print(f"  CROSS-EVENT WALL FATIGUE COMPARISON")
    print(f"{'='*70}")

    print(f"\n  {'Ticker':<8} {'Peak':<12} {'Tests':>6} {'Held':>6} {'Cascade':>8} "
          f"{'Rate':>8} {'Energy Ratio':>14}")
    print("  " + "-" * 68)

    for r in results:
        if r is None:
            continue
        er = f"{r['energy_ratio']:.2f}×" if r["energy_ratio"] else "N/A"
        print(f"  {r['ticker']:<8} {r['peak_date']:<12} {r['n_wall_tests']:>6} "
              f"{r['n_held']:>6} {r['n_cascade']:>8} {r['cascade_rate']:>7.0%} {er:>14}")

    # Test: do cascade rates correlate across events?
    cascade_rates = [r["cascade_rate"] for r in results if r is not None]
    if len(cascade_rates) >= 2:
        print(f"\n  Cascade rates across events: {[f'{cr:.1%}' for cr in cascade_rates]}")
        print(f"  Mean cascade rate: {np.mean(cascade_rates):.1%}")

    # Check for fatigue pattern: do cascades occur after multiple holds?
    holds_before_cascade = []
    for r in results:
        if r is None:
            continue
        for fe in r["fatigue_events"]:
            if fe["cascade"]:
                holds_before_cascade.append(fe["holds_before_cascade"])

    if holds_before_cascade:
        print(f"\n  Holds before cascade (fatigue pattern):")
        print(f"    Events: {holds_before_cascade}")
        print(f"    Mean holds before cascade: {np.mean(holds_before_cascade):.1f}")
        print(f"    Pattern: walls hold {np.mean(holds_before_cascade):.0f}× on avg before cascading")

    return {
        "n_events": len([r for r in results if r is not None]),
        "cascade_rates": cascade_rates,
        "mean_cascade_rate": round(np.mean(cascade_rates), 4) if cascade_rates else None,
        "holds_before_cascade": holds_before_cascade,
    }


def main():
    results = []
    for event in EVENTS:
        result = analyze_wall_fatigue(
            event["ticker"], event["peak_date"],
            event["window_before"], event["window_after"])
        results.append(result)

    comparison = cross_event_comparison(results)

    # Save
    output = {
        "analysis": "multi_event_wall_fatigue",
        "events": [r for r in results if r is not None],
        "comparison": comparison,
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
    }

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"multi_event_wall_fatigue_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved to: {out_path.name}")


if __name__ == "__main__":
    main()
