#!/usr/bin/env python3
"""
Magnitude Prediction Test: Do Gamma Walls Predict Volatility?
=============================================================
Pivots the failed meteorology test (direction prediction → 50%) to
ask a different question: can gamma wall proximity predict the
MAGNITUDE of next-day returns?

Hypotheses:
  H1: Price near a gamma wall → SMALLER |return| (containment)
  H2: Price in a trough (far from walls) → LARGER |return| (freedom)

If true, options structure doesn't predict direction but does predict
how much price can move — a "volatility containment" effect.

Run on GME, AAPL, TSLA for cross-ticker validation.

Usage:
    python magnitude_prediction_test.py [--tickers GME AAPL TSLA]
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
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)

sys.path.insert(0, str(Path(__file__).parent))
from phase5_paradigm import _load_options_day, _load_equity_day

THETA_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw" / "thetadata" / "trades"
POLYGON_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw" / "polygon" / "trades"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

from squeeze_mechanics_forensic import get_dates, get_equity_close


def run_magnitude_test(ticker, max_days=500):
    """
    Test whether gamma wall proximity predicts next-day |return|.

    Method:
    - For each day, build gamma energy map by strike
    - Compute "wall proximity" = min distance to nearest high-energy strike / price
    - Compute next-day |return|
    - Regress |return| ~ wall_proximity
    - Split into terciles: "near wall", "mid", "far from wall"
    """
    print(f"\n{'='*70}")
    print(f"  MAGNITUDE PREDICTION: {ticker}")
    print(f"{'='*70}")

    opts_dates = get_dates(ticker, "options")
    eq_dates = get_dates(ticker, "equity")

    # Convert to consistent date string format
    opts_clean = []
    for d in opts_dates:
        ds = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if "-" not in d else d
        opts_clean.append(ds)

    eq_clean = []
    for d in eq_dates:
        ds = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if "-" not in d else d
        eq_clean.append(ds)

    overlap = sorted(set(opts_clean) & set(eq_clean))
    if len(overlap) > max_days:
        overlap = overlap[-max_days:]  # Use most recent
    print(f"  Analyzing {len(overlap)} trading days")

    daily_records = []

    for i, date_str in enumerate(overlap):
        price = get_equity_close(ticker, date_str)
        if not price or price <= 0:
            continue

        try:
            opts = _load_options_day(ticker, date_str)
        except Exception:
            continue

        if opts.empty:
            continue

        # Build strike energy map (call volume by strike)
        call_vol = defaultdict(int)
        put_vol = defaultdict(int)
        total_vol = 0
        for _, row in opts.iterrows():
            strike = float(row["strike"])
            vol = int(row["size"])
            total_vol += vol
            if row["right"] in ("C", "c"):
                call_vol[strike] += vol
            else:
                put_vol[strike] += vol

        if not call_vol:
            continue

        # Find "walls" = strikes with significant call volume
        # Use volume-weighted approach: strikes in top 10% by volume
        vol_threshold = np.percentile(list(call_vol.values()), 90) if len(call_vol) > 10 else 0
        wall_strikes = [s for s, v in call_vol.items() if v >= vol_threshold and v > 50]

        if not wall_strikes:
            continue

        # Compute wall proximity (min distance to nearest wall / price %)
        distances = [abs(price - s) / price * 100 for s in wall_strikes]
        min_dist = min(distances)

        # Also compute: weighted average distance (walls with more volume count more)
        weighted_dist = 0
        total_wall_vol = 0
        for s in wall_strikes:
            v = call_vol[s]
            d = abs(price - s) / price * 100
            weighted_dist += d * v
            total_wall_vol += v
        weighted_dist = weighted_dist / max(total_wall_vol, 1)

        # Dominant wall energy
        top_wall_strike = max(call_vol, key=call_vol.get)
        top_wall_vol = call_vol[top_wall_strike]
        top_wall_dist = abs(price - top_wall_strike) / price * 100

        # C/P ratio
        cp_ratio = sum(call_vol.values()) / max(sum(put_vol.values()), 1)

        daily_records.append({
            "date": date_str,
            "price": round(price, 2),
            "min_wall_dist_pct": round(min_dist, 3),
            "weighted_wall_dist_pct": round(weighted_dist, 3),
            "top_wall_dist_pct": round(top_wall_dist, 3),
            "top_wall_strike": top_wall_strike,
            "top_wall_vol": top_wall_vol,
            "total_vol": total_vol,
            "n_walls": len(wall_strikes),
            "cp_ratio": round(cp_ratio, 2),
        })

        if (i + 1) % 50 == 0:
            print(f"    {i+1}/{len(overlap)}", end="", flush=True)

    print()

    # Compute next-day returns
    for i in range(len(daily_records) - 1):
        p_today = daily_records[i]["price"]
        p_tomorrow = daily_records[i + 1]["price"]
        ret = (p_tomorrow - p_today) / p_today
        daily_records[i]["next_day_return"] = round(ret, 6)
        daily_records[i]["next_day_abs_return"] = round(abs(ret), 6)

    # Remove last day (no return)
    records = [r for r in daily_records if "next_day_abs_return" in r]
    if len(records) < 30:
        print(f"  WARNING: Only {len(records)} records — insufficient for analysis")
        return {"ticker": ticker, "error": "insufficient data", "n_records": len(records)}

    df = pd.DataFrame(records)

    # === REGRESSION: |return| ~ wall proximity ===
    print(f"\n  REGRESSION: |return| ~ wall proximity ({len(df)} days)")

    # Test with min distance
    slope, intercept, r_val, p_val, std_err = stats.linregress(
        df["min_wall_dist_pct"], df["next_day_abs_return"])
    r_sq = r_val ** 2
    print(f"\n  Min Wall Distance → |Return|:")
    print(f"    Slope: {slope:.6f} (positive = farther from wall → bigger moves)")
    print(f"    R²: {r_sq:.6f}")
    print(f"    p-value: {p_val:.6f} {'***' if p_val < 0.001 else '**' if p_val < 0.01 else '*' if p_val < 0.05 else ''}")

    min_dist_result = {
        "slope": round(slope, 8),
        "r_squared": round(r_sq, 6),
        "p_value": round(p_val, 6),
        "n": len(df),
    }

    # Test with top wall distance
    slope_t, _, r_val_t, p_val_t, _ = stats.linregress(
        df["top_wall_dist_pct"], df["next_day_abs_return"])
    r_sq_t = r_val_t ** 2
    print(f"\n  Top Wall Distance → |Return|:")
    print(f"    Slope: {slope_t:.6f}")
    print(f"    R²: {r_sq_t:.6f}")
    print(f"    p-value: {p_val_t:.6f} {'***' if p_val_t < 0.001 else '**' if p_val_t < 0.01 else '*' if p_val_t < 0.05 else ''}")

    top_dist_result = {
        "slope": round(slope_t, 8),
        "r_squared": round(r_sq_t, 6),
        "p_value": round(p_val_t, 6),
    }

    # === TERCILE ANALYSIS ===
    # Split into 3 groups by wall proximity
    df["proximity_tercile"] = pd.qcut(df["min_wall_dist_pct"], 3,
                                       labels=["Near Wall", "Mid", "Far from Wall"])

    print(f"\n  TERCILE ANALYSIS:")
    print(f"  {'Tercile':<18} {'N':>5} {'Mean |Ret|':>12} {'Median |Ret|':>14} {'Mean Dist':>10}")
    print("  " + "-" * 62)

    tercile_stats = {}
    for tercile, grp in df.groupby("proximity_tercile", observed=True):
        n = len(grp)
        mean_ret = grp["next_day_abs_return"].mean()
        median_ret = grp["next_day_abs_return"].median()
        mean_dist = grp["min_wall_dist_pct"].mean()
        tercile_stats[str(tercile)] = {
            "n": n,
            "mean_abs_return": round(mean_ret, 6),
            "median_abs_return": round(median_ret, 6),
            "mean_dist": round(mean_dist, 3),
        }
        print(f"  {str(tercile):<18} {n:>5} {mean_ret*100:>11.3f}% {median_ret*100:>13.3f}% {mean_dist:>9.2f}%")

    # T-test: near wall vs far from wall
    near = df[df["proximity_tercile"] == "Near Wall"]["next_day_abs_return"]
    far = df[df["proximity_tercile"] == "Far from Wall"]["next_day_abs_return"]

    if len(near) > 5 and len(far) > 5:
        t_stat, t_pval = stats.ttest_ind(near, far, equal_var=False)
        direction = "NEAR < FAR (containment ✓)" if near.mean() < far.mean() else "NEAR ≥ FAR (no containment)"
        print(f"\n  T-test (Near vs Far):")
        print(f"    t-stat: {t_stat:.4f}")
        print(f"    p-value: {t_pval:.6f} {'***' if t_pval < 0.001 else '**' if t_pval < 0.01 else '*' if t_pval < 0.05 else ''}")
        print(f"    Direction: {direction}")
        ttest_result = {
            "t_stat": round(t_stat, 4),
            "p_value": round(t_pval, 6),
            "direction": direction,
            "near_mean": round(near.mean(), 6),
            "far_mean": round(far.mean(), 6),
        }
    else:
        ttest_result = {"error": "insufficient data in terciles"}

    # === CONDITIONAL: Control for volatility regime ===
    # Use rolling 20-day realized vol to control for vol regimes
    df["rv_20d"] = df["next_day_abs_return"].rolling(20).std()
    df_clean = df.dropna(subset=["rv_20d"])

    if len(df_clean) > 30:
        # Partial correlation: wall proximity → |return| controlling for rv
        from numpy.linalg import lstsq

        X = df_clean[["min_wall_dist_pct", "rv_20d"]].values
        y = df_clean["next_day_abs_return"].values
        X_aug = np.column_stack([X, np.ones(len(X))])
        beta, _, _, _ = lstsq(X_aug, y, rcond=None)
        y_pred = X_aug @ beta
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_sq_multi = 1 - ss_res / max(ss_tot, 1e-10)

        print(f"\n  MULTIVARIATE (controls for volatility regime):")
        print(f"    β_wall_dist: {beta[0]:.6f}")
        print(f"    β_rv20d: {beta[1]:.6f}")
        print(f"    R² (multi): {r_sq_multi:.6f}")

        multi_result = {
            "beta_wall_dist": round(beta[0], 8),
            "beta_rv20d": round(beta[1], 8),
            "r_squared_multi": round(r_sq_multi, 6),
        }
    else:
        multi_result = {"error": "insufficient data for multivariate"}

    return {
        "ticker": ticker,
        "n_records": len(df),
        "min_dist_regression": min_dist_result,
        "top_dist_regression": top_dist_result,
        "tercile_analysis": tercile_stats,
        "ttest_near_vs_far": ttest_result,
        "multivariate": multi_result,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="+", default=["GME", "AAPL", "TSLA"])
    args = parser.parse_args()

    all_results = {}
    for ticker in args.tickers:
        result = run_magnitude_test(ticker)
        all_results[ticker] = result

    # Cross-ticker summary
    print(f"\n\n{'='*70}")
    print(f"  CROSS-TICKER MAGNITUDE PREDICTION SUMMARY")
    print(f"{'='*70}")
    print(f"\n  {'Ticker':<8} {'Slope':>10} {'R²':>10} {'p-value':>10} {'Near Mean':>12} {'Far Mean':>12} {'T-test p':>10}")
    print("  " + "-" * 75)

    for ticker, result in all_results.items():
        if "error" in result:
            print(f"  {ticker:<8} {'ERROR':>10}")
            continue
        reg = result["min_dist_regression"]
        tt = result["ttest_near_vs_far"]
        near_m = tt.get("near_mean", 0)
        far_m = tt.get("far_mean", 0)
        t_p = tt.get("p_value", 999)
        print(f"  {ticker:<8} {reg['slope']:>10.6f} {reg['r_squared']:>10.6f} {reg['p_value']:>10.6f} "
              f"{near_m*100:>11.3f}% {far_m*100:>11.3f}% {t_p:>10.6f}")

    # Save results
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"magnitude_prediction_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Results saved to: {out_path.name}")


if __name__ == "__main__":
    main()
