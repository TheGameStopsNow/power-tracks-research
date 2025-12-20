#!/usr/bin/env python3
"""
Fetch a tiny sample dataset from Polygon.

Outputs a minimal price_paths.csv compatible with the Magic Demo:
columns: timestamp_us, price

Usage:
    POLYGON_API_KEY=... python tools/fetch_samples.py \
        --symbol GME --date 2024-05-13 \
        --out data/samples/local/gme_20240513/price_paths.csv \
        --bars 400

Notes:
- Keeps downloads small to avoid committing vendor data.
- Does not run unless an API key is provided.
"""
import argparse
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests


def fetch_from_polygon(symbol: str, date: str, limit_bars: int, api_key: str) -> pd.DataFrame:
    """
    Fetch minute bars from Polygon and return a dataframe with timestamp_us and price.
    """
    start = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/"
        f"{start.date()}/{end.date()}?adjusted=true&sort=asc&limit=50000&apiKey={api_key}"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    if not results:
        raise RuntimeError("No results returned from Polygon")
    rows = []
    for r in results[:limit_bars]:
        ts_us = int(r["t"]) * 1000  # Polygon returns ms
        rows.append({"timestamp_us": ts_us, "price": r["c"]})
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch a tiny sample for demos/tests.")
    parser.add_argument("--symbol", default="GME", help="Ticker symbol (e.g., GME)")
    parser.add_argument("--date", required=True, help="Trading date (YYYY-MM-DD, UTC)")
    parser.add_argument(
        "--out",
        default="data/samples/local/sample/price_paths.csv",
        help="Output CSV path (will be created, parents too).",
    )
    parser.add_argument(
        "--bars",
        type=int,
        default=400,
        help="Maximum bars to keep (keeps samples tiny for demos/CI).",
    )
    parser.add_argument(
        "--provider",
        choices=["polygon"],
        default="polygon",
        help="Data provider to use.",
    )
    args = parser.parse_args()

    api_key = os.environ.get("POLYGON_API_KEY")
    if not api_key:
        raise SystemExit(f"POLYGON_API_KEY not set; cannot fetch data.")

    df = fetch_from_polygon(args.symbol, args.date, args.bars, api_key)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)

    print(f"Wrote {len(df)} rows to {out_path}")
    print("Columns: timestamp_us, price")
    print("Reminder: data/samples/local is git-ignored.")


if __name__ == "__main__":
    main()
