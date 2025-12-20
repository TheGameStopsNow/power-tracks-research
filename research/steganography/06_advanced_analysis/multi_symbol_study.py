#!/usr/bin/env python3
"""
Large-Scale Multi-Symbol Correlation Study
===========================================

Tests 40+ symbols across categories:
- Meme stocks
- High-volatility names
- Tech giants
- Crypto-related
- Commodities
- Various others

Calculates pairwise MI and clusters symbols by correlation pattern.
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
from scipy.cluster.hierarchy import linkage, fcluster
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
OUTPUT_DIR = Path(__file__).resolve().parent / "results"

# All requested symbols (some may not have data)
SYMBOLS = [
    # Meme stocks
    "GME", "AMC", "KOSS", "BBBY", "BB",
    # High volatility / retail favorites
    "TSLA", "NVDA", "META", "NFLX", "PLTR",
    "MSTR", "LYFT", "FUBO", "BYND", "CHWY",
    # Other tickers
    "COST", "U", "BAC", "SIRI", "IHRT", "WBD",
    "NWL", "DJT", "TTEC", "BNED", "GOLD",
    # Tech
    "AAPL", "MSFT", "GOOGL",
    # ETFs/indices proxies
    "SPY", "QQQ",
    # Additional requested (filtering invalid/delisted)
    "IEP", "TR", "CMG", "HOLO", "SLV",
]


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
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            return pd.DataFrame()
        
        data = resp.json()
        results = data.get("results", [])
        
        if not results:
            return pd.DataFrame()
        
        df = pd.DataFrame(results)
        df = df.rename(columns={"t": "timestamp", "c": "price", "v": "volume"})
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["minute"] = df["timestamp"].dt.floor("T")
        return df
    except:
        return pd.DataFrame()


def calculate_mi_fast(prices1: np.ndarray, prices2: np.ndarray) -> float:
    """Fast MI calculation for aligned price arrays."""
    if len(prices1) < 30:
        return np.nan
    
    lsb1 = (prices1 * 100).astype(int) % 10
    lsb2 = (prices2 * 100).astype(int) % 10
    
    joint = np.zeros((10, 10))
    for l1, l2 in zip(lsb1, lsb2):
        joint[l1, l2] += 1
    joint /= len(prices1)
    
    px = joint.sum(axis=1)
    py = joint.sum(axis=0)
    
    mi = 0
    for i in range(10):
        for j in range(10):
            if joint[i, j] > 0 and px[i] > 0 and py[j] > 0:
                mi += joint[i, j] * np.log2(joint[i, j] / (px[i] * py[j]))
    
    return mi


def main():
    """Run large-scale correlation study."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    api_key = load_api_key()
    if not api_key:
        print("POLYGON_API_KEY not found")
        return
    
    date = "2024-05-16"  # High-activity day
    
    print("=" * 70)
    print("LARGE-SCALE MULTI-SYMBOL CORRELATION STUDY")
    print(f"Testing {len(SYMBOLS)} symbols on {date}")
    print("=" * 70)
    
    # Fetch all symbol data
    print("\n1. Fetching data...")
    symbol_data = {}
    
    for symbol in SYMBOLS:
        df = fetch_minute_bars(symbol, date, api_key)
        if not df.empty and len(df) > 100:
            symbol_data[symbol] = df
            print(f"  ✓ {symbol}: {len(df)} bars")
        else:
            print(f"  ✗ {symbol}: No data")
    
    valid_symbols = list(symbol_data.keys())
    n_symbols = len(valid_symbols)
    print(f"\nReceived data for {n_symbols}/{len(SYMBOLS)} symbols")
    
    if n_symbols < 3:
        print("Insufficient data")
        return
    
    # Calculate pairwise MI matrix
    print("\n2. Calculating pairwise MI...")
    mi_matrix = np.zeros((n_symbols, n_symbols))
    pair_results = []
    
    total_pairs = n_symbols * (n_symbols - 1) // 2
    done = 0
    
    for i in range(n_symbols):
        for j in range(i + 1, n_symbols):
            s1, s2 = valid_symbols[i], valid_symbols[j]
            
            # Align by minute
            df1 = symbol_data[s1]
            df2 = symbol_data[s2]
            merged = pd.merge(df1[["minute", "price"]], df2[["minute", "price"]], 
                               on="minute", suffixes=("_1", "_2"))
            
            if len(merged) > 30:
                mi = calculate_mi_fast(merged["price_1"].values, merged["price_2"].values)
                mi_matrix[i, j] = mi
                mi_matrix[j, i] = mi
                
                if not np.isnan(mi):
                    pair_results.append({
                        "pair": f"{s1}-{s2}",
                        "s1": s1,
                        "s2": s2,
                        "mi": mi,
                        "aligned": len(merged)
                    })
            
            done += 1
            if done % 100 == 0:
                print(f"  Processed {done}/{total_pairs} pairs...")
    
    print(f"  Computed {len(pair_results)} valid pairs")
    
    # Sort by MI
    pair_results.sort(key=lambda x: x["mi"], reverse=True)
    
    # Categorize symbols
    categories = {
        "meme": ["GME", "AMC", "KOSS", "BBBY", "BB", "DJT"],
        "tech": ["AAPL", "MSFT", "GOOGL", "NVDA", "META", "NFLX", "TSLA"],
        "etf": ["SPY", "QQQ"],
        "high_vol": ["MSTR", "LYFT", "FUBO", "BYND", "CHWY", "PLTR"],
        "other": []
    }
    
    # Assign category to each symbol
    symbol_category = {}
    for symbol in valid_symbols:
        assigned = False
        for cat, members in categories.items():
            if symbol in members:
                symbol_category[symbol] = cat
                assigned = True
                break
        if not assigned:
            symbol_category[symbol] = "other"
    
    # Category statistics
    category_stats = {}
    for cat in categories.keys():
        cat_symbols = [s for s in valid_symbols if symbol_category[s] == cat]
        cat_mis = []
        for r in pair_results:
            if symbol_category.get(r["s1"]) == cat and symbol_category.get(r["s2"]) == cat:
                cat_mis.append(r["mi"])
        if cat_mis:
            category_stats[cat] = {
                "n_symbols": len(cat_symbols),
                "n_pairs": len(cat_mis),
                "mean_mi": float(np.nanmean(cat_mis)),
                "max_mi": float(np.nanmax(cat_mis)),
                "min_mi": float(np.nanmin(cat_mis))
            }
    
    # Cross-category statistics
    cross_category = []
    for cat1 in categories.keys():
        for cat2 in categories.keys():
            if cat1 >= cat2:
                continue
            cat_mis = []
            for r in pair_results:
                c1 = symbol_category.get(r["s1"])
                c2 = symbol_category.get(r["s2"])
                if (c1 == cat1 and c2 == cat2) or (c1 == cat2 and c2 == cat1):
                    cat_mis.append(r["mi"])
            if cat_mis:
                cross_category.append({
                    "pair": f"{cat1}-{cat2}",
                    "mean_mi": float(np.nanmean(cat_mis)),
                    "n_pairs": len(cat_mis)
                })
    
    # Save results
    results = {
        "date": date,
        "n_symbols": n_symbols,
        "n_pairs": len(pair_results),
        "top_pairs": pair_results[:50],
        "category_stats": category_stats,
        "cross_category": cross_category,
        "all_pairs": pair_results
    }
    
    output_file = OUTPUT_DIR / "multi_symbol_study.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    # Generate report
    generate_report(results, valid_symbols, symbol_category)
    
    print("\n" + "=" * 70)
    print("STUDY COMPLETE")
    print("=" * 70)
    
    print("\nCategory Statistics:")
    for cat, stats in category_stats.items():
        print(f"  {cat}: mean MI = {stats['mean_mi']:.4f} (n={stats['n_pairs']} pairs)")
    
    print(f"\nTop 10 highest MI pairs:")
    for r in pair_results[:10]:
        print(f"  {r['pair']}: MI = {r['mi']:.4f}")


