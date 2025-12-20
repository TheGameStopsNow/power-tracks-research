#!/usr/bin/env python3
"""
Expanded Data Download for Year-Round Burst Analysis
=====================================================

Downloads 1-minute bar data for multiple symbols across a full year
to test if Power Track patterns occur year-round and per-symbol.

Symbols included:
- GME (primary target)
- Meme basket: AMC, BB, KOSS, BBBY, TLRY
- Tech controls: AAPL, NVDA, TSLA, AMD, MSFT
- Volatile small caps: SPCE, PLTR, SOFI, FUBO

Date range: Full 2024 (we can go back further if needed)

Usage:
    POLYGON_API_KEY=xxx python scripts/download_expanded_data.py [--symbols GME,AMC,BB] [--year 2024]
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, date
from pathlib import Path
import time

try:
    import requests
    import pandas as pd
except ImportError:
    print("Install: pip install requests pandas")
    sys.exit(1)

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
OUTPUT_DIR = BASE_DIR / "data" / "expanded_bars"

# Symbol groups for testing
SYMBOL_GROUPS = {
    "target": ["GME"],
    "meme_basket": ["AMC", "BB", "KOSS", "TLRY"],
    "tech_controls": ["AAPL", "NVDA", "TSLA", "AMD", "MSFT"],
    "volatile_small": ["SPCE", "PLTR", "SOFI", "FUBO", "MSTR"],
    "indexes": ["SPY", "QQQ", "IWM"]
}

DEFAULT_SYMBOLS = SYMBOL_GROUPS["target"] + SYMBOL_GROUPS["meme_basket"][:3] + ["SPY", "AAPL"]


def fetch_bars_single_day(symbol: str, day: date, api_key: str) -> pd.DataFrame:
    """Fetch 1-minute bars for a single day."""
    
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{day.isoformat()}/{day.isoformat()}"
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 50000,
        "apiKey": api_key,
    }
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            # Rate limited - wait and retry
            print(f"  Rate limited, waiting 60s...")
            time.sleep(60)
            resp = requests.get(url, params=params, timeout=30)
        
        resp.raise_for_status()
        data = resp.json()
        
        records = data.get("results", [])
        if not records:
            return pd.DataFrame()
        
        df = pd.DataFrame(records)
        df = df.rename(columns={
            "v": "volume",
            "o": "open",
            "c": "close",
            "h": "high",
            "l": "low",
            "t": "timestamp",
            "n": "transactions",
        })
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["symbol"] = symbol
        df["date"] = day.isoformat()
        
        return df
        
    except Exception as e:
        print(f"  Error fetching {symbol} {day}: {e}")
        return pd.DataFrame()


def download_symbol_year(symbol: str, year: int, api_key: str, output_dir: Path) -> dict:
    """Download all available trading days for a symbol in a given year."""
    
    symbol_dir = output_dir / symbol
    symbol_dir.mkdir(parents=True, exist_ok=True)
    
    start_date = date(year, 1, 1)
    end_date = min(date(year, 12, 31), date.today())
    
    stats = {
        "symbol": symbol,
        "year": year,
        "days_attempted": 0,
        "days_downloaded": 0,
        "days_skipped": 0,
        "total_bars": 0
    }
    
    current = start_date
    while current <= end_date:
        # Skip weekends
        if current.weekday() >= 5:
            current += timedelta(days=1)
            continue
        
        out_file = symbol_dir / f"{symbol}_{current.isoformat()}_minute.csv"
        
        # Skip if already exists
        if out_file.exists():
            stats["days_skipped"] += 1
            current += timedelta(days=1)
            continue
        
        stats["days_attempted"] += 1
        
        df = fetch_bars_single_day(symbol, current, api_key)
        
        if not df.empty:
            df.to_csv(out_file, index=False)
            stats["days_downloaded"] += 1
            stats["total_bars"] += len(df)
            print(f"  {symbol} {current}: {len(df)} bars")
        else:
            print(f"  {symbol} {current}: no data")
        
        # Rate limiting: ~5 requests per second free tier
        time.sleep(0.25)
        
        current += timedelta(days=1)
    
    return stats


def main():
    parser = argparse.ArgumentParser(description="Download expanded year-round data")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS),
                       help="Comma-separated list of symbols")
    parser.add_argument("--year", type=int, default=2024,
                       help="Year to download (default: 2024)")
    parser.add_argument("--all-groups", action="store_true",
                       help="Download all symbol groups (17 symbols)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be downloaded")
    args = parser.parse_args()
    
    api_key = os.getenv("POLYGON_API_KEY")
    if not api_key:
        print("Error: POLYGON_API_KEY environment variable required")
        print("  export POLYGON_API_KEY=your_key")
        sys.exit(1)
    
    # Determine symbols
    if args.all_groups:
        symbols = []
        for group in SYMBOL_GROUPS.values():
            symbols.extend(group)
        symbols = list(set(symbols))  # Dedupe
    else:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("EXPANDED DATA DOWNLOAD")
    print("=" * 70)
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Year: {args.year}")
    print(f"Output: {OUTPUT_DIR}")
    print()
    
    if args.dry_run:
        print("[DRY RUN] Would download:")
        for symbol in symbols:
            print(f"  {symbol}: ~252 trading days for {args.year}")
        return
    
    all_stats = []
    for symbol in symbols:
        print(f"\n>>> Downloading {symbol} for {args.year}")
        stats = download_symbol_year(symbol, args.year, api_key, OUTPUT_DIR)
        all_stats.append(stats)
    
    # Summary
    print("\n" + "=" * 70)
    print("DOWNLOAD SUMMARY")
    print("=" * 70)
    
    total_days = 0
    total_bars = 0
    for stats in all_stats:
        print(f"{stats['symbol']}: {stats['days_downloaded']} days, {stats['total_bars']:,} bars")
        total_days += stats["days_downloaded"]
        total_bars += stats["total_bars"]
    
    print(f"\nTotal: {total_days} symbol-days, {total_bars:,} bars")
    
    # Save manifest
    import json
    manifest = {
        "download_date": datetime.now().isoformat(),
        "year": args.year,
        "symbols": symbols,
        "stats": all_stats
    }
    
    with open(OUTPUT_DIR / "download_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    
    print(f"\nManifest saved to {OUTPUT_DIR / 'download_manifest.json'}")


if __name__ == "__main__":
    main()
