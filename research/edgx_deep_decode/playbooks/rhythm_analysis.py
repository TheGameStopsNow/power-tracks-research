#!/usr/bin/env python3
"""
Rhythm Analysis (Protocol Taxonomy)
===================================

Analyzes the physical delivery layer of the protocol.
Classifies opcodes based on their temporal profile (Rhythm).

Metrics:
    1. Inter-Arrival Time (IAT): How often does this opcode trigger?
    2. Burst Density: When it appears, does it appear in a cluster or isolated?
    3. Regularity: Is the IAT constant (Machine) or Poisson (Human)?
"""

from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from collections import defaultdict

# Import local modules
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
from core.extractors import extract_all_signals
from adversarial_decoding import bits_to_bytes

def analyze_rhythm(df: pd.DataFrame, bytes_list: List[int]) -> pd.DataFrame:
    """
    Correlates byte events with their timestamps to calculate rhythm metrics.
    """
    # 1. Map bytes to timestamps (End of byte)
    # Byte K corresponds to index (K+1)*8 - 1
    
    n_bytes = len(bytes_list)
    indices = [(k+1)*8 - 1 for k in range(n_bytes)]
    valid_indices = [i for i in indices if i < len(df)]
    
    timestamps = df.iloc[valid_indices]['timestamp'].values
    opcodes = np.array(bytes_list[:len(valid_indices)])
    
    unique_opcodes = np.unique(opcodes)
    
    metrics = []
    
    for op in unique_opcodes:
        # Ignore rare opcodes (< 50 occurrences)
        mask = (opcodes == op)
        count = np.sum(mask)
        if count < 50:
            continue
            
        times = timestamps[mask]
        
        # Calculate Inter-Arrival Times (in milliseconds)
        # diff returns Timedelta, convert to float ms
        iats = np.diff(times).astype(float) / 1e6 # ns to ms
        
        if len(iats) == 0:
            continue
            
        mean_iat = np.mean(iats)
        std_iat = np.std(iats)
        cv = std_iat / mean_iat if mean_iat > 0 else 0 # Coefficient of Variation
        
        # Burstiness: Short IATs (< 50ms) vs Long IATs
        burst_ratio = np.sum(iats < 50) / len(iats)
        
        metrics.append({
            'opcode': op,
            'hex': f"0x{op:02X}",
            'count': count,
            'mean_iat_ms': mean_iat,
            'cv_regularity': cv, # Lower = More Regular/Periodic
            'burst_ratio': burst_ratio
        })
        
    return pd.DataFrame(metrics)

def plot_rhythm_map(metrics_df: pd.DataFrame, output_path: Path):
    plt.figure(figsize=(10, 8))
    
    # Scatter Plot: Regularity vs Frequency (Mean IAT)
    # X-Axis: Mean IAT (Log Scale)
    # Y-Axis: Burst Ratio (Higher = More "Machine-Gun" like)
    
    # Color by Polarity (High vs Low)
    colors = ['red' if x > 127 else 'blue' for x in metrics_df['opcode']]
    
    plt.scatter(
        metrics_df['mean_iat_ms'], 
        metrics_df['burst_ratio'], 
        s=metrics_df['count'] / 5, # Size by prevalence
        c=colors,
        alpha=0.6,
        edgecolors='w'
    )
    
    plt.xscale('log')
    plt.xlabel("Mean Inter-Arrival Time (ms) [Log Scale]")
    plt.ylabel("Burst Ratio (% of IATs < 50ms)")
    plt.title("Opcode Rhythm Taxonomy\n(Size = Frequency, Red=HighBit, Blue=LowBit)")
    
    # Annotate Top 10
    top_10 = metrics_df.nlargest(10, 'count')
    for _, row in top_10.iterrows():
        plt.text(
            row['mean_iat_ms'], 
            row['burst_ratio'], 
            row['hex'], 
            fontsize=9
        )
        
    plt.grid(True, which="both", ls="-", alpha=0.2)
    plt.savefig(output_path)
    print(f"  Saved rhythm map to {output_path}")

def run_rhythm_analysis():
    print("=" * 60)
    print("PROTOCOL RHYTHM ANALYSIS")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    # Use same dense target
    target_dir = next((d for d in sample_dirs if "2024-09-05" in d.name), None)
    
    print(f"Profiling Rhythm on {target_dir.name}...")
    df = load_edgx_data(target_dir, symbol='GME')
    signals = extract_all_signals(df)
    bits = signals['price_lsb_1c']
    byte_stream = bits_to_bytes(bits)
    
    metrics_df = analyze_rhythm(df, byte_stream)
    
    print("-" * 60)
    print(f"{'Opcode':<8} | {'IAT (ms)':<10} | {'CV (Reg)':<8} | {'Burst%':<8} | {'Type'}")
    print("-" * 60)
    
    metrics_df = metrics_df.sort_values('count', ascending=False)
    
    for _, row in metrics_df.iterrows():
        # Classification
        if row['opcode'] in [0, 255]:
            otype = "PADDING"
        elif row['cv_regularity'] < 1.0:
            otype = "PERIODIC CLOCK"
        elif row['burst_ratio'] > 0.5:
            otype = "BURST DATA"
        else:
            otype = "SPORADIC"
            
        print(f"{row['hex']:<8} | {row['mean_iat_ms']:<10.1f} | {row['cv_regularity']:<8.2f} | {row['burst_ratio']*100:<7.1f}% | {otype}")
        
    out_dir = BASE_DIR / "research" / "edgx_deep_decode" / "results"
    plot_rhythm_map(metrics_df, out_dir / "rhythm_taxonomy.png")

if __name__ == "__main__":
    run_rhythm_analysis()
