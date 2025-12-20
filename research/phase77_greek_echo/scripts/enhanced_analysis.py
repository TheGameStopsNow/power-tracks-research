"""
Phase 77: Enhanced Greek Fingerprinting

This module adds:
1. Expiration bucketing (0DTE vs Weekly+)
2. Gamma sign analysis (+Γ vs -Γ)
3. Combined factor interactions
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from scipy import stats
import glob

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GREEK_DIR = BASE_DIR / "research/phase77_greek_echo/results"
BARS_DIR = BASE_DIR / "data/expanded_bars/GME"
OUTPUT_DIR = BASE_DIR / "research/phase77_greek_echo/results"

def load_opra_with_greeks():
    """Load individual trades with Greeks for expiration analysis."""
    df = pd.read_csv(GREEK_DIR / "opra_with_greeks.csv")
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed', utc=True)
    df['expiration'] = pd.to_datetime(df['expiration'], format='mixed', utc=True)
    
    # Compute days to expiry (DTE)
    df['dte'] = (df['expiration'] - df['timestamp']).dt.days
    
    # Classify expiration bucket
    df['exp_bucket'] = df['dte'].apply(lambda x: '0DTE' if x <= 0 else ('Weekly' if x <= 5 else 'Monthly+'))
    
    return df

def load_greek_flows():
    """Load aggregated Greek flows."""
    df = pd.read_csv(GREEK_DIR / "greek_flows_1s.csv")
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    return df

def load_minute_bars():
    """Load all minute bars for price evolution tracking."""
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

def identify_bursts_enhanced(flows_df, opra_df, gamma_threshold=200, min_gap_seconds=300):
    """
    Identify bursts with enhanced metadata including:
    - Gamma sign
    - Expiration bucket distribution
    """
    flows_df['is_burst'] = flows_df['gamma_flow'].abs() > gamma_threshold
    
    bursts = []
    last_burst_time = None
    
    for idx, row in flows_df[flows_df['is_burst']].iterrows():
        if last_burst_time is None or (row['timestamp'] - last_burst_time).total_seconds() > min_gap_seconds:
            
            # Get trades within ±5s of this burst
            window_start = row['timestamp'] - pd.Timedelta(seconds=5)
            window_end = row['timestamp'] + pd.Timedelta(seconds=5)
            
            window_trades = opra_df[(opra_df['timestamp'] >= window_start) & 
                                     (opra_df['timestamp'] <= window_end)]
            
            if len(window_trades) == 0:
                continue
            
            # Compute expiration distribution
            exp_dist = window_trades['exp_bucket'].value_counts(normalize=True)
            pct_0dte = exp_dist.get('0DTE', 0)
            pct_weekly = exp_dist.get('Weekly', 0)
            pct_monthly = exp_dist.get('Monthly+', 0)
            
            bursts.append({
                'timestamp': row['timestamp'],
                'delta_flow': row['delta_flow'],
                'gamma_flow': row['gamma_flow'],
                'charm_flow': row['charm_flow'],
                'pc_ratio': row['pc_ratio'],
                'underlying_price': row['underlying_price'],
                'iv': row['iv'],
                # Enhanced features
                'gamma_sign': np.sign(row['gamma_flow']),
                'pct_0dte': pct_0dte,
                'pct_weekly': pct_weekly,
                'pct_monthly': pct_monthly,
                'n_trades': len(window_trades)
            })
            last_burst_time = row['timestamp']
    
    return pd.DataFrame(bursts)

def track_price_evolution(burst_time, bars_df, horizons_days=[1, 5, 20, 60, 120]):
    """Track price evolution following a burst."""
    base_row = bars_df[bars_df['timestamp'] >= burst_time].head(1)
    if len(base_row) == 0:
        return None
    
    base_price = base_row['close'].iloc[0]
    base_idx = base_row.index[0]
    
    results = {'base_price': base_price, 'base_time': burst_time}
    
    for h in horizons_days:
        target_idx = base_idx + h * 390
        
        if target_idx < len(bars_df):
            future_price = bars_df.iloc[target_idx]['close']
            pct_return = (future_price - base_price) / base_price * 100
            results[f'ret_{h}d'] = pct_return
        else:
            results[f'ret_{h}d'] = np.nan
    
    return results

def main():
    print("Phase 77: Enhanced Greek Fingerprinting")
    print("=" * 60)
    
    # Load data
    opra_df = load_opra_with_greeks()
    flows_df = load_greek_flows()
    bars_df = load_minute_bars()
    
    print(f"Loaded {len(opra_df)} individual trades with Greeks")
    print(f"Loaded {len(flows_df)} 1-second Greek flow records")
    print(f"Loaded {len(bars_df)} minute bars")
    
    # Expiration distribution
    print(f"\nExpiration Distribution:")
    print(opra_df['exp_bucket'].value_counts())
    
    # Identify bursts with enhanced features
    bursts_df = identify_bursts_enhanced(flows_df, opra_df, gamma_threshold=200)
    print(f"\nIdentified {len(bursts_df)} enhanced bursts")
    
    if len(bursts_df) == 0:
        print("No bursts found.")
        return
    
    # Track evolution
    results = []
    for idx, burst in bursts_df.iterrows():
        evolution = track_price_evolution(burst['timestamp'], bars_df)
        if evolution:
            result = {**burst.to_dict(), **evolution}
            results.append(result)
    
    results_df = pd.DataFrame(results)
    print(f"Tracked {len(results_df)} bursts with evolution data")
    
    # ===== ANALYSIS =====
    print("\n" + "=" * 60)
    print("ENHANCED GREEK FINGERPRINT ANALYSIS")
    print("=" * 60)
    
    # 1. Gamma Sign Analysis
    print("\n--- GAMMA SIGN ANALYSIS ---")
    for horizon in [5, 20, 60]:
        ret_col = f'ret_{horizon}d'
        valid = results_df[[ret_col, 'gamma_sign']].dropna()
        
        pos_gamma = valid[valid['gamma_sign'] > 0][ret_col]
        neg_gamma = valid[valid['gamma_sign'] < 0][ret_col]
        
        if len(pos_gamma) > 1 and len(neg_gamma) > 1:
            t_stat, p_val = stats.ttest_ind(pos_gamma, neg_gamma)
            print(f"\n{horizon}d Returns by Gamma Sign:")
            print(f"  +Γ (Dealers Long Gamma): μ={pos_gamma.mean():.2f}% (n={len(pos_gamma)})")
            print(f"  -Γ (Dealers Short Gamma): μ={neg_gamma.mean():.2f}% (n={len(neg_gamma)})")
            print(f"  T-test: t={t_stat:.2f}, p={p_val:.2e}")
    
    # 2. Expiration Bucket Analysis
    print("\n--- EXPIRATION BUCKET ANALYSIS ---")
    for horizon in [5, 20, 60]:
        ret_col = f'ret_{horizon}d'
        valid = results_df[[ret_col, 'pct_0dte']].dropna()
        
        # Split by 0DTE dominance
        high_0dte = valid[valid['pct_0dte'] > 0.5][ret_col]  # >50% 0DTE
        low_0dte = valid[valid['pct_0dte'] < 0.2][ret_col]   # <20% 0DTE
        
        if len(high_0dte) > 1 and len(low_0dte) > 1:
            t_stat, p_val = stats.ttest_ind(high_0dte, low_0dte)
            print(f"\n{horizon}d Returns by 0DTE Dominance:")
            print(f"  High 0DTE (>50%): μ={high_0dte.mean():.2f}% (n={len(high_0dte)})")
            print(f"  Low 0DTE (<20%): μ={low_0dte.mean():.2f}% (n={len(low_0dte)})")
            print(f"  T-test: t={t_stat:.2f}, p={p_val:.2e}")
    
    # 3. Combined Factor Analysis: P/C + Gamma Sign
    print("\n--- COMBINED FACTOR: P/C × GAMMA SIGN ---")
    for horizon in [5, 20, 60]:
        ret_col = f'ret_{horizon}d'
        valid = results_df[[ret_col, 'pc_ratio', 'gamma_sign']].dropna()
        
        # High P/C + Negative Gamma (most bearish?)
        bear_combo = valid[(valid['pc_ratio'] > 2) & (valid['gamma_sign'] < 0)][ret_col]
        # Low P/C + Positive Gamma (most bullish?)
        bull_combo = valid[(valid['pc_ratio'] < 0.5) & (valid['gamma_sign'] > 0)][ret_col]
        
        if len(bear_combo) > 1 and len(bull_combo) > 1:
            t_stat, p_val = stats.ttest_ind(bear_combo, bull_combo)
            print(f"\n{horizon}d Returns by P/C × Gamma:")
            print(f"  Bearish (High P/C, -Γ): μ={bear_combo.mean():.2f}% (n={len(bear_combo)})")
            print(f"  Bullish (Low P/C, +Γ): μ={bull_combo.mean():.2f}% (n={len(bull_combo)})")
            print(f"  T-test: t={t_stat:.2f}, p={p_val:.2e}")
    
    # 4. Correlation Matrix
    print("\n--- CORRELATION MATRIX ---")
    corr_cols = ['gamma_flow', 'pc_ratio', 'pct_0dte', 'ret_5d', 'ret_20d', 'ret_60d']
    valid_corr = results_df[corr_cols].dropna()
    if len(valid_corr) > 10:
        corr_matrix = valid_corr.corr()
        print("\nCorrelation with 60d Returns:")
        print(corr_matrix['ret_60d'][:-1].sort_values())
    
    # Save results
    results_df.to_csv(OUTPUT_DIR / "burst_fingerprints_enhanced.csv", index=False)
    
    # Plot
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # P/C vs Returns
    valid = results_df[['pc_ratio', 'ret_20d']].dropna()
    if len(valid) > 3:
        axes[0, 0].scatter(valid['pc_ratio'], valid['ret_20d'], alpha=0.6, 
                           c=results_df.loc[valid.index, 'gamma_sign'], cmap='RdYlGn')
        axes[0, 0].axhline(0, color='k', linestyle='--')
        axes[0, 0].set_xlabel('P/C Ratio')
        axes[0, 0].set_ylabel('20d Return (%)')
        axes[0, 0].set_title('P/C Ratio vs 20d Return (color=Gamma Sign)')
    
    # 0DTE % vs Returns
    valid = results_df[['pct_0dte', 'ret_20d']].dropna()
    if len(valid) > 3:
        axes[0, 1].scatter(valid['pct_0dte']*100, valid['ret_20d'], alpha=0.6)
        axes[0, 1].axhline(0, color='k', linestyle='--')
        axes[0, 1].set_xlabel('% 0DTE Trades')
        axes[0, 1].set_ylabel('20d Return (%)')
        axes[0, 1].set_title('0DTE Concentration vs 20d Return')
    
    # Gamma sign box plot
    valid = results_df[['gamma_sign', 'ret_20d']].dropna()
    if len(valid) > 3:
        pos_g = valid[valid['gamma_sign'] > 0]['ret_20d']
        neg_g = valid[valid['gamma_sign'] < 0]['ret_20d']
        axes[1, 0].boxplot([pos_g, neg_g], labels=['+Γ (Dealers Long)', '-Γ (Dealers Short)'])
        axes[1, 0].axhline(0, color='k', linestyle='--')
        axes[1, 0].set_ylabel('20d Return (%)')
        axes[1, 0].set_title('Returns by Gamma Sign')
    
    # Combined factor
    valid = results_df[['pc_ratio', 'gamma_sign', 'ret_20d']].dropna()
    if len(valid) > 3:
        bear = valid[(valid['pc_ratio'] > 1.5) & (valid['gamma_sign'] < 0)]['ret_20d']
        bull = valid[(valid['pc_ratio'] < 1) & (valid['gamma_sign'] > 0)]['ret_20d']
        neutral = valid[~((valid['pc_ratio'] > 1.5) & (valid['gamma_sign'] < 0)) & 
                       ~((valid['pc_ratio'] < 1) & (valid['gamma_sign'] > 0))]['ret_20d']
        data = [d for d in [bear, neutral, bull] if len(d) > 0]
        labels = ['Bear', 'Neutral', 'Bull'][:len(data)]
        if data:
            axes[1, 1].boxplot(data, labels=labels)
            axes[1, 1].axhline(0, color='k', linestyle='--')
            axes[1, 1].set_ylabel('20d Return (%)')
            axes[1, 1].set_title('Returns by P/C × Gamma Combo')
    
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "enhanced_fingerprint_analysis.png", dpi=150)
    print(f"\nSaved: {OUTPUT_DIR / 'enhanced_fingerprint_analysis.png'}")
    print(f"Saved: {OUTPUT_DIR / 'burst_fingerprints_enhanced.csv'}")

if __name__ == "__main__":
    main()
