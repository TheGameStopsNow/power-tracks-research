#!/usr/bin/env python3
"""
Walk-Forward Validation Suite
=============================

Rigorously tests the "0xFC = Bullish" hypothesis on out-of-sample data.

Hypothesis:
    Events where opcode == 0xFC will have a higher 10s forward return 
    than the daily baseline (0x00/0xFF events).

Methodology:
    1. Select 5 random dates excluded from the training set (2024-09-05).
    2. For each date:
       - Extract signal and forward returns.
       - Calculate Mean Return(0xFC) and Mean Return(Baseline).
       - Calculate Alpha = Return(0xFC) - Return(Baseline).
    3. Aggregate results to determine global statistical significance.
"""

from pathlib import Path
from typing import Dict, List
import pandas as pd
import numpy as np
from scipy import stats
import json

# Import local modules
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
from core.extractors import extract_all_signals
from adversarial_decoding import bits_to_bytes
from price_correlation import calculate_future_returns
from semantic_mapper import map_opcodes_to_history

def test_hypothesis_on_date(sample_dir: Path) -> Dict:
    """
    Run the specific 0xFC hypothesis test on a single date.
    """
    print(f"Testing {sample_dir.name}...")
    
    # Load and Prep
    df = load_edgx_data(sample_dir)
    if df.empty or len(df) < 1000:
        return None
        
    df = calculate_future_returns(df, forward_windows=[10])
    events = map_opcodes_to_history(df)
    
    # Map returns back to events
    # (Simplified mapping via index logic from semantic_mapper)
    indices = [(k+1)*8 - 1 for k in range(len(events))]
    if len(indices) == 0:
        return None
        
    # Ensure indices are within bounds
    valid_indices = [i for i in indices if i < len(df)]
    if not valid_indices:
        return None
        
    returns = df.iloc[valid_indices]['fwd_return_10s'].values
    # Truncate events to match valid returns
    events = events.iloc[:len(returns)].copy()
    events['ret_10s'] = returns
    events = events.dropna()
    
    # Hypothesis Groups
    group_signal = events[events['opcode'] == 0xFC]['ret_10s']
    group_baseline = events[events['opcode'].isin([0x00, 0xFF])]['ret_10s']
    
    n_signal = len(group_signal)
    n_baseline = len(group_baseline)
    
    if n_signal < 5 or n_baseline < 50:
        print(f"  Skipping: Insufficient data (Signal n={n_signal})")
        return None
        
    mean_signal = group_signal.mean()
    mean_baseline = group_baseline.mean()
    alpha_bps = (mean_signal - mean_baseline) * 10000
    
    # Mann-Whitney U Test (Non-parametric is safer for returns)
    u_stat, p_val = stats.mannwhitneyu(group_signal, group_baseline, alternative='greater')
    
    return {
        'date': sample_dir.name.replace('sample_', ''),
        'n_signal': int(n_signal),
        'mean_signal': float(mean_signal),
        'mean_baseline': float(mean_baseline),
        'alpha_bps': float(alpha_bps),
        'p_value': float(p_val),
        'win': bool(alpha_bps > 0)
    }

import matplotlib.pyplot as plt

def run_walk_forward_validation():
    print("=" * 60)
    print("WALK-FORWARD VALIDATION: 0xFC HYPOTHESIS (FULL HISTORY)")
    print("=" * 60)
    
    all_dates = get_sample_dirs()
    
    # Exclude training date (2024-09-05) to maintain strict out-of-sample integrity
    test_dates = [d for d in all_dates if "2024-09-05" not in d.name]
    
    print(f"Running validation on {len(test_dates)} historical dates...")
            
    results = []
    
    for d in test_dates:
        try:
            res = test_hypothesis_on_date(d)
            if res:
                results.append(res)
                print(f"  Date: {res['date']:<12} | Alpha: {res['alpha_bps']:+6.2f} bps | n={res['n_signal']:<3} | p={res['p_value']:.4f}")
        except Exception as e:
            print(f"  Error on {d.name}: {e}")

    if not results:
        print("No valid results generated.")
        return

    # Aggregate Analysis
    print("-" * 60)
    wins = sum(1 for r in results if r['win'])
    total = len(results)
    alphas = [r['alpha_bps'] for r in results]
    avg_alpha = np.mean(alphas)
    
    # Fisher's Method for combining P-values
    p_values = [r['p_value'] for r in results]
    chi2_val = -2 * np.sum(np.log(p_values))
    combined_p = stats.chi2.sf(chi2_val, 2 * len(p_values))
    
    print(f"AGGREGATE RESULTS ({total} Days)")
    print(f"Win Rate:       {wins}/{total} ({wins/total*100:.1f}%)")
    print(f"Average Alpha:  {avg_alpha:+.2f} bps")
    print(f"Total Alpha:    {sum(alphas):+.2f} bps")
    print(f"Combined P-Val: {combined_p:.6f}")
    
    # === Visualization ===
    results.sort(key=lambda x: x['date'])
    dates = [r['date'] for r in results]
    cum_alpha = np.cumsum([r['alpha_bps'] for r in results])
    
    plt.figure(figsize=(12, 6))
    plt.plot(dates, cum_alpha, marker='o', linestyle='-', linewidth=2)
    plt.axhline(0, color='r', linestyle='--', alpha=0.5)
    plt.title(f"Cumulative Alpha of 0xFC Signal (Out-of-Sample)\n{total} Days | Win Rate: {wins/total*100:.1f}% | Avg Alpha: {avg_alpha:.2f} bps")
    plt.ylabel("Cumulative Alpha (Basis Points)")
    plt.xticks(rotation=45)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    out_img = BASE_DIR / "research" / "edgx_deep_decode" / "results" / "cumulative_alpha.png"
    plt.savefig(out_img)
    print(f"Saved visualization to {out_img}")

    # Save Results JSON
    out_path = BASE_DIR / "research" / "edgx_deep_decode" / "results" / "walk_forward_full_history.json"
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    run_walk_forward_validation()
