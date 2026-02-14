#!/usr/bin/env python3
"""
Gamma Spectrogram — 25-Ticker Panel Scan
==========================================
Batch compute rolling ACF for all tickers in the Polygon cache.
Outputs a ranked summary table and per-ticker JSON results.

Usage:
    python panel_scan.py [--max-days 500] [--interval 60] [--max-lag 20]
"""
import sys
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# Reuse infrastructure
ENGINE_DIR = Path(__file__).parent.parent / "phase98_cluster_bridge"
sys.path.insert(0, str(ENGINE_DIR))
from temporal_convolution_engine import load_equity_day

POLYGON_DIR = (
    Path(__file__).parent.parent.parent / "data" / "raw" / "polygon" / "trades"
)
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def get_available_equity_dates(symbol: str) -> list[str]:
    """List locally cached equity trading days."""
    for base in [POLYGON_DIR]:
        for prefix in [f"symbol={symbol}", f"symbol={symbol.upper()}"]:
            path = base / prefix
            if path.exists():
                return sorted(d.name.split("=")[1] for d in path.glob("date=*"))
    return []


def compute_daily_acf(
    prices: pd.Series,
    timestamps: pd.Series,
    interval_sec: float = 60.0,
    max_lag: int = 20,
) -> np.ndarray:
    """Compute ACF lag 1..max_lag for a single day."""
    df = pd.DataFrame({"ts": timestamps, "price": prices}).set_index("ts")
    bars = df.resample(f"{int(interval_sec)}s").last().dropna()
    returns = bars["price"].pct_change().dropna().values

    if len(returns) < max_lag + 10:
        return np.full(max_lag, np.nan)

    n = len(returns)
    mean = returns.mean()
    var = np.var(returns)
    if var < 1e-12:
        return np.full(max_lag, np.nan)

    acf = np.zeros(max_lag)
    for lag in range(1, max_lag + 1):
        acf[lag - 1] = (
            np.mean((returns[: n - lag] - mean) * (returns[lag:] - mean)) / var
        )
    return acf


def scan_ticker(
    symbol: str,
    max_days: int = 500,
    interval_sec: float = 60.0,
    max_lag: int = 20,
) -> dict:
    """Scan a single ticker and return summary stats."""
    dates = get_available_equity_dates(symbol)
    if not dates:
        return {"symbol": symbol, "status": "NO_DATA", "n_days": 0}

    dates = dates[:max_days]

    lag1_values = []
    acf_rows = []
    valid_dates = []

    for date_str in dates:
        eq = load_equity_day(symbol, date_str)
        if eq.empty or len(eq) < 100:
            continue
        acf = compute_daily_acf(eq["price"], eq["ts"], interval_sec, max_lag)
        if np.isnan(acf).all():
            continue
        lag1_values.append(acf[0])
        acf_rows.append(acf)
        valid_dates.append(date_str)

    if not lag1_values:
        return {"symbol": symbol, "status": "INSUFFICIENT_DATA", "n_days": 0}

    lag1 = np.array(lag1_values)
    n_dampened = int(np.sum(lag1 < 0))
    n_amplified = int(np.sum(lag1 > 0))
    n_total = len(lag1)

    # Count phase transitions
    transitions = 0
    for i in range(1, len(lag1)):
        if (lag1[i - 1] < 0 and lag1[i] > 0) or (lag1[i - 1] > 0 and lag1[i] < 0):
            transitions += 1

    return {
        "symbol": symbol,
        "status": "OK",
        "n_days": n_total,
        "date_range": f"{valid_dates[0]} → {valid_dates[-1]}",
        "n_dampened": n_dampened,
        "n_amplified": n_amplified,
        "pct_dampened": round(n_dampened / n_total * 100, 1),
        "pct_amplified": round(n_amplified / n_total * 100, 1),
        "mean_lag1": round(float(np.nanmean(lag1)), 4),
        "median_lag1": round(float(np.nanmedian(lag1)), 4),
        "min_lag1": round(float(np.nanmin(lag1)), 4),
        "max_lag1": round(float(np.nanmax(lag1)), 4),
        "std_lag1": round(float(np.nanstd(lag1)), 4),
        "transitions": transitions,
        "regime": "LONG_GAMMA" if n_dampened > n_amplified else "SHORT_GAMMA",
    }


