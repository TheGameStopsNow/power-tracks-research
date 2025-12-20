#!/usr/bin/env python3
"""
Comprehensive Robustness Analysis
==================================

Answer the critical questions:
1. How often do Power Track signals occur?
2. How many stocks show this pattern?
3. How long has it been working?
4. Is the edge consistent across time and symbols?
"""

import sys
from pathlib import Path
from datetime import datetime
import json
import re
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
SELECTIVITY_DIR = BASE_DIR / "pipelines" / "01_selectivity"
CLUSTER_DIR = BASE_DIR / "pipelines" / "02_clusters_gating"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "results"


def analyze_tisa_signature_coverage():
    """Analyze which dates and symbols have K-Spike signature data."""
    
    # Find all TISA spike signature files
    signature_files = list(SELECTIVITY_DIR.glob("tisa_spike_signatures_*.json"))
    
    coverage = defaultdict(lambda: {"dates": set(), "file_count": 0})
    date_symbol_matrix = defaultdict(set)
    
    for file in signature_files:
        # Parse filename: tisa_spike_signatures_GME_vs_SYMBOL_DATE.json
        match = re.search(r'tisa_spike_signatures_GME_vs_([A-Z0-9_]+)_(\d{4}-\d{2}-\d{2})\.json', file.name)
        if match:
            symbol = match.group(1)
            date = match.group(2)
            
            coverage[symbol]["dates"].add(date)
            coverage[symbol]["file_count"] += 1
            date_symbol_matrix[date].add(symbol)
    
    # Convert sets to lists for JSON serialization
    coverage_summary = {
        symbol: {
            "dates": sorted(list(data["dates"])),
            "date_count": len(data["dates"]),
            "file_count": data["file_count"]
        }
        for symbol, data in coverage.items()
    }
    
    date_coverage = {
        date: {
            "symbols": sorted(list(symbols)),
            "symbol_count": len(symbols)
        }
        for date, symbols in sorted(date_symbol_matrix.items())
    }
    
    return coverage_summary, date_coverage


def analyze_signal_frequency():
    """Determine how often Power Track signals fire."""
    
    # Read gating analysis
    gating_file = CLUSTER_DIR / "GATING_ANALYSIS.md"
    if not gating_file.exists():
        return None
    
    text = gating_file.read_text()
    
    # Extract N values using regex
    # Looking for pattern: | Gated (Cluster + Sig) | 58 |
    match = re.search(r'Gated.*?\|\s*(\d+)\s*\|', text)
    gated_n = int(match.group(1)) if match else None
    
    match_ungated = re.search(r'Ungated.*?\|\s*(\d+)\s*\|', text)
    ungated_n = int(match_ungated.group(1)) if match_ungated else None
    
    if gated_n and ungated_n:
        firing_rate = gated_n / ungated_n
        return {
            "gated_signals": gated_n,
            "total_bursts": ungated_n,
            "firing_rate": firing_rate,
            "interpretation": f"{firing_rate:.1%} of bursts pass the filter"
        }
    
    return None


def check_temporal_consistency():
    """Check if the edge has been tested across different time periods."""
    
    # Read holdout test
    holdout_file = CLUSTER_DIR / "gating_holdout.json"
    if not holdout_file.exists():
        return None
    
    with open(holdout_file) as f:
        holdout = json.load(f)
    
    return {
        "test_period": f"{holdout.get('test_start')} to {holdout.get('test_end')}",
        "test_days": holdout.get('N', 0),
        "p_value": holdout.get('p_value', 0),
        "significant": holdout.get('p_value', 1) < 0.05
    }


