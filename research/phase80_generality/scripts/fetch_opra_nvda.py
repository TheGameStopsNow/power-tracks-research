"""
Phase 80: Fetch NVDA OPRA Data (Generality Test)

This script fetches historical NVDA options trades for Feb-Apr 2024.
Assumes data is SPLIT-ADJUSTED (NVDA split 10:1 in June 2024).
Target Price Range: ~$60 - $95 (equivalent to pre-split $600-$950).
"""

import requests
import pandas as pd
import time
from pathlib import Path
from io import StringIO

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
OUTPUT_DIR = BASE_DIR / "research/phase80_generality/data/opra"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

THETA_BASE_URL = "http://127.0.0.1:25503/v3"

def fetch_option_trades(symbol, expiration, strike, right, date):
    url = f"{THETA_BASE_URL}/option/history/trade"
    params = {
        "symbol": symbol,
        "expiration": expiration,
        "strike": f"{strike:.3f}", # Millicents? No, float format usually works
        "right": right,
        "date": date
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        df = pd.read_csv(StringIO(resp.text))
        return df
    except Exception:
        return None

def main():
    print("Fetching NVDA Options Trades (Feb-Apr 2024)...")
    
    # Target dates: Same windows as GME Control to be comparable
    # Feb 5-9, Mar 4-8, Apr 1-5
    target_dates = [
        "20240205", "20240206", "20240207", "20240208", "20240209",
        "20240304", "20240305", "20240306", "20240307", "20240308",
        "20240401", "20240402", "20240403", "20240404", "20240405",
    ]
    
    expirations = {
        "20240205": "20240209", "20240206": "20240209", "20240207": "20240209", "20240208": "20240209", "20240209": "20240209",
        "20240304": "20240308", "20240305": "20240308", "20240306": "20240308", "20240307": "20240308", "20240308": "20240308",
        "20240401": "20240405", "20240402": "20240405", "20240403": "20240405", "20240404": "20240405", "20240405": "20240405",
    }
    
    # Strikes: Pre-Split Raw Values were ~$600-$900 in Feb-Apr 2024
    # Range 600 to 1000, step 5 or 10
    strikes = list(range(600, 1000, 10)) # Steps of 10 to cover range efficiently
    print(f"Targeting Strikes: {strikes[0]} - {strikes[-1]}")
    
    for date in target_dates:
        print(f"\nProcessing {date}...")
        expiry = expirations.get(date)
        all_trades = []
        
        for strike in strikes:
            for right in ['C', 'P']:
                df = fetch_option_trades("NVDA", expiry, strike, right, date)
                if df is not None and len(df) > 0:
                    df['fetched_strike'] = strike
                    df['fetched_right'] = right
                    df['expiration'] = expiry # Ensure this column exists
                    all_trades.append(df)
                    # print(f"  ${strike} {right}: {len(df)}") # specific print commented out to reduce noise
        
        if all_trades:
            final_df = pd.concat(all_trades, ignore_index=True)
            output_file = OUTPUT_DIR / f"nvda_option_trades_{date}.csv"
            final_df.to_csv(output_file, index=False)
            print(f"  Saved {len(final_df)} NVDA trades to {output_file}")
        else:
            print(f"  No trades found for {date} (Strikes {strikes[0]}-{strikes[-1]})")

if __name__ == "__main__":
    main()
