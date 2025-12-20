#!/usr/bin/env python3
"""
Inspect Burst Storms
=====================

Analyzes days with high concurrent bursts ("Storms") to determine their nature:
1. Basket Storms: Meme stocks only (GME, AMC, BB, etc.)
2. Market Storms: Broad market volatility (SPY, QQQ, AAPL involved)
3. Idiosyncratic: Isolated events

Calculates "Basket Coherence": How tightly coupled are the meme stocks distinct from the market?
"""

import sys
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
EXPANDED_DIR = BASE_DIR / "data" / "expanded_bars"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "results"

# Define Groups
BASKET_SYMBOLS = ["GME", "AMC", "BB", "KOSS", "TLRY", "CHWY", "PLTR"]
CONTROL_SYMBOLS = ["SPY", "QQQ", "DIA", "IWM", "AAPL", "MSFT", "NVDA", "TSLA"]

def detect_burst_for_day(df: pd.DataFrame) -> dict:
    if len(df) < 100: return {"is_burst": False}
    
    mean_vol = df['volume'].mean()
    max_vol = df['volume'].max()
    volume_spike = max_vol / mean_vol if mean_vol > 0 else 0
    price_range = (df['high'].max() - df['low'].min()) / df['open'].iloc[0]
    
    is_burst = volume_spike > 2.5 and price_range > 0.03
    
    return {
        "is_burst": is_burst,
        "volume_spike": volume_spike,
        "price_range": price_range
    }

def load_all_burst_data(expanded_dir: Path) -> pd.DataFrame:
    all_data = []
    symbol_dirs = [d for d in expanded_dir.iterdir() if d.is_dir()]
    
    print(f"Scanning {len(symbol_dirs)} symbols...")
    
    for symbol_dir in symbol_dirs:
        csv_files = sorted(symbol_dir.glob("*.csv"))
        for csv_file in csv_files:
            try:
                date_str = csv_file.stem.split("_")[1]
                df = pd.read_csv(csv_file)
                if 'close' not in df.columns: continue
                
                res = detect_burst_for_day(df)
                if res["is_burst"]:
                    all_data.append({
                        "date": date_str,
                        "symbol": symbol_dir.name,
                        "is_burst": True,
                        "volume_spike": res["volume_spike"],
                        "price_range": res["price_range"]
                    })
            except: continue
                
    return pd.DataFrame(all_data)

def analyze_storms(df: pd.DataFrame):
    # Pivot to Date x Symbol
    pivot = df.pivot_table(index="date", columns="symbol", values="is_burst", aggfunc='max').fillna(False)
    
    # Calculate Group Participation
    available_basket = [s for s in BASKET_SYMBOLS if s in pivot.columns]
    available_control = [s for s in CONTROL_SYMBOLS if s in pivot.columns]
    
    pivot['basket_count'] = pivot[available_basket].sum(axis=1)
    pivot['control_count'] = pivot[available_control].sum(axis=1)
    pivot['total_bursts'] = pivot['basket_count'] + pivot['control_count']
    
    # Define Storm Types
    # Basket Storm: High Basket count, Low Control count
    # Market Storm: High Control count
    
    pivot['storm_type'] = "Quiet"
    
    for i, row in pivot.iterrows():
        b_count = row['basket_count']
        c_count = row['control_count']
        
        if b_count >= 3 and c_count <= 1:
            pivot.at[i, 'storm_type'] = "PURE_BASKET"
        elif b_count >= 3 and c_count >= 2:
            pivot.at[i, 'storm_type'] = "MIXED_MARKET"
        elif c_count >= 2:
            pivot.at[i, 'storm_type'] = "BROAD_MARKET"
        elif b_count >= 1:
            pivot.at[i, 'storm_type'] = "ISOLATED_BASKET"
            
    # Filter for significant days
    storms = pivot[pivot['total_bursts'] >= 3].sort_index()
    
    return storms, pivot

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("BURST STORM INSPECTION")
    print("Differentiating Basket Mechanics from Market Volatility")
    print("=" * 70)
    
    df = load_all_burst_data(EXPANDED_DIR)
    
    if df.empty:
        print("No data found.")
        return
        
    storms, full_pivot = analyze_storms(df)
    
    print(f"\nTotal Days Analyzed: {len(full_pivot)}")
    print(f"Total Storm Days (>=3 bursts): {len(storms)}")
    
    print("\n>>> STORM TYPE DISTRIBUTION")
    print(full_pivot['storm_type'].value_counts())
    
    print("\n>>> RECENT PURE BASKET STORMS (The 'Signal')")
    pure_basket = storms[storms['storm_type'] == "PURE_BASKET"].sort_index(ascending=False)
    
    # Show last 20
    print(f"{'Date':<12} | {'Basket':<6} | {'Control':<7} | {'Symbols'}")
    print("-" * 60)
    
    for date, row in pure_basket.head(20).iterrows():
        # Get list of bursting symbols
        symbols = [col for col in full_pivot.columns if col not in ['basket_count', 'control_count', 'total_bursts', 'storm_type'] and full_pivot.at[date, col]]
        sym_str = ", ".join(symbols)
        print(f"{date:<12} | {row['basket_count']:<6} | {row['control_count']:<7} | {sym_str}")
        
    print("\n>>> MARKET STORMS (The 'Noise')")
    market_storms = storms[storms['storm_type'].isin(["MIXED_MARKET", "BROAD_MARKET"])].sort_index(ascending=False)
    print(f"Count: {len(market_storms)}")
    if not market_storms.empty:
        print(market_storms.head(5)[['basket_count', 'control_count', 'storm_type']])

    # Save Results
    with open(OUTPUT_DIR / "storm_analysis.json", "w") as f:
        # Convert index to string for JSON
        storms_json = storms.reset_index()
        storms_json['date'] = storms_json['date'].astype(str)
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "storm_counts": full_pivot['storm_type'].value_counts().to_dict(),
            "pure_basket_storms": pure_basket.index.tolist()
        }, f, indent=2)
        
    # Generate Report
    with open(OUTPUT_DIR / "storm_report.md", "w") as f:
        f.write("# Burst Storm Analysis\n\n")
        f.write("## Storm Types\n\n")
        f.write("| Type | Definition | Count |\n")
        f.write("|------|------------|-------|\n")
        for type_name, count in full_pivot['storm_type'].value_counts().items():
            f.write(f"| {type_name} | {count} |\n")
            
        f.write("\n## Pure Basket Storms (Signal)\n")
        f.write("Days where >=3 Meme Stocks burst, but <=1 Control stock burst.\n\n")
        f.write("| Date | Basket | Control | Symbols |\n")
        f.write("|------|--------|---------|---------|\n")
        for date, row in pure_basket.head(50).iterrows():
            symbols = [col for col in full_pivot.columns if col not in ['basket_count', 'control_count', 'total_bursts', 'storm_type'] and full_pivot.at[date, col]]
            # Filter solely for display
            basket_syms = [s for s in symbols if s in BASKET_SYMBOLS]
            f.write(f"| {date} | {row['basket_count']} | {row['control_count']} | {', '.join(basket_syms)} |\n")

if __name__ == "__main__":
    main()
