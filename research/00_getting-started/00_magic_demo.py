#!/usr/bin/env python3
"""
Magic Demo (real data, no sci-fi).

Loads a tiny real sample price-path CSV, finds the top 3 bursts by
z-scored 1-step returns, and saves a PNG plot with the anomalies marked.

Usage:
    python getting-started/00_magic_demo.py \
        --input data/samples/sample_2024-05-13/signals/price_paths.csv \
        --rows 2000 \
        --output getting-started/demo_output.png

Env overrides:
    POWER_TRACKS_PRICE_PATHS   Path to price_paths.csv
    POWER_TRACKS_SAMPLE_ROWS   Rows to read (int)
"""
import argparse
import os
from pathlib import Path
from typing import Iterable, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def load_price_paths(path: Path, rows: int) -> pd.DataFrame:
    df = pd.read_csv(path, nrows=rows)
    if not {"timestamp", "price"}.issubset(df.columns) and not {"timestamp_us", "price"}.issubset(df.columns):
        raise ValueError("price_paths.csv must include timestamp/timestamp_us and price columns")

    # Normalize timestamp column
    if "timestamp_us" not in df.columns and "timestamp" in df.columns:
        # Check if timestamp is already numeric (us) or datetime string
        if pd.api.types.is_numeric_dtype(df["timestamp"]):
             df["timestamp_us"] = df["timestamp"]
        else:
             df["timestamp"] = pd.to_datetime(df["timestamp"])
             df["timestamp_us"] = df["timestamp"].astype(np.int64) // 1000

    df = df.sort_values("timestamp_us").reset_index(drop=True)
    return df


def detect_anomalies(df: pd.DataFrame, top_k: int = 3) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    df["return"] = df["price"].diff()
    df["zscore"] = (df["return"] - df["return"].mean()) / (df["return"].std(ddof=0) + 1e-9)
    anomalies = df.nlargest(top_k, "zscore").copy()
    anomalies["reason"] = "Return spike (z-score)"
    return df, anomalies


def plot_anomalies(df: pd.DataFrame, anomalies: pd.DataFrame, output: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(df["timestamp_us"], df["price"], label="Price path", color="#2563eb", linewidth=1.2)
    ax.scatter(
        anomalies["timestamp_us"],
        anomalies["price"],
        color="#ef4444",
        zorder=5,
        label="Anomaly (top z-score)",
    )
    print("\n    ⚠️  EDUCATIONAL PURPOSE ONLY. NOT FINANCIAL ADVICE. ⚠️\n")
    ax.set_xlabel("timestamp_us")
    ax.set_ylabel("price ($)")
    ax.legend()
    ax.set_title("Power Tracks Demo: GME price path (sample_2024-05-13)")
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150)
    plt.close(fig)


def resolve_input_path(cli_input: Optional[str]) -> Path:
    # Priority: CLI arg > env > local directory > global samples
    if cli_input:
        return Path(cli_input)
    
    env_path = os.environ.get("POWER_TRACKS_PRICE_PATHS")
    if env_path:
        return Path(env_path)

    # Local data check
    local_data = Path(__file__).parent / "data"
    # Check for the specific CSV we know exists or generic name
    local_candidates = list(local_data.glob("*.csv"))
    if local_candidates:
        return local_candidates[0]

    # Global data fallback
    candidates = [
        Path("data/samples/micro/price_paths.csv"),
        Path("data/samples/local/gme_20240513/price_paths.csv"),
        Path("data/samples/gme_20240517/gme-trades-2024-05-17.csv"), # Manifest standard
        Path("data/samples/gme_20240517/trades.csv"), # Fallback
        Path("../../data/samples/gme_20240517/trades.csv"), # Relative from research/00
        Path("../../data/samples/gme_20240517/gme-trades-2024-05-17.csv"),
    ]

    for p in candidates:
        if p.exists():
            return p
            
    raise SystemExit(
        "No price_paths.csv found. Run 'python download_data.py' or provide --input."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Magic Demo using real sample price paths.")
    parser.add_argument(
        "--input",
        default=None,
        help="Path to price_paths.csv (overrides env and auto-discovery).",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=int(os.environ.get("POWER_TRACKS_SAMPLE_ROWS", "2000")),
        help="Rows to read for the demo (keep small for speed).",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).parent / "output/demo_output.png"),
        help="Path to save the plot PNG.",
    )
    args = parser.parse_args()

    input_path = resolve_input_path(args.input).expanduser()

    df = load_price_paths(input_path, args.rows)
    df_full, anomalies = detect_anomalies(df, top_k=3)

    print("=== Power Tracks Magic Demo ===")
    print(f"Source: {input_path}")
    print(f"Rows scanned: {len(df_full)}")
    print("\nTop 3 return spikes (z-score):")
    for _, row in anomalies.iterrows():
        print(
            f"  ts={row['timestamp_us']}  price=${row['price']:.2f}  "
            f"return={row['return']:.5f}  z={row['zscore']:.2f}"
        )

    output_path = Path(args.output)
    plot_anomalies(df_full, anomalies, output_path)
    print(f"\nSaved plot -> {output_path}")
    print("Next: open getting-started/01_magic_demo.ipynb for the guided version.")


if __name__ == "__main__":
    main()
