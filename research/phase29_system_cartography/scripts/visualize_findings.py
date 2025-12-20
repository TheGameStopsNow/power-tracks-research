
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
from pathlib import Path
from datetime import date, timedelta
import sys

# Paths
PHASE29_DIR = Path("/Users/TheGameStopsNow/Documents/GitHub/power-tracks-research/research/phase29_system_cartography")
REPORT_PATH = PHASE29_DIR / "SYSTEM_CARTOGRAPHY_REPORT.json"
SEEDS_FILE = PHASE29_DIR / "GME_2021-01-28_20210128_100000_ticks_seeds.csv"
PRICE_FILE = "/Users/TheGameStopsNow/Documents/GitHub/power-tracks-data/storage/ticks/GME_2021-01-28_20210128_100000_ticks.csv"
DELTA_FILE = PHASE29_DIR / "price_delta_signals.csv"



def extract_tape_snippet():
    print("Scanning FULL Real Tape for 7-4-1 Pattern...")
    
    real_file = PHASE29_DIR / "real_ticks/GME_2021-03-08_real_trades.csv"
    if not real_file.exists(): return

    df = pd.read_csv(real_file)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Calculate price deltas
    # We want absolute delta sequence: 0.07, 0.04, 0.01 (+/- 0.005 tolerance?)
    # Or exact cents: 0.07, 0.04, 0.01
    
    df['delta'] = df['price'].diff().abs().round(2)
    
    # Vectorized search pattern
    # Looking for row i=0.07, i+1=0.04, i+2=0.01
    
    # Create shifted columns
    d0 = df['delta']
    d1 = df['delta'].shift(-1)
    d2 = df['delta'].shift(-2)
    
    # Mask
    mask = (d0 == 0.07) & (d1 == 0.04) & (d2 == 0.01)
    matches = df[mask]
    
    out_file = PHASE29_DIR / "raw_tape_snippet.txt"
    
    with open(out_file, 'w') as f:
        f.write(f"REAL TAPE SCAN: GME 2021-03-08\n")
        f.write(f"Total Trades: {len(df)}\n")
        f.write(f"Pattern Matches (0.07 -> 0.04 -> 0.01): {len(matches)}\n\n")
        
        if len(matches) > 0:
            f.write("First 3 Matches:\n")
            for idx in matches.head(3).index:
                # Get context
                start = max(0, idx - 2)
                end = min(len(df), idx + 5)
                chunk = df.iloc[start:end]
                f.write(f"\nMatch at Index {idx} ({df.loc[idx, 'timestamp']}):\n")
                f.write(chunk[['timestamp', 'price', 'size', 'delta']].to_string())
                f.write("\n" + "-"*50 + "\n")
        else:
             f.write("RESULT: NO MATCHES FOUND IN REAL DATA.\n")
             f.write("The 7-4-1 Price Delta signal appears to be an artifact of synthetic interpolation.\n")
        
    print(f"Saved {out_file} with scan results.")


if __name__ == "__main__":
    if REPORT_PATH.exists():
        with open(REPORT_PATH, 'r') as f:
            report = json.load(f)
    else:
        print(f"Report not found at {REPORT_PATH}")
        
    extract_tape_snippet()
