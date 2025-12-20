"""
Phase 80: Verify Universality (Pivot E)

This script tests the "Prism Strategy" on NVDA bursts (Feb-Apr 2024).
Hypothesis: If the mechanic is universal, the Prism Model (High 0DTE + High IV) should generate Alpha on NVDA too.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
INPUT_FILE = BASE_DIR / "research/phase80_generality/output/nvda_bursts.csv" # or whatever the output of fingerprint is
# Actually checking fingerprint output filename... it usually saves as nvda_bursts.csv or similar.
# Let's assume standard naming based on previous file.
OUTPUT_DIR = BASE_DIR / "research/phase80_generality/output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def main():
    print("Phase 80: Generality Test (NVDA Prism Strategy)")
    print("="*60)
    
    file_path = INPUT_FILE
    if not file_path.exists():
        print("Burst fingerprints not found.")
        return
        
    df = pd.read_csv(file_path)
    print(f"Loaded {len(df)} NVDA bursts.")
    
    # Filter for valid T+20d returns
    valid = df.dropna(subset=['ret_20d']).copy()
    print(f"Valid bursts (T+20d): {len(valid)}")
    
    if len(valid) == 0: return

    # --- APPLY PRISM LOGIC ---
    # Parameters from Phase 78 (GME Model):
    # Score = 3*Z_0DTE + 1*Z_IV - 1.5*Z_Morning
    # Note: We re-standardize to NVDA's own distribution (Regime Relative).
    
    valid['hour'] = pd.to_datetime(valid['timestamp']).dt.hour
    
    valid['z_0dte'] = (valid['pct_0dte'] - valid['pct_0dte'].mean()) / (valid['pct_0dte'].std() + 1e-9)
    valid['z_iv'] = (valid['iv'] - valid['iv'].mean()) / (valid['iv'].std() + 1e-9)
    valid['z_morning'] = valid['hour'].apply(lambda x: 1 if x < 12 else 0)
    
    valid['prism_score'] = 3 * valid['z_0dte'] + 1 * valid['z_iv'] - 1.5 * valid['z_morning']
    
    # Strategy: Top 20%
    threshold = valid['prism_score'].quantile(0.80)
    valid['signal_prism'] = valid['prism_score'] > threshold
    
    # Performance
    benchmark_ret = valid['ret_20d'].mean()
    benchmark_win = (valid['ret_20d'] > 0).mean()
    
    strategy_trades = valid[valid['signal_prism']]
    strat_ret = strategy_trades['ret_20d'].mean()
    strat_win = (strategy_trades['ret_20d'] > 0).mean()
    
    alpha = strat_ret - benchmark_ret
    
    print("\nResults (T+20d):")
    print(f"Benchmark Return: {benchmark_ret:.2f}% (Win: {benchmark_win*100:.1f}%)")
    print(f"Prism Strategy:   {strat_ret:.2f}% (Win: {strat_win*100:.1f}%)")
    print(f"Alpha:            {alpha:.2f}%")
    
    if alpha > 2:
        print("\n✓ PASSED: Prism Model generates Alpha on NVDA.")
    else:
        print("\n✗ FAILED: No significant Alpha on NVDA.")
        
    # Plot
    plt.figure(figsize=(10, 6))
    valid = valid.sort_values('timestamp')
    valid['bmark_cum'] = valid['ret_20d'].cumsum()
    
    strat_cum = valid.copy()
    strat_cum.loc[~strat_cum['signal_prism'], 'ret_20d'] = 0
    strat_cum['strat_cum'] = strat_cum['ret_20d'].cumsum()
    
    plt.plot(valid['timestamp'], valid['bmark_cum'], label='Benchmark', color='gray')
    plt.plot(strat_cum['timestamp'], strat_cum['strat_cum'], label='Prism Strategy (NVDA)', color='green')
    
    plt.title("Generality Test: NVDA Prism Strategy")
    plt.ylabel("Cumulative Return (%)")
    plt.legend()
    plt.savefig(RESULTS_DIR / "nvda_generality_test.png")
    print(f"Saved plot: {RESULTS_DIR / 'nvda_generality_test.png'}")

if __name__ == "__main__":
    main()
