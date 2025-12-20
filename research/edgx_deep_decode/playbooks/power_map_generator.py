#!/usr/bin/env python3
"""
Power Map Generator (Phase 25)
==============================

Cartography of the EDGX "Volatility State Machine".
Classifies Opcodes based on their consistent position within the daily price range.

Methodology:
1. For each Day in May 2024:
   - Determine Session High/Low (from ticks).
   - For each Signal: calc `position = (price - low) / (high - low)`.
2. Aggregate by Opcode.
3. Classify:
   - CEILING (Resistance): Avg Pos > 0.75
   - FLOOR (Support): Avg Pos < 0.25
   - PIVOT (Mid): 0.25 <= Avg Pos <= 0.75
"""

from pathlib import Path
import pandas as pd
import numpy as np
import sys

# Import local modules
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs
from core.extractors import extract_all_signals
from adversarial_decoding import bits_to_bytes
from extended_analysis import parse_messages

def generate_power_map():
    print("=" * 60)
    print("POWER MAP GENERATOR: MAPPING THE MACHINE")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    # Filter for May 2024
    target_samples = [d for d in sample_dirs if "2024-05" in d.name]
    
    print(f"Scanning {len(target_samples)} days in May 2024...")
    
    all_signals = []
    
    for d in target_samples:
        try:
            df = load_edgx_data(d, symbol='GME')
            if df.empty: continue
            
            # Calculate Day Stats (Regular Hours mostly, but we use full available)
            day_high = df['price'].max()
            day_low = df['price'].min()
            day_range = day_high - day_low
            
            if day_range == 0: continue # Skip flat days
            
            signals = extract_all_signals(df)
            byte_stream = bits_to_bytes(signals['price_lsb_1c'])
            msgs = parse_messages(byte_stream, df)
            
            for m in msgs:
                if pd.notnull(m['header_type']):
                    op_hex = f"0x{int(m['header_type']):02X}"
                    price = m['price']
                    
                    # Normalized Position (0.0 = Low, 1.0 = High)
                    norm_pos = (price - day_low) / day_range
                    
                    all_signals.append({
                        'date': d.name,
                        'opcode': op_hex,
                        'price': price,
                        'norm_pos': norm_pos
                    })
                    
        except Exception as e:
            # print(f"Skipping {d.name}: {e}")
            pass
            
    df_res = pd.DataFrame(all_signals)
    
    # Aggregation
    print(f"\nProcessed {len(df_res)} signals across {len(target_samples)} days.")
    
    stats = df_res.groupby('opcode')['norm_pos'].agg(['count', 'mean', 'std', 'min', 'max'])
    # Filter for significance
    stats = stats[stats['count'] >= 3].sort_values('mean', ascending=False)
    
    print("\nTHE ROSETTA STONE (Opcode Classification):")
    print(f"{'Opcode':<8} | {'Class':<10} | {'Count':<5} | {'Avg Pos%':<8} | {'Consistency (Std)':<15}")
    print("-" * 70)
    
    for op, row in stats.iterrows():
        avg_pos = row['mean']
        
        # Classification
        cls = "PIVOT"
        if avg_pos >= 0.75: cls = "CEILING"
        elif avg_pos <= 0.25: cls = "FLOOR"
        else:
            # Sub-classify PIVOT
            if 0.4 <= avg_pos <= 0.6: cls = "MIDPOINT"
            elif 0.25 < avg_pos < 0.4: cls = "LOWER-MID"
            elif 0.6 < avg_pos < 0.75: cls = "UPPER-MID"
            
        print(f"{op:<8} | {cls:<10} | {int(row['count']):<5} | {avg_pos*100:6.1f}% | {row['std']:.3f}")

    # Specific check for the "Power Track" Opcodes from Phase 24
    print("\nVerifying May 17 Suspects:")
    suspects = ['0x80', '0xD7', '0xF5', '0x20', '0x40']
    
    print(f"{'Opcode':<8} | {'May 17 Role':<12} | {'Global Role':<12} | {'Global Avg Pos'}")
    print("-" * 60)
    
    roles = {
        '0x80': 'High/Ceiling',
        '0xD7': 'High/Ceiling',
        '0xF5': 'Low/Floor',
        '0x20': 'Low/Floor',
        '0x40': 'Low/Floor'
    }
    
    for op in suspects:
        if op in stats.index:
            avg = stats.loc[op, 'mean']
            g_role = "???"
            if avg >= 0.75: g_role = "CEILING"
            elif avg <= 0.25: g_role = "FLOOR"
            else: g_role = "MID"
            
            print(f"{op:<8} | {roles.get(op, '?'):<12} | {g_role:<12} | {avg*100:.1f}%")
        else:
             print(f"{op:<8} | {roles.get(op, '?'):<12} | {'Not Found':<12} | N/A")

if __name__ == "__main__":
    generate_power_map()
