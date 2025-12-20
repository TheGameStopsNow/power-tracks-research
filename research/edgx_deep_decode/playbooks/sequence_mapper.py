#!/usr/bin/env python3
"""
Sequence Mapper (Phase 26)
==========================

Decodes the "Grammar" of the EDGX Control Language.
Calculates Transition Probabilities and identifies common "Command Chains".

Hypothesis:
  - The "Power Tracks" are maintained by specific sequences of commands.
  - Example: Set Floor (0xA0) -> Lift (0x01) -> Stabilize (0x80).
"""

from pathlib import Path
import pandas as pd
import numpy as np
import sys
from collections import defaultdict, Counter

# Import local modules
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs
from core.extractors import extract_all_signals
from adversarial_decoding import bits_to_bytes
from extended_analysis import parse_messages

def map_sequences():
    print("=" * 60)
    print("SEQUENCE MAPPER: DECODING THE GRAMMAR")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    target_samples = [d for d in sample_dirs if "2024-05" in d.name]
    
    print(f"Scanning {len(target_samples)} days in May 2024...")
    
    all_msgs = []
    
    # Load and collect ordered messages per day
    for d in target_samples:
        try:
            df = load_edgx_data(d, symbol='GME')
            if df.empty: continue
            
            signals = extract_all_signals(df)
            byte_stream = bits_to_bytes(signals['price_lsb_1c'])
            msgs = parse_messages(byte_stream, df)
            
            # Extract header types sequence
            day_seq = []
            for m in msgs:
                if pd.notnull(m['header_type']):
                    op = f"0x{int(m['header_type']):02X}"
                    day_seq.append(op)
            
            if day_seq:
                all_msgs.append(day_seq)
                
        except Exception:
            pass
            
    print(f"Processed {len(all_msgs)} days of sequences.")
    
    # 1. Transition Matrix (Markov Chain)
    transitions = defaultdict(Counter)
    total_transitions = 0
    
    for seq in all_msgs:
        for i in range(len(seq) - 1):
            curr_op = seq[i]
            next_op = seq[i+1]
            transitions[curr_op][next_op] += 1
            total_transitions += 1
            
    # Print Top Transitions
    print("\nPRIMARY COMMAND LINKS (Transition Probabilities):")
    print(f"{'Source':<8} -> {'Target':<8} | {'Count':<5} | {'Prob':<6}")
    print("-" * 50)
    
    # Filter for significant sources (at least 5 occurrences)
    significant_sources = [k for k, v in transitions.items() if sum(v.values()) >= 5]
    
    sorted_sources = sorted(significant_sources, key=lambda k: sum(transitions[k].values()), reverse=True)
    
    for src in sorted_sources[:15]: # Top 15 most active opcodes
        counts = transitions[src]
        total = sum(counts.values())
        
        # Get top 3 targets for this source
        top_targets = counts.most_common(3)
        
        for tgt, count in top_targets:
            prob = count / total
            if prob > 0.10: # Only show significant links > 10%
                print(f"{src:<8} -> {tgt:<8} | {count:<5} | {prob:.2f}")
        print("-" * 50)
        
    # 2. Command Chains (3-grams)
    ngrams = Counter()
    
    for seq in all_msgs:
        if len(seq) < 3: continue
        for i in range(len(seq) - 2):
            # Chain string
            chain = f"{seq[i]} -> {seq[i+1]} -> {seq[i+2]}"
            ngrams[chain] += 1
            
    print("\nRECURRING COMMAND CHAINS (The Syntax):")
    print(f"{'Sequence':<30} | {'Count':<5}")
    print("-" * 50)
    
    for chain, count in ngrams.most_common(20):
        print(f"{chain:<30} | {count:<5}")
        
    # 3. Specific Logic Check (Example: Floor -> Lift)
    # Does 0xA0 (Floor) lead to 0x01 (Lift)?
    print("\nLOGIC CHECK: The 'Bounce' Sequence (0xA0 -> ?)")
    if '0xA0' in transitions:
        targets = transitions['0xA0'].most_common()
        for tgt, count in targets:
             print(f"  0xA0 -> {tgt}: {count}")
    else:
        print("  0xA0 not found in transitions.")

if __name__ == "__main__":
    map_sequences()
