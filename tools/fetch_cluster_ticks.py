
import os
import argparse
import requests
import pandas as pd
from pathlib import Path
import time
from datetime import datetime


import random
import datetime

# Extended Ticker List (Basket + Tech + ETF)
TARGETS = [
    # The "Cluster"
    "GME", "KOSS", "AMC", "BB", "EXPR", "PLTR", "TSLA", "CLOV", "OPEN", "TLRY", "SAVA", "WKHS",
    # Tech / Control
    "AAPL", "MSFT", "AMZN", "GOOGL", "NVDA", "AMD", "INTC", "META", "NFLX",
    # Market / VIX
    "SPY", "IWM", "QQQ", "VXX"
]

# Fixed Key Dates
FIXED_DATES = ["2021-01-28", "2021-03-08", "2024-05-13", "2024-05-14"]

def get_trading_days(year, limit=25):
    """
    Fetches trading days for a year by checking SPY aggregates.
    Returns a random sample of 'limit' days.
    """
    print(f"Fetching valid trading days for {year}...")
    url = f"https://api.polygon.io/v2/aggs/ticker/SPY/range/1/day/{year}-01-01/{year}-12-31?adjusted=true&sort=asc&limit=5000&apiKey={API_KEY}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if "results" not in data:
            return []
        
        # Extract dates (YYYY-MM-DD)
        # Polygon aggs result 't' is unix ms
        dates = []
        for r in data["results"]:
            dt = datetime.datetime.fromtimestamp(r['t'] / 1000, datetime.timezone.utc)
            dates.append(dt.strftime("%Y-%m-%d"))
            
        if not dates:
            return []
            
        # Sample
        if len(dates) > limit:
            return sorted(random.sample(dates, limit))
        return dates
        
    except Exception as e:
        print(f"Error fetching calendar for {year}: {e}")
        return []

def get_target_dates():
    """Generates the master list of dates to fetch."""
    all_dates = set(FIXED_DATES)
    
    # 25 days per year for 4 years = 100 random days
    years = [2021, 2022, 2023, 2024]
    for y in years:
        random_days = get_trading_days(y, limit=25)
        all_dates.update(random_days)
    
    return sorted(list(all_dates))

# Global override for DATES to use the generator


API_KEY = os.environ.get("POLYGON_API_KEY")

def fetch_trades_for_date(symbol, date, out_dir):
    """
    Fetch raw trades for a full day.
    Uses Polygon v3/trades with pagination.
    """
    print(f"[{symbol}] Fetching trades for {date}...")
    
    url = f"https://api.polygon.io/v3/trades/{symbol}?timestamp={date}&limit=50000&apiKey={API_KEY}"
    
    all_results = []
    next_url = url
    
    try:
        page_count = 0
        while next_url:
            resp = requests.get(next_url, timeout=15)
            if resp.status_code == 429:
                print("Rate limit hit. Sleeping 60s...")
                time.sleep(60)
                continue
                
            resp.raise_for_status()
            data = resp.json()
            
            results = data.get("results", [])
            if results:
                all_results.extend(results)
                
            next_url = data.get("next_url")
            if next_url:
                next_url += f"&apiKey={API_KEY}"
                
            page_count += 1
            if page_count % 5 == 0:
                print(f"[{symbol}] ... fetched {len(all_results)} trades so far (Page {page_count})")
            
            # Simple rate limiting protection
            time.sleep(0.1)

        if not all_results:
            print(f"[{symbol}] No trades found for {date}.")
            return None
            
        print(f"[{symbol}] Total retrieved: {len(all_results)} trades for {date}.")
        
        rows = []
        for r in all_results:
            # sip_timestamp is nanoseconds. Convert to micros
            ts_us = int(r.get("sip_timestamp") or r.get("participant_timestamp") or 0) // 1000
            
            rows.append({
                "timestamp_us": ts_us,
                "price": r.get("price"),
                "size": r.get("size"),
                "exchange": r.get("exchange"),
                "symbol": symbol
            })
            
        df = pd.DataFrame(rows)
        
        # Ensure directory exists for this date
        date_dir = out_dir / date
        date_dir.mkdir(parents=True, exist_ok=True)
        
        # Save
        filename = date_dir / f"{symbol}.csv"
        df.to_csv(filename, index=False)
        print(f"[{symbol}] Saved to {filename}")
        return df
        
    except Exception as e:
        print(f"[{symbol}] Error fetching {date}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="data/ticks", help="Base output directory")
    args = parser.parse_args()
    
    out_dir = Path(args.out_dir)
    
    if not API_KEY:
        print("Error: POLYGON_API_KEY environment variable not set.")
        return

    # Generate full date list
    all_dates = get_target_dates()
    print(f"Targeting {len(all_dates)} total dates across {len(TARGETS)} tickers.")
    print(f"Total expected files: {len(all_dates) * len(TARGETS)}")

    for date in all_dates:
        print(f"\n--- Processing Date: {date} ---")
        for sym in TARGETS:
            # Check if already exists to skip
            target_file = out_dir / date / f"{sym}.csv"
            if target_file.exists():
                print(f"[{sym}] Data for {date} already exists. Skipping.")
                continue
                
            fetch_trades_for_date(sym, date, out_dir)
            time.sleep(0.5) # Courtesy sleep between tickers

if __name__ == "__main__":
    main()
