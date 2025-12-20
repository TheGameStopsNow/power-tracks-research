"""
Phase 76: Multi-Template Echo Quantification

This script:
1. Extracts burst templates from 5 major GME events (2021-2024)
2. Tests echo detection across full 4-year history
3. Computes forward returns for each echo match
4. Quantifies predictive power and trading implications
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import glob
from scipy import stats
from datetime import timedelta

try:
    from dtaidistance import dtw
    dtw_distance = lambda a, b: dtw.distance(a.astype(np.float64), b.astype(np.float64))
except ImportError:
    print("dtaidistance not found, using fallback")
    def dtw_distance(a, b):
        return np.sqrt(np.sum((a - b[:len(a)])**2)) if len(a) <= len(b) else np.sqrt(np.sum((a[:len(b)] - b)**2))

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
BARS_DIR = BASE_DIR / "research/phase76_echo_quant/data/bars"
RESULTS_DIR = BASE_DIR / "research/phase76_echo_quant/output"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Define key GME events for template extraction
KEY_EVENTS = [
    {"name": "Jan 2021 Squeeze", "start": "2021-01-25", "end": "2021-01-29"},
    {"name": "Mar 2021 Run", "start": "2021-03-08", "end": "2021-03-12"},
    {"name": "Aug 2022 Split Run", "start": "2022-08-08", "end": "2022-08-12"},
    {"name": "Jan 2024 Dip", "start": "2024-01-11", "end": "2024-01-17"},
    {"name": "May 2024 Run", "start": "2024-05-13", "end": "2024-05-17"},
]

def load_all_bars():
    """Load all available bar data."""
    print("Loading all bar data...")
    bar_files = sorted(glob.glob(str(BARS_DIR / "GME_*_minute.csv")))
    
    all_bars = []
    for f in bar_files:
        df = pd.read_csv(f)
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        all_bars.append(df[['timestamp', 'close', 'volume']])
    
    df_all = pd.concat(all_bars, ignore_index=True)
    order = np.argsort(df_all['timestamp'].values)
    df_all = df_all.iloc[order].reset_index(drop=True)
    
    print(f"  Loaded {len(df_all)} bars from {len(bar_files)} files")
    print(f"  Date range: {df_all['timestamp'].min().date()} to {df_all['timestamp'].max().date()}")
    
    return df_all

def extract_event_template(bars_df, start_date, end_date, window_mins=60):
    """Extract normalized price shape from an event period."""
    event_bars = bars_df[(bars_df['timestamp'] >= start_date) & 
                         (bars_df['timestamp'] <= end_date)]
    
    if len(event_bars) < 20:
        return None
        
    # Find highest volatility moment
    event_bars = event_bars.copy()
    event_bars['ret'] = event_bars['close'].pct_change()
    event_bars['vol'] = event_bars['ret'].rolling(20).std()
    event_bars = event_bars.dropna()
    
    if len(event_bars) == 0:
        return None
        
    peak_idx = event_bars['vol'].idxmax()
    peak_time = event_bars.loc[peak_idx, 'timestamp']
    
    # Extract window
    start = peak_time - pd.Timedelta(minutes=window_mins//2)
    end = peak_time + pd.Timedelta(minutes=window_mins//2)
    
    window = bars_df[(bars_df['timestamp'] >= start) & (bars_df['timestamp'] <= end)]
    
    if len(window) < 20:
        return None
        
    prices = window['close'].values
    shape = (prices - prices.min()) / (prices.max() - prices.min() + 1e-9)
    
    return {
        'shape': shape,
        'peak_time': peak_time,
        'length': len(shape)
    }

def find_echoes_with_returns(template, bars_df, min_lag_days=30, max_matches=20):
    """Find echoes and compute forward returns for each."""
    tmpl_shape = template['shape']
    tmpl_time = template['peak_time']
    window_len = len(tmpl_shape)
    
    matches = []
    step = 30  # 30-minute step
    
    for j in range(0, len(bars_df) - window_len - 400, step):  # Leave room for forward returns
        chunk = bars_df.iloc[j:j+window_len]
        chunk_start = chunk['timestamp'].iloc[0]
        lag_days = (chunk_start - tmpl_time).days
        
        if abs(lag_days) < min_lag_days:
            continue
            
        prices = chunk['close'].values
        shape = (prices - prices.min()) / (prices.max() - prices.min() + 1e-9)
        
        dist = dtw_distance(tmpl_shape, shape)
        
        # Compute forward returns
        match_end_idx = j + window_len
        
        # Get future prices
        fwd_1d = match_end_idx + 390  # ~1 trading day
        fwd_5d = match_end_idx + 390*5
        fwd_20d = match_end_idx + 390*20
        
        base_price = chunk['close'].iloc[-1]
        
        ret_1d = None
        ret_5d = None
        ret_20d = None
        
        if fwd_1d < len(bars_df):
            ret_1d = (bars_df.iloc[fwd_1d]['close'] - base_price) / base_price * 100
        if fwd_5d < len(bars_df):
            ret_5d = (bars_df.iloc[fwd_5d]['close'] - base_price) / base_price * 100
        if fwd_20d < len(bars_df):
            ret_20d = (bars_df.iloc[fwd_20d]['close'] - base_price) / base_price * 100
            
        matches.append({
            'match_time': chunk_start,
            'lag_days': lag_days,
            'dtw_distance': dist,
            'ret_1d': ret_1d,
            'ret_5d': ret_5d,
            'ret_20d': ret_20d,
            'base_price': base_price
        })
    
    # Sort by distance and return top N
    matches = sorted(matches, key=lambda x: x['dtw_distance'])[:max_matches]
    return matches

def compute_baseline_returns(bars_df, n_samples=100):
    """Compute random entry baseline returns for comparison."""
    np.random.seed(42)
    baseline_1d = []
    baseline_5d = []
    baseline_20d = []
    
    valid_indices = range(390, len(bars_df) - 390*21)
    sample_indices = np.random.choice(valid_indices, min(n_samples, len(valid_indices)), replace=False)
    
    for idx in sample_indices:
        base_price = bars_df.iloc[idx]['close']
        
        fwd_1d = idx + 390
        fwd_5d = idx + 390*5
        fwd_20d = idx + 390*20
        
        if fwd_20d < len(bars_df):
            baseline_1d.append((bars_df.iloc[fwd_1d]['close'] - base_price) / base_price * 100)
            baseline_5d.append((bars_df.iloc[fwd_5d]['close'] - base_price) / base_price * 100)
            baseline_20d.append((bars_df.iloc[fwd_20d]['close'] - base_price) / base_price * 100)
    
    return {
        '1d': np.array(baseline_1d),
        '5d': np.array(baseline_5d),
        '20d': np.array(baseline_20d)
    }

def main():
    bars_df = load_all_bars()
    
    # Compute baseline
    print("\nComputing baseline returns...")
    baseline = compute_baseline_returns(bars_df, n_samples=200)
    print(f"  Baseline 1d: μ={baseline['1d'].mean():.2f}%, σ={baseline['1d'].std():.2f}%")
    print(f"  Baseline 5d: μ={baseline['5d'].mean():.2f}%, σ={baseline['5d'].std():.2f}%")
    print(f"  Baseline 20d: μ={baseline['20d'].mean():.2f}%, σ={baseline['20d'].std():.2f}%")
    
    all_matches = []
    
    for event in KEY_EVENTS:
        print(f"\n=== Processing: {event['name']} ===")
        
        template = extract_event_template(bars_df, event['start'], event['end'])
        
        if template is None:
            print(f"  Could not extract template for {event['name']}")
            continue
            
        print(f"  Template extracted: {template['length']} bars at {template['peak_time']}")
        
        matches = find_echoes_with_returns(template, bars_df, min_lag_days=30, max_matches=20)
        
        for m in matches:
            m['event_name'] = event['name']
        
        all_matches.extend(matches)
        
        if matches:
            best = matches[0]
            print(f"  Best match: {best['lag_days']:+d} days (DTW={best['dtw_distance']:.3f})")
            
    # Aggregate results
    df_matches = pd.DataFrame(all_matches)
    df_matches = df_matches.dropna(subset=['ret_1d', 'ret_5d', 'ret_20d'])
    
    print(f"\n{'='*60}")
    print("FORWARD RETURN ANALYSIS")
    print('='*60)
    
    echo_1d = df_matches['ret_1d'].values
    echo_5d = df_matches['ret_5d'].values
    echo_20d = df_matches['ret_20d'].values
    
    print(f"\nEcho Matches (n={len(df_matches)}):")
    print(f"  1d: μ={echo_1d.mean():.2f}%, σ={echo_1d.std():.2f}%")
    print(f"  5d: μ={echo_5d.mean():.2f}%, σ={echo_5d.std():.2f}%")
    print(f"  20d: μ={echo_20d.mean():.2f}%, σ={echo_20d.std():.2f}%")
    
    # T-tests
    print("\nSignificance Tests (Echo vs Baseline):")
    t_1d, p_1d = stats.ttest_ind(echo_1d, baseline['1d'])
    t_5d, p_5d = stats.ttest_ind(echo_5d, baseline['5d'])
    t_20d, p_20d = stats.ttest_ind(echo_20d, baseline['20d'])
    
    print(f"  1d: t={t_1d:.3f}, p={p_1d:.2e}")
    print(f"  5d: t={t_5d:.3f}, p={p_5d:.2e}")
    print(f"  20d: t={t_20d:.3f}, p={p_20d:.2e}")
    
    # Plot
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    for i, (horizon, echo_ret, base_ret, p_val) in enumerate([
        ('1d', echo_1d, baseline['1d'], p_1d),
        ('5d', echo_5d, baseline['5d'], p_5d),
        ('20d', echo_20d, baseline['20d'], p_20d)
    ]):
        ax = axes[i]
        ax.hist(base_ret, bins=20, alpha=0.5, label=f'Baseline (n={len(base_ret)})', density=True)
        ax.hist(echo_ret, bins=20, alpha=0.5, label=f'Echo (n={len(echo_ret)})', density=True)
        ax.axvline(base_ret.mean(), color='blue', linestyle='--')
        ax.axvline(echo_ret.mean(), color='orange', linestyle='--')
        ax.set_title(f'{horizon} Forward Returns (p={p_val:.2e})')
        ax.set_xlabel('Return (%)')
        ax.legend()
    
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "forward_returns_comparison.png", dpi=150)
    print(f"\nSaved: {RESULTS_DIR / 'forward_returns_comparison.png'}")
    
    # Save detailed results
    df_matches.to_csv(RESULTS_DIR / "echo_matches_with_returns.csv", index=False)
    print(f"Saved: {RESULTS_DIR / 'echo_matches_with_returns.csv'}")
    
    # Summary
    print("\n" + "="*60)
    print("PHASE 76 SUMMARY")
    print("="*60)
    
    sig_count = sum([p < 0.05 for p in [p_1d, p_5d, p_20d]])
    print(f"Significant Horizons: {sig_count}/3")
    
    if sig_count >= 1:
        print("\n*** ECHO PATTERN HAS PREDICTIVE POWER ***")
        if p_20d < 0.05:
            edge = echo_20d.mean() - baseline['20d'].mean()
            print(f"20-day Edge: {edge:+.2f}% vs baseline")
    else:
        print("\n*** NO SIGNIFICANT PREDICTIVE POWER DETECTED ***")

if __name__ == "__main__":
    main()