def estimate_signal_frequency_from_samples():
    """Estimate how often signals occur from available samples."""
    
    # Count sample days
    samples_dir = BASE_DIR / "data" / "samples"
    sample_dirs = list(samples_dir.glob("sample_*"))
    
    date_pattern = re.compile(r'sample_(\d{4}-\d{2}-\d{2})')
    dates = []
    for d in sample_dirs:
        match = date_pattern.search(d.name)
        if match:
            dates.append(match.group(1))
    
    if not dates:
        return None
    
    dates = sorted(dates)
    
    return {
        "total_days_sampled": len(dates),
        "date_range": f"{dates[0]} to {dates[-1]}",
        "dates": dates
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("COMPREHENSIVE ROBUSTNESS ANALYSIS")
    print("=" * 70)
    
    results = {}
    
    # ============================================================
    # 1. CROSS-SYMBOL COVERAGE
    # ============================================================
    print("\n" + "=" * 70)
    print("1. CROSS-SYMBOL COVERAGE (K-Spike Signatures)")
    print("=" * 70)
    
    symbol_coverage, date_coverage = analyze_tisa_signature_coverage()
    
    # Top symbols by coverage
    top_symbols = sorted(
        symbol_coverage.items(),
        key=lambda x: x[1]["date_count"],
        reverse=True
    )[:10]
    
    print(f"\nTotal symbols tested: {len(symbol_coverage)}")
    print(f"Total dates covered: {len(date_coverage)}")
    print(f"\nTop 10 symbols by date coverage:")
    for symbol, data in top_symbols:
        print(f"  {symbol}: {data['date_count']} dates")
    
    results["cross_symbol"] = {
        "total_symbols": len(symbol_coverage),
        "total_dates": len(date_coverage),
        "symbol_coverage": symbol_coverage,
        "date_coverage": date_coverage,
        "top_symbols": [
            {"symbol": s, "dates": d["date_count"]}
            for s, d in top_symbols
        ]
    }
    
    # ============================================================
    # 2. TEMPORAL COVERAGE
    # ============================================================
    print("\n" + "=" * 70)
    print("2. TEMPORAL COVERAGE")
    print("=" * 70)
    
    sample_info = estimate_signal_frequency_from_samples()
    if sample_info:
        print(f"\nData samples available:")
        print(f"  Days sampled: {sample_info['total_days_sampled']}")
        print(f"  Date range: {sample_info['date_range']}")
        results["temporal_coverage"] = sample_info
    
    # ============================================================
    # 3. SIGNAL FREQUENCY
    # ============================================================
    print("\n" + "=" * 70)
    print("3. SIGNAL FREQUENCY")
    print("=" * 70)
    
    freq = analyze_signal_frequency()
    if freq:
        print(f"\nGated signals: {freq['gated_signals']}")
        print(f"Total bursts: {freq['total_bursts']}")
        print(f"Firing rate: {freq['firing_rate']:.1%}")
        print(f"  -> {freq['interpretation']}")
        
        # Estimate signals per day
        if sample_info:
            bursts_per_day = freq['total_bursts'] / sample_info['total_days_sampled']
            signals_per_day = freq['gated_signals'] / sample_info['total_days_sampled']
            print(f"\nEstimated frequency:")
            print(f"  Bursts per day: {bursts_per_day:.1f}")
            print(f"  Gated signals per day: {signals_per_day:.1f}")
            
            freq["bursts_per_day"] = bursts_per_day
            freq["signals_per_day"] = signals_per_day
        
        results["signal_frequency"] = freq
    
    # ============================================================
    # 4. OUT-OF-SAMPLE VALIDATION
    # ============================================================
    print("\n" + "=" * 70)
    print("4. OUT-OF-SAMPLE VALIDATION")
    print("=" * 70)
    
    temporal = check_temporal_consistency()
    if temporal:
        print(f"\nHoldout test period: {temporal['test_period']}")
        print(f"P-value: {temporal['p_value']:.6f}")
        print(f"Statistically significant: {temporal['significant']}")
        results["out_of_sample"] = temporal
    
    # ============================================================
    # 5. ROBUSTNESS SUMMARY
    # ============================================================
    print("\n" + "=" * 70)
    print("ROBUSTNESS SUMMARY")
    print("=" * 70)
    
    summary = {
        "symbols_tested": len(symbol_coverage),
        "dates_tested": len(date_coverage) if date_coverage else 0,
        "date_range": f"{sorted(date_coverage.keys())[0]} to {sorted(date_coverage.keys())[-1]}" if date_coverage else "Unknown",
        "signals_per_day": freq.get("signals_per_day", 0) if freq else 0,
        "out_of_sample_validated": temporal["significant"] if temporal else False,
        "p_value": temporal["p_value"] if temporal else None
    }
    
    results["summary"] = summary
    
    print(f"\n✓ Tested across {summary['symbols_tested']} symbols")
    print(f"✓ Tested across {summary['dates_tested']} dates")
    print(f"✓ Date range: {summary['date_range']}")
    print(f"✓ Signals fire ~{summary['signals_per_day']:.1f} times per day")
    print(f"✓ Out-of-sample validated: {summary['out_of_sample_validated']}")
    
    # Critical assessment
    print("\n" + "=" * 70)
    print("CRITICAL ASSESSMENT")
    print("=" * 70)
    
    issues = []
    
    # Check date range
    if date_coverage:
        dates = sorted(date_coverage.keys())
        date_span_days = (pd.to_datetime(dates[-1]) - pd.to_datetime(dates[0])).days
        if date_span_days < 180:
            issues.append(f"Limited time span: only {date_span_days} days")
    
    # Check signal frequency
    if freq and freq.get("signals_per_day", 0) < 1:
        issues.append(f"Low signal frequency: {freq['signals_per_day']:.1f} per day")
    
    # Check symbol diversity
    if len(symbol_coverage) < 20:
        issues.append(f"Limited symbol coverage: only {len(symbol_coverage)} symbols")
    
    if issues:
        print("\n⚠️ ROBUSTNESS CONCERNS:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\n✅ No major robustness concerns detected")
    
    results["concerns"] = issues
    
    # Save results
    with open(OUTPUT_DIR / "robustness_analysis.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    # Generate report
    with open(OUTPUT_DIR / "robustness_report.md", "w") as f:
        f.write("# Power Tracks Robustness Analysis\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Summary\n\n")
        f.write(f"| Metric | Value |\n")
        f.write(f"|--------|-------|\n")
        f.write(f"| Symbols Tested | {summary['symbols_tested']} |\n")
        f.write(f"| Dates Tested | {summary['dates_tested']} |\n")
        f.write(f"| Date Range | {summary['date_range']} |\n")
        f.write(f"| Signals per Day | {summary['signals_per_day']:.1f} |\n")
        f.write(f"| Out-of-Sample p-value | {summary['p_value']:.6f} |\n")
        
        f.write("\n## Cross-Symbol Coverage\n\n")
        f.write(f"Tested GME patterns against {len(symbol_coverage)} symbols:\n\n")
        for symbol, data in top_symbols:
            f.write(f"- **{symbol}**: {data['dates']} dates\n")
        
        f.write("\n## Temporal Coverage\n\n")
        if sample_info:
            f.write(f"- **Days sampled**: {sample_info['total_days_sampled']}\n")
            f.write(f"- **Date range**: {sample_info['date_range']}\n")
        
        f.write("\n## Signal Frequency\n\n")
        if freq:
            f.write(f"- **Total bursts**: {freq['total_bursts']}\n")
            f.write(f"- **Gated signals**: {freq['gated_signals']}\n")
            f.write(f"- **Firing rate**: {freq['firing_rate']:.1%}\n")
            f.write(f"- **Signals per day**: ~{freq.get('signals_per_day', 0):.1f}\n")
        
        f.write("\n## Robustness Assessment\n\n")
        if issues:
            f.write("### ⚠️ Concerns\n\n")
            for issue in issues:
                f.write(f"- {issue}\n")
        else:
            f.write("### ✅ No Major Concerns\n\n")
            f.write("The signal appears robust across available data.\n")
    
    print("\n" + "=" * 70)
    print("ROBUSTNESS ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
