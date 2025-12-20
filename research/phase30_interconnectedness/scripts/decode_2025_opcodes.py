#!/usr/bin/env python3
"""
Decode EDGX Opcodes from 2025 Tick Data
Extracts LSBs from EDGX-only price stream to identify opcode vocabulary
"""

import pandas as pd
import numpy as np
from pathlib import Path
from collections import Counter

# Exchange codes (Polygon.io standard)
EXCHANGE_EDGX = 4

# Known opcodes from 2021 research
KNOWN_OPCODES = {
    0xA0: "FLOOR",      # Hard floor
    0x98: "CEILING",    # Hard ceiling  
    0x80: "PIVOT",      # Mid-point pivot
    0x10: "STATION",    # Station-keeping
    0x01: "LIFT",       # Price lift
    0x02: "DROP",       # Price drop
    0xDF: "SEED",       # Fractal seed (rare)
}

def extract_lsbs(prices):
    """Extract LSB from each price"""
    # Convert price to cents, then get LSB
    cents = (prices * 100).round().astype(int)
    lsbs =cents & 1
    return lsbs

def form_opcodes(lsbs):
    """Group LSBs into bytes (8 bits each)"""
    opcodes = []
    timestamps = []
    
    for i in range(0, len(lsbs) - 7, 8):
        # Form byte from 8 LSBs (MSB first)
        byte = 0
        for j in range(8):
            byte = (byte << 1) | lsbs.iloc[i + j]
        opcodes.append(byte)
        timestamps.append(lsbs.index[i + 7])  # Timestamp of completion
        
    return pd.DataFrame({'timestamp': timestamps, 'opcode': opcodes})

def analyze_vocabulary(df):
    """Analyze opcode distribution"""
    total = len(df)
    counts = Counter(df['opcode'])
    
    print(f"\n{'='*60}")
    print(f"OPCODE VOCABULARY ANALYSIS")
    print(f"{'='*60}")
    print(f"Total Opcodes Formed: {total:,}")
    print(f"Unique Opcodes: {len(counts)}")
    print(f"\nTop 20 Opcodes:")
    print(f"{'Hex':<8} {'Label':<12} {'Count':<10} {'Freq %':<8}")
    print(f"{'-'*60}")
    
    for opcode, count in counts.most_common(20):
        freq = (count / total) * 100
        label = KNOWN_OPCODES.get(opcode, "UNKNOWN")
        print(f"0x{opcode:02X}     {label:<12} {count:<10} {freq:>6.2f}%")
    
    # Check known opcode density
    known_count = sum(counts[k] for k in KNOWN_OPCODES.keys() if k in counts)
    known_pct = (known_count / total) * 100
    
    print(f"\n{'='*60}")
    print(f"Known Opcode Density: {known_pct:.2f}%")
    print(f"(Baseline random: 2.34% for 6 opcodes out of 256)")
    print(f"{'='*60}\n")
    
    return counts

def main():
    # Input files
    tsla_2025 = Path("data/ticks/2025-04-07/TSLA.csv")
    
    print(f"Loading {tsla_2025}...")
    df = pd.read_csv(tsla_2025)
    
    print(f"Total ticks: {len(df):,}")
    
    # Filter for EDGX only
    print("Filtering for EDGX (exchange code 4)...")
    edgx_mask = df['exchange'] == EXCHANGE_EDGX
    
    # Extract as numpy arrays to avoid pandas index issues
    timestamps = df.loc[edgx_mask, 'timestamp_us'].values
    prices = df.loc[edgx_mask, 'price'].values
    
    print(f"EDGX ticks: {len(prices):,} ({len(prices)/len(df)*100:.1f}%)")
    
    if len(prices) < 100:
        print("ERROR: Insufficient EDGX data")
        return
    
    # Sort arrays by timestamp
    print("Sorting by timestamp...")
    sort_idx = np.argsort(timestamps)
    timestamps = timestamps[sort_idx]
    prices = prices[sort_idx]
    
    # Extract LSBs
    print("Extracting LSBs...")
    cents = (prices * 100).round().astype(int)
    lsbs = cents & 1
    
    # Form opcodes
    print("Forming opcodes (8-bit bytes)...")
    opcodes = []
    opcode_timestamps = []
    
    for i in range(0, len(lsbs) - 7, 8):
        # Form byte from 8 LSBs (MSB first)
        byte = 0
        for j in range(8):
            byte = (byte << 1) | lsbs[i + j]
        opcodes.append(byte)
        opcode_timestamps.append(timestamps[i + 7])
    
    # Create results dataframe
    opcodes_df = pd.DataFrame({
        'timestamp': opcode_timestamps,
        'opcode': opcodes
    })
    
    # Analyze vocabulary
    vocab = analyze_vocabulary(opcodes_df)
    
    # Save results
    output_file = Path("research/phase30_interconnectedness/tsla_2025_opcodes.csv")
    opcodes_df.to_csv(output_file, index=False)
    print(f"Saved opcode sequence to {output_file}")
    
    # Save vocabulary summary
    summary_file = Path("research/phase30_interconnectedness/tsla_2025_vocab_summary.txt")
    with open(summary_file, 'w') as f:
        f.write(f"TSLA 2025-04-07 Opcode Vocabulary\n")
        f.write(f"Total opcodes: {len(opcodes_df):,}\n")
        f.write(f"Unique opcodes: {len(vocab)}\n\n")
        f.write(f"Top 50:\n")
        for opcode, count in vocab.most_common(50):
            label = KNOWN_OPCODES.get(opcode, "")
            f.write(f"0x{opcode:02X} {label:<12} {count:>8}\n")
    
    print(f"Saved vocabulary summary to {summary_file}")

if __name__ == "__main__":
    main()
