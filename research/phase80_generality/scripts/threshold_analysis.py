"""
Phase 80: Threshold Analysis (Pivot B)

This script performs a "Search for Criticality":
1. Iterates through potential thresholds for key features (0DTE %, IV).
2. Computes the separation (t-statistic) between groups above/below the threshold.
3. Identifies the "Tipping Point" where the signal becomes most potent.
4. Generates a Discontinuity Plot.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from scipy import stats

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
GREEK_DIR = BASE_DIR / "research/phase77_greek_echo/output"
OUTPUT_DIR = BASE_DIR / "research/phase80_generality/output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def load_data():
    df = pd.read_csv(GREEK_DIR / "bursts_deep_explored.csv")
    valid = df.dropna(subset=['ret_60d']).copy()
    return valid

def scan_thresholds(df, feature, target='ret_60d', steps=50):
    """
    Scan potential thresholds for a feature to find the best separation.
    """
    min_val = df[feature].quantile(0.05)
    max_val = df[feature].quantile(0.95)
    
    thresholds = np.linspace(min_val, max_val, steps)
    results = []
    
    for t in thresholds:
        group_above = df[df[feature] > t][target]
        group_below = df[df[feature] <= t][target]
        
        if len(group_above) < 10 or len(group_below) < 10:
            continue
            
        mean_diff = group_above.mean() - group_below.mean()
        t_stat, p_val = stats.ttest_ind(group_above, group_below)
        
        results.append({
            'threshold': t,
            'n_above': len(group_above),
            'mean_above': group_above.mean(),
            'mean_below': group_below.mean(),
            'diff': mean_diff,
            't_stat': abs(t_stat),
            'p_value': p_val
        })
        
    return pd.DataFrame(results)

def main():
    print("Phase 80: Threshold Analysis (Critical Mass Search)")
    print("=" * 60)
    
    df = load_data()
    print(f"Loaded {len(df)} valid bursts")
    
    features_to_test = ['pct_0dte', 'iv', 'pc_ratio', 'gamma_flow']
    
    best_breakpoints = {}
    
    plt.figure(figsize=(10, 6))
    
    for feat in features_to_test:
        print(f"\nScanning thresholds for {feat}...")
        results = scan_thresholds(df, feat)
        
        if len(results) == 0:
            print("  No valid thresholds found.")
            continue
            
        # Find max separation
        best = results.loc[results['t_stat'].idxmax()]
        best_breakpoints[feat] = best
        
        timestamp_for_label = feat
        
        print(f"  Critical Threshold: {best['threshold']:.4f}")
        print(f"  T-Stat: {best['t_stat']:.2f} (p={best['p_value']:.2e})")
        print(f"  Mean Above: {best['mean_above']:.2f}% | Below: {best['mean_below']:.2f}%")
        print(f"  Difference: {best['diff']:.2f}%")
        
        # Plot T-stat curve
        plt.plot(results['threshold'], results['t_stat'], label=f"{feat} (Max T={best['t_stat']:.1f})")
        
    plt.title("Search for Criticality: Threshold Strength")
    plt.xlabel("Threshold Value")
    plt.ylabel("Separation Strength (T-Statistic)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.savefig(OUTPUT_DIR / "threshold_search.png")
    print(f"\nSaved plot: {OUTPUT_DIR / 'threshold_search.png'}")
    
    # Save breakpoints
    bp_df = pd.DataFrame(best_breakpoints).T
    bp_df.to_csv(OUTPUT_DIR / "critical_breakpoints.csv")
    print(f"Saved breakpoints: {OUTPUT_DIR / 'critical_breakpoints.csv'}")

if __name__ == "__main__":
    main()
