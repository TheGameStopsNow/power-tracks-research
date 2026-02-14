"""
Rogue Wave Forensic — Adversarial Microstructure Tests

Implements two hypothesis families:

  A) "Player Piano" — Institutional Acoustic Pinning
     A1. Origination Cohort Scan — Gini coefficient of OI buildup
     A2. Charm Drift Detector — Regress returns on aggregate Charm

  B) "Rogue Wave Architect" — Engineered Squeeze Detection
     B1. Spear Tip Pattern Scanner — OI waterfall for squeeze expirations
     B2. Vanna Shock Amplifier — LEAPS delta recomputation at varying IV

Data source: ThetaData Theta Terminal (local, http://127.0.0.1:25503/v3)
API: /option/history/open_interest?symbol=X&expiration=*&date=YYYYMMDD

Usage:
  python rogue_wave_forensic.py --test spear_tip --ticker GME
  python rogue_wave_forensic.py --test origination --ticker GME
  python rogue_wave_forensic.py --test vanna_shock --ticker GME
  python rogue_wave_forensic.py --test all --ticker GME
"""

import argparse
import json
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
from io import StringIO

import numpy as np
import pandas as pd
import requests
from scipy import stats

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parents[2]
THETA_ROOT = BASE_DIR / "data" / "raw" / "thetadata" / "trades"
OI_CACHE_DIR = BASE_DIR / "data" / "raw" / "thetadata" / "open_interest"
RESULTS_DIR = Path(__file__).parent / "results"
OI_CACHE_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

THETA_BASE_URL = "http://127.0.0.1:25503/v3"

# ─── Known squeeze events ─────────────────────────────────────────────────────
SQUEEZE_EVENTS = {
    "GME": [
        {"name": "Jan 2021 Squeeze", "target_exp": "20210129", "peak": "20210128",
         "lookback_start": "20200401", "lookback_end": "20210129"},
        {"name": "Jun 2024 Squeeze", "target_exp": "20240621", "peak": "20240607",
         "lookback_start": "20230901", "lookback_end": "20240621"},
    ],
}

# ─── OI Fetcher ───────────────────────────────────────────────────────────────

def fetch_oi_snapshot(symbol: str, date_str: str) -> pd.DataFrame | None:
    """
    Fetch or load cached full OI surface for a symbol on a given date.
    Returns DataFrame with columns: [strike, right, expiration, open_interest]
    """
    cache_path = OI_CACHE_DIR / symbol / f"oi_{date_str}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)
    
    url = f"{THETA_BASE_URL}/option/history/open_interest"
    params = {"symbol": symbol, "expiration": "*", "date": date_str, "format": "json"}
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception as e:
        print(f"    Fetch error for {symbol} {date_str}: {e}")
        return None
    
    records = []
    for item in data.get("response", []):
        contract = item.get("contract", {})
        for d in item.get("data", []):
            oi = d.get("open_interest", 0)
            if oi > 0:
                records.append({
                    "strike": contract.get("strike", 0),
                    "right": contract.get("right", ""),
                    "expiration": contract.get("expiration", ""),
                    "open_interest": oi,
                })
    
    if not records:
        return None
    
    df = pd.DataFrame(records)
    df["expiration"] = pd.to_datetime(df["expiration"])
    
    # Cache
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(cache_path, index=False)
    return df


