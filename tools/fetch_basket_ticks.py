
import os
import argparse
import requests
import pandas as pd
from pathlib import Path
import time
from datetime import datetime

# Validated list from previous step
TARGETS = [
    "GROV", "LYFT", "SPY", "DJT", "IEP", "SIRI", "BYON", 
    "NVDA", "MSFT", "COST", "IHRT", "KOSS", "TSLA", "U", "CHWY", 
    "PLTR", "COKE", "AAPL", "KOPN"
]
CRYPTO = ["X:BTCUSD", "X:ETHUSD"]

API_KEY = os.environ.get("POLYGON_API_KEY")

def fetch_trades(symbol, date, limit=50000):
    """
    Fetch raw trades for LSB analysis.
    Uses Polygon v3/trades.
    """
    print(f"[{symbol}] Fetching trades for {date}...")
    
    # Polygon API expects 'BTC-USD' style for crypto sometimes, or 'X:BTCUSD'.
    # v3 trades/tickers usually takes X:BTCUSD for crypto.
    
    api_symbol = symbol
    
    url = f"https://api.polygon.io/v3/trades/{api_symbol}?timestamp={date}&limit={limit}&apiKey={API_KEY}"
    
    all_results = []
    
    try:
        # We will just fetch the first page/limit to keep it manageable for this sweep
        # Real deep dive would paginate.
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        results = data.get("results", [])
        if not results:
            print(f"[{symbol}] No trades found.")
            return None
            
        print(f"[{symbol}] Retrieved {len(results)} trades.")
        
        # Format for Deep Decode: needs timestamp in ms or us, and price.
        # Polygon v3 results: { "sip_timestamp": ns, "price": float, ... }
        
        rows = []
        for r in results:
            # sip_timestamp is nanoseconds. Convert to micros for compatibility with engine
            ts_us = int(r.get("sip_timestamp") or r.get("participant_timestamp") or 0) // 1000
            price = r.get("price")
            size = r.get("size")
            # Exchange ID is useful for deep decode filtering (EDGX=11/12 usually, but polygon maps differ)
            exchange = r.get("exchange") 
            
            rows.append({
                "timestamp_us": ts_us,
                "price": price,
                "size": size,
                "exchange": exchange,
                "symbol": symbol # Add symbol for combined CSVs
            })
            
        return pd.DataFrame(rows)
        
    except Exception as e:
        print(f"[{symbol}] Error: {e}")
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2024-05-13")
    parser.add_argument("--out-dir", default="data/basket_sweep")
    args = parser.parse_args()
    
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    combined_frames = []
    
    # Process Equities
    for sym in TARGETS:
        df = fetch_trades(sym, args.date)
        if df is not None:
            # Save individual
            df.to_csv(out_dir / f"{sym}_{args.date}.csv", index=False)
            combined_frames.append(df)
        time.sleep(0.2) # Rate limit respect
        
    # Process Crypto
    for sym in CRYPTO:
        # File system friendlier name
        safe_sym = sym.replace("X:", "")
        df = fetch_trades(sym, args.date)
        if df is not None:
            df.to_csv(out_dir / f"{safe_sym}_{args.date}.csv", index=False)
            combined_frames.append(df)
        time.sleep(0.2)

    if combined_frames:
        print("Merging all data...")
        master_df = pd.concat(combined_frames)
        master_df.sort_values("timestamp_us", inplace=True)
        master_path = out_dir / "basket_sweep_master.csv"
        master_df.to_csv(master_path, index=False)
        print(f"Saved master dataset to {master_path} ({len(master_df)} rows)")

if __name__ == "__main__":
    main()
