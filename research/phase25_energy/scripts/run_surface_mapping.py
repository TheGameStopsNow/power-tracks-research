
import os
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import matplotlib.pyplot as plt

# --- SETTINGS ---
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUT_DIR = BASE_DIR / "charts"
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

API_KEY = os.environ.get("POLYGON_API_KEY")
DATE_RANGE = ["2024-05-13", "2024-05-14", "2024-05-15", "2024-05-16", "2024-05-17"]

# Combined Targets: Core + Top 20 Sleepers from Dragnet
CORE = ["GME", "AMC", "KOSS", "BB", "SPY"]
# Top 20 from Phase 24 findings (hardcoded for stability)
SLEEPERS = [
    "LEN.B", "AMAL", "ALUR", "CNTB", "DJTWW",
    "MPU", "CMPX", "FLGC", "JAKK", "AXGN", 
    "MEGL", "BNS", "HOWL", "KELYA", "NCDL", 
    "GIC", "IAGG", "ORN", "ALNT", "QCLN"
]
ALL_TARGETS = list(set(CORE + SLEEPERS))

def fetch_and_calculate_bins(symbol, date, bin_window='15min'):
    local_path = DATA_DIR / f"{symbol}_{date}.csv"
    if local_path.exists():
        df = pd.read_csv(local_path)
    else:
        # Fetch logic (omitted for brevity, usage of existing cache assumed)
        # If missing, we skip or fetch (fetch logic same as before)
        # For this re-run, we assume data exists or we accept partials
        # Re-implementing fetch for robustness since we expanded list
        url = f"https://api.polygon.io/v3/trades/{symbol}?timestamp={date}&limit=50000&apiKey={API_KEY}"
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
            results = data.get("results", [])
            if not results: return []
            rows = [{"ts": r.get("sip_timestamp") or r.get("participant_timestamp"), "price": r["price"]} for r in results]
            df = pd.DataFrame(rows)
            df.to_csv(local_path, index=False)
        except: return []

    if df.empty: return []

    # Parse TS
    df['ts'] = pd.to_numeric(df['ts'], errors='coerce')
    df['dt'] = pd.to_datetime(df['ts'], unit='ns', errors='coerce')
    if df['dt'].isnull().all():
         df['dt'] = pd.to_datetime(df['ts'], unit='us', errors='coerce')
    if df['dt'].isnull().all():
         df['dt'] = pd.to_datetime(df['ts'], unit='ms', errors='coerce')
    
    df = df.dropna(subset=['dt'])
    
    # Resample Logic
    # Set index
    df = df.set_index('dt')
    
    # We need Opcode Density per BIN
    # Custom resampler?
    # Efficient: Iterate bins? Or groupby TimeGrouper?
    
    results = []
    # Resample into bins
    grouper = df.groupby(pd.Grouper(freq=bin_window))
    
    for time_key, group in grouper:
        if group.empty:
            dens = 0.0
        else:
            prices = group['price'].values
            lsbs = (np.floor(prices * 100).astype(int) & 1)
            n_bytes = len(lsbs) // 8
            if n_bytes == 0:
                dens = 0.0
            else:
                arr = lsbs[:n_bytes*8].reshape(-1, 8)
                powers = np.array([128, 64, 32, 16, 8, 4, 2, 1])
                vals = arr.dot(powers)
                ROSETTA = {0xA0, 0x98, 0x80, 0x10, 0x01, 0x02}
                dens = np.sum(np.isin(vals, list(ROSETTA))) / n_bytes
        
        results.append({
            "symbol": symbol,
            "timestamp": time_key,
            "density": dens
        })
        
    return results

def main():
    print("--- Phase 25b: High-Res Flow (15min) ---")
    all_data = []
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for sym in ALL_TARGETS:
            for date in DATE_RANGE:
                futures.append(executor.submit(fetch_and_calculate_bins, sym, date, '15min'))
                
        completed = 0
        for f in as_completed(futures):
            res = f.result()
            if res: all_data.extend(res)
            completed += 1
            if completed % 20 == 0: print(f"Processed {completed}...")
            
    df = pd.DataFrame(all_data)
    df.to_csv(DATA_DIR / "energy_surface_15m.csv", index=False)
    
    # Generate 15m Chart
    generate_stacked_area(df)

def generate_stacked_area(df):
    if df.empty: return
    
    pivot = df.pivot_table(index='timestamp', columns='symbol', values='density', fill_value=0)
    pivot = pivot.sort_index()
    
    # Sort
    cols = list(pivot.columns)
    priority = ["GME", "AMC", "KOSS", "LEN.B", "AMAL"]
    cols.sort(key=lambda x: priority.index(x) if x in priority else 99)
    pivot = pivot[cols]
    
    plt.figure(figsize=(20, 10)) # Wider for high res
    plt.stackplot(pivot.index, pivot.T, labels=pivot.columns, alpha=0.8)
    
    plt.title("High-Res Energy Surface (15min Resolution)", fontsize=16)
    plt.ylabel("Cumulative Density")
    plt.xlabel("Date/Time")
    
    plt.legend(loc='upper left', bbox_to_anchor=(1, 1), ncol=2) # 2 cols for many stocks
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "energy_surface_15m.png")
    print(f"Saved {OUT_DIR}/energy_surface_15m.png")

if __name__ == "__main__":
    main()
