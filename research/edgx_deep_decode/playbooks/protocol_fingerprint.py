#!/usr/bin/env python3
"""
Protocol Fingerprinting
=======================

Compares the discovered opcode structure to known financial protocols
(OUCH, ITCH, FIX) to see if there's a match.

Key Signatures to Check:
    - NASDAQ OUCH uses single-byte message types (A, U, D, etc)
    - ITCH uses specific byte values for message types
    - FIX uses field tags and delimiters
"""

from pathlib import Path
from typing import Dict, List
import numpy as np
import pandas as pd
from collections import Counter

# Import local modules
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
from core.extractors import extract_all_signals
from adversarial_decoding import bits_to_bytes

# Known Protocol Signatures
# NASDAQ OUCH Message Types (ASCII)
OUCH_TYPES = {
    ord('A'): 'Accept Order',
    ord('U'): 'Replace Order',
    ord('D'): 'Cancel Order',
    ord('E'): 'Executed',
    ord('C'): 'Executed With Price',
    ord('X'): 'Canceled',
    ord('J'): 'Rejected',
    ord('P'): 'Priority Update',
    ord('I'): 'Order Imbalance',
    ord('B'): 'Broken Trade',
}

# NASDAQ ITCH 5.0 Message Types
ITCH_TYPES = {
    ord('S'): 'System Event',
    ord('R'): 'Stock Directory',
    ord('H'): 'Trading Action',
    ord('Y'): 'Reg SHO',
    ord('L'): 'Market Participant Position',
    ord('A'): 'Add Order (No MPID)',
    ord('F'): 'Add Order (With MPID)',
    ord('E'): 'Order Executed',
    ord('C'): 'Order Executed With Price',
    ord('X'): 'Order Cancel',
    ord('D'): 'Order Delete',
    ord('U'): 'Order Replace',
    ord('P'): 'Trade (Non-Cross)',
    ord('Q'): 'Cross Trade',
    ord('B'): 'Broken Trade',
    ord('I'): 'NOII',
}

# Special Byte Semantics
SPECIAL_BYTES = {
    0x00: 'NULL Terminator / Padding',
    0xFF: 'End of Frame / All-Ones Flag',
    0x01: 'SOH (Start of Header) or Boolean TRUE',
    0x02: 'STX (Start of Text)',
    0x03: 'ETX (End of Text)',
    0x04: 'EOT (End of Transmission)',
    0x7F: 'DEL (Delete) or Max Signed Int8',
    0x80: 'High Bit Set / Negative Start or MSB Flag',
    0xFE: 'All-Ones-Minus-One / Near Max',
}

def analyze_protocol_match(byte_stream: List[int]) -> Dict:
    """
    Checks if the top opcodes match any known protocol signatures.
    """
    counts = Counter(byte_stream)
    top_20 = counts.most_common(20)
    
    results = {
        'ouch_matches': [],
        'itch_matches': [],
        'special_bytes': [],
    }
    
    for opcode, count in top_20:
        if opcode in OUCH_TYPES:
            results['ouch_matches'].append({
                'byte': f"0x{opcode:02X}",
                'char': chr(opcode) if 32 <= opcode <= 126 else '.',
                'ouch_meaning': OUCH_TYPES[opcode],
                'count': count
            })
            
        if opcode in ITCH_TYPES:
            results['itch_matches'].append({
                'byte': f"0x{opcode:02X}",
                'char': chr(opcode) if 32 <= opcode <= 126 else '.',
                'itch_meaning': ITCH_TYPES[opcode],
                'count': count
            })
            
        if opcode in SPECIAL_BYTES:
            results['special_bytes'].append({
                'byte': f"0x{opcode:02X}",
                'meaning': SPECIAL_BYTES[opcode],
                'count': count
            })
            
    return results

def analyze_boundary_semantics(byte_stream: List[int]):
    """
    Investigates the specific semantics of the 0x7F/0x80/0xFE boundaries.
    These are critical in signed/unsigned byte representations.
    """
    # In signed int8:
    #   0x7F = +127 (max positive)
    #   0x80 = -128 (min negative)
    #   0xFE = -2
    #   0xFF = -1
    
    # Check if transitions respect signed boundaries
    signed_crossings = 0
    unsigned_wraps = 0
    
    for i in range(len(byte_stream) - 1):
        curr = byte_stream[i]
        next_ = byte_stream[i+1]
        
        # Signed boundary crossing: 0x7F <-> 0x80
        if (curr == 0x7F and next_ == 0x80) or (curr == 0x80 and next_ == 0x7F):
            signed_crossings += 1
            
        # Unsigned wrap: 0xFF <-> 0x00
        if (curr == 0xFF and next_ == 0x00) or (curr == 0x00 and next_ == 0xFF):
            unsigned_wraps += 1
            
    return {
        'signed_boundary_crossings': signed_crossings,
        'unsigned_wraps': unsigned_wraps
    }

def run_fingerprinting():
    print("=" * 60)
    print("PROTOCOL FINGERPRINTING")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    target_dir = next((d for d in sample_dirs if "2024-09-05" in d.name), None)
    
    print(f"Fingerprinting {target_dir.name}...")
    
    df_raw = load_edgx_data(target_dir, symbol='GME')
    signals = extract_all_signals(df_raw)
    byte_stream = bits_to_bytes(signals['price_lsb_1c'])
    
    # Protocol Match
    matches = analyze_protocol_match(byte_stream)
    
    print("\n[1. NASDAQ OUCH Match]")
    if matches['ouch_matches']:
        for m in matches['ouch_matches']:
            print(f"  {m['byte']} ({m['char']}): {m['ouch_meaning']} - {m['count']} occurrences")
    else:
        print("  No OUCH signature matches.")
        
    print("\n[2. NASDAQ ITCH Match]")
    if matches['itch_matches']:
        for m in matches['itch_matches']:
            print(f"  {m['byte']} ({m['char']}): {m['itch_meaning']} - {m['count']} occurrences")
    else:
        print("  No ITCH signature matches.")
        
    print("\n[3. Special Byte Semantics]")
    for s in matches['special_bytes']:
        print(f"  {s['byte']}: {s['meaning']} - {s['count']} occurrences")
        
    # Boundary Analysis
    print("\n[4. Signed/Unsigned Boundary Analysis]")
    boundary = analyze_boundary_semantics(byte_stream)
    print(f"  Signed Boundary Crossings (0x7F <-> 0x80): {boundary['signed_boundary_crossings']}")
    print(f"  Unsigned Wraps (0xFF <-> 0x00): {boundary['unsigned_wraps']}")
    
    # Interpretation
    print("\n[INTERPRETATION]")
    if boundary['signed_boundary_crossings'] > boundary['unsigned_wraps']:
        print("  The protocol appears to use SIGNED byte semantics.")
    else:
        print("  The protocol appears to use UNSIGNED byte semantics (more common in network protocols).")

if __name__ == "__main__":
    run_fingerprinting()
