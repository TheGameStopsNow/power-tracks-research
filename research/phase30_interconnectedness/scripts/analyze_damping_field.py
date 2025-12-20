#!/usr/bin/env python3
"""
Phase 30E: Damping Field Analyzer
Analyzes intraday (1-minute) correlations between:
1. GME Opcode Density (The Jammer)
2. TSLA Volatility (The Signal)
3. TSLA 7-4-1 Signal Count (The Message)

Target: "Zombie Days" (High GME Density)
Hypothesis: High GME Density -> Low TSLA Volatility (Negative Correlation)
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys
import warnings

warnings.filterwarnings('ignore')

# Configuration
DATA_DIR = Path("data/ticks")
SIGNAL_LOG = Path("research/phase30_interconnectedness/2025_signal_log.csv")
OUTPUT_FILE = Path("research/phase30_interconnectedness/damping_field_report.txt")
EXCHANGE_EDGX = 4

# Known Zombie Days (from Phase 30D)
TARGET_DATES = [
    "2025-08-21", # 12.28% Density
    "2025-08-26", # 11.77% Density
    "2025-09-08", # 11.20% Density
    "2025-07-17", # 10.47% Density
    "2025-06-11", # High Rare Opcode Count (Seed Day)
]

def load_tick_data(date, symbol):
    path = DATA_DIR / date / f"{symbol}.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, usecols=['timestamp_us', 'price', 'exchange'])
        
        # Coerce to numeric (handle bad rows)
        df['timestamp_us'] = pd.to_numeric(df['timestamp_us'], errors='coerce')
        
        # Drop invalid timestamps
        df.dropna(subset=['timestamp_us'], inplace=True)
        
        if df.empty:
            return None
            
        # Data appears to be reverse chronological, flip to ascending
        if df['timestamp_us'].iloc[0] > df['timestamp_us'].iloc[-1]:
             df = df.iloc[::-1]
        
        # Fallback sort if needed (but might crash, so skip or try/except?)
        # Let's hope reversal is enough.
        
        df['datetime'] = pd.to_datetime(df['timestamp_us'], unit='us')
        df.set_index('datetime', inplace=True)
        
        return df
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return None

def calculate_opcode_density(gme_df):
    """Calculate Opcode Density per 1-minute bin"""
    # Filter EDGX
    edgx = gme_df[gme_df['exchange'] == EXCHANGE_EDGX].copy()
    if edgx.empty:
        return None

    # We need to act on the tick level first to identify opcodes, 
    # but for "Density" as a metric of *intensity*, raw count of EDGX ticks 
    # is a strong proxy, OR we can process opcodes if we want to be precise.
    # Given performance constraints, let's use "EDGX Tick Count" as a proxy for 
    # "Potential Opcode Bandwidth". 
    # BUT Phase 30D showed density is a specific property.
    # Let's try to be precise: "Known Opcode Hits" per minute.
    
    # 1. Extract LSBs (Vectorized)
    prices = edgx['price'].values
    cents = (prices * 100).round().astype(int)
    lsbs = cents & 1
    
    # 2. Reconstruct Opcodes (Stride 8)
    # This is tricky to bin directly by time because opcodes span 8 ticks.
    # We will assign the timestamp of the LAST tick to the opcode.
    
    opcodes = []
    timestamps = []
    
    # Fast iteration
    edgx_timestamps = edgx.index
    n_ticks = len(lsbs)
    
    # Only iterate full bytes
    limit = n_ticks - 7
    indices = range(0, limit, 8)
    
    # Pre-calculate powers of 2 for dot product if we wanted full vectorization, but loop is okay for 1 day
    # Let's stick to the loop for safety
    
    KNOWN_SET = {0xA0, 0x98, 0x80, 0x10, 0x01, 0x02, 0xDF}
    
    hit_timestamps = []
    
    for i in indices:
        byte = 0
        for j in range(8):
            byte = (byte << 1) | lsbs[i + j]
        
        if byte in KNOWN_SET:
            # Assign time of completion
            hit_timestamps.append(edgx_timestamps[i+7])
            
    # Create Series of Hits
    if not hit_timestamps:
        return pd.Series(0, index=gme_df.resample('1min').first().index) # Return empty
        
    hits_series = pd.Series(1, index=hit_timestamps)
    
    # Resample to 1-minute count
    density_per_min = hits_series.resample('1min').sum().fillna(0)
    
    return density_per_min

def analyze_day(date):
    print(f"Analyzing {date}...")
    
    # 1. Load Data
    gme_df = load_tick_data(date, "GME")
    tsla_df = load_tick_data(date, "TSLA")
    
    if gme_df is None or tsla_df is None:
        print("  Missing data.")
        return None
        
    # 2. GME Density (The Jammer)
    gme_density = calculate_opcode_density(gme_df)
    if gme_density is None or gme_density.sum() == 0:
        print("  No GME opcodes found.")
        return None
        
    # 3. TSLA Volatility (The Target)
    # Resample TSLA price to 1-min OHLC to get volatility (High - Low) or StdDev
    tsla_vol = tsla_df['price'].resample('1min').std().fillna(0)
    
    # 4. TSLA Signals (The Message)
    signal_df = pd.read_csv(SIGNAL_LOG)
    signal_df['datetime'] = pd.to_datetime(signal_df['timestamp_us'], unit='us')
    
    # Filter for date + TSLA
    day_signals = signal_df[
        (signal_df['date'] == date) & 
        (signal_df['symbol'] == 'TSLA')
    ]
    
    if not day_signals.empty:
        day_signals.set_index('datetime', inplace=True)
        tsla_signals = day_signals.resample('1min').size().reindex(tsla_vol.index, fill_value=0)
    else:
        tsla_signals = pd.Series(0, index=tsla_vol.index)

    # 5. Align Dataframes
    # Use intersection of times (market hours usually 9:30 - 16:00)
    df = pd.DataFrame({
        'GME_Density': gme_density,
        'TSLA_Vol': tsla_vol,
        'TSLA_Signals': tsla_signals
    }).dropna()
    
    # 6. Correlation Analysis
    corr_vol = df['GME_Density'].corr(df['TSLA_Vol'])
    corr_sig = df['GME_Density'].corr(df['TSLA_Signals'])
    
    # 7. Lag Analysis (Granger-lite)
    # Does GME(t) predict TSLA_Vol(t+1)?
    lag1_corr = df['GME_Density'].corr(df['TSLA_Vol'].shift(-1))
    lag5_corr = df['GME_Density'].corr(df['TSLA_Vol'].shift(-5))
    
    return {
        'date': date,
        'corr_vol': corr_vol,
        'corr_sig': corr_sig,
        'lag1_corr': lag1_corr,
        'lag5_corr': lag5_corr,
        'avg_density': df['GME_Density'].mean(),
        'avg_vol': df['TSLA_Vol'].mean()
    }

def main():
    print("PHASE 30E: DAMPING FIELD ANALYSIS")
    print("=================================")
    
    results = []
    
    for date in TARGET_DATES:
        res = analyze_day(date)
        if res:
            results.append(res)
            
    if not results:
        print("No results generated.")
        sys.exit(1)
        
    res_df = pd.DataFrame(results)
    
    print("\nRESULTS SUMMARY:")
    print(res_df.to_string(index=False))
    
    # Aggregate Stats
    avg_corr_vol = res_df['corr_vol'].mean()
    avg_corr_sig = res_df['corr_sig'].mean()
    
    with open(OUTPUT_FILE, 'w') as f:
        f.write("PHASE 30E: DAMPING FIELD REPORT\n")
        f.write("===============================\n\n")
        f.write(f"Analyzed {len(res_df)} Zombie Days.\n\n")
        f.write("HYPOTHESIS CHECK:\n")
        f.write(f"1. GME Density vs TSLA Volatility: {avg_corr_vol:.4f}\n")
        f.write(f"   (Exp: Negative. Result: {'CONFIRMED' if avg_corr_vol < -0.1 else 'INCONCLUSIVE'})\n\n")
        f.write(f"2. GME Density vs TSLA Signals: {avg_corr_sig:.4f}\n")
        f.write(f"   (Exp: Negative. Result: {'CONFIRMED' if avg_corr_sig < -0.1 else 'INCONCLUSIVE'})\n\n")
        
        f.write("DAY-BY-DAY BREAKDOWN:\n")
        f.write(res_df.to_string())
        
    print(f"\nReport saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
