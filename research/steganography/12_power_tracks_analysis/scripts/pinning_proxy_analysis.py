#!/usr/bin/env python3
"""
Pinning Proxy Analysis
=======================

Tests the hypothesis that bursts are preceded by "Options Pinning" (suppressed volatility).
Since we don't have raw options flow for HIP/EPD, we use Price Pinning as a proxy.

Metric:
- Previous Day Range (Vol)
- Hypothesis: Low Prev Day Vol (Pinning) -> High Probability of Burst (Explosion)
"""

import sys
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
EXPANDED_DIR = BASE_DIR / "data" / "expanded_bars"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "results"

def analyze_pinning(symbol_dir: Path) -> dict:
    csv_files = sorted(symbol_dir.glob("*.csv"))
    if not csv_files:
        return None
        
    data = []
    
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            if len(df) < 100: continue
            
            date_str = csv_file.stem.split("_")[1]
            
            # Calculate metrics
            open_price = df['open'].iloc[0]
            high = df['high'].max()
            low = df['low'].min()
            close = df['close'].iloc[-1]
            volume = df['volume'].mean() # Daily average minute volume? No, this is mean of minute volumes.
            
            price_range_pct = (high - low) / open_price
            
            # Burst Detection (Same logic)
            # We need max_vol / mean_vol. 
            volume_spike = df['volume'].max() / df['volume'].mean() if df['volume'].mean() > 0 else 0
            is_burst = volume_spike > 2.5 and price_range_pct > 0.03
            
            data.append({
                "date": date_str,
                "range_pct": price_range_pct,
                "is_burst": is_burst
            })
            
        except:
            continue
            
    if not data:
        return None
        
    df = pd.DataFrame(data)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    
    # Calculate Previous Day Range
    df['prev_range_pct'] = df['range_pct'].shift(1)
    
    # Drop first row
    df = df.dropna()
    
    # Analysis:
    # Compare P(Burst | Low Prev Vol) vs P(Burst | High Prev Vol)
    
    # Define "Low Vol" as bottom quartile of range
    low_vol_threshold = df['prev_range_pct'].quantile(0.25)
    high_vol_threshold = df['prev_range_pct'].quantile(0.75)
    
    # Probabilities
    p_burst_overall = df['is_burst'].mean()
    
    p_burst_given_low_prev = df[df['prev_range_pct'] <= low_vol_threshold]['is_burst'].mean()
    p_burst_given_high_prev = df[df['prev_range_pct'] >= high_vol_threshold]['is_burst'].mean()
    
    return {
        "symbol": symbol_dir.name,
        "p_burst_overall": p_burst_overall,
        "p_burst_given_low_prev": p_burst_given_low_prev,
        "p_burst_given_high_prev": p_burst_given_high_prev,
        "low_vol_lift": p_burst_given_low_prev / p_burst_overall if p_burst_overall else 0,
        "high_vol_lift": p_burst_given_high_prev / p_burst_overall if p_burst_overall else 0,
        "low_vol_samples": len(df[df['prev_range_pct'] <= low_vol_threshold])
    }

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("PINNING PROXY ANALYSIS")
    print("Does suppressed volatility (Pinning) predict bursts?")
    print("=" * 70)
    
    symbol_dirs = [d for d in EXPANDED_DIR.iterdir() if d.is_dir()]
    results = []
    
    for s_dir in symbol_dirs:
        res = analyze_pinning(s_dir)
        if res:
            results.append(res)
            
    # Sort by "Rebound Effect" (High Vol Lift - because volatility clustering usually means High->High)
    # But checking for "Coil" effect (Low->High)
    
    print(f"{'Symbol':<6} | {'Base Rate':<9} | {'After PIN (Low)':<15} | {'After VOL (High)':<16} | {'Pin Lift':<8}")
    print("-" * 75)
    
    for r in sorted(results, key=lambda x: x['symbol']):
        print(f"{r['symbol']:<6} | {r['p_burst_overall']:.1%}      | {r['p_burst_given_low_prev']:.1%}           | {r['p_burst_given_high_prev']:.1%}            | {r['low_vol_lift']:.2f}x")
        
    # Generate Report
    with open(OUTPUT_DIR / "pinning_report.md", "w") as f:
        f.write("# Pinning Proxy Analysis\n\n")
        f.write("## Hypothesis\n")
        f.write("Does 'Pinning' (Low Volatility) precede Bursts?\n\n")
        f.write("| Symbol | Base Rate | P(Burst|LowVol) | P(Burst|HighVol) | Pinning Lift |\n")
        f.write("|--------|-----------|-----------------|------------------|--------------|\n")
        for r in sorted(results, key=lambda x: x['symbol']):
            f.write(f"| {r['symbol']} | {r['p_burst_overall']:.1%} | {r['p_burst_given_low_prev']:.1%} | {r['p_burst_given_high_prev']:.1%} | {r['low_vol_lift']:.2f}x |\n")
            
    print("\n" + "=" * 70)
    print("PINNING ANALYSIS COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()
