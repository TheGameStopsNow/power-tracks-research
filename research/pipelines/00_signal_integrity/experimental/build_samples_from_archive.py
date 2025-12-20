#!/usr/bin/env python3
"""
Build sample_<date>/raw_ticks from a local Polygon archive (parquet) instead of calling the API.

Usage:
  python experimental/build_samples_from_archive.py \
    --archive-root "/path/to/polygon-market-data/data" \
    --symbol GME \
    --date 2024-05-06

This will:
  - Read trades from trades/<symbol>/YYYY/MM/DD/gme_trades_YYYY-MM-DD.parquet
  - Write CSV to reproducibility-bundle/sample_YYYY-MM-DD/raw_ticks/GME_YYYY-MM-DD_trades.csv
    with columns: timestamp, price, volume, venue, conditions, symbol
"""

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd


def main():
    parser = argparse.ArgumentParser(description="Build sample raw_ticks from local Polygon archive.")
    parser.add_argument("--archive-root", required=True, type=Path)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()

    date = datetime.strptime(args.date, "%Y-%m-%d").date()
    y = date.year
    m = f"{date.month:02d}"
    d = f"{date.day:02d}"
    symbol_lower = args.symbol.lower()

    parquet_path = (
        args.archive_root
        / "trades"
        / args.symbol
        / str(y)
        / m
        / d
        / f"{symbol_lower}_trades_{date.isoformat()}.parquet"
    )
    if not parquet_path.exists():
        raise SystemExit(f"Parquet file not found: {parquet_path}")

    print(f"Reading parquet: {parquet_path}")
    df = pd.read_parquet(parquet_path)
    # Ensure required columns (Polygon archive layout)
    required = ["sip_timestamp", "price", "size", "exchange_id", "conditions"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing columns in parquet: {missing}")

    out_dir = Path("sample_" + date.isoformat()) / "raw_ticks"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.symbol}_{date.isoformat()}_trades.csv"

    out_df = pd.DataFrame({
        "timestamp": df["sip_timestamp"],
        "price": df["price"],
        "volume": df["size"],
        "venue": df["exchange_id"],
        "conditions": df["conditions"],
        "symbol": args.symbol,
    })
    out_df.to_csv(out_path, index=False)
    print(f"Wrote raw_ticks CSV: {out_path} ({len(out_df):,} rows)")


if __name__ == "__main__":
    main()
