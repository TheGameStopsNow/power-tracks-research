#!/usr/bin/env python3
"""
Extended Hours Analysis (May 2024 Deep Dive)
============================================

Analyzes message distribution and signal predictive power across market sessions:
- Pre-Market (08:00 - 09:30)
- Regular Market (09:30 - 16:00)
- Post-Market (16:00 - 20:00)

Target Date Range: May 1, 2024 - May 18, 2024 (Roaring Kitty Week)
"""

from pathlib import Path
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from collections import Counter
import json

# Import local modules
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
from core.extractors import extract_all_signals
from adversarial_decoding import bits_to_bytes

# Constants
SOH = 0x01
STX = 0x02
ETX = 0x03
NULL = 0x00
FILL = 0xFF

def parse_messages(byte_stream: List[int], df: pd.DataFrame) -> List[Dict]:
    """Parse messages and attach timestamp/price."""
    messages = []
    i = 0
    n = len(byte_stream)
    
    while i < n:
        if byte_stream[i] == SOH:
            start_idx = i
            header = []
            i += 1
            while i < n and byte_stream[i] != STX and len(header) < 50:
                if byte_stream[i] not in [NULL, FILL]:
                    header.append(byte_stream[i])
                i += 1
            
            if i < n and byte_stream[i] == STX:
                i += 1
                while i < n and byte_stream[i] != ETX and i - start_idx < 150:
                    i += 1
                
                if i < n and byte_stream[i] == ETX:
                    trade_idx = (start_idx + 1) * 8 - 1
                    if trade_idx < len(df):
                        ts = df.iloc[trade_idx]['timestamp']
                        
                        # Determine session
                        # Convert to Market Time (ET)
                        ts_et = ts.tz_convert('US/Eastern')
                        time = ts_et.time()
                        
                        session = 'REGULAR'
                        if time < pd.Timestamp("09:30").time():
                            session = 'PRE'
                        elif time >= pd.Timestamp("16:00").time():
                            session = 'POST'
                            
                        messages.append({
                            'header_type': header[0] if header else None,
                            'timestamp': ts,
                            'session': session,
                            'price': df.iloc[trade_idx]['price']
                        })
                    i += 1
                    continue
        i += 1
    return messages

def analyze_may_samples():
    print("=" * 60)
    print("EXTENDED HOURS ANALYSIS: MAY 1-18, 2024")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    # Filter for May 1-18
    target_samples = []
    for d in sample_dirs:
        if "2024-05" in d.name:
            day = int(d.name.split("-")[-1])
            if 1 <= day <= 18:
                target_samples.append(d)
                
    print(f"Analyzing {len(target_samples)} samples...")
    
    all_messages = []
    
    for d in target_samples:
        print(f"  Scanning {d.name}...")
        try:
            df = load_edgx_data(d, symbol='GME')
            signals = extract_all_signals(df)
            byte_stream = bits_to_bytes(signals['price_lsb_1c'])
            
            msgs = parse_messages(byte_stream, df)
            for m in msgs:
                m['date'] = d.name.replace("sample_", "")
            
            all_messages.extend(msgs)
            print(f"    Found {len(msgs)} messages")
            
        except Exception as e:
            print(f"    Error: {e}")
            
    if not all_messages:
        print("No messages found.")
        return
        
    df_msgs = pd.DataFrame(all_messages)
    
    print("\n" + "=" * 60)
    print("SESSION DISTRIBUTION")
    print("=" * 60)
    
    session_counts = df_msgs['session'].value_counts()
    print(session_counts.to_string())
    
    print("\n" + "=" * 60)
    print("MESSAGE TYPES BY SESSION")
    print("=" * 60)
    
    session_types = pd.crosstab(df_msgs['header_type'].apply(lambda x: f"0x{int(x):02X}" if pd.notnull(x) else "None"), df_msgs['session'])
    print(session_types.to_string())
    
    # Check for predictive signals in Extended Hours
    # Specifically looking for the "Big Movers"
    print("\n" + "=" * 60)
    print("EXTENDED HOURS SIGNAL FORENSICS")
    print("=" * 60)
    
    # Filter for interesting events
    # Is there activity at 08:00?
    df_msgs['hour'] = df_msgs['timestamp'].dt.tz_convert('US/Eastern').dt.hour
    
    hourly = df_msgs['hour'].value_counts().sort_index()
    print("Messages by Hour:")
    print(hourly.to_string())

    print("\n" + "=" * 60)
    print("KEY SIGNAL DETAILS (0x27, 0xDF, 0x8D, 0x01)")
    print("=" * 60)
    
    targets = [0x27, 0xDF, 0x8D, 0x01]
    
    # Calculate returns if not already present
    # We need to look up N trades ahead. This is hard without full dataframe.
    # But we can just print the timestamp and let user cross ref for now.
    # Or better: Extract the signal instance and price.
    
    for _, row in df_msgs.iterrows():
        ht = row['header_type']
        if pd.notnull(ht) and int(ht) in targets:
            ts = row['timestamp'].tz_convert('US/Eastern')
            print(f"Signal 0x{int(ht):02X} | {ts} | {row['session']} | Price: ${row['price']:.2f}")
    
    # Detailed output
    out_dir = BASE_DIR / "research" / "edgx_deep_decode" / "results"
    df_msgs.to_csv(out_dir / "may_extended_analysis.csv", index=False)
    print(f"\nSaved results to {out_dir / 'may_extended_analysis.csv'}")

if __name__ == "__main__":
    analyze_may_samples()
