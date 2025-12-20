#!/usr/bin/env python3
"""
Prepare TISA Input
==================

Extracts the 'Micro-Seed' price path (Post-0xDF signal) pattern 
and saves it in the format expected by tisa_extended.py.

Format:
  timestamp_ms,price
  (ms since midnight UTC of the anchor date)
"""

from pathlib import Path
import pandas as pd
import sys

# Import local modules
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs

def prepare_seed():
    print("Preparing TISA Seed (May 16 0xDF)...")
    
    # Locate May 16 sample
    sample_dirs = get_sample_dirs()
    target_dir = next((d for d in sample_dirs if "2024-05-16" in d.name), None)
    
    if not target_dir:
        print("May 16 sample not found.")
        return

    # Load Data
    df = load_edgx_data(target_dir, symbol='GME')
    
    # Target Timestamp (extracted from Phase 19/21 results)
    # 2024-05-16 16:33:56.291 (Post-Market 0xDF)
    target_ts_str = "2024-05-16 16:33:56"
    target_ts = pd.Timestamp(target_ts_str).tz_localize("US/Eastern")
    
    # Find index
    # We allow some slop because we just want the burst
    # Actually, let's just search for the specific 0xDF again to be precise?
    # Or just use the timestamp search.
    
    # Filter using string since df['timestamp'] is TZ-aware
    mask = (df['timestamp'] >= target_ts)
    if not mask.any():
        print("Target timestamp not found.")
        return
        
    start_idx = df[mask].index[0]
    
    # Extract 500 ticks
    window = df.iloc[start_idx : start_idx + 500].copy()
    
    # Calculate timestamp_ms (since midnight UTC of 2024-05-16)
    # Check what TISA expects: "day_start + ms"
    # So if the date is 2024-05-16, day_start is 2024-05-16 00:00:00 UTC.
    
    base_date = pd.Timestamp("2024-05-16").tz_localize("UTC")
    
    # Convert window timestamp to UTC first
    window['ts_utc'] = window['timestamp'].dt.tz_convert("UTC")
    
    # Calculate delta
    window['delta'] = window['ts_utc'] - base_date
    window['timestamp_ms'] = window['delta'].dt.total_seconds() * 1000
    
    # Select columns
    out_df = window[['timestamp_ms', 'price']]
    
    # Save
    out_path = Path(__file__).parent / "seed_may16_0xDF.csv"
    out_df.to_csv(out_path, index=False)
    
    print(f"Saved seed to {out_path}")
    print(f"  Rows: {len(out_df)}")
    print(f"  Start ms: {out_df.iloc[0]['timestamp_ms']}")
    print(f"  Start Time (UTC): {base_date + pd.to_timedelta(out_df.iloc[0]['timestamp_ms'], unit='ms')}")

if __name__ == "__main__":
    prepare_seed()
