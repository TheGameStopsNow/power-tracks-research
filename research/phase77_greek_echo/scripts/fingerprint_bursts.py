"""
Phase 77: Burst Fingerprinting

This module:
1. Identifies high-activity "bursts" in the Greek flow data
2. Computes a fingerprint for each burst (Greek signature)
3. Links to subsequent price evolution to test predictive power
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from scipy import stats
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
INPUT_FILE = BASE_DIR / "research/phase77_greek_echo/output/greek_flows_1s.csv"
BARS_DIR = BASE_DIR / "data/expanded_bars/GME"
OUTPUT_DIR = BASE_DIR / "research/phase77_greek_echo/output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def load_greek_flows():
    """Load aggregated Greek flows."""
    df = pd.read_csv(INPUT_FILE)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    return df

def load_minute_bars():
    """Load all minute bars for price evolution tracking."""
    import glob
    
    bar_files = sorted(glob.glob(str(BARS_DIR / "GME_*_minute.csv")))
    all_bars = []
    
    for f in bar_files:
        temp = pd.read_csv(f)
        temp['timestamp'] = pd.to_datetime(temp['timestamp'], utc=True)
        all_bars.append(temp[['timestamp', 'close', 'volume']])
    
    df = pd.concat(all_bars, ignore_index=True)
    order = np.argsort(df['timestamp'].values)
    df = df.iloc[order].reset_index(drop=True)
    
    return df

def identify_bursts(flows_df, gamma_threshold=500, min_gap_seconds=300):
    """
    Identify bursts as periods with high gamma flow.
    A burst is defined as a second with |gamma_flow| > threshold.
    """
    flows_df['is_burst'] = flows_df['gamma_flow'].abs() > gamma_threshold
    
    bursts = []
    last_burst_time = None
    
    for idx, row in flows_df[flows_df['is_burst']].iterrows():
        if last_burst_time is None or (row['timestamp'] - last_burst_time).total_seconds() > min_gap_seconds:
            bursts.append({
                'timestamp': row['timestamp'],
                'delta_flow': row['delta_flow'],
                'gamma_flow': row['gamma_flow'],
                'charm_flow': row['charm_flow'],
                'pc_ratio': row['pc_ratio'],
                'underlying_price': row['underlying_price'],
                'iv': row['iv']
            })
            last_burst_time = row['timestamp']
    
    return pd.DataFrame(bursts)

def compute_fingerprint(burst):
    """
    Compute a fingerprint vector for a burst.
    """
    return {
        'gamma_sign': np.sign(burst['gamma_flow']),
        'delta_sign': np.sign(burst['delta_flow']),
        'gamma_magnitude': np.abs(burst['gamma_flow']),
        'delta_magnitude': np.abs(burst['delta_flow']),
        'pc_ratio': burst['pc_ratio'],
        'iv': burst['iv']
    }

def track_price_evolution(burst_time, bars_df, horizons_days=[1, 5, 20, 60, 120]):
    """
    Track price evolution following a burst.
    """
    base_row = bars_df[bars_df['timestamp'] >= burst_time].head(1)
    if len(base_row) == 0:
        return None
    
    base_price = base_row['close'].iloc[0]
    base_idx = base_row.index[0]
    
    results = {'base_price': base_price, 'base_time': burst_time}
    
    for h in horizons_days:
        # Approximate bar index (assume ~390 bars/day for regular hours)
        target_idx = base_idx + h * 390
        
        if target_idx < len(bars_df):
            future_price = bars_df.iloc[target_idx]['close']
            pct_return = (future_price - base_price) / base_price * 100
            results[f'ret_{h}d'] = pct_return
            results[f'dir_{h}d'] = 1 if pct_return > 0 else -1
        else:
            results[f'ret_{h}d'] = np.nan
            results[f'dir_{h}d'] = np.nan
    
    return results

def main():
    print("Phase 77: Burst Fingerprinting & Price Evolution")
    print("=" * 60)
    
    # Load data
    flows_df = load_greek_flows()
    bars_df = load_minute_bars()
    
    print(f"Loaded {len(flows_df)} 1-second Greek flow records")
    print(f"Loaded {len(bars_df)} minute bars")
    
    # Identify bursts
    bursts_df = identify_bursts(flows_df, gamma_threshold=200)
    print(f"\nIdentified {len(bursts_df)} bursts (γ > 200)")
    
    if len(bursts_df) == 0:
        print("No bursts found. Try lowering threshold.")
        return
    
    # Compute fingerprints and track evolution
    results = []
    
    for idx, burst in bursts_df.iterrows():
        fingerprint = compute_fingerprint(burst)
        evolution = track_price_evolution(burst['timestamp'], bars_df)
        
        if evolution:
            result = {**burst.to_dict(), **fingerprint, **evolution}
            results.append(result)
    
    results_df = pd.DataFrame(results)
    print(f"Tracked {len(results_df)} bursts with evolution data")
    
    # Analyze relationships
    print("\n" + "=" * 60)
    print("GREEK FINGERPRINT → PRICE EVOLUTION ANALYSIS")
    print("=" * 60)
    
    # Test: Gamma sign predicts direction?
    for horizon in [1, 5, 20, 60]:
        ret_col = f'ret_{horizon}d'
        dir_col = f'dir_{horizon}d'
        
        if ret_col not in results_df.columns:
            continue
            
        valid = results_df[[ret_col, 'gamma_sign', 'pc_ratio']].dropna()
        
        if len(valid) < 5:
            continue
        
        # Split by gamma sign
        pos_gamma = valid[valid['gamma_sign'] > 0][ret_col]
        neg_gamma = valid[valid['gamma_sign'] < 0][ret_col]
        
        if len(pos_gamma) > 1 and len(neg_gamma) > 1:
            t_stat, p_val = stats.ttest_ind(pos_gamma, neg_gamma)
            print(f"\nGamma Sign → {horizon}d Returns:")
            print(f"  +Γ bursts: μ={pos_gamma.mean():.2f}% (n={len(pos_gamma)})")
            print(f"  -Γ bursts: μ={neg_gamma.mean():.2f}% (n={len(neg_gamma)})")
            print(f"  T-test: t={t_stat:.2f}, p={p_val:.2e}")
        
        # Split by P/C ratio
        high_pc = valid[valid['pc_ratio'] > 2][ret_col]
        low_pc = valid[valid['pc_ratio'] < 0.5][ret_col]
        
        if len(high_pc) > 1 and len(low_pc) > 1:
            t_stat2, p_val2 = stats.ttest_ind(high_pc, low_pc)
            print(f"\nP/C Ratio → {horizon}d Returns:")
            print(f"  High P/C (>2): μ={high_pc.mean():.2f}% (n={len(high_pc)})")
            print(f"  Low P/C (<0.5): μ={low_pc.mean():.2f}% (n={len(low_pc)})")
            print(f"  T-test: t={t_stat2:.2f}, p={p_val2:.2e}")
    
    # Correlation analysis
    print("\n" + "=" * 60)
    print("CORRELATION: Fingerprint Features vs Returns")
    print("=" * 60)
    
    for horizon in [5, 20, 60]:
        ret_col = f'ret_{horizon}d'
        if ret_col not in results_df.columns:
            continue
            
        valid = results_df[['gamma_magnitude', 'pc_ratio', ret_col]].dropna()
        
        if len(valid) > 5:
            corr_gamma = valid[['gamma_magnitude', ret_col]].corr().iloc[0, 1]
            corr_pc = valid[['pc_ratio', ret_col]].corr().iloc[0, 1]
            print(f"\n{horizon}d Returns:")
            print(f"  Corr(|Γ|, ret): {corr_gamma:.3f}")
            print(f"  Corr(P/C, ret): {corr_pc:.3f}")
    
    # Save results
    results_df.to_csv(OUTPUT_DIR / "burst_fingerprints.csv", index=False)
    print(f"\nSaved: {OUTPUT_DIR / 'burst_fingerprints.csv'}")
    
    # Plot
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    
    # Gamma vs returns
    valid = results_df[['gamma_flow', 'ret_20d']].dropna()
    if len(valid) > 3:
        axes[0, 0].scatter(valid['gamma_flow'], valid['ret_20d'], alpha=0.6)
        axes[0, 0].axhline(0, color='k', linestyle='--')
        axes[0, 0].axvline(0, color='k', linestyle='--')
        axes[0, 0].set_xlabel('Gamma Flow')
        axes[0, 0].set_ylabel('20d Return (%)')
        axes[0, 0].set_title('Gamma Flow vs 20d Return')
    
    # P/C ratio vs returns
    valid = results_df[['pc_ratio', 'ret_20d']].dropna()
    if len(valid) > 3:
        axes[0, 1].scatter(valid['pc_ratio'], valid['ret_20d'], alpha=0.6)
        axes[0, 1].axhline(0, color='k', linestyle='--')
        axes[0, 1].set_xlabel('P/C Ratio')
        axes[0, 1].set_ylabel('20d Return (%)')
        axes[0, 1].set_title('P/C Ratio vs 20d Return')
    
    # Gamma sign distribution
    if 'gamma_sign' in results_df.columns:
        pos = (results_df['gamma_sign'] > 0).sum()
        neg = (results_df['gamma_sign'] < 0).sum()
        axes[1, 0].bar(['+Γ', '-Γ'], [pos, neg])
        axes[1, 0].set_title('Gamma Sign Distribution')
    
    # Return distribution by horizon
    horizons = [5, 20, 60]
    means = []
    for h in horizons:
        col = f'ret_{h}d'
        if col in results_df.columns:
            means.append(results_df[col].dropna().mean())
        else:
            means.append(0)
    axes[1, 1].bar([f'{h}d' for h in horizons], means)
    axes[1, 1].axhline(0, color='k', linestyle='--')
    axes[1, 1].set_title('Mean Return by Horizon')
    
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "greek_fingerprint_analysis.png", dpi=150)
    print(f"Saved: {OUTPUT_DIR / 'greek_fingerprint_analysis.png'}")

if __name__ == "__main__":
    main()
