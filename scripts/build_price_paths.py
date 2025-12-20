#!/usr/bin/env python3
"""
Derive price_paths.csv from a downloaded trades/options JSON payload.

Primary goal: turn fetched raw slices (stored under data/raw/, git-ignored)
into a tiny price_paths.csv with timestamp_us and price columns for demos/tests.

Usage:
    python scripts/build_price_paths.py \\
        --source data/raw/polygon/gme/2024-05-13/trades.json \\
        --out data/samples/local/gme_20240513/price_paths.csv \\
        [--limit 1200]
"""
import argparse
import json
from pathlib import Path

import pandas as pd


def build_price_paths(source: Path, out: Path, limit: int | None) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Trades JSON not found: {source}")

    payload = json.loads(source.read_text())
    results = (
        payload.get("results")
        or payload.get("ticks")
        or payload.get("bars")
        or []
    )
    if not results:
        raise ValueError(f"No results found in {source}")

    df = pd.DataFrame(results)
    if "t" in df.columns:  # polygon aggregates use milliseconds
        df["timestamp_us"] = pd.to_numeric(df["t"], errors="coerce") * 1000
    elif "sip_timestamp" in df.columns:  # polygon trades v3
        df["timestamp_us"] = pd.to_numeric(df["sip_timestamp"], errors="coerce")
    elif "timestamp" in df.columns:
        df["timestamp_us"] = pd.to_datetime(df["timestamp"]).view("int64") // 1000
    else:
        raise ValueError("No timestamp field found (expected t, sip_timestamp, or timestamp).")

    price_col = None
    for candidate in ("c", "p", "price"):
        if candidate in df.columns:
            price_col = candidate
            break
    if not price_col:
        raise ValueError("No price column found (expected c, p, or price).")

    out_df = df.loc[:, ["timestamp_us", price_col]].rename(columns={price_col: "price"})
    out_df = out_df.dropna(subset=["timestamp_us", "price"]).sort_values("timestamp_us")
    if limit:
        out_df = out_df.head(limit)

    out.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out, index=False)
    print(f"Wrote {len(out_df)} rows to {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert trades/options JSON to price_paths.csv")
    parser.add_argument(
        "--source",
        default="data/raw/polygon/gme/2024-05-13/trades.json",
        help="Path to the raw JSON (trades/options).",
    )
    parser.add_argument(
        "--out",
        default="data/samples/local/gme_20240513/price_paths.csv",
        help="Where to write price_paths.csv (git-ignored).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional row cap to keep samples small (0 = no cap).",
    )
    args = parser.parse_args()

    limit = args.limit if args.limit and args.limit > 0 else None
    build_price_paths(Path(args.source), Path(args.out), limit)


if __name__ == "__main__":
    main()
