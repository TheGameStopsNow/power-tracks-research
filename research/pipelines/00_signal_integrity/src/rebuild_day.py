#!/usr/bin/env python3
"""
Full rebuild for a given date:
- Fetch ticks from Polygon (requires POLYGON_API_KEY)
- Encode ticks -> frames (no cap by default)
- Decode frames -> signals
- Write per-day SHA256SUMS for all artifacts

Usage:
  POLYGON_API_KEY=... .venv/bin/python scripts/rebuild_day.py --symbol GME --date 2024-05-14
"""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import List


ROOT = Path(__file__).parent.parent


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def write_sha256sums(files: List[Path], sha_path: Path):
    sha_path.parent.mkdir(parents=True, exist_ok=True)
    with open(sha_path, "w") as f:
        f.write(f"# SHA256 Checksums for Power Tracks Sample Dataset ({sha_path.parent.name})\n")
        f.write("# Generated automatically - DO NOT EDIT MANUALLY\n\n")
        for p in files:
            f.write(f"{sha256_file(p)}  {p.relative_to(sha_path.parent)}\n")


def run(cmd: List[str], env=None):
    print(">>", " ".join(cmd))
    subprocess.check_call(cmd, env=env)


def main():
    parser = argparse.ArgumentParser(description="Rebuild a sample day end-to-end.")
    parser.add_argument("--symbol", required=True, help="Symbol, e.g., GME")
    parser.add_argument("--date", required=True, help="Date YYYY-MM-DD")
    parser.add_argument("--max-ticks", type=int, default=0, help="Optional cap; 0 = no cap")
    parser.add_argument("--chunk-size", type=int, default=0, help="Ticks per frame; 0 = all in one frame")
    args = parser.parse_args()

    sample_dir = ROOT / f"sample_{args.date}"
    raw_dir = sample_dir / "raw_ticks"
    decoded_dir = sample_dir / "decoded_frames"
    signals_dir = sample_dir / "signals"
    sha_path = sample_dir / "SHA256SUMS"

    # Fetch ticks
    env = os.environ.copy()
    api_key = env.get("POLYGON_API_KEY")
    if not api_key:
        raise SystemExit("POLYGON_API_KEY is required in the environment.")

    run(
        [
            str(ROOT / ".venv/bin/python"),
            str(ROOT / "scripts/fetch_sample_data.py"),
            "--symbol",
            args.symbol,
            "--date",
            args.date,
            "--output-dir",
            str(raw_dir),
        ],
        env=env,
    )

    # Encode
    run(
        [
            str(ROOT / ".venv/bin/python"),
            str(ROOT / "scripts/raw_to_signals.py"),
            "--input",
            str(raw_dir / f"{args.symbol}_{args.date}_trades.csv"),
            "--output",
            str(decoded_dir / "frames.bin"),
            "--format",
            "binary",
            "--chunk-size",
            str(args.chunk_size),
            "--max-ticks",
            str(args.max_ticks),
        ],
        env=env,
    )

    # Decode
    run(
        [
            str(ROOT / ".venv/bin/python"),
            str(ROOT / "scripts/raw_to_signals.py"),
            "--input",
            str(decoded_dir / "frames.bin"),
            "--output",
            str(signals_dir / "price_paths.csv"),
            "--format",
            "csv",
            "--decode",
        ],
        env=env,
    )

    # SHA256
    files = [
        raw_dir / f"{args.symbol}_{args.date}_trades.csv",
        decoded_dir / "frames.bin",
        decoded_dir / "frames.csv",
        signals_dir / "price_paths.csv",
    ]
    # optional files
    for extra in ["price_paths.parquet", "price_paths.sqlite"]:
        p = signals_dir / extra
        if p.exists():
            files.append(p)
    write_sha256sums(files, sha_path)
    print(f"Wrote SHA256SUMS: {sha_path}")


if __name__ == "__main__":
    main()
