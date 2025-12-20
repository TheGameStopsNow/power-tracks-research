#!/usr/bin/env python3
"""
Verify 7-4-1 Sync Marker
Checks if the 7-4-1 price delta signal acts as a byte framing marker.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from scipy.stats import chisquare
import sys
import os

# Configuration
DATA_DIR = Path("data/ticks")
TARGET_TICKER = "GME" # Primary target
# Known "War" dates or high activity dates to sample first
SAMPLE_DATES = [
    "2024-05-14", "2024-05-15", "2024-05-16", # Roaring Kitty Return
    "2021-01-28", # The Sneeze
    "2021-03-10", # Mar10 Day
    "2024-06-03",
    "2024-06-07"
]

# Known Opcode Vocabulary for "Validity" check
KNOWN_OPCODES = {
    0xA0, # FLOOR
    0x98, # CEILING
    0x80, # PIVOT
    0x10, # STATION
    0x01, # LIFT
    0x02, # DROP
    0x08, # AGGRESSION
    0xF8  # PEAK COMBAT
}

def load_trades(date_str):
    """Loads trade data for a specific date."""
    file_path = DATA_DIR / date_str / f"{TARGET_TICKER}.csv"
    if not file_path.exists():
        if (DATA_DIR / date_str).exists():
             csvs = list((DATA_DIR / date_str).glob("*.csv"))
             for c in csvs:
                 if "GME" in c.name:
                     file_path = c
                     break
    
    if not file_path.exists():
        print(f"File not found for {date_str}")
        return None

    try:
        df = pd.read_csv(file_path)
        print(f"Loaded {date_str}, shape: {df.shape}")
        if 'sip_timestamp' in df.columns:
             df.rename(columns={'sip_timestamp': 'timestamp_us'}, inplace=True)
        
        # Check columns
        if 'price' not in df.columns:
            print(f"Missing price column in {date_str}. Columns: {df.columns}")
            return None
            
        # Optimization: Check if sorted
        if 'timestamp_us' in df.columns:
            if not df['timestamp_us'].is_monotonic_increasing:
                print(f"Sorting {date_str}...")
                try:
                    df.sort_values('timestamp_us', inplace=True)
                except Exception as e:
                    print(f"Warning: Sort failed for {date_str}: {e}. Proceeding with unsorted data.")
        
        return df
    except Exception as e:
        print(f"Error loading {date_str}: {e}")
        import traceback
        traceback.print_exc()
        return None

def detect_741_signals(df):
    """
    Detects indices of 7-4-1 patterns (-0.07, -0.04, -0.01).
    Returns a list of indices where the pattern ENDS.
    """
    prices = df['price'].values
    deltas = np.round(np.diff(prices), 2)
    
    # Debug stats
    unique, counts = np.unique(deltas, return_counts=True)
    stats = dict(zip(unique, counts))
    print(f"Counts -> -0.07: {stats.get(-0.07, 0)}, -0.04: {stats.get(-0.04, 0)}, -0.01: {stats.get(-0.01, 0)}")

    valid_k = np.where( 
        (deltas[2:] == -0.01) & 
        (deltas[1:-1] == -0.04) & 
        (deltas[:-2] == -0.07) 
    )[0]
    
    pattern_end_indices = valid_k + 3
    
    count = len(pattern_end_indices)
    print(f"Matches found: {count}")
    
    return pattern_end_indices

def get_opcodes(prices):
    """Convert prices to byte opcodes (8-trade grouping)."""
    cents = (prices * 100).round().astype(int)
    lsbs = cents & 1
    
    n_bytes = len(lsbs) // 8
    if n_bytes == 0:
        return np.array([])
        
    lsbs_trunc = lsbs[:n_bytes*8]
    lsbs_reshaped = lsbs_trunc.reshape(-1, 8)
    
    weights = np.array([128, 64, 32, 16, 8, 4, 2, 1])
    opcodes = np.dot(lsbs_reshaped, weights)
    
    return opcodes

def calculate_validity(opcodes):
    """Percentage of opcodes that are in the known vocabulary."""
    if len(opcodes) == 0: return 0.0
    # Use numpy for speed
    mask = np.isin(opcodes, list(KNOWN_OPCODES))
    return np.mean(mask)

def main():
    print("Starting 7-4-1 Sync Verification...")
    
    total_signals = 0
    phase_counts = np.zeros(8, dtype=int)
    
    validity_scores = {offset: [] for offset in range(8)}
    
    processed_dates = 0
    
    # 1. Scan Dates
    for date_str in SAMPLE_DATES:
        df = load_trades(date_str)
        if df is None or len(df) < 100:
            continue
            
        processed_dates += 1
        
        # 2. Find Signals
        signal_indices = detect_741_signals(df)
        count = len(signal_indices)
        total_signals += count
        
        if count > 0:
            # 3. Check Phase Alignment
            phases = signal_indices % 8
            for p in phases:
                phase_counts[p] += 1
        
        # 4. Check Structure for ALL offsets (regardless of signals, to report best global offset)
        prices = df['price'].values
        for offset in range(8):
            current_opcodes = get_opcodes(prices[offset:])
            score = calculate_validity(current_opcodes)
            validity_scores[offset].append(score)
                
    print(f"\nProcessed {processed_dates} days.")
    print(f"Total 7-4-1 signals found: {total_signals}")
    
    if total_signals == 0:
        print("No signals found in the sample set. Cannot verify sync hypothesis.")
    else:
        # Results Analysis
        # 1. Phase Clustering
        print("\n--- Phase Alignment Analysis ---")
        print("Distribution of Signal Indices % 8:")
        for i, count in enumerate(phase_counts):
            pct = (count / total_signals) * 100 if total_signals > 0 else 0
            print(f"Phase {i}: {count} ({pct:.1f}%)")
            
        # Chi-square test for uniformity
        expected = [total_signals / 8] * 8
        chisq, p_val = chisquare(phase_counts, f_exp=expected)
        print(f"\nChi-Square Test for Uniformity: p-value = {p_val:.5f}")
        if p_val < 0.01:
            print(">> SIGNIFICANT CLUSTERING DETECTED. The signal favors specific byte phases.")
            best_phase = np.argmax(phase_counts)
            print(f">> Most common phase: {best_phase}")
        else:
            print(">> No significant clustering. Signal appears randomly distributed across byte phases.")
        
    # 2. Structure Enhancement
    print("\n--- Structure Enhancement Analysis ---")
    if any(validity_scores.values()):
        avg_scores = {k: np.mean(v) if v else 0 for k, v in validity_scores.items()}
        best_offset = max(avg_scores, key=avg_scores.get)
        best_score = avg_scores[best_offset]
        worst_score = min(avg_scores.values())
        avg_score_all = np.mean(list(avg_scores.values()))
        
        print("Average Valid Opcode Density per Offset:")
        for off, sc in avg_scores.items():
            print(f"Offset {off}: {sc:.4f}")
            
        print(f"\nBest Offset: {best_offset} (Score: {best_score:.4f})")
        print(f"Worst Offset: {min(avg_scores, key=avg_scores.get)} (Score: {worst_score:.4f})")
        
        improvement = (best_score - avg_score_all) / avg_score_all * 100
        print(f"Relative Improvement of Best vs Average: {improvement:.2f}%")
        
        # Correlation Check
        if total_signals > 0 and p_val < 0.01:
            print("\n--- Correlation Check ---")
            best_phase = np.argmax(phase_counts)
            print(f"Does the clustered signal phase ({best_phase}) match the best structure offset ({best_offset})?")
            if best_phase == best_offset:
                print(">> MATCH! Strong evidence for sync marker.")
            else:
                print(f">> MISMATCH. Signal clusters at {best_phase}, but structure peaks at {best_offset}.")
    else:
        print("No valid scores computation possible.")

if __name__ == "__main__":
    main()
