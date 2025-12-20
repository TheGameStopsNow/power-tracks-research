#!/usr/bin/env python3
"""
Temporal Deep Dive (Time-of-Day Analysis)
==========================================

Explores whether opcode distribution changes throughout the trading day.
Hypothesis: If this is infrastructure traffic, it might be uniform.
            If it's market-related, it might cluster at open/close.
"""

from pathlib import Path
from typing import Dict, List
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from collections import defaultdict

# Import local modules
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
from core.extractors import extract_all_signals
from adversarial_decoding import bits_to_bytes
from semantic_mapper import map_opcodes_to_history

def analyze_time_of_day(events_df: pd.DataFrame) -> pd.DataFrame:
    """
    Bins opcode events by hour of day and calculates frequency.
    """
    df = events_df.copy()
    df['hour'] = pd.to_datetime(df['timestamp']).dt.hour
    
    # Top 10 Active Opcodes (excluding padding)
    active_ops = df[~df['opcode'].isin([0, 255])]['opcode'].value_counts().head(10).index.tolist()
    
    # Build Hour x Opcode count matrix
    hour_counts = defaultdict(lambda: defaultdict(int))
    
    for _, row in df.iterrows():
        op = row['opcode']
        hour = row['hour']
        if op in active_ops:
            hour_counts[hour][op] += 1
            
    # Convert to DataFrame
    hours = list(range(9, 17)) # Market hours
    matrix = pd.DataFrame(0, index=hours, columns=active_ops)
    
    for h in hours:
        for op in active_ops:
            matrix.loc[h, op] = hour_counts[h].get(op, 0)
            
    return matrix

def plot_time_heatmap(matrix: pd.DataFrame, output_path: Path):
    plt.figure(figsize=(12, 6))
    
    # Normalize by column (per opcode) to see relative distribution
    norm_matrix = matrix.div(matrix.sum(axis=0), axis=1)
    
    hex_labels = [f"0x{c:02X}" for c in matrix.columns]
    
    plt.imshow(norm_matrix.T, aspect='auto', cmap='YlOrRd')
    plt.colorbar(label='Relative Frequency')
    
    plt.yticks(range(len(hex_labels)), hex_labels)
    plt.xticks(range(len(matrix.index)), [f"{h}:00" for h in matrix.index])
    
    plt.xlabel("Hour (ET)")
    plt.ylabel("Opcode")
    plt.title("Opcode Distribution by Time of Day")
    plt.tight_layout()
    plt.savefig(output_path)
    print(f"  Saved time heatmap to {output_path}")

def analyze_bit_positions(byte_stream: List[int]) -> pd.DataFrame:
    """
    Decomposes the byte stream into 8 individual bit channels.
    Calculates the entropy/variance of each bit position.
    """
    arr = np.array(byte_stream, dtype=np.uint8)
    
    bit_data = []
    for bit_pos in range(8):
        bit_values = (arr >> bit_pos) & 1
        
        # Entropy (simple: count of 1s)
        p1 = np.mean(bit_values)
        p0 = 1 - p1
        
        # Shannon Entropy
        if p1 > 0 and p0 > 0:
            entropy = -(p1 * np.log2(p1) + p0 * np.log2(p0))
        else:
            entropy = 0
            
        # Autocorrelation
        if len(bit_values) > 100:
            ac = np.corrcoef(bit_values[:-1], bit_values[1:])[0, 1]
        else:
            ac = 0
            
        bit_data.append({
            'bit_pos': bit_pos,
            'p_one': p1,
            'entropy': entropy,
            'autocorr': ac
        })
        
    return pd.DataFrame(bit_data)

def build_transition_graph(byte_stream: List[int], top_n: int = 15):
    """
    Builds a directed graph of opcode transitions.
    Returns edges and their weights.
    """
    from collections import Counter
    
    counts = Counter(byte_stream)
    top_ops = [k for k, v in counts.most_common(top_n)]
    
    edges = defaultdict(int)
    
    for i in range(len(byte_stream) - 1):
        curr = byte_stream[i]
        next_ = byte_stream[i+1]
        
        if curr in top_ops and next_ in top_ops:
            edges[(curr, next_)] += 1
            
    return edges, top_ops

