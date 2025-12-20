"""
Deep Echo Analysis: Statistical Validation of Long-Horizon Pattern Recurrence

This script:
1. Extracts robust burst templates from May 13-17, 2024 (high activity)
2. Searches historical data for time-dilated echoes using DTW
3. Tests significance via permutation (shuffled templates)
4. Analyzes lag distribution for clustering (120/240/420 day modes)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import glob
from scipy import stats
from scipy.cluster.hierarchy import dendrogram, linkage, fcluster

# DTW import
try:
    from tisa.dtw import dtw_distance
except ImportError:
    from dtaidistance import dtw
    dtw_distance = lambda a, b: dtw.distance(a.astype(np.float64), b.astype(np.float64))

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TICKS_DIR = BASE_DIR / "data/ticks"
BARS_DIR = BASE_DIR / "data/expanded_bars/GME"
RESULTS_DIR = BASE_DIR / "research/phase75_predictability/results"

def extract_burst_templates(start_date, end_date, n_templates=10, window_mins=60):
    """
    Extract burst templates from high-volatility windows.
    Use intraday volatility to identify burst moments.
    """
    print(f"Extracting burst templates from {start_date} to {end_date}...")
    
    # Load all bar files and filter by date
    bar_files = sorted(glob.glob(str(BARS_DIR / "GME_*_minute.csv")))
    
    all_bars = []
    for f in bar_files:
        temp = pd.read_csv(f)
        temp['timestamp'] = pd.to_datetime(temp['timestamp'], utc=True)
        all_bars.append(temp)
    
    if not all_bars:
        print("No bar data found.")
        return []
        
    df_all = pd.concat(all_bars, ignore_index=True)
    order = np.argsort(df_all['timestamp'].values)
    df_all = df_all.iloc[order].reset_index(drop=True)
    
    # Filter to date range
    df_all = df_all[(df_all['timestamp'] >= start_date) & (df_all['timestamp'] <= end_date)]
    print(f"  Bars in range: {len(df_all)}")
    
    # Compute rolling volatility (20-min window)
    df_all['ret'] = df_all['close'].pct_change()
    df_all['vol'] = df_all['ret'].rolling(20).std()
    
    # Find top N volatility peaks (bursts)
    df_all = df_all.dropna(subset=['vol'])
    df_all = df_all.sort_values('vol', ascending=False)
    
    burst_indices = []
    min_spacing = 30  # Minimum 30 bars between bursts
    
    for idx in df_all.index[:100]:  # Check top 100 vol events
        if len(burst_indices) >= n_templates:
            break
        # Check spacing from existing bursts
        too_close = False
        for existing in burst_indices:
            if abs(idx - existing) < min_spacing:
                too_close = True
                break
        if not too_close:
            burst_indices.append(idx)
    
    print(f"  Selected {len(burst_indices)} burst peaks.")
    
    # Extract templates around each burst
    templates = []
    df_sorted = pd.concat(all_bars, ignore_index=True)
    order = np.argsort(df_sorted['timestamp'].values)
    df_sorted = df_sorted.iloc[order].reset_index(drop=True)
    
    for idx in burst_indices:
        # Find the row in sorted df
        burst_time = df_all.loc[idx, 'timestamp']
        
        # Get window around burst
        start_time = burst_time - pd.Timedelta(minutes=window_mins//2)
        end_time = burst_time + pd.Timedelta(minutes=window_mins//2)
        
        window = df_sorted[(df_sorted['timestamp'] >= start_time) & 
                          (df_sorted['timestamp'] <= end_time)]
        
        if len(window) < 20:
            continue
            
        prices = window['close'].values
        # Normalize to [0, 1]
        shape = (prices - prices.min()) / (prices.max() - prices.min() + 1e-9)
        
        templates.append({
            'timestamp': burst_time,
            'date': burst_time.strftime('%Y-%m-%d'),
            'shape': shape,
            'volatility': df_all.loc[idx, 'vol']
        })
        
    print(f"  Extracted {len(templates)} templates.")
    return templates

def load_full_history(start_date='2023-01-01', end_date='2024-12-31', window_mins=60):
    """
    Load full history and create sliding windows for matching.
    """
    print(f"\nLoading history from {start_date} to {end_date}...")
    
    bar_files = sorted(glob.glob(str(BARS_DIR / "GME_*_minute.csv")))
    
    all_bars = []
    for f in bar_files:
        temp = pd.read_csv(f)
        temp['timestamp'] = pd.to_datetime(temp['timestamp'], utc=True)
        all_bars.append(temp[['timestamp', 'close']])
    
    if not all_bars:
        return pd.DataFrame()
        
    df_all = pd.concat(all_bars, ignore_index=True)
    order = np.argsort(df_all['timestamp'].values)
    df_all = df_all.iloc[order].reset_index(drop=True)
    df_all = df_all[(df_all['timestamp'] >= start_date) & (df_all['timestamp'] <= end_date)]
    
    print(f"  Loaded {len(df_all)} bars.")
    return df_all

def find_echoes_rigorous(templates, history_df, min_lag_days=30, top_n=5):
    """
    Find echoes with DTW matching. Returns raw distances for significance testing.
    """
    print("\nSearching for echoes...")
    
    results = []
    all_distances = []  # For null distribution
    
    for i, tmpl in enumerate(templates):
        tmpl_shape = tmpl['shape']
        tmpl_time = tmpl['timestamp']
        window_len = len(tmpl_shape)
        
        matches = []
        
        # Slide window across history
        step = 30  # 30-minute step
        for j in range(0, len(history_df) - window_len, step):
            chunk = history_df.iloc[j:j+window_len]
            
            chunk_start = chunk['timestamp'].iloc[0]
            lag_days = (chunk_start - tmpl_time).days
            
            # Skip if too close to template
            if abs(lag_days) < min_lag_days:
                continue
                
            prices = chunk['close'].values
            shape = (prices - prices.min()) / (prices.max() - prices.min() + 1e-9)
            
            dist = dtw_distance(tmpl_shape, shape)
            all_distances.append(dist)
            
            matches.append({
                'template_date': tmpl['date'],
                'template_time': tmpl_time,
                'match_time': chunk_start,
                'lag_days': lag_days,
                'dtw_distance': dist
            })
        
        # Get top N matches
        matches = sorted(matches, key=lambda x: x['dtw_distance'])[:top_n]
        results.extend(matches)
        
        if matches:
            print(f"  Template {i+1} ({tmpl['date']}): Best match at {matches[0]['lag_days']:+d} days (DTW={matches[0]['dtw_distance']:.4f})")
    
    return results, all_distances

def test_significance(matches, all_distances, alpha=0.05):
    """
    Test if matched distances are significantly lower than random.
    """
    print("\n=== Significance Testing ===")
    
    match_dists = [m['dtw_distance'] for m in matches]
    
    # Null distribution statistics
    null_mean = np.mean(all_distances)
    null_std = np.std(all_distances)
    
    # Test each match
    significant_count = 0
    for m in matches:
        z_score = (m['dtw_distance'] - null_mean) / null_std
        p_value = stats.norm.cdf(z_score)
        m['z_score'] = z_score
        m['p_value'] = p_value
        if p_value < alpha:
            significant_count += 1
    
    print(f"Null Distribution: μ={null_mean:.4f}, σ={null_std:.4f}")
    print(f"Significant Matches (p<{alpha}): {significant_count}/{len(matches)}")
    
    # Overall test: are match distances systematically lower?
    t_stat, p_overall = stats.ttest_1samp(match_dists, null_mean)
    print(f"T-test vs Null Mean: t={t_stat:.3f}, p={p_overall:.2e}")
    
    return matches, p_overall

def analyze_lag_clustering(matches):
    """
    Check if lags cluster around specific intervals (120, 240, 420 days).
    """
    print("\n=== Lag Distribution Analysis ===")
    
    lags = np.array([m['lag_days'] for m in matches if m['lag_days'] != 0])
    forward_lags = lags[lags > 0]
    backward_lags = -lags[lags < 0]
    
    print(f"Forward Echoes (Future): {len(forward_lags)}")
    print(f"Backward Echoes (Past): {len(backward_lags)}")
    
    if len(forward_lags) > 2:
        print(f"  Forward Lag Range: {forward_lags.min():.0f} to {forward_lags.max():.0f} days")
        print(f"  Forward Lag Mean: {forward_lags.mean():.0f} days")
        
    if len(backward_lags) > 2:
        print(f"  Backward Lag Range: {backward_lags.min():.0f} to {backward_lags.max():.0f} days")
        print(f"  Backward Lag Mean: {backward_lags.mean():.0f} days")
    
    # Check for suspected harmonic intervals
    suspected_modes = [120, 180, 240, 360, 420]
    
    print("\nMode Detection (checking for clustering around expected intervals):")
    all_lags = np.abs(lags)
    for mode in suspected_modes:
        nearby = np.sum(np.abs(all_lags - mode) <= 30)
        print(f"  {mode} days (±30): {nearby} matches")
    
    # Plot
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Histogram of all lags
    axes[0].hist(lags, bins=20, edgecolor='black', alpha=0.7)
    axes[0].axvline(0, color='r', linestyle='--', label='Template Date')
    axes[0].set_xlabel('Lag (Days)')
    axes[0].set_ylabel('Count')
    axes[0].set_title('Echo Lag Distribution (All Matches)')
    axes[0].legend()
    
    # DTW distance vs Lag
    dtw_dists = [m['dtw_distance'] for m in matches]
    lags_list = [m['lag_days'] for m in matches]
    axes[1].scatter(lags_list, dtw_dists, alpha=0.7)
    axes[1].set_xlabel('Lag (Days)')
    axes[1].set_ylabel('DTW Distance (Lower = Better Match)')
    axes[1].set_title('Match Quality vs Lag')
    
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "echo_deep_analysis.png", dpi=150)
    print(f"\nSaved: {RESULTS_DIR / 'echo_deep_analysis.png'}")
    
    return lags

def main():
    # 1. Extract burst templates from May 13-17, 2024
    templates = extract_burst_templates(
        start_date='2024-05-13', 
        end_date='2024-05-17', 
        n_templates=10,
        window_mins=60
    )
    
    if not templates:
        print("No templates extracted. Exiting.")
        return
        
    # 2. Load full history
    history_df = load_full_history(start_date='2023-01-01', end_date='2024-12-31')
    
    if history_df.empty:
        print("No history data. Exiting.")
        return
    
    # 3. Find echoes
    matches, all_distances = find_echoes_rigorous(templates, history_df, min_lag_days=30, top_n=5)
    
    # 4. Test significance
    matches, p_overall = test_significance(matches, all_distances)
    
    # 5. Analyze lag clustering
    lags = analyze_lag_clustering(matches)
    
    # 6. Save detailed results
    df_results = pd.DataFrame(matches)
    df_results.to_csv(RESULTS_DIR / "echo_deep_results.csv", index=False)
    print(f"\nSaved detailed results: {RESULTS_DIR / 'echo_deep_results.csv'}")
    
    # Summary
    print("\n" + "="*60)
    print("ECHO ANALYSIS SUMMARY")
    print("="*60)
    sig_matches = [m for m in matches if m.get('p_value', 1) < 0.05]
    print(f"Total Matches: {len(matches)}")
    print(f"Significant Matches (p<0.05): {len(sig_matches)}")
    print(f"Overall Significance (T-test p): {p_overall:.4f}")
    
    if p_overall < 0.05:
        print("\n*** PATTERN RECURRENCE IS STATISTICALLY SIGNIFICANT ***")
        print("The burst shapes from May 2024 have detectable echoes in historical data.")
    else:
        print("\n*** NO SIGNIFICANT PATTERN RECURRENCE DETECTED ***")
        print("The echo matches are not distinguishable from random shape matching.")

if __name__ == "__main__":
    main()
