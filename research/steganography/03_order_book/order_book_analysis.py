#!/usr/bin/env python3
"""
Steganography Research: Order Book Analysis (Phase 3)
=====================================================

Analyzes bid-ask spread patterns and order book configurations
for potential steganographic encoding.

Since we don't have live Level 2 data, we analyze:
1. Spread patterns from trade data (implied spreads)
2. Volume/price clustering patterns
3. Trade size distribution for codebook potential
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import json

import pandas as pd
import numpy as np
from scipy import stats
from collections import Counter

# Configuration
DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "samples"
OUTPUT_DIR = Path(__file__).resolve().parent / "results"


def analyze_price_clustering(prices: pd.Series) -> dict:
    """Analyze price clustering at specific levels."""
    # Round to various precisions
    cents = (prices * 100).round().astype(int) % 100
    nickels = (prices * 20).round().astype(int) % 20  # $0.05 increments
    dimes = (prices * 10).round().astype(int) % 10    # $0.10 increments
    
    # Count round number preferences
    round_dollar_count = sum(prices.round() == prices.round(2))
    round_50_cent = sum((prices * 2).round() == (prices * 2))
    round_25_cent = sum((prices * 4).round() == (prices * 4))
    
    # Most common price endings
    cents_counter = Counter(cents)
    most_common_cents = cents_counter.most_common(5)
    
    return {
        "round_dollar_pct": float(round_dollar_count / len(prices) * 100),
        "round_50_cent_pct": float(round_50_cent / len(prices) * 100),
        "round_25_cent_pct": float(round_25_cent / len(prices) * 100),
        "most_common_cents": [{"cents": c, "count": n, "pct": n/len(prices)*100} 
                              for c, n in most_common_cents],
        "entropy_cents": float(stats.entropy(list(cents_counter.values())))
    }


def analyze_volume_patterns(volumes: pd.Series) -> dict:
    """Analyze volume clustering and round-lot patterns."""
    # Round lot analysis
    round_100 = sum(volumes % 100 == 0)
    round_1000 = sum(volumes % 1000 == 0)
    odd_lot = sum(volumes < 100)
    
    # Volume digit analysis (last digit)
    last_digit = volumes.astype(int) % 10
    digit_counts = Counter(last_digit)
    
    # Volume size distribution
    small = sum(volumes < 100)
    medium = sum((volumes >= 100) & (volumes < 1000))
    large = sum(volumes >= 1000)
    
    return {
        "round_100_pct": float(round_100 / len(volumes) * 100),
        "round_1000_pct": float(round_1000 / len(volumes) * 100),
        "odd_lot_pct": float(odd_lot / len(volumes) * 100),
        "size_distribution": {
            "small_pct": float(small / len(volumes) * 100),
            "medium_pct": float(medium / len(volumes) * 100),
            "large_pct": float(large / len(volumes) * 100)
        },
        "last_digit_entropy": float(stats.entropy(list(digit_counts.values())))
    }


def analyze_spread_proxies(df: pd.DataFrame) -> dict:
    """Analyze implied spreads from consecutive trade prices."""
    if "price" not in df.columns:
        return {"error": "No price column"}
    
    prices = df["price"].dropna()
    price_changes = prices.diff().dropna()
    
    # Spread proxy: absolute price changes
    abs_changes = np.abs(price_changes)
    
    # Filter to likely spread-related changes (small, non-zero)
    small_changes = abs_changes[(abs_changes > 0) & (abs_changes < prices.median() * 0.01)]
    
    if len(small_changes) == 0:
        return {"error": "Insufficient small price changes"}
    
    # Analyze spread clustering
    rounded_spreads = (small_changes * 100).round()
    spread_counts = Counter(rounded_spreads)
    most_common_spreads = spread_counts.most_common(5)
    
    return {
        "median_spread_proxy": float(np.median(small_changes)),
        "mean_spread_proxy": float(np.mean(small_changes)),
        "spread_std": float(np.std(small_changes)),
        "most_common_spreads_cents": [{"cents": s, "count": c} for s, c in most_common_spreads],
        "unique_spread_values": len(spread_counts),
        "spread_entropy": float(stats.entropy(list(spread_counts.values())))
    }


def analyze_trade_sequences(df: pd.DataFrame) -> dict:
    """Analyze trade sequence patterns for potential encoding."""
    if "price" not in df.columns or "volume" not in df.columns:
        return {"error": "Missing columns"}
    
    # Direction analysis
    price_changes = df["price"].diff()
    upticks = (price_changes > 0).sum()
    downticks = (price_changes < 0).sum()
    zeroticks = (price_changes == 0).sum()
    
    # Run analysis on directions
    directions = np.sign(price_changes.dropna())
    runs = 1
    for i in range(1, len(directions)):
        if directions.iloc[i] != directions.iloc[i-1]:
            runs += 1
    
    # Expected runs for random
    n = len(directions)
    n_pos = (directions > 0).sum()
    n_neg = (directions <= 0).sum()
    if n_pos > 0 and n_neg > 0:
        expected_runs = (2 * n_pos * n_neg) / (n_pos + n_neg) + 1
        runs_ratio = runs / expected_runs
    else:
        runs_ratio = None
    
    return {
        "uptick_pct": float(upticks / len(price_changes.dropna()) * 100),
        "downtick_pct": float(downticks / len(price_changes.dropna()) * 100),
        "zerotick_pct": float(zeroticks / len(price_changes.dropna()) * 100),
        "direction_runs": int(runs),
        "runs_ratio": float(runs_ratio) if runs_ratio else None,
        "interpretation": "More runs than random" if runs_ratio and runs_ratio > 1.1 else 
                         "Fewer runs than random (momentum)" if runs_ratio and runs_ratio < 0.9 else
                         "Random-like"
    }


def analyze_single_day(sample_dir: Path) -> dict:
    """Run order book proxy analysis on a single day."""
    trades_files = list(sample_dir.glob("raw_ticks/*_trades.csv"))
    
    if not trades_files:
        return {"error": f"No trades found"}
    
    df = pd.read_csv(trades_files[0])
    
    if "price" not in df.columns or "volume" not in df.columns:
        return {"error": "Missing required columns"}
    
    date = sample_dir.name.replace("sample_", "")
    
    return {
        "date": date,
        "total_trades": len(df),
        "price_clustering": analyze_price_clustering(df["price"]),
        "volume_patterns": analyze_volume_patterns(df["volume"]),
        "spread_proxy": analyze_spread_proxies(df),
        "trade_sequences": analyze_trade_sequences(df)
    }


def main():
    """Run order book analysis across all trading days."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    sample_dirs = sorted(DATA_DIR.glob("sample_*"))
    
    if not sample_dirs:
        print(f"No sample directories found in {DATA_DIR}")
        return
    
    print(f"Found {len(sample_dirs)} trading days to analyze")
    print("=" * 60)
    
    results = []
    summary = {
        "total_days": 0,
        "high_round_lot_days": 0,
        "high_price_clustering_days": 0,
        "abnormal_runs_days": 0
    }
    
    for sample_dir in sample_dirs:
        print(f"\nAnalyzing {sample_dir.name}...")
        try:
            result = analyze_single_day(sample_dir)
            results.append(result)
            
            if "error" not in result:
                summary["total_days"] += 1
                
                if result["volume_patterns"]["round_100_pct"] > 30:
                    summary["high_round_lot_days"] += 1
                if result["price_clustering"]["round_dollar_pct"] > 5:
                    summary["high_price_clustering_days"] += 1
                if result["trade_sequences"]["runs_ratio"] and result["trade_sequences"]["runs_ratio"] < 0.9:
                    summary["abnormal_runs_days"] += 1
                
                print(f"  Trades: {result['total_trades']:,}")
                print(f"  Round-lot %: {result['volume_patterns']['round_100_pct']:.1f}%")
                print(f"  Round-dollar %: {result['price_clustering']['round_dollar_pct']:.1f}%")
                print(f"  Runs ratio: {result['trade_sequences']['runs_ratio']:.2f}")
        except Exception as e:
            print(f"  Error: {e}")
            results.append({"date": sample_dir.name, "error": str(e)})
    
    # Save results
    output_file = OUTPUT_DIR / "order_book_analysis_results.json"
    with open(output_file, "w") as f:
        json.dump({
            "analysis_timestamp": datetime.now().isoformat(),
            "summary": summary,
            "daily_results": results
        }, f, indent=2)
    
    # Generate report
    report_file = OUTPUT_DIR / "order_book_analysis_report.md"
    with open(report_file, "w") as f:
        f.write("# Order Book Microstructure Analysis (Phase 3)\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Summary\n\n")
        f.write("| Metric | Count | Percentage |\n")
        f.write("|--------|-------|------------|\n")
        f.write(f"| Days analyzed | {summary['total_days']} | 100% |\n")
        f.write(f"| High round-lot days (>30%) | {summary['high_round_lot_days']} | {100*summary['high_round_lot_days']/summary['total_days']:.1f}% |\n")
        f.write(f"| High price clustering | {summary['high_price_clustering_days']} | {100*summary['high_price_clustering_days']/summary['total_days']:.1f}% |\n")
        f.write(f"| Abnormal runs (momentum) | {summary['abnormal_runs_days']} | {100*summary['abnormal_runs_days']/summary['total_days']:.1f}% |\n\n")
        
        f.write("## Interpretation\n\n")
        f.write("- **Round-lot preference**: High percentages indicate algorithmic/institutional trading\n")
        f.write("- **Price clustering**: Tendency to trade at round prices (psychological levels)\n")
        f.write("- **Abnormal runs**: Fewer direction changes than random suggests momentum/trending\n\n")
        
        f.write("## Top Anomalies\n\n")
        sorted_by_round = sorted([r for r in results if "error" not in r], 
                                  key=lambda x: x["volume_patterns"]["round_100_pct"], reverse=True)
        for r in sorted_by_round[:5]:
            f.write(f"### {r['date']}\n")
            f.write(f"- Round-lot: {r['volume_patterns']['round_100_pct']:.1f}%\n")
            f.write(f"- Spread entropy: {r['spread_proxy'].get('spread_entropy', 'N/A')}\n")
            f.write("\n")
    
    print("\n" + "=" * 60)
    print("ORDER BOOK ANALYSIS SUMMARY")
    print("=" * 60)
    print(f"Days analyzed: {summary['total_days']}")
    print(f"High round-lot days: {summary['high_round_lot_days']} ({100*summary['high_round_lot_days']/summary['total_days']:.1f}%)")
    print(f"Abnormal runs days: {summary['abnormal_runs_days']} ({100*summary['abnormal_runs_days']/summary['total_days']:.1f}%)")
    print(f"\nResults saved to: {output_file}")
    print(f"Report saved to: {report_file}")


if __name__ == "__main__":
    main()
