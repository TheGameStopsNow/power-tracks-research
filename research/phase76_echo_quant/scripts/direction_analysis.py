"""
Phase 76: Direction-Conditioned Echo Analysis

Key hypothesis: The template shape direction (bullish V vs bearish Λ) 
may predict the direction of the echo's follow-through, even if magnitude is random.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from scipy import stats

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RESULTS_DIR = BASE_DIR / "research/phase76_echo_quant/results"

def classify_shape_direction(shape):
    """Classify shape as bullish (ends higher) or bearish (ends lower)."""
    if len(shape) < 2:
        return 'neutral'
    
    mid_idx = len(shape) // 2
    first_half_mean = shape[:mid_idx].mean()
    second_half_mean = shape[mid_idx:].mean()
    
    if second_half_mean > first_half_mean + 0.1:
        return 'bullish'
    elif second_half_mean < first_half_mean - 0.1:
        return 'bearish'
    else:
        return 'neutral'

def main():
    # Load the matches with returns
    df = pd.read_csv(RESULTS_DIR / "echo_matches_with_returns.csv")
    print(f"Loaded {len(df)} echo matches with return data")
    
    # Classify direction
    df['ret_5d_dir'] = np.where(df['ret_5d'] > 0, 1, -1)
    df['ret_20d_dir'] = np.where(df['ret_20d'] > 0, 1, -1)
    
    # Event-wise analysis
    print("\n=== Direction Analysis by Event ===")
    
    for event_name in df['event_name'].unique():
        event_df = df[df['event_name'] == event_name].dropna(subset=['ret_5d'])
        
        if len(event_df) < 5:
            continue
            
        pos_5d = (event_df['ret_5d'] > 0).sum()
        total = len(event_df)
        pct = pos_5d / total * 100
        
        # Binomial test
        result = stats.binomtest(pos_5d, total, 0.5, alternative='two-sided')
        p_val = result.pvalue
        
        print(f"\n{event_name}:")
        print(f"  5d: {pos_5d}/{total} positive ({pct:.1f}%), p={p_val:.3f}")
        
        pos_20d = (event_df['ret_20d'] > 0).sum()
        total_20d = event_df['ret_20d'].dropna().shape[0]
        if total_20d > 0:
            pct_20d = pos_20d / total_20d * 100
            result_20d = stats.binomtest(pos_20d, total_20d, 0.5, alternative='two-sided')
            p_val_20d = result_20d.pvalue
            print(f"  20d: {pos_20d}/{total_20d} positive ({pct_20d:.1f}%), p={p_val_20d:.3f}")
    
    # Overall hit rate
    print("\n=== Overall Direction Hit Rate ===")
    
    df_clean = df.dropna(subset=['ret_5d', 'ret_20d'])
    
    pos_5d_all = (df_clean['ret_5d'] > 0).sum()
    total_all = len(df_clean)
    hit_5d = pos_5d_all / total_all * 100
    
    pos_20d_all = (df_clean['ret_20d'] > 0).sum()
    hit_20d = pos_20d_all / total_all * 100
    
    print(f"5d Hit Rate: {pos_5d_all}/{total_all} ({hit_5d:.1f}%)")
    print(f"20d Hit Rate: {pos_20d_all}/{total_all} ({hit_20d:.1f}%)")
    
    # Test if any event shows consistent direction
    print("\n=== Consistency Test ===")
    
    # Jan 2021 Squeeze echoes - do they predict bullish follow-through?
    squeeze_df = df[df['event_name'] == 'Jan 2021 Squeeze'].dropna(subset=['ret_20d'])
    if len(squeeze_df) > 5:
        mean_20d = squeeze_df['ret_20d'].mean()
        std_20d = squeeze_df['ret_20d'].std()
        t_stat, p_val = stats.ttest_1samp(squeeze_df['ret_20d'], 0)
        print(f"Jan 2021 Squeeze echoes 20d return: μ={mean_20d:.2f}%, t={t_stat:.2f}, p={p_val:.3f}")
    
    # Create summary plot
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    # 5d direction by event
    events = df['event_name'].unique()
    hit_rates_5d = []
    hit_rates_20d = []
    
    for e in events:
        edf = df[df['event_name'] == e].dropna(subset=['ret_5d'])
        if len(edf) > 3:
            hit_rates_5d.append((e, (edf['ret_5d'] > 0).mean() * 100))
        edf20 = df[df['event_name'] == e].dropna(subset=['ret_20d'])
        if len(edf20) > 3:
            hit_rates_20d.append((e, (edf20['ret_20d'] > 0).mean() * 100))
    
    if hit_rates_5d:
        events_plot = [x[0] for x in hit_rates_5d]
        rates_plot = [x[1] for x in hit_rates_5d]
        
        axes[0].barh(events_plot, rates_plot)
        axes[0].axvline(50, color='r', linestyle='--', label='Random (50%)')
        axes[0].set_xlabel('5d Positive Hit Rate (%)')
        axes[0].set_title('5-Day Hit Rate by Template Event')
        axes[0].legend()
        
    if hit_rates_20d:
        events_plot = [x[0] for x in hit_rates_20d]
        rates_plot = [x[1] for x in hit_rates_20d]
        
        axes[1].barh(events_plot, rates_plot)
        axes[1].axvline(50, color='r', linestyle='--', label='Random (50%)')
        axes[1].set_xlabel('20d Positive Hit Rate (%)')
        axes[1].set_title('20-Day Hit Rate by Template Event')
        axes[1].legend()
    
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "direction_analysis.png", dpi=150)
    print(f"\nSaved: {RESULTS_DIR / 'direction_analysis.png'}")
    
    # Final verdict
    print("\n" + "="*60)
    print("DIRECTION ANALYSIS VERDICT")
    print("="*60)
    
    # Check if any horizon is significantly different from 50%
    p_5d_overall = stats.binomtest(pos_5d_all, total_all, 0.5).pvalue
    p_20d_overall = stats.binomtest(pos_20d_all, total_all, 0.5).pvalue
    
    if p_5d_overall < 0.05 or p_20d_overall < 0.05:
        print("*** DIRECTION PREDICTION IS STATISTICALLY SIGNIFICANT ***")
    else:
        print("*** NO SIGNIFICANT DIRECTIONAL EDGE ***")
        print("Echoes exist but do not predict direction better than random.")

if __name__ == "__main__":
    main()
