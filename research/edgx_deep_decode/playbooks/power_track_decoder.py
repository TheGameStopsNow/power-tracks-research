#!/usr/bin/env python3
"""
Power Track Decoder (Phase 24)
==============================

Deconstructs the signal stream into constituent "Power Tracks" based on Opcode.
Target Date: May 17, 2024 (Matches User's Image).

Hypothesis:
  - Specific Opcodes form the "High Power Line"
  - Specific Opcodes form the "Low Power Line"
  - The "Power Spread" is the delta between these tracks.
"""

from pathlib import Path
import pandas as pd
import sys

# Import local modules
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs
from core.extractors import extract_all_signals
from adversarial_decoding import bits_to_bytes
from extended_analysis import parse_messages

def decode_power_tracks():
    print("=" * 60)
    print("POWER TRACK DECODER: MAY 17, 2024")
    print("=" * 60)
    
    # Load May 17 Data
    sample_dirs = get_sample_dirs()
    target_dir = next((d for d in sample_dirs if "2024-05-17" in d.name), None)
    
    if not target_dir:
        print("May 17 sample not found.")
        return
        
    print(f"Loading {target_dir.name}...")
    df = load_edgx_data(target_dir, symbol='GME')
    
    # Extract
    signals = extract_all_signals(df)
    byte_stream = bits_to_bytes(signals['price_lsb_1c'])
    msgs = parse_messages(byte_stream, df)
    
    if not msgs:
        print("No messages found.")
        return
        
    df_msgs = pd.DataFrame(msgs)
    df_msgs['header_hex'] = df_msgs['header_type'].apply(lambda x: f"0x{int(x):02X}" if pd.notnull(x) else "None")
    df_msgs['timestamp'] = pd.to_datetime(df_msgs['timestamp']).dt.tz_convert('US/Eastern')
    
    print(f"Total Messages: {len(df_msgs)}")
    
    # Group by Opcode
    print("\nOpcode Statistics (The Tracks):")
    print(f"{'Opcode':<8} | {'Count':<5} | {'Min Price':<10} | {'Max Price':<10} | {'Avg Price':<10}")
    print("-" * 60)
    
    stats = []
    for op, group in df_msgs.groupby('header_hex'):
        stats.append({
            'Opcode': op,
            'Count': len(group),
            'Min': group['price'].min(),
            'Max': group['price'].max(),
            'Avg': group['price'].mean()
        })
        
    stats.sort(key=lambda x: x['Avg'], reverse=True)
    
    for s in stats:
        print(f"{s['Opcode']:<8} | {s['Count']:<5} | ${s['Min']:<9.2f} | ${s['Max']:<9.2f} | ${s['Avg']:<9.2f}")
        
    # Correlation Check
    # High vs Low Tracks
    # User image implies "High Power Line" and "Low Power Line".
    # Do we see a separation?
    
    print("\nTrack Analysis:")
    high_track = [s['Opcode'] for s in stats[:3]] # Top 3 highest priced opcodes
    low_track = [s['Opcode'] for s in stats[-3:]] # Bottom 3
    
    print(f"Potential HIGH Track Opcodes: {', '.join(high_track)}")
    print(f"Potential LOW Track Opcodes:  {', '.join(low_track)}")
    
    # Print Timeline of Tracks
    print("\nTimeline (Track Switching):")
    df_msgs = df_msgs.sort_values('timestamp')
    for _, row in df_msgs.iterrows():
        track_type = "MID"
        if row['header_hex'] in high_track: track_type = "HIGH"
        if row['header_hex'] in low_track: track_type = "LOW"
        
        print(f"{str(row['timestamp'].time())} | {row['header_hex']:<6} | ${row['price']:.2f} | {track_type}")

if __name__ == "__main__":
    decode_power_tracks()
