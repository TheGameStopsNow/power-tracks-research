#!/usr/bin/env python3
"""
Burst Clustering Analysis
==========================

Tests if bursts are random events or if they "cluster":
1. Temporal Clustering: Does a burst today predict a burst tomorrow?
2. Cross-Sectional Clustering: Do multiple stocks burst on the same day?
3. "Burst Storms": Identify high-intensity periods.

Hypothesis: If this is a valid signal mechanism (or structural failure),
events should not be independent. They should cluster.
"""

import sys
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
# Imports removed


BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
EXPANDED_DIR = BASE_DIR / "data" / "expanded_bars"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "results"

def detect_burst_for_day(df: pd.DataFrame) -> dict:
    """Detect if a burst occurred."""
    if len(df) < 100:
        return {"is_burst": False}
    
    mean_vol = df['volume'].mean()
    max_vol = df['volume'].max()
    volume_spike = max_vol / mean_vol if mean_vol > 0 else 0
    
    price_range = (df['high'].max() - df['low'].min()) / df['open'].iloc[0]
    
    # Same threshold as before
    is_burst = volume_spike > 2.5 and price_range > 0.03
    
    return {
        "is_burst": is_burst,
        "volume_spike": volume_spike,
        "price_range": price_range
    }

def load_all_burst_data(expanded_dir: Path) -> pd.DataFrame:
    """Load burst status for all symbols and dates."""
    all_data = []
    
    # Iterate over all symbol directories
    symbol_dirs = [d for d in expanded_dir.iterdir() if d.is_dir()]
    
    print(f"Scanning {len(symbol_dirs)} symbols: {[s.name for s in symbol_dirs]}")
    
    for symbol_dir in symbol_dirs:
        csv_files = sorted(symbol_dir.glob("*.csv"))
        for csv_file in csv_files:
            try:
                date_str = csv_file.stem.split("_")[1]
                df = pd.read_csv(csv_file)
                if 'close' not in df.columns:
                    continue
                    
                res = detect_burst_for_day(df)
                if res:
                    all_data.append({
                        "date": date_str,
                        "symbol": symbol_dir.name,
                        "is_burst": res["is_burst"],
                        "volume_spike": res["volume_spike"]
                    })
            except Exception:
                continue
                
    return pd.DataFrame(all_data)

def analyze_temporal_clustering(df: pd.DataFrame) -> dict:
    """
    Test P(Burst(t) | Burst(t-1)) vs P(Burst(t))
    """
    results = {}
    
    for symbol in df['symbol'].unique():
        sym_df = df[df['symbol'] == symbol].sort_values("date").copy()
        
        if len(sym_df) < 10:
            continue
            
        sym_df['prev_burst'] = sym_df['is_burst'].shift(1).fillna(False)
        
        # Base probability (Unconditional)
        p_burst = sym_df['is_burst'].mean()
        
        # Conditional probability
        # When yesterday WAS a burst
        after_burst = sym_df[sym_df['prev_burst'] == True]
        p_burst_given_burst = after_burst['is_burst'].mean() if len(after_burst) > 0 else 0
        
        # Lift
        lift = p_burst_given_burst / p_burst if p_burst > 0 else 0
        
        results[symbol] = {
            "p_burst": p_burst,
            "p_burst_given_burst": p_burst_given_burst,
            "lift": lift,
            "n_days": len(sym_df),
            "n_bursts": sym_df['is_burst'].sum()
        }
        
    return results

