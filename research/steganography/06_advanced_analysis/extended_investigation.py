#!/usr/bin/env python3
"""
Extended Investigation: Control Comparison & Intraday Patterns
==============================================================

1. Compare meme stock correlations to non-meme pairs (AAPL-MSFT)
2. Analyze intraday time patterns of correlation
3. Break down correlation by time window
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

MEME_SYMBOLS = ["GME", "KOSS", "AMC"]
CONTROL_SYMBOLS = ["AAPL", "MSFT", "GOOGL"]


def load_api_key() -> str:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.startswith("POLYGON_API_KEY="):
                    return line.strip().split("=", 1)[1]
    return os.getenv("POLYGON_API_KEY", "")


def fetch_minute_bars(symbol: str, date: str, api_key: str) -> pd.DataFrame:
    """Fetch minute bars from Polygon API."""
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{date}/{date}"
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 50000,
        "apiKey": api_key
    }
    
    resp = requests.get(url, params=params, timeout=60)
    if resp.status_code != 200:
        return pd.DataFrame()
    
    data = resp.json()
    results = data.get("results", [])
    
    if not results:
        return pd.DataFrame()
    
    df = pd.DataFrame(results)
    df = df.rename(columns={"t": "timestamp", "c": "price", "v": "volume"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def calculate_mi(df1: pd.DataFrame, df2: pd.DataFrame) -> dict:
    """Calculate mutual information between aligned price LSBs."""
    # Align by minute
    df1["minute"] = df1["timestamp"].dt.floor("T")
    df2["minute"] = df2["timestamp"].dt.floor("T")
    
    merged = pd.merge(df1[["minute", "price"]], df2[["minute", "price"]], 
                       on="minute", suffixes=("_1", "_2"))
    
    if len(merged) < 50:
        return {"error": "Insufficient aligned data", "aligned": len(merged)}
    
    lsb1 = (merged["price_1"] * 100).astype(int) % 10
    lsb2 = (merged["price_2"] * 100).astype(int) % 10
    
    # Calculate MI
    joint = pd.crosstab(lsb1, lsb2, normalize=True)
    px = joint.sum(axis=1)
    py = joint.sum(axis=0)
    
    mi = 0
    for i in joint.index:
        for j in joint.columns:
            if joint.loc[i, j] > 0 and px[i] > 0 and py[j] > 0:
                mi += joint.loc[i, j] * np.log2(joint.loc[i, j] / (px[i] * py[j]))
    
    # Also calculate Pearson correlation
    corr = np.corrcoef(lsb1, lsb2)[0, 1]
    
    return {
        "aligned_minutes": len(merged),
        "mutual_information": float(mi),
        "correlation": float(corr) if not np.isnan(corr) else 0
    }


def analyze_by_time_window(df1: pd.DataFrame, df2: pd.DataFrame, s1: str, s2: str) -> dict:
    """Analyze correlation by time of day."""
    df1["hour"] = df1["timestamp"].dt.hour
    df2["hour"] = df2["timestamp"].dt.hour
    
    windows = {
        "open_15min": (9, 10, 30, 45),  # 9:30-9:45
        "morning": (10, 12, 0, 0),
        "midday": (12, 14, 0, 0),
        "afternoon": (14, 15, 0, 30),
        "close_15min": (15, 16, 45, 0)  # 3:45-4:00
    }
    
    results = {}
    for name, (h_start, h_end, m_start, m_end) in windows.items():
        if m_start > 0 or m_end > 0:
            d1 = df1[((df1["hour"] == h_start) & (df1["timestamp"].dt.minute >= m_start)) |
                      ((df1["hour"] == h_end) & (df1["timestamp"].dt.minute < m_end))]
            d2 = df2[((df2["hour"] == h_start) & (df2["timestamp"].dt.minute >= m_start)) |
                      ((df2["hour"] == h_end) & (df2["timestamp"].dt.minute < m_end))]
        else:
            d1 = df1[(df1["hour"] >= h_start) & (df1["hour"] < h_end)]
            d2 = df2[(df2["hour"] >= h_start) & (df2["hour"] < h_end)]
        
        if len(d1) > 10 and len(d2) > 10:
            mi_result = calculate_mi(d1, d2)
            if "mutual_information" in mi_result:
                results[name] = mi_result["mutual_information"]
    
    return results


def main():
    """Run extended investigation."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    api_key = load_api_key()
    if not api_key:
        print("POLYGON_API_KEY not found")
        return
    
    # Analyze multiple dates
    dates = ["2024-05-14", "2024-05-15", "2024-05-16"]
    
    print("=" * 60)
    print("EXTENDED INVESTIGATION")
    print("=" * 60)
    
    results = {
        "meme_pairs": [],
        "control_pairs": [],
        "intraday_patterns": []
    }
    
    for date in dates:
        print(f"\n>>> {date}")
        
        # Fetch meme stocks
        meme_data = {}
        print("  Meme stocks:")
        for symbol in MEME_SYMBOLS:
            df = fetch_minute_bars(symbol, date, api_key)
            if not df.empty:
                print(f"    {symbol}: {len(df)} bars")
                meme_data[symbol] = df
        
        # Fetch control stocks
        control_data = {}
        print("  Control stocks:")
        for symbol in CONTROL_SYMBOLS:
            df = fetch_minute_bars(symbol, date, api_key)
            if not df.empty:
                print(f"    {symbol}: {len(df)} bars")
                control_data[symbol] = df
        
        # Calculate meme pair MIs
        print("\n  Meme pair correlations:")
        for i, s1 in enumerate(list(meme_data.keys())):
            for s2 in list(meme_data.keys())[i+1:]:
                mi_result = calculate_mi(meme_data[s1], meme_data[s2])
                if "mutual_information" in mi_result:
                    print(f"    {s1}-{s2}: MI={mi_result['mutual_information']:.4f}")
                    results["meme_pairs"].append({
                        "date": date,
                        "pair": f"{s1}-{s2}",
                        "mi": mi_result["mutual_information"],
                        "corr": mi_result["correlation"]
                    })
                    
                    # Intraday breakdown
                    intraday = analyze_by_time_window(meme_data[s1], meme_data[s2], s1, s2)
                    if intraday:
                        results["intraday_patterns"].append({
                            "date": date,
                            "pair": f"{s1}-{s2}",
                            "windows": intraday
                        })
        
        # Calculate control pair MIs
        print("\n  Control pair correlations:")
        for i, s1 in enumerate(list(control_data.keys())):
            for s2 in list(control_data.keys())[i+1:]:
                mi_result = calculate_mi(control_data[s1], control_data[s2])
                if "mutual_information" in mi_result:
                    print(f"    {s1}-{s2}: MI={mi_result['mutual_information']:.4f}")
                    results["control_pairs"].append({
                        "date": date,
                        "pair": f"{s1}-{s2}",
                        "mi": mi_result["mutual_information"],
                        "corr": mi_result["correlation"]
                    })
    
    # Save results
    output_file = OUTPUT_DIR / "extended_investigation.json"
    with open(output_file, "w") as f:
        json.dump({
            "analysis_timestamp": datetime.now().isoformat(),
            "results": results
        }, f, indent=2)
    
    # Generate report
    generate_report(results)
    
    print("\n" + "=" * 60)
    print("INVESTIGATION COMPLETE")
    print("=" * 60)
    
    # Print summary
    meme_mis = [r["mi"] for r in results["meme_pairs"]]
    control_mis = [r["mi"] for r in results["control_pairs"]]
    
    if meme_mis and control_mis:
        print(f"\nMeme stocks avg MI: {np.mean(meme_mis):.4f}")
        print(f"Control stocks avg MI: {np.mean(control_mis):.4f}")
        print(f"Ratio: {np.mean(meme_mis)/np.mean(control_mis):.2f}x")


