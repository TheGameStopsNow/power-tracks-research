"""
Phase 81: Fingerprint Universe Bursts (TSLA, AMD)

Aggregates Greek flow, identifies bursts, computes Prism Fingerprints, and tracks returns.
"""

import pandas as pd
import numpy as np
import glob
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
GREEK_DIR = BASE_DIR / "research/phase81_precision/output"
EXPANDED_BARS_DIR = BASE_DIR / "research/phase81_precision/data/bars"
OUTPUT_DIR = BASE_DIR / "research/phase81_precision/output"

def load_and_aggregate(ticker):
    files = sorted(list(GREEK_DIR.glob(f"{ticker.lower()}_greeks_*.csv")))
    all_bursts = []
    
    print(f"Fingerprinting {ticker} ({len(files)} days)...")
    
    for f in files:
        try:
            df = pd.read_csv(f)
            df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed', utc=True)
            df = df.set_index('timestamp').sort_index()
            
            # Filter Invalid IVs
            if 'iv' in df.columns:
                df = df[(df['iv'] > 0.001) & (df['iv'] < 5.0)]
            
            df['is_0dte'] = (df['time_to_expiry'] < (1/365)).astype(int)
            
            # Aggregate to 1s
            agg = df.resample('1s').agg({
                'gamma': 'sum',
                'delta': 'sum',
                'charm': 'sum',
                'size': 'sum',
                'is_0dte': 'sum',
                'underlying_price': 'last',
                'iv': 'mean' # Real IV from compute_greeks
            }).dropna()
            
            # Simple Burst Threshold (99th percentile of file?)
            # Or absolute? Let's use percentile for generality.
            if len(agg) < 10: continue
            
            threshold = agg['gamma'].abs().quantile(0.99) # Absolute Gamma burst
            bursts = agg[agg['gamma'].abs() > threshold].copy()
            
            if len(bursts) == 0: continue
            
            bursts['ticker'] = ticker
            bursts['pct_0dte'] = bursts['is_0dte'] / bursts['size']
            bursts['gamma_flow'] = bursts['gamma']
            bursts['delta_flow'] = bursts['delta']
            bursts['charm_flow'] = bursts['charm']
            
            # Deduplicate (keep max within 5 mins) - Skip for speed/MVP
            
            # Need to restore timestamp as column
            bursts = bursts.reset_index()
            all_bursts.append(bursts)
            
        except Exception as e:
            print(f"Error {f.name}: {e}")
            
    if all_bursts:
        return pd.concat(all_bursts)
    return pd.DataFrame()

def track_returns(bursts):
    # Load bars for each ticker
    tickers = bursts['ticker'].unique()
    
    bursts['ret_1d'] = np.nan
    bursts['ret_5d'] = np.nan
    
    final_dfs = []
    
    for ticker in tickers:
        subset = bursts[bursts['ticker'] == ticker].copy()
        bar_dir = EXPANDED_BARS_DIR / ticker
        files = sorted(list(bar_dir.glob("*.csv")))
        print(f"  Ticker {ticker}: Searching {bar_dir} -> Found {len(files)} files.")
        
        all_bars = []
        for f in files:
            try:
                temp = pd.read_csv(f)
                temp['timestamp'] = pd.to_datetime(temp['timestamp'], format='mixed', utc=True)
                all_bars.append(temp[['timestamp', 'close']])
            except Exception as e:
                print(f"Failed to load {f.name}: {e}")
                continue
            
        if not all_bars: continue
        
        valid_bars = [df for df in all_bars if not df.empty]
        if not valid_bars: continue
        
        bars_df = pd.concat(valid_bars)
        print(f"  Ticker {ticker}: Concat size {len(bars_df)}")
        if len(bars_df) > 0:
            bars_df = bars_df.sort_values('timestamp').reset_index(drop=True)
        bar_times = bars_df['timestamp'].values.astype('datetime64[ns]')
        
        # Track
        for idx, row in subset.iterrows():
            t0 = row['timestamp'].to_datetime64()
            start_pos = np.searchsorted(bar_times, t0)
            
            if start_pos >= len(bars_df): continue
            base_price = bars_df.iloc[start_pos]['close']
            
            # 1 day = 390 mins
            idx_1d = min(start_pos + 390, len(bars_df)-1)
            time_1d = (bars_df.iloc[idx_1d]['timestamp'] - row['timestamp']).total_seconds() / 86400
            
            # 2 days (since we only fetched 1 week)
            # Actually we fetched Feb 5-9. Ret_5d might be partial.
            # Let's check T+2d (Short term precision).
            
            idx_end = min(start_pos + 390*2, len(bars_df)-1)
            price_end = bars_df.iloc[idx_end]['close']
            ret = (price_end - base_price) / base_price * 100
            
            subset.at[idx, 'ret_2d'] = ret # We'll use 2d for short term validity
            
        final_dfs.append(subset)
        
    if final_dfs:
        return pd.concat(final_dfs)
    return pd.DataFrame()

def main():
    print("Phase 81: Fingerprinting Universe...")
    
    all_data = []
    for ticker in ["TSLA", "AMD"]:
        b = load_and_aggregate(ticker)
        all_data.append(b)
        
    if not all_data: return
    
    full_df = pd.concat(all_data)
    print(f"Total Bursts: {len(full_df)}")
    
    tagged = track_returns(full_df)
    
    out_file = OUTPUT_DIR / "universe_burst_fingerprints.csv"
    tagged.to_csv(out_file, index=False)
    print(f"Saved {len(tagged)} fingerprints.")

if __name__ == "__main__":
    main()
