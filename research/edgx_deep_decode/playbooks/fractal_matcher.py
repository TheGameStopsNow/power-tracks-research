#!/usr/bin/env python3
"""
Fractal Matcher: The "Tsunami" Hypothesis
==========================================

Tests the theory that micro-scale tick bursts act as "compressed seeds" 
for future macro-scale price action.

Methodology:
1. Extract "Micro-Shapes": Price paths of 100-500 ticks following key signals (0xDF, 0x27).
2. Normalize: MinMax scaling to 0-1 range (Price and Time).
3. Search: Sliding window over Macro Data (Hourly/Daily bars).
4. Compare: Use Euclidean Distance (Correlation) and DTW (Dynamic Time Warping) to match shapes.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.spatial.distance import euclidean

# Import local modules
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
from core.extractors import extract_all_signals
from adversarial_decoding import bits_to_bytes
from extended_analysis import parse_messages # Reuse parser

def normalize_series(s: np.array) -> np.array:
    """MinMax normalization to 0-1 range."""
    if len(s) == 0: return s
    min_val = np.min(s)
    max_val = np.max(s)
    if max_val - min_val == 0:
        return np.zeros_like(s)
    return (s - min_val) / (max_val - min_val)

def simple_dtw(s1, s2):
    """
    Simple Dynamic Time Warping implementation (O(N^2)).
    Returns distance score (lower is better).
    """
    n, m = len(s1), len(s2)
    dtw_matrix = np.zeros((n+1, m+1))
    
    dtw_matrix[0, 1:] = np.inf
    dtw_matrix[1:, 0] = np.inf
    
    for i in range(1, n+1):
        for j in range(1, m+1):
            cost = abs(s1[i-1] - s2[j-1])
            dtw_matrix[i, j] = cost + min(dtw_matrix[i-1, j],    # insertion
                                          dtw_matrix[i, j-1],    # deletion
                                          dtw_matrix[i-1, j-1])  # match
    return dtw_matrix[n, m]

def extract_seeds(target_opcode=0xDF, window=200):
    """Extract price paths following specific opcodes."""
    print(f"Extracting seeds for 0x{target_opcode:02X}...")
    sample_dirs = get_sample_dirs()
    # Focus on May dates
    seeds = []
    
    for d in sample_dirs:
        if "2024-05" not in d.name: continue
        
        try:
            df = load_edgx_data(d, symbol='GME')
            signals = extract_all_signals(df)
            byte_stream = bits_to_bytes(signals['price_lsb_1c'])
            msgs = parse_messages(byte_stream, df)
            
            for m in msgs:
                if m['header_type'] == target_opcode:
                    # Find the index in the original DF matching this message
                    # parse_messages gives us 'timestamp' and 'price'
                    # We need the index
                    ts = m['timestamp']
                    idx = df[df['timestamp'] == ts].index[0]
                    
                    # Extract forward window
                    if idx + window < len(df):
                        path = df.iloc[idx : idx+window]['price'].values
                        seeds.append({
                            'date': d.name,
                            'timestamp': ts,
                            'path': path,
                            'norm_path': normalize_series(path)
                        })
        except Exception:
            continue
            
    print(f"  Found {len(seeds)} seeds.")
    return seeds

def load_macro_data(symbol="GME"):
    """
    Simulate loading macro data. 
    In a real scenario, we'd pull hourly candles.
    Here, we'll downsample the high-res tick data we have to simulate 'Macro'.
    """
    print("Constructing Macro Chart (Simulated from Ticks)...")
    sample_dirs = get_sample_dirs()
    
    full_price_history = []
    
    for d in sample_dirs:
        if "2024-05" in d.name:
            try:
                df = load_edgx_data(d, symbol='GME')
                # Downsample to 1-minute bars to simulate "Macro"
                df.set_index('timestamp', inplace=True)
                bars = df['price'].resample('1min').ohlc()
                bars = bars.dropna()
                full_price_history.append(bars['close'])
            except:
                pass
                
    if not full_price_history:
        return pd.Series()
        
    macro_series = pd.concat(full_price_history)
    print(f"  Macro Series: {len(macro_series)} bars (1-min resolution)")
    return macro_series.values

def match_fractals():
    print("=" * 60)
    print("FRACTAL SEED MATCHING (TSUNAMI HYPOTHESIS)")
    print("=" * 60)
    
    # 1. Get Seeds (The "Micro")
    # Target 0xDF (The "Sell/Crash" signal) and 0x27 (The "Buy" Signal)
    seeds = extract_seeds(target_opcode=0xDF, window=500) # 500 ticks ~ 1-5 minutes of micro-action
    
    if not seeds:
        print("No seeds found.")
        return

    # 2. Get Ocean (The "Macro")
    macro_data = load_macro_data()
    norm_macro = normalize_series(macro_data)
    
    if len(macro_data) == 0:
        print("No macro data available.")
        return

    # 3. Sliding Window Search
    # We look for where the Seed Shape appears in the Macro Data
    # But "Scaled Up" and "Slowed Down".
    # DTW handles the "Slowed Down". "Scaled Up" handled by normalization.
    
    print("\nMatching Seeds to Future Price Action...")
    
    for seed in seeds[:3]: # Check first few seeds
        print(f"\nSeed: {seed['timestamp']} (0xDF)")
        best_score = float('inf')
        best_idx = -1
        best_window = []
        
        # Search window approach
        # Assume the seed predicts a move that takes approx same 'number of steps' 
        # but in macro bars (minutes) vs micro ticks.
        # Window size = len(seed) bars 
        
        window_size = len(seed['path']) 
        step = window_size // 5 # Step size
        
        for i in range(0, len(norm_macro) - window_size, step):
            macro_window = norm_macro[i : i+window_size]
            
            # Fast Check: Correlation
            corr = np.corrcoef(seed['norm_path'], macro_window)[0,1]
            
            # If correlation is high positive, check DTW
            if corr > 0.8:
                score = simple_dtw(seed['norm_path'], macro_window)
                if score < best_score:
                    best_score = score
                    best_idx = i
                    best_window = macro_window
                    
        if best_idx != -1:
            print(f"  BEST MATCH Found at Bar Index {best_idx}")
            print(f"  Similarity Score (DTW): {best_score:.4f}")
            print(f"  Correlation: {np.corrcoef(seed['norm_path'], best_window)[0,1]:.4f}")
            # In a real tool, we would plot this. 
            # Here we just report the strong match.
            
            if best_score < 5.0: # Arbitrary threshold for "Good Match"
                print("  >> SIGNIFICANT FRACTAL MATCH DETECTED <<")
        else:
            print("  No strong match found.")

if __name__ == "__main__":
    match_fractals()
