#!/usr/bin/env python3
"""
Phase 61: Provenance Test (Mechanism Lock-In)
=============================================

Goal: Determine if the 93.5Hz signal is a timestamp artifact or venue-specific mechanism.

Experiment A: Jitter Sweep
- Levels: 0 (Ref), 1us (1000ns), 1ms (1e6 ns), 5ms (5e6 ns).
- Hypothesis: If artifact, it survives 1us but dies at 1-5ms. If real mechanism, it might survive 1ms (if coarse clock) or die (if fine clock).

Experiment B: Venue Ablation
- Venues: All, EDGX (4), NYSE (N/A?), NASDAQ (N/A?).
- Hypothesis: Signal might be localized to one exchange.
"""

import numpy as np
import pandas as pd
from pathlib import Path
import sys
import json

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from research.phase57_detection_stack.layer0_data_harness import TickLoader
from research.phase57_detection_stack.layer2_cyclostationary import MultiScaleScanner

def run_l2_scan(timestamps):
    scanner = MultiScaleScanner(bin_sizes_ms=[1]) # Focus on 1ms for 93.5Hz (Nyquist 500Hz)
    results = scanner._scan_single(timestamps, 1, threshold=3.0)
    # Look for 93.5Hz peak
    target_found = None
    for p in results:
        if 90 < p['freq_hz'] < 97: # Wide net around 93.5
            if target_found is None or p['power_ratio'] > target_found['power_ratio']:
                target_found = p
    return target_found

def run_provenance_suite(symbol="GME", date="2024-05-14"):
    print(f"--- Phase 61 Provenance Test: {symbol} on {date} ---")
    loader = TickLoader()
    
    # --- Experiment A: Jitter Sweep ---
    print("\n[Experiment A] Jitter Sweep")
    jitters = [0, 1000, 1000000, 5000000] # 0, 1us, 1ms, 5ms
    
    for j in jitters:
        df = loader.load_ticks(date, symbol, jitter_amount_ns=j)
        if df is None or df.empty:
            print(f"  Jitter {j}ns: Load Failed")
            continue
            
        # SLICE TO WINDOW 1 (13:30 - 13:35 UTC) where signal was found
        # 13:30 is 9:30 ET
        # Just use absolute time from file if possible, or relative to start
        # The file starts around 13:30? No, it's full day.
        # Find start of file:
        t0 = df['timestamp'].iloc[0].normalize() + pd.Timedelta(hours=13, minutes=30)
        t1 = t0 + pd.Timedelta(minutes=5)
        
        df_slice = df[(df['timestamp'] >= t0) & (df['timestamp'] < t1)]
        
        if len(df_slice) < 1000:
             print(f"  Warning: Window Slice Empty? Len={len(df_slice)}. Falling back to first 5 mins.")
             df_slice = df.iloc[:10000]
        else:
             print(f"  Slice {len(df_slice)} events ({df_slice['timestamp'].min()} - {df_slice['timestamp'].max()})")
        
        timestamps = df_slice['timestamp'].astype(np.int64).values / 1e9
        peak = run_l2_scan(timestamps)
        
        status = "MISSING"
        power = 0.0
        if peak:
            status = f"FOUND ({peak['freq_hz']:.2f} Hz)"
            power = peak['power_ratio']
            
        print(f"  Jitter {j:9} ns: {status} | Power={power:.1f}")

    # --- Experiment B: Venue Ablation ---
    print("\n[Experiment B] Venue Ablation")
    # First load all to see venues
    df_ref = loader.load_ticks(date, symbol)
    if df_ref is None: return
    
    top_venues = df_ref['venue'].astype(str).value_counts().head(5).index.tolist()
    print(f"  Top Venues: {top_venues}")
    
    # Test each top venue in isolation
    for v in top_venues:
        df_v = loader.load_ticks(date, symbol, venue_filter=[v])
        if df_v is None or len(df_v) < 1000:
            print(f"  Venue {v}: Insufficient Data")
            continue
            
        # SLICE TO WINDOW 1 (13:30 - 13:35 UTC)
        t0 = df_v['timestamp'].iloc[0].normalize() + pd.Timedelta(hours=13, minutes=30)
        t1 = t0 + pd.Timedelta(minutes=5)
        df_v = df_v[(df_v['timestamp'] >= t0) & (df_v['timestamp'] < t1)]
             
        timestamps = df_v['timestamp'].astype(np.int64).values / 1e9
        peak = run_l2_scan(timestamps)
        
        status = "MISSING"
        power = 0.0
        if peak:
            status = f"FOUND ({peak['freq_hz']:.2f} Hz)"
            power = peak['power_ratio']
            
        print(f"  Venue {v:9}: {status} | Power={power:.1f}")

if __name__ == "__main__":
    run_provenance_suite()
