#!/usr/bin/env python3
"""
Options Timing Analysis
========================

Tests if bursts correlate with options mechanics:
1. Monthly OPEX (3rd Friday) pinning effects
2. Weekly options expiry (every Friday)
3. 0DTE (same-day expiry) effects
4. Gamma exposure timing

Hypothesis: Bursts may cluster around options expiry due to:
- Delta hedging unwinding
- Options pinning breaking down
- Gamma squeezes
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
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


def get_monthly_opex_dates(year: int) -> list:
    """Get 3rd Friday of each month (monthly options expiry)."""
    opex_dates = []
    for month in range(1, 13):
        c = calendar.monthcalendar(year, month)
        # 3rd Friday is the Friday in week 2 or 3
        for week in c:
            if week[calendar.FRIDAY] != 0:
                first_friday = week[calendar.FRIDAY]
                break
        # Third Friday
        third_friday = first_friday + 14
        opex_dates.append(f"{year}-{month:02d}-{third_friday:02d}")
    return opex_dates


def is_friday(date_str: str) -> bool:
    """Check if date is a Friday (weekly options expiry)."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.weekday() == 4  # Friday = 4
    except:
        return False


def is_monthly_opex(date_str: str, opex_dates: list) -> bool:
    """Check if date is monthly options expiry."""
    return date_str in opex_dates


