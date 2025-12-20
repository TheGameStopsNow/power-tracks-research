import requests
import pandas as pd
import os
from pathlib import Path
import time

API_KEY = 'XphynICZWIks2AQP95uaFbJnomi1gS7u'
SYMBOL = 'GME'

# Target Dates (Control: Jan 2024 - likely lower gamma than May 2024 peak)
# Jan 4, 5, 8, 9, 10 (2024)
DATES = ['2024-01-04', '2024-01-05', '2024-01-08', '2024-01-09', '2024-01-10']

BASE_DIR = Path(__file__).resolve().parent.parent.parent

def fetch_day(date):
    print(f"Fetching {date}...")
    
    # Setup Output
    sample_dir = BASE_DIR / f"data/samples/sample_{date}/raw_ticks"
    if not sample_dir.exists():
        os.makedirs(sample_dir)
        
    output_file = sample_dir / f"GME_{date}_trades.csv"
    if output_file.exists():
        print(f"  File exists: {output_file}. Skipping.")
        return

    url = f"https://api.polygon.io/v2/ticks/stocks/trades/{SYMBOL}/{date}"
    params = {
        'apiKey': API_KEY,
        'limit': 50000,
        'order': 'asc'
    }
    
    all_trades = []
    next_url = None
    
    # First Call
    try:
        r = requests.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        
        if 'results' in data:
            all_trades.extend(data['results'])
            
        if 'next_url' in data:
            next_url = data['next_url']
            
    except Exception as e:
        print(f"  Error fetching init: {e}")
        return

    # Pagination Loop
    page_count = 1
    while next_url:
        print(f"  Fetching page {page_count} ({len(all_trades)} trades so far)...", end='\r')
        try:
            # next_url already has params? Polygon usually includes them.
            # But we need to append apiKey if it's not in next_url
            if 'apiKey' not in next_url:
                 next_url += f"&apiKey={API_KEY}"
                 
            r = requests.get(next_url)
            r.raise_for_status()
            data = r.json()
            
            if 'results' in data:
                all_trades.extend(data['results'])
                
            next_url = data.get('next_url')
            page_count += 1
            
            # Rate limit guard (5 calls/min is free tier, assuming paid tier here?)
            # User said "download using api key", assumed valid.
            # Just in case, tiny sleep.
            time.sleep(0.1)
            
        except Exception as e:
            print(f"  Error fetching page {page_count}: {e}")
            break
            
    print(f"  Freq Complete. Total Trades: {len(all_trades)}")
    
    # Save
    if all_trades:
        df = pd.DataFrame(all_trades)
        # Rename cols to match existing format: timestamp, price, volume...
        # Polygon: t (ns), p, s, x, c, i, ...
        # My scripts expect: timestamp, price, volume
        
        # Convert T to datetime
        df['timestamp'] = pd.to_datetime(df['t'], unit='ns')
        df['price'] = df['p']
        df['volume'] = df['s']
        
        # Keep relevant
        save_df = df[['timestamp', 'price', 'volume', 't', 'x', 'c']]
        save_df.to_csv(output_file, index=False)
        print(f"  Saved to {output_file}")
    else:
        print("  No trades found.")

def main():
    for d in DATES:
        fetch_day(d)
        
if __name__ == "__main__":
    main()
