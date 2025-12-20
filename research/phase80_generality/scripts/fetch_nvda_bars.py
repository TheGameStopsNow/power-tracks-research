"""
Phase 80: Fetch NVDA Minute Bars (Generality Test)

Fetches minute-level OHLCV for NVDA for Feb-Apr 2024.
Used to compute Greeks for option trades.
"""

import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import time
from io import StringIO

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
OUTPUT_DIR = BASE_DIR / "research/phase80_generality/data/bars"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

THETA_BASE_URL = "http://127.0.0.1:25503/v3"

def fetch_bars(symbol, date):
    url = f"{THETA_BASE_URL}/hist/stock/quote" # Or /hist/stock/trade? Quote gives NBBO. Trade gives executed.
    # We used /bar for GME.
    # Check what Phase 75 used: It fetched Quotes and aggregated? No, it used Polygon actually.
    # But here we are 100% Theta.
    # Theta /v3/hist/stock/bar is presumably available?
    # Let's try /v3/hist/stock/ohlc
    
    # Actually, previous phases used POLYGON for bars?
    # Let's check `fetch_opra_theta.py`... no that was for options ticks.
    # `expanded_bars` folder has GME_..._minute.csv.
    # Let's check where they came from. `fetch_bar_data.py` likely.
    # If Theta doesn't have easy bars, I'll use Polygon API if key is available.
    # The summary says Polygon API is available.
    
    # Let's try Theta first (free, local).
    url = f"{THETA_BASE_URL}/hist/stock/ohlc"
    
    # Actually, let's just use Polygon for reliability if Theta bar endpoint is unknown.
    # But I prefer internal consistency.
    # Let's assume there is a fetch_bars_theta or similar I can adapt?
    pass

import os
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")

def fetch_polygon_bars(symbol, date_str):
    # date_str: YYYYMMDD
    # Polygon needs YYYY-MM-DD
    dt = datetime.strptime(date_str, "%Y%m%d")
    poly_date = dt.strftime("%Y-%m-%d")
    
    print(f"Fetching Polygon Bars for {poly_date}...")
    
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{poly_date}/{poly_date}"
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 50000,
        "apiKey": POLYGON_API_KEY
    }
    
    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        print(f"Error {resp.status_code}: {resp.text}")
        return None
        
    data = resp.json()
    if data['queryCount'] == 0 or 'results' not in data:
        print("No data.")
        return None
        
    df = pd.DataFrame(data['results'])
    # Rename cols: t -> timestamp, c -> close
    df['timestamp'] = pd.to_datetime(df['t'], unit='ms', utc=True)
    df['close'] = df['c']
    df['open'] = df['o']
    df['high'] = df['h']
    df['low'] = df['l']
    df['volume'] = df['v']
    
    return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

def main():
    print("Fetching NVDA Minute Bars (Feb-Apr 2024)")
    
    dates = [
        "20240205", "20240206", "20240207", "20240208", "20240209",
        "20240304", "20240305", "20240306", "20240307", "20240308",
        "20240401", "20240402", "20240403", "20240404", "20240405",
    ]
    
    for date in dates:
        df = fetch_polygon_bars("NVDA", date)
        if df is not None:
             out_file = OUTPUT_DIR / f"NVDA_{date}_minute.csv"
             df.to_csv(out_file, index=False)
             print(f"Saved {len(df)} bars to {out_file}")
        time.sleep(0.5)

if __name__ == "__main__":
    main()
