#!/usr/bin/env python3
"""
Phase 4A: Millisecond Lead-Lag Engine (The Causal Millisecond)
Phase 4B: Shadow Order Book (Gamma Wall inference from options OI)

For each large options block trade (≥ threshold contracts), measure
the equity volume response in subsequent time windows.
This measures the REACTION TIME of delta-hedging algorithms.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

POLYGON_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw" / "polygon" / "trades"
THETA_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw" / "thetadata" / "trades"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def load_equity_trades(ticker: str, date_str: str) -> pd.DataFrame:
    """Load tick-level equity trades. date_str = 'YYYY-MM-DD'."""
    path = POLYGON_ROOT / f"symbol={ticker}" / f"date={date_str}" / "part-0.parquet"
    if not path.exists():
        raise FileNotFoundError(f"No equity data: {path}")
    df = pd.read_parquet(path)
    df = df.rename(columns={"timestamp": "ts", "price": "eq_price", "size": "eq_size"})
    # ts is already datetime64[ns]
    df = df.sort_values("ts").reset_index(drop=True)
    # Filter to regular trading hours
    df = df[(df["ts"].dt.hour >= 9) & (df["ts"].dt.hour < 16)]
    df = df[~((df["ts"].dt.hour == 9) & (df["ts"].dt.minute < 30))]
    return df[["ts", "eq_price", "eq_size"]]


def load_options_trades(ticker: str, date_str: str) -> pd.DataFrame:
    """Load tick-level options trades. date_str = 'YYYY-MM-DD'."""
    # ThetaData uses YYYYMMDD partitioning
    date_key = date_str.replace("-", "")
    path = THETA_ROOT / f"root={ticker}" / f"date={date_key}" / "part-0.parquet"
    if not path.exists():
        raise FileNotFoundError(f"No options data: {path}")
    df = pd.read_parquet(path)
    # Parse timestamp (string with ms precision)
    df["ts"] = pd.to_datetime(df["timestamp"], format="ISO8601")
    df = df.sort_values("ts").reset_index(drop=True)
    # Filter to regular hours
    df = df[(df["ts"].dt.hour >= 9) & (df["ts"].dt.hour < 16)]
    df = df[~((df["ts"].dt.hour == 9) & (df["ts"].dt.minute < 30))]
    # Normalize column names (schema varies across dates)
    if "expiration" not in df.columns and "expiry" in df.columns:
        df = df.rename(columns={"expiry": "expiration"})
    # Normalize right column (C/P vs CALL/PUT)
    if df["right"].dtype == object:
        df["right"] = df["right"].str[0]  # 'CALL'->'C', 'PUT'->'P', 'C'->'C', 'P'->'P'
    cols = ["ts", "strike", "right", "size", "price"]
    if "expiration" in df.columns:
        cols.append("expiration")
    return df[cols]


# ---------------------------------------------------------------------------
# Phase 4A: Lead-Lag Response Function
# ---------------------------------------------------------------------------

def compute_lead_lag(
    eq_df: pd.DataFrame,
    opts_df: pd.DataFrame,
    min_size: int = 50,
    windows_ms: list[int] = None,
) -> dict:
    """
    For each large options trade (>= min_size contracts), measure
    equity volume response in subsequent time windows.
    
    Returns response function: window_ms -> mean equity trades per window.
    """
    if windows_ms is None:
        windows_ms = [50, 100, 250, 500, 1000, 2000, 5000, 10000]

    # Filter to large options trades
    large = opts_df[opts_df["size"] >= min_size].copy()
    print(f"  Large options trades (>= {min_size} contracts): {len(large)}")
    if len(large) == 0:
        return {"error": "No large trades found"}

    # Convert timestamps to int64 nanoseconds for fast comparison
    eq_ts = eq_df["ts"].values.astype("int64")  # nanoseconds
    eq_sz = eq_df["eq_size"].values
    large_ts = large["ts"].values.astype("int64")
    
    # For each window, count equity trades and total equity volume
    response_trades = {w: [] for w in windows_ms}
    response_volume = {w: [] for w in windows_ms}
    response_abs_return = {w: [] for w in windows_ms}
    
    # Also measure "before" windows as a control
    control_trades = {w: [] for w in windows_ms}
    
    eq_prices = eq_df["eq_price"].values

    for i, opt_ts in enumerate(large_ts):
        if i % 500 == 0 and i > 0:
            print(f"    Processing trade {i}/{len(large_ts)}...")
        
        for w in windows_ms:
            w_ns = w * 1_000_000  # convert ms to ns
            
            # After window: [opt_ts, opt_ts + w_ns]
            mask_after = (eq_ts > opt_ts) & (eq_ts <= opt_ts + w_ns)
            n_after = mask_after.sum()
            vol_after = eq_sz[mask_after].sum() if n_after > 0 else 0
            
            # Price change in window
            if n_after > 0:
                after_prices = eq_prices[mask_after]
                abs_ret = abs(after_prices[-1] - after_prices[0]) / after_prices[0] * 10000  # bps
            else:
                abs_ret = 0.0
            
            response_trades[w].append(n_after)
            response_volume[w].append(vol_after)
            response_abs_return[w].append(abs_ret)
            
            # Before window (control): [opt_ts - w_ns, opt_ts]
            mask_before = (eq_ts >= opt_ts - w_ns) & (eq_ts < opt_ts)
            control_trades[w].append(mask_before.sum())

    # Compute statistics
    result = {}
    for w in windows_ms:
        after_mean = float(np.mean(response_trades[w]))
        before_mean = float(np.mean(control_trades[w]))
        ratio = after_mean / before_mean if before_mean > 0 else float("inf")
        result[str(w)] = {
            "window_ms": w,
            "mean_eq_trades_after": round(after_mean, 2),
            "mean_eq_trades_before": round(before_mean, 2),
            "response_ratio": round(ratio, 3),
            "mean_eq_volume_after": round(float(np.mean(response_volume[w])), 1),
            "mean_abs_return_bps": round(float(np.mean(response_abs_return[w])), 2),
        }
    
    return result


# ---------------------------------------------------------------------------
# Phase 4A runner: Multi-date, multi-ticker
# ---------------------------------------------------------------------------

def run_lead_lag_single(ticker: str, date_str: str, min_size: int = 50) -> dict:
    """Run lead-lag for a single ticker-date."""
    print(f"\n{'='*60}")
    print(f"Lead-Lag: {ticker} {date_str}")
    print(f"{'='*60}")
    
    eq_df = load_equity_trades(ticker, date_str)
    opts_df = load_options_trades(ticker, date_str)
    
    print(f"  Equity trades: {len(eq_df)}")
    print(f"  Options trades: {len(opts_df)}")
    
    result = compute_lead_lag(eq_df, opts_df, min_size=min_size)
    
    # Summary
    print(f"\n  === RESPONSE FUNCTION ===")
    print(f"  {'Window':>8}  {'After':>8}  {'Before':>8}  {'Ratio':>8}  {'Vol':>8}  {'|Ret| bps':>10}")
    for k, v in sorted(result.items(), key=lambda x: int(x[0])):
        if isinstance(v, dict):
            print(f"  {v['window_ms']:>6}ms  {v['mean_eq_trades_after']:>8.1f}  "
                  f"{v['mean_eq_trades_before']:>8.1f}  {v['response_ratio']:>8.3f}  "
                  f"{v['mean_eq_volume_after']:>8.1f}  {v['mean_abs_return_bps']:>10.2f}")
    
    return result


def run_lead_lag_panel(tickers_dates: list[tuple[str, str]], min_size: int = 20) -> dict:
    """Run lead-lag across multiple ticker-dates and aggregate."""
    all_results = {}
    for ticker, date_str in tickers_dates:
        try:
            r = run_lead_lag_single(ticker, date_str, min_size=min_size)
            all_results[f"{ticker}_{date_str}"] = r
        except FileNotFoundError as e:
            print(f"  SKIP: {e}")
    
    # Panel aggregate
    if all_results:
        windows = sorted(set(int(k) for r in all_results.values() for k in r.keys() if k.isdigit()))
        panel_agg = {}
        for w in windows:
            ratios = [r[str(w)]["response_ratio"] for r in all_results.values() if str(w) in r and isinstance(r[str(w)], dict)]
            if ratios:
                panel_agg[str(w)] = {
                    "window_ms": w,
                    "panel_mean_ratio": round(float(np.mean(ratios)), 3),
                    "panel_std_ratio": round(float(np.std(ratios)), 3),
                    "n_tickers": len(ratios),
                }
        all_results["PANEL_AGGREGATE"] = panel_agg
    
    return all_results


# ---------------------------------------------------------------------------
# Phase 4B: Shadow Order Book (gamma exposure by strike)
# ---------------------------------------------------------------------------

def compute_gamma_exposure(opts_df: pd.DataFrame, spot_price: float) -> pd.DataFrame:
    """
    Approximate net gamma exposure per strike from trade flow.
    
    Since we don't have OI directly, we use net trade flow as a proxy:
    - Aggregate buy-side volume per strike (positive gamma for calls, negative for puts
      from dealer perspective when selling to customers)
    - Compute $ gamma exposure = net_flow × 100 × BSM_gamma × spot²
    
    Simplified: use cumulative trade count × size as a proxy for positioning.
    """
    # Aggregate by strike
    by_strike = opts_df.groupby(["strike", "right"]).agg(
        total_volume=("size", "sum"),
        trade_count=("size", "count"),
        mean_price=("price", "mean"),
        last_price=("price", "last"),
    ).reset_index()
    
    # Approximate BSM gamma for ATM options (simplified)
    # gamma ≈ N'(d1) / (S * sigma * sqrt(T))
    # For a crude estimate: gamma is highest ATM and decays with moneyness
    by_strike["moneyness"] = by_strike["strike"] / spot_price
    by_strike["approx_gamma"] = np.exp(-0.5 * ((by_strike["moneyness"] - 1.0) / 0.1) ** 2) / (spot_price * 0.4 * np.sqrt(1/12))
    
    # Dealer perspective: institutional investors are NET SELLERS of options
    # So dealer is long gamma on both calls and puts
    # Gamma exposure per strike = gamma × volume × 100 × spot²
    by_strike["gamma_dollars"] = by_strike["approx_gamma"] * by_strike["total_volume"] * 100 * spot_price
    
    # Calls contribute positive gamma, puts contribute positive gamma for long dealer
    # The "wall" effect: high absolute gamma = price tends to pin/repel at that strike
    by_strike = by_strike.sort_values("strike").reset_index(drop=True)
    
    return by_strike


def compute_price_strike_interaction(
    eq_df: pd.DataFrame,
    gamma_walls: pd.DataFrame,
    spot_price: float,
    n_top: int = 5,
) -> dict:
    """
    Measure price behavior near high-gamma strikes.
    For the top N gamma walls, check if price shows increased reversal
    (pinning / repulsion) near those strikes.
    """
    # Get top gamma walls
    top_strikes = gamma_walls.nlargest(n_top, "gamma_dollars")
    
    results = {}
    for _, wall in top_strikes.iterrows():
        strike = wall["strike"]
        gamma_val = wall["gamma_dollars"]
        
        # Define "near" as within 1% of the strike
        threshold = strike * 0.01
        near_mask = (eq_df["eq_price"] >= strike - threshold) & (eq_df["eq_price"] <= strike + threshold)
        far_mask = ~near_mask
        
        if near_mask.sum() < 10 or far_mask.sum() < 10:
            continue
        
        # Compute 1-minute return ACF near vs. far from the strike
        eq_near = eq_df[near_mask].copy()
        eq_far = eq_df[far_mask].copy()
        
        # Use sequential returns
        def compute_seq_acf(prices):
            if len(prices) < 20:
                return float("nan")
            rets = np.diff(prices) / prices[:-1]
            if len(rets) < 2:
                return float("nan")
            return float(np.corrcoef(rets[:-1], rets[1:])[0, 1])
        
        acf_near = compute_seq_acf(eq_near["eq_price"].values)
        acf_far = compute_seq_acf(eq_far["eq_price"].values)
        
        results[str(strike)] = {
            "strike": strike,
            "gamma_dollars": round(gamma_val, 0),
            "ticks_near": int(near_mask.sum()),
            "ticks_far": int(far_mask.sum()),
            "acf_near": round(acf_near, 4) if not np.isnan(acf_near) else None,
            "acf_far": round(acf_far, 4) if not np.isnan(acf_far) else None,
            "right": wall["right"],
        }
    
    return results


def run_shadow_orderbook(ticker: str, date_str: str) -> dict:
    """Run shadow order book analysis for a single day."""
    print(f"\n{'='*60}")
    print(f"Shadow Order Book: {ticker} {date_str}")
    print(f"{'='*60}")
    
    eq_df = load_equity_trades(ticker, date_str)
    opts_df = load_options_trades(ticker, date_str)
    
    # Get spot price (median of equity trades)
    spot = float(eq_df["eq_price"].median())
    print(f"  Spot price (median): ${spot:.2f}")
    print(f"  Equity trades: {len(eq_df)}, Options trades: {len(opts_df)}")
    
    # Compute gamma exposure
    gamma = compute_gamma_exposure(opts_df, spot)
    
    # Top gamma walls
    top_walls = gamma.nlargest(10, "gamma_dollars")
    print(f"\n  === TOP GAMMA WALLS ===")
    print(f"  {'Strike':>8}  {'Right':>5}  {'Volume':>8}  {'Gamma $':>12}")
    for _, w in top_walls.iterrows():
        print(f"  ${w['strike']:>7.1f}  {w['right']:>5}  {w['total_volume']:>8}  ${w['gamma_dollars']:>11,.0f}")
    
    # Price-strike interaction
    interaction = compute_price_strike_interaction(eq_df, gamma, spot, n_top=8)
    
    if interaction:
        print(f"\n  === PRICE-STRIKE INTERACTION ===")
        print(f"  {'Strike':>8}  {'Right':>5}  {'ACF Near':>10}  {'ACF Far':>10}  {'Delta':>8}")
        for k, v in sorted(interaction.items(), key=lambda x: float(x[0])):
            acf_n = v["acf_near"] if v["acf_near"] is not None else float("nan")
            acf_f = v["acf_far"] if v["acf_far"] is not None else float("nan")
            delta = acf_n - acf_f if not (np.isnan(acf_n) or np.isnan(acf_f)) else float("nan")
            print(f"  ${float(k):>7.1f}  {v['right']:>5}  {acf_n:>10.4f}  {acf_f:>10.4f}  {delta:>8.4f}")
    
    return {
        "spot": spot,
        "top_gamma_walls": top_walls.to_dict("records"),
        "price_strike_interaction": interaction,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def find_overlapping_dates(ticker: str, max_dates: int = 10) -> list[str]:
    """Find dates where both equity and options data exist."""
    eq_dir = POLYGON_ROOT / f"symbol={ticker}"
    opts_dir = THETA_ROOT / f"root={ticker}"
    
    if not eq_dir.exists() or not opts_dir.exists():
        return []
    
    eq_dates = {d.name.replace("date=", "") for d in eq_dir.iterdir() if d.is_dir()}
    opts_dates = {d.name.replace("date=", "").replace("-", "") for d in opts_dir.iterdir() if d.is_dir()}
    
    # Normalize: equity uses YYYY-MM-DD, options uses YYYYMMDD
    opts_dates_normalized = set()
    for d in opts_dates:
        if len(d) == 8:
            opts_dates_normalized.add(f"{d[:4]}-{d[4:6]}-{d[6:8]}")
    
    overlap = sorted(eq_dates & opts_dates_normalized)
    return overlap[-max_dates:]


def main():
    parser = argparse.ArgumentParser(description="Phase 4: Causal Forensics")
    parser.add_argument("--mode", choices=["leadlag", "shadow", "both"], default="both")
    parser.add_argument("--ticker", default="GME")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD; if omitted, auto-detect")
    parser.add_argument("--min-size", type=int, default=20, help="Min option trade size")
    parser.add_argument("--max-dates", type=int, default=5)
    args = parser.parse_args()
    
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Find dates
    if args.date:
        dates = [args.date]
    else:
        dates = find_overlapping_dates(args.ticker, args.max_dates)
        print(f"Found {len(dates)} overlapping dates for {args.ticker}")
        if not dates:
            print("No overlapping dates found!")
            sys.exit(1)
    
    all_results = {"ticker": args.ticker, "dates": dates}
    
    if args.mode in ("leadlag", "both"):
        pairs = [(args.ticker, d) for d in dates]
        leadlag_results = run_lead_lag_panel(pairs, min_size=args.min_size)
        all_results["leadlag"] = leadlag_results
        
        # Save
        out_path = RESULTS_DIR / f"phase4a_leadlag_{args.ticker}.json"
        with open(out_path, "w") as f:
            json.dump(leadlag_results, f, indent=2, default=str)
        print(f"\nSaved lead-lag results to {out_path}")
    
    if args.mode in ("shadow", "both"):
        shadow_results = {}
        for d in dates:
            try:
                shadow_results[d] = run_shadow_orderbook(args.ticker, d)
            except FileNotFoundError as e:
                print(f"  SKIP: {e}")
        
        all_results["shadow"] = shadow_results
        
        # Save
        out_path = RESULTS_DIR / f"phase4b_shadow_{args.ticker}.json"
        with open(out_path, "w") as f:
            json.dump(shadow_results, f, indent=2, default=str)
        print(f"\nSaved shadow order book results to {out_path}")
    
    # Print panel summary
    if "leadlag" in all_results and "PANEL_AGGREGATE" in all_results["leadlag"]:
        print(f"\n{'='*60}")
        print(f"PANEL LEAD-LAG SUMMARY: {args.ticker}")
        print(f"{'='*60}")
        panel = all_results["leadlag"]["PANEL_AGGREGATE"]
        print(f"{'Window':>8}  {'Mean Ratio':>12}  {'Std':>8}  {'N':>4}")
        for k, v in sorted(panel.items(), key=lambda x: int(x[0])):
            print(f"{v['window_ms']:>6}ms  {v['panel_mean_ratio']:>12.3f}  "
                  f"{v['panel_std_ratio']:>8.3f}  {v['n_tickers']:>4}")


if __name__ == "__main__":
    main()
