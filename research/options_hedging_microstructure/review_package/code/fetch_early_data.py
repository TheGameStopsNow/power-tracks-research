#!/usr/bin/env python3
"""
Fetch pre-2020 GME tick data from Polygon (2018-01-01 → 2020-09-30).

Usage:
  source .venv/bin/activate
  python research/options_hedging_microstructure/fetch_early_data.py
"""
import os
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

API_KEY = os.environ.get("POLYGON_API_KEY")
if not API_KEY:
    print("ERROR: POLYGON_API_KEY not set")
    sys.exit(1)

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "raw" / "polygon" / "trades"
SYMBOL = "GME"

session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retries))


def get_trading_days(symbol, from_date, to_date):
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{from_date}/{to_date}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": API_KEY}
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return [pd.Timestamp(bar["t"], unit="ms", tz="US/Eastern").strftime("%Y-%m-%d") for bar in results]


def fetch_day(symbol, date_str):
    out_path = DATA_DIR / f"symbol={symbol}" / f"date={date_str}" / "part-0.parquet"
    if out_path.exists():
        return -1

    all_results = []
    url = f"https://api.polygon.io/v3/trades/{symbol}"
    params = {"timestamp": date_str, "limit": 50000, "apiKey": API_KEY}

    while url:
        resp = session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            time.sleep(12)
            continue
        resp.raise_for_status()
        data = resp.json()
        all_results.extend(data.get("results", []))
        url = data.get("next_url")
        if url and "apiKey" not in url:
            url += f"&apiKey={API_KEY}"
        params = {}

    if not all_results:
        return 0

    df = pd.DataFrame(all_results)
    if "sip_timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["sip_timestamp"], unit="ns")
    cols = [c for c in ["timestamp", "price", "size", "exchange", "conditions"] if c in df.columns]
    df = df[cols]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    return len(df)


def main():
    from_date = "2018-01-01"
    to_date = "2020-09-30"

    print(f"Fetching trading days for {SYMBOL} from {from_date} to {to_date}...")
    trading_days = get_trading_days(SYMBOL, from_date, to_date)
    print(f"Found {len(trading_days)} trading days")

    missing = [d for d in trading_days
               if not (DATA_DIR / f"symbol={SYMBOL}" / f"date={d}" / "part-0.parquet").exists()]
    print(f"{len(missing)} days need fetching ({len(trading_days) - len(missing)} cached)")

    if not missing:
        print("All days already fetched!")
        return

    fetched = errors = 0
    for i, date in enumerate(missing):
        try:
            count = fetch_day(SYMBOL, date)
            status = "cached" if count == -1 else ("empty" if count == 0 else f"{count:,} trades")
            if count > 0:
                fetched += 1
        except Exception as e:
            status = f"ERROR: {e}"
            errors += 1

        if (i + 1) % 10 == 0 or i == 0 or i == len(missing) - 1:
            print(f"  [{i+1}/{len(missing)}] {(i+1)/len(missing)*100:.0f}%  {date}  {status}")

        time.sleep(0.25)

    print(f"\nDone! Fetched {fetched}, errors {errors}, skipped {len(missing)-fetched-errors}")


if __name__ == "__main__":
    main()
