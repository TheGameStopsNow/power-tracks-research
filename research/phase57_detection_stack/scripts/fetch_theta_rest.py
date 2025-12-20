import requests
import pandas as pd
import os
from pathlib import Path
import time

# Configuration
SYMBOL_ROOT = 'GME'
# Terminal told us strictly /v3/
BASE_URL = "http://127.0.0.1:25503/v3" 
BASE_DIR = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = BASE_DIR / "data/raw/data/options_library/GME/flat_files_import"

# Dates to Fetch (YYYYMMDD)
# May 2024 (High Gamma Event)
DATES_HIGH = ['20240513', '20240514', '20240515', '20240516', '20240517', '20240520']
# Jan 2024 (Control)
DATES_LOW = ['20240104', '20240105', '20240108', '20240109', '20240110']

ALL_DATES = DATES_HIGH + DATES_LOW

def fetch_greeks_snapshot(date_str):
    """
    Fetches End-of-Day Option Greeks/OI Snapshot via V3 Bulk Endpoint.
    """
    print(f"Fetching Snapshot for {date_str}...")
    
    # Research says hist/bulk_hist combined.
    # Try /v3/hist/option/greeks with root-only params (implicit bulk?)
    url = f"{BASE_URL}/hist/option/greeks"
    
    # Needs date? Snapshots are usually current. 
    # Historical Snapshot usually requires `date` or `timestamp`.
    # Let's hope it accepts start_date/end_date like history.
    # If not, we fall back to /v3/hist/option/greeks (non-bulk) loop? No, too slow.
    
    # Let's try sticking to documented params but new endpoint.
    
    # Param: use_csv=true to get CSV directly?
    params = {
        'symbol': SYMBOL_ROOT, # Changed from root
        'start_date': date_str,
        'end_date': date_str,
        'expiration': 0, # Changed from exp
        'right': 'C',
        'interval': 0, # Changed from ivl
        'format': 'csv' # Changed from use_csv, value csv
    }
    
    # Try Calls
    try:
        r = requests.get(url, params=params)
        if r.status_code == 400 or r.status_code == 422:
             print("  V3 Param Error, retrying with 'root'...")
             # Maybe default param check
             pass
        r.raise_for_status()
        
        # Save Calls
        out_c = OUTPUT_DIR / f"options_{date_str}_C.csv"
        with open(out_c, 'wb') as f:
            f.write(r.content)
        print(f"  Saved Calls: {out_c}")
        
    except Exception as e:
        print(f"  Error Fetching Calls: {e}")
        # Debug response text if available
        try: print(r.text) 
        except: pass

    # Try Puts
    try:
        params['right'] = 'P'
        r = requests.get(url, params=params)
        r.raise_for_status()
        
        out_p = OUTPUT_DIR / f"options_{date_str}_P.csv"
        with open(out_p, 'wb') as f:
            f.write(r.content)
        print(f"  Saved Puts: {out_p}")
        
    except Exception as e:
        print(f"  Error Fetching Puts: {e}")


def main():
    if not OUTPUT_DIR.exists():
        os.makedirs(OUTPUT_DIR)
        
    print("Connecting to Theta Terminal V3...")
    # Test Connection
    try:
        # /v3/list/roots/option ? 
        # Error said: use v3 format.
        test_url = f"{BASE_URL}/list/roots/option?root={SYMBOL_ROOT}"
        r = requests.get(test_url)
        print(f"Test Status: {r.status_code}")
        if r.status_code != 200:
             print(f"Response: {r.text}")
             # If root param deprecated, try ?symbol=GME
             test_url_2 = f"{BASE_URL}/list/roots/option?symbol={SYMBOL_ROOT}"
             r2 = requests.get(test_url_2)
             if r2.status_code == 200:
                 print("  Success using ?symbol=")
             
    except Exception as e:
        print(f"Connection Failed: {e}")
        return

    # Run Fetch
    for d in ALL_DATES:
        fetch_greeks_snapshot(d)

if __name__ == "__main__":
    main()
