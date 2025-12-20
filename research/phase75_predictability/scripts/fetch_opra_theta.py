"""
Fetch OPRA Options Tick Data from ThetaData (Local Terminal)

This script fetches historical options trades for GME via the local Theta Terminal.
"""

import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import time
from io import StringIO

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = BASE_DIR / "data/opra_ticks"
OUTPUT_DIR.mkdir(exist_ok=True)

THETA_BASE_URL = "http://127.0.0.1:25503/v3"

def fetch_option_trades(symbol, expiration, strike, right, date):
    """
    Fetch trades for a specific option contract on a date.
    ThetaData endpoint: /option/history/trade
    """
    url = f"{THETA_BASE_URL}/option/history/trade"
    params = {
        "symbol": symbol,
        "expiration": expiration,
        "strike": f"{strike:.3f}",
        "right": right,
        "date": date
    }
    
    try:
        resp = requests.get(url, params=params, timeout=60)
        if resp.status_code != 200:
            print(f"  Error {resp.status_code}: {resp.text[:100]}")
            return None
            
        # Parse CSV response
        df = pd.read_csv(StringIO(resp.text))
        return df
    except Exception as e:
        print(f"  Exception: {e}")
        return None

def main():
    print("ThetaData OPRA Options Trade Fetcher")
    print("=" * 40)
    
    # Target parameters - Extended date range for larger sample
    symbol = "GME"
    
    # Multiple weeks across 2024 for diversity
    target_dates = [
        # Feb 2024
        "20240205", "20240206", "20240207", "20240208", "20240209",
        # Mar 2024
        "20240304", "20240305", "20240306", "20240307", "20240308",
        # Apr 2024
        "20240401", "20240402", "20240403", "20240404", "20240405",
    ]
    
    # Corresponding weekly expirations
    expirations = {
        "20240205": "20240209", "20240206": "20240209", "20240207": "20240209", 
        "20240208": "20240209", "20240209": "20240209",
        "20240304": "20240308", "20240305": "20240308", "20240306": "20240308",
        "20240307": "20240308", "20240308": "20240308",
        "20240401": "20240405", "20240402": "20240405", "20240403": "20240405",
        "20240404": "20240405", "20240405": "20240405",
    }
    
    # ATM strikes for early 2024 ($12-25 range)
    strikes = [12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]
    
    for target_date in target_dates:
        print(f"\n{'='*50}")
        print(f"Fetching options trades for {symbol} on {target_date}...")
        
        # Use the WEEKLY expiry from lookup table
        expiration = expirations.get(target_date, target_date)
        
        all_trades = []
        
        for strike in strikes:
            for right in ["call", "put"]:
                df = fetch_option_trades(symbol, expiration, strike, right, target_date)
                if df is not None and len(df) > 0:
                    df['fetched_strike'] = strike
                    df['fetched_right'] = right
                    df['date'] = target_date
                    all_trades.append(df)
                    print(f"  ${strike} {right.upper()}: {len(df)} trades")
                time.sleep(0.05)  # Rate limit courtesy
                
        if not all_trades:
            print(f"  No trades found for {target_date}.")
            continue
            
        df_all = pd.concat(all_trades, ignore_index=True)
        df_all['timestamp'] = pd.to_datetime(df_all['timestamp'], format='mixed', utc=True)
        df_all = df_all.sort_values('timestamp')
        
        output_path = OUTPUT_DIR / f"gme_option_trades_{target_date}.csv"
        df_all.to_csv(output_path, index=False)
        
        print(f"  Saved {len(df_all)} trades to {output_path}")
        
    print(f"\n{'='*50}")
    print("All dates complete!")

if __name__ == "__main__":
    main()

