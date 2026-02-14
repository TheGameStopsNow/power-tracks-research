#!/usr/bin/env python3
"""
Stacking Resonance Test: Constructive Expiration Interference
==============================================================
Tests whether options bought at different times targeting the SAME expiration
date create super-linear amplification (constructive interference) versus
linearly accumulated positions.

Core idea: invert the analysis anchor from "trade date" → "target expiration".
For each major expiration, measure the temporal variance of origination (how
stacked the buildup is) and compare final-month equity microstructure behavior.

Tests:
  1. Stacking Density — origination variance per expiration
  2. Amplification — Fragility Ratio & ACF in high vs low stacking cohorts
  3. Forward Wrinkles — periodic RV bumps before expiration (Vanna/Charm waves)
  4. Dispersion Buying — new positions opening when nearby expirations die

Usage:
    python stacking_resonance_test.py --ticker GME
    python stacking_resonance_test.py --ticker TSLA --max-days 500
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
# Infrastructure imports
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "phase98_cluster_bridge"))

from panel_scan import POLYGON_DIR, compute_daily_acf
try:
    from temporal_convolution_engine import load_equity_day
except ImportError:
    from panel_scan import load_equity_day  # type: ignore

from phase5_paradigm import _load_options_day

THETA_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw" / "thetadata" / "trades"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ===========================================================================
# Step 1: Build Expiration-Anchored Volume Map
# ===========================================================================

def get_options_dates(ticker: str) -> list[str]:
    """List all cached options trade dates (YYYYMMDD)."""
    opts_dir = THETA_ROOT / f"root={ticker}"
    if not opts_dir.exists():
        return []
    return sorted(d.name.replace("date=", "") for d in opts_dir.iterdir() if d.is_dir())


def build_expiration_map(ticker: str, max_days: int = 0) -> dict:
    """
    Build a map: expiration_date → list of (trade_date, dte_at_trade, volume, contracts)

    This inverts the perspective from "what traded today?" to
    "when was the buildup for this expiration assembled?"
    """
    dates = get_options_dates(ticker)
    if max_days > 0:
        dates = dates[-max_days:]

    exp_map = defaultdict(list)
    total_dates = len(dates)

    print(f"  [{ticker}] Scanning {total_dates} trade dates for expiration map...", end="", flush=True)

    for i, date_str in enumerate(dates):
        trade_date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        try:
            opts = _load_options_day(ticker, trade_date_str)
        except (FileNotFoundError, Exception):
            continue

        if opts.empty or "expiration" not in opts.columns:
            continue

        trade_date = pd.Timestamp(trade_date_str)

        # Group by expiration date
        for exp_str, grp in opts.groupby("expiration"):
            exp_date = pd.Timestamp(exp_str)
            dte = (exp_date - trade_date).days
            if dte < 0:
                continue  # skip expired

            total_contracts = int(grp["size"].sum())
            n_trades = len(grp)

            exp_map[exp_str].append({
                "trade_date": trade_date_str,
                "dte_at_trade": dte,
                "contracts": total_contracts,
                "n_trades": n_trades,
            })

        if (i + 1) % 100 == 0:
            print(f" {i+1}", end="", flush=True)

    print(f" → {len(exp_map)} expirations mapped")
    return dict(exp_map)


# ===========================================================================
# Step 2: Stacking Density Score
# ===========================================================================

def compute_stacking_density(exp_map: dict, min_total_contracts: int = 1000) -> pd.DataFrame:
    """
    For each expiration, compute:
    - total_contracts: sum across all origination dates
    - n_origination_dates: how many distinct trade dates contributed
    - origination_span: DTE range (max_dte - min_dte for originations)
    - stacking_density: volume-weighted std of origination DTE
    - stacking_score: normalized density (higher = more stacked from varied origins)
    - n_tranches: count of distinct DTE clusters (via a simple gap-based grouping)
    """
    rows = []
    for exp_str, trades in exp_map.items():
        total_contracts = sum(t["contracts"] for t in trades)
        if total_contracts < min_total_contracts:
            continue

        dtes = np.array([t["dte_at_trade"] for t in trades])
        volumes = np.array([t["contracts"] for t in trades])
        n_dates = len(trades)

        # Volume-weighted mean and std of origination DTE
        w_mean_dte = np.average(dtes, weights=volumes)
        w_var_dte = np.average((dtes - w_mean_dte) ** 2, weights=volumes)
        w_std_dte = np.sqrt(w_var_dte)

        # Origination span
        span = int(dtes.max() - dtes.min())

        # Count distinct DTE "tranches" (clusters ≥ 30 days apart)
        sorted_dtes = np.sort(np.unique(dtes))[::-1]  # descending
        tranches = 1
        for j in range(1, len(sorted_dtes)):
            if sorted_dtes[j - 1] - sorted_dtes[j] > 30:
                tranches += 1

        # Energy concentration: volume from distant origins (DTE > 60 at trade)
        far_volume = sum(t["contracts"] for t in trades if t["dte_at_trade"] > 60)
        near_volume = sum(t["contracts"] for t in trades if t["dte_at_trade"] <= 30)
        far_ratio = far_volume / total_contracts if total_contracts > 0 else 0.0

        rows.append({
            "expiration": exp_str,
            "total_contracts": total_contracts,
            "n_origination_dates": n_dates,
            "origination_span_days": span,
            "stacking_density": round(w_std_dte, 2),
            "mean_origination_dte": round(w_mean_dte, 1),
            "n_tranches": tranches,
            "far_volume_ratio": round(far_ratio, 3),
            "near_volume": near_volume,
            "far_volume": far_volume,
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["expiration_dt"] = pd.to_datetime(df["expiration"])
    df = df.sort_values("expiration_dt").reset_index(drop=True)

    # Normalize stacking score within population
    if df["stacking_density"].std() > 0:
        df["stacking_zscore"] = (
            (df["stacking_density"] - df["stacking_density"].mean())
            / df["stacking_density"].std()
        )
    else:
        df["stacking_zscore"] = 0.0

    return df


# ===========================================================================
# Step 3: Amplification Test — Compare High vs Low Stacking Cohorts
# ===========================================================================

def compute_expiration_window_metrics(
    ticker: str, exp_date: str, window_days: int = 30
) -> dict | None:
    """
    Compute equity microstructure metrics in the final N days before an expiration.
    Returns ACF, RV, and volume stats for the window.
    """
    exp_dt = pd.Timestamp(exp_date)
    start_dt = exp_dt - timedelta(days=window_days + 10)  # buffer for weekends

    # Collect equity dates in window
    eq_dates = []
    for fmt in [f"symbol={ticker}", f"symbol={ticker.upper()}"]:
        sym_path = POLYGON_DIR / fmt
        if sym_path.exists():
            for d in sym_path.glob("date=*"):
                date_str = d.name.split("=")[1]
                dt = pd.Timestamp(date_str)
                if start_dt <= dt <= exp_dt:
                    eq_dates.append(date_str)
    eq_dates = sorted(eq_dates)[-window_days:]

    if len(eq_dates) < 10:
        return None

    acf_values = []
    rv_values = []
    vol_values = []

    for date_str in eq_dates:
        eq = load_equity_day(ticker, date_str)
        if eq.empty or len(eq) < 100:
            continue

        # ACF
        acf = compute_daily_acf(eq["price"], eq["ts"], interval_sec=60.0, max_lag=5)
        if not np.isnan(acf[0]):
            acf_values.append(acf[0])

        # RV
        df_bars = pd.DataFrame({"ts": eq["ts"], "price": eq["price"]}).set_index("ts")
        bars = df_bars.resample("60s").last().dropna()
        rets = bars["price"].pct_change().dropna().values
        if len(rets) > 20:
            rv = float(np.sum(rets ** 2))
            rv_values.append(rv)

        # Volume
        vol = float(eq["size"].sum()) if "size" in eq.columns else float(len(eq))
        vol_values.append(vol)

    if len(acf_values) < 5:
        return None

    return {
        "n_days": len(acf_values),
        "mean_acf1": float(np.mean(acf_values)),
        "std_acf1": float(np.std(acf_values)),
        "pct_amplified": float(np.mean(np.array(acf_values) > 0)) * 100,
        "mean_rv": float(np.mean(rv_values)) if rv_values else None,
        "std_rv": float(np.std(rv_values)) if rv_values else None,
        "mean_volume": float(np.mean(vol_values)) if vol_values else None,
    }


def run_amplification_test(
    ticker: str, density_df: pd.DataFrame, n_cohort: int = 15
) -> dict:
    """
    Compare microstructure metrics between high-stacking and low-stacking
    expiration cohorts in the final 30 days before each expiration.
    """
    if len(density_df) < n_cohort * 2:
        n_cohort = max(5, len(density_df) // 3)

    # Sort by stacking density
    sorted_df = density_df.sort_values("stacking_density", ascending=False)
    high_stack = sorted_df.head(n_cohort)
    low_stack = sorted_df.tail(n_cohort)

    def measure_cohort(cohort, label):
        results = []
        for _, row in cohort.iterrows():
            print(f"    {label}: measuring exp={row['expiration']}...", end="", flush=True)
            metrics = compute_expiration_window_metrics(ticker, row["expiration"])
            if metrics:
                metrics["expiration"] = row["expiration"]
                metrics["stacking_density"] = row["stacking_density"]
                metrics["total_contracts"] = row["total_contracts"]
                metrics["n_tranches"] = row["n_tranches"]
                results.append(metrics)
                print(f" ACF={metrics['mean_acf1']:+.4f} RV={metrics['mean_rv']:.6f}" if metrics['mean_rv'] else " ACF={metrics['mean_acf1']:+.4f}")
            else:
                print(" SKIP (insufficient equity data)")
        return results

    print(f"\n  Measuring HIGH-stacking cohort ({n_cohort} expirations)...")
    high_results = measure_cohort(high_stack, "HIGH")

    print(f"\n  Measuring LOW-stacking cohort ({n_cohort} expirations)...")
    low_results = measure_cohort(low_stack, "LOW")

    if not high_results or not low_results:
        return {"status": "INSUFFICIENT_DATA"}

    # Compare cohorts
    high_acf = [r["mean_acf1"] for r in high_results]
    low_acf = [r["mean_acf1"] for r in low_results]
    high_rv = [r["mean_rv"] for r in high_results if r["mean_rv"] is not None]
    low_rv = [r["mean_rv"] for r in low_results if r["mean_rv"] is not None]
    high_amp = [r["pct_amplified"] for r in high_results]
    low_amp = [r["pct_amplified"] for r in low_results]

    # T-test approximation (Welch's)
    def welch_t(a, b):
        a, b = np.array(a), np.array(b)
        n_a, n_b = len(a), len(b)
        if n_a < 2 or n_b < 2:
            return 0.0, 1.0
        var_a, var_b = np.var(a, ddof=1), np.var(b, ddof=1)
        se = np.sqrt(var_a / n_a + var_b / n_b)
        if se < 1e-12:
            return 0.0, 1.0
        t = (np.mean(a) - np.mean(b)) / se
        # Approximate p-value (two-tailed, normal approximation)
        from scipy import stats
        df_denom = (var_a / n_a + var_b / n_b) ** 2 / (
            (var_a / n_a) ** 2 / (n_a - 1) + (var_b / n_b) ** 2 / (n_b - 1)
        )
        p = 2 * stats.t.sf(abs(t), df=max(1, df_denom))
        return float(t), float(p)

    t_acf, p_acf = welch_t(high_acf, low_acf)
    t_rv, p_rv = welch_t(high_rv, low_rv) if high_rv and low_rv else (0, 1)

    return {
        "status": "OK",
        "n_high": len(high_results),
        "n_low": len(low_results),
        "high_stack": {
            "mean_acf1": round(float(np.mean(high_acf)), 4),
            "std_acf1": round(float(np.std(high_acf)), 4),
            "mean_pct_amplified": round(float(np.mean(high_amp)), 1),
            "mean_rv": round(float(np.mean(high_rv)), 8) if high_rv else None,
            "mean_density": round(float(high_stack["stacking_density"].mean()), 2),
            "mean_tranches": round(float(high_stack["n_tranches"].mean()), 1),
        },
        "low_stack": {
            "mean_acf1": round(float(np.mean(low_acf)), 4),
            "std_acf1": round(float(np.std(low_acf)), 4),
            "mean_pct_amplified": round(float(np.mean(low_amp)), 1),
            "mean_rv": round(float(np.mean(low_rv)), 8) if low_rv else None,
            "mean_density": round(float(low_stack["stacking_density"].mean()), 2),
            "mean_tranches": round(float(low_stack["n_tranches"].mean()), 1),
        },
        "delta": {
            "acf1_diff": round(float(np.mean(high_acf)) - float(np.mean(low_acf)), 4),
            "rv_ratio": round(float(np.mean(high_rv)) / float(np.mean(low_rv)), 3) if high_rv and low_rv and np.mean(low_rv) > 0 else None,
            "amplified_diff": round(float(np.mean(high_amp)) - float(np.mean(low_amp)), 1),
        },
        "statistics": {
            "t_acf": round(t_acf, 3),
            "p_acf": round(p_acf, 4),
            "t_rv": round(t_rv, 3),
            "p_rv": round(p_rv, 4),
        },
    }


# ===========================================================================
# Step 4: Forward Wrinkle Detection
# ===========================================================================

def detect_forward_wrinkles(
    ticker: str, exp_date: str, lookback_days: int = 90
) -> dict | None:
    """
    Look for periodic RV bumps in the equity tape leading up to an expiration.
    These "wrinkles" would be evidence of Vanna/Charm-driven hedge adjustments
    propagating forward through time.
    """
    exp_dt = pd.Timestamp(exp_date)
    start_dt = exp_dt - timedelta(days=lookback_days + 10)

    # Collect equity dates
    eq_dates = []
    for prefix in [f"symbol={ticker}", f"symbol={ticker.upper()}"]:
        sym_path = POLYGON_DIR / prefix
        if sym_path.exists():
            for d in sym_path.glob("date=*"):
                date_str = d.name.split("=")[1]
                dt = pd.Timestamp(date_str)
                if start_dt <= dt <= exp_dt:
                    eq_dates.append(date_str)
    eq_dates = sorted(eq_dates)

    if len(eq_dates) < 30:
        return None

    # Compute daily RV
    rv_series = []
    date_series = []
    for date_str in eq_dates:
        eq = load_equity_day(ticker, date_str)
        if eq.empty or len(eq) < 100:
            continue
        df_bars = pd.DataFrame({"ts": eq["ts"], "price": eq["price"]}).set_index("ts")
        bars = df_bars.resample("60s").last().dropna()
        rets = bars["price"].pct_change().dropna().values
        if len(rets) > 20:
            rv = float(np.sum(rets ** 2))
            rv_series.append(rv)
            date_series.append(pd.Timestamp(date_str))

    if len(rv_series) < 20:
        return None

    rv_arr = np.array(rv_series)
    dates_arr = np.array(date_series)

    # DTE for each measurement
    dte_arr = np.array([(exp_dt - d).days for d in dates_arr])

    # Detrend: remove linear trend
    from numpy.polynomial import polynomial as P
    coeffs = P.polyfit(dte_arr, rv_arr, deg=1)
    trend = P.polyval(dte_arr, coeffs)
    detrended = rv_arr - trend

    # Look for periodicity using FFT
    n = len(detrended)
    if n < 10:
        return None

    fft = np.fft.rfft(detrended)
    power = np.abs(fft) ** 2
    freqs = np.fft.rfftfreq(n, d=1.0)  # 1 sample per trading day

    # Skip DC component
    if len(power) < 3:
        return None
    power[0] = 0  # remove DC

    # Find dominant frequency
    peak_idx = np.argmax(power[1:]) + 1
    peak_freq = freqs[peak_idx]
    peak_period = 1.0 / peak_freq if peak_freq > 0 else float("inf")
    peak_power = power[peak_idx]
    total_power = power[1:].sum()
    peak_power_ratio = peak_power / total_power if total_power > 0 else 0.0

    # Check if peak period matches Charm decay milestones
    # T-90, T-60, T-30, T-14, T-7 → periods of ~30, 23, 16, 7 trading days
    charm_periods = [30, 23, 16, 7, 5]
    closest_charm = min(charm_periods, key=lambda p: abs(p - peak_period))
    charm_match = abs(peak_period - closest_charm) / closest_charm < 0.25  # within 25%

    # RV ratio: final 5 days vs days 30-60
    if len(rv_arr) > 30:
        final_rv = np.mean(rv_arr[-5:])
        mid_rv = np.mean(rv_arr[:min(30, len(rv_arr))])
        rv_acceleration = final_rv / mid_rv if mid_rv > 0 else 1.0
    else:
        rv_acceleration = None

    return {
        "n_days": n,
        "peak_period_days": round(peak_period, 1),
        "peak_power_ratio": round(peak_power_ratio, 3),
        "closest_charm_period": closest_charm,
        "charm_match": charm_match,
        "rv_acceleration_ratio": round(rv_acceleration, 3) if rv_acceleration else None,
        "mean_rv": round(float(np.mean(rv_arr)), 8),
        "final_5d_rv": round(float(np.mean(rv_arr[-5:])), 8),
    }


# ===========================================================================
# Step 5: Dispersion Buying Detection
# ===========================================================================

def detect_dispersion_buying(exp_map: dict) -> list[dict]:
    """
    Check if new options positions open at dates when nearby expirations are
    dying (dispersing their energy). This tests the idea that traders buy into
    the "energy vacuum" left by expiring contracts.
    """
    exps = sorted(exp_map.keys())
    dispersion_events = []

    for i, exp in enumerate(exps):
        exp_dt = pd.Timestamp(exp)
        trades = exp_map[exp]

        # Find the earliest big origination (>10% of total volume)
        total_vol = sum(t["contracts"] for t in trades)
        if total_vol < 500:
            continue

        # Was there significant buying on the day a nearby expiration expired?
        for t in trades:
            trade_dt = pd.Timestamp(t["trade_date"])

            # Check if another expiration expired within ±3 days of this trade
            for other_exp in exps:
                if other_exp == exp:
                    continue
                other_dt = pd.Timestamp(other_exp)
                gap = abs((trade_dt - other_dt).days)
                if gap <= 3 and t["dte_at_trade"] > 7:
                    # This trade happened right as another expiration expired
                    # and it's not just a same-week roll
                    pct_of_total = t["contracts"] / total_vol * 100
                    if pct_of_total > 2:  # at least 2% of the buildup
                        dispersion_events.append({
                            "target_exp": exp,
                            "trade_date": t["trade_date"],
                            "dying_exp": other_exp,
                            "gap_days": gap,
                            "dte_at_trade": t["dte_at_trade"],
                            "contracts": t["contracts"],
                            "pct_of_total": round(pct_of_total, 1),
                        })

    return dispersion_events


# ===========================================================================
# Orchestrator
# ===========================================================================

def run_stacking_test(ticker: str, max_days: int = 0) -> dict:
    """Run the complete stacking resonance test for one ticker."""
    print(f"\n{'='*70}")
    print(f"STACKING RESONANCE TEST — {ticker}")
    print(f"{'='*70}")

    # Step 1: Build expiration map
    exp_map = build_expiration_map(ticker, max_days)
    if not exp_map:
        return {"ticker": ticker, "status": "NO_DATA"}

    # Step 2: Compute stacking density
    print(f"\n  Computing stacking density for {len(exp_map)} expirations...")
    density_df = compute_stacking_density(exp_map, min_total_contracts=500)
    if density_df.empty:
        return {"ticker": ticker, "status": "INSUFFICIENT_EXPIRATIONS"}

    print(f"  → {len(density_df)} expirations above threshold")
    print(f"  Stacking density range: {density_df['stacking_density'].min():.1f} – {density_df['stacking_density'].max():.1f}")
    print(f"  Mean origination span: {density_df['origination_span_days'].mean():.0f} days")

    # Print top and bottom stacking
    print(f"\n  TOP-5 Highest Stacking Density:")
    for _, r in density_df.nlargest(5, "stacking_density").iterrows():
        print(f"    {r['expiration']:12s}  density={r['stacking_density']:6.1f}  "
              f"contracts={r['total_contracts']:7d}  span={r['origination_span_days']:3d}d  "
              f"tranches={r['n_tranches']}  far_ratio={r['far_volume_ratio']:.2f}")

    print(f"\n  BOTTOM-5 Lowest Stacking Density:")
    for _, r in density_df.nsmallest(5, "stacking_density").iterrows():
        print(f"    {r['expiration']:12s}  density={r['stacking_density']:6.1f}  "
              f"contracts={r['total_contracts']:7d}  span={r['origination_span_days']:3d}d  "
              f"tranches={r['n_tranches']}  far_ratio={r['far_volume_ratio']:.2f}")

    # Step 3: Amplification test
    print(f"\n{'─'*70}")
    print(f"  AMPLIFICATION TEST: High vs Low stacking cohorts")
    print(f"{'─'*70}")
    amp_results = run_amplification_test(ticker, density_df)

    if amp_results.get("status") == "OK":
        h = amp_results["high_stack"]
        l = amp_results["low_stack"]
        d = amp_results["delta"]
        s = amp_results["statistics"]

        print(f"\n  ┌─────────────────────┬──────────────┬──────────────┬──────────┐")
        print(f"  │ Metric              │ HIGH Stack   │ LOW Stack    │ Δ        │")
        print(f"  ├─────────────────────┼──────────────┼──────────────┼──────────┤")
        print(f"  │ Mean ACF₁           │ {h['mean_acf1']:+.4f}       │ {l['mean_acf1']:+.4f}       │ {d['acf1_diff']:+.4f}   │")
        print(f"  │ Std ACF₁            │ {h['std_acf1']:.4f}        │ {l['std_acf1']:.4f}        │          │")
        print(f"  │ % Amplified Days    │ {h['mean_pct_amplified']:5.1f}%       │ {l['mean_pct_amplified']:5.1f}%       │ {d['amplified_diff']:+.1f}pp  │")
        if h["mean_rv"] is not None and l["mean_rv"] is not None:
            print(f"  │ Mean RV             │ {h['mean_rv']:.2e}  │ {l['mean_rv']:.2e}  │ {d['rv_ratio']:.3f}x  │")
        print(f"  │ Mean Density         │ {h['mean_density']:6.1f}       │ {l['mean_density']:6.1f}       │          │")
        print(f"  │ Mean Tranches        │ {h['mean_tranches']:5.1f}        │ {l['mean_tranches']:5.1f}        │          │")
        print(f"  └─────────────────────┴──────────────┴──────────────┴──────────┘")
        print(f"  Statistics: ACF t={s['t_acf']:.3f} p={s['p_acf']:.4f}")
        if s["p_rv"] < 1:
            print(f"              RV  t={s['t_rv']:.3f} p={s['p_rv']:.4f}")

        # Interpret
        if d["acf1_diff"] > 0:
            print(f"\n  ⚡ HIGH stacking → LESS dampening (ACF shifted +{d['acf1_diff']:.4f})")
            print(f"      → Supports constructive interference hypothesis!")
        else:
            print(f"\n  🔵 HIGH stacking → MORE dampening (ACF shifted {d['acf1_diff']:.4f})")
            print(f"      → Stacking reinforces Long Gamma Default")

    # Step 4: Forward wrinkle detection (on top stacked expirations)
    print(f"\n{'─'*70}")
    print(f"  FORWARD WRINKLE DETECTION")
    print(f"{'─'*70}")

    top_stacked = density_df.nlargest(10, "stacking_density")
    wrinkle_results = []
    for _, row in top_stacked.iterrows():
        wrinkles = detect_forward_wrinkles(ticker, row["expiration"])
        if wrinkles:
            wrinkles["expiration"] = row["expiration"]
            wrinkles["stacking_density"] = row["stacking_density"]
            wrinkle_results.append(wrinkles)
            charm_flag = "✓ CHARM MATCH" if wrinkles["charm_match"] else ""
            print(f"    {row['expiration']:12s}  period={wrinkles['peak_period_days']:5.1f}d  "
                  f"power={wrinkles['peak_power_ratio']:.3f}  "
                  f"accel={wrinkles['rv_acceleration_ratio']:.2f}x  {charm_flag}")
        else:
            print(f"    {row['expiration']:12s}  SKIP (insufficient data)")

    if wrinkle_results:
        charm_matches = sum(1 for w in wrinkle_results if w["charm_match"])
        mean_accel = np.mean([w["rv_acceleration_ratio"] for w in wrinkle_results if w["rv_acceleration_ratio"]])
        print(f"\n  Charm-period matches: {charm_matches}/{len(wrinkle_results)}")
        print(f"  Mean RV acceleration (final 5d / mid-period): {mean_accel:.2f}x")

    # Step 5: Dispersion buying
    print(f"\n{'─'*70}")
    print(f"  DISPERSION BUYING DETECTION")
    print(f"{'─'*70}")

    disp_events = detect_dispersion_buying(exp_map)
    if disp_events:
        print(f"  Found {len(disp_events)} dispersion buying events")
        # Group by target expiration
        by_target = defaultdict(list)
        for e in disp_events:
            by_target[e["target_exp"]].append(e)

        print(f"  Unique target expirations with dispersion buying: {len(by_target)}")
        total_exps = len(density_df)
        disp_pct = len(by_target) / total_exps * 100 if total_exps > 0 else 0
        print(f"  Percentage of expirations with dispersion buying: {disp_pct:.1f}%")

        # Show top examples
        for target, events in sorted(by_target.items(), key=lambda x: -len(x[1]))[:5]:
            print(f"\n    Target: {target} ({len(events)} events)")
            for e in events[:3]:
                print(f"      Bought {e['contracts']:5d} contracts on {e['trade_date']} "
                      f"(DTE={e['dte_at_trade']}d) as {e['dying_exp']} expired "
                      f"({e['pct_of_total']:.1f}% of total)")
    else:
        print(f"  No dispersion buying events detected.")

    # Compile results
    result = {
        "ticker": ticker,
        "status": "OK",
        "n_expirations": len(density_df),
        "n_trade_dates": len(get_options_dates(ticker)),
        "density_summary": {
            "min": round(float(density_df["stacking_density"].min()), 2),
            "mean": round(float(density_df["stacking_density"].mean()), 2),
            "median": round(float(density_df["stacking_density"].median()), 2),
            "max": round(float(density_df["stacking_density"].max()), 2),
            "std": round(float(density_df["stacking_density"].std()), 2),
        },
        "amplification": amp_results,
        "wrinkles": {
            "n_tested": len(wrinkle_results),
            "charm_matches": sum(1 for w in wrinkle_results if w["charm_match"]),
            "mean_rv_acceleration": round(float(np.mean([
                w["rv_acceleration_ratio"] for w in wrinkle_results
                if w["rv_acceleration_ratio"]
            ])), 3) if wrinkle_results else None,
            "details": wrinkle_results,
        },
        "dispersion_buying": {
            "n_events": len(disp_events),
            "n_target_expirations": len(set(e["target_exp"] for e in disp_events)) if disp_events else 0,
            "pct_expirations": round(
                len(set(e["target_exp"] for e in disp_events)) / len(density_df) * 100, 1
            ) if disp_events and len(density_df) > 0 else 0.0,
        },
    }

    return result


# ===========================================================================
# CLI
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Stacking Resonance Test")
    parser.add_argument("--ticker", type=str, required=True, help="Ticker symbol")
    parser.add_argument("--max-days", type=int, default=0,
                        help="Max trade dates to scan (0 = all)")
    args = parser.parse_args()

    result = run_stacking_test(args.ticker.upper(), max_days=args.max_days)

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outpath = RESULTS_DIR / f"stacking_resonance_{args.ticker.upper()}_{timestamp}.json"

    # Clean numpy types for JSON
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
