#!/usr/bin/env python3
"""
Test L3 Robustness
==================
Runs VenueLagTracker on Window 2 of 2024-05-14 GME (where L3 was found).
Prints Switching Score and Component Stability.
"""
import pandas as pd
import numpy as np
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from research.phase57_detection_stack.layer0_data_harness import TickLoader
from research.phase57_detection_stack.layer3_latency import VenueLagTracker

def test_l3():
    date = "2024-05-14"
    symbol = "GME"
    loader = TickLoader()
    print(f"Loading {symbol} on {date}...")
    df = loader.load_ticks(date, symbol)
    if df is None: return

    # Window 2: 13:35 UTC (approx)
    # Start: 13:35:33
    t0 = pd.Timestamp(f"{date} 13:35:33", tz="UTC")
    t1 = t0 + pd.Timedelta(minutes=5)
    
    df_slice = df[(df['timestamp'] >= t0) & (df['timestamp'] < t1)]
    print(f"Window 2 Slice: {len(df_slice)} trades")
    
    # Run L3 Tracker (EDGX vs NYSE/Arca?)
    # Report said Pair [EDGX, 12] (Check venue ID match, 12 might be Arca)
    v1 = '4' # EDGX
    v2 = '12' # NYSE Arca?
    
    tracker = VenueLagTracker(v1, v2)
    lags, lag_times = tracker.compute_lags(df_slice)
    print(f"Computed {len(lags)} lags between {v1} and {v2}")
    
    if len(lags) < 100:
        print("Not enough lags.")
        return
        
    stats = tracker.analyze_distribution(lags)
    print("Distribution Stats:")
    for c in stats['components']:
        print(f"  Mode Mean: {c['mean']*1000:.3f} ms, Weight: {c['weight']:.2f}")
        
    # Coherence
    t_start = t0.value / 1e9
    
    # DEBUG Logic
    subwindow_sec = 60.0
    sub_id = np.floor((lag_times - t_start) / subwindow_sec).astype(int)
    print(f"Sub-ID unique counts: {np.unique(sub_id, return_counts=True)}")
    print(f"Lag Times Range: {lag_times.min()} - {lag_times.max()}")
    print(f"Window Start: {t_start}")
    
    res = tracker.l3_temporal_coherence(lags, lag_times, t_start)
    
    print("\nCoherence Result:")
    print(f"  Multimodal: {res['multimodal']}")
    print(f"  Valid Switch: {res['valid_switch']}")
    print(f"  Switching Score: {res['switching_score']:.5f} (Should be stable)")
    print(f"  P-Value: {res['switching_p']:.4f}")
    print(f"  Weights Series: {res['w_series']}")

if __name__ == "__main__":
    test_l3()
