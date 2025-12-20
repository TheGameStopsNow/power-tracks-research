#!/usr/bin/env python3
"""
Fetch minute bars from Polygon for a symbol/date range.

Usage:
  POLYGON_API_KEY=... python scripts/fetch_minute_bars.py --symbol GME --date 2024-05-14 --out bars/GME_2024-05-14_minute.csv

Notes:
  - Uses v2/aggs/ticker/{symbol}/range/1/minute/{from}/{to}
  - Requires POLYGON_API_KEY in env or --api-key
"""

import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path
import requests
import pandas as pd


def fetch_minute(symbol: str, date: str, api_key: str) -> pd.DataFrame:
    start = date
    end = date
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{start}/{end}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    if not results:
        raise ValueError(f"No bars returned for {symbol} on {date}")
    rows = []
    for r in results:
        ts = datetime.utcfromtimestamp(r["t"] / 1000.0)
        rows.append(
            {
                "timestamp": ts.isoformat() + "Z",
                "open": r["o"],
                "high": r["h"],
                "low": r["l"],
                "close": r["c"],
                "volume": r["v"],
                "vwap": r.get("vw"),
                "transactions": r.get("n"),
            }
        )
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description="Fetch Polygon minute bars for a date.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--out", required=True, type=Path, help="Output CSV path")
    parser.add_argument("--api-key", help="Polygon API key (or POLYGON_API_KEY env)")
    args = parser.parse_args()

    api_key = args.api_key or os.getenv("POLYGON_API_KEY")
    if not api_key:
        raise SystemExit("POLYGON_API_KEY or --api-key is required.")

    df = fetch_minute(args.symbol, args.date, api_key)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"Wrote {len(df)} bars to {args.out}")


if __name__ == "__main__":
    main()
