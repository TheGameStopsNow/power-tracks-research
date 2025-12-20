"""
Phase 81: Fetch Universe Bars (TSLA, AMD)

Fetch minute bars from Polygon for the Universe Generality Test.
Period: Feb 5-9, 2024.
"""

import requests
import pandas as pd
import time
from pathlib import Path
import os
import datetime

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
BARS_DIR_TSLA = BASE_DIR / "research/phase81_precision/data/bars/TSLA"
BARS_DIR_AMD = BASE_DIR / "research/phase81_precision/data/bars/AMD"
BARS_DIR_TSLA.mkdir(parents=True, exist_ok=True)
BARS_DIR_AMD.mkdir(parents=True, exist_ok=True)

POLYGON_KEY = os.environ.get("POLYGON_API_KEY")

def fetch_bars(ticker, output_dir):
    print(f"Fetching Polygon Bars for {ticker}...")
    
    # Dates: Feb 5-12 (cover T+2 days roughly)
    dates = [
        "2024-02-05", "2024-02-06", "2024-02-07", "2024-02-08", "2024-02-09",
        "2024-02-12", "2024-02-13" # Next week for returns
    ]
    
    for dt in dates:
        print(f"  {dt}...", end=" ", flush=True)
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/minute/{dt}/{dt}"
        params = {
            "adjusted": "true",
            "sort": "asc",
            "limit": 50000,
            "apiKey": POLYGON_KEY
        }
        
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            
            if data.get("resultsCount", 0) > 0:
                df = pd.DataFrame(data["results"])
                # Columns: v, vw, o, c, h, l, t, n
                df = df.rename(columns={
                    "v": "volume", "o": "open", "c": "close", "h": "high", "l": "low", "t": "timestamp"
                })
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
                
                out_file = output_dir / f"{ticker}_{dt.replace('-','')}_minute.csv"
                df.to_csv(out_file, index=False)
                print(f"Saved {len(df)} bars.")
            else:
                print("No data.")
                
        except Exception as e:
            print(f"Error: {e}")
            
        time.sleep(0.5) # Rate limit safety

def main():
    if not POLYGON_KEY:
        print("Error: POLYGON_API_KEY not set.")
        return

    fetch_bars("TSLA", BARS_DIR_TSLA)
    fetch_bars("AMD", BARS_DIR_AMD)

if __name__ == "__main__":
    main()
