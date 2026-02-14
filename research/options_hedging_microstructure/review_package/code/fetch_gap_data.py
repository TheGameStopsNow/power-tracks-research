#!/usr/bin/env python3
"""
Fetch missing GME tick data from Polygon to fill the 2021-06 → 2024-05 gap.

Usage:
  source .venv/bin/activate
  POLYGON_API_KEY=xxx python research/options_hedging_microstructure/fetch_gap_data.py
"""
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

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

# Persistent session
session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retries))


def get_trading_days(symbol: str, from_date: str, to_date: str) -> list[str]:
    """Get list of actual trading days from Polygon aggregates."""
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{from_date}/{to_date}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": API_KEY}
    resp = session.get(url, params=params, timeout=30)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    dates = []
    for bar in results:
        ts = pd.Timestamp(bar["t"], unit="ms", tz="US/Eastern")
        dates.append(ts.strftime("%Y-%m-%d"))
    return dates


def fetch_day(symbol: str, date_str: str) -> int:
    """Fetch tick trades for one day. Returns trade count."""
    out_path = DATA_DIR / f"symbol={symbol}" / f"date={date_str}" / "part-0.parquet"
    if out_path.exists():
        return -1  # already exists

    all_results = []
    url = f"https://api.polygon.io/v3/trades/{symbol}"
    params = {"timestamp": date_str, "limit": 50000, "apiKey": API_KEY}

    while url:
        resp = session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            # Rate limited — wait and retry
            time.sleep(12)
            continue
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        all_results.extend(results)
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
    # Gap: 2021-06-02 to 2024-04-30
    from_date = "2021-06-02"
    to_date = "2024-04-30"

    print(f"Fetching trading days for {SYMBOL} from {from_date} to {to_date}...")
    trading_days = get_trading_days(SYMBOL, from_date, to_date)
    print(f"Found {len(trading_days)} trading days in the gap period")

    # Filter out already-fetched days
    missing = []
    for d in trading_days:
        p = DATA_DIR / f"symbol={SYMBOL}" / f"date={d}" / "part-0.parquet"
        if not p.exists():
            missing.append(d)

    print(f"{len(missing)} days need fetching ({len(trading_days) - len(missing)} already cached)")

    if not missing:
        print("All days already fetched!")
        return

    fetched = 0
    errors = 0
    for i, date in enumerate(missing):
        try:
            count = fetch_day(SYMBOL, date)
            if count == -1:
                status = "cached"
            elif count == 0:
                status = "empty"
            else:
                status = f"{count:,} trades"
                fetched += 1
        except Exception as e:
            status = f"ERROR: {e}"
            errors += 1

        if (i + 1) % 10 == 0 or i == 0 or i == len(missing) - 1:
            pct = (i + 1) / len(missing) * 100
            print(f"  [{i+1}/{len(missing)}] {pct:.0f}%  {date}  {status}")

        # Polygon free tier: 5 calls/min. Paid: higher. Use 0.25s delay.
        time.sleep(0.25)

    print(f"\nDone! Fetched {fetched} days, {errors} errors, "
          f"{len(missing) - fetched - errors} empty/cached")


if __name__ == "__main__":
    main()