def main():
    parser = argparse.ArgumentParser(description="Panel scan all tickers")
    parser.add_argument("--max-days", type=int, default=500)
    parser.add_argument("--interval", type=float, default=60.0)
    parser.add_argument("--max-lag", type=int, default=20)
    parser.add_argument("--tickers", nargs="*", default=None,
                        help="Specific tickers to scan (default: all)")
    args = parser.parse_args()

    # Discover all tickers
    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        tickers = sorted(
            d.name.split("=")[1]
            for d in POLYGON_DIR.glob("symbol=*")
            if d.is_dir()
        )

    print(f"\n{'='*80}")
    print(f"  GAMMA SPECTROGRAM — {len(tickers)}-TICKER PANEL SCAN")
    print(f"  Interval: {args.interval}s | Max lag: {args.max_lag} | Max days/ticker: {args.max_days}")
    print(f"{'='*80}\n")

    results = []
    for i, symbol in enumerate(tickers):
        print(f"  [{i+1:2d}/{len(tickers)}] {symbol:6s} ... ", end="", flush=True)
        result = scan_ticker(symbol, args.max_days, args.interval, args.max_lag)
        results.append(result)

        if result["status"] == "OK":
            regime_icon = "🔵" if result["regime"] == "LONG_GAMMA" else "🔴"
            print(
                f"{regime_icon} {result['regime']:12s} | "
                f"Days={result['n_days']:3d} | "
                f"Dampened={result['pct_dampened']:5.1f}% | "
                f"ACF₁={result['mean_lag1']:+.4f}"
            )
        else:
            print(f"⚠️  {result['status']}")

    # Summary table
    ok_results = [r for r in results if r["status"] == "OK"]
    ok_results.sort(key=lambda r: r["mean_lag1"])

    print(f"\n{'='*80}")
    print(f"  RANKED RESULTS (sorted by mean Lag-1 ACF)")
    print(f"{'='*80}")
    print(f"  {'Rank':>4s}  {'Ticker':6s}  {'Regime':12s}  {'Days':>4s}  {'Damp%':>5s}  {'Amp%':>5s}  {'ACF₁':>7s}  {'Min':>7s}  {'Max':>7s}  {'Trans':>5s}")
    print(f"  {'─'*4}  {'─'*6}  {'─'*12}  {'─'*4}  {'─'*5}  {'─'*5}  {'─'*7}  {'─'*7}  {'─'*7}  {'─'*5}")

    for rank, r in enumerate(ok_results, 1):
        regime_icon = "🔵" if r["regime"] == "LONG_GAMMA" else "🔴"
        print(
            f"  {rank:4d}  {r['symbol']:6s}  "
            f"{regime_icon} {r['regime']:10s}  "
            f"{r['n_days']:4d}  "
            f"{r['pct_dampened']:5.1f}  "
            f"{r['pct_amplified']:5.1f}  "
            f"{r['mean_lag1']:+.4f}  "
            f"{r['min_lag1']:+.4f}  "
            f"{r['max_lag1']:+.4f}  "
            f"{r['transitions']:5d}"
        )

    # Aggregate stats
    all_lag1 = [r["mean_lag1"] for r in ok_results]
    n_lg = sum(1 for r in ok_results if r["regime"] == "LONG_GAMMA")
    n_sg = sum(1 for r in ok_results if r["regime"] == "SHORT_GAMMA")

    print(f"\n  {'─'*70}")
    print(f"  Panel Summary:")
    print(f"    Tickers scanned: {len(ok_results)}")
    print(f"    Long Gamma Default: {n_lg} ({n_lg/len(ok_results)*100:.0f}%)")
    print(f"    Short Gamma Dominant: {n_sg} ({n_sg/len(ok_results)*100:.0f}%)")
    print(f"    Panel mean ACF₁: {np.mean(all_lag1):+.4f}")
    print(f"    Panel median ACF₁: {np.median(all_lag1):+.4f}")
    print(f"  {'─'*70}\n")

    # Save results
    out_path = RESULTS_DIR / "panel_scan_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  Results saved to {out_path.name}")

    # Save markdown table for draft
    md_path = RESULTS_DIR / "panel_scan_table.md"
    with open(md_path, "w") as f:
        f.write("# Gamma Spectrogram — Panel Scan Results\n\n")
        f.write(f"| Rank | Ticker | Regime | Days | Dampened% | Amplified% | Mean ACF₁ | Min | Max | Transitions |\n")
        f.write(f"|------|--------|--------|------|-----------|------------|-----------|-----|-----|-------------|\n")
        for rank, r in enumerate(ok_results, 1):
            regime = "Long Gamma" if r["regime"] == "LONG_GAMMA" else "Short Gamma"
            f.write(
                f"| {rank} | {r['symbol']} | {regime} | {r['n_days']} | "
                f"{r['pct_dampened']}% | {r['pct_amplified']}% | "
                f"{r['mean_lag1']:+.4f} | {r['min_lag1']:+.4f} | {r['max_lag1']:+.4f} | "
                f"{r['transitions']} |\n"
            )
        f.write(f"\n**Panel: {n_lg}/{len(ok_results)} Long Gamma ({n_lg/len(ok_results)*100:.0f}%) | "
                f"Mean ACF₁ = {np.mean(all_lag1):+.4f}**\n")
    print(f"  Markdown table saved to {md_path.name}\n")


if __name__ == "__main__":
    main()
