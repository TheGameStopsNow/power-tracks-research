#!/usr/bin/env python3
"""
Protocol Inspector (Forensics)
==============================

Deep dive into the byte structure of decoded messages.
1. Checksum Verification: Is the last byte an LRC (XOR sum) or Checksum?
2. Payload Decoding: Try to read payloads as ASCII, Int32, or BCD.
3. Metadata Matching: Do payload values match trade price/size?
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from collections import Counter, defaultdict
import struct

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

def parse_messages(byte_stream: List[int]) -> List[Dict]:
    """Parse messages with SOH...STX...ETX framing."""
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
                body = []
                while i < n and byte_stream[i] != ETX and len(body) < 150:
                    if byte_stream[i] not in [NULL, FILL]:
                        body.append(byte_stream[i])
                    i += 1
                    
                if i < n and byte_stream[i] == ETX:
                    # Capture the full raw packet including framing
                    raw = byte_stream[start_idx : i+1]
                    messages.append({
                        'header': header,
                        'body': body,
                        'raw': raw,
                        'start_idx': start_idx
                    })
                    continue
        i += 1
    return messages

def verify_checksums(messages: List[Dict]):
    """
    Test common checksum algorithms on the message content.
    Target: Last byte of body might be the checksum.
    """
    algorithms = {
        'XOR (LRC)': lambda data: getattr(np.bitwise_xor.reduce(data), 'item', lambda: 0)(),
        'SUM (Modulo 256)': lambda data: sum(data) % 256,
        'SUM (Inverted)': lambda data: (256 - (sum(data) % 256)) % 256
    }
    
    results = defaultdict(int)
    total_msgs = len(messages)
    
    for m in messages:
        body = m['body']
        if len(body) < 2:
            continue
            
        # Hypothesis 1: Last byte is checksum of everything before it in Body?
        candidate_checksum = body[-1]
        payload = body[:-1]
        
        # Hypothesis 2: Checksum covers Header + Body?
        # Let's focus on Body first as standard in some protocols
        
        for name, func in algorithms.items():
            calc = func(payload)
            if calc == candidate_checksum:
                results[f"Body_LastByte_{name}"] += 1
                
            # Try Header + Payload
            calc_full = func(m['header'] + payload)
            if calc_full == candidate_checksum:
                results[f"Full_LastByte_{name}"] += 1
                
    return results, total_msgs

def decode_payload_contents(messages: List[Dict]):
    """
    Attempt to interpret payloads as readable data.
    """
    print("\n[Payload Content Inspection]")
    
    for i, m in enumerate(messages[:10]): # Inspect top 10
        body = m['body']
        print(f"\nMessage {i+1} (Header: {' '.join([f'{b:02X}' for b in m['header']])})")
        print(f"  Raw Body: {' '.join([f'{b:02X}' for b in body])}")
        
        # 1. ASCII
        valid_ascii = [b for b in body if 32 <= b <= 126]
        if len(valid_ascii) > len(body) * 0.5: # 50% readable
            ascii_str = "".join([chr(b) for b in body if 32 <= b <= 126])
            print(f"  ASCII: \"{ascii_str}\"")
            
        # 2. Integers (Big Endian)
        # Try extracting 4-byte chunks
        if len(body) >= 4:
            vals = []
            for j in range(0, len(body)-3, 4):
                chunk = body[j:j+4]
                val = int.from_bytes(chunk, byteorder='big')
                vals.append(val)
                # Heuristic: Valid trade prices/sizes usually < 1,000,000,000
                if 0 < val < 10000000: 
                    print(f"  Int32 (Big): {val} (Offset {j})")
                    
    print("\n... (End of Sample Inspection)")

def run_forensics():
    print("=" * 60)
    print("PROTOCOL FORENSICS (PHASE 17)")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    target_dir = next((d for d in sample_dirs if "2024-09-05" in d.name), None)
    
    print(f"Inspecting {target_dir.name}...")
    
    df_raw = load_edgx_data(target_dir, symbol='GME')
    signals = extract_all_signals(df_raw)
    byte_stream = bits_to_bytes(signals['price_lsb_1c'])
    
    messages = parse_messages(byte_stream)
    print(f"  Found {len(messages)} messages.")
    
    if not messages:
        return

    # 1. Checksum Analysis
    print("\n[1. Checksum Algorithm Validation]")
    results, total = verify_checksums(messages)
    
    for algo, count in sorted(results.items(), key=lambda x: -x[1]):
        rate = count / total * 100
        print(f"  {algo}: {count}/{total} matches ({rate:.1f}%)")
        
    if not results:
        print("  No standard checksum algorithm matched.")
        
    # 2. Content Decoding
    decode_payload_contents(messages)

if __name__ == "__main__":
    run_forensics()
