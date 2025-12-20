#!/usr/bin/env python3
"""
Build a micro sample from an existing price_paths CSV.

This trims a larger sample (e.g., sample_2024-05-13) down to a tiny slice
that is safe to commit and fast for demos/tests.

Usage:
    # After fetching your own local sample (make data ...)
    python tools/build_micro_sample.py \
        --source data/samples/local/gme_20240513/price_paths.csv \
        --rows 600 \
        --out data/samples/micro/price_paths.csv
"""
import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a tiny micro sample for demos/tests.")
    parser.add_argument(
        "--source",
        default="data/samples/local/gme_20240513/price_paths.csv",
        help="Path to the larger price_paths.csv (ideally from make data).",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=600,
        help="Rows to keep (small to keep CI fast).",
    )
    parser.add_argument(
        "--out",
        default="data/samples/micro/price_paths.csv",
        help="Output path for the micro sample.",
    )
    args = parser.parse_args()

    src = Path(args.source)
    if not src.exists():
        raise SystemExit(f"Source file not found: {src}")

    df = pd.read_csv(src, nrows=args.rows)
    if not {"timestamp_us", "price"}.issubset(df.columns):
        raise SystemExit("Source CSV missing required columns: timestamp_us, price")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)

    print(f"Wrote micro sample: {out_path} ({len(df)} rows)")


if __name__ == "__main__":
    main()
