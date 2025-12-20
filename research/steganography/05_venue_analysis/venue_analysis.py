#!/usr/bin/env python3
"""
Steganography Research: Venue-Based Anomaly Analysis
=====================================================

Analyzes trading patterns by venue (EDGX, OTC, standard exchanges) for:
1. Venue-specific LSB patterns
2. Cross-venue timing correlations
3. Venue switching as potential encoding
4. Price/volume anomalies by venue type

Exchange ID Reference (Polygon SIP):
- 1: NYSE
- 2: NASDAQ
- 4: NYSE MKT (AMEX)
- 11: NYSE Chicago
- 12: NYSE National
- 15: IEX
- 17: CBOE
- 18: EDGX
- 19: EDGA
- 21: MEMX
- OTC: Off-exchange/Dark pools
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from scipy import stats
from collections import Counter

# Configuration
DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "samples"
OUTPUT_DIR = Path(__file__).resolve().parent / "results"

# Venue classification
VENUE_TYPES = {
    "OTC": "dark_pool",
    "1": "exchange",
    "2": "exchange",
    "4": "exchange",
    "9": "exchange",
    "10": "exchange",
    "11": "exchange",
    "12": "exchange",
    "15": "iex",
    "17": "cboe",
    "18": "edgx",
    "19": "edga",
    "20": "exchange",
    "21": "memx",
    "CBOE": "cboe",
    "EDGX": "edgx",
}


def classify_venue(venue: str) -> str:
    """Classify venue into category."""
    return VENUE_TYPES.get(str(venue), "other")


def analyze_venue_lsb(df: pd.DataFrame, venue_filter: str = None) -> dict:
    """Analyze LSB patterns for a specific venue or all data."""
    subset = df if venue_filter is None else df[df["venue"] == venue_filter]
    
    if len(subset) < 100:
        return {"error": "Insufficient data", "count": len(subset)}
    
    prices = subset["price"].dropna()
    volumes = subset["volume"].dropna()
    
    # Price LSB (cents digit)
    price_lsb = (prices * 100).astype(int) % 10
    lsb_counts = np.bincount(price_lsb.values, minlength=10)
    expected = np.full(10, len(prices) / 10)
    chi2, p_value = stats.chisquare(lsb_counts, expected)
    
    # Entropy
    probs = lsb_counts / len(prices)
    entropy = stats.entropy(probs, base=2)
    max_entropy = np.log2(10)
    
    return {
        "count": len(subset),
        "price_lsb_chi2": float(chi2),
        "price_lsb_pvalue": float(p_value),
        "price_lsb_significant": bool(p_value < 0.05),
        "entropy": float(entropy),
        "normalized_entropy": float(entropy / max_entropy),
        "lsb_distribution": lsb_counts.tolist(),
        "mean_price": float(prices.mean()),
        "mean_volume": float(volumes.mean())
    }


def analyze_cross_venue_timing(df: pd.DataFrame) -> dict:
    """Analyze timing patterns between venues."""
    # Sort by timestamp
    df = df.sort_values("timestamp").reset_index(drop=True)
    
    # Parse timestamps
    df["ts"] = pd.to_datetime(df["timestamp"], format="ISO8601")
    
    # Calculate venue-to-venue transitions
    venue_transitions = []
    for i in range(1, len(df)):
        if df.iloc[i]["venue"] != df.iloc[i-1]["venue"]:
            delta_ns = (df.iloc[i]["ts"] - df.iloc[i-1]["ts"]).total_seconds() * 1e6
            venue_transitions.append({
                "from": str(df.iloc[i-1]["venue"]),
                "to": str(df.iloc[i]["venue"]),
                "delta_us": delta_ns
            })
    
    if not venue_transitions:
        return {"error": "No venue transitions found"}
    
    transitions_df = pd.DataFrame(venue_transitions)
    
    # Most common transitions
    transition_counts = Counter([(t["from"], t["to"]) for t in venue_transitions])
    top_transitions = transition_counts.most_common(10)
    
    # Timing by transition type
    transition_timing = {}
    for (from_v, to_v), count in top_transitions[:5]:
        subset = transitions_df[(transitions_df["from"] == from_v) & 
                                 (transitions_df["to"] == to_v)]["delta_us"]
        if len(subset) > 10:
            transition_timing[f"{from_v}->{to_v}"] = {
                "count": int(count),
                "mean_us": float(subset.mean()),
                "median_us": float(subset.median()),
                "std_us": float(subset.std())
            }
    
    # OTC to exchange timing (potential front-running signal)
    otc_to_exchange = transitions_df[
        (transitions_df["from"] == "OTC") & 
        (transitions_df["to"] != "OTC")
    ]["delta_us"]
    
    exchange_to_otc = transitions_df[
        (transitions_df["from"] != "OTC") & 
        (transitions_df["to"] == "OTC")
    ]["delta_us"]
    
    return {
        "total_transitions": len(venue_transitions),
        "unique_transition_types": len(transition_counts),
        "top_transitions": [{"from": f, "to": t, "count": c} 
                            for (f, t), c in top_transitions],
        "transition_timing": transition_timing,
        "otc_to_exchange": {
            "count": len(otc_to_exchange),
            "mean_us": float(otc_to_exchange.mean()) if len(otc_to_exchange) > 0 else None,
            "median_us": float(otc_to_exchange.median()) if len(otc_to_exchange) > 0 else None
        },
        "exchange_to_otc": {
            "count": len(exchange_to_otc),
            "mean_us": float(exchange_to_otc.mean()) if len(exchange_to_otc) > 0 else None,
            "median_us": float(exchange_to_otc.median()) if len(exchange_to_otc) > 0 else None
        }
    }


def analyze_venue_sequence_patterns(df: pd.DataFrame) -> dict:
    """Analyze venue sequences for potential encoding patterns."""
    df = df.sort_values("timestamp").reset_index(drop=True)
    
    venues = df["venue"].astype(str).values
    
    # N-gram analysis
    bigrams = Counter(zip(venues[:-1], venues[1:]))
    trigrams = Counter(zip(venues[:-2], venues[1:-1], venues[2:]))
    
    # Entropy of venue sequence
    venue_counts = Counter(venues)
    probs = np.array(list(venue_counts.values())) / len(venues)
    venue_entropy = stats.entropy(probs, base=2)
    
    # Runs test on venue changes
    changes = [1 if venues[i] != venues[i-1] else 0 for i in range(1, len(venues))]
    runs = 1
    for i in range(1, len(changes)):
        if changes[i] != changes[i-1]:
            runs += 1
    
    # Expected runs
    n1 = sum(changes)
    n0 = len(changes) - n1
    if n1 > 0 and n0 > 0:
        expected_runs = (2 * n1 * n0) / (n1 + n0) + 1
        runs_ratio = runs / expected_runs
    else:
        runs_ratio = None
    
    return {
        "unique_venues": len(venue_counts),
        "venue_distribution": dict(venue_counts.most_common(10)),
        "venue_entropy": float(venue_entropy),
        "top_bigrams": [{"pair": list(k), "count": v} 
                        for k, v in bigrams.most_common(5)],
        "runs_in_sequence": runs,
        "runs_ratio": float(runs_ratio) if runs_ratio else None,
        "interpretation": "More switching than random" if runs_ratio and runs_ratio > 1.1 else
                         "Pattern detected (less switching)" if runs_ratio and runs_ratio < 0.9 else
                         "Random-like"
    }


def analyze_venue_price_divergence(df: pd.DataFrame) -> dict:
    """Check for price divergence between venues (potential arbitrage/signaling)."""
    # Group by venue and get price stats
    venue_stats = df.groupby("venue").agg({
        "price": ["count", "mean", "std", "min", "max"],
        "volume": ["sum", "mean"]
    })
    
    venue_stats.columns = ["_".join(col) for col in venue_stats.columns]
    venue_stats = venue_stats.reset_index()
    
    # Calculate price divergence
    overall_mean = df["price"].mean()
    
    divergences = []
    for _, row in venue_stats.iterrows():
        if row["price_count"] >= 100:
            divergence = (row["price_mean"] - overall_mean) / overall_mean * 100
            divergences.append({
                "venue": str(row["venue"]),
                "count": int(row["price_count"]),
                "mean_price": float(row["price_mean"]),
                "divergence_pct": float(divergence),
                "volume_share": float(row["volume_sum"] / df["volume"].sum() * 100)
            })
    
    divergences.sort(key=lambda x: abs(x["divergence_pct"]), reverse=True)
    
    return {
        "overall_mean_price": float(overall_mean),
        "venue_divergences": divergences[:10],
        "max_divergence_pct": divergences[0]["divergence_pct"] if divergences else 0
    }


def analyze_single_day(sample_dir: Path) -> dict:
    """Run full venue analysis on a single day."""
    trades_files = list(sample_dir.glob("raw_ticks/*_trades.csv"))
    
    if not trades_files:
        return {"error": "No trades found"}
    
    df = pd.read_csv(trades_files[0])
    
    required_cols = ["timestamp", "price", "volume", "venue"]
    if not all(col in df.columns for col in required_cols):
        return {"error": "Missing required columns"}
    
    date = sample_dir.name.replace("sample_", "")
    
    # Overall LSB by venue category
    venue_lsb = {}
    for venue in df["venue"].unique():
        venue_lsb[str(venue)] = analyze_venue_lsb(df, venue)
    
    # Categorize venues
    df["venue_type"] = df["venue"].apply(classify_venue)
    venue_type_lsb = {}
    for venue_type in df["venue_type"].unique():
        subset = df[df["venue_type"] == venue_type]
        if len(subset) >= 100:
            venue_type_lsb[venue_type] = analyze_venue_lsb(subset)
    
    return {
        "date": date,
        "total_trades": len(df),
        "venue_lsb": venue_lsb,
        "venue_type_lsb": venue_type_lsb,
        "cross_venue_timing": analyze_cross_venue_timing(df.head(50000)),  # Limit for performance
        "venue_sequences": analyze_venue_sequence_patterns(df.head(50000)),
        "price_divergence": analyze_venue_price_divergence(df)
    }


def main():
    """Run venue-based analysis."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    sample_dirs = sorted(DATA_DIR.glob("sample_*"))
    
    if not sample_dirs:
        print(f"No sample directories found in {DATA_DIR}")
        return
    
    print("=" * 60)
    print("VENUE-BASED ANOMALY ANALYSIS")
    print("=" * 60)
    
    results = []
    summary = {
        "total_days": 0,
        "otc_dominant_days": 0,
        "high_otc_anomaly_days": 0,
        "edgx_anomaly_days": 0,
        "cross_venue_pattern_days": 0
    }
    
    for sample_dir in sample_dirs:
        print(f"\nAnalyzing {sample_dir.name}...")
        try:
            result = analyze_single_day(sample_dir)
            results.append(result)
            
            if "error" not in result:
                summary["total_days"] += 1
                
                # Check OTC dominance
                if "dark_pool" in result.get("venue_type_lsb", {}):
                    otc_data = result["venue_type_lsb"]["dark_pool"]
                    if otc_data.get("count", 0) > result["total_trades"] * 0.3:
                        summary["otc_dominant_days"] += 1
                    if otc_data.get("price_lsb_significant"):
                        summary["high_otc_anomaly_days"] += 1
                
                # Check EDGX
                if "edgx" in result.get("venue_type_lsb", {}):
                    if result["venue_type_lsb"]["edgx"].get("price_lsb_significant"):
                        summary["edgx_anomaly_days"] += 1
                
                # Check cross-venue patterns
                if result.get("venue_sequences", {}).get("runs_ratio", 1) < 0.9:
                    summary["cross_venue_pattern_days"] += 1
                
                print(f"  Trades: {result['total_trades']:,}")
                print(f"  Unique venues: {result['venue_sequences'].get('unique_venues', 0)}")
                
        except Exception as e:
            print(f"  Error: {e}")
            results.append({"date": sample_dir.name, "error": str(e)})
    
    # Save results
    output_file = OUTPUT_DIR / "venue_analysis_results.json"
    with open(output_file, "w") as f:
        json.dump({
            "analysis_timestamp": datetime.now().isoformat(),
            "summary": summary,
            "daily_results": results
        }, f, indent=2, default=str)
    
    # Generate report
    report_file = OUTPUT_DIR / "venue_analysis_report.md"
    generate_report(results, summary, report_file)
    
    print("\n" + "=" * 60)
    print("VENUE ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"Days analyzed: {summary['total_days']}")
    print(f"OTC-dominant days: {summary['otc_dominant_days']}")
    print(f"High OTC anomaly days: {summary['high_otc_anomaly_days']}")
    print(f"Cross-venue pattern days: {summary['cross_venue_pattern_days']}")
    print(f"\nResults saved to: {output_file}")


def generate_report(results: list, summary: dict, report_file: Path):
    """Generate markdown report."""
    with open(report_file, "w") as f:
        f.write("# Venue-Based Anomaly Analysis\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Summary\n\n")
        f.write("| Metric | Count | Percentage |\n")
        f.write("|--------|-------|------------|\n")
        f.write(f"| Days analyzed | {summary['total_days']} | 100% |\n")
        if summary['total_days'] > 0:
            f.write(f"| OTC-dominant days (>30%) | {summary['otc_dominant_days']} | {100*summary['otc_dominant_days']/summary['total_days']:.1f}% |\n")
            f.write(f"| OTC LSB anomaly days | {summary['high_otc_anomaly_days']} | {100*summary['high_otc_anomaly_days']/summary['total_days']:.1f}% |\n")
            f.write(f"| EDGX anomaly days | {summary['edgx_anomaly_days']} | {100*summary['edgx_anomaly_days']/summary['total_days']:.1f}% |\n")
            f.write(f"| Cross-venue pattern days | {summary['cross_venue_pattern_days']} | {100*summary['cross_venue_pattern_days']/summary['total_days']:.1f}% |\n\n")
        
        f.write("## Venue Types\n\n")
        f.write("| Type | Description |\n")
        f.write("|------|-------------|\n")
        f.write("| OTC/Dark Pool | Off-exchange, less transparent |\n")
        f.write("| EDGX | CBOE EDGX Exchange |\n")
        f.write("| IEX | Investor's Exchange (speed bump) |\n")
        f.write("| Exchange | NYSE, NASDAQ, etc. |\n\n")
        
        f.write("## Cross-Venue Timing Patterns\n\n")
        valid_results = [r for r in results if "error" not in r]
        if valid_results:
            r = valid_results[0]  # Use first day as example
            timing = r.get("cross_venue_timing", {})
            if timing.get("transition_timing"):
                f.write("### Transition Timing (First Day Sample)\n\n")
                f.write("| Transition | Count | Mean (µs) | Median (µs) |\n")
                f.write("|------------|-------|-----------|-------------|\n")
                for trans, data in timing["transition_timing"].items():
                    f.write(f"| {trans} | {data['count']} | {data['mean_us']:.0f} | {data['median_us']:.0f} |\n")
                f.write("\n")
        
        f.write("## Potential Anomalies\n\n")
        for r in valid_results:
            if r.get("venue_sequences", {}).get("runs_ratio", 1) < 0.9:
                f.write(f"### {r['date']} ⚠️ Low runs ratio\n")
                f.write(f"- Runs ratio: {r['venue_sequences']['runs_ratio']:.2f}\n")
                f.write(f"- Interpretation: {r['venue_sequences']['interpretation']}\n\n")
    
    print(f"Report saved to: {report_file}")


if __name__ == "__main__":
    main()
