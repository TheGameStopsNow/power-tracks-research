"""
Phase 81: Precision Threshold Analysis

This script performs a high-resolution "Sweep" of IV thresholds to pinpoint the exact Tipping Point.
Focus: 65.0% to 75.0% range with 0.1% steps.
Asset: GME (valid bursts).
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from scipy import stats

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
GREEK_DIR = BASE_DIR / "research/phase77_greek_echo/output"
OUTPUT_DIR = BASE_DIR / "research/phase81_precision/output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def load_data():
    df = pd.read_csv(GREEK_DIR / "bursts_deep_explored.csv")
    valid = df.dropna(subset=['ret_60d']).copy()
    return valid

def precision_sweep(df, feature, start, end, step, target='ret_60d'):
    """
    High-resolution scan.
    """
    thresholds = np.arange(start, end + step, step)
    results = []
    
    for t in thresholds:
        group_above = df[df[feature] > t][target]
        group_below = df[df[feature] <= t][target]
        
        if len(group_above) < 5 or len(group_below) < 5:
            continue
            
        mean_above = group_above.mean()
        mean_below = group_below.mean()
        diff = mean_above - mean_below
        t_stat, p_val = stats.ttest_ind(group_above, group_below, equal_var=False)
        
        results.append({
            'threshold': t,
            'n_above': len(group_above),
            'mean_above': mean_above,
            'diff': diff,
            't_stat': abs(t_stat),
            'p_value': p_val
        })
        
    return pd.DataFrame(results)

def main():
    print("Phase 81: High Precision Threshold Sweep (GME)")
    print("=" * 60)
    
    df = load_data()
    print(f"Loaded {len(df)} bursts.")
    
    # Feature: IV (Implied Volatility)
    # Range: 0.60 to 0.80 (60% to 80%)
    print("\nScanning IV Thresholds (60% - 80%)...")
    res = precision_sweep(df, 'iv', 0.60, 0.80, 0.001) # 0.1% steps
    
    if len(res) == 0:
        print("No valid results.")
        return

    # Find Peak T-Stat
    best_t = res.loc[res['t_stat'].idxmax()]
    
    print(f"\nPEAK STATISTICAL SIGNIFICANCE:")
    print(f"Threshold: {best_t['threshold']:.4f} ({best_t['threshold']*100:.2f}%)")
    print(f"T-Stat:    {best_t['t_stat']:.4f}")
    print(f"P-Value:   {best_t['p_value']:.4e}")
    print(f"Alpha delta: {best_t['diff']:.2f}%")
    
    # Check 69.0% specifically
    # Find closest
    idx_69 = (res['threshold'] - 0.69).abs().idxmin()
    row_69 = res.loc[idx_69]
    print(f"\nAT 69.0%:")
    print(f"Threshold: {row_69['threshold']:.4f}")
    print(f"T-Stat:    {row_69['t_stat']:.4f}")
    
    # Plot
    plt.figure(figsize=(12, 6))
    
    # Plot T-Stat
    plt.subplot(1, 2, 1)
    plt.plot(res['threshold'], res['t_stat'], label='T-Statistic', color='blue')
    plt.axvline(best_t['threshold'], color='red', linestyle='--', label=f"Peak: {best_t['threshold']:.3f}")
    plt.axvline(0.69, color='green', linestyle=':', label="69% (Meme)")
    plt.title("Statistical Significance vs IV Threshold")
    plt.xlabel("IV Threshold")
    plt.ylabel("T-Statistic")
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    # Plot Mean Returns
    plt.subplot(1, 2, 2)
    plt.plot(res['threshold'], res['mean_above'], label='Return (Above)', color='purple')
    plt.axvline(best_t['threshold'], color='red', linestyle='--')
    plt.title("Avg Return if IV > Threshold")
    plt.xlabel("IV Threshold")
    plt.ylabel("60d Return (%)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "precision_sweep_iv.png")
    print(f"Saved plot: {OUTPUT_DIR / 'precision_sweep_iv.png'}")
    
    res.to_csv(OUTPUT_DIR / "precision_sweep_data.csv", index=False)

if __name__ == "__main__":
    main()
