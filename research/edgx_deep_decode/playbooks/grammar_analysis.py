#!/usr/bin/env python3
"""
Grammar Analysis (Markov Transition Matrix)
===========================================

Analyzes the syntax of the sparse protocol by calculating the probability
of Opcode B following Opcode A ($P(O_{t+1}|O_t)$).

Objective:
    Identify "Start" bytes (followed by diverse outcomes), "Stop" bytes,
    and rigid sequences (e.g., 0x80 always followed by 0x01).
"""

from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from collections import Counter, defaultdict

# Import local modules
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
from core.extractors import extract_all_signals
from adversarial_decoding import bits_to_bytes


def build_transition_matrix(bytes_list: List[int]) -> pd.DataFrame:
    """
    Constructs a transition matrix for the byte stream.
    Focuses on the top 20 most frequent opcodes to keep visualization manageable.
    """
    # 1. Identify Top 20 tokens
    counts = Counter(bytes_list)
    top_20 = [k for k, v in counts.most_common(20)]
    
    # Filter stream to only these tokens for matrix (treat others as 'OTHER')
    # Actually, better to just compute full matrix for Top 20 vs Top 20
    
    transitions = defaultdict(Counter)
    
    for i in range(len(bytes_list) - 1):
        curr = bytes_list[i]
        next_ = bytes_list[i+1]
        
        if curr in top_20 and next_ in top_20:
            transitions[curr][next_] += 1
            
    # Convert to DataFrame
    matrix = pd.DataFrame(0, index=top_20, columns=top_20)
    
    for curr in top_20:
        total = sum(transitions[curr].values())
        if total > 0:
            for next_ in top_20:
                # Probability
                matrix.loc[curr, next_] = transitions[curr][next_] / total
                
    return matrix

def plot_transition_heatmap(matrix: pd.DataFrame, output_path: Path):
    plt.figure(figsize=(12, 12))
    
    # Convert labels to Hex
    hex_labels = [f"0x{x:02X}" for x in matrix.index]
    
    plt.imshow(matrix, cmap='viridis', interpolation='nearest')
    plt.colorbar()
    
    # Tiks
    plt.xticks(np.arange(len(hex_labels)), hex_labels, rotation=45)
    plt.yticks(np.arange(len(hex_labels)), hex_labels)
    
    # Annotate
    for i in range(len(hex_labels)):
        for j in range(len(hex_labels)):
            text = f"{matrix.iloc[i, j]:.2f}"
            if matrix.iloc[i, j] > 0.5:
                color = "black"
            else:
                color = "white"
            plt.text(j, i, text, ha="center", va="center", color=color, fontsize=8)
            
    plt.title("Opcode Transition Probability Matrix (P(Next|Current))")
    plt.xlabel("Next Opcode")
    plt.ylabel("Current Opcode")
    plt.tight_layout()
    plt.savefig(output_path)
    print(f"  Saved heatmap to {output_path}")

def analyze_sequences(bytes_list: List[int], min_len: int = 3) -> List[Tuple]:
    """
    Finds rigid sequences that appear frequently.
    Uses a sliding window approach.
    """
    seq_counts = Counter()
    
    # Scan for 3-grams
    for i in range(len(bytes_list) - min_len):
        seq = tuple(bytes_list[i : i+min_len])
        # Filter out sequences of just padding (0x00 or 0xFF)
        if set(seq).issubset({0, 255}):
            continue
        seq_counts[seq] += 1
        
    return seq_counts.most_common(20)

def run_grammar_analysis():
    print("=" * 60)
    print("PROTOCOL GRAMMAR ANALYSIS")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    # Use 2024-09-05 as a dense example
    target_dir = next((d for d in sample_dirs if "2024-09-05" in d.name), None)
    
    if not target_dir:
        print("Target sample not found.")
        return
        
    print(f"Analyzing {target_dir.name}...")
    df = load_edgx_data(target_dir, symbol='GME')
    signals = extract_all_signals(df)
    bits = signals['price_lsb_1c']
    byte_stream = bits_to_bytes(bits)
    
    print(f"  Stream Length: {len(byte_stream)} bytes")
    
    # 1. Transition Matrix
    matrix = build_transition_matrix(byte_stream)
    
    out_dir = BASE_DIR / "research" / "edgx_deep_decode" / "results"
    out_dir.mkdir(exist_ok=True)
    
    plot_transition_heatmap(matrix, out_dir / "transition_matrix.png")
    
    # 2. Strongest Links
    print("\n[Rigid Transitions (Prob > 0.5)]")
    # Identify localized structure
    for curr in matrix.index:
        row = matrix.loc[curr]
        best_next = row.idxmax()
        prob = row.max()
        
        if prob > 0.5:
            # Re-convert labels if they are ints (but we changed them to hex in plotting func only)
            # The matrix returned by build_transition_matrix has int index
            curr_hex = f"0x{curr:02X}"
            next_hex = f"0x{best_next:02X}"
            
            # Check if self-loop (padding)
            if curr == best_next:
                 if curr in [0, 255]:
                     continue # Ignore padding loops
            
            print(f"  {curr_hex} -> {next_hex} (Prob: {prob:.2%})")

    # 3. Sequence Mining
    print("\n[Frequent 3-byte Sequences (ignoring padding)]")
    top_seqs = analyze_sequences(byte_stream)
    for seq, count in top_seqs:
        hex_seq = " -> ".join([f"0x{b:02X}" for b in seq])
        print(f"  {hex_seq} : {count} occurrences")

if __name__ == "__main__":
    run_grammar_analysis()
