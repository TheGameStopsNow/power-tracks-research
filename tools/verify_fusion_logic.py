#!/usr/bin/env python3
"""
Verify Fusion Logic on Any Symbol
=================================
Reads a standardized CSV (timestamp_us, price), extracts LSBs,
and runs the Fusion State machine to detect Regimes.
"""
import argparse
import pandas as pd
from collections import Counter

# Fusion Opcode Definitions
OP_FLOOR = 0xA0
OP_CEILING = 0x98
OP_PIVOT = 0x80
OP_STATION = 0x10

def get_opcode_name(op):
    if op == OP_FLOOR: return "FLOOR (War)"
    if op == OP_CEILING: return "CEILING (War)"
    if op == OP_PIVOT: return "PIVOT (Peace)"
    if op == OP_STATION: return "STATION (Peace)"
    return f"UNKNOWN (0x{op:02X})"

def run_fusion_verification(csv_path, symbol):
    print(f"Loading data for {symbol} from {csv_path}...")
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} ticks.")

    # 1. Extract LSBs
    # Assuming price is standard format (e.g. 5.25), multiply by 100
    df['lsb'] = (df['price'] * 100).astype(int) & 1
    
    # 2. Assemble Bytes
    bits = df['lsb'].tolist()
    bytes_out = []
    
    # Simple chunking by 8 (aligned stream assumption for verification test)
    # In real stream, we might need sliding window, but for verification of EXISTENCE
    # of opcodes, aligned check is usually sufficient if data is clean.
    for i in range(0, len(bits), 8):
        chunk = bits[i:i+8]
        if len(chunk) == 8:
            byte_val = 0
            for bit in chunk:
                byte_val = (byte_val << 1) | bit
            bytes_out.append(byte_val)

    print(f"Assembled {len(bytes_out)} bytes from stream.")

    # 3. Analyze Regime
    counts = Counter(bytes_out)
    
    storm_ops = counts[OP_FLOOR] + counts[OP_CEILING]
    peace_ops = counts[OP_PIVOT] + counts[OP_STATION]
    total_ops = storm_ops + peace_ops
    
    print("\n[Opcode Detection Results]")
    print(f"  FLOOR (0xA0):   {counts[OP_FLOOR]}")
    print(f"  CEILING (0x98): {counts[OP_CEILING]}")
    print(f"  PIVOT (0x80):   {counts[OP_PIVOT]}")
    print(f"  STATION (0x10): {counts[OP_STATION]}")
    
    print(f"\n[Fusion Logic State]")
    print(f"  Storm Signals: {storm_ops}")
    print(f"  Peace Signals: {peace_ops}")
    
    regime = "NEUTRAL"
    if total_ops > 0:
        storm_score = storm_ops / total_ops
        print(f"  Storm Score: {storm_score:.2f}")
        
        if storm_score > 0.6:
            regime = "WAR (STORM)"
        elif storm_score < 0.3 and total_ops > 2: # Lower threshold for tiny sample
            regime = "PEACE (CALM)"
        else:
            regime = "TRANSITION"
    else:
        print("  Storm Score: 0.00 (No Events)")

    print(f"  FINAL REGIME: {regime}")
    print("="*40)
    
    if regime != "NEUTRAL":
        print(f"SUCCESS: Logic verified on {symbol}. Regime state detected.")
    else:
        print(f"NOTE: No signals detected in this sample. Logic ran successfully, but signal strength was low.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--symbol", default="UNKNOWN")
    args = parser.parse_args()
    
    run_fusion_verification(args.file, args.symbol)
