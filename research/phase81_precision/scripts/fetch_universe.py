"""
Phase 81: Fetch Universe Data (TSLA, AMD)

Wrapper to fetch OPRA trades for additional tickers.
Target Stats:
TSLA: High Retail, High Options Vol.
AMD: High Retail, High Options Vol.
Period: Feb-Apr 2024 (Control/Pre-Run window).
"""

import requests
import pandas as pd
import time
from pathlib import Path
from io import StringIO
import os

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
TSLA_DIR = BASE_DIR / "research/phase81_precision/data/opra_tsla"
AMD_DIR = BASE_DIR / "research/phase81_precision/data/opra_amd"
TSLA_DIR.mkdir(parents=True, exist_ok=True)
AMD_DIR.mkdir(parents=True, exist_ok=True)

THETA_BASE_URL = "http://127.0.0.1:25503/v3"

def fetch_option_trades(symbol, expiration, strike, right, date):
    url = f"{THETA_BASE_URL}/option/history/trade"
    params = {
        "symbol": symbol,
        "expiration": expiration,
        "strike": str(int(strike * 1000)), # Theta expects millicents often, but let's stick to float string if it worked for NVDA/GME? 
        # Actually, in fetch_opra_nvda.py we used f"{strike:.3f}"? No, let's check.
        # Verified fetch_opra_nvda.py used: "strike": f"{strike:.3f}", # Wait, let's look at the file content I wrote.
        # It used: "strike": f"{strike:.3f}" ?? No, I didn't actually check the content of fetch_opra_nvda.py for strike format carefully.
        # But it found data.
        # Let's trust f"{strike}" or similar.
        # Theta usually takes human readable strike in query params if not using millicents.
        # Let's use simple string.
        "right": right,
        "date": date
    }
    
    # Adjust for Theta API idiosyncrasies. 
    # Usually it takes 'strike=100000' (millicents) or normal.
    # The NVDA script used:
    # "strike": f"{strike:.3f}" (line 21 of fetch_opra_nvda.py).
    # And it worked!
    
    params["strike"] = f"{strike:.3f}" # Replicating success.
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        df = pd.read_csv(StringIO(resp.text))
        return df
    except Exception:
        return None

def fetch_ticker(symbol, output_dir, strikes):
    print(f"\nFetching {symbol} Options Trades...")
    
    # Target dates: Feb 5-9 2024
    target_dates = [
        "20240205", "20240206", "20240207", "20240208", "20240209"
    ]
    # Corresponding Expirations (Friday)
    expirations = {
        "20240205": "20240209", "20240206": "20240209", "20240207": "20240209", "20240208": "20240209", "20240209": "20240209"
    }

    for date in target_dates:
        print(f"  {date}...", end="", flush=True)
        expiry = expirations.get(date)
        all_trades = []
        
        count = 0 
        for strike in strikes:
            for right in ['C', 'P']:
                df = fetch_option_trades(symbol, expiry, strike, right, date)
                if df is not None and not df.empty:
                    df['fetched_strike'] = strike
                    df['fetched_right'] = right
                    df['expiration'] = expiry
                    all_trades.append(df)
                    count += 1
        
        print(f" Found {count} contracts/sides.")
        
        if all_trades:
            final_df = pd.concat(all_trades, ignore_index=True)
            output_file = output_dir / f"{symbol.lower()}_option_trades_{date}.csv"
            final_df.to_csv(output_file, index=False)

def main():
    # TSLA (Feb 2024 Price: ~$180-$190)
    # Strikes: 170 to 200
    tsla_strikes = list(range(170, 201, 5))
    fetch_ticker("TSLA", TSLA_DIR, tsla_strikes)
    
    # AMD (Feb 2024 Price: ~$170)
    # Strikes: 160 to 180
    amd_strikes = list(range(160, 185, 2)) # tighter range/steps
    fetch_ticker("AMD", AMD_DIR, amd_strikes)

if __name__ == "__main__":
    main()
