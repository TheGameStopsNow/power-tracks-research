#!/usr/bin/env python3
"""
Packet Decoder (ASCII Framing)
==============================

Uses ASCII control codes for message framing:
    SOH (0x01) = Start of Header
    STX (0x02) = Start of Text (Body)
    ETX (0x03) = End of Text
    EOT (0x04) = End of Transmission

Standard ASCII Message Format:
    [SOH] [Header] [STX] [Body] [ETX] [EOT]

We will attempt to parse the byte stream using this structure.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from collections import Counter, defaultdict
from dataclasses import dataclass

# Import local modules
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR

# Optional dependencies (commented out for standalone package)
# from core.extractors import extract_all_signals
# from adversarial_decoding import bits_to_bytes

# Stub function for bits_to_bytes (if needed for legacy code)
def bits_to_bytes(bits):
    """Convert list of bits to bytes"""
    bytes_out = []
    for i in range(0, len(bits), 8):
        byte_bits = bits[i:i+8]
        if len(byte_bits) == 8:
            byte_val = sum(b << (7-j) for j, b in enumerate(byte_bits))
            bytes_out.append(byte_val)
    return bytes_out

# ASCII Control Codes
SOH = 0x01  # Start of Header
STX = 0x02  # Start of Text
ETX = 0x03  # End of Text
EOT = 0x04  # End of Transmission
NULL = 0x00
FILL = 0xFF

@dataclass
class Message:
    header: List[int]
    body: List[int]
    raw: List[int]
    start_idx: int
    
    def hex_header(self) -> str:
        return " ".join([f"{b:02X}" for b in self.header])
        
    def hex_body(self) -> str:
        return " ".join([f"{b:02X}" for b in self.body])

def parse_messages(byte_stream: List[int]) -> List[Message]:
    """
    Attempts to parse the byte stream using ASCII framing.
    Looks for patterns like: [SOH] ... [STX] ... [ETX]
    """
    messages = []
    i = 0
    n = len(byte_stream)
    
    while i < n:
        # Look for SOH
        if byte_stream[i] == SOH:
            start_idx = i
            header = []
            body = []
            
            # Collect header until STX or timeout
            i += 1
            while i < n and byte_stream[i] != STX and len(header) < 50:
                if byte_stream[i] not in [NULL, FILL]:  # Skip padding in header
                    header.append(byte_stream[i])
                i += 1
                
            # Found STX?
            if i < n and byte_stream[i] == STX:
                i += 1
                # Collect body until ETX
                while i < n and byte_stream[i] != ETX and len(body) < 100:
                    if byte_stream[i] not in [NULL, FILL]:
                        body.append(byte_stream[i])
                    i += 1
                    
                # Valid message if we found ETX
                if i < n and byte_stream[i] == ETX:
                    raw = byte_stream[start_idx : i+1]
                    messages.append(Message(header=header, body=body, raw=raw, start_idx=start_idx))
                    i += 1
                    continue
                    
        i += 1
        
    return messages

def analyze_messages(messages: List[Message]) -> Dict:
    """
    Analyzes the parsed messages.
    """
    if not messages:
        return {}
        
    # Statistics
    header_lengths = [len(m.header) for m in messages]
    body_lengths = [len(m.body) for m in messages]
    
    # Classify by first header byte
    header_types = Counter([tuple(m.header[:1]) if m.header else (None,) for m in messages])
    
    # Common bodies
    body_types = Counter([tuple(m.body) for m in messages])
    
    return {
        'count': len(messages),
        'avg_header_len': np.mean(header_lengths),
        'avg_body_len': np.mean(body_lengths),
        'header_types': header_types.most_common(10),
        'body_types': body_types.most_common(10)
    }

def run_packet_decoder():
    print("=" * 60)
    print("PACKET DECODER (ASCII FRAMING)")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    target_dir = next((d for d in sample_dirs if "2024-09-05" in d.name), None)
    
    print(f"Decoding {target_dir.name}...")
    
    df_raw = load_edgx_data(target_dir, symbol='GME')
    signals = extract_all_signals(df_raw)
    byte_stream = bits_to_bytes(signals['price_lsb_1c'])
    
    print(f"  Stream Length: {len(byte_stream)} bytes")
    
    # Count control codes
    counts = Counter(byte_stream)
    print(f"\n[Control Code Counts]")
    print(f"  SOH (0x01): {counts.get(SOH, 0)}")
    print(f"  STX (0x02): {counts.get(STX, 0)}")
    print(f"  ETX (0x03): {counts.get(ETX, 0)}")
    print(f"  EOT (0x04): {counts.get(EOT, 0)}")
    
    # Parse Messages
    print("\n[Parsing Messages using SOH/STX/ETX framing...]")
    messages = parse_messages(byte_stream)
    print(f"  Found {len(messages)} complete messages")
    
    if messages:
        stats = analyze_messages(messages)
        
        print(f"\n[Message Statistics]")
        print(f"  Avg Header Length: {stats['avg_header_len']:.1f} bytes")
        print(f"  Avg Body Length: {stats['avg_body_len']:.1f} bytes")
        
        print("\n[Sample Messages (First 5)]")
        for i, m in enumerate(messages[:5]):
            print(f"  Message {i+1}: Header=[{m.hex_header()}] Body=[{m.hex_body()}]")
            
        print("\n[Most Common Header Types]")
        for ht, count in stats['header_types']:
            hex_str = " ".join([f"0x{b:02X}" for b in ht]) if ht[0] is not None else "EMPTY"
            print(f"  {hex_str}: {count} occurrences")
            
    else:
        # Try alternative parsing: Look for any [SOH]...[ETX] without strict STX
        print("\n[Fallback: Searching for any SOH...ETX patterns]")
        simple_messages = []
        i = 0
        while i < len(byte_stream):
            if byte_stream[i] == SOH:
                start = i
                i += 1
                while i < len(byte_stream) and byte_stream[i] != ETX and i - start < 100:
                    i += 1
                if i < len(byte_stream) and byte_stream[i] == ETX:
                    simple_messages.append(byte_stream[start:i+1])
            i += 1
            
        print(f"  Found {len(simple_messages)} simple patterns")
        for i, m in enumerate(simple_messages[:5]):
            hex_str = " ".join([f"{b:02X}" for b in m])
            print(f"  Pattern {i+1}: [{hex_str}]")

if __name__ == "__main__":
    run_packet_decoder()
