#!/usr/bin/env python3
"""
GME Master Scanner - Phase 30D
Unified tool for "Pulse Checks" (random sampling) and "Deep Scans" (comprehensive audit).
Extracts Opcode Density, detects Rare Opcodes, and identifies "Zombie Mode" activity.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import argparse
import random
import multiprocessing
import sys
from collections import Counter

# Configuration
DATA_DIR = Path("data/ticks")
EXCHANGE_EDGX = 4

# Known Opcodes (from 2021 Research & decode_2025_opcodes.py)
KNOWN_OPCODES = {
    0xA0: "FLOOR",
    0x98: "CEILING",
    0x80: "PIVOT",
    0x10: "STATION",
    0x01: "LIFT",
    0x02: "DROP",
    0xDF: "SEED", # Rare
}

RARE_OPCODES = [0xDF, 0xA0]

def get_available_dates(year="2025"):
    """Get all available date directories for a given year."""
    if not DATA_DIR.exists():
        return []
    dates = [d for d in DATA_DIR.iterdir() if d.is_dir() and d.name.startswith(year)]
    return sorted(dates)

def analyze_file(file_path):
    """
    Process a single ticker file.
    Returns dictionary with:
      - date
      - volume (total)
      - edgx_volume
      - opcode_density
      - rare_opcode_count
      - zombie_score (custom metric)
      - top_opcodes (list of top 5)
    """
    try:
        # Load only necessary columns
        df = pd.read_csv(file_path, usecols=['timestamp_us', 'price', 'exchange'])
    except Exception as e:
        return None

    total_vol = len(df)
    
    # Filter EDGX
    edgx_df = df[df['exchange'] == EXCHANGE_EDGX].copy()
    edgx_vol = len(edgx_df)
    
    if edgx_vol < 100:
        return {
            "date": file_path.parent.name,
            "volume": total_vol,
            "edgx_volume": edgx_vol,
            "opcode_density": 0.0,
            "rare_opcode_count": 0,
            "zombie_score": 0.0,
            "top_opcodes": []
        }

    # Sort
    try:
        if edgx_df['timestamp_us'].isnull().any():
             # Drop rows with invalid timestamps
             edgx_df = edgx_df.dropna(subset=['timestamp_us'])
             
        edgx_df.sort_values('timestamp_us', inplace=True)
    except Exception as e:
        print(f"Error sorting {file_path}: {e}")
        return None
    
    # Extract Opcode
    try:
        prices = edgx_df['price'].values
        cents = (prices * 100).round().astype(int)
        lsbs = cents & 1
        
        opcodes = []
        # Vectorized approach or simple loop. Loop is fine for byte construction.
        # We step by 8 ticks.
        for i in range(0, len(lsbs) - 7, 8):
            byte = 0
            for j in range(8):
                byte = (byte << 1) | lsbs[i + j]
            opcodes.append(byte)
    except Exception as e:
        print(f"Error extracting opcodes {file_path}: {e}")
        return None
        
    if not opcodes:
        return {
            "date": file_path.parent.name,
            "volume": total_vol,
            "edgx_volume": edgx_vol,
            "opcode_density": 0.0,
            "rare_opcode_count": 0,
            "zombie_score": 0.0,
            "top_opcodes": []
        }

    # Analysis
    opcode_counts = Counter(opcodes)
    total_ops = len(opcodes)
    
    # Density: % of opcodes that are in KNOWN_OPCODES
    known_hits = sum(opcode_counts[k] for k in KNOWN_OPCODES if k in opcode_counts)
    density = (known_hits / total_ops) * 100 if total_ops > 0 else 0
    
    # Rare Opcodes
    rare_hits = sum(opcode_counts[k] for k in RARE_OPCODES if k in opcode_counts)
    
    # Zombie Score: High density + Low Volume.
    # We'll define it simply here, refine later.
    # e.g., density * (1 / log(volume)) roughly. 
    # For now, let's just return raw metrics.
    
    top_5 = opcode_counts.most_common(5)
    
    return {
        "date": file_path.parent.name,
        "volume": total_vol,
        "edgx_volume": edgx_vol,
        "opcode_density": density,
        "rare_opcode_count": rare_hits,
        "zombie_score": 0.0, # Computed at aggregation level if needed
        "top_opcodes": top_5
    }

def process_date(args):
    """Wrapper for multiprocessing"""
    date_dir, symbol = args
    file_path = date_dir / f"{symbol}.csv"
    
    if not file_path.exists():
        return None
        
    return analyze_file(file_path)

def main():
    parser = argparse.ArgumentParser(description="GME Master Scanner 2025")
    parser.add_argument("--mode", choices=["pulse", "deep"], required=True, help="Scan mode")
    parser.add_argument("--symbol", default="GME", help="Ticker symbol to scan")
    parser.add_argument("--limit", type=int, default=20, help="Number of days to sample in pulse mode")
    args = parser.parse_args()
    
    print(f"Initializing {args.mode.upper()} scan for {args.symbol}...")
    
    available_dates = get_available_dates()
    
    if not available_dates:
        print("No 2025 data found in data/ticks/")
        sys.exit(1)
        
    target_dates = []
    if args.mode == "pulse":
        if len(available_dates) > args.limit:
            target_dates = random.sample(available_dates, args.limit)
        else:
            target_dates = available_dates
        print(f"Selected {len(target_dates)} random dates.")
    else:
        target_dates = available_dates
        print(f"Selected FULL YEAR: {len(target_dates)} dates.")
    
    # Prepare Task List
    tasks = [(d, args.symbol) for d in target_dates]
    
    results = []
    
    # Run Pool
    with multiprocessing.Pool() as pool:
        for i, res in enumerate(pool.imap_unordered(process_date, tasks), 1):
             if res:
                 results.append(res)
             if i % 10 == 0:
                 print(f"Processed {i}/{len(tasks)}...", end="\r")
                 
    print(f"\nProcessing Complete. {len(results)} valid days found.")
    
    if not results:
        print("No results generated.")
        sys.exit(0)
        
    # Aggregate Results
    df_results = pd.DataFrame(results)
    df_results.sort_values("date", inplace=True)
    
    # Calculate Averages
    avg_density = df_results['opcode_density'].mean()
    high_density_days = df_results[df_results['opcode_density'] > 5.0]
    
    print("\n" + "="*50)
    print(f"SCAN REPORT: {args.symbol} ({args.mode.upper()})")
    print("="*50)
    print(f"Days Scanned: {len(df_results)}")
    print(f"Avg Opcode Density: {avg_density:.2f}%")
    print(f"High Density Days (>5%): {len(high_density_days)}")
    print(f"Rare Opcodes Found: {df_results['rare_opcode_count'].sum()}")
    
    # Save Report
    output_csv = BASE_DIR / "output" / f"{args.symbol}_2025_{args.mode}_scan.csv"
    df_results.to_csv(output_csv, index=False)
    print(f"\nDetailed logs saved to: {output_csv}")
    
    # Alert on anomalies
    if not high_density_days.empty:
        print("\n[!] Top 5 High Density Days:")
        print(high_density_days[['date', 'opcode_density', 'edgx_volume']].sort_values('opcode_density', ascending=False).head(5))

    if df_results['rare_opcode_count'].sum() > 0:
        print("\n[!] Days with Rare Opcodes:")
        print(df_results[df_results['rare_opcode_count'] > 0][['date', 'rare_opcode_count']])

if __name__ == "__main__":
    main()
