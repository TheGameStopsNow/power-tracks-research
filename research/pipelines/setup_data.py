#!/usr/bin/env python3
"""
Power Tracks Research Data Setup (manifest-driven)
=================================================

Downloads every raw slice defined in `docs/raw_data_manifest.json` directly into
the folders expected by the pipelines/tests. No raw data is shipped; everything is
fetched at runtime using the user’s API key and stored in gitignored paths.

Usage:
    python pipelines/setup_data.py [--study STUDY_ID] [--dry-run]

Options:
    --study STUDY_ID    Filter manifest entries whose destination contains the study ID.
    --dry-run           Print the files that would be fetched without downloading.

Requirements:
    POLYGON_API_KEY environment variable
    requests
    pandas
"""
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from dotenv import load_dotenv

try:
    import pandas as pd
    import requests
except ImportError:
    print("Please install the dependencies: pip install pandas requests")
    raise

BASE_DIR = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = BASE_DIR / "docs" / "raw_data_manifest.json"
DEFAULT_BARS_LIMIT = 50000


def load_manifest() -> List[Dict[str, str]]:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Manifest missing: {MANIFEST_PATH}")
    manifest = json.loads(MANIFEST_PATH.read_text())
    return manifest.get("sources", [])


def format_dest(entry: Dict[str, str]) -> Path:
    template = entry.get("dest", "")
    if not template:
        raise ValueError("Manifest entry missing 'dest'")
    symbol = entry.get("symbol", "").lower()
    return Path(template.format(provider=entry["provider"], symbol=symbol, date=entry["date"]))


def format_pipeline_path(entry: Dict[str, str]) -> Path | None:
    pipeline_template = entry.get("pipeline_path")
    if not pipeline_template:
        return None
    symbol = entry.get("symbol", "").lower()
    return Path(pipeline_template.format(provider=entry["provider"], symbol=symbol, date=entry["date"]))


def determine_data_type(entry: Dict[str, str]) -> str:
    if entry.get("data_type"):
        return entry["data_type"]
    dest = entry.get("dest", "")
    if "bars" in dest:
        return "bars"
    if "test_ticks" in dest or "test-data" in dest or "features" in dest:
        return "trades"
    return "trades"


def fetch_bars(symbol: str, start: str, end: str, api_key: str) -> pd.DataFrame:
    start_date = start.split("T")[0]
    end_date = end.split("T")[0]
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{start_date}/{end_date}"
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": DEFAULT_BARS_LIMIT,
        "apiKey": api_key,
    }
    print(f"  Fetching bars for {symbol} ({start_date} → {end_date})")
    records = []
    while True:
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("results", []))
        next_url = data.get("next_url")
        if not next_url:
            break
        url = next_url
        params = {"apiKey": api_key}
    if not records:
        print(f"  Warning: no bars returned for {symbol}")
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
    return df


def fetch_trades(symbol: str, date: str, api_key: str) -> pd.DataFrame:
    url = f"https://api.polygon.io/v3/trades/{symbol}"
    dt = datetime.fromisoformat(date)
    start_ns = int(dt.replace(hour=13, minute=0).timestamp() * 1e9)
    end_ns = int(dt.replace(hour=20, minute=0).timestamp() * 1e9)
    params = {
        "timestamp.gte": start_ns,
        "timestamp.lt": end_ns,
        "limit": 50000,
        "apiKey": api_key,
    }
    print(f"  Fetching trades for {symbol} on {date}")
    records = []
    while True:
        resp = requests.get(url, params=params, timeout=60)
        if resp.status_code == 403:
            print("  Warning: Tick permissions missing; skipping.")
            break
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("results", []))
        next_url = data.get("next_url")
        if not next_url:
            break
        url = next_url
        params = {"apiKey": api_key}
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    if "participant_timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["participant_timestamp"], unit="ns")
    elif "sip_timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["sip_timestamp"], unit="ns")
    return df


def save_dataframe(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"  Saved {path}")


def process_entry(entry: Dict[str, str], api_key: str, dry_run: bool) -> None:
    dest_path = format_dest(entry)
    pipeline_path = format_pipeline_path(entry)
    data_type = determine_data_type(entry)
    if dry_run:
        target = pipeline_path or dest_path
        print(f"[dry-run] Would fetch {entry['symbol']} {entry['date']} → {target} ({data_type})")
        return
    if data_type == "bars":
        start = entry.get("start")
        end = entry.get("end")
        if not start or not end:
            raise ValueError("Missing start/end for bars entry")
        df = fetch_bars(entry["symbol"], start, end, api_key)
        if not df.empty:
            out_path = pipeline_path or dest_path
            if out_path.is_dir():
                out_path = out_path / f"{entry['symbol'].upper()}_{entry['date']}_minute.csv"
            save_dataframe(df, out_path)
    elif data_type == "trades":
        df = fetch_trades(entry["symbol"], entry["date"], api_key)
        if not df.empty:
            out_path = pipeline_path or dest_path
            if out_path.is_dir():
                out_path = out_path / f"{entry['symbol'].upper()}_{entry['date']}_trades.csv"
            save_dataframe(df, out_path)
    else:
        print(f"  Skipping unsupported data_type '{data_type}' for {entry['dest']}")


def filter_entries(entries: List[Dict[str, str]], study: str | None) -> List[Dict[str, str]]:
    if not study:
        return entries
    return [entry for entry in entries if study in entry.get("dest", "")]


def main():
    parser = argparse.ArgumentParser(description="Fetch research raw data per manifest")
    parser.add_argument("--dry-run", action="store_true", help="Show downloads without running them")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("POLYGON_API_KEY")
    if not api_key:
        print("POLYGON_API_KEY not set; set it in .env or environment.")
        return

    entries = load_manifest()
    filtered = filter_entries(entries, args.study)
    if not filtered:
        print("No manifest entries match the requested filter.")
        return

    for entry in filtered:
        print(f"\nEntry: {entry.get('notes', entry.get('dest'))}")
        process_entry(entry, api_key, args.dry_run)


if __name__ == "__main__":
    main()
