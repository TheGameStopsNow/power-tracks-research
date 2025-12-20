
import os
import argparse
import requests
import pandas as pd
import numpy as np
from pathlib import Path
import time
from scipy.signal import correlate, periodogram
import matplotlib.pyplot as plt

# Configuration
SYMBOLS = ["GME", "SPY", "AAPL", "GROV"]
DATES = ["2024-05-13", "2024-05-14", "2024-05-15", "2024-05-16", "2024-05-17"]
API_KEY = os.environ.get("POLYGON_API_KEY")
OUT_DIR = Path("research/phase13_temporal/data")

def fetch_day(symbol, date):
    path = OUT_DIR / f"{symbol}_{date}.csv"
    if path.exists():
        print(f"[{symbol}] Skipping {date}, already exists.")
        return pd.read_csv(path)
    
    print(f"[{symbol}] Fetching {date}...")
    url = f"https://api.polygon.io/v3/trades/{symbol}?timestamp={date}&limit=50000&apiKey={API_KEY}"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results: return None
        
        rows = []
        for r in results:
            ts_us = int(r.get("sip_timestamp") or r.get("participant_timestamp") or 0) // 1000
            price = r.get("price")
            rows.append({"timestamp_us": ts_us, "price": price})
            
        df = pd.DataFrame(rows)
        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        return df
    except Exception as e:
        print(f"[{symbol}] Error: {e}")
        return None

def extract_opcodes(df):
    """Convert Price stream to Opcode Stream (Timestamp -> Opcode Name)"""
    if df is None or df.empty: return []
    df = df.sort_values("timestamp_us")
    
    # LSBs
    lsbs = (np.floor(df["price"] * 100).astype(int) & 1).values
    n_bytes = len(lsbs) // 8
    
    events = []
    # Opcode Mapping (Subset of interest)
    INTERESTING = {0xA0: "STORM", 0x98: "STORM", 0x80: "PEACE", 0x01: "LIFT"}
    
    for i in range(n_bytes):
        byte_val = 0
        for b in range(8):
            byte_val |= (lsbs[i*8 + b] << (7-b))
            
        if byte_val in INTERESTING:
            # Use timestamp of last bit
            ts = df.iloc[i*8 + 7]["timestamp_us"]
            events.append({"timestamp_us": ts, "type": INTERESTING[byte_val]})
            
    return pd.DataFrame(events)

def rasterize(events, start_ts, end_ts, resolution_ms=10):
    """Convert events to binary array [0, 0, 1, 0...]"""
    if events.empty: 
        size = int((end_ts - start_ts) / (resolution_ms * 1000))
        return np.zeros(size)
    
    # Align to grid
    events["grid_idx"] = ((events["timestamp_us"] - start_ts) / (resolution_ms * 1000)).astype(int)
    
    max_idx = int((end_ts - start_ts) / (resolution_ms * 1000))
    grid = np.zeros(max_idx + 1)
    
    # Mark hits
    # If multiple events in same bucket, still just 1 (presence)
    valid_indices = events[events["grid_idx"] < max_idx]["grid_idx"].unique()
    grid[valid_indices] = 1
    return grid

def analyze_day(date):
    print(f"\n--- Analyzing {date} ---")
    data_map = {}
    
    # 1. Load & Extract
    for sym in SYMBOLS:
        df = fetch_day(sym, date)
        ops = extract_opcodes(df)
        data_map[sym] = ops
        
    start_ts = min([df["timestamp_us"].min() for df in data_map.values() if not df.empty] or [0])
    end_ts = max([df["timestamp_us"].max() for df in data_map.values() if not df.empty] or [0])
    
    if start_ts == 0: return
    
    # 2. Rasterize (10ms buckets)
    # Why 10ms? HFT reaction time is ~1-10ms. 
    grids = {}
    for sym, ops in data_map.items():
        grids[sym] = rasterize(ops, start_ts, end_ts, resolution_ms=10)
        
    # 3. Correlation: SPY vs Others
    spy_grid = grids.get("SPY")
    if spy_grid is None: return
    
    results = []
    
    for target in ["GME", "GROV", "AAPL"]:
        target_grid = grids.get(target)
        if target_grid is None: continue
        
        # Cross Correlation
        # Using numpy correlate
        # Need to center?
        # Normalize
        # Simple Pearson on shifted arrays is better interpreting
        
        # Window: +/- 5 seconds (500 buckets)
        lags = np.arange(-500, 501)
        corrs = []
        
        for lag in lags:
            if lag < 0:
                s = spy_grid[:lag]
                t = target_grid[-lag:]
            elif lag > 0:
                s = spy_grid[lag:]
                t = target_grid[:-lag]
            else:
                s = spy_grid
                t = target_grid
                
            # Truncate to match length (overlapping part)
            # Actually numpy/scipy correlate is faster but let's be explicit
            # Binary correlation: Phi coefficient? Or just dot product?
            # Dot Product = Co-occurrence count
            if len(s) == 0: val = 0
            else: val = np.dot(s, t) # Co-firing count
            corrs.append(val)
            
        # Find Peak
        peak_idx = np.argmax(corrs)
        peak_lag = lags[peak_idx] * 10 # ms
        peak_val = corrs[peak_idx]
        
        print(f"SPY vs {target}: Peak Lag = {peak_lag}ms (Count={peak_val})")
        results.append({"target": target, "lag_ms": peak_lag, "co_occurrence": peak_val})
        
    # 4. Heartbeat (FFT on SPY)
    # fs = 100 Hz (10ms)
    fs = 100
    f, Pxx = periodogram(spy_grid, fs)
    # Find dominant freq
    top_idx = np.argmax(Pxx)
    print(f"SPY Dominant Freq: {f[top_idx]:.2f} Hz (Period: {1/f[top_idx]:.2f}s)")

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for date in DATES:
        analyze_day(date)

if __name__ == "__main__":
    main()
