"""
Phase 81: Universal Threshold Precision Test

Hypothesis: If 66.4% IV is a mechanical "Tipping Point", it should appear in TSLA and AMD.
This script:
1. Loads `universe_burst_fingerprints.csv`.
2. Runs the RDD Sweep (Precision Sweep) on the aggregated data.
3. Checks if the Peak T-Stat aligns with GME's 66.4%.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from scipy import stats

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
INPUT_FILE = BASE_DIR / "research/phase81_precision/output/universe_burst_fingerprints.csv"
OUTPUT_DIR = BASE_DIR / "research/phase81_precision/output"

def main():
    print("Phase 81: Universal Threshold Test (TSLA + AMD)")
    print("="*60)
    
    if not INPUT_FILE.exists():
        print("Fingerprints not found.")
        return
        
    df = pd.read_csv(INPUT_FILE)
    print(f"Loaded {len(df)} universe bursts.")
    
    # Filter for valid returns
    valid = df.dropna(subset=['ret_2d']).copy()
    print(f"Valid bursts: {len(valid)}")
    
    if len(valid) == 0: return

    # Feature: IV
    # Scan 40% to 100% (TSLA/AMD might be different range than GME)
    start, end, step = 0.40, 1.00, 0.005 # 0.5% steps
    thresholds = np.arange(start, end + step, step)
    
    results = []
    
    for t in thresholds:
        above = valid[valid['iv'] > t]['ret_2d']
        below = valid[valid['iv'] <= t]['ret_2d']
        
        if len(above) < 5 or len(below) < 5: continue
        
        t_stat, p_val = stats.ttest_ind(above, below, equal_var=False)
        diff = above.mean() - below.mean()
        
        results.append({
            'threshold': t,
            'mean_above': above.mean(),
            't_stat': abs(t_stat),
            'p_value': p_val,
            'diff': diff,
            'n_above': len(above)
        })
        
    res_df = pd.DataFrame(results)
    
    if len(res_df) == 0:
        print("No valid results found.")
        return

    # Find Peaks
    peak = res_df.loc[res_df['t_stat'].idxmax()]
    
    print(f"\nGLOBAL UNIVERSE PEAK:")
    print(f"Threshold: {peak['threshold']:.4f} ({peak['threshold']*100:.2f}%)")
    print(f"T-Stat:    {peak['t_stat']:.4f}")
    print(f"Alpha:     {peak['diff']:.2f}%")
    
    # Check GME's 66.4%
    idx_gme = (res_df['threshold'] - 0.664).abs().idxmin()
    row_gme = res_df.loc[idx_gme]
    print(f"\nAT GME CRITICAL MASS (66.4%):")
    print(f"T-Stat:    {row_gme['t_stat']:.4f}")
    print(f"Alpha:     {row_gme['diff']:.2f}%")
    
    # Plot
    plt.figure(figsize=(10, 6))
    plt.plot(res_df['threshold'], res_df['t_stat'], label='T-Stat (Universe)')
    plt.axvline(peak['threshold'], color='red', linestyle='--', label=f"Peak {peak['threshold']:.2f}")
    plt.axvline(0.664, color='green', linestyle=':', label="GME Tip (0.664)")
    plt.title("Universal Threshold Search")
    plt.xlabel("IV")
    plt.ylabel("Significance (T-Stat)")
    plt.legend()
    plt.savefig(OUTPUT_DIR / "universal_threshold_sweep.png")
    print(f"Saved plot: {OUTPUT_DIR / 'universal_threshold_sweep.png'}")

if __name__ == "__main__":
    main()
