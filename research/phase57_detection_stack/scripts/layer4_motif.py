#!/usr/bin/env python3
"""
Layer 4: Motif Mining
=====================

Detects "Recurrent Sequences" (Symbolic Motifs) that survive Permutation Testing.

Method:
1. Symbolize stream (e.g. Price Delta > 0 -> 'U', < 0 -> 'D', = 0 -> 'F').
2. Count N-grams (e.g. 3-grams 'UDU').
3. Null Hypothesis: Symbols are independent (or Markovian).
4. Permutation Test: Shake the stream (block bootstrap or simple shuffle) N times.
5. Identify motifs with P < 0.05 (FDR corrected).
"""

import numpy as np
import pandas as pd
from collections import Counter
import itertools
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from research.phase57_detection_stack.layer0_data_harness import TickLoader

class MotifMiner:
    def __init__(self, ngram_len: int = 3):
        self.n = ngram_len
        
    def symbolize(self, df: pd.DataFrame) -> str:
        """
        Convert trade stream to string of symbols.
        Simple grammar:
        Price Step: U (Up), D (Down), F (Flat)
        Size: S (Small < 100), L (Large >= 100)
        Combined: US, UL, DS, DL, FS, FL
        """
        # Price diff
        deltas = df['price'].diff().fillna(0)
        
        symbols = []
        sizes = df['volume'].values
        
        # Vectorized symbol construction?
        # Python loop is fine for <100k
        
        for d, s in zip(deltas, sizes):
            char_p = 'F'
            if d > 0: char_p = 'U'
            elif d < 0: char_p = 'D'
            
            char_s = 'S'
            if s >= 100: char_s = 'L'
            
            symbols.append(char_p + char_s)
            
        return symbols

    def count_ngrams(self, symbols: list) -> Counter:
        """Count occurrences of N-grams."""
        ngrams = zip(*[symbols[i:] for i in range(self.n)])
        # Join tuples back to strings
        ngram_strings = ["-".join(x) for x in ngrams]
        return Counter(ngram_strings)

    def block_shuffle(self, symbols: list, block_size: int = 20):
        """
        Shuffle blocks of symbols to preserve local autocorrelation.
        """
        n = len(symbols)
        if n == 0: return symbols
        
        # Split into blocks
        n_blocks = n // block_size
        remainder = n % block_size
        
        blocks = [symbols[i*block_size : (i+1)*block_size] for i in range(n_blocks)]
        if remainder:
            blocks.append(symbols[n_blocks*block_size:])
            
        np.random.shuffle(blocks)
        
        # Flatten
        return list(itertools.chain.from_iterable(blocks))

    def analyze_motifs(self, df: pd.DataFrame, n_perms: int = 100, block_size: int = 20):
        """
        Run permutation test with Block Shuffle.
        Returns robust motifs.
        """
        symbols = self.symbolize(df)
        if not symbols: return []
        
        real_counts = self.count_ngrams(symbols)
        
        # Store counts
        motif_perm_counts = {k: [] for k in real_counts.keys()}
        
        for _ in range(n_perms):
            # Phase 57b: Block Shuffle
            shuffled_syms = self.block_shuffle(symbols, block_size=block_size)
            
            perm_counts = self.count_ngrams(shuffled_syms)
            
            for k in real_counts.keys():
                motif_perm_counts[k].append(perm_counts.get(k, 0))
                
        # Calculate stats with FDR (Benjamini-Hochberg)
        # First get p-values for all motifs
        candidates = []
        for motif, observed in real_counts.items():
            if observed < 5: continue # Ignore rare
            
            nulls = np.array(motif_perm_counts[motif])
            mean_null = np.mean(nulls)
            std_null = np.std(nulls) 
            
            # P-value (One-sided)
            # Add 1 to avoid zero (conservative)
            p_val = (np.sum(nulls >= observed) + 1) / (n_perms + 1)
            
            # Z-score for info
            z = (observed - mean_null) / (std_null + 1e-9)
            
            candidates.append({
                'motif': motif,
                'observed': observed,
                'expected': mean_null,
                'z_score': z,
                'p_value': p_val
            })
            
        # FDR Correction
        candidates.sort(key=lambda x: x['p_value'])
        m = len(candidates)
        results = []
        
        for i, cand in enumerate(candidates):
            rank = i + 1
            # Critical value (Q=0.05)
            # BH: P(k) <= k/m * Q
            cand['fdr_threshold'] = (rank / m) * 0.05
            cand['significant'] = cand['p_value'] <= cand['fdr_threshold']
            
            if cand['significant']:
                results.append(cand)
                
        return sorted(results, key=lambda x: x['z_score'], reverse=True)


if __name__ == "__main__":
    loader = TickLoader()
    test_date = "2024-05-14"
    symbol = "GME"
    df = loader.load_ticks(test_date, symbol)
    
    if df is not None:
        # Slice
        sub = df.iloc[10000:15000].copy() # 5000 trades
        
        miner = MotifMiner(ngram_len=3)
        print("Mining Motifs (this may take a moment)...")
        motifs = miner.analyze_motifs(sub, n_perms=50)
        
        print(f"Found {len(motifs)} enriched motifs (p < 0.05):")
        for m in motifs[:5]:
            print(f"  {m['motif']}: Obs={m['observed']}, Exp={m['expected']:.1f}, Z={m['z_score']:.2f}")
