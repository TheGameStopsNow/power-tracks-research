
import requests
import pandas as pd
from pathlib import Path
import os
import sys

from dotenv import load_dotenv

# Load env vars
load_dotenv()

# Constants
API_KEY = os.environ.get("POLYGON_API_KEY")
BASE_URL = "https://api.polygon.io/v3/trades"
PHASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PHASE_DIR / "real_ticks"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TARGETS = [
    ("GME", "2021-03-08"), # 7-4-1 Signal Day
    ("GME", "2021-01-28"), # Sneeze Peak
    ("GME", "2021-02-24")  # Another Volatility Spike Day
]

def fetch_real_trades(ticker, date):
    print(f"Fetching REAL TRADES for {ticker} on {date}...")
    
    # Polygon Trades Endpoint (v3)
    # limit=50000 per page
    all_trades = []
    url = f"{BASE_URL}/{ticker}?timestamp={date}&limit=50000&apiKey={API_KEY}"
    
    while url:
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            results = data.get("results", [])
            print(f"  Got {len(results)} trades...")
            all_trades.extend(results)
            
            # Pagination
            url = data.get("next_url")
            if url:
                url += f"&apiKey={API_KEY}"
                
            # Safety limit for demo (don't download GBs if huge)
            if len(all_trades) > 500000:
                print("  Hit safety limit (500k trades). Stopping fetch.")
                break
                
        except Exception as e:
            print(f"  Error: {e}")
            break
            
    if not all_trades:
        print("  No trades found.")
        return

    # Convert to DF
    # Polygon results: { 'sip_timestamp': ..., 'price': ..., 'size': ..., ... }
    df = pd.DataFrame(all_trades)
    
    # Rename for compatibility
    # sip_timestamp is nanoseconds
    df['timestamp'] = pd.to_datetime(df['sip_timestamp'], unit='ns')
    df = df.rename(columns={'price': 'price', 'size': 'size'})
    df['source'] = 'polygon_real_trades'
    
    # Select cols
    cols = ['timestamp', 'price', 'size', 'exchange', 'conditions', 'source']
    # Filter available cols
    df = df[[c for c in cols if c in df.columns]]
    
    out_file = OUTPUT_DIR / f"{ticker}_{date}_real_trades.csv"
    df.to_csv(out_file, index=False)
    print(f"Saved {len(df)} REAL TRADES to {out_file}")

if __name__ == "__main__":
    if not API_KEY:
        print("Error: POLYGON_API_KEY not set.")
        sys.exit(1)
        
    for ticker, date in TARGETS:
        fetch_real_trades(ticker, date)