def generate_report(results: dict):
    """Generate markdown report."""
    report_file = OUTPUT_DIR / "extended_investigation_report.md"
    
    with open(report_file, "w") as f:
        f.write("# Extended Investigation: Meme vs Control Stocks\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        # Summary statistics
        meme_mis = [r["mi"] for r in results["meme_pairs"]]
        control_mis = [r["mi"] for r in results["control_pairs"]]
        
        if meme_mis and control_mis:
            f.write("## Summary\n\n")
            f.write("| Category | Mean MI | Max MI | Min MI |\n")
            f.write("|----------|---------|--------|--------|\n")
            f.write(f"| **Meme stocks** | {np.mean(meme_mis):.4f} | {max(meme_mis):.4f} | {min(meme_mis):.4f} |\n")
            f.write(f"| Control stocks | {np.mean(control_mis):.4f} | {max(control_mis):.4f} | {min(control_mis):.4f} |\n\n")
            
            ratio = np.mean(meme_mis) / np.mean(control_mis) if np.mean(control_mis) > 0 else 0
            f.write(f"**Meme stocks show {ratio:.1f}x higher correlation than control stocks**\n\n")
        
        f.write("## Meme Stock Pairs\n\n")
        f.write("| Date | Pair | MI | Correlation |\n")
        f.write("|------|------|----|--------------|\n")
        for r in sorted(results["meme_pairs"], key=lambda x: x["mi"], reverse=True):
            rating = "🔴" if r["mi"] > 0.15 else ("🟡" if r["mi"] > 0.08 else "🟢")
            f.write(f"| {r['date']} | {r['pair']} | {r['mi']:.4f} {rating} | {r['corr']:.4f} |\n")
        
        f.write("\n## Control Stock Pairs\n\n")
        f.write("| Date | Pair | MI | Correlation |\n")
        f.write("|------|------|----|--------------|\n")
        for r in sorted(results["control_pairs"], key=lambda x: x["mi"], reverse=True):
            f.write(f"| {r['date']} | {r['pair']} | {r['mi']:.4f} | {r['corr']:.4f} |\n")
        
        f.write("\n## Intraday Patterns\n\n")
        f.write("MI by time of day (meme stocks):\n\n")
        
        # Group by pair
        pair_windows = {}
        for item in results["intraday_patterns"]:
            pair = item["pair"]
            if pair not in pair_windows:
                pair_windows[pair] = []
            pair_windows[pair].append(item)
        
        for pair, items in pair_windows.items():
            f.write(f"### {pair}\n\n")
            f.write("| Date | Open | Morning | Midday | Afternoon | Close |\n")
            f.write("|------|------|---------|--------|-----------|-------|\n")
            for item in items:
                w = item["windows"]
                def fmt(val):
                    return f"{val:.4f}" if isinstance(val, (int, float)) else "-"
                f.write(f"| {item['date']} | {fmt(w.get('open_15min'))} | {fmt(w.get('morning'))} | {fmt(w.get('midday'))} | {fmt(w.get('afternoon'))} | {fmt(w.get('close_15min'))} |\n")
            f.write("\n")
        
        f.write("## Interpretation\n\n")
        if meme_mis and control_mis and np.mean(meme_mis) > np.mean(control_mis) * 1.5:
            f.write("> **⚠️ Meme stocks show significantly higher LSB correlation than normal stocks.**\n\n")
            f.write("This confirms the anomaly is specific to meme stocks, not a general market artifact.\n")
        else:
            f.write("> Correlation levels are similar between meme and control stocks.\n")
    
    print(f"Report saved to: {report_file}")


if __name__ == "__main__":
    main()
