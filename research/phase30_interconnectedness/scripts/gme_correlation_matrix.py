#!/usr/bin/env python3
"""
GME Correlation Matrix - Phase 30D
Analyzes the relationship between GME Opcode Density (Hidden Activity)
and TSLA/MSFT 7-4-1 Signal Volatility (Overt Activity).
Tests the Leader-Lag Hypothesis.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt # Optional, but good for future
import sys

# Input Files
GME_SCAN_FILE = Path("research/phase30_interconnectedness/GME_2025_deep_scan.csv")
SIGNAL_LOG_FILE = Path("research/phase30_interconnectedness/2025_signal_log.csv")
OUTPUT_REPORT = Path("research/phase30_interconnectedness/2025_correlation_report.txt")

def main():
    if not GME_SCAN_FILE.exists():
        print(f"Error: Missing GME Scan file {GME_SCAN_FILE}")
        sys.exit(1)
    
    if not SIGNAL_LOG_FILE.exists():
        print(f"Error: Missing Signal Log file {SIGNAL_LOG_FILE}")
        sys.exit(1)

    print("Loading datasets...")
    
    # 1. Load GME Data (Daily resolution)
    gme_df = pd.read_csv(GME_SCAN_FILE)
    gme_df['date'] = pd.to_datetime(gme_df['date'])
    gme_df = gme_df.set_index('date').sort_index()
    
    # 2. Load Signal Log
    signals_df = pd.read_csv(SIGNAL_LOG_FILE)
    signals_df['date'] = pd.to_datetime(signals_df['date'])
    
    # Filter for TSLA/MSFT
    tsla_signals = signals_df[signals_df['symbol'] == 'TSLA']
    msft_signals = signals_df[signals_df['symbol'] == 'MSFT']
    
    # Group by Date to get daily counts
    tsla_counts = tsla_signals.groupby('date').size().rename("TSLA_Signals")
    msft_counts = msft_signals.groupby('date').size().rename("MSFT_Signals")
    
    # 3. Merge Datasets
    merged = gme_df[['opcode_density', 'rare_opcode_count']].join([tsla_counts, msft_counts], how='outer').fillna(0)
    
    # 4. Correlation Analysis
    print("\nRunning Cross-Correlation Analysis...")
    
    results = []
    
    for lag in range(-5, 6): # -5 to +5 days
        # Shift TSLA relative to GME
        # If Lag > 0: GME(t) vs TSLA(t+lag) -> Does GME predict future TSLA?
        # If Lag < 0: GME(t) vs TSLA(t-lag) -> Does TSLA predict future GME? (or GME reacts to past TSLA)
        
        # We want corr(GME_t, TSLA_t+k)
        # Shift TSLA back by k: TSLA.shift(-k) aligns t+k with t
        
        # Pearson Correlation
        corr_tsla = merged['opcode_density'].corr(merged['TSLA_Signals'].shift(-lag))
        corr_msft = merged['opcode_density'].corr(merged['MSFT_Signals'].shift(-lag))
        
        results.append({
            "Lag_Days": lag,
            "GME_vs_TSLA_Corr": corr_tsla,
            "GME_vs_MSFT_Corr": corr_msft
        })
        
    res_df = pd.DataFrame(results)
    
    # 5. Interpretation
    # Find max correlation
    max_tsla = res_df.loc[res_df['GME_vs_TSLA_Corr'].abs().idxmax()]
    max_msft = res_df.loc[res_df['GME_vs_MSFT_Corr'].abs().idxmax()]
    
    # Check specifically for Leader-Lag (Lag > 0 means GME leads)
    positive_lags = res_df[res_df['Lag_Days'] > 0]
    avg_pred_tsla = positive_lags['GME_vs_TSLA_Corr'].mean()
    
    # 6. Generate Report
    with open(OUTPUT_REPORT, 'w') as f:
        f.write("PHASE 30D: GME INTERCONNECTEDNESS AUDIT\n")
        f.write("=======================================\n\n")
        
        f.write("1. DATASET SUMMARY\n")
        f.write(f"   GME Days Analyzed: {len(gme_df)}\n")
        f.write(f"   TSLA Signal Events: {len(tsla_signals)}\n")
        f.write(f"   MSFT Signal Events: {len(msft_signals)}\n")
        f.write(f"   Common Dates: {len(merged)}\n\n")
        
        f.write("2. CORRELATION MATRIX (GME Opcode Density vs Signal Count)\n")
        f.write(res_df.to_string(index=False))
        f.write("\n\n")
        
        f.write("3. KEY FINDINGS\n")
        f.write(f"   Max TSLA Correlation: {max_tsla['GME_vs_TSLA_Corr']:.4f} at Lag {int(max_tsla['Lag_Days'])}\n")
        f.write(f"   Max MSFT Correlation: {max_msft['GME_vs_MSFT_Corr']:.4f} at Lag {int(max_msft['Lag_Days'])}\n")
        
        if max_tsla['Lag_Days'] > 0:
             f.write("   -> SIGNAL DETECTED: GME Density precedes TSLA activity (LEADER).\n")
        elif max_tsla['Lag_Days'] < 0:
             f.write("   -> SIGNAL DETECTED: GME Density follows TSLA activity (FOLLOWER).\n")
        else:
             f.write("   -> SYNCHRONOUS: GME and TSLA move together.\n")
             
        f.write("\n4. ANOMALY DETECTION (Zombie Mode)\n")
        # Identify days with High GME Density but ZERO TSLA Signals
        zombies = merged[(merged['opcode_density'] > 8.0) & (merged['TSLA_Signals'] == 0)]
        f.write(f"   Found {len(zombies)} days where GME was shouting (>8% density) but TSLA was silent.\n")
        if not zombies.empty:
            f.write("   Top 5 Zombie Days:\n")
            f.write(zombies['opcode_density'].nlargest(5).to_string())

    print(f"Report generated: {OUTPUT_REPORT}")
    print(res_df)

if __name__ == "__main__":
    main()
