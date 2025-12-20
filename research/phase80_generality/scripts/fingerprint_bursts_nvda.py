"""
Phase 80: Fingerprint NVDA Bursts (Generality Test)

This script:
1. Loads NVDA Greek flow.
2. Identifies Bursts (High Gamma Flow).
3. Computes Prism Fingerprints (0DTE %, IV, Charm).
4. Tracks T+20d returns (control period max availability).
"""

import pandas as pd
import numpy as np
import glob
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
INPUT_FILE = BASE_DIR / "research/phase80_generality/output/nvda_greeks.csv"
OUTPUT_DIR = BASE_DIR / "research/phase80_generality/output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def load_and_aggregate():
    # The original code iterated through multiple files.
    # Now, we expect a single aggregated file as INPUT_FILE.
    # The 'files' variable will now just contain this single file.
    files = [INPUT_FILE] # Adapt to load a single input file
    all_bursts = []
    
    for f in files:
        print(f"Processing {f.name}...")
        try:
            df = pd.read_csv(f)
            df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed', utc=True)
            
            # Aggregate to 1s
            df = df.set_index('timestamp').sort_index()
            # Key Metrics: Gamma Flow, Delta Flow, Charm Flow, Trade Count, 0DTE Count
            df['is_0dte'] = (df['time_to_expiry'] < (1/365)).astype(int)
            
            # Check if IV exists
            if 'iv' not in df.columns:
                df['iv'] = 0.45 # Constant assumption from compute_greeks
            
            agg = df.resample('1s').agg({
                'gamma': 'sum',
                'delta': 'sum',
                'charm': 'sum',
                'size': 'sum', # Volume
                'is_0dte': 'sum', # Count of 0DTE trades
                'underlying_price': 'last',
                'iv': 'mean' # Actually sigma=0.45 fixed, but passing through if needed
            }).dropna()
            
            # Identifying Bursts
            # Threshold: > 99th percentile of that day's second-by-second gamma flow?
            # Or fixed threshold? 
            # NVDA size is different from GME. Use percentile.
            threshold = agg['gamma'].mean() + 3 * agg['gamma'].std()
            bursts = agg[agg['gamma'] > threshold].copy()
            
            if len(bursts) == 0: continue
            
            # Add Fingerprints
            bursts['pct_0dte'] = bursts['is_0dte'] / bursts['size'] # Ratio of trades
            bursts['gamma_flow'] = bursts['gamma']
            bursts['delta_flow'] = bursts['delta']
            bursts['charm_flow'] = bursts['charm']
            
            # Basic deduplication (take max within 5 min window)
            # Simple skip for MVP
            bursts['timestamp'] = bursts.index
            all_bursts.append(bursts)
            
        except Exception as e:
            print(f"Error processing {f}: {e}")
            if 'df' in locals():
                print(f"Columns: {df.columns.tolist()}")
            
    if all_bursts:
        return pd.concat(all_bursts)
    else:
        return pd.DataFrame()

def track_returns(bursts):
    # Load all bars
    bar_files = sorted(list(BARS_DIR.glob("*.csv")))
    all_bars = []
    print(f"Loading bars from {BARS_DIR}...")
    for f in bar_files:
        try:
            temp = pd.read_csv(f)
            if len(temp) == 0: continue
            temp['timestamp'] = pd.to_datetime(temp['timestamp'], utc=True)
            all_bars.append(temp[['timestamp', 'close']])
        except Exception:
            continue
            
    if not all_bars:
        print("No bars loaded!")
        return bursts
        
    bars_df = pd.concat(all_bars).sort_values('timestamp').reset_index(drop=True)
    print(f"Loaded {len(bars_df)} bars.")
        
    bars_df = pd.concat(all_bars).sort_values('timestamp').reset_index(drop=True)
    bar_times = bars_df['timestamp'].values.astype('datetime64[ns]')
    
    bursts['ret_5d'] = np.nan
    bursts['ret_20d'] = np.nan
    
    # 5 days = 5 * 390 = 1950 minutes
    # 20 days = 7800 minutes
    
    valid_bursts = []
    
    for idx, row in bursts.iterrows():
        t0 = row['timestamp'].to_datetime64()
        start_pos = np.searchsorted(bar_times, t0)
        
        if start_pos >= len(bars_df): continue
        
        base_price = bars_df.iloc[start_pos]['close']
        
        # T+5d
        idx_5d = min(start_pos + 1950, len(bars_df)-1)
        price_5d = bars_df.iloc[idx_5d]['close']
        ret_5d = (price_5d - base_price) / base_price * 100
        
        # T+20d
        idx_20d = min(start_pos + 7800, len(bars_df)-1)
        price_20d = bars_df.iloc[idx_20d]['close']
        ret_20d = (price_20d - base_price) / base_price * 100
        
        # Check if we actually reached the horizon (timestamp diff)
        time_5d = (bars_df.iloc[idx_5d]['timestamp'] - row['timestamp']).total_seconds() / 86400
        # If less than 1 day, ignore
        if time_5d < 1: ret_5d = np.nan
        
        row['ret_5d'] = ret_5d
        row['ret_20d'] = ret_20d
        valid_bursts.append(row)
        
    return pd.DataFrame(valid_bursts)

def main():
    print("Fingerprinting NVDA Bursts...")
    bursts = load_and_aggregate()
    print(f"Found {len(bursts)} bursts.")
    
    if len(bursts) == 0: return

    tagged = track_returns(bursts)
    
    out_file = OUTPUT_DIR / "nvda_burst_fingerprints.csv"
    tagged.to_csv(out_file, index=False)
    print(f"Saved {len(tagged)} fingerprints to {out_file}")

if __name__ == "__main__":
    main()
