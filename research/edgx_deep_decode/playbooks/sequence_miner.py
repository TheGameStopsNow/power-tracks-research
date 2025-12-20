#!/usr/bin/env python3
"""
Sequence Miner (Vocabulary Extraction)
======================================

Mines the protocol stream for "Words" and "Sentences".
Isolates active data packets from the padding carrier wave.

Methodology:
    1. Packetization: Split stream where > N contiguous padding bytes exist.
    2. N-Gram Analysis: Count frequencies of 3, 4, 5-byte sequences.
    3. Dictionary Generation: List unique, recurring packets.
"""

from pathlib import Path
from typing import Dict, List, Tuple
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

def packetize_stream(bytes_list: List[int], min_padding_run: int = 3) -> List[List[int]]:
    """
    Splits the stream into 'Active Packets' by cutting on runs of
    padding (0x00 or 0xFF).
    """
    packets = []
    current_packet = []
    
    pad_run = 0
    last_byte = -1
    
    for b in bytes_list:
        is_padding = (b == 0x00 or b == 0xFF)
        
        if is_padding:
            if b == last_byte:
                pad_run += 1
            else:
                pad_run = 1 # Reset if padding switches type (rare but possible)
        else:
            pad_run = 0
            
        last_byte = b
        
        # Logic: If we hit a run of N padding bytes, we consider the previous packet closed
        # But we only want to keep the *non-padding* parts
        
        if is_padding and pad_run >= min_padding_run:
            if current_packet:
                # Strip trailing padding
                while current_packet and (current_packet[-1] == 0x00 or current_packet[-1] == 0xFF):
                    current_packet.pop()
                    
                if current_packet:
                    packets.append(current_packet)
                current_packet = []
        else:
            # Add to current packet
            # If we were in a padding run but it broke, we start fresh or continue?
            # Ideally, we only add NON-padding bytes, or bytes that are part of the detailed message
            # Simple approach: Add everything, then split on pure blocks of padding.
            current_packet.append(b)
            
    # Cleanup: This logic is a bit messy because 'current_packet' includes the padding run until it hits limit
    # Better approach:
    # 1. Convert to string or list
    # 2. Split by delimiter tokens? No, stream is too long
    
    # Revised Logic:
    # Iterate. If byte is non-padding, add to curr.
    # If byte is padding, check if it's the start of a long run.
    
    clean_packets = []
    curr = []
    consecutive_pad = 0
    
    for b in bytes_list:
        if b == 0x00 or b == 0xFF:
            consecutive_pad += 1
            if consecutive_pad >= min_padding_run:
                # Close packet
                if curr:
                    # Remove the padding bytes that might have snuck in (the first min_run-1 bytes)
                    real_payload = curr[:-(min_padding_run-1)] if min_padding_run > 1 else curr
                    if real_payload:
                        clean_packets.append(real_payload)
                    curr = []
            else:
                curr.append(b) # Add potential padding (might be internal)
        else:
            consecutive_pad = 0
            curr.append(b)
            
    if curr:
        clean_packets.append(curr)
        
    return clean_packets

def mine_ngrams(packets: List[List[int]], n: int = 3) -> List[Tuple]:
    """
    Finds most frequent N-grams within the isolated packets.
    """
    ngrams = Counter()
    for p in packets:
        if len(p) < n:
            continue
        for i in range(len(p) - n + 1):
            seq = tuple(p[i : i+n])
            ngrams[seq] += 1
            
    return ngrams.most_common(50)

def run_sequence_mining():
    print("=" * 60)
    print("SEQUENCE MINER (VOCABULARY GENERATION)")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    # Use 2024-09-05 (Dense sample)
    target_dir = next((d for d in sample_dirs if "2024-09-05" in d.name), None)
    
    print(f"Mining {target_dir.name}...")
    df = load_edgx_data(target_dir, symbol='GME')
    signals = extract_all_signals(df)
    bits = signals['price_lsb_1c']
    byte_stream = bits_to_bytes(bits)
    
    print(f"  Stream Length: {len(byte_stream)} bytes")
    
    # Packetize
    # Use strict splitting: any run of 5+ padding bytes breaks the packet
    packets = packetize_stream(byte_stream, min_padding_run=5)
    print(f"  Isolated {len(packets)} active packets (non-padding clusters)")
    
    # Analyze Packet Lengths
    lengths = [len(p) for p in packets]
    if lengths:
        print(f"  Mean Packet Length: {np.mean(lengths):.2f} bytes")
        print(f"  Max Packet Length:  {np.max(lengths)} bytes")
    
    # Vocabulary Generation (Full Packets)
    print("\n[Recurring Full Packets (Sentences)]")
    # Convert active packets to tuples for counting
    packet_tuples = [tuple(p) for p in packets]
    sentence_counts = Counter(packet_tuples)
    
    for seq, count in sentence_counts.most_common(20):
        if len(seq) < 2: continue # Ignore single byte packets
        hex_seq = " ".join([f"{b:02X}" for b in seq])
        print(f"  [{hex_seq}] : {count} occurrences")
        
    # Vocabulary Generation (N-Grams / Words)
    print("\n[Recurring 3-Gram Words]")
    grams3 = mine_ngrams(packets, n=3)
    for seq, count in grams3[:15]:
         hex_seq = " ".join([f"{b:02X}" for b in seq])
         print(f"  {hex_seq} : {count}")
         
    print("\n[Recurring 4-Gram Words]")
    grams4 = mine_ngrams(packets, n=4)
    for seq, count in grams4[:15]:
         hex_seq = " ".join([f"{b:02X}" for b in seq])
         print(f"  {hex_seq} : {count}")

    # Save to JSON
    out_data = {
        "top_sentences": [{"hex": " ".join([f"{b:02X}" for b in k]), "count": v} for k, v in sentence_counts.most_common(50)],
        "top_3grams": [{"hex": " ".join([f"{b:02X}" for b in k]), "count": v} for k, v in grams3],
    }
    
    out_path = BASE_DIR / "research" / "edgx_deep_decode" / "results" / "vocabulary_20240905.json"
    with open(out_path, 'w') as f:
        json.dump(out_data, f, indent=2)
    print(f"\nSaved vocabulary to {out_path}")

if __name__ == "__main__":
    run_sequence_mining()
