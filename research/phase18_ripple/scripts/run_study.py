
import os
import requests
import pandas as pd
import numpy as np
from pathlib import Path
import time

# --- THE STRATEGIC UNIVERSE (52 Symbols) ---
# Derived from Phase 16/17 findings to test "Source vs Sink" dynamics.

# 1. The Activators (High Variance during War)
ACTIVATORS = ["KOSS", "GME", "SLE", "CLOV", "OPEN", "COF", "AJG", "BB", "FUBO", "AMC", "COIN", "BYON", "MARA"]

# 2. The Deactivated (Negative Variance - Potential Liquidity Sources)
DEACTIVATED = ["KOPN", "FCEL", "CVNA", "NVDA", "BK", "DPZ", "EXC", "ETN", "WMB"]

# 3. The Pillars (The "Blanket" - High Stability)
PILLARS = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "JPM", "BAC", "XOM", "CVX", "WMT", "KO", "PEP", "MCD", "PG"]

# 4. User Interest / Anomalies
ANOMALIES = ["WORK", "BLIAQ", "SPY", "VIX", "U", "CHWY", "SIRI", "PLTR", "UBER", "LYFT", "HOOD", "RIVN", "DKNG", "SOFI"]

UNIVERSE = sorted(list(set(ACTIVATORS + DEACTIVATED + PILLARS + ANOMALIES)))

# --- TIMELINE (5 Weeks) ---
# April 29 - May 31, 2024
# Week -2: Apr 29 - May 3
# Week -1: May 6 - May 10
# Week  0: May 13 - May 17 (The Event)
# Week +1: May 20 - May 24
# Week +2: May 27 - May 31

DATES = [
    # W-2
    "2024-04-29", "2024-04-30", "2024-05-01", "2024-05-02", "2024-05-03",
    # W-1
    "2024-05-06", "2024-05-07", "2024-05-08", "2024-05-09", "2024-05-10",
    # W0 (Event)
    "2024-05-13", "2024-05-14", "2024-05-15", "2024-05-16", "2024-05-17",
    # W+1
    "2024-05-20", "2024-05-21", "2024-05-22", "2024-05-23", "2024-05-24",
    # W+2
    "2024-05-27", "2024-05-28", "2024-05-29", "2024-05-30", "2024-05-31"
]

# ... (Imports remain the same)

# Use paths relative to this script
# Use paths relative to this script
API_KEY = os.getenv("POLYGON_API_KEY")
BASE_DIR = Path(__file__).parent
OUT_DIR = BASE_DIR / "data"

# ... (rest of code)

def fetch_day(symbol, date):
    path = OUT_DIR / f"{symbol}_{date}.csv"
    if path.exists(): return pd.read_csv(path)
    
    # Try cache from previous phases (Relative to Project Root, need to handle this carefully)
    # Assuming script is run from project root, OR we can climb up.
    # Let's try to resolve project root dynamically or rely on relative "../"
    
    project_root = BASE_DIR.parent.parent
    prev_dirs = [
        project_root / "phase17_targeted/data",
        project_root / "phase16_galaxy/data",
        project_root / "phase15_atlas/data",
        project_root / "data/basket_sweep" # This might be outside research folder depending on structure
    ]
    # Fallback to CWD relative if above fails (heuristic)
    if not prev_dirs[0].exists():
         prev_dirs = [
             Path("research/phase17_targeted/data"),
             Path("research/phase16_galaxy/data"),
             Path("research/phase15_atlas/data"),
             Path("data/basket_sweep")
         ]
    for d in prev_dirs:
        cache_p = d / f"{symbol}_{date}.csv"
        if cache_p.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            df = pd.read_csv(cache_p)
            df.to_csv(path, index=False)
            return df

    # Fetch
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
    lsbs = (np.floor(df["price"] * 100).astype(int) & 1).values
    n_bytes = len(lsbs) // 8
    
    valid_ops = 0
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
    
    print("\n--- Phase 18: The Ripple Effect ---")
    print(f"Universe: {len(UNIVERSE)} Symbols")
    print(f"Timeline: {len(DATES)} Days (Apr 29 - May 31)")
    
    # Data Structure: { Date: { Symbol: Density } }
    timeline_data = {d: {} for d in DATES}
    
    for i, sym in enumerate(UNIVERSE):
        print(f"[{i+1}/{len(UNIVERSE)}] Scanning {sym}...")
        for date in DATES:
            if not API_KEY:
                print("API_KEY not found. Skipping fetch.")
                continue
            try:
                df = fetch_day(sym, date)
            except Exception as e:
                print(f"Failed to fetch {sym} {date}: {e}")
                continue
            dens = analyze_density(df)
            timeline_data[date][sym] = dens
            
    # Export Matrix
    df_matrix = pd.DataFrame.from_dict(timeline_data, orient='index')
    df_matrix.index.name = 'date'
    df_matrix.to_csv(OUT_DIR / "daily_density_matrix.csv")
    print(f"Saved Density Matrix to {OUT_DIR}/daily_density_matrix.csv")
    
    # --- ANALYSIS ---
    # 1. Total System Energy
    df_matrix['SYSTEM_TOTAL'] = df_matrix.sum(axis=1)
    
    # 2. Correlation Analysis targeting Negative Correlation with KOSS/GME
    targets = ["KOSS", "GME", "SLE"]
    correlations = {}
    
    for t in targets:
        if t not in df_matrix.columns: continue
        correlations[t] = {}
        for col in df_matrix.columns:
            if col == 'SYSTEM_TOTAL' or col == t: continue
            # Simple Pearson
            corr = df_matrix[t].corr(df_matrix[col])
            correlations[t][col] = corr
            
    # Export Correlations
    corr_rows = []
    for t, counterparts in correlations.items():
        for c, val in counterparts.items():
            corr_rows.append({"Target": t, "Counterpart": c, "Correlation": val})
            
    df_corr = pd.DataFrame(corr_rows)
    df_corr.to_csv(OUT_DIR / "ripple_correlations.csv", index=False)
    
    # Print Top Anti-Correlated pairs
    print("\n--- Top Anti-Correlations (Counter-Weights) ---")
    neg_corr = df_corr.sort_values("Correlation", ascending=True).head(10)
    print(neg_corr)

if __name__ == "__main__":
    main()
