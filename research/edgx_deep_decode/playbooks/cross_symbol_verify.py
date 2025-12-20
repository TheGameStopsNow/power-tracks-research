#!/usr/bin/env python3
"""
Cross-Symbol Broadcast Verifier
===============================

Tests if the EDGX Deep Decode signals appear simultaneously on multiple symbols.
If they do, it confirms the "System Broadcast" / Infrastructure hypothesis.

Hypothesis:
    Opcode `0x27` (or similar) is a "Heartbeat" or "Sync" message
    sent to the entire exchange, leaking into all active symbols.
"""

from pathlib import Path
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Import local modules
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import get_sample_dirs, BASE_DIR
from core.extractors import extract_price_lsb

# We need a custom loader that doesn't filter by single symbol immediately
# extracting from the raw CSV is expensive, so we'll do it carefully.

def load_multi_symbol_data(sample_dir: Path, symbols: List[str]) -> Dict[str, pd.DataFrame]:
    """
    Loads data for a list of symbols from the same date.
    Efficiently scans the CSV.
    """
    # Finding the CSV
    csv_files = list(sample_dir.rglob("*.csv.gz"))
    if not csv_files:
        csv_files = list(sample_dir.rglob("*.csv"))
        
    if not csv_files:
        print(f"No CSV found in {sample_dir}")
        return {}
        
    csv_path = csv_files[0]
    print(f"Scanning {csv_path.name} for {symbols}...")
    
    # Chunked load to filter
    chunks = []
    # Columns: assume standard [timestamp, symbol, price, size, ...]
    # We need to know column names. Standard loader uses:
    # names=['sip_dt', 'symbol', 'price', 'size', 'exchange', 'conditions'] or similar
    
    # Let's try to infer from header or use standard names
    # Using explicit names based on known schema
    cols = ['participant_timestamp', 'symbol', 'price', 'size']
    
    data_map = {s: [] for s in symbols}
    
    try:
        # Use a large chunksize to speed up
        reader = pd.read_csv(csv_path, chunksize=1000000, 
                             usecols=[0, 1, 2, 3], # Assume first 4 are relevant
                             names=['timestamp', 'symbol', 'price', 'size'],
                             header=0) # Assume header exists
                             
        for chunk in reader:
            chunk['symbol'] = chunk['symbol'].astype(str)
            for sym in symbols:
                mask = chunk['symbol'] == sym
                if mask.any():
                    data_map[sym].append(chunk[mask])
                    
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return {}
        
    # Concat
    result = {}
    for sym, chunks in data_map.items():
        if chunks:
            df = pd.concat(chunks)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp')
            result[sym] = df
            print(f"  Loaded {sym}: {len(df)} ticks")
        else:
            print(f"  {sym}: No data found.")
            
    return result

def check_simultaneity(data_map: Dict[str, pd.DataFrame]):
    """
    Checks if opcodes appear at the same time across symbols.
    """
    print("\n[Signal Extraction]")
    
    opcodes_map = {}
    for sym, df in data_map.items():
        # bits = extract_price_lsb(df) # We need the 8-bit opcodes
        # Re-implement bits_to_bytes logic here briefly
        # Standard: 1 bit per trade. 8 trades = 1 byte.
        # This is tricky for alignment. Timestamps are better.
        
        # Let's look at the LSBs directly in time
        df['lsb'] = (df['price'] * 10000).astype(int) % 2
        opcodes_map[sym] = df
        
    # We need to find "Silent Broadcasts".
    # Sync Event: A pattern of LSBs appearing at specific Time T across all symbols.
    # But trades are asynchronous.
    
    # Alternative: Do the "Rare Opcodes" (like 0x27) appear closely in time?
    # We first need to construct the opcode stream for each symbol.
    
    broadcast_events = []
    
    from adversarial_decoding import bits_to_bytes
    
    for sym, df in opcodes_map.items():
        bits = df['lsb'].values
        # Extract bytes (skip=8)
        bytes_ = bits_to_bytes(bits, skip=8)
        
        # We need identifying timestamps for these bytes.
        # Byte i corresponds to trade index (i+1)*8 - 1
        
        indices = [(i+1)*8 - 1 for i in range(len(bytes_))]
        timestamps = df.iloc[indices]['timestamp'].values
        
        # Filter for "Interesting" bytes (Not 0x00, 0xFF)
        # 0x27, 0xDF, 0x80
        targets = [0x27, 0xDF, 0x80, 0x01, 0xFD]
        
        for b, ts in zip(bytes_, timestamps):
            if b in targets:
                broadcast_events.append({
                    'symbol': sym,
                    'opcode': f"0x{b:02X}",
                    'timestamp': ts
                })
                
    events_df = pd.DataFrame(broadcast_events)
    if events_df.empty:
        print("No target opcodes found.")
        return
        
    events_df['timestamp'] = pd.to_datetime(events_df['timestamp'])
    events_df = events_df.sort_values('timestamp')
    
    print(f"\n[Detected {len(events_df)} Potential Broadcast Events]")
    
    # Find Clusters: Same opcode within 1 second across multiple symbols
    # Group by Opcode
    for op, group in events_df.groupby('opcode'):
        # Check time gaps
        group = group.sort_values('timestamp')
        group['dt'] = group['timestamp'].diff().dt.total_seconds()
        
        # Find bursts where multiple symbols active within small window
        # Simple sliding window count
        
        print(f"\nOpcode {op}:")
        counts = group['symbol'].value_counts()
        print(f"  Symbol Counts: {counts.to_dict()}")
        
        # Check for overlap
        # If we see < 100ms gap between different symbols
        close_events = group[group['dt'] < 0.1] # 100ms
        if len(close_events) > 0:
            print(f"  ** SIMULTANEOUS EVENTS DETECTED ** ({len(close_events)} pairs < 100ms)")
            print(close_events[['timestamp', 'symbol', 'dt']].head().to_string())
        else:
            print("  No simultaneous events found.")

def run_broadcast_check():
    print("=" * 60)
    print("CROSS-SYMBOL BROADCAST VERIFICATION")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    target_dir = next((d for d in sample_dirs if "2024-09-05" in d.name), None)
    
    # We need a few high-volume symbols to ensure overlap
    symbols = ['GME', 'SPY', 'NVDA', 'AAPL', 'MSFT']
    
    print(f"Checking {target_dir.name} for {symbols}...")
    
    data_map = load_multi_symbol_data(target_dir, symbols)
    
    if len(data_map) < 2:
        print("Not enough symbols loaded for cross-check.")
        return
        
    check_simultaneity(data_map)

if __name__ == "__main__":
    run_broadcast_check()
