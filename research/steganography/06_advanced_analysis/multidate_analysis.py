#!/usr/bin/env python3
"""
Multi-Date Multi-Symbol Analysis
================================

Runs the correlation study across multiple dates to confirm patterns
and filter out single-day anomalies like CMG.
"""

import os
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import requests

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
OUTPUT_DIR = Path(__file__).resolve().parent / "results"

# Focus on reliable symbols with good liquidity
SYMBOLS = [
    "GME", "AMC", "KOSS", "BB", "DJT",
    "TSLA", "NVDA", "META", "NFLX", "PLTR",
    "MSTR", "LYFT", "FUBO", "BYND", "CHWY",
    "AAPL", "MSFT", "GOOGL", "SPY", "QQQ",
    "BAC", "SIRI", "GOLD", "SLV", "U", "HOLO"
]

DATES = ["2024-05-14", "2024-05-15", "2024-05-16", "2024-05-17", "2024-05-20"]


def load_api_key() -> str:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.startswith("POLYGON_API_KEY="):
                    return line.strip().split("=", 1)[1]
    return ""


def fetch_bars(symbol: str, date: str, api_key: str) -> pd.DataFrame:
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{date}/{date}"
    resp = requests.get(url, params={"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key}, timeout=30)
    if resp.status_code != 200:
        return pd.DataFrame()
    results = resp.json().get("results", [])
    if not results:
        return pd.DataFrame()
    df = pd.DataFrame(results)
    df = df.rename(columns={"t": "timestamp", "c": "price"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df["minute"] = df["timestamp"].dt.floor("T")
    return df


def calculate_mi(prices1, prices2):
    if len(prices1) < 50:
        return np.nan
    lsb1 = (prices1 * 100).astype(int) % 10
    lsb2 = (prices2 * 100).astype(int) % 10
    joint = np.zeros((10, 10))
    for l1, l2 in zip(lsb1, lsb2):
        joint[l1, l2] += 1
    joint /= len(prices1)
    px, py = joint.sum(axis=1), joint.sum(axis=0)
    mi = 0
    for i in range(10):
        for j in range(10):
            if joint[i, j] > 0 and px[i] > 0 and py[j] > 0:
                mi += joint[i, j] * np.log2(joint[i, j] / (px[i] * py[j]))
    return mi


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    api_key = load_api_key()
    
    print("=" * 70)
    print("MULTI-DATE CORRELATION CONSISTENCY CHECK")
    print(f"Symbols: {len(SYMBOLS)}, Dates: {len(DATES)}")
    print("=" * 70)
    
    # Track MI by pair across dates
    pair_mi_history = {}
    
    for date in DATES:
        print(f"\n>>> {date}")
        
        symbol_data = {}
        for symbol in SYMBOLS:
            df = fetch_bars(symbol, date, api_key)
            if not df.empty and len(df) > 200:  # Require 200+ bars for reliability
                symbol_data[symbol] = df
        
        print(f"  {len(symbol_data)}/{len(SYMBOLS)} symbols with sufficient data")
        
        syms = list(symbol_data.keys())
        for i in range(len(syms)):
            for j in range(i + 1, len(syms)):
                s1, s2 = syms[i], syms[j]
                pair = tuple(sorted([s1, s2]))
                
                merged = pd.merge(symbol_data[s1][["minute", "price"]], 
                                   symbol_data[s2][["minute", "price"]], 
                                   on="minute", suffixes=("_1", "_2"))
                
                if len(merged) > 50:
                    mi = calculate_mi(merged["price_1"].values, merged["price_2"].values)
                    if not np.isnan(mi):
                        if pair not in pair_mi_history:
                            pair_mi_history[pair] = []
                        pair_mi_history[pair].append({"date": date, "mi": mi})
    
    # Calculate consistency (std of MI) and mean
    consistent_pairs = []
    for pair, history in pair_mi_history.items():
        if len(history) >= 3:  # Need at least 3 dates
            mis = [h["mi"] for h in history]
            consistent_pairs.append({
                "pair": f"{pair[0]}-{pair[1]}",
                "mean_mi": np.mean(mis),
                "std_mi": np.std(mis),
                "n_dates": len(history),
                "consistency": np.mean(mis) / (np.std(mis) + 0.01)  # Signal-to-noise
            })
    
    # Sort by mean MI
    consistent_pairs.sort(key=lambda x: x["mean_mi"], reverse=True)
    
    # Separate meme pairs
    meme = ["GME", "AMC", "KOSS", "BB", "DJT"]
    meme_pairs = [p for p in consistent_pairs if p["pair"].split("-")[0] in meme and p["pair"].split("-")[1] in meme]
    non_meme_pairs = [p for p in consistent_pairs if p not in meme_pairs]
    
    # Generate report
    with open(OUTPUT_DIR / "multidate_report.md", "w") as f:
        f.write("# Multi-Date Correlation Consistency\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        f.write(f"**Dates**: {', '.join(DATES)}\n\n")
        
        f.write("## Top 20 Most Consistently Correlated Pairs\n\n")
        f.write("| Pair | Mean MI | Std | Consistency | Meme? |\n")
        f.write("|------|---------|-----|-------------|-------|\n")
        for p in consistent_pairs[:20]:
            is_meme = "✓" if p in meme_pairs else ""
            f.write(f"| {p['pair']} | {p['mean_mi']:.4f} | {p['std_mi']:.4f} | {p['consistency']:.2f} | {is_meme} |\n")
        
        f.write("\n## Meme Stock Pairs Only\n\n")
        f.write("| Pair | Mean MI | Std | Consistency |\n")
        f.write("|------|---------|-----|-------------|\n")
        for p in sorted(meme_pairs, key=lambda x: x["mean_mi"], reverse=True)[:10]:
            f.write(f"| {p['pair']} | {p['mean_mi']:.4f} | {p['std_mi']:.4f} | {p['consistency']:.2f} |\n")
        
        f.write("\n## Statistics\n\n")
        meme_mi = [p["mean_mi"] for p in meme_pairs] if meme_pairs else [0]
        non_meme_mi = [p["mean_mi"] for p in non_meme_pairs] if non_meme_pairs else [0]
        f.write(f"- Meme pairs mean MI: **{np.mean(meme_mi):.4f}**\n")
        f.write(f"- Non-meme pairs mean MI: **{np.mean(non_meme_mi):.4f}**\n")
        f.write(f"- Ratio: **{np.mean(meme_mi)/np.mean(non_meme_mi):.2f}x**\n")
    
    print("\n" + "=" * 70)
    print("COMPLETE")
    print("=" * 70)
    print(f"Meme pairs mean MI: {np.mean(meme_mi):.4f}")
    print(f"Non-meme pairs mean MI: {np.mean(non_meme_mi):.4f}")
    print(f"\nTop 5 most correlated pairs:")
    for p in consistent_pairs[:5]:
        print(f"  {p['pair']}: {p['mean_mi']:.4f}")


if __name__ == "__main__":
    main()
