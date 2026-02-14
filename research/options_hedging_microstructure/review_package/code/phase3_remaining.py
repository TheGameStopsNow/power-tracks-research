#!/usr/bin/env python3
"""
Phase 3B/3C/3E: Remaining Empirical Engines
=============================================
3B — ACF vs Options Volume Ratio (proxy: uses equity trade count as volume proxy)
3C — Monthly ACF Decay Curves (do IPO tickers converge toward dampening?)
3E — Cross-Ticker Contagion (did AMC/BB go amplified before their own squeeze?)

Usage:
  python phase3_remaining.py --mode decay --max-days 500
  python phase3_remaining.py --mode contagion --squeeze-window 20210101 20210301
  python phase3_remaining.py --mode all
"""
import sys
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ENGINE_DIR = Path(__file__).parent.parent / "phase98_cluster_bridge"
sys.path.insert(0, str(ENGINE_DIR))
from temporal_convolution_engine import load_equity_day

POLYGON_DIR = (
    Path(__file__).parent.parent.parent / "data" / "raw" / "polygon" / "trades"
)
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def get_available_equity_dates(symbol: str) -> list[str]:
    for prefix in [f"symbol={symbol}", f"symbol={symbol.upper()}"]:
        path = POLYGON_DIR / prefix
        if path.exists():
            return sorted(d.name.split("=")[1] for d in path.glob("date=*"))
    return []


def compute_daily_acf1(eq: pd.DataFrame, interval_sec: float = 60.0) -> float:
    """Compute ACF lag-1 for one day."""
    df = pd.DataFrame({"ts": eq["ts"], "price": eq["price"]}).set_index("ts")
    bars = df.resample(f"{int(interval_sec)}s").last().dropna()
    returns = bars["price"].pct_change().dropna().values
    if len(returns) < 10:
        return np.nan
    mean = returns.mean()
    var = np.var(returns)
    if var < 1e-12:
        return np.nan
    return float(np.mean((returns[:-1] - mean) * (returns[1:] - mean)) / var)


# ============================================================================
# 3C: Monthly ACF Decay Curves
# ============================================================================

def compute_decay_curve(
    symbol: str,
    dates: list[str],
    window_days: int = 20,
    step_days: int = 20,
) -> list[dict]:
    """Compute rolling 20-day mean ACF, stepped monthly."""
    all_acf = []
    for date_str in dates:
        eq = load_equity_day(symbol, date_str)
        if eq.empty or len(eq) < 100:
            all_acf.append({"date": date_str, "acf1": np.nan, "n_trades": 0})
            continue
        acf1 = compute_daily_acf1(eq)
        all_acf.append({"date": date_str, "acf1": acf1, "n_trades": len(eq)})

    # Compute rolling mean
    results = []
    for i in range(0, len(all_acf), step_days):
        window = all_acf[i : i + window_days]
        vals = [x["acf1"] for x in window if not np.isnan(x["acf1"])]
        if vals:
            results.append({
                "month_idx": len(results),
                "start_date": window[0]["date"],
                "end_date": window[-1]["date"],
                "mean_acf1": round(float(np.mean(vals)), 4),
                "std_acf1": round(float(np.std(vals)), 4),
                "n_days": len(vals),
                "pct_dampened": round(float(sum(1 for v in vals if v < 0) / len(vals) * 100), 1),
            })

    return results


def run_decay(tickers: list[str], max_days: int = 500):
    """Run 3C decay curves for multiple tickers."""
    print(f"\n{'='*70}")
    print(f"  3C: MONTHLY ACF DECAY CURVES")
    print(f"{'='*70}")

    all_curves = {}
    for symbol in tickers:
        dates = get_available_equity_dates(symbol)[:max_days]
        if not dates:
            print(f"  {symbol}: NO DATA")
            continue

        print(f"  {symbol:6s} ({len(dates)} days) ... ", end="", flush=True)
        curve = compute_decay_curve(symbol, dates)
        all_curves[symbol] = curve

        if curve:
            first = curve[0]["mean_acf1"]
            last = curve[-1]["mean_acf1"]
            trend = "↓ convergent" if abs(last) > abs(first) else "→ stable" if abs(first - last) < 0.03 else "↑ divergent"
            print(f"Start={first:+.4f} → End={last:+.4f}  {trend}")
        else:
            print("NO VALID WINDOWS")

    # Summary
    print(f"\n  {'─'*60}")
    print(f"  {'Ticker':6s}  {'Start ACF₁':>10s}  {'End ACF₁':>10s}  {'Δ':>8s}  {'Months':>6s}  {'Trend':>12s}")
    print(f"  {'─'*6}  {'─'*10}  {'─'*10}  {'─'*8}  {'─'*6}  {'─'*12}")
    for symbol, curve in all_curves.items():
        if len(curve) >= 2:
            first = curve[0]["mean_acf1"]
            last = curve[-1]["mean_acf1"]
            delta = last - first
            trend = "DEEPENING" if delta < -0.02 else "STABLE" if abs(delta) < 0.02 else "SHALLOWING"
            print(f"  {symbol:6s}  {first:+10.4f}  {last:+10.4f}  {delta:+8.4f}  {len(curve):6d}  {trend:>12s}")

    # Save
    out_path = RESULTS_DIR / "decay_curves.json"
    serializable = {k: v for k, v in all_curves.items()}
    with open(out_path, "w") as f:
        json.dump(serializable, f, indent=2, default=str)
    print(f"\n  Saved to {out_path}")

    return all_curves


