import requests

BASE_URL = "http://127.0.0.1:25503/v3"

def test(url, params={}):
    print(f"Testing {url} {params} ...")
    try:
        r = requests.get(url, params=params)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
             print(f"Response: {r.text[:100]}")
    except Exception as e:
        print(f"Error: {e}")

# Roots
test(f"{BASE_URL}/list/roots")
test(f"{BASE_URL}/list/roots/option")
test(f"{BASE_URL}/list/roots", {'type': 'option'})
test(f"{BASE_URL}/list/roots", {'sec_type': 'option'})
test(f"{BASE_URL}/list/roots", {'security_type': 'option'})
