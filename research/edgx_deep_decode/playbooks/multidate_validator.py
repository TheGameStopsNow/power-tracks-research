#!/usr/bin/env python3
"""
Multi-Date Message Signal Validator
====================================

Validates the predictive power of message types across all historical dates.
Tests hypothesis: Do 0x27/0xDF/0x8D consistently predict price movements?
"""

from pathlib import Path
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from collections import Counter, defaultdict
import json

# Import local modules
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
from core.extractors import extract_all_signals
from adversarial_decoding import bits_to_bytes

# Message parsing constants
SOH = 0x01
STX = 0x02
ETX = 0x03
NULL = 0x00
FILL = 0xFF

def parse_messages_simple(byte_stream: List[int], df: pd.DataFrame) -> List[Dict]:
    """Simplified message parser returning header type and timestamp."""
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
                        header_type = header[0] if header else None
                        messages.append({
                            'header_type': header_type,
                            'timestamp': df.iloc[trade_idx]['timestamp'],
                            'price': df.iloc[trade_idx]['price'],
                            'byte_index': start_idx
                        })
                    i += 1
                    continue
        i += 1
        
    return messages

def calculate_message_alpha(messages: List[Dict], df: pd.DataFrame) -> pd.DataFrame:
    """Calculate forward returns for each message."""
    results = []
    
    for msg in messages:
        if msg['header_type'] is None:
            continue
            
        ts = msg['timestamp']
        window_start = ts
        window_end = ts + pd.Timedelta(seconds=10)
        
        future_df = df[(df['timestamp'] > window_start) & (df['timestamp'] <= window_end)]
        
        if len(future_df) > 0:
            price_change = (future_df['price'].iloc[-1] - msg['price']) / msg['price']
            
            results.append({
                'header_type': f"0x{msg['header_type']:02X}",
                'alpha_10s': price_change * 10000  # bps
            })
            
    return pd.DataFrame(results)

def process_single_date(sample_dir: Path) -> Optional[pd.DataFrame]:
    """Process a single date and return message alpha statistics."""
    try:
        df = load_edgx_data(sample_dir, symbol='GME')
        if df.empty or len(df) < 1000:
            return None
            
        signals = extract_all_signals(df)
        byte_stream = bits_to_bytes(signals['price_lsb_1c'])
        
        messages = parse_messages_simple(byte_stream, df)
        if not messages:
            return None
            
        alpha_df = calculate_message_alpha(messages, df)
        if alpha_df.empty:
            return None
            
        return alpha_df
        
    except Exception as e:
        return None

def run_multidate_validation():
    print("=" * 60)
    print("MULTI-DATE MESSAGE SIGNAL VALIDATION")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    
    all_results = []
    
    print("\nProcessing dates...")
    for sample_dir in sample_dirs:
        date_str = sample_dir.name.replace('sample_', '')
        
        alpha_df = process_single_date(sample_dir)
        
        if alpha_df is not None and not alpha_df.empty:
            alpha_df['date'] = date_str
            all_results.append(alpha_df)
            
            msg_count = len(alpha_df)
            avg_alpha = alpha_df['alpha_10s'].mean()
            print(f"  {date_str}: {msg_count:3d} messages | Avg Alpha: {avg_alpha:+7.2f} bps")
        else:
            print(f"  {date_str}: No messages")
            
    if not all_results:
        print("\nNo data to analyze.")
        return
        
    # Combine all dates
    combined_df = pd.concat(all_results, ignore_index=True)
    
    print("\n" + "=" * 60)
    print("AGGREGATE STATISTICS BY MESSAGE TYPE")
    print("=" * 60)
    
    stats = combined_df.groupby('header_type').agg({
        'alpha_10s': ['count', 'mean', 'std', lambda x: (x > 0).sum() / len(x)]
    }).round(2)
    
    stats.columns = ['Count', 'Mean Alpha (bps)', 'Std Dev', 'Win Rate']
    stats = stats.sort_values('Mean Alpha (bps)', ascending=False)
    
    print(stats.to_string())
    
    # Focus on the "discovered" signals
    print("\n" + "=" * 60)
    print("KEY SIGNAL VALIDATION")
    print("=" * 60)
    
    key_signals = ['0x27', '0xDF', '0x8D', '0x01']
    
    for sig in key_signals:
        sig_data = combined_df[combined_df['header_type'] == sig]['alpha_10s']
        
        if len(sig_data) > 0:
            mean_alpha = sig_data.mean()
            win_rate = (sig_data > 0).sum() / len(sig_data)
            n = len(sig_data)
            
            # T-test: Is mean significantly different from 0?
            from scipy import stats as sp_stats
            if len(sig_data) > 1:
                t_stat, p_val = sp_stats.ttest_1samp(sig_data, 0)
            else:
                p_val = 1.0
                
            print(f"\n{sig}:")
            print(f"  Occurrences: {n}")
            print(f"  Mean Alpha: {mean_alpha:+.2f} bps")
            print(f"  Win Rate: {win_rate:.1%}")
            print(f"  P-Value: {p_val:.4f} {'***' if p_val < 0.01 else '**' if p_val < 0.05 else '*' if p_val < 0.1 else ''}")
            
    # Save results
    out_dir = BASE_DIR / "research" / "edgx_deep_decode" / "results"
    combined_df.to_csv(out_dir / "multidate_validation.csv", index=False)
    
    # Summary JSON
    summary = {
        'total_messages': len(combined_df),
        'unique_dates': combined_df['date'].nunique(),
        'message_types': len(combined_df['header_type'].unique()),
        'top_performers': stats.head(5).to_dict(),
    }
    
    with open(out_dir / "multidate_summary.json", 'w') as f:
        json.dump(summary, f, indent=2, default=str)
        
    print(f"\n\nSaved results to {out_dir}")
    print(f"  - multidate_validation.csv")
    print(f"  - multidate_summary.json")

if __name__ == "__main__":
    run_multidate_validation()
