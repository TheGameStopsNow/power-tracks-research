
import os
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# --- SETTINGS ---
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

API_KEY = os.environ.get("POLYGON_API_KEY")
PROBE_DATE = "2024-05-14" # The "Loudest" Day
WORKERS = 10 # Parallel requests

def fetch_master_list():
    print("Fetching Master Ticker List...")
    tickers = []
    url = f"https://api.polygon.io/v3/reference/tickers?market=stocks&active=true&limit=1000&apiKey={API_KEY}"
    
    while url:
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
            results = data.get("results", [])
            for r in results:
                # Filter out obvious noise?
                # Keep it broad for now.
                tickers.append(r["ticker"])
                
            url = data.get("next_url")
            if url: url += f"&apiKey={API_KEY}"
            print(f"  Count: {len(tickers)}...")
            if len(tickers) > 8000: break # Safety cap
            
        except Exception as e:
            print(f"Error fetching tickers: {e}")
            break
            
    return tickers

def scan_symbol(symbol):
    url = f"https://api.polygon.io/v3/trades/{symbol}?timestamp={PROBE_DATE}&limit=50000&apiKey={API_KEY}"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        results = data.get("results", [])
        
        if not results: return symbol, 0, 0.0
        
        count = len(results)
        if count < 1000: return symbol, count, 0.0 # Ignore low liquidity noise (BLIAQ filter)
        
        prices = [r["price"] for r in results]
        lsbs = (np.floor(np.array(prices) * 100).astype(int) & 1)
        
        # Fast Opcode Check
        # We need bytes
        n_bytes = len(lsbs) // 8
        if n_bytes == 0: return symbol, count, 0.0
        
        valid_ops = 0
        ROSETTA = {0xA0, 0x98, 0x80, 0x10, 0x01, 0x02}
        
        # Optimize loop?
        # Construct bytes numerically
        lsbs = lsbs[:n_bytes*8] # Truncate
        bytes_val = np.packbits(lsbs.reshape(-1, 8), axis=1) # Incorrect usage of packbits typically gives 8-bit packed?
        # packbits logic differs. Manual shift is safer for consistency with previous scripts.
        
        # Manual shift (validated in Phase 20)
        # Reshape to (N, 8)
        arr = lsbs.reshape(-1, 8)
        # Dot product with powers of 2 
        # [128, 64, 32, 16, 8, 4, 2, 1]
        powers = np.array([128, 64, 32, 16, 8, 4, 2, 1])
        byte_values = arr.dot(powers)
        
        # Vectorized check
        valid_mask = np.isin(byte_values, list(ROSETTA))
        valid_ops = np.sum(valid_mask)
        
        density = valid_ops / n_bytes
        return symbol, count, density
        
    except Exception as e:
        return symbol, 0, 0.0

def main():
    print(f"--- Phase 24: Operation Dragnet ({PROBE_DATE}) ---")
    
    # 1. Get List
    # Cache it
    list_path = DATA_DIR / "master_ticker_list.csv"
    if list_path.exists():
        tickers = pd.read_csv(list_path)["ticker"].tolist()
        print(f"Loaded {len(tickers)} tickers from cache.")
    else:
        tickers = fetch_master_list()
        pd.DataFrame({"ticker": tickers}).to_csv(list_path, index=False)
    
    # Random Sample or Full?
    # Let's do a "Sector Sweep".
    # For speed in this demo, let's scan the first 1000.
    # User said "Without blowing up my computer".
    # 1000 symbols * 1 HTTP request ~ 1000 requests. 
    # With 10 threads -> 100 batches. ~1-2 minutes.
    
    scan_targets = tickers[:2000] # First 2000 alphabetical? Maybe randomize?
    # Shuffling to get a mix
    import random
    random.shuffle(tickers)
    scan_targets = tickers[:1000] # Random 1000 "Probe"
    
    print(f"Scanning {len(scan_targets)} random symbols...")
    
    results = []
    
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(scan_symbol, sym): sym for sym in scan_targets}
        
        completed = 0
        for future in as_completed(futures):
            completed += 1
            if completed % 50 == 0:
                print(f"Progress: {completed}/{len(scan_targets)}...")
            
            sym, count, dens = future.result()
            if dens > 0.02: # Log anything > 2% density
                results.append({"symbol": sym, "count": count, "density": dens})
                
    # Save Rank
    df = pd.DataFrame(results).sort_values("density", ascending=False)
    df.to_csv(DATA_DIR / "dragnet_results.csv", index=False)
    
    print("\n--- Top Discoveries ---")
    print(df.head(20))

if __name__ == "__main__":
    main()