def days_to_opex(date_str: str, opex_dates: list) -> int:
    """Calculate days to next monthly OPEX."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        future_opex = [datetime.strptime(d, "%Y-%m-%d") for d in opex_dates if d >= date_str]
        if future_opex:
            return (min(future_opex) - dt).days
        return 30
    except:
        return 30


def detect_burst_for_day(df: pd.DataFrame) -> dict:
    """Detect if a burst occurred and return characteristics."""
    
    if len(df) < 100:
        return {"is_burst": False}
    
    # Calculate metrics
    mean_vol = df['volume'].mean()
    max_vol = df['volume'].max()
    volume_spike = max_vol / mean_vol if mean_vol > 0 else 0
    
    price_range = (df['high'].max() - df['low'].min()) / df['open'].iloc[0]
    
    # Detect burst
    is_burst = volume_spike > 2.5 and price_range > 0.03
    
    return {
        "is_burst": is_burst,
        "volume_spike": float(volume_spike),
        "price_range": float(price_range),
        "volume": float(df['volume'].sum()),
        "open": float(df['open'].iloc[0]),
        "close": float(df['close'].iloc[-1]) if len(df) > 0 else 0,
        "return": float((df['close'].iloc[-1] / df['open'].iloc[0] - 1)) if len(df) > 0 else 0
    }


def analyze_options_timing(symbol_dir: Path) -> dict:
    """Analyze burst relationship to options expiry."""
    
    csv_files = sorted(symbol_dir.glob("*.csv"))
    if not csv_files:
        return {"error": "No data"}
    
    # Determine year from first file
    first_file = csv_files[0]
    date_str = first_file.stem.split("_")[1]
    year = int(date_str.split("-")[0])
    
    opex_dates = get_monthly_opex_dates(year)
    
    daily_data = []
    
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            if 'close' not in df.columns:
                continue
            
            date_str = csv_file.stem.split("_")[1]
            burst_info = detect_burst_for_day(df)
            
            burst_info["date"] = date_str
            burst_info["is_friday"] = is_friday(date_str)
            burst_info["is_opex"] = is_monthly_opex(date_str, opex_dates)
            burst_info["days_to_opex"] = days_to_opex(date_str, opex_dates)
            
            daily_data.append(burst_info)
            
        except Exception as e:
            continue
    
    if not daily_data:
        return {"error": "No valid data"}
    
    df_results = pd.DataFrame(daily_data)
    
    # Calculate burst rates by options timing
    total_days = len(df_results)
    total_bursts = df_results['is_burst'].sum()
    
    # Friday vs non-Friday
    friday_bursts = df_results[df_results['is_friday']]['is_burst'].sum()
    friday_days = df_results['is_friday'].sum()
    non_friday_bursts = df_results[~df_results['is_friday']]['is_burst'].sum()
    non_friday_days = (~df_results['is_friday']).sum()
    
    # Monthly OPEX vs non-OPEX
    opex_bursts = df_results[df_results['is_opex']]['is_burst'].sum()
    opex_days = df_results['is_opex'].sum()
    
    # Days to OPEX analysis
    days_to_opex_bursts = df_results.groupby('days_to_opex')['is_burst'].agg(['sum', 'count'])
    days_to_opex_bursts['rate'] = days_to_opex_bursts['sum'] / days_to_opex_bursts['count']
    
    # Week around OPEX (5 days before to OPEX)
    opex_week = df_results[df_results['days_to_opex'] <= 5]
    non_opex_week = df_results[df_results['days_to_opex'] > 5]
    
    results = {
        "symbol": symbol_dir.name,
        "year": year,
        "total_days": total_days,
        "total_bursts": int(total_bursts),
        "base_burst_rate": total_bursts / total_days if total_days > 0 else 0,
        
        "friday_analysis": {
            "friday_days": int(friday_days),
            "friday_bursts": int(friday_bursts),
            "friday_rate": friday_bursts / friday_days if friday_days > 0 else 0,
            "non_friday_days": int(non_friday_days),
            "non_friday_bursts": int(non_friday_bursts),
            "non_friday_rate": non_friday_bursts / non_friday_days if non_friday_days > 0 else 0
        },
        
        "opex_analysis": {
            "opex_days": int(opex_days),
            "opex_bursts": int(opex_bursts),
            "opex_rate": opex_bursts / opex_days if opex_days > 0 else 0
        },
        
        "opex_week_analysis": {
            "week_before_days": len(opex_week),
            "week_before_bursts": int(opex_week['is_burst'].sum()),
            "week_before_rate": opex_week['is_burst'].mean() if len(opex_week) > 0 else 0,
            "other_days": len(non_opex_week),
            "other_bursts": int(non_opex_week['is_burst'].sum()),
            "other_rate": non_opex_week['is_burst'].mean() if len(non_opex_week) > 0 else 0
        }
    }
    
    # Calculate statistical significance (chi-square test)
    from scipy import stats
    
    # Friday vs non-Friday
    if friday_days > 0 and non_friday_days > 0:
        contingency = [
            [friday_bursts, friday_days - friday_bursts],
            [non_friday_bursts, non_friday_days - non_friday_bursts]
        ]
        chi2, pval, _, _ = stats.chi2_contingency(contingency)
        results["friday_significance"] = {
            "chi2": float(chi2),
            "p_value": float(pval),
            "significant": pval < 0.05
        }
    
    return results


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("OPTIONS TIMING ANALYSIS")
    print("Do bursts correlate with options expiry?")
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
        result = analyze_options_timing(symbol_dir)
        all_results.append(result)
        
        if "error" not in result:
            base_rate = result['base_burst_rate']
            friday_rate = result['friday_analysis']['friday_rate']
            opex_rate = result['opex_analysis']['opex_rate']
            opex_week_rate = result['opex_week_analysis']['week_before_rate']
            
            print(f"  Base burst rate: {base_rate:.1%}")
            print(f"  Friday rate: {friday_rate:.1%} (weekly expiry)")
            print(f"  OPEX rate: {opex_rate:.1%} (monthly expiry)")
            print(f"  Week-of-OPEX rate: {opex_week_rate:.1%}")
            
            if result.get("friday_significance"):
                if result["friday_significance"]["significant"]:
                    print(f"  ⚠️ Friday effect SIGNIFICANT (p={result['friday_significance']['p_value']:.4f})")
                else:
                    print(f"  ✓ No significant Friday effect (p={result['friday_significance']['p_value']:.4f})")
    
    # Aggregate analysis
    print("\n" + "=" * 70)
    print("AGGREGATE OPTIONS TIMING")
    print("=" * 70)
    
    # Calculate aggregate rates
    valid_results = [r for r in all_results if "error" not in r]
    
    if valid_results:
        agg_friday_bursts = sum(r['friday_analysis']['friday_bursts'] for r in valid_results)
        agg_friday_days = sum(r['friday_analysis']['friday_days'] for r in valid_results)
        agg_non_friday_bursts = sum(r['friday_analysis']['non_friday_bursts'] for r in valid_results)
        agg_non_friday_days = sum(r['friday_analysis']['non_friday_days'] for r in valid_results)
        
        print(f"\nFriday (weekly expiry): {agg_friday_bursts}/{agg_friday_days} = {agg_friday_bursts/agg_friday_days:.1%}")
        print(f"Non-Friday: {agg_non_friday_bursts}/{agg_non_friday_days} = {agg_non_friday_bursts/agg_non_friday_days:.1%}")
        
        agg_opex_bursts = sum(r['opex_analysis']['opex_bursts'] for r in valid_results)
        agg_opex_days = sum(r['opex_analysis']['opex_days'] for r in valid_results)
        
        print(f"\nMonthly OPEX: {agg_opex_bursts}/{agg_opex_days} = {agg_opex_bursts/agg_opex_days:.1%}")
    
    # Save results
    with open(OUTPUT_DIR / "options_timing_analysis.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": all_results
        }, f, indent=2, default=str)
    
    # Generate report
    with open(OUTPUT_DIR / "options_timing_report.md", "w") as f:
        f.write("# Options Timing Analysis\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Hypothesis\n\n")
        f.write("Bursts may correlate with options mechanics:\n")
        f.write("- Weekly options expiry (Friday)\n")
        f.write("- Monthly OPEX (3rd Friday)\n")
        f.write("- Gamma/delta hedging effects\n\n")
        
        f.write("## Results by Symbol\n\n")
        f.write("| Symbol | Base Rate | Friday Rate | OPEX Rate | Significant? |\n")
        f.write("|--------|-----------|-------------|-----------|-------------|\n")
        
        for r in valid_results:
            sig = "⚠️" if r.get("friday_significance", {}).get("significant", False) else "✓"
            f.write(f"| {r['symbol']} | {r['base_burst_rate']:.1%} ")
            f.write(f"| {r['friday_analysis']['friday_rate']:.1%} ")
            f.write(f"| {r['opex_analysis']['opex_rate']:.1%} ")
            f.write(f"| {sig} |\n")
    
    print("\n" + "=" * 70)
    print("OPTIONS TIMING ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
