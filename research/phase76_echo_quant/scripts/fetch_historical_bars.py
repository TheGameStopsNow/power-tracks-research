"""
Fetch Historical Minute Bars from Polygon (2021-2022)

This script fetches GME minute bars for the missing 2021-2022 period.
"""

import os
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import time
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
OUTPUT_DIR = BASE_DIR / "research/phase76_echo_quant/data/bars"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")
BASE_URL = "https://api.polygon.io"

def fetch_bars_for_date(symbol, date_str):
    """Fetch minute bars for a single date."""
    url = f"{BASE_URL}/v2/aggs/ticker/{symbol}/range/1/minute/{date_str}/{date_str}"
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 50000,
        "apiKey": POLYGON_API_KEY
    }
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("results"):
                return data["results"]
        return []
    except Exception as e:
        print(f"  Error fetching {date_str}: {e}")
        return []

def main():
    if not POLYGON_API_KEY:
        print("ERROR: POLYGON_API_KEY not found")
        return
        
    print(f"Polygon API Key: {POLYGON_API_KEY[:8]}...")
    
    symbol = "GME"
    
    # Date ranges to fetch
    # 2021: Full year (includes Jan squeeze)
    # 2022: Full year
    start_date = datetime(2021, 1, 1)
    end_date = datetime(2022, 12, 31)
    
    current = start_date
    total_fetched = 0
    
    print(f"\nFetching {symbol} minute bars from {start_date.date()} to {end_date.date()}...")
    
    while current <= end_date:
        date_str = current.strftime("%Y-%m-%d")
        output_file = OUTPUT_DIR / f"GME_{date_str}_minute.csv"
        
        # Skip weekends
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue
            
        # Skip if file already exists
        if output_file.exists():
            current += timedelta(days=1)
            continue
        
        bars = fetch_bars_for_date(symbol, date_str)
        
        if bars:
            df = pd.DataFrame(bars)
            # Rename columns to match existing format
            df = df.rename(columns={
                'v': 'volume',
                'vw': 'vw',
                'o': 'open',
                'c': 'close',
                'h': 'high',
                'l': 'low',
                't': 'timestamp_ms',
                'n': 'transactions'
            })
            
            # Convert timestamp
            df['timestamp'] = pd.to_datetime(df['timestamp_ms'], unit='ms')
            df['symbol'] = symbol
            df['date'] = date_str
            
            # Save
            df.to_csv(output_file, index=False)
            total_fetched += 1
            
            if total_fetched % 20 == 0:
                print(f"  Fetched {total_fetched} days... (currently at {date_str})")
        
        # Rate limit: Polygon free tier is 5 calls/min
        time.sleep(0.25)
        current += timedelta(days=1)
    
    print(f"\n--- Complete ---")
    print(f"Total days fetched: {total_fetched}")

if __name__ == "__main__":
    main()
