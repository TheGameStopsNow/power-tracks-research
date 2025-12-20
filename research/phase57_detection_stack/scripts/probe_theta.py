import requests
import time

BASE_URL = "http://127.0.0.1:25503/v3"
SYMBOL = "GME"
DATE = "20240517"

ENDPOINTS = [
    "/list/contracts?symbol=GME",            # V3 uses symbol
    "/list/contracts?root=GME",              # V2 check
    "/list/contracts/option?symbol=GME",
    "/snapshot/option/greeks",               # Retry
    "/bulk/snapshot/option/greeks", 
    "/hist/option/greeks",
    "/history"
]

def probe():
    print("Probing ThetaData V3 Endpoints...")
    
    # Common Params
    params = {
        'symbol': SYMBOL, # V3
        'start_date': DATE,
        'end_date': DATE,
        'expiration': 0,
        'right': 'C',
        'interval': 0,
        'format': 'csv'
    }
    
    for ep in ENDPOINTS:
        url = BASE_URL + ep
        try:
            print(f"Testing {ep} ...")
            r = requests.get(url, params=params)
            print(f"  Status: {r.status_code}")
            if r.status_code != 404:
                print(f"  Response: {r.text[:200]}")
            
            if r.status_code == 200:
                print(f">>> FOUND VALID ENDPOINT: {ep} <<<")
                
        except Exception as e:
            print(f"  Error: {e}")
        time.sleep(0.5)

if __name__ == "__main__":
    probe()
