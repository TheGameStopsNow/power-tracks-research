
import pandas as pd
from pathlib import Path
import os
import multiprocessing
from functools import partial

# Configuration
DATA_DIR = Path("data/ticks")
OUTPUT_FILE = Path("research/phase30_interconnectedness/2025_signal_log.csv")

# Patterns
PATTERN_FWD = [0.07, 0.04, 0.01]
PATTERN_REV = [0.01, 0.04, 0.07]

def scan_file(filepath):
    """
    Scans a single tick file for the patterns.
    Returns a dataframe of events.
    """
    try:
        # Optimization: Read only needed columns
        df = pd.read_csv(filepath, usecols=['timestamp_us', 'price', 'symbol'])
    except Exception as e:
        # print(f"Failed to read {filepath}: {e}")
        return pd.DataFrame()

    if len(df) < 4:
        return pd.DataFrame()

    # Calculate Price Delta
    df['delta'] = df['price'].diff().abs().round(2)
    
    d0 = df['delta']
    d1 = df['delta'].shift(1)
    d2 = df['delta'].shift(2)
    
    # Forward Pattern
    mask_fwd = (d2 == PATTERN_FWD[0]) & (d1 == PATTERN_FWD[1]) & (d0 == PATTERN_FWD[2])
    
    # Reverse Pattern
    mask_rev = (d2 == PATTERN_REV[0]) & (d1 == PATTERN_REV[1]) & (d0 == PATTERN_REV[2])
    
    events = []
    parent_date = filepath.parent.name
    
    # Extract Forward Events
    fwd_indices = df.index[mask_fwd]
    if not fwd_indices.empty:
        # vectorized extraction?
        # row access is slow. 
        # But we need specific rows.
        for idx in fwd_indices:
            row = df.iloc[idx]
            events.append({
                "timestamp_us": row['timestamp_us'],
                "symbol": row['symbol'],
                "price": row['price'],
                "type": "FORWARD_741",
                "date": parent_date
            })
        
    # Extract Reverse Events
    rev_indices = df.index[mask_rev]
    if not rev_indices.empty:
        for idx in rev_indices:
            row = df.iloc[idx]
            events.append({
                "timestamp_us": row['timestamp_us'],
                "symbol": row['symbol'],
                "price": row['price'],
                "type": "REVERSE_741",
                "date": parent_date
            })
        
    return pd.DataFrame(events)

def process_date(date_dir):
    """Helper to process all files in a date directory"""
    day_events = []
    for csv_file in date_dir.glob("*.csv"):
        df = scan_file(csv_file)
        if not df.empty:
            day_events.append(df)
    
    if day_events:
        return pd.concat(day_events)
    return None

def main():
    if not DATA_DIR.exists():
        print(f"Data directory {DATA_DIR} not found.")
        return

    # Filter for 2025 directories only
    dirs = [d for d in DATA_DIR.iterdir() if d.is_dir() and d.name.startswith("2025")]
    dirs.sort()
    
    print(f"Parallel Scanning {len(dirs)} dates from 2025 using {multiprocessing.cpu_count()} cores...")

    all_dfs = []
    
    with multiprocessing.Pool() as pool:
        for i, result in enumerate(pool.imap_unordered(process_date, dirs), 1):
            if result is not None:
                all_dfs.append(result)
            
            if i % 10 == 0:
                print(f"Processed {i}/{len(dirs)} dates...")
                
    if all_dfs:
        master_log = pd.concat(all_dfs)
        master_log.sort_values(["date", "timestamp_us"], inplace=True)
        
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        master_log.to_csv(OUTPUT_FILE, index=False)
        print(f"\nScan Complete. Saved {len(master_log)} total events to {OUTPUT_FILE}")
        
        # Quick summary stats
        print("\nTop 5 Active Tickers in 2025:")
        print(master_log['symbol'].value_counts().head(5))
    else:
        print("No events found in any files.")

if __name__ == "__main__":
    main()
