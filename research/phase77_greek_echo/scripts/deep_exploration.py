"""
Phase 77: Deep Exploration

Additional dimensions to explore:
1. Strike distance from ATM (ITM vs OTM dominance)
2. Time of day effects (morning vs afternoon bursts)
3. IV level conditioning (high vs low IV bursts)
4. Charm (delta decay) analysis
5. Burst sequencing (consecutive bursts)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from scipy import stats

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GREEK_DIR = BASE_DIR / "research/phase77_greek_echo/results"
OUTPUT_DIR = BASE_DIR / "research/phase77_greek_echo/results"

def load_data():
    trades = pd.read_csv(GREEK_DIR / "opra_with_greeks.csv")
    trades['timestamp'] = pd.to_datetime(trades['timestamp'], format='mixed', utc=True)
    
    bursts = pd.read_csv(GREEK_DIR / "burst_fingerprints_enhanced.csv")
    bursts['timestamp'] = pd.to_datetime(bursts['timestamp'], format='mixed', utc=True)
    
    return trades, bursts

def explore_strike_distance(trades, bursts):
    """Analyze ITM vs OTM dominance in bursts."""
    print("\n" + "="*60)
    print("1. STRIKE DISTANCE ANALYSIS (ITM vs OTM)")
    print("="*60)
    
    # Compute moneyness for each trade
    trades['moneyness'] = trades['strike'] / trades['underlying_price']
    
    # For calls: moneyness < 1 = ITM, > 1 = OTM
    # For puts: moneyness > 1 = ITM, < 1 = OTM
    trades['is_itm'] = ((trades['option_type'] == 'call') & (trades['moneyness'] < 0.95)) | \
                       ((trades['option_type'] == 'put') & (trades['moneyness'] > 1.05))
    
    trades['is_atm'] = (trades['moneyness'] >= 0.95) & (trades['moneyness'] <= 1.05)
    trades['is_otm'] = ~trades['is_itm'] & ~trades['is_atm']
    
    # Aggregate per burst
    for idx, burst in bursts.iterrows():
        window_start = burst['timestamp'] - pd.Timedelta(seconds=5)
        window_end = burst['timestamp'] + pd.Timedelta(seconds=5)
        
        window_trades = trades[(trades['timestamp'] >= window_start) & 
                               (trades['timestamp'] <= window_end)]
        
        if len(window_trades) > 0:
            bursts.loc[idx, 'pct_itm'] = window_trades['is_itm'].mean()
            bursts.loc[idx, 'pct_atm'] = window_trades['is_atm'].mean()
            bursts.loc[idx, 'pct_otm'] = window_trades['is_otm'].mean()
    
    # Test: OTM dominance effect
    valid = bursts[['pct_otm', 'ret_5d', 'ret_20d', 'ret_60d']].dropna()
    
    high_otm = valid[valid['pct_otm'] > 0.5]['ret_20d']
    low_otm = valid[valid['pct_otm'] < 0.3]['ret_20d']
    
    if len(high_otm) > 1 and len(low_otm) > 1:
        t_stat, p_val = stats.ttest_ind(high_otm, low_otm)
        print(f"\n20d Returns by OTM Dominance:")
        print(f"  High OTM (>50%): μ={high_otm.mean():.2f}% (n={len(high_otm)})")
        print(f"  Low OTM (<30%): μ={low_otm.mean():.2f}% (n={len(low_otm)})")
        print(f"  T-test: t={t_stat:.2f}, p={p_val:.2e}")
    
    return bursts

def explore_time_of_day(bursts):
    """Analyze morning vs afternoon burst effects."""
    print("\n" + "="*60)
    print("2. TIME OF DAY ANALYSIS")
    print("="*60)
    
    # Extract hour
    bursts['hour'] = bursts['timestamp'].dt.hour
    
    # Morning: 9:30-12:00 (hours 9-11)
    # Afternoon: 12:00-16:00 (hours 12-15)
    bursts['session'] = bursts['hour'].apply(
        lambda h: 'Morning' if h < 12 else ('Afternoon' if h < 16 else 'After-Hours')
    )
    
    for horizon in [5, 20, 60]:
        ret_col = f'ret_{horizon}d'
        valid = bursts[[ret_col, 'session']].dropna()
        
        morning = valid[valid['session'] == 'Morning'][ret_col]
        afternoon = valid[valid['session'] == 'Afternoon'][ret_col]
        
        if len(morning) > 3 and len(afternoon) > 3:
            t_stat, p_val = stats.ttest_ind(morning, afternoon)
            print(f"\n{horizon}d Returns by Session:")
            print(f"  Morning (9:30-12:00): μ={morning.mean():.2f}% (n={len(morning)})")
            print(f"  Afternoon (12:00-16:00): μ={afternoon.mean():.2f}% (n={len(afternoon)})")
            print(f"  T-test: t={t_stat:.2f}, p={p_val:.2e}")
    
    return bursts

def explore_iv_conditioning(bursts):
    """Analyze high IV vs low IV burst effects."""
    print("\n" + "="*60)
    print("3. IMPLIED VOLATILITY CONDITIONING")
    print("="*60)
    
    # Median split on IV
    median_iv = bursts['iv'].median()
    
    for horizon in [5, 20, 60]:
        ret_col = f'ret_{horizon}d'
        valid = bursts[[ret_col, 'iv']].dropna()
        
        high_iv = valid[valid['iv'] > median_iv][ret_col]
        low_iv = valid[valid['iv'] <= median_iv][ret_col]
        
        if len(high_iv) > 3 and len(low_iv) > 3:
            t_stat, p_val = stats.ttest_ind(high_iv, low_iv)
            print(f"\n{horizon}d Returns by IV (median={median_iv:.2f}):")
            print(f"  High IV: μ={high_iv.mean():.2f}% (n={len(high_iv)})")
            print(f"  Low IV: μ={low_iv.mean():.2f}% (n={len(low_iv)})")
            print(f"  T-test: t={t_stat:.2f}, p={p_val:.2e}")

def explore_charm(bursts):
    """Analyze charm (delta decay) effects."""
    print("\n" + "="*60)
    print("4. CHARM (DELTA DECAY) ANALYSIS")
    print("="*60)
    
    # Charm sign: positive = delta increasing, negative = delta decaying
    for horizon in [5, 20, 60]:
        ret_col = f'ret_{horizon}d'
        valid = bursts[[ret_col, 'charm_flow']].dropna()
        
        # Split by charm sign
        pos_charm = valid[valid['charm_flow'] > 0][ret_col]
        neg_charm = valid[valid['charm_flow'] < 0][ret_col]
        
        if len(pos_charm) > 3 and len(neg_charm) > 3:
            t_stat, p_val = stats.ttest_ind(pos_charm, neg_charm)
            print(f"\n{horizon}d Returns by Charm Sign:")
            print(f"  +Charm (delta increasing): μ={pos_charm.mean():.2f}% (n={len(pos_charm)})")
            print(f"  -Charm (delta decaying): μ={neg_charm.mean():.2f}% (n={len(neg_charm)})")
            print(f"  T-test: t={t_stat:.2f}, p={p_val:.2e}")
    
    # Correlation
    valid = bursts[['charm_flow', 'ret_60d']].dropna()
    if len(valid) > 10:
        corr = valid.corr().iloc[0, 1]
        print(f"\nCorr(charm_flow, 60d return): {corr:.3f}")

def explore_burst_sequencing(bursts):
    """Analyze patterns in consecutive bursts."""
    print("\n" + "="*60)
    print("5. BURST SEQUENCING ANALYSIS")
    print("="*60)
    
    # Sort by timestamp
    bursts_sorted = bursts.sort_values('timestamp').reset_index(drop=True)
    
    # Compute time to next burst
    bursts_sorted['time_to_next'] = bursts_sorted['timestamp'].shift(-1) - bursts_sorted['timestamp']
    bursts_sorted['hours_to_next'] = bursts_sorted['time_to_next'].dt.total_seconds() / 3600
    
    # Same-day follow-up bursts (within 4 hours)
    bursts_sorted['has_followup'] = bursts_sorted['hours_to_next'] < 4
    
    for horizon in [5, 20]:
        ret_col = f'ret_{horizon}d'
        valid = bursts_sorted[[ret_col, 'has_followup']].dropna()
        
        with_followup = valid[valid['has_followup']][ret_col]
        without_followup = valid[~valid['has_followup']][ret_col]
        
        if len(with_followup) > 3 and len(without_followup) > 3:
            t_stat, p_val = stats.ttest_ind(with_followup, without_followup)
            print(f"\n{horizon}d Returns by Follow-up Burst (<4h):")
            print(f"  With Follow-up: μ={with_followup.mean():.2f}% (n={len(with_followup)})")
            print(f"  Without Follow-up: μ={without_followup.mean():.2f}% (n={len(without_followup)})")
            print(f"  T-test: t={t_stat:.2f}, p={p_val:.2e}")
    
    return bursts_sorted

def create_summary_heatmap(bursts):
    """Create correlation heatmap of all features vs returns."""
    print("\n" + "="*60)
    print("6. FEATURE CORRELATION HEATMAP")
    print("="*60)
    
    features = ['gamma_flow', 'delta_flow', 'charm_flow', 'pc_ratio', 'iv', 
                'pct_0dte', 'ret_1d', 'ret_5d', 'ret_20d', 'ret_60d']
    
    valid_cols = [c for c in features if c in bursts.columns]
    valid = bursts[valid_cols].dropna()
    
    if len(valid) > 10:
        corr_matrix = valid.corr()
        
        plt.figure(figsize=(10, 8))
        im = plt.imshow(corr_matrix, cmap='RdBu_r', vmin=-1, vmax=1)
        plt.colorbar(im)
        plt.xticks(range(len(corr_matrix.columns)), corr_matrix.columns, rotation=45, ha='right')
        plt.yticks(range(len(corr_matrix.columns)), corr_matrix.columns)
        # Add values
        for i in range(len(corr_matrix.columns)):
            for j in range(len(corr_matrix.columns)):
                plt.text(j, i, f'{corr_matrix.iloc[i, j]:.2f}', ha='center', va='center', fontsize=8)
        plt.title('Feature Correlation Matrix')
        plt.tight_layout()
        plt.savefig(OUTPUT_DIR / "deep_exploration_heatmap.png", dpi=150)
        print(f"\nSaved: {OUTPUT_DIR / 'deep_exploration_heatmap.png'}")
        
        # Print strongest correlations with 60d return
        if 'ret_60d' in corr_matrix.columns:
            print("\nStrongest Correlations with 60d Return:")
            corrs = corr_matrix['ret_60d'].drop('ret_60d').sort_values(key=abs, ascending=False)
            for feat, corr in corrs.head(5).items():
                print(f"  {feat}: {corr:.3f}")

def main():
    print("Phase 77: Deep Exploration of Greek Fingerprints")
    print("=" * 60)
    
    trades, bursts = load_data()
    print(f"Loaded {len(trades)} trades, {len(bursts)} bursts")
    
    # Run all explorations
    bursts = explore_strike_distance(trades, bursts)
    bursts = explore_time_of_day(bursts)
    explore_iv_conditioning(bursts)
    explore_charm(bursts)
    bursts = explore_burst_sequencing(bursts)
    create_summary_heatmap(bursts)
    
    # Save enhanced dataset
    bursts.to_csv(OUTPUT_DIR / "bursts_deep_explored.csv", index=False)
    print(f"\nSaved: {OUTPUT_DIR / 'bursts_deep_explored.csv'}")
    
    # Final summary
    print("\n" + "="*60)
    print("DEEP EXPLORATION SUMMARY")
    print("="*60)
    print("""
Key dimensions analyzed:
1. Strike Distance (ITM/ATM/OTM)
2. Time of Day (Morning vs Afternoon)
3. IV Level (High vs Low)
4. Charm (Delta Decay)
5. Burst Sequencing (Follow-up bursts)

Check output for statistically significant relationships!
""")

if __name__ == "__main__":
    main()
