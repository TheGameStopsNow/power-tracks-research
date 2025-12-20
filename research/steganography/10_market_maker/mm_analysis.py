#!/usr/bin/env python3
"""
Phase 7c: Market Maker Signature Analysis
=========================================

Attempts to identify market maker signatures:
1. Quote timing patterns by exchange
2. Size clustering (MMs often use round sizes)
3. Spread patterns
4. Trading fingerprints
"""

import os
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from scipy import stats
from collections import Counter

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "samples"
OUTPUT_DIR = Path(__file__).resolve().parent / "results"

# Known exchange IDs for classification
EXCHANGE_NAMES = {
    "1": "NYSE",
    "2": "NASDAQ",
    "4": "AMEX",
    "11": "NYSE_CHI",
    "12": "NYSE_NAT",
    "15": "IEX",
    "17": "CBOE",
    "18": "EDGX",
    "19": "EDGA",
    "21": "MEMX",
    "OTC": "OTC/ATS"
}


def analyze_exchange_patterns(df: pd.DataFrame) -> dict:
    """Analyze trading patterns by exchange/venue."""
    if "venue" not in df.columns:
        return {"error": "No venue data"}
    
    patterns = {}
    
    for venue in df["venue"].unique():
        venue_df = df[df["venue"] == venue]
        
        if len(venue_df) < 100:
            continue
        
        prices = venue_df["price"].dropna()
        volumes = venue_df["volume"].dropna()
        
        # Price LSB
        price_lsb = (prices * 100).astype(int) % 10
        lsb_counts = np.bincount(price_lsb.astype(int), minlength=10)
        chi2, pval = stats.chisquare(lsb_counts, np.full(10, len(prices) / 10))
        
        # Volume patterns
        round_100 = (volumes % 100 == 0).sum() / len(volumes)
        round_1000 = (volumes % 1000 == 0).sum() / len(volumes)
        
        # Size distribution
        size_bins = pd.cut(volumes, bins=[0, 100, 500, 1000, 5000, np.inf], 
                           labels=["tiny", "small", "medium", "large", "huge"])
        size_dist = size_bins.value_counts(normalize=True).to_dict()
        
        patterns[str(venue)] = {
            "name": EXCHANGE_NAMES.get(str(venue), str(venue)),
            "n_trades": len(venue_df),
            "price_lsb_chi2": float(chi2),
            "price_lsb_pvalue": float(pval),
            "round_100_pct": float(round_100 * 100),
            "round_1000_pct": float(round_1000 * 100),
            "mean_size": float(volumes.mean()),
            "median_size": float(volumes.median()),
            "size_distribution": {k: float(v) for k, v in size_dist.items()}
        }
    
    return patterns


def analyze_timing_by_venue(df: pd.DataFrame) -> dict:
    """Analyze timing patterns by venue."""
    try:
        df["ts"] = pd.to_datetime(df["timestamp"], format="ISO8601")
    except:
        return {"error": "Cannot parse timestamps"}
    
    timing_patterns = {}
    
    for venue in df["venue"].unique():
        venue_df = df[df["venue"] == venue].sort_values("ts")
        
        if len(venue_df) < 100:
            continue
        
        iat = venue_df["ts"].diff().dt.total_seconds().dropna() * 1000  # ms
        iat = iat[(iat > 0) & (iat < 10000)]  # Filter
        
        if len(iat) < 50:
            continue
        
        timing_patterns[str(venue)] = {
            "name": EXCHANGE_NAMES.get(str(venue), str(venue)),
            "mean_iat_ms": float(iat.mean()),
            "median_iat_ms": float(iat.median()),
            "std_iat_ms": float(iat.std()),
            "min_iat_ms": float(iat.min()),
            "pct_under_1ms": float((iat < 1).sum() / len(iat) * 100),
            "pct_under_10ms": float((iat < 10).sum() / len(iat) * 100)
        }
    
    return timing_patterns


