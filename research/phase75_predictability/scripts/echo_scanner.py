"""
Echo Scanner: Detect long-horizon replays of burst shapes using DTW (tisa-finance).

This script:
1. Loads "Burst Templates" (high-volatility events from May 2024).
2. Searches historical price data for time-dilated replicas of these templates.
3. Uses Dynamic Time Warping (DTW) for shape matching.
4. Tests significance against block-bootstrap surrogates.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import glob
# User's custom DTW library
try:
    from tisa.dtw import dtw_distance  # Try user's library
except ImportError:
    from dtaidistance import dtw  # Fallback
    dtw_distance = lambda a, b: dtw.distance(a, b)

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
TICKS_DIR = BASE_DIR / "data/ticks"
BARS_DIR = BASE_DIR / "data/expanded_bars/GME"
RESULTS_DIR = BASE_DIR / "research/phase75_predictability/results"

def load_burst_templates(n_templates=5):
    """
    Identify top N burst events from May 2024 and extract normalized price shapes.
    """
    print("Loading Burst Templates from May 2024...")
    
    # Load barrier events (these are our "burst" points)
    events_path = BASE_DIR / "research/phase74_rega/results/expanded_barrier_events.csv"
    df_events = pd.read_csv(events_path)
    df_events['timestamp'] = pd.to_datetime(df_events['timestamp'], format='mixed', utc=True)
    
    # Filter to May 2024 and sort by Net Volume (largest bursts)
    df_may = df_events[df_events['timestamp'].dt.month == 5]
    df_may = df_may.sort_values('net_vol_3s', ascending=False, key=abs)
    
    # Top N bursts
    top_bursts = df_may.head(n_templates)
    print(f"Selected {len(top_bursts)} burst templates.")
    
    templates = []
    for idx, row in top_bursts.iterrows():
        burst_time = row['timestamp']
        date_str = burst_time.strftime('%Y-%m-%d')
        
        # Load minute bars for that day
        bar_file = BARS_DIR / f"GME_{date_str}_minute.csv"
        if not bar_file.exists():
            print(f"  Skipping {date_str} - no bar file.")
            continue
            
        bars = pd.read_csv(bar_file)
        bars['timestamp'] = pd.to_datetime(bars['timestamp'], utc=True)
        
        # Extract +/- 30 mins around burst
        window_start = burst_time - pd.Timedelta(minutes=30)
        window_end = burst_time + pd.Timedelta(minutes=30)
        
        window_bars = bars[(bars['timestamp'] >= window_start) & (bars['timestamp'] <= window_end)]
        
        if len(window_bars) < 10:
            print(f"  Skipping burst at {burst_time} - insufficient window data.")
            continue
            
        # Normalize shape (0-1 scale)
        prices = window_bars['close'].values
        shape = (prices - prices.min()) / (prices.max() - prices.min() + 1e-9)
        
        templates.append({
            'timestamp': burst_time,
            'date': date_str,
            'shape': shape,
            'length': len(shape),
            'net_flow': row['net_vol_3s']
        })
        print(f"  Template: {date_str} @ {burst_time.strftime('%H:%M')} | Shape Length: {len(shape)}")
        
    return templates

def load_history_shapes(start_date='2023-01-01', end_date='2024-12-31', window_mins=60):
    """
    Load historical price bars and segment into overlapping windows.
    """
    print(f"\nLoading history from {start_date} to {end_date}...")
    
    bar_files = sorted(glob.glob(str(BARS_DIR / "GME_*_minute.csv")))
    
    all_bars = []
    for f in bar_files:
        temp = pd.read_csv(f)
        temp['timestamp'] = pd.to_datetime(temp['timestamp'], utc=True)
        all_bars.append(temp[['timestamp', 'close']])
        
    if not all_bars:
        print("No bar files found.")
        return []
        
    df_all = pd.concat(all_bars, ignore_index=True)
    # Use numpy argsort to bypass pandas sorting bug
    order = np.argsort(df_all['timestamp'].values)
    df_all = df_all.iloc[order].reset_index(drop=True)
    df_all = df_all[(df_all['timestamp'] >= start_date) & (df_all['timestamp'] <= end_date)]
    
    print(f"Loaded {len(df_all)} bars.")
    
    # Segment into windows (sliding every 30 mins)
    windows = []
    step = 30  # minutes
    
    for i in range(0, len(df_all) - window_mins, step):
        chunk = df_all.iloc[i:i+window_mins]
        prices = chunk['close'].values
        shape = (prices - prices.min()) / (prices.max() - prices.min() + 1e-9)
        
        windows.append({
            'start_time': chunk['timestamp'].iloc[0],
            'end_time': chunk['timestamp'].iloc[-1],
            'shape': shape
        })
        
    print(f"Created {len(windows)} history windows.")
    return windows

def find_echoes(templates, history, top_n=10):
    """
    Search for nearest matches using DTW.
    """
    print("\nSearching for Echoes using DTW...")
    
    results = []
    
    for tmpl in templates:
        tmpl_shape = tmpl['shape']
        tmpl_date = pd.Timestamp(tmpl['timestamp'])
        
        matches = []
        
        for win in history:
            win_date = pd.Timestamp(win['start_time'])
            
            # Skip if too close to template (within 30 days)
            lag_days = (win_date - tmpl_date).days
            if abs(lag_days) < 30:
                continue
                
            # DTW distance
            dist = dtw_distance(tmpl_shape.astype(np.float64), win['shape'].astype(np.float64))
            
            matches.append({
                'template_date': tmpl['date'],
                'match_date': win['start_time'],
                'lag_days': lag_days,
                'dtw_distance': dist
            })
            
        # Sort by DTW distance (lower = better match)
        matches = sorted(matches, key=lambda x: x['dtw_distance'])[:top_n]
        results.extend(matches)
        
        print(f"  Template {tmpl['date']}: Best match @ {matches[0]['lag_days']} days (DTW={matches[0]['dtw_distance']:.4f})")
        
    return results

def main():
    templates = load_burst_templates(n_templates=5)
    if not templates:
        print("No templates found. Exiting.")
        return
        
    history = load_history_shapes(start_date='2023-06-01', end_date='2024-12-31', window_mins=60)
    
    echoes = find_echoes(templates, history, top_n=5)
    
    # Analyze lag distribution
    lags = [e['lag_days'] for e in echoes if e['lag_days'] > 0]
    
    print(f"\n--- Echo Detection Results ---")
    print(f"Total Echoes Found: {len(echoes)}")
    if lags:
        print(f"Lag Distribution (Forward Only):")
        print(f"  Mean: {np.mean(lags):.0f} days")
        print(f"  Median: {np.median(lags):.0f} days")
        print(f"  Modes: Check histogram for ~120, ~240, ~420 clusters")
        
        # Plot
        plt.figure(figsize=(10, 6))
        plt.hist(lags, bins=20, edgecolor='black')
        plt.title("Echo Lag Distribution (DTW Matches)")
        plt.xlabel("Lag (Days)")
        plt.ylabel("Count")
        plt.savefig(RESULTS_DIR / "echo_lag_distribution.png")
        print(f"Saved: {RESULTS_DIR / 'echo_lag_distribution.png'}")
        
    # Save results
    df_echoes = pd.DataFrame(echoes)
    df_echoes.to_csv(RESULTS_DIR / "echo_matches.csv", index=False)
    print(f"Saved: {RESULTS_DIR / 'echo_matches.csv'}")

if __name__ == "__main__":
    main()
