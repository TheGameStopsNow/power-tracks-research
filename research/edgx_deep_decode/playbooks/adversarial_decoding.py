#!/usr/bin/env python3
"""
Adversarial Decoding Module
===========================

Attempts to decode the extracted bitstream into readable text or opcodes
assuming various substitution ciphers or encoding schemes.

Techniques:
1. 8-bit ASCII mapping
2. Substitution Cipher Solver (Frequency Analysis)
3. Opcode Search (limited instruction set)
4. Entropy Visualization (rolling window)
"""

from pathlib import Path
from typing import List, Dict, Optional
import numpy as np
import pandas as pd
from collections import Counter
import matplotlib.pyplot as plt
import json

# Import local modules
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
from core.extractors import extract_all_signals


def bits_to_bytes(bits: List[int]) -> List[int]:
    """Convert bitstream to list of byte values (0-255)."""
    # Ensure divisible by 8
    n_bytes = len(bits) // 8
    bytes_list = []
    
    for i in range(n_bytes):
        chunk = bits[i*8 : (i+1)*8]
        val = 0
        for bit in chunk:
            val = (val << 1) | bit
        bytes_list.append(val)
        
    return bytes_list


def frequency_analysis(bytes_list: List[int]) -> Dict:
    """Analyze frequency of bytes."""
    counts = Counter(bytes_list)
    total = len(bytes_list)
    return {k: v/total for k, v in counts.items()}


def attempt_ascii_decode(bytes_list: List[int]) -> str:
    """
    Attempt to convert valid ASCII bytes to a string.
    Replaces non-printable chars with '.'.
    """
    chars = []
    for b in bytes_list:
        if 32 <= b <= 126:  # Printable ASCII
            chars.append(chr(b))
        else:
            chars.append('.')
    return "".join(chars)


def search_for_opcodes(
    bytes_list: List[int],
    vocab_size: int = 16
) -> Dict:
    """
    Analyze if the stream looks like a limited instruction set (opcodes).
    If the stream is dominated by a few unique values, it might be opcodes.
    """
    counts = Counter(bytes_list)
    most_common = counts.most_common(vocab_size)
    
    # Calculate coverage of top N tokens
    top_n_count = sum(c for _, c in most_common)
    coverage = top_n_count / len(bytes_list)
    
    return {
        'vocab_size': vocab_size,
        'coverage': coverage,
        'most_common_opcodes': most_common
    }


def analyze_rolling_entropy(
    bytes_list: List[int],
    window: int = 64
) -> List[float]:
    """Calculate rolling entropy to detect encrypted vs plaintext regions."""
    entropy_profile = []
    
    for i in range(0, len(bytes_list) - window, window // 4):
        chunk = bytes_list[i : i+window]
        counts = Counter(chunk)
        probs = [c/window for c in counts.values()]
        ent = -sum(p * np.log2(p) for p in probs)
        entropy_profile.append(ent)
        
    return entropy_profile


def run_adversarial_decoder(
    sample_dir: Path,
    signal_name: str = 'price_lsb_1c'
):
    print(f"Running Adversarial Decoding on {signal_name}...")
    
    # Load data
    df = load_edgx_data(sample_dir).head(50000)
    signals = extract_all_signals(df)
    
    if signal_name not in signals:
        print(f"Error: Signal {signal_name} not found.")
        return
        
    bits = signals[signal_name]
    byte_stream = bits_to_bytes(bits)
    
    print(f"  Extracted {len(byte_stream)} bytes")
    
    # 1. ASCII Decode
    ascii_text = attempt_ascii_decode(byte_stream)
    print(f"\n[ASCII Sample (first 200 chars)]:")
    print(f"  {ascii_text[:200]}")
    
    # Check for long alphanumeric strings
    import re
    alpha_strings = re.findall(r'[A-Za-z0-9]{4,}', ascii_text)
    print(f"\n  Found {len(alpha_strings)} alphanumeric strings > 4 chars")
    if alpha_strings:
        print(f"  Examples: {alpha_strings[:5]}")
    
    # 2. Opcode Analysis
    opcodes = search_for_opcodes(byte_stream)
    print(f"\n[Opcode Analysis]")
    print(f"  Top 16 values cover {opcodes['coverage']*100:.2f}% of stream")
    print(f"  Most common: {opcodes['most_common_opcodes'][:5]}")
    
    # 3. Rolling Entropy
    entropy = analyze_rolling_entropy(byte_stream)
    avg_ent = np.mean(entropy)
    print(f"\n[Entropy Analysis]")
    print(f"  Average Rolling Entropy: {avg_ent:.4f} (Max 8.0)")
    
    return {
        'ascii_sample': ascii_text[:500],
        'found_strings': alpha_strings[:20],
        'opcode_coverage': opcodes['coverage'],
        'avg_entropy': avg_ent
    }


if __name__ == "__main__":
    test_dir = get_sample_dirs()[-1]
    run_adversarial_decoder(test_dir)
