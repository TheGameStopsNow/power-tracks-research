import requests

BASE_URL = "http://127.0.0.1:25503/v3"
SYMBOL = "GME"
DATE = "20240517"

def title(t):
    print(f"\n--- {t} ---")

def test(url, params):
    try:
        r = requests.get(url, params=params)
        print(f"URL: {r.url}")
        print(f"Status: {r.status_code}")
        if r.status_code != 200:
            print(f"Response: {r.text[:500]}")
        else:
            print(f"Response Head: {r.text[:500]}") # Check if it's a list (Bulk)
    except Exception as e:
        print(f"Error: {e}")

title("IV Single Contract Probe")

# Get one contract from the list we saw
# "GME","2024-05-31",2.500,"PUT"
params = {
    'symbol': 'GME', 
    'date': '20240517', 
    'expiration': '20240531', 
    'strike': '2500', # Strike is usually in millis for some APIs? No, response said 2.500. 
                      # Wait, response csv said 2.500. 
                      # Docs say "100.00" or "$100.00". 
                      # Let's try "2.5".
    'right': 'P'
}
# ThetaData Format: YYYYMMDD usually.
# docs: "YYYY-MM-DD" or "YYYYMMDD".
# The response had dashes "2024-05-31".
# I'll use dashes to match.

params['expiration'] = '2024-05-31'
params['strike'] = '2.5' # Try simple float string

test(f"{BASE_URL}/option/history/greeks/implied_volatility", params)