# ============================================================================
# 3E: Cross-Ticker Contagion
# ============================================================================

def run_contagion(
    primary: str = "GME",
    contagion_tickers: list[str] = None,
    start_date: str = "20210101",
    end_date: str = "20210401",
    window_days: int = 5,
):
    """
    Test: during GME squeeze, did correlated tickers' ACFs go positive
    BEFORE their own price action peaked?
    """
    if contagion_tickers is None:
        contagion_tickers = ["AMC", "BYND", "PLTR", "HOOD", "SNAP", "TSLA"]

    print(f"\n{'='*70}")
    print(f"  3E: CROSS-TICKER CONTAGION ({primary} → peers)")
    print(f"  Window: {start_date} → {end_date}")
    print(f"{'='*70}")

    all_tickers = [primary] + [t for t in contagion_tickers if t != primary]
    ticker_data = {}

    for symbol in all_tickers:
        dates = get_available_equity_dates(symbol)
        # Filter to window
        dates = [d for d in dates if start_date <= d.replace("-", "") <= end_date]
        if not dates:
            print(f"  {symbol}: NO DATA in squeeze window")
            continue

        print(f"  Loading {symbol:6s} ({len(dates)} days) ... ", end="", flush=True)
        daily = []
        for date_str in dates:
            eq = load_equity_day(symbol, date_str)
            if eq.empty or len(eq) < 100:
                continue
            acf1 = compute_daily_acf1(eq)
            daily.append({"date": date_str, "acf1": acf1, "n_trades": len(eq)})
        ticker_data[symbol] = daily
        print(f"{len(daily)} valid days")

    if primary not in ticker_data:
        print(f"  ⚠️  Primary ticker {primary} has no data in this window")
        return {}

    # Compute rolling 5-day ACF for each ticker
    print(f"\n  Rolling {window_days}-day ACF:")
    print(f"  {'Date':<12s}", end="")
    for sym in all_tickers:
        if sym in ticker_data:
            print(f"  {sym:>8s}", end="")
    print()

    # Align dates
    all_dates = sorted(set(
        d["date"] for data in ticker_data.values() for d in data
    ))

    # Build lookup
    lookup = {}
    for sym, data in ticker_data.items():
        lookup[sym] = {d["date"]: d["acf1"] for d in data}

    # Rolling window
    contagion_results = []
    for i in range(len(all_dates)):
        window_dates = all_dates[max(0, i - window_days + 1) : i + 1]
        row = {"date": all_dates[i]}
        for sym in all_tickers:
            if sym in lookup:
                vals = [lookup[sym][d] for d in window_dates if d in lookup[sym] and not np.isnan(lookup[sym].get(d, np.nan))]
                row[sym] = round(float(np.mean(vals)), 4) if vals else np.nan
        contagion_results.append(row)

        # Print every 5th row
        if i % 5 == 0:
            print(f"  {row['date']:<12s}", end="")
            for sym in all_tickers:
                if sym in ticker_data:
                    val = row.get(sym, np.nan)
                    if np.isnan(val):
                        print(f"  {'N/A':>8s}", end="")
                    else:
                        color = "🔴" if val > 0 else "🔵"
                        print(f"  {color}{val:+.3f}", end="")
            print()

    # Find contagion events: peer goes positive within ±5 days of primary going positive
    primary_pos_dates = [r["date"] for r in contagion_results if r.get(primary, -1) > 0]

    print(f"\n  {'─'*60}")
    print(f"  CONTAGION ANALYSIS:")
    print(f"  {primary} amplified on {len(primary_pos_dates)} windows")

    for sym in contagion_tickers:
        if sym not in ticker_data:
            continue
        peer_pos_dates = [r["date"] for r in contagion_results if r.get(sym, -1) > 0]
        # Count overlaps
        overlap = len(set(primary_pos_dates) & set(peer_pos_dates))
        total = max(len(primary_pos_dates), 1)
        pct = round(overlap / total * 100, 1) if total > 0 else 0
        print(f"  {sym:6s}: amplified on {len(peer_pos_dates)} windows | overlap with {primary}: {overlap} ({pct}%)")

    # Save
    out_path = RESULTS_DIR / f"contagion_{primary}.json"
    with open(out_path, "w") as f:
        json.dump(contagion_results, f, indent=2, default=str)
    print(f"\n  Saved to {out_path}")

    return contagion_results


