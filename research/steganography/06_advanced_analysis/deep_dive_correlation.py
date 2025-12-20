#!/usr/bin/env python3
"""
Deep Dive: GME-KOSS-KOPN Correlation Analysis
==============================================

Investigates the unexpectedly high mutual information between meme stock
price LSBs. Adds KOPN and expands analysis to understand the correlation.

Key questions:
1. Is the correlation consistent across time windows?
2. Does it vary by venue?
3. What specific LSB digits are correlated?
4. Is there a time lag in the correlation?
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
OUTPUT_DIR = Path(__file__).resolve().parent / "results"

SYMBOLS = ["GME", "KOSS", "KOPN", "AMC"]


def load_api_key() -> str:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.startswith("POLYGON_API_KEY="):
                    return line.strip().split("=", 1)[1]
    return os.getenv("POLYGON_API_KEY", "")


def fetch_trades(symbol: str, date: str, api_key: str, limit: int = 50000) -> pd.DataFrame:
    """Fetch trades from Polygon API."""
    # Use v2 aggs endpoint for minute bars (more reliable)
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{date}/{date}"
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 50000,
        "apiKey": api_key
    }
    
    resp = requests.get(url, params=params, timeout=60)
    if resp.status_code != 200:
        print(f"    API error for {symbol}: {resp.status_code}")
        return pd.DataFrame()
    
    data = resp.json()
    results = data.get("results", [])
    
    if not results:
        return pd.DataFrame()
    
    df = pd.DataFrame(results)
    df = df.rename(columns={"t": "timestamp", "c": "price", "v": "volume"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def calculate_lsb_joint_distribution(df1: pd.DataFrame, df2: pd.DataFrame, 
                                      time_window_ms: int = 100) -> dict:
    """Calculate detailed LSB joint distribution."""
    df1["time_bin"] = (df1["timestamp"].astype(int) // (time_window_ms * 1_000_000))
    df2["time_bin"] = (df2["timestamp"].astype(int) // (time_window_ms * 1_000_000))
    
    common_bins = set(df1["time_bin"]) & set(df2["time_bin"])
    
    if len(common_bins) < 100:
        return {"error": "Insufficient data"}
    
    lsb1, lsb2 = [], []
    for bin_id in list(common_bins)[:20000]:
        rows1 = df1[df1["time_bin"] == bin_id]
        rows2 = df2[df2["time_bin"] == bin_id]
        if len(rows1) > 0 and len(rows2) > 0:
            lsb1.append(int(rows1.iloc[0]["price"] * 100) % 10)
            lsb2.append(int(rows2.iloc[0]["price"] * 100) % 10)
    
    lsb1, lsb2 = np.array(lsb1), np.array(lsb2)
    
    # Joint distribution matrix
    joint_matrix = np.zeros((10, 10))
    for l1, l2 in zip(lsb1, lsb2):
        joint_matrix[l1, l2] += 1
    joint_matrix /= len(lsb1)
    
    # Mutual Information
    px = joint_matrix.sum(axis=1)
    py = joint_matrix.sum(axis=0)
    mi = 0
    for i in range(10):
        for j in range(10):
            if joint_matrix[i, j] > 0 and px[i] > 0 and py[j] > 0:
                mi += joint_matrix[i, j] * np.log2(joint_matrix[i, j] / (px[i] * py[j]))
    
    # Find strongest correlations
    deviation = joint_matrix - np.outer(px, py)
    max_dev_idx = np.unravel_index(np.argmax(np.abs(deviation)), deviation.shape)
    
    return {
        "aligned_points": len(lsb1),
        "mutual_information": float(mi),
        "max_deviation": {
            "lsb1": int(max_dev_idx[0]),
            "lsb2": int(max_dev_idx[1]),
            "observed": float(joint_matrix[max_dev_idx]),
            "expected": float(px[max_dev_idx[0]] * py[max_dev_idx[1]]),
            "ratio": float(joint_matrix[max_dev_idx] / (px[max_dev_idx[0]] * py[max_dev_idx[1]] + 1e-10))
        },
        "joint_matrix": joint_matrix.tolist()
    }


def analyze_lag_correlation(df1: pd.DataFrame, df2: pd.DataFrame, 
                            max_lag_ms: int = 1000) -> dict:
    """Check if correlation appears with a time lag."""
    df1 = df1.sort_values("timestamp")
    df2 = df2.sort_values("timestamp")
    
    lags = [0, 10, 50, 100, 200, 500, 1000]
    mi_by_lag = {}
    
    for lag in lags:
        df2_lagged = df2.copy()
        df2_lagged["timestamp"] = df2_lagged["timestamp"] + pd.Timedelta(milliseconds=lag)
        
        result = calculate_lsb_joint_distribution(df1, df2_lagged, time_window_ms=100)
        if "mutual_information" in result:
            mi_by_lag[lag] = result["mutual_information"]
    
    if not mi_by_lag:
        return {"error": "No lag data"}
    
    best_lag = max(mi_by_lag, key=mi_by_lag.get)
    
    return {
        "mi_by_lag_ms": mi_by_lag,
        "best_lag_ms": best_lag,
        "best_mi": mi_by_lag[best_lag],
        "interpretation": "Significant lag" if best_lag > 0 and mi_by_lag[best_lag] > mi_by_lag.get(0, 0) * 1.2 else "No lag"
    }


def analyze_by_time_window(df1: pd.DataFrame, df2: pd.DataFrame) -> dict:
    """Analyze if correlation varies by time of day."""
    df1["hour"] = df1["timestamp"].dt.hour
    df2["hour"] = df2["timestamp"].dt.hour
    
    windows = {
        "open": (9, 10),
        "midday": (11, 14),
        "close": (15, 16)
    }
    
    results = {}
    for name, (start, end) in windows.items():
        d1 = df1[(df1["hour"] >= start) & (df1["hour"] < end)]
        d2 = df2[(df2["hour"] >= start) & (df2["hour"] < end)]
        
        if len(d1) > 1000 and len(d2) > 1000:
            mi_result = calculate_lsb_joint_distribution(d1, d2)
            if "mutual_information" in mi_result:
                results[name] = mi_result["mutual_information"]
    
    return results


def main():
    """Run deep dive analysis."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    api_key = load_api_key()
    if not api_key:
        print("POLYGON_API_KEY not found")
        return
    
    # Focus on the high-correlation days
    dates = ["2024-05-15", "2024-05-16", "2024-05-17"]
    
    print("=" * 60)
    print("DEEP DIVE: GME-KOSS-KOPN CORRELATION")
    print("=" * 60)
    
    results = []
    
    for date in dates:
        print(f"\n>>> Analyzing {date}...")
        
        symbol_data = {}
        for symbol in SYMBOLS:
            df = fetch_trades(symbol, date, api_key)
            if not df.empty:
                print(f"  {symbol}: {len(df):,} trades")
                symbol_data[symbol] = df
            else:
                print(f"  {symbol}: No data")
        
        if len(symbol_data) < 2:
            continue
        
        day_result = {"date": date, "pairwise": {}}
        
        # Pairwise analysis
        symbols_list = list(symbol_data.keys())
        for i in range(len(symbols_list)):
            for j in range(i + 1, len(symbols_list)):
                s1, s2 = symbols_list[i], symbols_list[j]
                pair = f"{s1}-{s2}"
                
                print(f"\n  Analyzing {pair}...")
                
                # Detailed joint distribution
                joint = calculate_lsb_joint_distribution(symbol_data[s1], symbol_data[s2])
                
                # Lag analysis
                lag = analyze_lag_correlation(symbol_data[s1], symbol_data[s2])
                
                # Time window analysis
                windows = analyze_by_time_window(symbol_data[s1], symbol_data[s2])
                
                day_result["pairwise"][pair] = {
                    "joint_distribution": joint,
                    "lag_analysis": lag,
                    "time_windows": windows
                }
                
                if "mutual_information" in joint:
                    print(f"    MI: {joint['mutual_information']:.4f}")
                    if "max_deviation" in joint:
                        dev = joint["max_deviation"]
                        print(f"    Strongest: {s1}:{dev['lsb1']} <-> {s2}:{dev['lsb2']} (ratio: {dev['ratio']:.2f})")
        
        results.append(day_result)
    
    # Save results
    output_file = OUTPUT_DIR / "deep_dive_correlation.json"
    with open(output_file, "w") as f:
        json.dump({
            "analysis_timestamp": datetime.now().isoformat(),
            "symbols": SYMBOLS,
            "dates": dates,
            "results": results
        }, f, indent=2, default=str)
    
    # Generate report
    generate_report(results)
    
    print("\n" + "=" * 60)
    print("DEEP DIVE COMPLETE")
    print("=" * 60)


