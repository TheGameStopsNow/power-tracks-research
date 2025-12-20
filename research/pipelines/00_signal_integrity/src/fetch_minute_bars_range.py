#!/usr/bin/env python3
"""
Batch fetch Polygon 1-minute bars for a date range (inclusive).

Usage:
  POLYGON_API_KEY=... python scripts/fetch_minute_bars_range.py \
    --symbol GME \
    --start 2023-11-25 \
    --end 2025-11-25 \
    --outdir bars_range

Notes:
  - Saves one CSV per day: <outdir>/<symbol>_YYYY-MM-DD_minute.csv
  - Skips files that already exist unless --overwrite is set.
  - Relies on fetch_minute_bars.py for per-day fetch.
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime, timedelta, date
from pathlib import Path


def run(cmd, env):
    subprocess.check_call(cmd, env=env)


def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days) + 1):
        yield start_date + timedelta(n)


def main():
    parser = argparse.ArgumentParser(description="Batch fetch Polygon minute bars for a date range.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--outdir", type=Path, required=True, help="Output directory")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    api_key = os.getenv("POLYGON_API_KEY")
    if not api_key:
        raise SystemExit("POLYGON_API_KEY is required.")

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    today = date.today()
    if end > today:
        print(f"[cap] end {end} is in the future; capping at today {today}")
        end = today
    args.outdir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    for day in daterange(start, end):
        if day.weekday() >= 5:
            print(f"[skip] {day} is weekend")
            continue
        out = args.outdir / f"{args.symbol}_{day.isoformat()}_minute.csv"
        if out.exists() and not args.overwrite:
            print(f"[skip] {out} exists")
            continue
        cmd = [
            str(Path(__file__).parent / "fetch_minute_bars.py"),
            "--symbol",
            args.symbol,
            "--date",
            day.isoformat(),
            "--out",
            str(out),
        ]
        print(">>", " ".join(cmd))
        # Use the current interpreter to avoid relying on a "python" shim.
        try:
            run([sys.executable, *cmd], env=env)
        except subprocess.CalledProcessError as exc:
            print(f"[warn] fetch failed for {day}: {exc}")


if __name__ == "__main__":
    main()
