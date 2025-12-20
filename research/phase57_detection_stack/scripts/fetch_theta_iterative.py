import requests
import pandas as pd
import io
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Configuration
SYMBOL = 'GME'
BASE_URL = "http://127.0.0.1:25503/v3"
OUTPUT_DIR = Path("data/theta/raw")

# Dates
DATES_HIGH = ['20240513', '20240514', '20240515', '20240516', '20240517', '20240520']
DATES_LOW = ['20240104', '20240105', '20240108', '20240109', '20240110']
ALL_DATES = DATES_HIGH + DATES_LOW

def get_bulk_oi(date_str):
    """Fetches Bulk Open Interest for the date."""
    url = f"{BASE_URL}/option/history/open_interest"
    params = {
        'symbol': SYMBOL,
        'date': date_str,
        'expiration': '*',
        'strike': '*',
        'right': 'C' # Param is ignored/wildcarded by API for OI? 
                     # Actually user probe showed mixed C/P in response.
                     # So 'right' param might be ignored or treated as wildcard if not specified? 
                     # Or maybe we need to fetch P separately?
                     # Probe output showed "CALL" and "PUT" rows. So it returns both.
                     # I'll pass 'C' just to satisfy param requirement if any.
    }
    
    # Try fetching
    print(f"[{date_str}] Fetching Bulk Open Interest...")
    r = request_with_retry(url, params, max_retries=3, timeout=60)
    
    if r and r.status_code == 200:

        # Save exact response
        outfile = OUTPUT_DIR / f"oi_{date_str}.csv"
        with open(outfile, 'wb') as f:
            f.write(r.content)
        print(f"  Saved {outfile} ({len(r.content)/1024:.1f} KB)")
        return True
    else:
        print(f"  Error fetching OI: {r.status_code if r else 'None'}")
        return False


def get_contracts(date_str):
    """Fetches list of contracts for the date."""
    url = f"{BASE_URL}/option/list/contracts/quote"
    params = {'symbol': SYMBOL, 'date': date_str}
    
    print(f"[{date_str}] Fetching Contract List...")
    r = request_with_retry(url, params, max_retries=3, timeout=60)
    
    if r and r.status_code == 200:

        # Parse CSV
        try:
            df = pd.read_csv(io.BytesIO(r.content))
            return df
        except Exception as e:
            print(f"  Error parsing Contracts: {e}")
            return None
    else:
         print(f"  Error fetching Contracts: {r.status_code if r else 'None'}")
         return None


# Global Session
session = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
session.mount('http://', adapter)

def request_with_retry(url, params, max_retries=5, timeout=10):
    """Makes a request with exponential backoff for rate limits."""
    delay = 0.5 # Start with 0.5s (Faster recovery)
    for i in range(max_retries):
        try:
            r = session.get(url, params=params, timeout=timeout)
            
            if r.status_code == 200:
                return r
            elif r.status_code in [429, 473, 503]:
                # Rate limited or server busy
                print(f"  [Rate Limit {r.status_code}] Sleeping {delay}s...", end='\r')
                time.sleep(delay)
                delay *= 2 # Exponential backoff
                continue
            elif r.status_code == 404:
                return r # Not found is final
            else:
                # Other error (500, 400), maybe retry?
                print(f"  [Error {r.status_code}] Retrying...", end='\r')
                time.sleep(delay)
                delay *= 1.5
                continue
                
        except requests.RequestException as e:
            print(f"  [Exception {e}] Retrying...", end='\r')
            time.sleep(delay)
            delay *= 1.5
            
    return None # Failed after retries

def fetch_iv_for_contract(date_str, row):
    """Fetches IV for a single contract and returns the LAST row (EOD)."""
    url = f"{BASE_URL}/option/history/greeks/implied_volatility"
    # Format expiration: YYYY-MM-DD
    
    right_short = 'C' if 'CALL' in str(row['right']).upper() else 'P'
    params = {
        'symbol': SYMBOL,
        'date': date_str,
        'expiration': row['expiration'],
        'strike': row['strike'],
        'right': right_short
    }
    
    # Removed preemptive sleep to maximize speed.
    # Relying on request_with_retry backoff if 473 is hit.
    
    r = request_with_retry(url, params, timeout=15)

    
    if r is None:
        return None
        
    if r.status_code != 200:
        if r.status_code != 404:
            print(f"ERR {r.status_code} ", end='')
        return None

    text = r.text
    if not text: return None
    
    # Fast parse
    lines = text.strip().split('\n')
    if len(lines) < 2: return None
    return lines[-1]



