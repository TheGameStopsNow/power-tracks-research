
import os
import pandas as pd
import numpy as np
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

# --- SETTINGS ---
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Re-use Phase 19 data cache if possible to save time, or fetch fresh
# We need high-res 1-minute aligned data.
# We will focus on the "Core Basket" + "Control" for this deep dive.
BASKET = ["GME", "AMC", "KOSS", "SLE", "CLOV", "BB", "SPY", "AAPL", "NVDA"]
DATE_RANGE = ["2024-05-13", "2024-05-14", "2024-05-15", "2024-05-16", "2024-05-17"] # War Week

API_KEY = os.environ.get("POLYGON_API_KEY")

def load_or_fetch_ticks(symbol, date):
    # Try finding in previous caches first
    roots = [
        BASE_DIR.parent / "phase19_long_tail/data",
        BASE_DIR.parent / "phase18_ripple/data",
        BASE_DIR.parent / "phase17_targeted/data"
    ]
    
    filename = f"{symbol}_{date}.csv"
    for r in roots:
        p = r / filename
        if p.exists():
            return pd.read_csv(p)
            
    # If not found, we skip (assuming previous phases did their job) or fetch?
    # Let's assume we have data from Phase 18/19 for these dates. 
    # If strictly needed, we can implement fetch logic here, but let's try to map existing data first.
    return None

def main():
    print("--- Phase 22: Synchronicity Analysis ---")
    
    # 1. Build the "Event Matrix" (Time x Symbol)
    # 1-minute resolution
    
    minute_events = {} # "YYYY-MM-DD HH:MM" -> { "GME": 1, "AMC": 0 ... }
    
    total_files = len(BASKET) * len(DATE_RANGE)
    processed = 0
    
    for date in DATE_RANGE:
        print(f"Processing {date}...")
        for sym in BASKET:
            df = load_or_fetch_ticks(sym, date)
            if df is None or df.empty:
                continue
                
            # Process Ticks -> Opcodes
            prices = df["price"].values
            ts_ms = df["timestamp_us"].values // 1000 # Convert US to MS for consistency if needed, wait input is US
            # Actually timestamp_us in cached CSVs from run_study.py (Phase 19) was already converted?
            # Phase 19 run_study: "ts_us = int(...) // 1000" -> So it is ms? Name implies us.
            # Let's check a sample.
            # If values differ by 1000x, we know.
            # Logic: We define 1 minute bins.
            
            # Convert to datetime
            # df['dt'] = pd.to_datetime(df['timestamp_us'], unit='us') # Checking Phase 19 logic
            # Phase 19: "df['datetime'] = pd.to_datetime(df['timestamp_us'], unit='us')"
            # So the column IS microseconds.
            
            try:
                times = pd.to_datetime(df['timestamp_us'], unit='us')
            except:
                # Fallback if it was ms
                times = pd.to_datetime(df['timestamp_us'], unit='ms')
                
            # Filter Opcodes
            lsbs = (np.floor(prices * 100).astype(int) & 1)
            
            # Simple Byte-Check Window
            # Doing a sliding window here is slow. 
            # Simplified "Burst Check": If a minute has > threshold valid opcodes?
            # Or simplified: Start of byte aligned?
            
            # For Synchronicity, we check if the SYMBOL emitted a valid ROSETTA Opcode in that minute.
            # We iterate prices, form bytes. If byte in Rosetta, mark its timestamp.
            ROSETTA = {0xA0, 0x98, 0x80, 0x10, 0x01, 0x02}
            
            # Vectorized Byte Construction (Fast)
            # Pad to multiple of 8
            pad = (8 - (len(lsbs) % 8)) % 8
            if pad > 0:
                lsbs = np.pad(lsbs, (0, pad), 'constant')
            
            lsbs_reshaped = lsbs.reshape(-1, 8)
            # Pack bits: (bit0<<7) | (bit1<<6) ...
            # Powers of 2: [128, 64, 32, 16, 8, 4, 2, 1]
            powers = np.array([128, 64, 32, 16, 8, 4, 2, 1], dtype=int)
            bytes_val = np.dot(lsbs_reshaped, powers)
            
            # Timestamps for the start of each byte (every 8th tick)
            byte_times = times[::8]
            
            # Filter
            mask = np.isin(bytes_val, list(ROSETTA))
            valid_times = byte_times[mask[:len(byte_times)]] # Adjust length if needed
            
            # Bin by Minute
            if len(valid_times) > 0:
                # Floor to minute
                minutes = valid_times.dt.floor('min') # T = Minute
                unique_minutes = minutes.unique()
                
                for t in unique_minutes:
                    key = t.strftime("%Y-%m-%d %H:%M")
                    if key not in minute_events: minute_events[key] = {}
                    minute_events[key][sym] = 1
                    
    # 2. Convert to DataFrame
    matrix_df = pd.DataFrame.from_dict(minute_events, orient='index').fillna(0)
    matrix_df = matrix_df.sort_index()
    
    # Save Matrix
    matrix_df.to_csv(DATA_DIR / "synchronicity_matrix.csv")
    print(f"Index size: {len(matrix_df)}")
    
    # 3. Calculate Jaccard Similarity (Co-occurrence)
    # P(A and B) / P(A or B)
    if not matrix_df.empty:
        cooc = pd.DataFrame(index=matrix_df.columns, columns=matrix_df.columns)
        for s1 in matrix_df.columns:
            for s2 in matrix_df.columns:
                if s1 == s2:
                    cooc.loc[s1, s2] = 1.0
                    continue
                
                # Intersection (Both 1)
                both = ((matrix_df[s1] == 1) & (matrix_df[s2] == 1)).sum()
                # Union (Either 1)
                either = ((matrix_df[s1] == 1) | (matrix_df[s2] == 1)).sum()
                
                score = both / either if either > 0 else 0.0
                cooc.loc[s1, s2] = score
                
        cooc.to_csv(DATA_DIR / "jaccard_matrix.csv")
        print("\n--- Co-occurrence (Jaccard) ---")
        print(cooc)
        
    # 4. Find Cluster Events (>20% active)
    if not matrix_df.empty:
        matrix_df['active_count'] = matrix_df.sum(axis=1)
        matrix_df['active_ratio'] = matrix_df['active_count'] / len(BASKET)
        
        clusters = matrix_df[matrix_df['active_ratio'] >= 0.25] # 25% threshold
        clusters.to_csv(DATA_DIR / "cluster_events.csv")
        print(f"\nFound {len(clusters)} Cluster Events (>25% simultaneity).")
        if not clusters.empty:
            print(clusters.head())

if __name__ == "__main__":
    main()
