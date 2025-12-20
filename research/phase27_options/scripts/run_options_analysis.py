
import os
import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

from dotenv import load_dotenv

# Setup
load_dotenv()
PHASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PHASE_DIR / "data"
OUT_DIR = PHASE_DIR / "output"
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)
API_KEY = os.environ.get("POLYGON_API_KEY")

# Inputs
# Inputs
# Assuming standard structure research/phaseXX/data
REPO_ROOT = PHASE_DIR.parent.parent
PHASE_25_DATA = PHASE_DIR.parent / "phase25_energy/data/energy_surface_15m.csv"

def analyze_cycles():
    print("--- 1. Energy Return Cycle Analysis ---")
    if not PHASE_25_DATA.exists():
        print("Phase 25 data missing.")
        return
        
    try:
        df = pd.read_csv(PHASE_25_DATA)
    except Exception as e:
        print(f"Failed to read Phase 25 data: {e}")
        return
    pivot = df.pivot_table(index='timestamp', columns='symbol', values='density', fill_value=0)
    
    # Analyze Piston A (GME)
    gme_series = pivot['GME']
    
    # Autocorrelation
    # Lags up to 40 step (10 hours)
    lags = range(1, 41)
    autocorr = [gme_series.autocorr(lag=l) for l in lags]
    
    # Find peak negative (max drain) and peak positive (return)
    peak_lag = np.argmax(autocorr) + 1
    # Actually we want the first *negative* peak (drain) then return?
    # Or just periodicity.
    
    plt.figure(figsize=(10, 5))
    plt.bar(lags, autocorr, color='purple')
    plt.axhline(0, color='black', linewidth=0.5)
    plt.title("Energy Return Cycle: GME Density Autocorrelation (15m Lags)")
    plt.xlabel("Lag (15-min Steps)")
    plt.ylabel("Correlation")
    plt.grid(True, alpha=0.3)
    plt.savefig(OUT_DIR / "energy_return_cycle.png")
    print(f"Saved {OUT_DIR}/energy_return_cycle.png")

import json

def load_gme_tick_data():
    date = "2024-05-14"
    symbol = "GME"
    # Use path from manifest (folder containing trades.json)
    json_path = DATA_DIR / f"{symbol}_{date}" / "trades.json"
    
    if json_path.exists():
        with open(json_path, 'r') as f:
            data = json.load(f)
        if isinstance(data, dict) and 'results' in data:
            return pd.DataFrame(data['results'])
        return pd.DataFrame()
    
    print(f"Warning: Data file {json_path} not found. Run download_data.py first.")
    # Fallback to CSV if it exists (legacy)
    csv_path = DATA_DIR / f"{symbol}_{date}.csv"
    if csv_path.exists():
        return pd.read_csv(csv_path)

    return pd.DataFrame()

def analyze_strike_gravity(df):
    if df.empty: return
    print("--- 3. Strike Gravity Test ---")
    
    # Logic:
    # 1. Calculate Opcode Density for each tick (LSB)
    # 2. Calculate Distance to Nearest $1.00 Strike
    # 3. Bin by Distance -> plot Avg Density
    
    prices = df['price'].values
    lsbs = (np.floor(prices * 100).astype(int) & 1)
    
    # Check if Opcode (Rolling window or just static check? Static check is hard per tick)
    # Let's verify per-tick LSB is "part of a sequence"?
    # Alternatively: Just check if *high density minutes* correlate with *strike proximity*.
    # Let's do Tick-Level grouping.
    
    # Distance to nearest integer dollar (e.g. 29.00, 30.00)
    # GME was around $30-$60 this week. Strikes likely $1 or $0.5 intervals.
    # Let's assume $1.00 strikes.
    dist_to_strike = np.abs(prices - np.round(prices))
    
    # Create DF
    # We can't know if a SINGLE tick is an Opcode (it takes 8).
    # Heuristic: Check density of "LSB=1" vs "LSB=0"? No.
    # Group by Price Cent?
    
    # Better approach:
    # 1. Group ticks into 1-sec or smaller bins.
    # 2. Calc Density of bin.
    # 3. Calc Avg Price of bin.
    # 4. Correlate.
    
    # Mocking bins by chunking array
    chunk_size = 100
    n_chunks = len(prices) // chunk_size
    
    results = []
    
    for i in range(n_chunks):
        chunk_prices = prices[i*chunk_size : (i+1)*chunk_size]
        chunk_lsbs = lsbs[i*chunk_size : (i+1)*chunk_size]
        
        # Calc Density
        n_bytes = chunk_size // 8
        arr = chunk_lsbs[:n_bytes*8].reshape(-1, 8)
        powers = np.array([128, 64, 32, 16, 8, 4, 2, 1])
        vals = arr.dot(powers)
        ROSETTA = {0xA0, 0x98, 0x80, 0x10, 0x01, 0x02}
        dens = np.sum(np.isin(vals, list(ROSETTA))) / n_bytes
        
        avg_price = np.mean(chunk_prices)
        dist = np.abs(avg_price - np.round(avg_price))
        
        results.append({"density": dens, "dist": dist, "price": avg_price})
        
    res_df = pd.DataFrame(results)
    
    # Bin by Distance (0.00 to 0.50)
    res_df['dist_bin'] = pd.cut(res_df['dist'], bins=10)
    gravity = res_df.groupby('dist_bin')['density'].mean()
    
    plt.figure(figsize=(10, 6))
    gravity.plot(kind='bar', color='crimson')
    plt.title("Strike Gravity: Opcode Density vs Distance to Nearest $1 Strike")
    plt.xlabel("Distance to Strike ($)")
    plt.ylabel("Avg Opcode Density")
    plt.xticks(rotation=45)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "strike_gravity.png")
    print(f"Saved {OUT_DIR}/strike_gravity.png")

def main():
    analyze_cycles()
    df = load_gme_tick_data()
    analyze_strike_gravity(df)

if __name__ == "__main__":
    main()
