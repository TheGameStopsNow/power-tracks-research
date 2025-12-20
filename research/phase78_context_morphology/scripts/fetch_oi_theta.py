"""
Phase 78: Fetch Open Interest (OI) from ThetaData

This script:
1. Reads the list of burst dates from Phase 77 results.
2. Fetches EOD Open Interest for GME for a BROAD range of strikes ($10-$120).
3. Saves to `data/open_interest/gme_oi_{YYYYMMDD}.csv`.
"""

import requests
import pandas as pd
from pathlib import Path
import time
from io import StringIO
import sys

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
BURST_FILE = BASE_DIR / "research/phase77_greek_echo/output/burst_fingerprints_enhanced.csv"
OUTPUT_DIR = BASE_DIR / "research/phase78_context_morphology/data/open_interest"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

THETA_BASE_URL = "http://127.0.0.1:25503/v3"

def get_unique_dates():
    if not BURST_FILE.exists():
        print(f"Error: {BURST_FILE} not found.")
        return []
    
    df = pd.read_csv(BURST_FILE)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    dates = df['timestamp'].dt.strftime('%Y%m%d').unique().tolist()
    return sorted(dates)

def fetch_open_interest(symbol, expiration, strike, right, date):
    """
    Fetch Open Interest for a specific contract on a date.
    Likely endpoint: /option/history/open_interest
    """
    # Note: ThetaData usually provides EOD OHLCV + OI in one "eod" request or similar.
    # But let's try specific open_interest history.
    # If not available, we use /option/eod and extract OI.
    
    url = f"{THETA_BASE_URL}/option/eod" # Using EOD to get OI
    params = {
        "symbol": symbol,
        "expiration": expiration,
        "strike": f"{strike:.3f}",
        "right": right,
        "date": date,
        "type": "open_interest" # Some endpoints use type param or return all
    }
    
    # Actually, standard v3 might just be /option/eod returning a CSV with OI column
    # Let's try /option/eod first, standard request.
    params = {
        "symbol": symbol,
        "expiration": expiration,
        "strike": f"{strike:.3f}",
        "right": right,
        "date": date
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            print(f"Error {resp.status_code}: {resp.text}")
            return None
        
        # Parse
        df = pd.read_csv(StringIO(resp.text))
        if len(df) == 0:
            print("Empty CSV response")
            return None
        
        # Check columns
        if 'open_interest' in df.columns:
            return df['open_interest'].iloc[-1]
        elif 'oi' in df.columns:
            return df['oi'].iloc[-1]
        
        print(f"Columns found: {df.columns.tolist()}")
        return None
    except Exception as e:
        print(f"Exception: {e}")
        return None

def main():
    print("Fetching Open Interest for GEX Profiling...")
    dates = get_unique_dates()
    print(f"Targeting {len(dates)} dates.")
    
    # We need to know the EXPIRATIONS for each date to fetch the relevant chain.
    # GEX depends on ALL open expirations at that time.
    # This is hard: we don't know the full option chain structure for past dates easily without a chain listing endpoint.
    
    # Alternative strategy:
    # Use the /v3/list/expirations endpoint to find all expirations active on that date?
    # Or just fetch the specific expirations we already used in Phase 75 (weeklies).
    # BUT GEX requires the whole board (monthlies, LEAPS).
    
    # Compromise for MVP:
    # Only fetch the expiry relevant to the burst (which we have in the burst file).
    # GEX Profile is dominated by the near-term expiries anyway.
    # We will fetch strikes $10-$60 for the Burst's Expiration.
    
    burst_df = pd.read_csv(BURST_FILE)
    burst_df['timestamp'] = pd.to_datetime(burst_df['timestamp'], utc=True)
    burst_df['date'] = burst_df['timestamp'].dt.strftime('%Y%m%d')
    
    # Group by date to process optimally
    daily_groups = burst_df.groupby('date')
    
    strikes = range(10, 60, 1) # $10 to $59 steps of $1
    
    for date_str, group in daily_groups:
        output_file = OUTPUT_DIR / f"gme_oi_{date_str}.csv"
        if output_file.exists():
            print(f"Skipping {date_str}, already exists.")
            continue
            
        print(f"\nProcessing {date_str}...")
        
        # Find all expirations involved in bursts on this day
        # In reality, we want the whole board, but we'll approximate with the burst's expiry + neighbors?
        # Let's just use the expirations present in the burst file + maybe logic.
        # Actually, Phase 75 fetcher had a fixed 'expiration' per week.
        # We will reuse that logic or valid expirations found in burst file.
        # But wait, burst file doesn't list strictly the contract details, justaggregated flow?
        # Ah, burst file is aggregated. We don't have contract details per burst row directly unless we saved them.
        # We saved 'pct_0dte', 'pct_weekly' etc.
        
        # Let's use the mapping from fetch_opra_theta.py for consistency
        # Feb-Apr mappings
        exp_map = {
            "20240205": "20240209", "20240206": "20240209", "20240207": "20240209", "20240208": "20240209", "20240209": "20240209",
            "20240304": "20240308", "20240305": "20240308", "20240306": "20240308", "20240307": "20240308", "20240308": "20240308",
            "20240401": "20240405", "20240402": "20240405", "20240403": "20240405", "20240404": "20240405", "20240405": "20240405",
            # May 2024
            "20240513": "20240517", "20240514": "20240517", "20240515": "20240517", "20240516": "20240517", "20240517": "20240517",
            # Jan 2024
            "20240103": "20240112", "20240104": "20240112", "20240105": "20240112", "20240108": "20240112", "20240109": "20240112", "20240110": "20240112"
        }
        
        expiry = exp_map.get(date_str)
        if not expiry:
            print(f"  No expiry mapping for {date_str}, skipping.")
            continue
            
        print(f"  Target Expiry: {expiry}")
        
        records = []
        for strike in strikes:
            for right in ['C', 'P']:
                # Fetch Calls
                oi = fetch_open_interest("GME", expiry, strike, right, date_str)
                if oi is not None:
                    records.append({
                        'date': date_str,
                        'expiration': expiry,
                        'strike': strike,
                        'right': right,
                        'open_interest': oi
                    })
                    sys.stdout.write(".")
                    sys.stdout.flush()
                time.sleep(0.02) # Rate limit
        
        if records:
            df_oi = pd.DataFrame(records)
            df_oi.to_csv(output_file, index=False)
            print(f"\n  Saved {len(df_oi)} OI records.")
        else:
            print(f"\n  No data found.")

if __name__ == "__main__":
    main()
