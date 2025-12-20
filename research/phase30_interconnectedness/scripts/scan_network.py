
import pandas as pd
from pathlib import Path
import os

# Configuration
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "ticks"
OUTPUT_FILE = BASE_DIR / "output" / "signal_log.csv"

# Patterns
PATTERN_FWD = [0.07, 0.04, 0.01]
PATTERN_REV = [0.01, 0.04, 0.07]

def scan_file(filepath):
    """
    Scans a single tick file for the patterns.
    Returns a dataframe of events.
    """
    print(f"Scanning {filepath}...")
    try:
        df = pd.read_csv(filepath)
    except Exception as e:
        print(f"Failed to read {filepath}: {e}")
        return pd.DataFrame()

    if len(df) < 4:
        return pd.DataFrame()

    # Calculate Price Delta
    # We care about absolute difference between consecutive trades
    # diff() gives current - prev. We take abs().
    # Rounding is crucial for float matching.
    df['delta'] = df['price'].diff().abs().round(2)
    
    # We need to find sequences.
    # We can use rolling windows or shift comparison. 
    # For a 3-step pattern, we look at i, i-1, i-2
    # Patterns are mapped to the LAST trade in the sequence (the trigger).
    
    # alignment:
    # d0 = delta at i
    # d1 = delta at i-1
    # d2 = delta at i-2
    
    d0 = df['delta']
    d1 = df['delta'].shift(1)
    d2 = df['delta'].shift(2)
    
    # Forward Pattern: 0.07 (oldest), 0.04, 0.01 (newest)
    # This means d2=0.07, d1=0.04, d0=0.01 at current index i
    
    mask_fwd = (d2 == PATTERN_FWD[0]) & (d1 == PATTERN_FWD[1]) & (d0 == PATTERN_FWD[2])
    
    # Reverse Pattern: 0.01 (oldest), 0.04, 0.07 (newest)
    mask_rev = (d2 == PATTERN_REV[0]) & (d1 == PATTERN_REV[1]) & (d0 == PATTERN_REV[2])
    
    events = []
    
    # Extract Forward Events
    fwd_indices = df.index[mask_fwd]
    for idx in fwd_indices:
        row = df.iloc[idx]
        events.append({
            "timestamp_us": row['timestamp_us'],
            "symbol": row['symbol'],
            "price": row['price'],
            "type": "FORWARD_741",
            "date": filepath.parent.name # Infer date from folder structure
        })
        
    # Extract Reverse Events
    rev_indices = df.index[mask_rev]
    for idx in rev_indices:
        row = df.iloc[idx]
        events.append({
            "timestamp_us": row['timestamp_us'],
            "symbol": row['symbol'],
            "price": row['price'],
            "type": "REVERSE_741",
            "date": filepath.parent.name
        })
        
    return pd.DataFrame(events)

def main():
    all_events = []
    
    # Walk through the data directory
    # Expecting data/ticks/{date}/{ticker}.csv
    if not DATA_DIR.exists():
        print(f"Data directory {DATA_DIR} not found.")
        return

    for date_dir in DATA_DIR.iterdir():
        if not date_dir.is_dir():
            continue
            
        print(f"Scanning date: {date_dir.name}")
        for csv_file in date_dir.glob("*.csv"):
            events_df = scan_file(csv_file)
            if not events_df.empty:
                all_events.append(events_df)
                print(f"  Found {len(events_df)} signals in {csv_file.name}")
            else:
                print(f"  No signals in {csv_file.name}")
                
    if all_events:
        master_log = pd.concat(all_events)
        if 'timestamp_us' in master_log.columns:
            master_log.sort_values("timestamp_us", inplace=True)
        
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        master_log.to_csv(OUTPUT_FILE, index=False)
        print(f"\nScan Complete. Saved {len(master_log)} total events to {OUTPUT_FILE}")
        
        # Quick summary stats
        print("\nSummary by Symbol/Type:")
        print(master_log.groupby(['symbol', 'type', 'date']).size())
    else:
        print("No events found in any files.")

if __name__ == "__main__":
    main()