def process_date(date_str):
    # 1. Get OI
    if not get_bulk_oi(date_str):
        print("Skipping IV due to OI failure/skip.")
        # proceed anyway?
        pass

    # 2. Get Contracts
    df_contracts = get_contracts(date_str)
    if df_contracts is None or df_contracts.empty:
        print("  No contracts found.")
        return

    print(f"  Found {len(df_contracts)} contracts. Fetching IV (Optimized)...")
    
    # 3. Fetch IV (Threaded)
    iv_rows = []
    # Header from probe: symbol,expiration,strike,right,timestamp,bid,bid_implied_vol,midpoint,implied_vol,ask,ask_implied_vol,iv_error,underlying_timestamp,underlying_price
    # We will just save the raw CSV lines
    
    # We need to know the header to write the file properly
    # We'll assume the first successful fetch gives us the header
    success_count = 0
    header_str = "symbol,expiration,strike,right,timestamp,bid,bid_implied_vol,midpoint,implied_vol,ask,ask_implied_vol,iv_error,underlying_timestamp,underlying_price"
    
    success_count = 0
    header_str = "symbol,expiration,strike,right,timestamp,bid,bid_implied_vol,midpoint,implied_vol,ask,ask_implied_vol,iv_error,underlying_timestamp,underlying_price"
    
    out_file = OUTPUT_DIR / f"iv_{date_str}.csv"
    existing_keys = set()
    write_header = True
    
    # Check for existing progress
    if out_file.exists():
        try:
            # Read existing to find what's done
            # We just need exp, strike, right to identify. 
            # But the file format is CSV without clear primary key cols in strict order? 
            # Header: symbol,expiration,strike,right,...
            # We can scan the file.
            with open(out_file, 'r') as f:
                header = f.readline()
                if header.strip() == header_str:
                    write_header = False
                    for line in f:
                        parts = line.split(',')
                        if len(parts) > 4:
                            # "GME","2024...",2.5,"CALL"...
                            # exp is idx 1, strike idx 2, right idx 3.
                            # Standardize format for key
                            e_date = parts[1].replace('"', '')
                            strike = float(parts[2])
                            right = parts[3].replace('"', '')
                            existing_keys.add((e_date, strike, right))
            print(f"  Resuming {date_str}: Found {len(existing_keys)} fetched contracts.")
        except Exception as e:
            print(f"  Error reading existing file: {e}. Overwriting.")
            write_header = True
            existing_keys = set()

    # Filter contracts
    to_fetch = []
    skipped = 0
    for idx, row in df_contracts.iterrows():
        # Key match: e_date (YYYY-MM-DD), strike (float), right (CALL/PUT)
        k = (row['expiration'], float(row['strike']), row['right'])
        if k in existing_keys:
            skipped += 1
            success_count += 1
        else:
            to_fetch.append(row)
            
    if not to_fetch:
        print(f"  All contracts already fetched for {date_str}.")
        return

    print(f"  Fetching {len(to_fetch)} remaining contracts (Skipped {skipped})...")

    # Use max_workers=20 (Ludicrous Speed)
    # Pushing to the absolute limit. Backoff will handle 473s.
    
    with open(out_file, 'a') as f_out: # Append mode
        if write_header:
            f_out.write(header_str + "\n")
        
        with ThreadPoolExecutor(max_workers=20) as executor:

            # Submit only remaining
            futures = {executor.submit(fetch_iv_for_contract, date_str, row): row for row in to_fetch}
            
            completion_count = 0
            for future in as_completed(futures):
                res = future.result()
                completion_count += 1
                
                # Feedback every 50 to reduce I/O spam
                if completion_count % 50 == 0:
                     print(f"  [{completion_count}/{len(to_fetch)}] ...", end='\r')

                if res:
                    f_out.write(res + "\n")
                    f_out.flush() 
                    success_count += 1
                else:
                    # Failed
                    pass

                
    print(f"\n  Finished {date_str}. Total Valid: {success_count} / {len(df_contracts)}.")




def main():
    if not OUTPUT_DIR.exists():
        os.makedirs(OUTPUT_DIR)
        
    for d in ALL_DATES:
        process_date(d)

if __name__ == "__main__":
    main()