# ============================================================================
# 3B: ACF vs Trade Intensity (proxy for volume ratio)
# ============================================================================

def run_volume_proxy(tickers: list[str], max_days: int = 200):
    """
    Proxy for options/equity volume ratio: use trade count intensity
    (trades per minute) as a proxy for activity level.
    Test: does higher trade intensity correlate with stronger dampening?
    """
    print(f"\n{'='*70}")
    print(f"  3B: ACF vs TRADE INTENSITY (volume proxy)")
    print(f"{'='*70}")

    results = []
    for symbol in tickers:
        dates = get_available_equity_dates(symbol)[:max_days]
        if not dates:
            continue

        print(f"  {symbol:6s} ... ", end="", flush=True)

        acf_vals = []
        intensity_vals = []
        for date_str in dates:
            eq = load_equity_day(symbol, date_str)
            if eq.empty or len(eq) < 100:
                continue
            acf1 = compute_daily_acf1(eq)
            if np.isnan(acf1):
                continue
            # Trade intensity = trades per minute (6.5 hour day = 390 min)
            intensity = len(eq) / 390.0
            acf_vals.append(acf1)
            intensity_vals.append(intensity)

        if not acf_vals:
            print("NO DATA")
            continue

        mean_acf = float(np.mean(acf_vals))
        mean_intensity = float(np.mean(intensity_vals))
        # Correlation
        if len(acf_vals) > 5:
            corr = float(np.corrcoef(acf_vals, intensity_vals)[0, 1])
        else:
            corr = np.nan

        results.append({
            "symbol": symbol,
            "mean_acf1": round(mean_acf, 4),
            "mean_intensity": round(mean_intensity, 1),
            "correlation": round(corr, 4) if not np.isnan(corr) else None,
            "n_days": len(acf_vals),
        })
        print(f"ACF₁={mean_acf:+.4f}  Intensity={mean_intensity:6.1f} trades/min  Corr={corr:+.4f}")

    # Sort by intensity
    results.sort(key=lambda r: r["mean_intensity"])

    print(f"\n  {'─'*60}")
    print(f"  SUMMARY (sorted by trade intensity):")
    print(f"  {'Ticker':6s}  {'Intensity':>10s}  {'Mean ACF₁':>10s}  {'Corr':>8s}")
    print(f"  {'─'*6}  {'─'*10}  {'─'*10}  {'─'*8}")
    for r in results:
        corr_str = f"{r['correlation']:+.4f}" if r['correlation'] is not None else "N/A"
        print(f"  {r['symbol']:6s}  {r['mean_intensity']:10.1f}  {r['mean_acf1']:+10.4f}  {corr_str:>8s}")

    # Panel correlation
    intensities = [r["mean_intensity"] for r in results]
    acfs = [r["mean_acf1"] for r in results]
    if len(intensities) > 3:
        panel_corr = float(np.corrcoef(intensities, acfs)[0, 1])
        print(f"\n  Panel correlation (intensity vs ACF₁): {panel_corr:+.4f}")
        if panel_corr < -0.3:
            print(f"  → Higher trade intensity → stronger dampening (supports Long Gamma Default)")
        elif panel_corr > 0.3:
            print(f"  → Higher trade intensity → weaker dampening (suggests retail amplification)")
        else:
            print(f"  → Weak relationship — dampening is structural, not intensity-dependent")

    out_path = RESULTS_DIR / "volume_proxy_scatter.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Saved to {out_path}")

    return results


# ============================================================================
# CLI Entry
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Phase 3 Remaining Engines")
    parser.add_argument("--mode", choices=["decay", "contagion", "volume", "all"], default="all")
    parser.add_argument("--max-days", type=int, default=500)
    parser.add_argument("--tickers", nargs="*", default=None)
    parser.add_argument("--squeeze-start", default="20210101")
    parser.add_argument("--squeeze-end", default="20210401")
    args = parser.parse_args()

    # Default tickers
    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        tickers = sorted(
            d.name.split("=")[1]
            for d in POLYGON_DIR.glob("symbol=*")
            if d.is_dir()
        )

    if args.mode in ("decay", "all"):
        run_decay(tickers, args.max_days)

    if args.mode in ("contagion", "all"):
        run_contagion("GME", ["AMC", "BYND", "PLTR", "TSLA", "SNAP", "LCID"],
                      args.squeeze_start, args.squeeze_end)

    if args.mode in ("volume", "all"):
        run_volume_proxy(tickers, args.max_days)


if __name__ == "__main__":
    main()
