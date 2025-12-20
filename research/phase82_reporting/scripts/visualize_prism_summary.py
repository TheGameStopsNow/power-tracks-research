"""
Phase 82: Prism Mechanic Summary Visualization

Generates a publication-quality chart summarizing the two key laws of the Warped Prism:
1. The Loose Coupling (IV Threshold > 66.4%)
2. The Accelerant (Positive Charm > Negative Charm)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
# import seaborn as sns (Unavailable)
from pathlib import Path
from scipy import stats

BASE_DIR = Path(__file__).resolve().parent.parent.parent
INPUT_FILE = BASE_DIR / "research/phase77_greek_echo/results/burst_fingerprints_enhanced.csv"
OUTPUT_DIR = BASE_DIR / "research/phase82_reporting"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def main():
    # Load Data
    df = pd.read_csv(INPUT_FILE)
    valid = df.dropna(subset=['ret_60d']).copy()
    
    # Set Style
    plt.style.use('dark_background')
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))
    
    # --- Panel 1: The Loose Coupling (IV Threshold) ---
    # Bin IV into buckets
    valid['iv_bin'] = pd.cut(valid['iv'], bins=np.arange(0.3, 1.3, 0.1))
    iv_stats = valid.groupby('iv_bin')['ret_60d'].agg(['mean', 'count', 'sem']).reset_index()
    iv_stats['iv_mid'] = iv_stats['iv_bin'].apply(lambda x: x.mid)
    
    # Plot bars
    ax1 = axes[0]
    bars = ax1.bar(iv_stats['iv_mid'], iv_stats['mean'], width=0.08, color='skyblue', alpha=0.7, yerr=iv_stats['sem'])
    
    # Highlight the Threshold
    ax1.axvline(0.664, color='#ff0055', linestyle='--', linewidth=2, label='Critical Mass (66.4%)')
    
    # Add annotations
    ax1.text(0.68, 15, "LOOSE COUPLING\n(Volatility > 66%)", color='#ff0055', fontsize=12, fontweight='bold')
    ax1.text(0.40, -5, "Stiff Coupling\n(No Echo)", color='gray', fontsize=10)
    
    ax1.set_title("Law 1: The Loose Coupling (IV Threshold)", fontsize=14, pad=15)
    ax1.set_xlabel("Implied Volatility (IV)", fontsize=12)
    ax1.set_ylabel("60-Day Forward Return (%)", fontsize=12)
    ax1.grid(True, alpha=0.2)
    ax1.legend()
    
    # --- Panel 2: The Accelerant (Charm Regime) ---
    # Split by Charm Sign
    pos_charm = valid[valid['charm_flow'] > 0]['ret_60d']
    neg_charm = valid[valid['charm_flow'] < 0]['ret_60d']
    
    # Plot Distributions (KDE using Scipy)
    ax2 = axes[1]
    
    if len(pos_charm) > 1 and len(neg_charm) > 1:
        # Positive KDE
        kde_pos = stats.gaussian_kde(pos_charm)
        x_range = np.linspace(min(pos_charm.min(), neg_charm.min()), max(pos_charm.max(), neg_charm.max()), 100)
        ax2.plot(x_range, kde_pos(x_range), color='#00ff88', label=f'Positive Charm (Accelerant)\nMean: {pos_charm.mean():.1f}%', linewidth=2)
        ax2.fill_between(x_range, kde_pos(x_range), color='#00ff88', alpha=0.3)
        
        # Negative KDE
        kde_neg = stats.gaussian_kde(neg_charm)
        ax2.plot(x_range, kde_neg(x_range), color='#ffcc00', label=f'Negative Charm (Stabilizer)\nMean: {neg_charm.mean():.1f}%', linewidth=2)
        ax2.fill_between(x_range, kde_neg(x_range), color='#ffcc00', alpha=0.3)
        
        ax2.axvline(pos_charm.mean(), color='#00ff88', linestyle=':')
        ax2.axvline(neg_charm.mean(), color='#ffcc00', linestyle=':')
    else:
        print("Not enough data for KDE")
    
    ax2.set_title("Law 2: The Accelerant (Dealer Charm)", fontsize=14, pad=15)
    ax2.set_xlabel("60-Day Return Distribution", fontsize=12)
    ax2.set_ylabel("Density", fontsize=12)
    ax2.grid(True, alpha=0.2)
    ax2.legend(loc='upper right')
    
    # Final Polish
    plt.tight_layout()
    plt.suptitle("The Physics of the Warped Prism: Validated Mechanics", fontsize=18, y=1.05)
    
    # Save
    out_path = OUTPUT_DIR / "prism_mechanic_summary.png"
    plt.savefig(out_path, bbox_inches='tight', dpi=150)
    print(f"Saved chart to {out_path}")

if __name__ == "__main__":
    main()
