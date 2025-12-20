"""
Phase 80: Regime Analysis (Pivot C)

This script tests the "Dealer Gamma" Hypothesis:
- Dealer Short Gamma (-GEX): Price is unstable, volatility expands.
- Dealer Long Gamma (+GEX): Price is pinned, volatility is suppressed.

Method:
1. Infers Dealer Gamma orientation from burst flow.
   - Flow > 0 (Retail Buy Call) -> Dealer Short Gamma.
   - Flow < 0 (Retail Sell Call) -> Dealer Long Gamma.
2. Compares realized volatility (absolute return) over T+5 and T+20 days for each regime.
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
    valid = df.dropna(subset=['ret_20d']).copy()
    return valid

def analyze_regimes(df):
    """
    Split by Gamma Flow Direction.
    Assumption: 'gamma_flow' is the *Aggressor's* Gamma.
    Dealer Gamma = -1 * Aggressor Gamma.
    """
    
    # Dealer Gamma Sign was all Short (Positive User Gamma).
    # Pivot to CHARM REGIME.
    # Charm = dDelta / dTime.
    # +Charm: Delta increases as time passes (accelerant).
    # -Charm: Delta decreases as time passes (decay/stabilizer).
    
    pos_charm = df[df['charm_flow'] > 0].copy()
    neg_charm = df[df['charm_flow'] < 0].copy()
    
    # Metric: Absolute Return (Volatility Proxy)
    pos_vol = pos_charm['ret_20d'].abs()
    neg_vol = neg_charm['ret_20d'].abs()
    
    print("\nRegime Volatility Analysis (Charm Sign T+20d Abs Return):")
    print(f"Positive Charm (+): n={len(pos_charm)}, Mean Vol={pos_vol.mean():.2f}%")
    print(f"Negative Charm (-): n={len(neg_charm)}, Mean Vol={neg_vol.mean():.2f}%")
    
    # Test significance
    t_stat, p_val = stats.ttest_ind(pos_vol, neg_vol, equal_var=False)
    print(f"Difference T-Stat: {t_stat:.2f} (p={p_val:.4f})")
    
    if p_val < 0.05:
        dir_str = "Positive" if pos_vol.mean() > neg_vol.mean() else "Negative"
        print(f"✓ SIGNIFICANT: {dir_str} Charm regime has higher volatility.")
    else:
        print("✗ NO SIGNIFICANT DIFFERENCE.")
        
    return pos_charm, neg_charm

def plot_regimes(pos_c, neg_c):
    plt.figure(figsize=(10, 6))
    
    # Boxplot of Abs Returns
    data = [pos_c['ret_20d'].abs(), neg_c['ret_20d'].abs()]
    plt.boxplot(data, tick_labels=['Positive Charm\n(Accelerant)', 'Negative Charm\n(Decay)'])
    
    plt.ylabel('Absolute 20d Return (%)')
    plt.title('Volatility Regime Test: Charm Sign')
    plt.grid(axis='y', alpha=0.3)
    
    plt.savefig(OUTPUT_DIR / "regime_charm.png")
    print(f"\nSaved plot: {OUTPUT_DIR / 'regime_charm.png'}")

def main():
    print("Phase 80: Regime Analysis (Dealer Gamma)")
    print("="*60)
    
    df = load_data()
    print(f"Loaded {len(df)} bursts")
    
    short, long_g = analyze_regimes(df)
    plot_regimes(short, long_g)

if __name__ == "__main__":
    main()