def plot_transition_graph(edges: dict, nodes: List[int], output_path: Path):
    """
    Creates a simple graph visualization using matplotlib.
    """
    # Attempt to use networkx if available
    try:
        import networkx as nx
        
        G = nx.DiGraph()
        for (src, dst), weight in edges.items():
            if weight > 10: # Filter weak edges
                G.add_edge(f"0x{src:02X}", f"0x{dst:02X}", weight=weight)
                
        plt.figure(figsize=(12, 12))
        pos = nx.spring_layout(G, k=2, iterations=50)
        
        # Separate High/Low
        node_colors = ['red' if int(n[2:], 16) > 127 else 'blue' for n in G.nodes()]
        
        nx.draw(G, pos, with_labels=True, node_color=node_colors, 
                node_size=1500, font_size=10, font_weight='bold',
                edge_color='gray', arrows=True, arrowsize=15)
                
        # Edge labels
        edge_labels = {(u, v): d['weight'] for u, v, d in G.edges(data=True) if d['weight'] > 50}
        nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=8)
        
        plt.title("Opcode Transition Graph\n(Red=High Channel, Blue=Low Channel)")
        plt.savefig(output_path)
        print(f"  Saved transition graph to {output_path}")
        
    except ImportError:
        print("  NetworkX not available, skipping graph visualization.")

def run_deep_exploration():
    print("=" * 60)
    print("DEEP STRUCTURAL EXPLORATION (PHASE 12)")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    target_dir = next((d for d in sample_dirs if "2024-09-05" in d.name), None)
    
    print(f"Analyzing {target_dir.name}...")
    
    df_raw = load_edgx_data(target_dir, symbol='GME')
    events = map_opcodes_to_history(df_raw)
    signals = extract_all_signals(df_raw)
    byte_stream = bits_to_bytes(signals['price_lsb_1c'])
    
    out_dir = BASE_DIR / "research" / "edgx_deep_decode" / "results"
    
    # 1. Time of Day
    print("\n[1. Time-of-Day Analysis]")
    tod_matrix = analyze_time_of_day(events)
    plot_time_heatmap(tod_matrix, out_dir / "time_of_day_heatmap.png")
    
    # Peak Hour Analysis
    total_per_hour = tod_matrix.sum(axis=1)
    peak_hour = total_per_hour.idxmax()
    print(f"  Peak Activity Hour: {peak_hour}:00 ET")
    
    # 2. Bit-Level
    print("\n[2. Bit-Level Decomposition]")
    bit_df = analyze_bit_positions(byte_stream)
    
    print("  Bit Position Analysis (Higher Entropy = More Information):")
    print(bit_df.to_string(index=False))
    
    # Identify "Hot" bits
    hot_bits = bit_df[bit_df['entropy'] > 0.8]['bit_pos'].tolist()
    cold_bits = bit_df[bit_df['entropy'] < 0.5]['bit_pos'].tolist()
    print(f"  Hot Bits (High Entropy): {hot_bits}")
    print(f"  Cold Bits (Low Entropy): {cold_bits}")
    
    # 3. Transition Graph
    print("\n[3. State Transition Graph]")
    edges, nodes = build_transition_graph(byte_stream)
    plot_transition_graph(edges, nodes, out_dir / "transition_graph.png")
    
    # Find Self-Loops (Persistence)
    print("  Self-Loops (State Persistence):")
    for (src, dst), weight in sorted(edges.items(), key=lambda x: -x[1])[:10]:
        if src == dst:
            print(f"    0x{src:02X} -> 0x{src:02X} : {weight} (Stable State)")

if __name__ == "__main__":
    run_deep_exploration()