def identify_mm_signatures(df: pd.DataFrame) -> dict:
    """Attempt to identify market maker signatures."""
    # Group trades by characteristics
    df["size_bucket"] = pd.cut(df["volume"], 
                                bins=[0, 100, 500, 1000, np.inf], 
                                labels=["tiny", "small", "medium", "large"])
    
    df["price_cents"] = (df["price"] * 100).astype(int) % 100
    
    # Look for repeated patterns
    signatures = []
    
    # Pattern 1: Venue + size bucket combinations
    venue_size = df.groupby(["venue", "size_bucket"]).size()
    top_combos = venue_size.nlargest(10)
    
    for (venue, size), count in top_combos.items():
        signatures.append({
            "type": "venue_size",
            "venue": str(venue),
            "size": str(size),
            "count": int(count),
            "pct": float(count / len(df) * 100)
        })
    
    # Pattern 2: Round price preference by venue
    round_prices = df.groupby("venue").apply(
        lambda x: (x["price_cents"] % 25 == 0).sum() / len(x) * 100
    )
    
    for venue, pct in round_prices.items():
        if pct > 30:  # Significant round price preference
            signatures.append({
                "type": "round_price",
                "venue": str(venue),
                "round_pct": float(pct)
            })
    
    return {
        "n_signatures": len(signatures),
        "top_signatures": signatures[:20]
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    sample_dirs = sorted(DATA_DIR.glob("sample_*"))[:5]  # First 5 days
    
    print("=" * 60)
    print("MARKET MAKER SIGNATURE ANALYSIS")
    print("=" * 60)
    
    all_patterns = []
    
    for sample_dir in sample_dirs:
        trades_files = list(sample_dir.glob("raw_ticks/*_trades.csv"))
        if not trades_files:
            continue
        
        date = sample_dir.name.replace("sample_", "")
        print(f"\n>>> {date}")
        
        df = pd.read_csv(trades_files[0])
        
        if "venue" not in df.columns:
            continue
        
        print(f"  {len(df):,} trades")
        
        exchange_patterns = analyze_exchange_patterns(df)
        timing_patterns = analyze_timing_by_venue(df)
        mm_signatures = identify_mm_signatures(df)
        
        result = {
            "date": date,
            "n_trades": len(df),
            "exchange_patterns": exchange_patterns,
            "timing_by_venue": timing_patterns,
            "mm_signatures": mm_signatures
        }
        all_patterns.append(result)
        
        # Print summary
        print(f"  Venues: {len(exchange_patterns)}")
        print(f"  Signatures: {mm_signatures['n_signatures']}")
    
    # Save results
    with open(OUTPUT_DIR / "mm_analysis.json", "w") as f:
        json.dump({"timestamp": datetime.now().isoformat(), "results": all_patterns}, f, indent=2, default=str)
    
    # Generate report
    with open(OUTPUT_DIR / "mm_report.md", "w") as f:
        f.write("# Market Maker Signature Analysis\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        if all_patterns:
            f.write("## Exchange Pattern Summary\n\n")
            f.write("| Venue | Trades | Round 100 % | Round 1000 % | LSB Anomaly |\n")
            f.write("|-------|--------|-------------|--------------|-------------|\n")
            
            # Aggregate across days
            venue_stats = {}
            for day in all_patterns:
                for venue, stats in day["exchange_patterns"].items():
                    if venue not in venue_stats:
                        venue_stats[venue] = []
                    venue_stats[venue].append(stats)
            
            for venue, stats_list in venue_stats.items():
                name = stats_list[0].get("name", venue)
                trades = sum(s["n_trades"] for s in stats_list)
                r100 = np.mean([s["round_100_pct"] for s in stats_list])
                r1000 = np.mean([s["round_1000_pct"] for s in stats_list])
                anomaly = "✓" if np.mean([s["price_lsb_pvalue"] for s in stats_list]) < 0.05 else ""
                f.write(f"| {name} | {trades:,} | {r100:.1f}% | {r1000:.1f}% | {anomaly} |\n")
            
            f.write("\n## Timing Patterns by Venue\n\n")
            f.write("| Venue | Mean IAT (ms) | <1ms % | <10ms % |\n")
            f.write("|-------|---------------|--------|--------|\n")
            
            for day in all_patterns[:1]:  # First day
                for venue, timing in day["timing_by_venue"].items():
                    if isinstance(timing, dict) and "error" not in timing:
                        f.write(f"| {timing.get('name', venue)} | {timing['mean_iat_ms']:.1f} | {timing['pct_under_1ms']:.1f}% | {timing['pct_under_10ms']:.1f}% |\n")
    
    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
