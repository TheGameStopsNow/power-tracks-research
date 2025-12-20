#!/usr/bin/env python3
"""
Vocab Vectorizer (Contextual Clustering)
========================================

Uses Latent Semantic Analysis (LSA) to embed opcodes in 2D space.
Opcodes that appear in similar contexts (preceded/followed by same bytes)
will cluster together.

Methodology:
    1. Build Co-Occurrence Matrix (Window=1).
    2. Apply SVD (Singular Value Decomposition).
    3. Project to 2D components.
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

def build_cooccurrence_matrix(bytes_list: List[int], window: int = 1) -> pd.DataFrame:
    """
    Counts how often opcode B appears within +/- window of opcode A.
    """
    counts = Counter(bytes_list)
    top_20 = [k for k, v in counts.most_common(20)]
    
    # Initialize matrix
    matrix = pd.DataFrame(0, index=top_20, columns=top_20)
    
    for i in range(len(bytes_list)):
        curr = bytes_list[i]
        if curr not in top_20: continue
            
        start = max(0, i - window)
        end = min(len(bytes_list), i + window + 1)
        
        context = bytes_list[start:end]
        for neighbor in context:
            if neighbor in top_20 and neighbor != curr:
                matrix.loc[curr, neighbor] += 1
                
    return matrix

def compute_embeddings(cooc_matrix: pd.DataFrame) -> pd.DataFrame:
    """
    Applies SVD to the co-occurrence matrix.
    """
    # Normalize rows (P(Context|Word))
    vals = cooc_matrix.values
    # Add epsilon to avoid div by zero
    row_sums = vals.sum(axis=1)[:, np.newaxis] + 1e-10
    normalized = vals / row_sums
    
    # SVD
    U, S, Vt = np.linalg.svd(normalized, full_matrices=False)
    
    # Take top 2 components
    coords = U[:, :2] # * S[:2]  <-- Scaling by eigenvalues usually better
    
    # Scale by singular values for proper distance
    coords = coords * S[:2]
    
    embed_df = pd.DataFrame(coords, index=cooc_matrix.index, columns=['x', 'y'])
    return embed_df

def plot_embeddings(embed_df: pd.DataFrame, output_path: Path):
    plt.figure(figsize=(10, 8))
    
    x = embed_df['x']
    y = embed_df['y']
    labels = [f"0x{i:02X}" for i in embed_df.index]
    
    # Color by Polarity (Bit 7)
    colors = ['red' if idx > 127 else 'blue' for idx in embed_df.index]
    
    plt.scatter(x, y, c=colors, s=100, alpha=0.7, edgecolors='k')
    
    for i, txt in enumerate(labels):
        plt.text(x.iloc[i]+0.002, y.iloc[i]+0.002, txt, fontsize=9)
        
    plt.title("Opcode Embeddings (LSA/SVD)\nRed=HighBit, Blue=LowBit")
    plt.xlabel("Component 1 (Context)")
    plt.ylabel("Component 2 (Context)")
    plt.grid(True, alpha=0.3)
    plt.axhline(0, color='grey', linewidth=0.5)
    plt.axvline(0, color='grey', linewidth=0.5)
    
    plt.savefig(output_path)
    print(f"  Saved embedding plot to {output_path}")

def run_vectorization():
    print("=" * 60)
    print("VOCABULARY VECTORIZATION (SEMANTIC CLUSTERING)")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    target_dir = next((d for d in sample_dirs if "2024-09-05" in d.name), None)
    
    print(f"Vectorizing {target_dir.name}...")
    df = load_edgx_data(target_dir, symbol='GME')
    signals = extract_all_signals(df)
    bits = signals['price_lsb_1c']
    byte_stream = bits_to_bytes(bits)
    
    # 1. Co-occurrence
    cooc = build_cooccurrence_matrix(byte_stream, window=2)
    
    # 2. Embeddings
    embeds = compute_embeddings(cooc)
    
    # 3. Visualize
    out_dir = BASE_DIR / "research" / "edgx_deep_decode" / "results"
    plot_embeddings(embeds, out_dir / "opcode_clusters.png")
    
    # 4. Analyze Clusters
    # Calculate pairwise distances to find synonyms
    print("\n[Nearest Neighbors (Potential Synonyms)]")
    
    # Simple Euclidean distance
    from scipy.spatial.distance import pdist, squareform
    dists = squareform(pdist(embeds))
    dist_df = pd.DataFrame(dists, index=embeds.index, columns=embeds.index)
    
    # Find closest pair for each opcode
    for op in embeds.index:
        # Sort by distance
        closest = dist_df.loc[op].sort_values().index[1] # 0 is self
        score = dist_df.loc[op, closest]
        
        print(f"  0x{op:02X} <--> 0x{closest:02X} (Dist: {score:.4f})")

if __name__ == "__main__":
    run_vectorization()
