#!/usr/bin/env python3
"""
Semantic Mapper (The Rosetta Stone)
===================================

Correlates specific opcodes (bytes) with immediate future price direction.
Builds a dictionary of meanings (e.g., 0x01 = BUY, 0x80 = SELL).

Methodology:
1. Extracts bitstream and groups into 8-bit bytes (Opcodes).
2. Maps each Opcode to its specific timestamp (end of the 8-trade burst).
3. Calculates forward returns (1s, 10s, 60s) for each Opcode instance.
4. Performs statistical t-tests against the baseline (0x00/0xFF padding).
"""

from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
from scipy import stats
import json
import warnings

# Import local modules
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
from core.extractors import extract_all_signals
from adversarial_decoding import bits_to_bytes
from price_correlation import calculate_future_returns


def map_opcodes_to_history(
    df: pd.DataFrame, 
    signal_name: str = 'price_lsb_1c'
) -> pd.DataFrame:
    """
    Extracts opcodes and aligns them with historical market data.
    Returns a DataFrame where each row is an Opcode event.
    """
    signals = extract_all_signals(df)
    if signal_name not in signals:
        return pd.DataFrame()
        
    bits = signals[signal_name]
    
    # We strictly use 8-bit alignment as found by the Fuzzer
    # Byte k corresponds to trades [8k : 8k+8]
    # We assign the event time to the last trade in the byte (trigger time)
    
    n_bytes = len(bits) // 8
    events = []
    
    for k in range(n_bytes):
        # Extract Byte
        chunk = bits[k*8 : (k+1)*8]
        val = 0
        for b in chunk:
            val = (val << 1) | b
            
        # Get market context at the moment the byte was completed
        idx = (k+1) * 8 - 1
        if idx >= len(df):
            break
            
        row = df.iloc[idx]
        events.append({
            'timestamp': row['timestamp'],
            'price': row['price'],
            'opcode': val,
            'opcode_hex': f"0x{val:02X}"
        })
        
    return pd.DataFrame(events)


def analyze_semantics(
    sample_dir: Path,
    output_dir: Path
):
    print(f"Mapping Semantics for {sample_dir.name}...")
    
    # Load data with forward returns pre-calculated
    # using load_edgx_data standard load then calculating returns
    df = load_edgx_data(sample_dir)
    if df.empty:
        print("  ✗ No data")
        return
        
    # Calculate returns on the full tick stream first
    # Windows: 1s, 10s, 60s
    print("  Calculating forward returns...")
    df = calculate_future_returns(df, forward_windows=[1, 10, 60])
    
    # Extract Opcodes aligned with valid return data
    events_df = map_opcodes_to_history(df)
    
    # Merge forward returns into events_df based on timestamp match
    # (Since events_df timestamps are a subset of df timestamps, we can join)
    # Using 'timestamp' as key might be tricky with floats/indices. 
    # Better to rely on index if preserved, but map_opcodes logic used iloc.
    # Let's map back via index: events[k] corresponds to df.iloc[(k+1)*8 - 1]
    
    indices = [(k+1)*8 - 1 for k in range(len(events_df))]
    
    # Extract returns for these indices
    returns_subset = df.iloc[indices][['fwd_return_1s', 'fwd_return_10s', 'fwd_return_60s']].reset_index(drop=True)
    
    events_df = pd.concat([events_df, returns_subset], axis=1)
    
    # Drop rows where future returns are NaN (end of file)
    events_df = events_df.dropna()
    
    print(f"  Analyzed {len(events_df)} opcode events")
    
    # Group by Opcode and calculate stats
    stats_list = []
    
    # Define Baseline: 0x00 (Idle) and 0xFF (Padding)
    baseline_df = events_df[events_df['opcode'].isin([0, 255])]
    baseline_mean = baseline_df['fwd_return_10s'].mean()
    baseline_std = baseline_df['fwd_return_10s'].std()
    
    print(f"  Baseline (Idle/Pad) 10s Return: {baseline_mean*100:.6f}% (n={len(baseline_df)})")
    
    # Analyze top 20 opcodes
    top_opcodes = events_df['opcode'].value_counts().head(20).index
    
    results = {}
    
    for op in top_opcodes:
        sub = events_df[events_df['opcode'] == op]
        hex_code = f"0x{op:02X}"
        
        # T-test vs Baseline (for 10s return)
        if len(sub) > 10 and len(baseline_df) > 10:
            t, p = stats.ttest_ind(sub['fwd_return_10s'], baseline_df['fwd_return_10s'], equal_var=False)
        else:
            t, p = 0, 1.0
            
        mean_ret = sub['fwd_return_10s'].mean()
        
        # Calculate impact relative to baseline (basis points)
        impact_bps = (mean_ret - baseline_mean) * 10000
        
        results[hex_code] = {
            'count': int(len(sub)),
            'mean_return_10s': float(mean_ret),
            'impact_bps': float(impact_bps),
            'p_value': float(p),
            'significant': bool(p < 0.05)
        }
    
    # Save per-run results
    out_file = output_dir / f"semantics_{sample_dir.name.replace('sample_', '')}.json"
    with open(out_file, 'w') as f:
        json.dump(results, f, indent=2)
        
    # Print Significant Findings
    print("\n  [Significant Semantic Mappings (p < 0.05)]")
    sig_found = False
    for code, data in results.items():
        if data['significant'] and code not in ['0x00', '0xFF']:
            sig_found = True
            direction = "BULLISH" if data['impact_bps'] > 0 else "BEARISH"
            print(f"    {code}: {direction} ({data['impact_bps']:+.2f} bps) - n={data['count']}")
            
    if not sig_found:
        print("    None found in this sample.")


if __name__ == "__main__":
    import argparse
    
    # Default to scanning the most recent valid directory
    # Ideally we'd loop over all, but let's start with a focused run
    sample_dirs = get_sample_dirs()
    # Find 2024-09-05 as a reliable test bed
    target = next((d for d in sample_dirs if "2024-09-05" in d.name), sample_dirs[-1])
    
    output_dir = BASE_DIR / "research" / "edgx_deep_decode" / "results"
    
    analyze_semantics(target, output_dir)
