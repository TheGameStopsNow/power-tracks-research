#!/usr/bin/env python3
"""
Fetch raw slices defined in docs/raw_data_manifest.json into git-ignored paths.
Supports Polygon trades (aggregates). Other APIs are skipped with a notice.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "docs" / "raw_data_manifest.json"
OUT_ROOT = ROOT / "data" / "samples" / "local"


def fetch_polygon_trades(symbol: str, date: str, start: Optional[str], end: Optional[str], api_key: str, out_dir: Path) -> None:
    target = out_dir / "trades.json"
    if target.exists() and not FORCE_FETCH:
        print(f"[skip] exists {target}")
        return
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00")) if start else datetime.fromisoformat(f"{date}T00:00:00+00:00")
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else datetime.fromisoformat(f"{date}T23:59:59+00:00")
    
    url = f"https://api.polygon.io/v3/trades/{symbol}"
    params = {
        "timestamp.gte": int(start_dt.timestamp() * 1e9),
        "timestamp.lt": int(end_dt.timestamp() * 1e9),
        "limit": 50000,
        "apiKey": api_key,
        "sort": "timestamp",
        "order": "asc"
    }
    
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[fetch] trades {symbol} {date} -> {out_dir}")
    
    all_results = []
    while True:
        resp = requests.get(url, params=params, timeout=60)
        if resp.status_code == 403:
            print("\n" + "!" * 80)
            print("CRITICAL: 403 Forbidden accessing Polygon Trades API.")
            print("This research phase requires HISTORICAL TICK DATA (Trades).")
            print("Please UPGRADE your Polygon.io API key to 'Stocks Developer' plan or higher.")
            print("!" * 80 + "\n")
            # Clear partially created directory/file if needed, but for now just error out
            raise PermissionError("Polygon API Key insufficient for Trades data.")
            
        resp.raise_for_status()
        data = resp.json()
        all_results.extend(data.get("results", []))
        next_url = data.get("next_url")
        if not next_url:
            break
        url = next_url
        params = {"apiKey": api_key}
        
    target.write_text(json.dumps({"results": all_results}))


def fetch_polygon_bars(symbol: str, start: Optional[str], end: Optional[str], api_key: str, target: Path) -> None:
    if target.exists() and not FORCE_FETCH:
        print(f"[skip] exists {target}")
        return
    if not start or not end:
        raise ValueError("start and end required for bars fetch")
    start_date = start.split("T")[0]
    end_date = end.split("T")[0]
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{start_date}/{end_date}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key}
    print(f"[fetch] bars {symbol} {start_date}->{end_date} -> {target}")
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
    import pandas as pd

    df = pd.DataFrame(records)
    if "t" in df.columns:
        df["timestamp"] = pd.to_datetime(df["t"], unit="ms")
    target.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(target, index=False)


def fetch_polygon_options_flow(symbol: str, date: str, start: Optional[str], end: Optional[str], api_key: str, out_dir: Path) -> None:
    target = out_dir / "options_flow.json"
    if target.exists() and not FORCE_FETCH:
        print(f"[skip] exists {target}")
        return
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00")) if start else datetime.fromisoformat(f"{date}T00:00:00+00:00")
    end_dt = datetime.fromisoformat(end.replace("Z", "+00:00")) if end else datetime.fromisoformat(f"{date}T23:59:59+00:00")
    url = "https://api.polygon.io/v3/trades/options"
    params = {
        "underlying_ticker": symbol,
        "timestamp.gte": int(start_dt.timestamp() * 1e9),
        "timestamp.lt": int(end_dt.timestamp() * 1e9),
        "limit": 50000,
        "apiKey": api_key,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[fetch] options-flow {symbol} {date} -> {out_dir}")
    all_results = []
    while True:
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        all_results.extend(data.get("results", []))
        next_url = data.get("next_url")
        if not next_url:
            break
        url = next_url
        params = {"apiKey": api_key}
    target.write_text(json.dumps({"results": all_results}))


import argparse

def main() -> None:
    load_dotenv() # Load variables from .env if present
    parser = argparse.ArgumentParser(description="Fetch raw slices from a data manifest.")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH, help="Path to manifest.json")
    args = parser.parse_args()

    global FORCE_FETCH
    FORCE_FETCH = os.environ.get("FORCE_FETCH", "").lower() in {"1", "true", "yes"}
    api_key = os.environ.get("POLYGON_API_KEY")
    if not api_key:
        print("POLYGON_API_KEY not set; skipping manifest fetch.")
        return
    
    target_manifest = args.manifest.resolve()
    if not target_manifest.exists():
        print(f"Manifest not found at {target_manifest}, skipping.")
        return
    
    print(f"Using manifest: {target_manifest}")
    manifest = json.loads(target_manifest.read_text())
    for src in manifest.get("sources", []):
        provider = src.get("provider")
        api = src.get("api")
        symbol = src.get("symbol")
        date = src.get("date")
        start = src.get("start")
        end = src.get("end")
        symbol_lower = symbol.lower() if symbol else ""
        dest = src.get("dest")
        pipeline_path = src.get("pipeline_path")
        if dest:
            p = Path(dest.format(provider=provider, symbol=symbol_lower, date=date))
            if not p.is_absolute():
                out_dir = target_manifest.parent / p
            else:
                out_dir = p
        else:
            out_dir = OUT_ROOT / provider / symbol_lower / date
        try:
            if provider == "polygon" and api == "trades":
                fetch_polygon_trades(symbol, date, start, end, api_key, out_dir)
            elif provider == "polygon" and api == "bars":
                target = (
                    Path(pipeline_path.format(provider=provider, symbol=symbol_lower, date=date))
                    if pipeline_path
                    else out_dir / f"{symbol.upper()}_{date}_minute.csv"
                )
                fetch_polygon_bars(symbol, start, end, api_key, target)
            elif provider == "polygon" and api == "options-flow":
                fetch_polygon_options_flow(symbol, date, start, end, api_key, out_dir)
            else:
                print(f"[skip] provider/api not supported in script: {provider}/{api}")
        except Exception as e:
            print(f"[error] {provider}/{api} {symbol} {date}: {e}")


if __name__ == "__main__":
    main()