def analyze_cross_sectional_clustering(df: pd.DataFrame) -> dict:
    """
    Analyze concurrent bursts across symbols.
    """
    # Pivot to Date x Symbol matrix
    pivot = df.pivot_table(index="date", columns="symbol", values="is_burst", aggfunc='max').fillna(False)
    
    # Count concurrent bursts per day
    pivot['concurrent_bursts'] = pivot.sum(axis=1)
    
    # Distribution of concurrency
    dist = pivot['concurrent_bursts'].value_counts().sort_index().to_dict()
    
    # Identify "Burst Storms" (days with >= 3 bursts)
    storms = pivot[pivot['concurrent_bursts'] >= 3].index.tolist()
    
    # Correlation Matrix (Phi coefficient for binary variables)
    # Using simple Pearson on boolean (0/1) works as Phi
    corr_matrix = pivot.drop(columns=['concurrent_bursts']).corr()
    
    # Clean up correlation matrix for JSON
    corr_dict = corr_matrix.where(pd.notnull(corr_matrix), None).to_dict()
    
    return {
        "concurrency_distribution": dist,
        "storm_dates": storms,
        "correlation_matrix": corr_dict,
        "avg_concurrent": float(pivot['concurrent_bursts'].mean()),
        "max_concurrent": int(pivot['concurrent_bursts'].max())
    }

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("BURST CLUSTERING ANALYSIS")
    print("Do bursts cluster in time or across symbols?")
    print("=" * 70)
    
    # 1. Load Data
    print(">>> Loading data...")
    df = load_all_burst_data(EXPANDED_DIR)
    
    if df.empty:
        print("No data found.")
        return

    print(f"Loaded {len(df)} symbol-days.")
    
    # 2. Temporal Clustering
    print("\n>>> Analyzing Temporal Clustering (Auto-correlation)...")
    temporal_res = analyze_temporal_clustering(df)
    
    print("\nSymbol | P(Burst) | P(Burst|Burst) | Lift (Clustering Factor)")
    print("-" * 60)
    for sym, res in sorted(temporal_res.items(), key=lambda x: x[1]['lift'], reverse=True):
        print(f"{sym:<6} | {res['p_burst']:.1%}   | {res['p_burst_given_burst']:.1%}         | {res['lift']:.2f}x")
        
    # 3. Cross-Sectional Clustering
    print("\n>>> Analyzing Cross-Sectional Clustering (Sympathy)...")
    cross_res = analyze_cross_sectional_clustering(df)
    
    print(f"\nAverage concurrent bursts: {cross_res['avg_concurrent']:.2f}")
    print(f"Max concurrent bursts: {cross_res['max_concurrent']}")
    print("\nConcurrency Distribution (Days with N bursts):")
    for n, count in cross_res['concurrency_distribution'].items():
        print(f"  {n} bursts: {count} days")
        
    print(f"\nBurst Storms (>=3 symbols): {len(cross_res['storm_dates'])} days")
    if len(cross_res['storm_dates']) > 0:
        print(f"Recent storms: {sorted(cross_res['storm_dates'])[-10:]}")
        
    # Save Results
    results = {
        "timestamp": datetime.now().isoformat(),
        "temporal": temporal_res,
        "cross_sectional": cross_res
    }
    
    with open(OUTPUT_DIR / "burst_clustering.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
        
    # Generate Report
    with open(OUTPUT_DIR / "clustering_report.md", "w") as f:
        f.write("# Burst Clustering Analysis\n\n")
        f.write("## 1. Temporal Clustering (Momentum)\n\n")
        f.write("Does a burst today predict a burst tomorrow?\n\n")
        f.write("| Symbol | Base Rate | P(Burst|PrevBurst) | Lift |\n")
        f.write("|--------|-----------|--------------------|------|\n")
        for sym, res in sorted(temporal_res.items(), key=lambda x: x[1]['lift'], reverse=True):
            f.write(f"| {sym} | {res['p_burst']:.1%} | {res['p_burst_given_burst']:.1%} | **{res['lift']:.2f}x** |\n")
            
        f.write("\n## 2. Cross-Sectional Clustering (Sympathy)\n\n")
        f.write("Do bursts happen together?\n\n")
        f.write(f"- **Max Concurrent Bursts**: {cross_res['max_concurrent']}\n")
        f.write(f"- **days with >=3 bursts**: {len(cross_res['storm_dates'])}\n\n")
        
        f.write("### Concurrency Distribution\n")
        for n, count in cross_res['concurrency_distribution'].items():
            f.write(f"- **{n} bursts**: {count} days\n")
            
    print("\n" + "=" * 70)
    print("CLUSTERING ANALYSIS COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    main()
