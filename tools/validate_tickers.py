
import os
import requests
import time

API_KEY = os.environ.get("POLYGON_API_KEY")
DATE = "2024-05-13"

TICKERS = [
    "GROV", "LYFT", "SPY", "DJT", "IEP", "BBBY", "SIRI", "BYON", 
    "NVDA", "MSFT", "COST", "IHRT", "KOSS", "TSLA", "U", "CHWY", 
    "PLTR", "COKE", "AAPL", "WORK", "KOPN"
]

CRYPTO = ["BTC", "ETH"]

def check_ticker(ticker, prefix=""):
    symbol = f"{prefix}{ticker}"
    # Minimal fetch: 1 minute bar
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{DATE}/{DATE}?limit=1&apiKey={API_KEY}"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("resultsCount", 0) > 0:
                print(f"[OK] {symbol}")
                return True
            else:
                print(f"[EMPTY] {symbol} (No data for {DATE})")
                return False
        else:
            print(f"[FAIL] {symbol} (Status {resp.status_code})")
            return False
    except Exception as e:
        print(f"[ERR] {symbol} ({e})")
        return False
    finally:
        time.sleep(0.2) # Rate limit safety

print("--- Validating Equity ---")
for t in TICKERS:
    # Check standard
    if not check_ticker(t):
        # Try OTC for BBBY? (BBBYQ)
        if t == "BBBY":
            check_ticker("BBBYQ")

print("\n--- Validating Crypto ---")
for c in CRYPTO:
    # Try X:BTCUSD format
    check_ticker(f"{c}USD", prefix="X:")
