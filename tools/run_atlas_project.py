
import os
import argparse
import requests
import pandas as pd
import numpy as np
from pathlib import Path
import time
from collections import Counter

# --- THE ATLAS UNIVERSE (52 Symbols) ---
# Ground Zero
BASKET_MEME = ["GME", "AMC", "KOSS", "CHWY", "EXPR", "BBBY"]
# Meme Adjacent / High Vol
BASKET_ADJ = ["PLTR", "TSLA", "HOOD", "SOFI", "OPEN", "DKNG", "RIVN", "MARA", "COIN", "BYON"]
# Mega Cap (Control)
BASKET_MEGA = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AMD", "NFLX"]
# Legacy (Control)
BASKET_LEGACY = ["KO", "PEP", "WMT", "TGT", "JPM", "BAC", "XOM", "CVX", "F", "GM", "GE", "T", "VZ", "DIS", "CMCSA"]
# Micro / Random
BASKET_MICRO = ["GROV", "KOPN", "U", "IHRT", "DJT", "IEP", "SIRI", "LYFT", "COKE"]

# Combine
UNIVERSE = sorted(list(set(BASKET_MEME + BASKET_ADJ + BASKET_MEGA + BASKET_LEGACY + BASKET_MICRO)))

# --- DATES ---
WAR_WEEK = ["2024-05-13", "2024-05-14", "2024-05-15", "2024-05-16", "2024-05-17"]
PEACE_WEEK = ["2024-04-15", "2024-04-16", "2024-04-17", "2024-04-18", "2024-04-19"]

API_KEY = os.environ.get("POLYGON_API_KEY")
OUT_DIR = Path("research/phase15_atlas/data")

def fetch_day(symbol, date):
    # Check cache
    path = OUT_DIR / f"{symbol}_{date}.csv"
    if path.exists(): return pd.read_csv(path)
    
    # Try basket sweep location
    sweep_path = Path(f"data/basket_sweep/{symbol}_{date}.csv")
    if sweep_path.exists(): 
        # Cache it here too
        df = pd.read_csv(sweep_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        return df
        
    print(f"[{symbol}] Fetching {date}...")
    url = f"https://api.polygon.io/v3/trades/{symbol}?timestamp={date}&limit=50000&apiKey={API_KEY}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200: return None
        data = resp.json()
        results = data.get("results", [])
        if not results: return None
        
        rows = []
        for r in results:
            ts_us = int(r.get("sip_timestamp") or r.get("participant_timestamp") or 0) // 1000
            price = r.get("price")
            rows.append({"timestamp_us": ts_us, "price": price})
            
        df = pd.DataFrame(rows)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        return df
    except:
        return None

def analyze_density(df):
    if df is None or df.empty: return 0.0
    # Approx Opcode Density
    lsbs = (np.floor(df["price"] * 100).astype(int) & 1).values
    n_bytes = len(lsbs) // 8
    
    valid_ops = 0
    # Rosetta Opcodes
    ROSETTA = {0xA0, 0x98, 0x80, 0x10, 0x01, 0x02}
    
    for i in range(n_bytes):
        byte_val = 0
        for b in range(8):
            byte_val |= (lsbs[i*8 + b] << (7-b))
        if byte_val in ROSETTA:
            valid_ops += 1
            
    return valid_ops / n_bytes if n_bytes > 0 else 0.0

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("\n--- Phase 15: The Atlas Project ---")
    print(f"Universe: {len(UNIVERSE)} Symbols")
    print("Dates: War (May 13-17) vs Peace (Apr 15-19)")
    
    results = []
    
    for sym in UNIVERSE:
        # 1. Analyze War Week
        war_densities = []
        for date in WAR_WEEK:
            df = fetch_day(sym, date)
            d = analyze_density(df)
            war_densities.append(d)
            
        avg_war = np.mean(war_densities) if war_densities else 0.0
        
        # 2. Analyze Peace Week
        peace_densities = []
        for date in PEACE_WEEK:
            df = fetch_day(sym, date)
            d = analyze_density(df)
            peace_densities.append(d)
        
        avg_peace = np.mean(peace_densities) if peace_densities else 0.0
        
        # 3. Diff
        diff = avg_war - avg_peace
        
        print(f"[{sym}] War={avg_war:.1%}, Peace={avg_peace:.1%}, Diff={diff:+.1%}")
        
        results.append({
            "symbol": sym,
            "war_density": avg_war,
            "peace_density": avg_peace,
            "diff": diff
        })
        
    # Export
    df_res = pd.DataFrame(results)
    df_res.to_csv(OUT_DIR / "atlas_results.csv", index=False)
    print(f"Saved Atlas results to {OUT_DIR}/atlas_results.csv")

if __name__ == "__main__":
    main()
