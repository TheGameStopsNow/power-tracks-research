#!/usr/bin/env python3
"""
Universal Grammar Validator (Phase 27)
======================================

Validates the "EDGX Volatility State Machine" hypothesis across long baselines
and different market regimes.

Regimes:
1. "The Echo" (Mar 2023)
2. "The Storm" (May 2024)
3. "The Calm" (June - Sept 2024)

Tests:
1. Is 0xA0 *always* the Hard Floor? (Consistency Check)
2. Does 0x80 shift roles? (Ceiling in Storm vs Pivot in Calm)
"""

from pathlib import Path
import pandas as pd
import numpy as np
import sys
from collections import defaultdict

# Import local modules
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs
from core.extractors import extract_all_signals
from adversarial_decoding import bits_to_bytes
from extended_analysis import parse_messages

def validate_universal_grammar():
    print("=" * 70)
    print("UNIVERSAL GRAMMAR VALIDATOR: HISTORICAL VERIFICATION")
    print("=" * 70)
    
    sample_dirs = get_sample_dirs()
    
    # Define Regimes
    regimes = {
        "MAR_2023": [d for d in sample_dirs if "2023-03" in d.name],
        "MAY_2024": [d for d in sample_dirs if "2024-05" in d.name],
        "LATE_2024": [d for d in sample_dirs if any(x in d.name for x in ["2024-06", "2024-07", "2024-08", "2024-09"])]
    }
    
    print(f"Regimes Found:")
    for name, dirs in regimes.items():
        print(f"  {name}: {len(dirs)} samples")
        
    # Stats storage
    # regime -> opcode -> list of positions
    results = defaultdict(lambda: defaultdict(list))
    
    for r_name, r_dirs in regimes.items():
        print(f"\nScanning {r_name}...")
        for d in r_dirs:
            try:
                df = load_edgx_data(d, symbol='GME')
                if df.empty: continue
                
                day_high = df['price'].max()
                day_low = df['price'].min()
                day_range = day_high - day_low
                
                if day_range == 0: continue
                
                signals = extract_all_signals(df)
                byte_stream = bits_to_bytes(signals['price_lsb_1c'])
                msgs = parse_messages(byte_stream, df)
                
                for m in msgs:
                    if pd.notnull(m['header_type']):
                        op = f"0x{int(m['header_type']):02X}"
                        price = m['price']
                        norm_pos = (price - day_low) / day_range
                        results[r_name][op].append(norm_pos)
            except:
                pass

    # Comparative Analysis
    print("\n" + "="*70)
    print(f"{'Opcode':<8} | {'Regime':<10} | {'Count':<5} | {'Avg Pos':<8} | {'Role':<12}")
    print("-" * 70)
    
    # Analyze key opcodes across regimes
    keys = ['0xA0', '0x80', '0x98', '0x01', '0x10', '0x3E']
    
    for op in keys:
        print(f"--- Analysis: {op} ---")
        for r_name in ["MAR_2023", "MAY_2024", "LATE_2024"]:
            data = results[r_name].get(op, [])
            if not data:
                print(f"{op:<8} | {r_name:<10} | {'0':<5} | {'N/A':<8} | Not Seen")
                continue
                
            avg_pos = np.mean(data)
            count = len(data)
            
            role = "PIVOT"
            if avg_pos < 0.2: role = "FLOOR"
            if avg_pos > 0.8: role = "CEILING"
            if 0.6 <= avg_pos <= 0.8: role = "UPPER-MID"
            
            print(f"{op:<8} | {r_name:<10} | {count:<5} | {avg_pos*100:5.1f}%   | {role:<12}")

    # Specific Hypothesis Check
    print("\nHYPOTHESIS VERIFICATION:")
    
    # 1. 0xA0 Stability
    pos_map = {r: np.mean(results[r]['0xA0']) for r in regimes if results[r]['0xA0']}
    print("1. Is 0xA0 always the Floor?")
    for r, p in pos_map.items():
        print(f"   {r}: {p*100:.1f}%")
        
    # 2. 0x80 Role Shift
    print("\n2. Does 0x80 shift roles?")
    pos_80 = {r: np.mean(results[r]['0x80']) for r in regimes if results[r]['0x80']}
    for r, p in pos_80.items():
        print(f"   {r}: {p*100:.1f}%")

if __name__ == "__main__":
    validate_universal_grammar()
