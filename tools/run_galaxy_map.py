
import os
import requests
import pandas as pd
import numpy as np
from pathlib import Path
import time
import random

# --- THE GALAXY UNIVERSE (~200 Symbols) ---

# 1. The Meme Complex (Ground Zero)
MEMES = ["GME", "AMC", "KOSS", "CHWY", "EXPR", "BBBY", "TLRY", "CLOV", "WISH", "SNDL", "BB", "NOK", "PLTR", "TSLA", "HOOD", "SOFI", "OPEN", "DKNG", "RIVN", "MARA", "COIN", "BYON", "MSTR", "RIOT", "HUT", "CVNA", "UPST", "AI", "SPCE", "NKLA"]

# 2. Tech / Mega Cap (The Stability Layer)
TECH = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AMD", "NFLX", "AVGO", "CSCO", "ORCL", "ADBE", "CRM", "INTC", "QCOM", "TXN", "IBM", "MU", "NOW", "UBER", "ABNB", "PANW", "SNOW", "SQ", "PYPL", "SHOP", "ZM", "CRWD", "NET", "DDOG"]

# 3. Finance (The Banking Layer)
FINANCE = ["JPM", "BAC", "WFC", "C", "GS", "MS", "BLK", "SCHW", "AXP", "V", "MA", "COF", "USB", "PNC", "TFC", "BK", "STT", "HIG", "ALL", "TRV", "CB", "MMC", "AON", "AJG", "SPGI", "MCO", "CME", "ICE", "NDAQ", "KKR"]

# 4. Consumer / Retail (The Real Economy)
CONSUMER = ["WMT", "TGT", "COST", "HD", "LOW", "MCD", "SBUX", "NKE", "LULU", "EXPE", "BKNG", "MAR", "HLT", "CMG", "DPZ", "YUM", "KO", "PEP", "PG", "CL", "K", "GIS", "MO", "PM", "EL", "TAP", "STZ", "MNST", "KHC", "TSN"]

# 5. Energy / Industrial (The Heavy Layer)
INDUSTRIAL = ["XOM", "CVX", "COP", "SLB", "EOG", "OXY", "MPC", "PSX", "VLO", "KMI", "WMB", "OKE", "GE", "HON", "CAT", "DE", "MMM", "ETN", "EMR", "ITW", "PH", "CMI", "PCAR", "D", "SO", "NEE", "DUK", "EXC", "AEP", "SRE"]

# 6. High Short Interest / Volatility / Random (The Vulnerability Layer)
SHORT_INT = ["CVNA", "UPST", "AFRM", "FUB", "OPEN", "LCID", "NKLA", "SPCE", "RIDE", "WKHS", "BLNK", "FCEL", "PLUG", "SUNW", "JKS", "DQ", "NIO", "XPEV", "LI", "BABA", "PDD", "JD", "BIDU", "TME", "IQ", "HTHT", "TAL", "EDU", "GOTU"]

# Combine and deduplicate
UNIVERSE = sorted(list(set(MEMES + TECH + FINANCE + CONSUMER + INDUSTRIAL + SHORT_INT)))

# --- DATES ---
WAR_WEEK = ["2024-05-13", "2024-05-14", "2024-05-15", "2024-05-16", "2024-05-17"]
PEACE_WEEK = ["2024-04-15", "2024-04-16", "2024-04-17", "2024-04-18", "2024-04-19"]

API_KEY = os.environ.get("POLYGON_API_KEY")
OUT_DIR = Path("research/phase16_galaxy/data")

def fetch_day(symbol, date):
    # Check cache
    path = OUT_DIR / f"{symbol}_{date}.csv"
    if path.exists(): return pd.read_csv(path)
    
    # Try basket sweep location
    sweep_path = Path(f"data/basket_sweep/{symbol}_{date}.csv")
    if sweep_path.exists(): 
        path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.read_csv(sweep_path)
        df.to_csv(path, index=False)
        return df
        
    # print(f"[{symbol}] Fetching {date}...")
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

def get_sector(sym):
    if sym in MEMES: return "Meme"
    if sym in TECH: return "Tech"
    if sym in FINANCE: return "Finance"
    if sym in CONSUMER: return "Consumer"
    if sym in INDUSTRIAL: return "Industrial"
    if sym in SHORT_INT: return "HighShort"
    return "Other"

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("\n--- Phase 16: The Galaxy Map ---")
    print(f"Universe: {len(UNIVERSE)} Symbols")
    print("Dates: War (May 13-17) vs Peace (Apr 15-19)")
    
    results = []
    
    for i, sym in enumerate(UNIVERSE):
        print(f"[{i+1}/{len(UNIVERSE)}] Processing {sym}...")
        
        # War
        war_densities = []
        for date in WAR_WEEK:
            df = fetch_day(sym, date)
            war_densities.append(analyze_density(df))
        avg_war = np.mean(war_densities) if war_densities else 0.0
        
        # Peace
        peace_densities = []
        for date in PEACE_WEEK:
            df = fetch_day(sym, date)
            peace_densities.append(analyze_density(df))
        avg_peace = np.mean(peace_densities) if peace_densities else 0.0
        
        diff = avg_war - avg_peace
        
        results.append({
            "symbol": sym,
            "sector": get_sector(sym),
            "war_density": avg_war,
            "peace_density": avg_peace,
            "diff": diff
        })
        
    # Export
    df_res = pd.DataFrame(results)
    df_res.to_csv(OUT_DIR / "galaxy_map.csv", index=False)
    print(f"Saved Galaxy Map to {OUT_DIR}/galaxy_map.csv")
    
    # Generate JSON for potential viz
    df_res.to_json(OUT_DIR / "galaxy_map.json", orient="records", indent=2)

if __name__ == "__main__":
    main()
