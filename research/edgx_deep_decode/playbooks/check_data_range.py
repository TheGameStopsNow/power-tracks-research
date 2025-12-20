#!/usr/bin/env python3
"""
Check Data Range
================

Verifies the time range of the loaded data for May 2024 samples.
"""

from pathlib import Path
import pandas as pd
import sys

# Import local modules
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs

def check_ranges():
    sample_dirs = get_sample_dirs()
    # Filter for May 2024
    may_samples = [d for d in sample_dirs if "2024-05" in d.name]
    
    print(f"Found {len(may_samples)} samples in May 2024:")
    
    for d in may_samples:
        try:
            df = load_edgx_data(d, symbol='GME')
            min_ts = df['timestamp'].min()
            max_ts = df['timestamp'].max()
            
            # Convert to Eastern Time for readability
            min_et = min_ts.tz_convert('US/Eastern')
            max_et = max_ts.tz_convert('US/Eastern')
            
            print(f"  {d.name}: {min_et.strftime('%H:%M:%S')} - {max_et.strftime('%H:%M:%S')} ({len(df)} ticks)")
        except Exception as e:
            print(f"  {d.name}: Error - {e}")

if __name__ == "__main__":
    check_ranges()
