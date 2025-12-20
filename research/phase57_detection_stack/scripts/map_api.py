import requests
import time

BASE_URL = "http://127.0.0.1:25503/v3"
SYMBOL = "GME"

PATHS = [
    "/list/contracts",
    "/list/contracts/option",
    "/list/roots/option",
    "/history/option/greeks",
    "/hist/option/greeks",
    "/bulk/hist/option/greeks", # Expect 410
    "/bulk_hist/option/greeks",
    "/snapshot/option/greeks",
    "/bulk_snapshot/option/greeks",
    "/bulk/snapshot/option/greeks",
    "/greeks/option",
    "/option/greeks",
    "/bulk/greeks",
    "/bulk/option/greeks"
]

def map_api():
    print("Mapping V3 API Structure via 410 Checks...")
    
    # Use 'root' to trigger 410 if path is valid
    params = {'root': SYMBOL} 
    
    found_paths = []
    
    for p in PATHS:
        url = BASE_URL + p
        try:
            r = requests.get(url, params=params)
            print(f"Path: {p:30} | Status: {r.status_code}")
            
            if r.status_code == 410:
                print(f"  >>> FOUND PATH (Deprecated Params): {p}")
                found_paths.append(p)
            elif r.status_code == 200:
                print(f"  >>> FOUND PATH (Working): {p}")
                found_paths.append(p)
                
        except Exception as e:
            print(f"Error: {e}")
            
    print("\n--- Valid Paths Found ---")
    for p in found_paths:
        print(p)

    # Phase 2: Try to Fix Found Paths with 'symbol'
    print("\n--- Phase 2: Retrying Valid Paths with 'symbol' ---")
    params_v3 = {'symbol': SYMBOL, 'start_date': '20240517', 'end_date': '20240517', 'format': 'csv'}
    for p in found_paths:
         # Try logic
         url = BASE_URL + p
         r = requests.get(url, params=params_v3)
         print(f"Path: {p:30} | Status: {r.status_code}")
         if r.status_code != 200:
             print(f"  Msg: {r.text[:100]}")

if __name__ == "__main__":
    map_api()