def fetch_oi_timeseries(symbol: str, start_date: str, end_date: str,
                        target_exp: str = None, progress: bool = True,
                        max_workers: int = 8) -> pd.DataFrame:
    """
    Fetch OI snapshots across a range of dates, returning a combined DataFrame.
    If target_exp is set, filter to only that expiration.
    Uses ThreadPoolExecutor for parallel fetching (8 workers default).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    dates = pd.bdate_range(start, end)
    
    # Check how many are already cached
    cached = sum(1 for d in dates
                 if (OI_CACHE_DIR / symbol / f"oi_{d.strftime('%Y%m%d')}.parquet").exists())
    if progress:
        print(f"    {cached}/{len(dates)} already cached, fetching {len(dates) - cached} new")
    
    def _fetch_one(d):
        date_str = d.strftime("%Y%m%d")
        df = fetch_oi_snapshot(symbol, date_str)
        if df is not None and len(df) > 0:
            df = df.copy()
            df["observation_date"] = d
            if target_exp:
                target_dt = pd.Timestamp(target_exp)
                df = df[df["expiration"] == target_dt]
            return df
        return None
    
    all_frames = []
    done_count = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_one, d): d for d in dates}
        for future in as_completed(futures):
            done_count += 1
            result = future.result()
            if result is not None and len(result) > 0:
                all_frames.append(result)
            if progress and done_count % 20 == 0:
                sys.stdout.write(f"    {done_count}/{len(dates)}\n")
                sys.stdout.flush()
    
    if progress:
        sys.stdout.write(f"    {len(dates)}/{len(dates)} done\n")
    
    if not all_frames:
        return pd.DataFrame()
    
    return pd.concat(all_frames, ignore_index=True)


# ─── Test B1: Spear Tip Pattern Scanner ──────────────────────────────────────

def run_spear_tip_test(ticker: str) -> dict:
    """
    For each known squeeze event, build an OI waterfall chart tracking how
    open interest targeting the squeeze expiration accumulated over time.
    
    Key output: origination profile — was OI buildup smooth (organic) or
    step-function (engineered)?
    """
    events = SQUEEZE_EVENTS.get(ticker, [])
    if not events:
        print(f"  No known squeeze events for {ticker}")
        return {"status": "NO_EVENTS", "ticker": ticker}
    
    results = []
    
    for event in events:
        name = event["name"]
        target_exp = event["target_exp"]
        start = event["lookback_start"]
        end = event["lookback_end"]
        
        print(f"\n{'='*70}")
        print(f"  SPEAR TIP ANALYSIS: {name}")
        print(f"  Target expiration: {target_exp}")
        print(f"  Lookback: {start} to {end}")
        print(f"{'='*70}")
        
        # Fetch OI timeseries for this target expiration
        print(f"  Fetching OI timeseries...")
        ts = fetch_oi_timeseries(ticker, start, end, target_exp=target_exp)
        
        if ts.empty:
            print(f"  No OI data found for this period")
            results.append({"event": name, "status": "NO_DATA"})
            continue
        
        # Aggregate: total OI per observation date (sum across strikes/rights)
        daily_oi = ts.groupby("observation_date")["open_interest"].sum().sort_index()
        
        # First date the target expiration appears with OI > 0
        first_oi_date = daily_oi[daily_oi > 0].index[0] if (daily_oi > 0).any() else None
        
        print(f"  OI timeseries: {len(daily_oi)} observations")
        print(f"  First OI date: {first_oi_date}")
        print(f"  Peak OI: {daily_oi.max():,.0f} on {daily_oi.idxmax().strftime('%Y-%m-%d')}")
        
        # Compute daily changes
        daily_changes = daily_oi.diff().fillna(0)
        
        # --- Gini coefficient of daily OI changes ---
        abs_changes = daily_changes.abs()
        abs_changes_sorted = np.sort(abs_changes.values)
        n = len(abs_changes_sorted)
        if n > 0 and abs_changes_sorted.sum() > 0:
            index = np.arange(1, n + 1)
            gini = (2 * np.sum(index * abs_changes_sorted) - (n + 1) * np.sum(abs_changes_sorted)) / (n * np.sum(abs_changes_sorted))
        else:
            gini = 0.0
        
        # --- Detect step-function jumps ---
        # A "jump" is a daily change > 2× the median absolute change
        median_change = abs_changes.median()
        threshold = max(median_change * 3, 100)  # At least 3× median or 100 contracts
        jumps = daily_changes[abs_changes > threshold]
        large_jumps = daily_changes[abs_changes > threshold * 3]
        
        # --- DTE profile of buildup ---
        target_dt = pd.Timestamp(target_exp)
        daily_oi_with_dte = daily_oi.to_frame("oi")
        daily_oi_with_dte["dte"] = (target_dt - daily_oi_with_dte.index).days
        
        # Bin by DTE bands
        dte_bands = [
            ("T-700 to T-365", 365, 700),
            ("T-365 to T-180", 180, 365),
            ("T-180 to T-90", 90, 180),
            ("T-90 to T-30", 30, 90),
            ("T-30 to T-7", 7, 30),
            ("T-7 to T-0", 0, 7),
        ]
        
        band_results = []
        for band_name, dte_lo, dte_hi in dte_bands:
            band = daily_oi_with_dte[(daily_oi_with_dte["dte"] >= dte_lo) & (daily_oi_with_dte["dte"] < dte_hi)]
            if len(band) > 0:
                band_start_oi = band["oi"].iloc[0]
                band_end_oi = band["oi"].iloc[-1]
                oi_added = band_end_oi - band_start_oi
                pct_of_total = oi_added / daily_oi.max() * 100 if daily_oi.max() > 0 else 0
                band_results.append({
                    "band": band_name,
                    "days": len(band),
                    "oi_start": int(band_start_oi),
                    "oi_end": int(band_end_oi),
                    "oi_added": int(oi_added),
                    "pct_of_peak": round(pct_of_total, 1),
                })
        
        # --- Print results ---
        print(f"\n  Gini coefficient of daily OI changes: {gini:.4f}")
        print(f"  (Higher = more concentrated/institutional, Lower = more distributed/organic)")
        print(f"  Jumps (>3× median): {len(jumps)}")
        print(f"  Large jumps (>9× median): {len(large_jumps)}")
        
        print(f"\n  DTE Band Buildup Profile:")
        print(f"  {'Band':<20} {'Days':>5} {'OI Start':>10} {'OI End':>10} {'Added':>10} {'%Peak':>7}")
        print(f"  {'-'*62}")
        for b in band_results:
            print(f"  {b['band']:<20} {b['days']:>5} {b['oi_start']:>10,} {b['oi_end']:>10,} {b['oi_added']:>10,} {b['pct_of_peak']:>6.1f}%")
        
        # --- Top 10 largest daily jumps ---
        top_jumps = daily_changes.abs().nlargest(10)
        print(f"\n  Top 10 Largest Daily OI Changes:")
        print(f"  {'Date':<12} {'Change':>10} {'DTE':>5} {'Direction':>10}")
        print(f"  {'-'*40}")
        for date, val in top_jumps.items():
            dte = (target_dt - date).days
            actual = daily_changes[date]
            direction = "ADD" if actual > 0 else "CLOSE"
            print(f"  {date.strftime('%Y-%m-%d'):<12} {int(actual):>+10,} {dte:>5} {direction:>10}")
        
        # --- Strike distribution analysis ---
        # Where did OI concentrate? Check at peak
        peak_date = daily_oi.idxmax()
        peak_snapshot = ts[ts["observation_date"] == peak_date]
        
        if not peak_snapshot.empty:
            # Group by strike for calls
            call_oi = peak_snapshot[peak_snapshot["right"] == "CALL"].groupby("strike")["open_interest"].sum()
            put_oi = peak_snapshot[peak_snapshot["right"] == "PUT"].groupby("strike")["open_interest"].sum()
            
            print(f"\n  OI at Peak ({peak_date.strftime('%Y-%m-%d')}):")
            print(f"  Total Call OI: {call_oi.sum():>12,}")
            print(f"  Total Put OI:  {put_oi.sum():>12,}")
            
            print(f"\n  Top 5 Call Strikes:")
            for strike, oi in call_oi.nlargest(5).items():
                print(f"    ${strike:.2f}: {oi:>10,}")
            
            print(f"\n  Top 5 Put Strikes:")
            for strike, oi in put_oi.nlargest(5).items():
                print(f"    ${strike:.2f}: {oi:>10,}")
        
        # Verdict
        if gini > 0.6 and len(large_jumps) >= 3:
            verdict = "ENGINEERED (high concentration + discrete jumps)"
        elif gini > 0.5:
            verdict = "MIXED (moderate concentration)"
        else:
            verdict = "ORGANIC (distributed buildup)"
        
        print(f"\n  VERDICT: {verdict}")
        
        results.append({
            "event": name,
            "target_expiration": target_exp,
            "lookback": f"{start} to {end}",
            "n_observations": len(daily_oi),
            "first_oi_date": str(first_oi_date),
            "peak_oi": int(daily_oi.max()),
            "peak_date": str(daily_oi.idxmax()),
            "gini_coefficient": round(gini, 4),
            "n_jumps": len(jumps),
            "n_large_jumps": len(large_jumps),
            "dte_bands": band_results,
            "top_jumps": [
                {"date": date.strftime("%Y-%m-%d"), "change": int(daily_changes[date]),
                 "dte": int((target_dt - date).days)}
                for date, _ in top_jumps.items()
            ],
            "verdict": verdict,
        })
    
    return {"test": "spear_tip", "ticker": ticker, "events": results}


# ─── Test A1: Origination Cohort Scan ────────────────────────────────────────

def run_origination_cohort_test(ticker: str) -> dict:
    """
    For the top gamma walls identified from our existing analysis,
    measure the Gini coefficient of daily OI changes at each wall strike.
    
    High Gini = institutional injection (discrete jumps)
    Low Gini = organic flow (smooth buildup)
    """
    print(f"\n{'='*70}")
    print(f"  ORIGINATION COHORT SCAN: {ticker}")
    print(f"{'='*70}")
    
    # We need to identify gamma walls. Use recent data to find the top OI strikes.
    # Fetch a recent OI snapshot to identify candidate walls.
    end = datetime.now()
    start = end - timedelta(days=90)
    
    # Sample recent dates to find top OI strikes
    sample_dates = pd.bdate_range(start, end)[-5:]  # Last 5 trading days
    
    all_oi = []
    for d in sample_dates:
        df = fetch_oi_snapshot(ticker, d.strftime("%Y%m%d"))
        if df is not None:
            all_oi.append(df)
    
    if not all_oi:
        print("  No recent OI data found")
        return {"status": "NO_DATA", "ticker": ticker}
    
    combined = pd.concat(all_oi)
    
    # Find the top 5 strikes by call OI (these are candidate gamma walls)
    call_oi = combined[combined["right"] == "CALL"].groupby("strike")["open_interest"].mean()
    top_strikes = call_oi.nlargest(10).index.tolist()
    
    print(f"  Top OI strikes: {top_strikes[:5]}")
    
    # For each top strike, fetch OI over 60 days and compute Gini
    lookback_start = (end - timedelta(days=90)).strftime("%Y%m%d")
    lookback_end = end.strftime("%Y%m%d")
    
    print(f"  Fetching 90-day OI timeseries for top strikes...")
    ts = fetch_oi_timeseries(ticker, lookback_start, lookback_end)
    
    if ts.empty:
        print("  No OI timeseries data")
        return {"status": "NO_DATA", "ticker": ticker}
    
    # Analyze each top strike
    strike_results = []
    for strike in top_strikes[:5]:
        strike_data = ts[(ts["strike"] == strike) & (ts["right"] == "CALL")]
        if strike_data.empty:
            continue
        
        daily = strike_data.groupby("observation_date")["open_interest"].sum().sort_index()
        changes = daily.diff().fillna(0).abs()
        
        # Gini coefficient
        sorted_changes = np.sort(changes.values)
        n = len(sorted_changes)
        if n > 0 and sorted_changes.sum() > 0:
            index = np.arange(1, n + 1)
            gini = (2 * np.sum(index * sorted_changes) - (n + 1) * np.sum(sorted_changes)) / (n * np.sum(sorted_changes))
        else:
            gini = 0.0
        
        # Count large moves
        median_change = changes.median()
        threshold = max(median_change * 3, 50)
        n_jumps = (changes > threshold).sum()
        
        classification = "INSTITUTIONAL" if gini > 0.55 else "MIXED" if gini > 0.4 else "ORGANIC"
        
        strike_results.append({
            "strike": strike,
            "mean_oi": int(daily.mean()),
            "gini": round(gini, 4),
            "n_jumps": int(n_jumps),
            "n_observations": len(daily),
            "classification": classification,
        })
        
        print(f"    ${strike:.2f}: Gini={gini:.4f} ({classification}), "
              f"Mean OI={daily.mean():,.0f}, Jumps={n_jumps}")
    
    # Summary
    mean_gini = np.mean([s["gini"] for s in strike_results]) if strike_results else 0
    pct_institutional = sum(1 for s in strike_results if s["classification"] == "INSTITUTIONAL") / max(len(strike_results), 1) * 100
    
    print(f"\n  Mean Gini: {mean_gini:.4f}")
    print(f"  % Institutional: {pct_institutional:.0f}%")
    
    return {
        "test": "origination_cohort",
        "ticker": ticker,
        "mean_gini": round(mean_gini, 4),
        "pct_institutional": round(pct_institutional, 1),
        "strikes": strike_results,
    }


# ─── Test B2: Vanna Shock Amplifier ──────────────────────────────────────────

def _bs_delta(S, K, T, r, sigma, is_call=True):
    """Black-Scholes delta calculation."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    delta = stats.norm.cdf(d1) if is_call else stats.norm.cdf(d1) - 1
    return delta


