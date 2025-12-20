#!/usr/bin/env python3
"""
TISA Extended: Fractal Surveillance
===================================

Scans daily data for "Seeds" - recurring micro-structures that match
known high-impact signal bursts.

The "Holographic Principle" suggests that micro-scale bursts (0xDF)
contain compressed templates for macro-scale moves.

This tool:
1. Loads a "Seed" (e.g., May 16 0xDF burst).
2. Extracts its LSB signature.
3. Scans other days to find high-correlation matches (Hamming distance or similar).
"""

import sys
from pathlib import Path
from typing import List, Optional, Tuple, Dict
import pandas as pd
import numpy as np
from dataclasses import dataclass

# Import local modules
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs

@dataclass
class SeedSignature:
    name: str
    lsb_sequence: List[int]
    price_profile: List[float] # Normalized
    
class SeedCatalog:
    def __init__(self):
        self.seeds: Dict[str, SeedSignature] = {}
        
    def load_seed_from_csv(self, name: str, filepath: Path):
        df = pd.read_csv(filepath)
        # Extract LSBs
        # Assuming price is raw, let's just take int(price*100) & 1 like before
        lsbs = [int(p * 100) & 1 for p in df['price']]
        
        # Normalized price profile (0-1)
        prices = df['price'].values
        norm_prices = (prices - np.min(prices)) / (np.max(prices) - np.min(prices) + 1e-9)
        
        self.seeds[name] = SeedSignature(
            name=name,
            lsb_sequence=lsbs,
            price_profile=norm_prices.tolist()
        )
        print(f"Loaded Seed '{name}': {len(lsbs)} ticks")

def scan_day(df: pd.DataFrame, seed: SeedSignature, threshold: float = 0.8) -> List[dict]:
    """
    Scans a day's dataframe for the seed pattern.
    Uses sliding window bit-matching (Hamming accuracy).
    """
    matches = []
    
    day_lsbs = np.array([int(p * 100) & 1 for p in df['price'].values])
    seed_lsbs = np.array(seed.lsb_sequence)
    
    n = len(day_lsbs)
    m = len(seed_lsbs)
    
    if n < m:
        return []
        
    # Sliding window validation
    # This can be slow in pure Python, so we'll do a simple stride or optimized numpy way
    # For < 100k ticks, specific numpy sliding is best
    
    # Create view of windows
    # shape (n-m+1, m)
    # This might be too memory intensive if n is huge and m is large.
    # Let's do a stride loop for safety or use convolution if it were cross-correlation.
    # For bit matching: (Window == Seed).mean()
    
    print(f"Scanning {n} ticks for {m}-length pattern...")
    
    # Heuristic: Check every 10th tick to speed up, then refine? 
    # Or just run full scan if m is small (~500). 500 * 100k = 50M ops (doable)
    
    step = 10 # Optimization
    
    for i in range(0, n - m, step):
        window = day_lsbs[i : i+m]
        match_score = np.mean(window == seed_lsbs)
        
        if match_score >= threshold:
            # Refine local max?
            matches.append({
                'index': i,
                'timestamp': df.iloc[i]['timestamp'],
                'score': match_score,
                'price': df.iloc[i]['price']
            })
            
    return matches

def run_tisa_scan():
    print("=" * 60)
    print("TISA EXTENDED: FRACTAL SURVEILLANCE")
    print("=" * 60)
    
    # 1. Load Seed
    catalog = SeedCatalog()
    base_dir = Path(__file__).parent
    seed_path = base_dir / "seed_may16_0xDF.csv"
    
    if not seed_path.exists():
        print(f"Error: Seed file not found at {seed_path}")
        return
        
    catalog.load_seed_from_csv("May16_0xDF", seed_path)
    seed = catalog.seeds["May16_0xDF"]
    
    # 2. Load Target Day
    sample_dirs = get_sample_dirs()
    if not sample_dirs:
        return
        
    target_dir = sample_dirs[-1] # Scan latest
    print(f"Scanning Target: {target_dir.name}")
    
    df = load_edgx_data(target_dir, symbol='GME')
    
    # 3. Match
    hits = scan_day(df, seed, threshold=0.75) # Lower threshold for fuzzy matching
    
    print(f"\nScan Complete. Found {len(hits)} Candidate Matches (>75%)")
    
    # Deduplicate hits (consecutive windows)
    if hits:
        # Sort by score
        hits.sort(key=lambda x: x['score'], reverse=True)
        top_hit = hits[0]
        print(f"Top Match: Score {top_hit['score']:.1%} @ {top_hit['timestamp']}")
        
        print("\nTop 5 Hits:")
        for h in hits[:5]:
            print(f"  {h['timestamp']} | Score: {h['score']:.1%} | Price: ${h['price']:.2f}")

if __name__ == "__main__":
    run_tisa_scan()
