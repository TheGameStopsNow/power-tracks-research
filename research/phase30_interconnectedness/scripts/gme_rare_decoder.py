#!/usr/bin/env python3
"""
GME Rare Decoder - Phase 30E
Extracts the "Language" of the Zombie Mode.
Finds 0xDF (Seed) and 0xA0 (Floor) and captures the surrounding opcode context.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from collections import Counter
import sys

# Configuration
SCAN_FILE = Path("research/phase30_interconnectedness/GME_2025_deep_scan.csv")
DATA_DIR = Path("data/ticks")
EXCHANGE_EDGX = 4
CONTEXT_WINDOW = 4 # Look at 4 opcodes before and after

# Known Opcodes
KNOWN = {
    0xA0: "FLOOR",
    0x98: "CEILING",
    0x80: "PIVOT",
    0x10: "STATION",
    0x01: "LIFT",
    0x02: "DROP",
    0xDF: "SEED",
}

def get_label(code):
    return KNOWN.get(code, f"0x{code:02X}")

def analyze_phrases(date, file_path):
    try:
        df = pd.read_csv(file_path, usecols=['timestamp_us', 'price', 'exchange'])
    except:
        return []
    
    edgx_df = df[df['exchange'] == EXCHANGE_EDGX].copy()
    if edgx_df.empty: return []
    
    # Robust Sorting
    try:
         if edgx_df['timestamp_us'].isnull().any():
             edgx_df = edgx_df.dropna(subset=['timestamp_us'])
         edgx_df.sort_values('timestamp_us', inplace=True)
    except:
        return []

    # Extract Opcodes
    prices = edgx_df['price'].values
    cents = (prices * 100).round().astype(int)
    lsbs = cents & 1
    
    opcodes = []
    timestamps = []
    
    # Needs to be efficient
    for i in range(0, len(lsbs) - 7, 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | lsbs[i + j]
        opcodes.append(byte)
        # Use timestamp of the LAST bit (completion of byte)
        timestamps.append(edgx_df.iloc[min(i+7, len(edgx_df)-1)]['timestamp_us'])

    # Find Patterns
    phrases = []
    
    for i, code in enumerate(opcodes):
        if code in [0xDF, 0xA0]:
            # Extract Context
            start = max(0, i - CONTEXT_WINDOW)
            end = min(len(opcodes), i + CONTEXT_WINDOW + 1)
            
            sequence = opcodes[start:end]
            
            # Format phrase
            phrase_parts = []
            for j, op in enumerate(sequence):
                label = get_label(op)
                if op == code and (start + j) == i: # The target itself
                     phrase_parts.append(f"[{label}]")
                else:
                     phrase_parts.append(label)
            
            phrases.append({
                "date": date,
                "timestamp": timestamps[i], # Approx time of the target opcode
                "target": get_label(code),
                "phrase_raw": tuple(sequence),
                "phrase_str": " -> ".join(phrase_parts)
            })
            
    return phrases

def main():
    if not SCAN_FILE.exists():
        print(f"Missing {SCAN_FILE}")
        sys.exit(1)
        
    print("Loading scan results...")
    scan_df = pd.read_csv(SCAN_FILE)
    
    # Filter for days with rare opcodes
    target_days = scan_df[scan_df['rare_opcode_count'] > 0]
    print(f"Found {len(target_days)} days with rare opcodes.")
    
    # Sort by count descending to prioritize most active days
    target_days = target_days.sort_values('rare_opcode_count', ascending=False) #.head(20) # Top 20 days
    
    all_phrases = []
    
    print("Decoding context...")
    for idx, row in target_days.iterrows():
        date = row['date']
        file_path = DATA_DIR / date / "GME.csv"
        
        if file_path.exists():
            phrases = analyze_phrases(date, file_path)
            all_phrases.extend(phrases)
            # print(f"  {date}: Found {len(phrases)} phrases")
        
    if not all_phrases:
        print("No phrases extracted.")
        sys.exit()
        
    # Stats
    phrase_df = pd.DataFrame(all_phrases)
    
    # Most common phrases for 0xA0
    floors = phrase_df[phrase_df['target'] == 'FLOOR']
    common_floors = Counter(floors['phrase_str']).most_common(10)
    
    # Most common phrases for 0xDF
    seeds = phrase_df[phrase_df['target'] == 'SEED']
    common_seeds = Counter(seeds['phrase_str']).most_common(10)
    
    print("\n" + "="*60)
    print("GME ZOMBIE DIALECT DECODER REPORT")
    print("="*60)
    
    print(f"\nTotal Rare Packets Analyzed: {len(phrase_df)}")
    
    print("\nTOP 10 CONTEXTS FOR [FLOOR] (0xA0):")
    for phrase, count in common_floors:
        print(f"{count:4d} | {phrase}")
        
    print("\nTOP 10 CONTEXTS FOR [SEED] (0xDF):")
    for phrase, count in common_seeds:
        print(f"{count:4d} | {phrase}")
        
    # Save raw log
    output_log = Path("research/phase30_interconnectedness/GME_RARE_PACKET_LOG.txt")
    with open(output_log, 'w') as f:
        f.write("GME RARE PACKET LOG (2025)\n")
        f.write("==========================\n")
        for p in all_phrases:
            f.write(f"{p['date']} {p['timestamp']}: {p['phrase_str']}\n")
            
    print(f"\nFull log saved to {output_log}")

if __name__ == "__main__":
    main()
