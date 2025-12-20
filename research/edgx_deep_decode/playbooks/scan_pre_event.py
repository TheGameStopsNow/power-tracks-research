#!/usr/bin/env python3
"""
Pre-Event Scanner (May 6-10, 2024)
==================================

Targeted extraction of every single protocol message during the "Quiet Week"
before the Roaring Kitty tweet (May 12) and the Price Rip (May 13).

Goal: Find the "Wake Up" signal.
"""

from pathlib import Path
from typing import Dict, List
import pandas as pd
import sys

# Import local modules
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
from extended_analysis import parse_messages # Reuse parser
from core.extractors import extract_all_signals
from adversarial_decoding import bits_to_bytes

def scan_pre_event():
    print("=" * 60)
    print("PRE-EVENT FORENSICS: MAY 6-10, 2024")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    # Filter for May 6-10
    target_dates = [6, 7, 8, 9, 10]
    target_samples = []
    
    for d in sample_dirs:
        if "2024-05" in d.name:
            day = int(d.name.split("-")[-1])
            if day in target_dates:
                target_samples.append(d)
                
    print(f"Scanning {len(target_samples)} days...")
    
    all_events = []
    
    for d in target_samples:
        try:
            df = load_edgx_data(d, symbol='GME')
            signals = extract_all_signals(df)
            byte_stream = bits_to_bytes(signals['price_lsb_1c'])
            
            msgs = parse_messages(byte_stream, df)
            for m in msgs:
                m['date'] = d.name.replace("sample_", "")
                # Format hex for readability
                m['header_hex'] = f"0x{int(m['header_type']):02X}" if m['header_type'] is not None else "None"
                all_events.append(m)
                
        except Exception as e:
            print(f"  Error loading {d.name}: {e}")
            
    # Sort and Print Chronologically
    df_events = pd.DataFrame(all_events)
    if df_events.empty:
        print("No events found.")
        return
        
    df_events['timestamp'] = pd.to_datetime(df_events['timestamp']).dt.tz_convert('US/Eastern')
    df_events = df_events.sort_values('timestamp')
    
    print(f"\nFound {len(df_events)} messages. Full Timeline:")
    print("-" * 80)
    print(f"{'Timestamp (ET)':<30} | {'Type':<6} | {'Session':<8} | {'Price':<8}")
    print("-" * 80)
    
    for _, row in df_events.iterrows():
        print(f"{str(row['timestamp']):<30} | {row['header_hex']:<6} | {row['session']:<8} | ${row['price']:.2f}")

    # Analysis
    print("\n" + "=" * 60)
    print("ANOMALY DETECTION")
    print("=" * 60)
    
    # Check Friday Post-Market (May 10 after 16:00)
    friday = df_events[df_events['date'] == '2024-05-10']
    friday_post = friday[friday['session'] == 'POST']
    
    if not friday_post.empty:
        print("Friday Post-Market Activity (The Weekend Signal?):")
        print(friday_post[['timestamp', 'header_hex', 'price']].to_string())
    else:
        print("No Post-Market activity on Friday May 10.")
        
    # Rare Types Check
    # What appeared this week that is rare?
    counts = df_events['header_hex'].value_counts()
    print("\nOpcode Distribution (May 6-10):")
    print(counts.to_string())

if __name__ == "__main__":
    scan_pre_event()
