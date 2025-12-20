
import os
import requests
import pandas as pd
from pathlib import Path
import time
import datetime

# Full Ticker List
TARGETS = [
    "GME", "KOSS", "AMC", "BB", "EXPR", "PLTR", "TSLA", "CLOV", "OPEN", "TLRY", "SAVA", "WKHS",
    "AAPL", "MSFT", "AMZN", "GOOGL", "NVDA", "AMD", "INTC", "META", "NFLX",
    "SPY", "IWM", "QQQ"
]

API_KEY = os.environ.get("POLYGON_API_KEY")

def get_2025_trading_days():
    """Fetches all trading days in 2025 using SPY as reference."""
    print("Fetching 2025 trading days...")
    # From Jan 1 2025 to today (Dec 10 2025)
    url = f"https://api.polygon.io/v2/aggs/ticker/SPY/range/1/day/2025-01-01/2025-12-10?adjusted=true&sort=asc&limit=5000&apiKey={API_KEY}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if "results" not in data:
            return []
        
        dates = []
        for r in data["results"]:
            dt = datetime.datetime.fromtimestamp(r['t'] / 1000, datetime.timezone.utc)
            dates.append(dt.strftime("%Y-%m-%d"))
            
        print(f"Found {len(dates)} trading days in 2025")
        return sorted(dates)
        
    except Exception as e:
        print(f"Error fetching calendar: {e}")
        return []

def fetch_trades_for_date(symbol, date, out_dir):
    """Fetch raw trades for a full day."""
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
            
            time.sleep(0.1)

        if not all_results:
            print(f"[{symbol}] No trades found for {date}.")
            return None
            
        print(f"[{symbol}] Total retrieved: {len(all_results)} trades for {date}.")
        
        rows = []
        for r in all_results:
            ts_us = int(r.get("sip_timestamp") or r.get("participant_timestamp") or 0) // 1000
            
            rows.append({
                "timestamp_us": ts_us,
                "price": r.get("price"),
                "size": r.get("size"),
                "exchange": r.get("exchange"),
                "symbol": symbol
            })
            
        df = pd.DataFrame(rows)
        
        date_dir = out_dir / date
        date_dir.mkdir(parents=True, exist_ok=True)
        
        filename = date_dir / f"{symbol}.csv"
        df.to_csv(filename, index=False)
        print(f"[{symbol}] Saved to {filename}")
        return df
        
    except Exception as e:
        print(f"[{symbol}] Error fetching {date}: {e}")
        return None

def main():
    out_dir = Path("data/ticks")
    
    if not API_KEY:
        print("Error: POLYGON_API_KEY environment variable not set.")
        return

    dates_2025 = get_2025_trading_days()
    
    if not dates_2025:
        print("No 2025 dates found.")
        return

    print(f"Targeting {len(dates_2025)} dates in 2025 across {len(TARGETS)} tickers")
    print(f"Total expected files: {len(dates_2025) * len(TARGETS)}")

    for date in dates_2025:
        print(f"\n--- Processing Date: {date} ---")
        for sym in TARGETS:
            target_file = out_dir / date / f"{sym}.csv"
            if target_file.exists():
                print(f"[{sym}] Data for {date} already exists. Skipping.")
                continue
                
            fetch_trades_for_date(sym, date, out_dir)
            time.sleep(0.5)

if __name__ == "__main__":
    main()
