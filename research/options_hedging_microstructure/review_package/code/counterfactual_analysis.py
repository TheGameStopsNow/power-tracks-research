#!/usr/bin/env python3
"""
Counterfactual Analysis: GME Squeeze vs Non-Squeeze Base Rates
==============================================================
Runs the same squeeze mechanics analyses on GME during non-squeeze
periods to establish the base rate of:
  - Wall failures (how often do walls break without cascades?)
  - Dealer delta ranges (what's normal dealer delta behavior?)
  - Pin distance distributions (how does normal magnetism look?)

Usage:
    python counterfactual_analysis.py
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

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

TICKER = "GME"

# Import vectorized BS functions
from squeeze_mechanics_forensic import (
    _batch_iv_from_price, _bs_delta_vec, _approx_delta,
    get_dates, get_equity_close, get_equity_ohlc
)


def analyze_period(period_name, center_date, window_before=90, window_after=20):
    """
    Run wall failure + dealer delta + magnetism analysis on a given period.
    """
    print(f"\n{'='*70}")
    print(f"  ANALYZING: {period_name}")
    print(f"  Center date: {center_date}, Window: -{window_before}d to +{window_after}d")
    print(f"{'='*70}")

    center_dt = pd.Timestamp(center_date)
    start_dt = center_dt - timedelta(days=window_before)
    end_dt = center_dt + timedelta(days=window_after)

    opts_dates = get_dates(TICKER, "options")
    eq_dates = get_dates(TICKER, "equity")

    # Build date windows
    opts_set = set()
    window_dates = []
    for d in opts_dates:
        ds = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if "-" not in d else d
        dt = pd.Timestamp(ds)
        if start_dt <= dt <= end_dt:
            window_dates.append(ds)
        opts_set.add(ds.replace("-", ""))

    eq_window = []
    for d in eq_dates:
        ds = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if "-" not in d else d
        dt = pd.Timestamp(ds)
        if start_dt <= dt <= end_dt:
            eq_window.append(ds)

    print(f"  Options days: {len(window_dates)}, Equity days: {len(eq_window)}")

    # =========================================================================
    # A) WALL FAILURE ANALYSIS
    # =========================================================================
    print(f"\n  --- Wall Failure Analysis ---")

    daily_data = []
    for i, date_str in enumerate(eq_window):
        ohlc = get_equity_ohlc(TICKER, date_str)
        if not ohlc:
            continue

        date_key = date_str.replace("-", "")
        call_vol = defaultdict(int)

        if date_key in opts_set:
            try:
                opts = _load_options_day(TICKER, date_str)
                if not opts.empty:
                    # Vectorized groupby instead of iterrows
                    calls = opts[opts["right"].isin(["C", "c"])]
                    if not calls.empty:
                        cv = calls.groupby("strike")["size"].sum()
                        for s, v in cv.items():
                            call_vol[float(s)] = int(v)
            except Exception:
                pass

        price = ohlc["close"]
        walls_above = []
        for strike, vol in sorted(call_vol.items()):
            if strike > price and vol > 100:
                walls_above.append({"strike": strike, "call_vol": vol})
        walls_above.sort(key=lambda x: x["call_vol"], reverse=True)

        daily_data.append({
            "date": date_str, **ohlc,
            "walls": walls_above[:10],
        })

        if (i + 1) % 20 == 0:
            print(f"    {i+1}/{len(eq_window)}", end="", flush=True)

    print()

    # Wall test logic
    wall_tests = []
    for i in range(1, len(daily_data)):
        day = daily_data[i]
        prev = daily_data[i - 1]
        price = day["close"]
        high = day["high"]

        dominant_wall = None
        dominant_vol = 0
        for wall in prev.get("walls", []):
            if wall["call_vol"] > dominant_vol and wall["strike"] > prev["close"]:
                dominant_wall = wall["strike"]
                dominant_vol = wall["call_vol"]

        if dominant_wall is None:
            continue

        approach_pct = (dominant_wall - prev["close"]) / prev["close"] * 100
        if approach_pct > 15:
            continue

        breached = high >= dominant_wall
        held = price < dominant_wall

        recovered = False
        if i + 1 < len(daily_data) and breached and not held:
            next_close = daily_data[i + 1]["close"]
            recovered = next_close < dominant_wall

        wall_tests.append({
            "date": day["date"],
            "close": price,
            "wall": dominant_wall,
            "approach_pct": round(approach_pct, 2),
            "breached": breached,
            "held": held,
            "cascade": breached and not held and not recovered,
        })

    n_tests = len(wall_tests)
    n_breached = sum(1 for w in wall_tests if w["breached"])
    n_cascade = sum(1 for w in wall_tests if w["cascade"])
    breach_rate = n_breached / max(n_tests, 1)
    cascade_rate = n_cascade / max(n_tests, 1)

    print(f"  Wall tests: {n_tests}")
    print(f"  Breached: {n_breached} ({breach_rate*100:.1f}%)")
    print(f"  Cascades: {n_cascade} ({cascade_rate*100:.1f}%)")

    # =========================================================================
    # B) DEALER DELTA RANGE (vectorized)
    # =========================================================================
    print(f"\n  --- Dealer Delta Range ---")

    daily_delta = []
    for i, date_str in enumerate(window_dates):
        price = get_equity_close(TICKER, date_str)
        if not price:
            continue

        try:
            opts = _load_options_day(TICKER, date_str)
        except Exception:
            continue

        if opts.empty or "expiration" not in opts.columns:
            continue

        trade_dt = pd.Timestamp(date_str)
        opts = opts[opts["expiration"].notna()].copy()
        opts["dte"] = (pd.to_datetime(opts["expiration"]) - trade_dt).dt.days
        opts = opts[opts["dte"] >= 0]

        if opts.empty:
            continue

        strikes = opts["strike"].values.astype(float)
        rights = opts["right"].values
        volumes = opts["size"].values.astype(int)
        opt_prices = opts["price"].values.astype(float) if "price" in opts.columns else np.zeros(len(opts))
        dte_days = opts["dte"].values.astype(float)
        T = np.maximum(dte_days / 365.0, 0.001)
        is_call = np.array([r in ("C", "c") for r in rights])

        ivs = _batch_iv_from_price(opt_prices, price, strikes, T, is_call)
        bs_deltas = _bs_delta_vec(price, strikes, T, ivs, is_call)
        delta_shares = bs_deltas * volumes * 100

        total_call = float(np.sum(delta_shares[is_call]))
        total_put = float(np.sum(delta_shares[~is_call]))
        dealer_delta = -(total_call + total_put)

        daily_delta.append({
            "date": date_str,
            "price": price,
            "dealer_delta": round(dealer_delta),
        })

        if (i + 1) % 20 == 0:
            print(f"    {i+1}/{len(window_dates)}", end="", flush=True)

    print()

    deltas = [d["dealer_delta"] for d in daily_delta]
    if deltas:
        delta_mean = np.mean(deltas)
        delta_std = np.std(deltas)
        delta_max = max(deltas)
        delta_min = min(deltas)
        delta_abs_max = max(abs(d) for d in deltas)
        sign_changes = sum(1 for i in range(1, len(deltas)) if deltas[i] * deltas[i-1] < 0)
        print(f"  Dealer delta range: {delta_min:+,.0f} to {delta_max:+,.0f}")
        print(f"  Mean: {delta_mean:+,.0f}, Std: {delta_std:,.0f}")
        print(f"  Max |delta|: {delta_abs_max:,}")
        print(f"  Sign changes: {sign_changes}")
    else:
        delta_mean = delta_std = delta_max = delta_min = delta_abs_max = 0
        sign_changes = 0

    # =========================================================================
    # C) PIN DISTANCE DISTRIBUTION (vectorized)
    # =========================================================================
    print(f"\n  --- Pin Distance Distribution ---")

    pin_distances = []
    for i, date_str in enumerate(window_dates):
        price = get_equity_close(TICKER, date_str)
        if not price:
            continue

        try:
            opts = _load_options_day(TICKER, date_str)
        except Exception:
            continue

        if opts.empty:
            continue

        # Vectorized groupby
        sv = opts.groupby("strike")["size"].sum()
        if sv.empty:
            continue

        top_strike = float(sv.idxmax())
        pin_dist = abs(price - top_strike) / price * 100
        pin_distances.append({
            "date": date_str,
            "price": price,
            "top_strike": top_strike,
            "pin_distance_pct": round(pin_dist, 2),
        })

    if pin_distances:
        pins = [p["pin_distance_pct"] for p in pin_distances]
        pin_mean = np.mean(pins)
        pin_median = np.median(pins)
        pin_std = np.std(pins)
        pin_pct90 = np.percentile(pins, 90)
        print(f"  Mean pin distance: {pin_mean:.2f}%")
        print(f"  Median: {pin_median:.2f}%, Std: {pin_std:.2f}%")
        print(f"  90th percentile: {pin_pct90:.2f}%")
    else:
        pin_mean = pin_median = pin_std = pin_pct90 = 0

    return {
        "period": period_name,
        "center_date": center_date,
        "n_trading_days": len(eq_window),
        "wall_analysis": {
            "n_tests": n_tests,
            "n_breached": n_breached,
            "n_cascade": n_cascade,
            "breach_rate": round(breach_rate, 4),
            "cascade_rate": round(cascade_rate, 4),
        },
        "delta_analysis": {
            "mean": round(delta_mean),
            "std": round(delta_std),
            "max": round(float(delta_max)),
            "min": round(float(delta_min)),
            "abs_max": round(float(delta_abs_max)),
            "sign_changes": sign_changes,
        },
        "pin_analysis": {
            "mean": round(pin_mean, 2),
            "median": round(pin_median, 2),
            "std": round(pin_std, 2),
            "pct90": round(pin_pct90, 2),
        },
    }


def statistical_comparison(squeeze_result, counterfactual_results):
    """Compare squeeze period metrics vs counterfactual periods."""
    print(f"\n\n{'='*70}")
    print(f"  STATISTICAL COMPARISON: SQUEEZE VS COUNTERFACTUAL")
    print(f"{'='*70}")

    cf_breach_rates = [r["wall_analysis"]["breach_rate"] for r in counterfactual_results]
    cf_cascade_rates = [r["wall_analysis"]["cascade_rate"] for r in counterfactual_results]
    cf_pin_means = [r["pin_analysis"]["mean"] for r in counterfactual_results]
    cf_delta_abs_maxes = [r["delta_analysis"]["abs_max"] for r in counterfactual_results]

    sq_breach = squeeze_result["wall_analysis"]["breach_rate"]
    sq_cascade = squeeze_result["wall_analysis"]["cascade_rate"]
    sq_pin = squeeze_result["pin_analysis"]["mean"]
    sq_delta = squeeze_result["delta_analysis"]["abs_max"]

    print(f"\n  {'Metric':<30} {'Squeeze':>12} {'CF Mean':>12} {'CF Std':>10} {'Z-Score':>10}")
    print("  " + "-" * 78)

    results = {}

    # Wall breach rate
    cf_mean = np.mean(cf_breach_rates)
    cf_std = np.std(cf_breach_rates) if len(cf_breach_rates) > 1 else 0.01
    z = (sq_breach - cf_mean) / max(cf_std, 0.001)
    print(f"  {'Wall Breach Rate':<30} {sq_breach:>11.1%} {cf_mean:>11.1%} {cf_std:>9.1%} {z:>10.2f}")
    results["breach_z"] = round(z, 2)

    # Cascade rate
    cf_mean = np.mean(cf_cascade_rates)
    cf_std = np.std(cf_cascade_rates) if len(cf_cascade_rates) > 1 else 0.01
    z = (sq_cascade - cf_mean) / max(cf_std, 0.001)
    print(f"  {'Cascade Rate':<30} {sq_cascade:>11.1%} {cf_mean:>11.1%} {cf_std:>9.1%} {z:>10.2f}")
    results["cascade_z"] = round(z, 2)

    # Pin distance
    cf_mean = np.mean(cf_pin_means)
    cf_std = np.std(cf_pin_means) if len(cf_pin_means) > 1 else 0.01
    z = (sq_pin - cf_mean) / max(cf_std, 0.001)
    print(f"  {'Mean Pin Distance %':<30} {sq_pin:>11.2f}% {cf_mean:>10.2f}% {cf_std:>8.2f}% {z:>10.2f}")
    results["pin_z"] = round(z, 2)

    # Max |dealer delta|
    cf_mean = np.mean(cf_delta_abs_maxes)
    cf_std = np.std(cf_delta_abs_maxes) if len(cf_delta_abs_maxes) > 1 else 1
    z = (sq_delta - cf_mean) / max(cf_std, 1)
    print(f"  {'Max |Dealer Δ|':<30} {sq_delta:>12,} {cf_mean:>12,.0f} {cf_std:>10,.0f} {z:>10.2f}")
    results["delta_z"] = round(z, 2)

    # Fisher exact test
    sq_tests = squeeze_result["wall_analysis"]["n_tests"]
    sq_casc = squeeze_result["wall_analysis"]["n_cascade"]
    cf_tests = sum(r["wall_analysis"]["n_tests"] for r in counterfactual_results)
    cf_casc = sum(r["wall_analysis"]["n_cascade"] for r in counterfactual_results)

    fisher_p = None
    if sq_tests > 0 and cf_tests > 0:
        table = [[sq_casc, sq_tests - sq_casc],
                 [cf_casc, cf_tests - cf_casc]]
        odds_ratio, fisher_p = stats.fisher_exact(table)
        print(f"\n  Fisher Exact Test (cascade rates):")
        print(f"    Squeeze: {sq_casc}/{sq_tests} cascades")
        print(f"    Counterfactual: {cf_casc}/{cf_tests} cascades")
        print(f"    Odds ratio: {odds_ratio:.2f}, p-value: {fisher_p:.6f}")
        results["fisher_p"] = round(fisher_p, 6)

    return results


def main():
    periods = [
        ("GME Squeeze (Jan 2021)", "2021-01-28", 90, 20),
        ("GME Calm 2022 Q1", "2022-03-15", 90, 20),
        ("GME Calm 2023 Q1", "2023-03-15", 90, 20),
        ("GME Calm 2024 Q1", "2024-03-15", 90, 20),
    ]

    results = []
    for name, center, before, after in periods:
        result = analyze_period(name, center, before, after)
        results.append(result)

    squeeze_result = results[0]
    counterfactual_results = results[1:]

    comparison = statistical_comparison(squeeze_result, counterfactual_results)

    output = {
        "analysis": "counterfactual",
        "ticker": TICKER,
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "periods": [{
            "name": r["period"],
            "center_date": r["center_date"],
            "n_days": r["n_trading_days"],
            "wall_breach_rate": r["wall_analysis"]["breach_rate"],
            "wall_cascade_rate": r["wall_analysis"]["cascade_rate"],
            "delta_abs_max": r["delta_analysis"]["abs_max"],
            "pin_mean": r["pin_analysis"]["mean"],
        } for r in results],
        "comparison": comparison,
    }

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"counterfactual_GME_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved to: {out_path.name}")


if __name__ == "__main__":
    main()