def generate_report(results: list):
    """Generate detailed markdown report."""
    report_file = OUTPUT_DIR / "deep_dive_report.md"
    
    with open(report_file, "w") as f:
        f.write("# Deep Dive: Cross-Symbol LSB Correlation\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        f.write(f"**Symbols**: {', '.join(SYMBOLS)}\n\n")
        
        f.write("## Key Findings\n\n")
        
        # Collect all pair MIs
        all_pairs = {}
        for r in results:
            for pair, data in r["pairwise"].items():
                if "joint_distribution" in data and "mutual_information" in data["joint_distribution"]:
                    mi = data["joint_distribution"]["mutual_information"]
                    if pair not in all_pairs:
                        all_pairs[pair] = []
                    all_pairs[pair].append({"date": r["date"], "mi": mi})
        
        f.write("### Mutual Information by Pair\n\n")
        f.write("| Pair | Date | MI | Rating |\n")
        f.write("|------|------|----|---------|\n")
        for pair, entries in sorted(all_pairs.items(), key=lambda x: max(e["mi"] for e in x[1]), reverse=True):
            for e in entries:
                rating = "🔴 HIGH" if e["mi"] > 0.2 else ("🟡 MEDIUM" if e["mi"] > 0.1 else "🟢 LOW")
                f.write(f"| {pair} | {e['date']} | {e['mi']:.4f} | {rating} |\n")
        
        f.write("\n## Detailed Analysis\n\n")
        
        for r in results:
            f.write(f"### {r['date']}\n\n")
            for pair, data in r["pairwise"].items():
                if "joint_distribution" not in data:
                    continue
                    
                joint = data["joint_distribution"]
                if "error" in joint:
                    continue
                
                f.write(f"#### {pair}\n\n")
                f.write(f"- **MI**: {joint['mutual_information']:.4f}\n")
                
                if "max_deviation" in joint:
                    dev = joint["max_deviation"]
                    symbols = pair.split("-")
                    f.write(f"- **Strongest correlation**: {symbols[0]} cents={dev['lsb1']} ↔ {symbols[1]} cents={dev['lsb2']}\n")
                    f.write(f"  - Observed: {dev['observed']:.4f}, Expected: {dev['expected']:.4f}, Ratio: {dev['ratio']:.2f}x\n")
                
                if "time_windows" in data and data["time_windows"]:
                    f.write("- **By time window**:\n")
                    for window, mi in data["time_windows"].items():
                        f.write(f"  - {window}: MI = {mi:.4f}\n")
                
                f.write("\n")
        
        f.write("## Interpretation\n\n")
        f.write("> **High MI between different stocks' price LSBs is anomalous.**\n\n")
        f.write("Possible explanations:\n")
        f.write("1. **Shared market maker** - Same MM handling multiple meme stocks\n")
        f.write("2. **Correlated retail flow** - Same apps/brokers routing similar orders\n")
        f.write("3. **Algorithmic correlation** - HFT strategies linking meme stock prices\n")
        f.write("4. **Exchange rounding** - Similar tick/lot constraints\n")
    
    print(f"Report saved to: {report_file}")


if __name__ == "__main__":
    main()
