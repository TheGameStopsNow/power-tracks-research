#!/usr/bin/env python3
"""
Protocol Inspector: DLE Framing Check
======================================

Hypothesis: The protocol uses DLE (Data Link Escape, 0x10) stuffing.
Standard DLE framing:
    Start: DLE STX (0x10 0x02)
    End:   DLE ETX (0x10 0x03)
    Data:  If 0x10 appears in data, it is doubled (0x10 0x10).
"""

from pathlib import Path
from typing import List, Dict
import pandas as pd
from collections import Counter

# Import local modules
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
from core.extractors import extract_all_signals
from adversarial_decoding import bits_to_bytes

DLE = 0x10
STX = 0x02
ETX = 0x03
SOH = 0x01

def parse_dle_messages(byte_stream: List[int]) -> List[List[int]]:
    """
    Parses messages checking for DLE-STX ... DLE-ETX.
    Handles DLE stuffing (0x10 0x10 -> 0x10).
    """
    messages = []
    current_msg = []
    in_message = False
    i = 0
    n = len(byte_stream)
    
    while i < n - 1:
        byte = byte_stream[i]
        next_byte = byte_stream[i+1]
        
        if byte == DLE:
            if next_byte == STX:
                # Start of Message
                in_message = True
                current_msg = []
                i += 2 # Skip DLE STX
                continue
            elif next_byte == ETX:
                # End of Message
                if in_message:
                    messages.append(current_msg)
                    in_message = False
                i += 2
                continue
            elif next_byte == DLE:
                # Escaped DLE
                if in_message:
                    current_msg.append(DLE)
                i += 2
                continue
                
        if in_message:
            current_msg.append(byte)
            
        i += 1
        
    return messages

def run_dle_check():
    print("=" * 60)
    print("DLE FRAMING CHECK")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    target_dir = next((d for d in sample_dirs if "2024-09-05" in d.name), None)
    
    print(f"Inspecting {target_dir.name}...")
    
    df_raw = load_edgx_data(target_dir, symbol='GME')
    signals = extract_all_signals(df_raw)
    byte_stream = bits_to_bytes(signals['price_lsb_1c'])
    
    # Check for DLE sequences count
    seqs = []
    for i in range(len(byte_stream)-1):
        if byte_stream[i] == DLE:
            seqs.append(f"10 {byte_stream[i+1]:02X}")
            
    print(f"\n[DLE Sequence Frequency]")
    print(pd.Series(seqs).value_counts().head(10).to_string())
    
    # Try Parsing
    messages = parse_dle_messages(byte_stream)
    print(f"\n[DLE Parsing Results]")
    print(f"  Found {len(messages)} DLE-framed messages.")
    
    for i, m in enumerate(messages[:5]):
        print(f"  Msg {i+1}: Length={len(m)}, Hex={' '.join([f'{b:02X}' for b in m[:20]])}...")

if __name__ == "__main__":
    run_dle_check()
