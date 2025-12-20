#!/usr/bin/env python3
"""
Fractal Inspector
=================

Inspects the specific successful match found by fractal_matcher.py.
Target: Bar Index 7300 in the macro series.
"""

from pathlib import Path
import pandas as pd
import sys

# Import local modules
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fractal_matcher import load_macro_data

def inspect_match():
    # Re-load macro series (this repeats work but ensures index alignment)
    print("Reloading Macro Data to Map Index to Time...")
    from core.loader import get_sample_dirs
    sample_dirs = get_sample_dirs()
    # Filter for May
    sample_dirs = [d for d in sample_dirs if "2024-05" in d.name]
    
    full_price_history = []
    
    # Needs to match load_macro_data order exactly
    for d in sample_dirs:
        try:
            trades_files = list(d.glob(f"raw_ticks/GME*_trades.csv"))
            if trades_files:
                df = pd.read_csv(trades_files[0])
                df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True) # Standardize
                df.set_index('timestamp', inplace=True)
                bars = df['price'].resample('1min').ohlc()
                bars = bars.dropna()
                full_price_history.append(bars['close'])
        except:
            pass
            
    if not full_price_history:
        print("Failed to load macro data")
        return

    macro_series = pd.concat(full_price_history)
    print(f"Total Bars: {len(macro_series)}")
    
    # Target Index from previous run: 7300
    # Window Size was 200 bars (default extract_seeds) or 500? Use 500 from call.
    start_idx = 7300
    end_idx = 7300 + 500
    
    if start_idx < len(macro_series):
        match_window = macro_series.iloc[start_idx : end_idx]
        print("\nMATCHED FRACTAL WINDOW:")
        print(f"Start Time: {match_window.index[0]}")
        print(f"End Time:   {match_window.index[-1]}")
        print(f"Start Price: ${match_window.iloc[0]:.2f}")
        print(f"End Price:   ${match_window.iloc[-1]:.2f}")
        
        # Describe the shape
        change = (match_window.iloc[-1] - match_window.iloc[0]) / match_window.iloc[0] * 100
        print(f"Shape Description: {change:+.2f}% Move over {len(match_window)} minutes")
    else:
        print("Index out of bounds.")

if __name__ == "__main__":
    inspect_match()
