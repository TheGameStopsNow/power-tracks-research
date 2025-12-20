#!/usr/bin/env python3
"""
Cross-Symbol Correlation Analysis
==================================

Analyzes synchronized patterns across GME and other meme stocks (AMC, KOSS).
Looks for coordinated timing and LSB patterns that could indicate
cross-symbol covert channels.
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from scipy import stats
import requests

# Configuration
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "samples"
OUTPUT_DIR = Path(__file__).resolve().parent / "results"

SYMBOLS = ["GME", "AMC", "KOSS"]


def load_api_key() -> str:
    """Load Polygon API key from .env file."""
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.startswith("POLYGON_API_KEY="):
                    return line.strip().split("=", 1)[1]
    return os.getenv("POLYGON_API_KEY", "")


def fetch_trades(symbol: str, date: str, api_key: str, limit: int = 50000) -> pd.DataFrame:
    """Fetch trades from Polygon API."""
    url = f"https://api.polygon.io/v3/trades/{symbol}"
    params = {
        "timestamp.gte": f"{date}T09:30:00Z",
        "timestamp.lte": f"{date}T16:00:00Z",
        "limit": limit,
        "apiKey": api_key
    }
    
    records = []
    while True:
        resp = requests.get(url, params=params, timeout=60)
        if resp.status_code != 200:
            print(f"  API error: {resp.status_code}")
            break
        
        data = resp.json()
        results = data.get("results", [])
        records.extend(results)
        
        if len(results) < limit or len(records) >= 100000:
            break
        
        next_url = data.get("next_url")
        if not next_url:
            break
        url = next_url
        params = {"apiKey": api_key}
    
    if not records:
        return pd.DataFrame()
    
    df = pd.DataFrame(records)
    if "sip_timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["sip_timestamp"], unit="ns")
    return df


def calculate_cross_symbol_mi(df1: pd.DataFrame, df2: pd.DataFrame, 
                               time_window_ms: int = 100) -> dict:
    """Calculate mutual information between two symbols' LSB patterns."""
    # Align by time window
    df1["time_bin"] = (df1["timestamp"].astype(int) // (time_window_ms * 1_000_000))
    df2["time_bin"] = (df2["timestamp"].astype(int) // (time_window_ms * 1_000_000))
    
    # Get overlapping time bins
    common_bins = set(df1["time_bin"]) & set(df2["time_bin"])
    
    if len(common_bins) < 100:
        return {"error": "Insufficient overlapping data", "common_bins": len(common_bins)}
    
    # Extract LSBs for common bins
    lsb1 = []
    lsb2 = []
    
    for bin_id in list(common_bins)[:10000]:  # Limit for efficiency
        rows1 = df1[df1["time_bin"] == bin_id]
        rows2 = df2[df2["time_bin"] == bin_id]
        
        if len(rows1) > 0 and len(rows2) > 0:
            lsb1.append(int(rows1.iloc[0]["price"] * 100) % 10)
            lsb2.append(int(rows2.iloc[0]["price"] * 100) % 10)
    
    if len(lsb1) < 100:
        return {"error": "Insufficient aligned data"}
    
    lsb1 = np.array(lsb1)
    lsb2 = np.array(lsb2)
    
    # Calculate mutual information
    joint = pd.crosstab(lsb1, lsb2, normalize=True)
    px = joint.sum(axis=1)
    py = joint.sum(axis=0)
    
    mi = 0
    for i in joint.index:
        for j in joint.columns:
            if joint.loc[i, j] > 0 and px[i] > 0 and py[j] > 0:
                mi += joint.loc[i, j] * np.log2(joint.loc[i, j] / (px[i] * py[j]))
    
    # Correlation of LSB sequences
    correlation = np.corrcoef(lsb1, lsb2)[0, 1]
    
    return {
        "aligned_points": len(lsb1),
        "mutual_information": float(mi),
        "correlation": float(correlation) if not np.isnan(correlation) else 0,
        "lsb1_mean": float(np.mean(lsb1)),
        "lsb2_mean": float(np.mean(lsb2))
    }


def analyze_timing_sync(df1: pd.DataFrame, df2: pd.DataFrame, 
                        symbol1: str, symbol2: str) -> dict:
    """Analyze timing synchronization between two symbols."""
    ts1 = df1["timestamp"].values
    ts2 = df2["timestamp"].values
    
    # Find nearest neighbor timestamps
    sync_gaps = []
    for t in ts1[:1000]:  # Sample for efficiency
        diffs = np.abs(ts2 - t)
        min_diff = np.min(diffs) / 1e6  # Convert to ms
        if min_diff < 1000:  # Within 1 second
            sync_gaps.append(min_diff)
    
    if not sync_gaps:
        return {"error": "No synchronized trades found"}
    
    sync_gaps = np.array(sync_gaps)
    
    return {
        "symbol1": symbol1,
        "symbol2": symbol2,
        "sync_points": len(sync_gaps),
        "mean_gap_ms": float(np.mean(sync_gaps)),
        "median_gap_ms": float(np.median(sync_gaps)),
        "min_gap_ms": float(np.min(sync_gaps)),
        "pct_under_100ms": float(np.mean(sync_gaps < 100) * 100),
        "pct_under_10ms": float(np.mean(sync_gaps < 10) * 100)
    }


def analyze_date(date: str, api_key: str) -> dict:
    """Analyze cross-symbol patterns for a single date."""
    print(f"\n  Fetching data for {date}...")
    
    symbol_data = {}
    for symbol in SYMBOLS:
        df = fetch_trades(symbol, date, api_key)
        if not df.empty:
            print(f"    {symbol}: {len(df)} trades")
            symbol_data[symbol] = df
        else:
            print(f"    {symbol}: No data")
    
    if len(symbol_data) < 2:
        return {"date": date, "error": "Insufficient symbols with data"}
    
    results = {
        "date": date,
        "symbols": list(symbol_data.keys()),
        "trade_counts": {s: len(d) for s, d in symbol_data.items()},
        "cross_mi": {},
        "timing_sync": {}
    }
    
    # Pairwise analysis
    symbols_list = list(symbol_data.keys())
    for i in range(len(symbols_list)):
        for j in range(i + 1, len(symbols_list)):
            s1, s2 = symbols_list[i], symbols_list[j]
            pair = f"{s1}-{s2}"
            
            # Cross-symbol MI
            mi_result = calculate_cross_symbol_mi(symbol_data[s1], symbol_data[s2])
            results["cross_mi"][pair] = mi_result
            
            # Timing sync
            sync_result = analyze_timing_sync(symbol_data[s1], symbol_data[s2], s1, s2)
            results["timing_sync"][pair] = sync_result
    
    return results


def main():
    """Run cross-symbol analysis."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    api_key = load_api_key()
    if not api_key:
        print("POLYGON_API_KEY not found")
        return
    
    # Dates to analyze (use same as GME data)
    dates = [
        "2024-05-13", "2024-05-14", "2024-05-15", "2024-05-16", "2024-05-17"
    ]
    
    print("=" * 60)
    print("CROSS-SYMBOL CORRELATION ANALYSIS")
    print(f"Symbols: {', '.join(SYMBOLS)}")
    print("=" * 60)
    
    results = []
    for date in dates:
        try:
            result = analyze_date(date, api_key)
            results.append(result)
            
            if "error" not in result:
                for pair, mi in result["cross_mi"].items():
                    if "mutual_information" in mi:
                        print(f"    {pair} MI: {mi['mutual_information']:.4f}")
                        
        except Exception as e:
            print(f"  Error: {e}")
            results.append({"date": date, "error": str(e)})
    
    # Save results
    output_file = OUTPUT_DIR / "cross_symbol_results.json"
    with open(output_file, "w") as f:
        json.dump({
            "analysis_timestamp": datetime.now().isoformat(),
            "symbols": SYMBOLS,
            "daily_results": results
        }, f, indent=2, default=str)
    
    # Generate report
    report_file = OUTPUT_DIR / "cross_symbol_report.md"
    with open(report_file, "w") as f:
        f.write("# Cross-Symbol Correlation Analysis\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        f.write(f"**Symbols analyzed**: {', '.join(SYMBOLS)}\n\n")
        
        f.write("## Mutual Information (Price LSB)\n\n")
        f.write("| Date | Pair | MI | Correlation |\n")
        f.write("|------|------|----|--------------|\n")
        for r in results:
            if "error" not in r:
                for pair, mi in r["cross_mi"].items():
                    if "mutual_information" in mi:
                        f.write(f"| {r['date']} | {pair} | {mi['mutual_information']:.4f} | {mi['correlation']:.4f} |\n")
        
        f.write("\n## Timing Synchronization\n\n")
        f.write("| Date | Pair | Sync Points | Median Gap (ms) | <10ms (%) |\n")
        f.write("|------|------|-------------|-----------------|----------|\n")
        for r in results:
            if "error" not in r:
                for pair, sync in r["timing_sync"].items():
                    if "sync_points" in sync:
                        f.write(f"| {r['date']} | {pair} | {sync['sync_points']} | {sync['median_gap_ms']:.1f} | {sync['pct_under_10ms']:.1f}% |\n")
        
        f.write("\n## Interpretation\n\n")
        f.write("> Cross-symbol MI > 0.1 would suggest coordinated LSB patterns.\n")
        f.write("> High timing sync (many trades <10ms apart) could indicate coordinated execution.\n")
    
    print("\n" + "=" * 60)
    print("CROSS-SYMBOL ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"Results saved to: {output_file}")


if __name__ == "__main__":
    main()