def run_vanna_shock_test(ticker: str) -> dict:
    """
    During squeeze events, measure how LEAPS delta changed as IV exploded.
    If deep OTM LEAPS gained significant delta, MMs were forced to delta-hedge,
    creating a feedback loop.
    """
    events = SQUEEZE_EVENTS.get(ticker, [])
    if not events:
        return {"status": "NO_EVENTS", "ticker": ticker}
    
    results = []
    
    for event in events:
        name = event["name"]
        peak = event["peak"]
        target_exp = event["target_exp"]
        
        print(f"\n{'='*70}")
        print(f"  VANNA SHOCK ANALYSIS: {name}")
        print(f"{'='*70}")
        
        # Get OI snapshot right before peak
        pre_date = (pd.Timestamp(peak) - timedelta(days=14)).strftime("%Y%m%d")
        peak_date_str = peak
        
        pre_oi = fetch_oi_snapshot(ticker, pre_date)
        peak_oi = fetch_oi_snapshot(ticker, peak_date_str)
        
        if pre_oi is None or peak_oi is None:
            print(f"  Missing OI data for {pre_date} or {peak_date_str}")
            results.append({"event": name, "status": "NO_DATA"})
            continue
        
        # Focus on LEAPS (DTE > 180 from peak date)
        peak_dt = pd.Timestamp(peak)
        pre_oi["dte"] = (pre_oi["expiration"] - pd.Timestamp(pre_date)).dt.days
        leaps = pre_oi[pre_oi["dte"] > 180].copy()
        
        if leaps.empty:
            print(f"  No LEAPS found (DTE > 180)")
            results.append({"event": name, "status": "NO_LEAPS"})
            continue
        
        print(f"  LEAPS contracts: {len(leaps)} (DTE > 180)")
        print(f"  Total LEAPS OI: {leaps['open_interest'].sum():,}")
        
        # Estimate pre-squeeze and peak-squeeze conditions
        # We need stock prices - approximate from known data
        # For GME Jan 2021: pre-squeeze ~$35, peak ~$350, pre-IV ~100%, peak-IV ~800%
        if ticker == "GME" and "Jan 2021" in name:
            S_pre, IV_pre = 35.0, 1.0
            S_peak, IV_peak = 350.0, 8.0
        elif ticker == "GME" and "Jun 2024" in name:
            S_pre, IV_pre = 20.0, 0.8
            S_peak, IV_peak = 65.0, 3.0
        else:
            S_pre, IV_pre = 50.0, 0.5
            S_peak, IV_peak = 100.0, 2.0
        
        r = 0.05
        
        # Recompute deltas at pre and peak conditions
        total_delta_pre = 0
        total_delta_peak = 0
        shock_records = []
        
        for _, row in leaps.iterrows():
            K = row["strike"]
            T = row["dte"] / 365.0
            oi = row["open_interest"]
            is_call = row["right"] == "CALL"
            
            delta_pre = _bs_delta(S_pre, K, T, r, IV_pre, is_call)
            delta_peak = _bs_delta(S_peak, K, T, r, IV_peak, is_call)
            
            shares_pre = delta_pre * oi * 100
            shares_peak = delta_peak * oi * 100
            
            total_delta_pre += shares_pre
            total_delta_peak += shares_peak
            
            if abs(delta_peak) > 0.01 and oi > 100:
                shock_records.append({
                    "strike": K,
                    "right": row["right"],
                    "dte": row["dte"],
                    "oi": oi,
                    "delta_pre": round(delta_pre, 4),
                    "delta_peak": round(delta_peak, 4),
                    "delta_ratio": round(delta_peak / max(abs(delta_pre), 0.001), 1),
                    "shares_pre": int(shares_pre),
                    "shares_peak": int(shares_peak),
                })
        
        shock_records.sort(key=lambda x: abs(x["shares_peak"] - x["shares_pre"]), reverse=True)
        
        print(f"\n  Pre-squeeze total LEAPS delta: {total_delta_pre:>+15,.0f} shares")
        print(f"  Peak-squeeze total LEAPS delta: {total_delta_peak:>+15,.0f} shares")
        print(f"  Forced hedging demand: {total_delta_peak - total_delta_pre:>+15,.0f} shares")
        
        if total_delta_pre != 0:
            amplification = total_delta_peak / total_delta_pre
            print(f"  Amplification factor: {amplification:.1f}×")
        
        print(f"\n  Top 10 Largest Vanna Shocks:")
        print(f"  {'Strike':>8} {'Right':>5} {'DTE':>5} {'OI':>8} {'Δ Pre':>8} {'Δ Peak':>8} {'Ratio':>7} {'Shares ΔΔ':>12}")
        print(f"  {'-'*65}")
        for rec in shock_records[:10]:
            dd = rec["shares_peak"] - rec["shares_pre"]
            print(f"  ${rec['strike']:>7.2f} {rec['right']:>5} {rec['dte']:>5} "
                  f"{rec['oi']:>8,} {rec['delta_pre']:>+8.4f} {rec['delta_peak']:>+8.4f} "
                  f"{rec['delta_ratio']:>6.1f}× {dd:>+12,}")
        
        results.append({
            "event": name,
            "n_leaps": len(leaps),
            "total_leaps_oi": int(leaps["open_interest"].sum()),
            "total_delta_pre": int(total_delta_pre),
            "total_delta_peak": int(total_delta_peak),
            "forced_hedging_shares": int(total_delta_peak - total_delta_pre),
            "amplification": round(total_delta_peak / max(abs(total_delta_pre), 1), 1),
            "top_shocks": shock_records[:10],
        })
    
    return {"test": "vanna_shock", "ticker": ticker, "events": results}


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Rogue Wave Forensic Tests")
    parser.add_argument("--test", choices=["spear_tip", "origination", "vanna_shock", "all"],
                        default="all", help="Which test to run")
    parser.add_argument("--ticker", default="GME", help="Ticker symbol")
    args = parser.parse_args()
    
    ticker = args.ticker.upper()
    all_results = {"ticker": ticker, "tests": {}}
    
    if args.test in ("spear_tip", "all"):
        result = run_spear_tip_test(ticker)
        all_results["tests"]["spear_tip"] = result
    
    if args.test in ("origination", "all"):
        result = run_origination_cohort_test(ticker)
        all_results["tests"]["origination"] = result
    
    if args.test in ("vanna_shock", "all"):
        result = run_vanna_shock_test(ticker)
        all_results["tests"]["vanna_shock"] = result
    
    # Save results
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"rogue_wave_{ticker}_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n  Results saved to: {out_path.name}")


if __name__ == "__main__":
    main()
