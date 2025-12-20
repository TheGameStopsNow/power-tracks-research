"""
Fetch OPRA Options Tick Data from Polygon.io

This script fetches historical options trades for GME for the May 2024 period.
It constructs the Net Delta Flow series needed for Hayashi-Yoshida lead-lag analysis.
"""

import os
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
OUTPUT_DIR = BASE_DIR / "research/phase75_predictability/data/opra_ticks"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

def get_options_contracts(symbol, date_str, expiry_gte, expiry_lte):
    """
    Get list of option contracts for a symbol on a given date.
    """
    url = f"https://api.polygon.io/v3/reference/options/contracts"
    params = {
        "underlying_ticker": symbol,
        "expiration_date.gte": expiry_gte,
        "expiration_date.lte": expiry_lte,
        "limit": 250,
        "apiKey": POLYGON_API_KEY
    }
    
    resp = requests.get(url, params=params, timeout=30)
    if resp.status_code != 200:
        print(f"Error fetching contracts: {resp.status_code} - {resp.text[:200]}")
        return []
        
    data = resp.json()
    return data.get("results", [])

def fetch_option_trades(ticker, date_str):
    """
    Fetch all trades for a specific option contract on a date.
    ticker: OPRA symbol like 'O:GME240517C00030000'
    """
    url = f"https://api.polygon.io/v3/trades/{ticker}"
    params = {
        "timestamp.gte": f"{date_str}T04:00:00Z",  # Pre-market
        "timestamp.lte": f"{date_str}T23:59:59Z",
        "limit": 50000,
        "apiKey": POLYGON_API_KEY
    }
    
    all_trades = []
    
    while True:
        resp = requests.get(url, params=params, timeout=60)
        if resp.status_code != 200:
            print(f"  Error fetching trades for {ticker}: {resp.status_code}")
            break
            
        data = resp.json()
        results = data.get("results", [])
        all_trades.extend(results)
        
        # Pagination
        next_url = data.get("next_url")
        if not next_url:
            break
        url = next_url
        params = {"apiKey": POLYGON_API_KEY}
        
    return all_trades

def main():
    if not POLYGON_API_KEY:
        print("ERROR: POLYGON_API_KEY not found in environment.")
        print("Please set it in .env file.")
        return
        
    print(f"Polygon API Key: {POLYGON_API_KEY[:8]}...")
    
    symbol = "GME"
    target_date = "2024-05-17"  # High Activity Day
    expiry_gte = "2024-05-17"
    expiry_lte = "2024-05-24"  # Weekly options
    
    print(f"\n1. Fetching option contracts for {symbol} expiring {expiry_gte} to {expiry_lte}...")
    contracts = get_options_contracts(symbol, target_date, expiry_gte, expiry_lte)
    print(f"   Found {len(contracts)} contracts.")
    
    if not contracts:
        print("No contracts found. Exiting.")
        return
        
    # Focus on ATM calls (strike near $30 based on May 2024 price range)
    atm_strikes = [25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35]
    target_contracts = [c for c in contracts if c.get("strike_price") in atm_strikes and c.get("contract_type") == "call"]
    print(f"   Filtered to {len(target_contracts)} ATM call contracts.")
    
    all_trades = []
    
    print(f"\n2. Fetching trades for {target_date}...")
    for i, contract in enumerate(target_contracts[:10]):  # Limit to 10 contracts for speed
        ticker = contract["ticker"]
        strike = contract["strike_price"]
        
        trades = fetch_option_trades(ticker, target_date)
        print(f"   [{i+1}/{min(len(target_contracts), 10)}] {ticker} (Strike ${strike}): {len(trades)} trades")
        
        for t in trades:
            all_trades.append({
                "timestamp": t.get("sip_timestamp") or t.get("participant_timestamp"),
                "price": t.get("price"),
                "size": t.get("size"),
                "strike": strike,
                "ticker": ticker,
                "conditions": t.get("conditions", [])
            })
            
    if not all_trades:
        print("\nNo trades found. Polygon may not have OPRA tick data for your subscription tier.")
        return
        
    df = pd.DataFrame(all_trades)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ns', utc=True)
    df = df.sort_values('timestamp')
    
    output_path = OUTPUT_DIR / f"gme_option_trades_{target_date}.csv"
    df.to_csv(output_path, index=False)
    print(f"\nSaved {len(df)} trades to {output_path}")
    
    # Summary
    print(f"\n--- Summary ---")
    print(f"Total Trades: {len(df)}")
    print(f"Time Range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"Strikes: {sorted(df['strike'].unique())}")

if __name__ == "__main__":
    main()
