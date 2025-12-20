#!/usr/bin/env python3
"""
Per-Symbol Burst Detection
===========================

Hypothesis: Each stock may have its OWN characteristic burst signature.
GME rejects other stocks NOT because bursts don't exist there,
but because we're looking for GME's specific pattern.

This script:
1. Loads expanded data for multiple symbols
2. Detects bursts in each symbol using a generic burst detector
3. Characterizes each symbol's burst signature
4. Tests if Symbol A's bursts predict Symbol A (not just GME→GAE)

A "burst" is defined as:
- Volume spike > 2x rolling average
- Price move > 2% in 1 hour
- High volatility concentration
"""

import sys
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from scipy import stats
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
EXPANDED_DIR = BASE_DIR / "data" / "expanded_bars"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "results"


def detect_bursts_generic(df: pd.DataFrame, 
                          volume_threshold: float = 2.0,
                          price_threshold: float = 0.02,
                          lookback: int = 20) -> pd.DataFrame:
    """
    Detect bursts using a generic algorithm applicable to any stock.
    
    Returns DataFrame of detected bursts with characteristics.
    """
    
    if len(df) < lookback * 2:
        return pd.DataFrame()
    
    # Calculate rolling metrics
    df = df.copy()
    df['volume_ma'] = df['volume'].rolling(lookback).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma']
    
    # Calculate price changes
    df['return_1bar'] = df['close'].pct_change()
    df['return_1h'] = df['close'].pct_change(60)  # 60 minutes
    df['volatility'] = df['return_1bar'].rolling(lookback).std()
    
    # Detect bursts: volume spike + price move
    bursts = []
    
    i = lookback
    while i < len(df) - 60:
        row = df.iloc[i]
        
        # Check volume spike
        if row['volume_ratio'] < volume_threshold:
            i += 1
            continue
        
        # Check 1-hour price move
        future_slice = df.iloc[i:i+60]
        if len(future_slice) < 60:
            break
            
        max_move = abs(future_slice['close'].max() / row['close'] - 1)
        min_move = abs(future_slice['close'].min() / row['close'] - 1)
        hour_move = max(max_move, min_move)
        
        if hour_move < price_threshold:
            i += 1
            continue
        
        # This is a burst!
        burst = {
            'timestamp': row['timestamp'] if 'timestamp' in df.columns else df.index[i],
            'date': str(row.get('date', df.iloc[i].name)),
            'idx': i,
            'volume_ratio': float(row['volume_ratio']),
            'hour_move': float(hour_move),
            'volatility': float(row['volatility']),
            'direction': 'up' if future_slice['close'].iloc[-1] > row['close'] else 'down',
            'open': float(row['open']),
            'close': float(row['close'])
        }
        bursts.append(burst)
        
        # Skip ahead to avoid counting same burst multiple times
        i += 30
    
    return pd.DataFrame(bursts)


def characterize_burst_signature(bursts_df: pd.DataFrame) -> dict:
    """
    Create a signature profile for the bursts of a symbol.
    """
    
    if bursts_df.empty:
        return {"count": 0}
    
    return {
        "count": len(bursts_df),
        "mean_volume_ratio": float(bursts_df['volume_ratio'].mean()),
        "std_volume_ratio": float(bursts_df['volume_ratio'].std()),
        "mean_hour_move": float(bursts_df['hour_move'].mean()),
        "std_hour_move": float(bursts_df['hour_move'].std()),
        "mean_volatility": float(bursts_df['volatility'].mean()),
        "up_ratio": float((bursts_df['direction'] == 'up').mean()),
        "monthly_distribution": bursts_df.groupby(
            pd.to_datetime(bursts_df['date']).dt.month
        ).size().to_dict() if 'date' in bursts_df.columns else {}
    }


def analyze_symbol(symbol_dir: Path) -> dict:
    """Analyze all data for a single symbol."""
    
    csv_files = sorted(symbol_dir.glob("*.csv"))
    if not csv_files:
        return {"symbol": symbol_dir.name, "error": "No data files"}
    
    all_bursts = []
    days_analyzed = 0
    total_bars = 0
    
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            if 'close' not in df.columns or 'volume' not in df.columns:
                continue
            
            days_analyzed += 1
            total_bars += len(df)
            
            bursts = detect_bursts_generic(df)
            if not bursts.empty:
                bursts['symbol'] = symbol_dir.name
                all_bursts.append(bursts)
                
        except Exception as e:
            continue
    
    if all_bursts:
        combined_bursts = pd.concat(all_bursts, ignore_index=True)
    else:
        combined_bursts = pd.DataFrame()
    
    signature = characterize_burst_signature(combined_bursts)
    signature['symbol'] = symbol_dir.name
    signature['days_analyzed'] = days_analyzed
    signature['total_bars'] = total_bars
    signature['bursts_per_day'] = len(combined_bursts) / days_analyzed if days_analyzed > 0 else 0
    
    return signature


