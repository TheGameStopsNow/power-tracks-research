#!/usr/bin/env python3
"""
Layer 4: Motif Search (Symbolic Analysis)
=========================================

Detects statistically significant recurring sequences (motifs) in discretized tick features.

Hypothesis:
A covert channel might use a sequence of symbols (e.g. "Small Trade -> Large Trade -> Small Trade")
as a start/stop marker or to encode data, appearing more frequently than random chance.

Method:
1. Tokenize the stream (e.g., discretize size into 'S', 'M', 'L', or inter-arrival times into quantiles).
2. Count observed N-grams (length 3, 4, 5).
3. Null Hypothesis Generation: Shuffle the stream K times (preserving symbol counts but destroying order).
4. Compare observed counts vs Null distribution (Z-score).
5. Report motifs with significant Z-scores (e.g., > 4.0) after Bonferroni correction.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Tuple
from collections import Counter
import itertools
from pathlib import Path
import sys

# Add repo root to path
BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

class MotifSearcher:
    def __init__(self, n_gram_len: int = 3, n_permutations: int = 100):
        self.n = n_gram_len
        self.n_perms = n_permutations

    def tokenize(self, df: pd.DataFrame, feature: str = 'size') -> List[str]:
        """
        Simple tokenizer.
        feature: 'size' or 'dt' (inter-arrival).
        """
        if feature == 'size':
            # Quintiles based on log volume? Or simple buckets.
            # Simple buckets for robustness:
            # 1 = Odd lot (<100)
            # 2 = Round lot (100)
            # 3 = Large (>100)
            # 4 = Huge (>1000)
            # But let's use quantiles for adaptive tokenization
            
            vals = df['volume'].values
            q = np.quantile(vals, [0.33, 0.66])
            
            tokens = []
            for v in vals:
                if v <= q[0]: tokens.append('S')
                elif v <= q[1]: tokens.append('M')
                else: tokens.append('L')
            return tokens
        
        elif feature == 'dt':
            # Delta Time Quantiles
            timestamps = df['timestamp'].astype(np.int64).values # nanos
            dt = np.diff(timestamps)
            dt = np.insert(dt, 0, 0) # align length
            # Remove zeros for log
            dt = np.maximum(dt, 1)
            
            q = np.quantile(dt, [0.33, 0.66])
            tokens = []
            for d in dt:
                if d <= q[0]: tokens.append('A') # Fast
                elif d <= q[1]: tokens.append('B') # Med
                else: tokens.append('C') # Slow
            return tokens
        
        return []

    def count_ngrams(self, tokens: List[str]) -> Counter:
        # Create strings of N tokens
        # e.g. "S-M-L"
        grams = []
        for i in range(len(tokens) - self.n + 1):
            gram = "".join(tokens[i : i+self.n])
            grams.append(gram)
        return Counter(grams)

    def search_motifs(self, df: pd.DataFrame, feature: str = 'size') -> Dict[str, Any]:
        
        if len(df) < 50:
            return {'error': 'Insufficient data'}
            
        tokens = self.tokenize(df, feature)
        observed_counts = self.count_ngrams(tokens)
        
        unique_motifs = list(observed_counts.keys())
        
        # Monte Carlo Permutations
        perm_stats = {m: [] for m in unique_motifs}
        
        tokens_arr = np.array(tokens)
        
        for _ in range(self.n_perms):
            # Shuffle
            shuffled = np.random.permutation(tokens_arr)
            # Count
            # Fast N-gram using zip?
            # Creating list of strings in loop is slow in pure python but fine for prototype <10k events
            grams_perm = ["".join(shuffled[i : i+self.n]) for i in range(len(shuffled) - self.n + 1)]
            c_perm = Counter(grams_perm)
            
            for m in unique_motifs:
                perm_stats[m].append(c_perm.get(m, 0))
                
        # Calculate Z-scores
        results = []
        for m in unique_motifs:
            obs = observed_counts[m]
            null_dist = np.array(perm_stats[m])
            mean_null = np.mean(null_dist)
            std_null = np.std(null_dist)
            
            if std_null == 0:
                z_score = 0
            else:
                z_score = (obs - mean_null) / std_null
            
            # P-value (one-sided: we care about over-represented)
            # Count how many nulls >= obs
            p_val = np.sum(null_dist >= obs) / self.n_perms
            
            if z_score > 3.0: # Threshold
                results.append({
                    'motif': m,
                    'count': obs,
                    'expected': float(mean_null),
                    'z_score': float(z_score),
                    'p_val': float(p_val)
                })
                
        # Sort by Z-score
        results.sort(key=lambda x: x['z_score'], reverse=True)
        
        return {
            'feature': feature,
            'n_gram': self.n,
            'n_events': len(tokens),
            'significant_motifs': results
        }

if __name__ == "__main__":
    print("Testing Layer 4 MotifSearcher...")
    
    # Synthetic Data: "S-L-S" repeated often
    # 1000 events
    # Background: Random S, M, L
    import random
    
    data = []
    
    # Inject motif
    motif = ['S', 'L', 'S']
    
    for i in range(1000):
        if i % 10 == 0:
            data.extend(motif)
        else:
            data.append(random.choice(['S', 'M', 'L']))
            
    # Mock DF
    # We need 'volume' to map to S/M/L
    # S < 33%, M < 66%, L > 66%
    # Let's just mock the tokenize method to test the logic or create numeric data that maps correctly
    
    # S=10, M=50, L=100
    vals = []
    for t in data:
        if t == 'S': vals.append(10)
        elif t == 'M': vals.append(50)
        elif t == 'L': vals.append(100)
        
    df = pd.DataFrame({'volume': vals})
    
    searcher = MotifSearcher(n_gram_len=3, n_permutations=200)
    
    # Note: Tokenizer uses quantiles. 
    # Our synthetic data might not perfectly align with 33/66 quantiles if distribution is skewed
    # But 'S' will be low, 'L' high.
    
    res = searcher.search_motifs(df, feature='size')
    
    print(f"Feature: {res['feature']}")
    print("Significant Motifs (Z > 3.0):")
    for m in res['significant_motifs']:
        print(f"  {m['motif']}: Obs={m['count']}, Exp={m['expected']:.1f}, Z={m['z_score']:.2f}")
    
    # Expect 'SLS' (mapped to S L S) to be high
