import requests

BASE_URL = "http://127.0.0.1:25503/v3"
SYMBOL = "GME"

def test_stock():
    url = f"{BASE_URL}/snapshot/stock/quote"
    params = {'symbol': SYMBOL}
    print(f"Testing {url} ...")
    try:
        r = requests.get(url, params=params)
        print(f"Status: {r.status_code}")
        print(f"Response: {r.text[:200]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_stock()
