#!/usr/bin/env python3
"""
Phase 30E: Seed Day Forensics
Event Study on 0xDF (Fractal Seed) Opcodes.
Analyzes market reaction (SPY, QQQ, TSLA) around the "Seed" event.

Hypothesis: 0xDF marks a "State Reset" or "Volatility Collapse".
"""

import pandas as pd
import numpy as np
from pathlib import Path
import warnings

warnings.filterwarnings('ignore')

# Configuration
DATA_DIR = Path("data/ticks")
OUTPUT_FILE = Path("research/phase30_interconnectedness/seed_event_study.csv")
EXCHANGE_EDGX = 4

# Target Dates (High 0xDF count)
SEED_DAYS = [
    "2025-01-06", # 73 Seeds
    "2025-06-11", # 83 Seeds
    "2025-01-02", # 48 Seeds
    "2025-01-07"  # 57 Seeds
]

WINDOW_PRE = 10  # Minutes before
WINDOW_POST = 30 # Minutes after

def load_price_series(date, symbol):
    path = DATA_DIR / date / f"{symbol}.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, usecols=['timestamp_us', 'price'])
        # Coerce
        df['timestamp_us'] = pd.to_numeric(df['timestamp_us'], errors='coerce')
        df.dropna(subset=['timestamp_us'], inplace=True)
        
        if df.empty: return None
        
        # Data appears to be reverse chronological, flip to ascending
        if df['timestamp_us'].iloc[0] > df['timestamp_us'].iloc[-1]:
             df = df.iloc[::-1]
        return df
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return None

def extract_seed_timestamps(date):
    """Find 0xDF timestamps in GME EDGX data"""
    path = DATA_DIR / date / "GME.csv"
    if not path.exists():
        return []
    
    df = pd.read_csv(path, usecols=['timestamp_us', 'price', 'exchange'])
    edgx = df[df['exchange'] == EXCHANGE_EDGX].copy()
    
    if edgx.empty:
        return []
        
    edgx = edgx.dropna(subset=['timestamp_us']).sort_values('timestamp_us')
    
    prices = edgx['price'].values
    cents = (prices * 100).round().astype(int)
    lsbs = cents & 1
    timestamps = edgx['timestamp_us'].values
    
    seeds = []
    
    for i in range(0, len(lsbs) - 7, 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | lsbs[i+j]
            
        if byte == 0xDF:
            # Mark time
            seeds.append(timestamps[i+7]) # Time of completion
            
    return seeds

def get_event_window(price_df, event_ts, symbol):
    """Extract return profile around event"""
    # Convert window to us
    window_pre_us = WINDOW_PRE * 60 * 1_000_000
    window_post_us = WINDOW_POST * 60 * 1_000_000
    
    start_ts = event_ts - window_pre_us
    end_ts = event_ts + window_post_us
    
    # Filter
    # Using searchsorted for speed if array is large
    # but boolean mask is fine for daily file
    mask = (price_df['timestamp_us'] >= start_ts) & (price_df['timestamp_us'] <= end_ts)
    window = price_df[mask].copy()
    
    if window.empty:
        return None
        
    # Normalize Time (Minutes relative to event)
    window['rel_min'] = (window['timestamp_us'] - event_ts) / 60_000_000
    
    # Normalize Price (Return relative to event time price)
    # Find price closest to event_ts
    # If exact match missing, use nearest
    
    # Absolute difference
    idx_nearest = (np.abs(window['timestamp_us'] - event_ts)).argmin()
    base_price = window.iloc[idx_nearest]['price']
    
    window['pct_change'] = (window['price'] - base_price) / base_price * 100
    
    # Bin to 1-minute intervals for averaging
    window['bin'] = window['rel_min'].round().astype(int)
    
    # Group by bin, get mean return for that bin
    profile = window.groupby('bin')['pct_change'].last() # Use last price in bin
    
    return profile

def main():
    print("PHASE 30E: SEED DAY FORENSICS")
    print("================================")
    
    all_profiles = []
    
    for date in SEED_DAYS:
        print(f"Scanning {date}...")
        seeds = extract_seed_timestamps(date)
        print(f"  Found {len(seeds)} Seeds (0xDF).")
        
        if not seeds:
            continue
            
        # Load Context
        spy_df = load_price_series(date, "SPY")
        qqq_df = load_price_series(date, "QQQ")
        tsla_df = load_price_series(date, "TSLA")
        
        for seed_ts in seeds:
            # Process SPY
            if spy_df is not None:
                p = get_event_window(spy_df, seed_ts, "SPY")
                if p is not None:
                    df_p = p.reset_index()
                    df_p['symbol'] = 'SPY'
                    df_p['event_id'] = f"{date}_{seed_ts}"
                    all_profiles.append(df_p)
                    
            # Process QQQ
            if qqq_df is not None:
                p = get_event_window(qqq_df, seed_ts, "QQQ")
                if p is not None:
                    df_p = p.reset_index()
                    df_p['symbol'] = 'QQQ'
                    df_p['event_id'] = f"{date}_{seed_ts}"
                    all_profiles.append(df_p)
                    
            # Process TSLA
            if tsla_df is not None:
                p = get_event_window(tsla_df, seed_ts, "TSLA")
                if p is not None:
                    df_p = p.reset_index()
                    df_p['symbol'] = 'TSLA'
                    df_p['event_id'] = f"{date}_{seed_ts}"
                    all_profiles.append(df_p)

    if not all_profiles:
        print("No profiles generated.")
        return

    full_df = pd.concat(all_profiles)
    
    # Aggregate
    # Group by Symbol and Bin (Rel Minute) -> Mean Return
    agg = full_df.groupby(['symbol', 'bin'])['pct_change'].agg(['mean', 'std', 'count']).reset_index()
    
    # Save
    agg.to_csv(OUTPUT_FILE, index=False)
    print(f"\nEvent Study Data saved to {OUTPUT_FILE}")
    
    # Display Snippet
    print("\nRESULTS (SPY Mean Response):")
    spy_res = agg[agg['symbol'] == 'SPY'].pivot(index='bin', columns='symbol', values='mean')
    # Show key bins
    relevant_bins = [-10, -5, -1, 0, 1, 5, 10, 30]
    print(spy_res.loc[[b for b in relevant_bins if b in spy_res.index]])

if __name__ == "__main__":
    main()
