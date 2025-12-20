#!/usr/bin/env python3
"""
Cross-Date Vocabulary Stability Analysis
=========================================

Checks if the opcode vocabulary is consistent across all historical dates.
If the vocabulary changes, it might indicate regime shifts or updates to
the underlying infrastructure.
"""

from pathlib import Path
from typing import Dict, List
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

def get_vocabulary_for_date(sample_dir: Path) -> Dict[int, int]:
    """
    Returns opcode frequency counts for a single date.
    """
    try:
        df = load_edgx_data(sample_dir, symbol='GME')
        if df.empty or len(df) < 1000:
            return {}
            
        signals = extract_all_signals(df)
        byte_stream = bits_to_bytes(signals['price_lsb_1c'])
        return Counter(byte_stream)
    except Exception as e:
        return {}

def run_stability_check():
    print("=" * 60)
    print("CROSS-DATE VOCABULARY STABILITY CHECK")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    
    all_vocabs = {}
    
    for d in sample_dirs:
        vocab = get_vocabulary_for_date(d)
        if vocab:
            date_str = d.name.replace('sample_', '')
            all_vocabs[date_str] = vocab
            total = sum(vocab.values())
            top_3 = vocab.most_common(3)
            top_str = ", ".join([f"0x{k:02X}:{v/total*100:.1f}%" for k, v in top_3])
            print(f"  {date_str}: {total:>6} bytes | Top-3: {top_str}")
            
    # Calculate Vocabulary Overlap
    print("\n[Vocabulary Overlap Analysis]")
    
    # Get union of all Top-20 opcodes across all dates
    all_top_20 = set()
    for vocab in all_vocabs.values():
        for op, _ in vocab.most_common(20):
            all_top_20.add(op)
            
    print(f"  Unique opcodes in Top-20 across all dates: {len(all_top_20)}")
    
    # Check which opcodes are ALWAYS in Top-20
    stable_opcodes = []
    for op in all_top_20:
        present_in_all = all([op in set([k for k, v in v.most_common(20)]) for v in all_vocabs.values()])
        if present_in_all:
            stable_opcodes.append(op)
            
    print(f"  Opcodes consistently in Top-20: {[f'0x{o:02X}' for o in sorted(stable_opcodes)]}")
    
    # Calculate Jaccard Similarity between consecutive dates
    print("\n[Temporal Stability (Jaccard Similarity of Top-20)]")
    
    dates = sorted(all_vocabs.keys())
    for i in range(len(dates) - 1):
        date1, date2 = dates[i], dates[i+1]
        
        set1 = set([k for k, v in all_vocabs[date1].most_common(20)])
        set2 = set([k for k, v in all_vocabs[date2].most_common(20)])
        
        jaccard = len(set1 & set2) / len(set1 | set2)
        print(f"  {date1} <-> {date2}: {jaccard:.2%}")

if __name__ == "__main__":
    run_stability_check()
