#!/usr/bin/env python3
"""
Year-Round Burst Analysis
==========================

Tests if Power Track bursts occur throughout the year, not just around
the May 2024 squeeze event.

Key questions:
1. Do bursts happen in every month?
2. Is there seasonality?
3. Are quiet periods (Feb, Aug) different from hot periods (May)?
"""

import sys
from pathlib import Path
from datetime import datetime
import json
import calendar
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
EXPANDED_DIR = BASE_DIR / "data" / "expanded_bars"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "results"


def detect_burst(df: pd.DataFrame, volume_threshold: float = 2.5, price_threshold: float = 0.03) -> bool:
    """Quick burst detection for a single day."""
    
    if len(df) < 100:
        return False
    
    # Check for volume spike
    mean_vol = df['volume'].mean()
    max_vol = df['volume'].max()
    
    if max_vol < mean_vol * volume_threshold:
        return False
    
    # Check for price move
    price_range = (df['high'].max() - df['low'].min()) / df['open'].iloc[0]
    
    return price_range > price_threshold


def analyze_year_round(symbol_dir: Path) -> dict:
    """Analyze burst distribution across all months."""
    
    csv_files = sorted(symbol_dir.glob("*.csv"))
    
    monthly_data = defaultdict(lambda: {"days": 0, "bursts": 0, "total_volume": 0})
    daily_bursts = []
    
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            if 'close' not in df.columns:
                continue
            
            # Extract date from filename
            # Format: SYMBOL_YYYY-MM-DD_minute.csv
            date_str = csv_file.stem.split("_")[1]
            date = datetime.strptime(date_str, "%Y-%m-%d")
            month = date.month
            
            monthly_data[month]["days"] += 1
            monthly_data[month]["total_volume"] += df['volume'].sum()
            
            is_burst = detect_burst(df)
            if is_burst:
                monthly_data[month]["bursts"] += 1
                daily_bursts.append({
                    "date": date_str,
                    "month": month,
                    "month_name": calendar.month_abbr[month],
                    "volume": float(df['volume'].sum()),
                    "range_pct": float((df['high'].max() - df['low'].min()) / df['open'].iloc[0])
                })
                
        except Exception as e:
            continue
    
    # Calculate monthly statistics
    monthly_stats = {}
    for month in range(1, 13):
        data = monthly_data[month]
        if data["days"] > 0:
            monthly_stats[calendar.month_abbr[month]] = {
                "days": data["days"],
                "bursts": data["bursts"],
                "burst_rate": data["bursts"] / data["days"],
                "avg_daily_volume": data["total_volume"] / data["days"]
            }
    
    return {
        "symbol": symbol_dir.name,
        "monthly_stats": monthly_stats,
        "daily_bursts": daily_bursts,
        "total_days": sum(d["days"] for d in monthly_data.values()),
        "total_bursts": sum(d["bursts"] for d in monthly_data.values())
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("YEAR-ROUND BURST ANALYSIS")
    print("Do Power Track signals occur throughout the year?")
    print("=" * 70)
    
    if not EXPANDED_DIR.exists():
        print(f"\nNo expanded data at {EXPANDED_DIR}")
        print("Run download_expanded_data.py first")
        return
    
    symbol_dirs = [d for d in EXPANDED_DIR.iterdir() if d.is_dir()]
    
    if not symbol_dirs:
        print("No symbol data found")
        return
    
    all_results = []
    
    for symbol_dir in sorted(symbol_dirs):
        print(f"\n>>> {symbol_dir.name}")
        result = analyze_year_round(symbol_dir)
        all_results.append(result)
        
        if result["monthly_stats"]:
            print(f"  Total days: {result['total_days']}")
            print(f"  Total bursts: {result['total_bursts']}")
            print(f"  Average burst rate: {result['total_bursts']/result['total_days']:.1%}")
            
            # Show monthly breakdown
            print("  Monthly breakdown:")
            for month, stats in sorted(result["monthly_stats"].items(), 
                                       key=lambda x: list(calendar.month_abbr).index(x[0])):
                print(f"    {month}: {stats['burst_rate']:.0%} ({stats['bursts']}/{stats['days']} days)")
    
    # Cross-symbol seasonality analysis
    print("\n" + "=" * 70)
    print("SEASONALITY ANALYSIS")
    print("=" * 70)
    
    if all_results:
        # Aggregate monthly burst rates
        agg_monthly = defaultdict(lambda: {"bursts": 0, "days": 0})
        
        for result in all_results:
            for month, stats in result["monthly_stats"].items():
                agg_monthly[month]["bursts"] += stats["bursts"]
                agg_monthly[month]["days"] += stats["days"]
        
        print("\nAggregate burst rates by month:")
        for month in list(calendar.month_abbr)[1:]:
            if month in agg_monthly:
                data = agg_monthly[month]
                rate = data["bursts"] / data["days"] if data["days"] > 0 else 0
                print(f"  {month}: {rate:.1%} ({data['bursts']}/{data['days']} days)")
    
    # Save results
    with open(OUTPUT_DIR / "year_round_analysis.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": all_results
        }, f, indent=2, default=str)
    
    # Generate report
    with open(OUTPUT_DIR / "year_round_report.md", "w") as f:
        f.write("# Year-Round Burst Analysis\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Question\n\n")
        f.write("Do Power Track bursts occur throughout the year, or only during specific periods?\n\n")
        
        f.write("## Summary\n\n")
        if all_results:
            total_days = sum(r["total_days"] for r in all_results)
            total_bursts = sum(r["total_bursts"] for r in all_results)
            f.write(f"- **Total symbol-days analyzed**: {total_days}\n")
            f.write(f"- **Total bursts detected**: {total_bursts}\n")
            f.write(f"- **Overall burst rate**: {total_bursts/total_days:.1%}\n\n")
        
        f.write("## Monthly Breakdown\n\n")
        f.write("| Month | Days | Bursts | Rate |\n")
        f.write("|-------|------|--------|------|\n")
        
        for month in list(calendar.month_abbr)[1:]:
            if month in agg_monthly:
                data = agg_monthly[month]
                rate = data["bursts"] / data["days"] if data["days"] > 0 else 0
                f.write(f"| {month} | {data['days']} | {data['bursts']} | {rate:.1%} |\n")
    
    print("\n" + "=" * 70)
    print("YEAR-ROUND ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
