#!/usr/bin/env python3
"""
Message Payload Analyzer
========================

Deep analysis of the 22 decoded messages:
1. Map messages to market timestamps
2. Analyze payload byte patterns
3. Look for fixed-length fields
4. Correlate messages with price/volume events
"""

from pathlib import Path
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from collections import Counter, defaultdict
from dataclasses import dataclass
import json

# Import local modules
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
from core.extractors import extract_all_signals
from adversarial_decoding import bits_to_bytes
from semantic_mapper import map_opcodes_to_history

# Import Message class from packet_decoder
SOH = 0x01
STX = 0x02
ETX = 0x03
EOT = 0x04
NULL = 0x00
FILL = 0xFF

@dataclass
class TimestampedMessage:
    header: List[int]
    body: List[int]
    timestamp: pd.Timestamp
    byte_index: int
    price: float
    
def parse_messages_with_timestamps(byte_stream: List[int], df: pd.DataFrame) -> List[TimestampedMessage]:
    """
    Parse messages and map them to timestamps from the original dataframe.
    Each byte corresponds to 8 trades (skip=8).
    """
    messages = []
    i = 0
    n = len(byte_stream)
    
    while i < n:
        if byte_stream[i] == SOH:
            start_idx = i
            header = []
            body = []
            
            # Collect header until STX
            i += 1
            while i < n and byte_stream[i] != STX and len(header) < 50:
                if byte_stream[i] not in [NULL, FILL]:
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
                    # Map byte index to timestamp
                    # Byte K corresponds to trade index (K+1)*8 - 1
                    trade_idx = (start_idx + 1) * 8 - 1
                    
                    if trade_idx < len(df):
                        timestamp = df.iloc[trade_idx]['timestamp']
                        price = df.iloc[trade_idx]['price']
                        
                        messages.append(TimestampedMessage(
                            header=header,
                            body=body,
                            timestamp=timestamp,
                            byte_index=start_idx,
                            price=price
                        ))
                    i += 1
                    continue
                    
        i += 1
        
    return messages

def analyze_field_patterns(messages: List[TimestampedMessage]) -> Dict:
    """
    Analyze if message bodies have fixed-length field structure.
    """
    body_lengths = [len(m.body) for m in messages]
    
    # Check for common lengths (potential fixed formats)
    length_counts = Counter(body_lengths)
    
    # Analyze byte positions for all messages
    # Check if certain positions have consistent values
    max_len = max(body_lengths) if body_lengths else 0
    position_analysis = []
    
    for pos in range(min(20, max_len)):  # First 20 bytes
        values_at_pos = []
        for m in messages:
            if pos < len(m.body):
                values_at_pos.append(m.body[pos])
                
        if values_at_pos:
            unique_vals = len(set(values_at_pos))
            most_common = Counter(values_at_pos).most_common(1)[0]
            
            position_analysis.append({
                'position': pos,
                'unique_values': unique_vals,
                'most_common_byte': f"0x{most_common[0]:02X}",
                'frequency': most_common[1] / len(values_at_pos)
            })
            
    return {
        'body_length_distribution': dict(length_counts),
        'position_analysis': position_analysis[:10]  # Top 10 positions
    }

def correlate_with_market(messages: List[TimestampedMessage], df: pd.DataFrame) -> pd.DataFrame:
    """
    Correlate message occurrences with market events.
    """
    results = []
    
    for msg in messages:
        # Get market context around this message
        ts = msg.timestamp
        
        # Look backward and forward 10 seconds
        window_start = ts - pd.Timedelta(seconds=10)
        window_end = ts + pd.Timedelta(seconds=10)
        
        window_df = df[(df['timestamp'] >= window_start) & (df['timestamp'] <= window_end)]
        
        if len(window_df) > 0:
            price_change = (window_df['price'].iloc[-1] - window_df['price'].iloc[0]) / window_df['price'].iloc[0]
            volume_sum = len(window_df)
            price_volatility = window_df['price'].std()
            
            header_type = msg.header[0] if msg.header else None
            
            results.append({
                'timestamp': ts,
                'header_type': f"0x{header_type:02X}" if header_type is not None else "EMPTY",
                'header_len': len(msg.header),
                'body_len': len(msg.body),
                'price': msg.price,
                'price_change_10s': price_change * 10000,  # bps
                'volume_10s': volume_sum,
                'volatility': price_volatility
            })
            
    return pd.DataFrame(results)

def run_payload_analysis():
    print("=" * 60)
    print("MESSAGE PAYLOAD ANALYSIS")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    target_dir = next((d for d in sample_dirs if "2024-09-05" in d.name), None)
    
    print(f"Analyzing {target_dir.name}...")
    
    df_raw = load_edgx_data(target_dir, symbol='GME')
    signals = extract_all_signals(df_raw)
    byte_stream = bits_to_bytes(signals['price_lsb_1c'])
    
    # Parse with timestamps
    print("\n[1. Parsing Messages with Market Context...]")
    messages = parse_messages_with_timestamps(byte_stream, df_raw)
    print(f"  Found {len(messages)} timestamped messages")
    
    if not messages:
        print("  No messages to analyze.")
        return
        
    # Field Pattern Analysis
    print("\n[2. Field Pattern Analysis]")
    patterns = analyze_field_patterns(messages)
    
    print(f"  Body Length Distribution:")
    for length, count in sorted(patterns['body_length_distribution'].items()):
        print(f"    {length} bytes: {count} messages")
        
    print(f"\n  Byte Position Consistency (First 10 positions):")
    for p in patterns['position_analysis']:
        if p['frequency'] > 0.5:  # More than 50% messages have same value
            print(f"    Pos {p['position']}: {p['most_common_byte']} ({p['frequency']*100:.0f}% consistent) - Potential fixed field")
            
    # Market Correlation
    print("\n[3. Market Event Correlation]")
    corr_df = correlate_with_market(messages, df_raw)
    
    print(f"  Message Types and Market Impact:")
    grouped = corr_df.groupby('header_type').agg({
        'price_change_10s': 'mean',
        'volume_10s': 'mean',
        'volatility': 'mean'
    })
    print(grouped.to_string())
    
    # Time of Day Distribution
    print("\n[4. Message Time Distribution]")
    corr_df['hour'] = pd.to_datetime(corr_df['timestamp']).dt.hour
    hour_dist = corr_df['hour'].value_counts().sort_index()
    print("  Messages by Hour:")
    for hour, count in hour_dist.items():
        print(f"    {hour}:00 ET: {count} messages")
        
    # Save detailed results
    out_dir = BASE_DIR / "research" / "edgx_deep_decode" / "results"
    corr_df.to_csv(out_dir / "message_analysis.csv", index=False)
    print(f"\n  Saved detailed analysis to {out_dir / 'message_analysis.csv'}")

if __name__ == "__main__":
    run_payload_analysis()