def compare_signatures(signatures: list) -> dict:
    """Compare burst signatures across symbols."""
    
    if len(signatures) < 2:
        return {"error": "Need at least 2 symbols to compare"}
    
    # Filter out symbols with no bursts
    valid = [s for s in signatures if s.get('count', 0) > 0]
    
    if len(valid) < 2:
        return {"error": "Not enough symbols with bursts"}
    
    # Calculate similarity matrix based on signature features
    comparison = {
        "symbols": [s['symbol'] for s in valid],
        "burst_counts": {s['symbol']: s['count'] for s in valid},
        "bursts_per_day": {s['symbol']: s.get('bursts_per_day', 0) for s in valid},
        "volume_ratios": {s['symbol']: s.get('mean_volume_ratio', 0) for s in valid},
        "hour_moves": {s['symbol']: s.get('mean_hour_move', 0) for s in valid},
    }
    
    # Calculate which symbols have similar patterns
    if len(valid) >= 2:
        from itertools import combinations
        similarities = {}
        for s1, s2 in combinations(valid, 2):
            # Simple similarity: correlation of key metrics
            v1 = [s1.get('mean_volume_ratio', 0), s1.get('mean_hour_move', 0), s1.get('up_ratio', 0.5)]
            v2 = [s2.get('mean_volume_ratio', 0), s2.get('mean_hour_move', 0), s2.get('up_ratio', 0.5)]
            
            # Euclidean distance (lower = more similar)
            dist = sum((a - b) ** 2 for a, b in zip(v1, v2)) ** 0.5
            similarities[f"{s1['symbol']}_vs_{s2['symbol']}"] = {
                "distance": float(dist),
                "similar": dist < 1.0
            }
        comparison["similarities"] = similarities
    
    return comparison


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("PER-SYMBOL BURST DETECTION")
    print("Testing if each stock has its own burst signature")
    print("=" * 70)
    
    # Check for expanded data
    if not EXPANDED_DIR.exists():
        print(f"\nNo expanded data found at {EXPANDED_DIR}")
        print("Run download_expanded_data.py first:")
        print("  POLYGON_API_KEY=xxx python scripts/download_expanded_data.py")
        return
    
    # Find all symbol directories
    symbol_dirs = [d for d in EXPANDED_DIR.iterdir() if d.is_dir()]
    
    if not symbol_dirs:
        print(f"No symbol data in {EXPANDED_DIR}")
        return
    
    print(f"\nFound {len(symbol_dirs)} symbols with data")
    
    # Analyze each symbol
    signatures = []
    for symbol_dir in sorted(symbol_dirs):
        print(f"\n>>> Analyzing {symbol_dir.name}")
        sig = analyze_symbol(symbol_dir)
        signatures.append(sig)
        
        if sig.get('count', 0) > 0:
            print(f"  Days: {sig.get('days_analyzed', 0)}")
            print(f"  Bursts: {sig.get('count', 0)}")
            print(f"  Bursts/day: {sig.get('bursts_per_day', 0):.2f}")
            print(f"  Avg volume spike: {sig.get('mean_volume_ratio', 0):.1f}x")
            print(f"  Avg hour move: {sig.get('mean_hour_move', 0):.1%}")
    
    # Compare signatures
    print("\n" + "=" * 70)
    print("SIGNATURE COMPARISON")
    print("=" * 70)
    
    comparison = compare_signatures(signatures)
    
    if "symbols" in comparison:
        print(f"\nSymbols with bursts: {', '.join(comparison['symbols'])}")
        print(f"\nBursts per day:")
        for sym, bpd in sorted(comparison['bursts_per_day'].items(), key=lambda x: -x[1]):
            print(f"  {sym}: {bpd:.2f}")
    
    # Save results
    results = {
        "timestamp": datetime.now().isoformat(),
        "signatures": signatures,
        "comparison": comparison
    }
    
    with open(OUTPUT_DIR / "per_symbol_bursts.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    # Generate report
    with open(OUTPUT_DIR / "per_symbol_bursts_report.md", "w") as f:
        f.write("# Per-Symbol Burst Detection\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Hypothesis\n\n")
        f.write("Each stock may have its OWN characteristic burst signature.\n")
        f.write("GME rejects other stocks not because bursts don't exist,\n")
        f.write("but because we're looking for GME's specific pattern.\n\n")
        
        f.write("## Burst Detection Results\n\n")
        f.write("| Symbol | Days | Bursts | Bursts/Day | Avg Vol Spike | Avg Hour Move |\n")
        f.write("|--------|------|--------|------------|---------------|---------------|\n")
        
        for sig in sorted(signatures, key=lambda x: -x.get('count', 0)):
            if sig.get('count', 0) > 0:
                f.write(f"| {sig['symbol']} | {sig.get('days_analyzed', 0)} ")
                f.write(f"| {sig['count']} | {sig.get('bursts_per_day', 0):.2f} ")
                f.write(f"| {sig.get('mean_volume_ratio', 0):.1f}x ")
                f.write(f"| {sig.get('mean_hour_move', 0):.1%} |\n")
        
        f.write("\n## Key Insights\n\n")
        
        # Analyze the results
        if signatures:
            with_bursts = [s for s in signatures if s.get('count', 0) > 0]
            if with_bursts:
                top_symbol = max(with_bursts, key=lambda x: x.get('bursts_per_day', 0))
                f.write(f"- **Most burst-prone**: {top_symbol['symbol']} ({top_symbol.get('bursts_per_day', 0):.2f}/day)\n")
                
                avg_bpd = np.mean([s.get('bursts_per_day', 0) for s in with_bursts])
                f.write(f"- **Average bursts/day across symbols**: {avg_bpd:.2f}\n")
            else:
                f.write("- No bursts detected in any symbol\n")
    
    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
