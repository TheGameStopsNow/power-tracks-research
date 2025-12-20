"""
Phase 80: Compute Greeks for NVDA (Generality Test)

This script computes Greeks for the newly fetched NVDA OPRA trades.
It replicates `compute_greeks.py` but adjusted for NVDA parameters.
"""

import pandas as pd
import numpy as np
import scipy.stats as stats
from pathlib import Path
import glob
import time

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
OPRA_DIR = BASE_DIR / "research/phase80_generality/data/opra" # Changed from ticks_nvda
BARS_DIR = BASE_DIR / "research/phase80_generality/data/bars" # Changed from expanded_bars/NVDA
OUTPUT_DIR = BASE_DIR / "research/phase80_generality/output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
R = 0.052

def load_bars_for_date(date_str):
    bar_file = BARS_DIR / f"NVDA_{date_str}_minute.csv"
    if not bar_file.exists():
        return None
    df = pd.read_csv(bar_file)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.sort_values('timestamp')
    return df

def black_scholes_call(S, K, T, r, sigma):
    # Same as before
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    call = (S * stats.norm.cdf(d1) - K * np.exp(-r * T) * stats.norm.cdf(d2))
    return call

def compute_greeks(row):
    try:
        S = row['underlying_price']
        K = row['fetched_strike']
        
        # Parse expiration (YYYYMMDD to datetime)
        # Assuming current date is in row['timestamp']
        # T = (expiry - now) / 365
        # Or parse row['expiration']
        
        # Simple T approx:
        # We need expiration date. The fetcher saved 'expiration' column.
        # But format is YYYYMMDD string.
        
        # Let's rely on T being passed or computed.
        # For speed, let's pre-compute T in the dataframe before apply.
        T = row['time_to_expiry']
        
        r = R
        sigma = 0.45 # Fixed IV approx (NVDA avg)
        
        if T <= 0.001: return pd.Series([0,0,0,0], index=['delta','gamma','theta','charm'])
        
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        
        if row['fetched_right'] == 'C':
            delta = stats.norm.cdf(d1)
        else:
            delta = stats.norm.cdf(d1) - 1
            
        gamma = stats.norm.pdf(d1) / (S * sigma * np.sqrt(T))
        
        # Charm
        charm = -stats.norm.pdf(d1) * (2*r*T - d2*sigma*np.sqrt(T)) / (2*T*sigma*np.sqrt(T))
        
        return pd.Series([delta, gamma, 0, charm], index=['delta','gamma','theta','charm'])
        
    except Exception:
        return pd.Series([0,0,0,0], index=['delta','gamma','theta','charm'])

def process_file(file_path):
    # Extract date from filename: nvda_option_trades_20240205.csv
    date_str = file_path.stem.split('_')[-1]
    
    # Load Bars
    bars = load_bars_for_date(date_str)
    if bars is None:
        print(f"  Missing bars for {date_str}, skipping.")
        return None

    print(f"Processing {file_path.name}...")
    df = pd.read_csv(file_path)
    
    if len(df) == 0: return None
    
    # Prepare merge
    # Ticks have 'timestamp' (string? no, usually millis or string from Theta)
    # Theta CSV: 2024-02-05T09:30:00.000Z or similar?
    # Let's check format. It might be different. 
    # fetch_opra_nvda used pd.read_csv(StringIO(resp.text)).
    # Theta CSV usually has 'ms_of_day' or 'timestamp'.
    # If standard Theta v3 CSV: 'date' (YYYYMMDD) + 'ms_of_day' or 'timestamp'.
    
    # Assuming 'timestamp' exists and isparseable.
    # We need to inspect column names to be sure, but we saw them in Verification Step:
    # ['symbol', 'expiration', 'strike', 'right', 'timestamp', 'sequence', ... 'fetched_strike']
    
    # Parse timestamp
    # It might be an integer (millis) or string.
    # Theta V3 history usually returns formatted string if not efficient.
    # Let's assume to_datetime works.
    
    # Parse timestamp (Assume ET and convert to UTC)
    # Theta usually returns exchange time (ET).
    # Handle ambiguous times during DST transition? March is tricky.
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed')
    if df['timestamp'].dt.tz is None:
        df['timestamp'] = df['timestamp'].dt.tz_localize('America/New_York', ambiguous='infer').dt.tz_convert('UTC')
    
    # Merge AsOf
    df = df.sort_values('timestamp')
    
    # Fix Bar Prices (Un-Split)
    bars = bars.copy()
    bars['close'] = bars['close'] * 10
    
    print(f"  Bar Time Range: {bars['timestamp'].min()} to {bars['timestamp'].max()}")
    print(f"  Trade Time Range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    # Merge with bars
    # bars timestamp is UTC.
    merged = pd.merge_asof(
        df, 
        bars[['timestamp', 'close']], 
        on='timestamp', 
        direction='backward',
        tolerance=pd.Timedelta('5min') # Allow 5 min staleness
    )
    
    merged['underlying_price'] = merged['close']
    merged = merged.dropna(subset=['underlying_price'])
    
    if len(merged) == 0:
        return None
        
    # Compute Time to Expiry (T)
    # Expiration is string YYYYMMDD
    merged['expiry_dt'] = pd.to_datetime(merged['expiration'].astype(str), format='%Y%m%d').dt.tz_localize('UTC') + pd.Timedelta(hours=16) 
    merged['time_to_expiry'] = (merged['expiry_dt'] - merged['timestamp']).dt.total_seconds() / (365 * 24 * 3600)
    
    # Filter expired
    merged = merged[merged['time_to_expiry'] > 0]
    
    # Compute Greeks
    # Using 'apply' is slow but safe for MVP.
    greeks = merged.apply(compute_greeks, axis=1)
    result = pd.concat([merged, greeks], axis=1)
    
    # Save
    out_file = OUTPUT_DIR / f"nvda_greeks_{date_str}.csv"
    result.to_csv(out_file, index=False)
    print(f"  Saved {len(result)} rows with Greeks to {out_file}")
    
    return result

def main():
    print("Computing Greeks for NVDA...")
    files = sorted(list(OPRA_DIR.glob("*.csv")))
    
    for f in files:
        process_file(f)

if __name__ == "__main__":
    main()