def generate_report(results: dict, symbols: list, symbol_category: dict):
    """Generate markdown report."""
    report_file = OUTPUT_DIR / "multi_symbol_report.md"
    
    with open(report_file, "w") as f:
        f.write("# Large-Scale Multi-Symbol Correlation Study\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        f.write(f"**Date analyzed**: {results['date']}\n")
        f.write(f"**Symbols**: {results['n_symbols']}\n")
        f.write(f"**Pairs analyzed**: {results['n_pairs']}\n\n")
        
        f.write("## Category Statistics\n\n")
        f.write("| Category | # Symbols | Mean MI | Max MI | Min MI |\n")
        f.write("|----------|-----------|---------|--------|--------|\n")
        for cat, stats in results["category_stats"].items():
            f.write(f"| {cat} | {stats['n_symbols']} | {stats['mean_mi']:.4f} | {stats['max_mi']:.4f} | {stats['min_mi']:.4f} |\n")
        
        f.write("\n## Cross-Category Correlations\n\n")
        f.write("| Categories | Mean MI | # Pairs |\n")
        f.write("|------------|---------|--------|\n")
        for item in sorted(results["cross_category"], key=lambda x: x["mean_mi"], reverse=True):
            f.write(f"| {item['pair']} | {item['mean_mi']:.4f} | {item['n_pairs']} |\n")
        
        f.write("\n## Top 30 Highest Correlation Pairs\n\n")
        f.write("| Pair | MI | Rating |\n")
        f.write("|------|----|---------|\n")
        for r in results["top_pairs"][:30]:
            rating = "🔴 HIGH" if r["mi"] > 0.15 else ("🟡 MED" if r["mi"] > 0.10 else "🟢 LOW")
            f.write(f"| {r['pair']} | {r['mi']:.4f} | {rating} |\n")
        
        f.write("\n## Interpretation\n\n")
        
        # Find which category has highest internal MI
        if results["category_stats"]:
            top_cat = max(results["category_stats"].items(), key=lambda x: x[1]["mean_mi"])
            f.write(f"**Highest intra-category correlation**: {top_cat[0]} (mean MI = {top_cat[1]['mean_mi']:.4f})\n\n")
        
        meme_mi = results["category_stats"].get("meme", {}).get("mean_mi", 0)
        tech_mi = results["category_stats"].get("tech", {}).get("mean_mi", 0)
        
        if meme_mi > tech_mi * 1.3:
            f.write("> ⚠️ **Meme stocks show significantly higher intra-category correlation than tech stocks**\n")
        elif tech_mi > meme_mi * 1.3:
            f.write("> ✅ **Tech stocks show higher correlation than meme stocks** - meme patterns are not anomalous\n")
        else:
            f.write("> ✅ **Correlation levels are similar across categories** - no evidence of meme-specific anomalies\n")
    
    print(f"Report saved to: {report_file}")


if __name__ == "__main__":
    main()
