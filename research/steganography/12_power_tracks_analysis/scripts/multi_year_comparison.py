#!/usr/bin/env python3
"""
Multi-Year Comparison Analysis
===============================

Compares burst patterns across multiple years to test temporal stability:
1. Are 2023 patterns similar to 2024?
2. Has the edge decayed or improved?
3. Regime changes over time
"""

import sys
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
EXPANDED_DIR = BASE_DIR / "data" / "expanded_bars"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "results"


def detect_burst_for_day(df: pd.DataFrame) -> dict:
    """Detect if a burst occurred."""
    if len(df) < 100:
        return {"is_burst": False, "volume_spike": 0, "price_range": 0}
    
    mean_vol = df['volume'].mean()
    max_vol = df['volume'].max()
    volume_spike = max_vol / mean_vol if mean_vol > 0 else 0
    
    price_range = (df['high'].max() - df['low'].min()) / df['open'].iloc[0]
    
    is_burst = volume_spike > 2.5 and price_range > 0.03
    
    return {
        "is_burst": is_burst,
        "volume_spike": float(volume_spike),
        "price_range": float(price_range),
        "daily_return": float((df['close'].iloc[-1] / df['open'].iloc[0] - 1)) if len(df) > 0 else 0
    }


def analyze_by_year(symbol_dir: Path) -> dict:
    """Analyze burst patterns by year."""
    
    csv_files = sorted(symbol_dir.glob("*.csv"))
    if not csv_files:
        return {"error": "No data"}
    
    yearly_data = defaultdict(list)
    
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            if 'close' not in df.columns:
                continue
            
            date_str = csv_file.stem.split("_")[1]
            year = date_str.split("-")[0]
            
            burst_info = detect_burst_for_day(df)
            burst_info["date"] = date_str
            
            yearly_data[year].append(burst_info)
            
        except Exception as e:
            continue
    
    # Calculate yearly statistics
    yearly_stats = {}
    for year, data in yearly_data.items():
        if not data:
            continue
            
        df_year = pd.DataFrame(data)
        
        bursts = df_year['is_burst'].sum()
        total_days = len(df_year)
        
        # Calculate returns on burst days vs non-burst days
        burst_days = df_year[df_year['is_burst']]
        non_burst_days = df_year[~df_year['is_burst']]
        
        yearly_stats[year] = {
            "total_days": total_days,
            "burst_days": int(bursts),
            "burst_rate": bursts / total_days if total_days > 0 else 0,
            "avg_volume_spike": float(df_year['volume_spike'].mean()),
            "avg_price_range": float(df_year['price_range'].mean()),
            "burst_day_return": float(burst_days['daily_return'].mean()) if len(burst_days) > 0 else 0,
            "non_burst_day_return": float(non_burst_days['daily_return'].mean()) if len(non_burst_days) > 0 else 0,
            "burst_day_return_std": float(burst_days['daily_return'].std()) if len(burst_days) > 0 else 0,
        }
    
    return {
        "symbol": symbol_dir.name,
        "yearly_stats": yearly_stats
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("MULTI-YEAR COMPARISON ANALYSIS")
    print("Are burst patterns consistent across years?")
    print("=" * 70)
    
    if not EXPANDED_DIR.exists():
        print(f"No data at {EXPANDED_DIR}")
        return
    
    symbol_dirs = [d for d in EXPANDED_DIR.iterdir() if d.is_dir()]
    
    if not symbol_dirs:
        print("No symbol data found")
        return
    
    all_results = []
    
    for symbol_dir in sorted(symbol_dirs):
        print(f"\n>>> {symbol_dir.name}")
        result = analyze_by_year(symbol_dir)
        all_results.append(result)
        
        if "yearly_stats" in result:
            for year, stats in sorted(result["yearly_stats"].items()):
                print(f"  {year}:")
                print(f"    Days: {stats['total_days']}, Bursts: {stats['burst_days']} ({stats['burst_rate']:.1%})")
                print(f"    Avg vol spike: {stats['avg_volume_spike']:.1f}x, Avg range: {stats['avg_price_range']:.1%}")
                print(f"    Burst day return: {stats['burst_day_return']:.2%}, Non-burst: {stats['non_burst_day_return']:.2%}")
    
    # Cross-year comparison
    print("\n" + "=" * 70)
    print("YEAR-OVER-YEAR COMPARISON")
    print("=" * 70)
    
    for result in all_results:
        if "yearly_stats" not in result:
            continue
            
        symbol = result["symbol"]
        years = sorted(result["yearly_stats"].keys())
        
        if len(years) >= 2:
            print(f"\n{symbol}:")
            for i in range(1, len(years)):
                y1, y2 = years[i-1], years[i]
                s1, s2 = result["yearly_stats"][y1], result["yearly_stats"][y2]
                
                rate_change = s2["burst_rate"] - s1["burst_rate"]
                return_change = s2["burst_day_return"] - s1["burst_day_return"]
                
                print(f"  {y1} → {y2}:")
                print(f"    Burst rate: {s1['burst_rate']:.1%} → {s2['burst_rate']:.1%} ({rate_change:+.1%})")
                print(f"    Burst return: {s1['burst_day_return']:.2%} → {s2['burst_day_return']:.2%} ({return_change:+.2%})")
    
    # Save results
    with open(OUTPUT_DIR / "multi_year_comparison.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": all_results
        }, f, indent=2, default=str)
    
    # Generate report
    with open(OUTPUT_DIR / "multi_year_report.md", "w") as f:
        f.write("# Multi-Year Comparison Analysis\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Summary by Symbol\n\n")
        
        for result in all_results:
            if "yearly_stats" not in result:
                continue
            
            f.write(f"### {result['symbol']}\n\n")
            f.write("| Year | Days | Bursts | Rate | Avg Vol Spike | Burst Return |\n")
            f.write("|------|------|--------|------|---------------|-------------|\n")
            
            for year, stats in sorted(result["yearly_stats"].items()):
                f.write(f"| {year} | {stats['total_days']} | {stats['burst_days']} ")
                f.write(f"| {stats['burst_rate']:.1%} | {stats['avg_volume_spike']:.1f}x ")
                f.write(f"| {stats['burst_day_return']:.2%} |\n")
            
            f.write("\n")
    
    print("\n" + "=" * 70)
    print("MULTI-YEAR ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
