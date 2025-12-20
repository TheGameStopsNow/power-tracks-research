#!/usr/bin/env python3
"""
Second-Pass Forensic Analysis
==============================

Based on initial findings:
1. 63.26% of price deltas are ZERO - this is highly unusual!
2. 5.31% are MIRROR patterns
3. XOR encoding has much LOWER entropy than delta

This script digs deeper into these anomalies to understand:
- Why are 63% of deltas zero? (Repeated prices = unusual)
- Can the zero deltas encode hidden bits? (1 = zero, 0 = non-zero)
- What does the mirror pattern sequence mean?
"""

import sys
from pathlib import Path
from datetime import datetime
import json
import struct
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from scipy import stats
from collections import Counter

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "samples"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "results"


def analyze_zero_deltas(df: pd.DataFrame) -> dict:
    """Deep analysis of zero-delta patterns."""
    
    prices = df["price"].dropna().values[:10000]
    PRICE_SCALE = 10_000
    scaled = [int(p * PRICE_SCALE) for p in prices]
    
    # Find all zero deltas
    deltas = [scaled[i] - scaled[i-1] for i in range(1, len(scaled))]
    
    zero_positions = [i for i, d in enumerate(deltas) if d == 0]
    non_zero_positions = [i for i, d in enumerate(deltas) if d != 0]
    
    # Encode zeros as binary stream
    zero_bits = [1 if d == 0 else 0 for d in deltas]
    
    # Analyze the zero-position pattern
    # Could this be encoding hidden bits?
    
    # Test randomness of zero positions
    if len(zero_positions) > 100:
        # Chi-square test on inter-zero gaps
        gaps = [zero_positions[i+1] - zero_positions[i] for i in range(len(zero_positions) - 1)]
        gap_counts = Counter(gaps)
        
        # Is the gap distribution uniform or patterned?
        observed = list(gap_counts.values())
        expected = [sum(observed) / len(observed)] * len(observed)
        chi2, pval = stats.chisquare(observed, expected)
    else:
        chi2, pval = 0, 1
        gaps = []
    
    # Run length encoding of zeros
    runs = []
    current_run = 0
    for d in deltas:
        if d == 0:
            current_run += 1
        else:
            if current_run > 0:
                runs.append(current_run)
            current_run = 0
    if current_run > 0:
        runs.append(current_run)
    
    # Attempt to decode zero bits as ASCII
    ascii_attempt = ""
    for i in range(0, min(256, len(zero_bits) - 7), 8):
        byte_val = 0
        for j in range(8):
            byte_val = (byte_val << 1) | zero_bits[i + j]
        if 32 <= byte_val < 127:
            ascii_attempt += chr(byte_val)
        else:
            ascii_attempt += "."
    
    return {
        "total_deltas": len(deltas),
        "zero_count": len(zero_positions),
        "zero_ratio": len(zero_positions) / len(deltas),
        "max_consecutive_zeros": max(runs) if runs else 0,
        "mean_run_length": float(np.mean(runs)) if runs else 0,
        "run_distribution": dict(Counter(runs).most_common(10)),
        "gap_chi2": float(chi2),
        "gap_pvalue": float(pval),
        "gaps_random": pval > 0.05,
        "ascii_decode_attempt": ascii_attempt[:50],
        "has_readable_text": sum(1 for c in ascii_attempt[:50] if c.isalnum()) > 10
    }


def analyze_mirror_patterns(df: pd.DataFrame) -> dict:
    """Analyze the 5.31% mirror patterns (same magnitude, opposite sign)."""
    
    prices = df["price"].dropna().values[:10000]
    PRICE_SCALE = 10_000
    scaled = [int(p * PRICE_SCALE) for p in prices]
    
    deltas = [scaled[i] - scaled[i-1] for i in range(1, len(scaled))]
    
    # Find mirror patterns
    mirrors = []
    for i in range(1, len(deltas)):
        if deltas[i] == -deltas[i-1] and deltas[i] != 0:
            mirrors.append({
                "position": i,
                "value": abs(deltas[i]),
                "direction": "down_to_up" if deltas[i] > 0 else "up_to_down"
            })
    
    # Analyze mirror positions for pattern
    if len(mirrors) > 10:
        positions = [m["position"] for m in mirrors]
        values = [m["value"] for m in mirrors]
        
        # Position gaps
        gaps = [positions[i+1] - positions[i] for i in range(len(positions) - 1)]
        
        # Could positions encode bits?
        position_mod = [p % 16 for p in positions]  # Modular pattern
        
        # Could values encode bits?
        value_lsb = [v % 2 for v in values]
        
        return {
            "mirror_count": len(mirrors),
            "mirror_ratio": len(mirrors) / len(deltas),
            "position_gaps": gaps[:20],
            "position_mod_16": dict(Counter(position_mod)),
            "value_lsb_ratio": sum(value_lsb) / len(value_lsb) if value_lsb else 0,
            "sample_mirrors": mirrors[:10]
        }
    
    return {"mirror_count": len(mirrors), "insufficient_data": True}


def analyze_xor_vs_delta_anomaly(df: pd.DataFrame) -> dict:
    """
    XOR encoding has LOWER entropy than delta.
    This is unusual - let's understand why.
    """
    
    prices = df["price"].dropna().values[:10000]
    PRICE_SCALE = 10_000
    scaled = [int(p * PRICE_SCALE) for p in prices]
    
    # Compare XOR and delta patterns
    deltas = [scaled[i] - scaled[i-1] for i in range(1, len(scaled))]
    xors = [scaled[i] ^ scaled[i-1] for i in range(1, len(scaled))]
    
    # Analyze XOR bit patterns
    xor_bits = []
    for x in xors[:1000]:
        for bit in range(20):
            xor_bits.append((x >> bit) & 1)
    
    # Which bits change most often in XOR?
    bit_change_freq = {}
    for bit in range(20):
        changes = [(xors[i] >> bit) & 1 for i in range(len(xors))]
        bit_change_freq[bit] = sum(changes) / len(changes)
    
    # XOR reveals which bits flip between consecutive prices
    # If low bits flip rarely, prices are "sticky" at certain levels
    
    return {
        "xor_entropy": float(stats.entropy(np.histogram(xors, bins=50)[0] + 1)),
        "delta_entropy": float(stats.entropy(np.histogram(deltas, bins=50)[0] + 1)),
        "bit_flip_frequency": bit_change_freq,
        "low_bits_sticky": bit_change_freq.get(0, 0) < 0.3,
        "interpretation": "Prices tend to repeat or differ by small amounts" if bit_change_freq.get(0, 0) < 0.3 else "Normal price movement"
    }


def extract_hidden_channel(df: pd.DataFrame) -> dict:
    """
    Attempt to extract hidden channel from zero-delta positions.
    If zeros are placed intentionally, their positions could encode bits.
    """
    
    prices = df["price"].dropna().values[:10000]
    PRICE_SCALE = 10_000
    scaled = [int(p * PRICE_SCALE) for p in prices]
    
    deltas = [scaled[i] - scaled[i-1] for i in range(1, len(scaled))]
    
    # Extract zero/non-zero as binary
    binary_stream = [1 if d == 0 else 0 for d in deltas]
    
    # Method 1: Direct binary interpretation
    direct_bytes = []
    for i in range(0, len(binary_stream) - 7, 8):
        byte_val = 0
        for j in range(8):
            byte_val = (byte_val << 1) | binary_stream[i + j]
        direct_bytes.append(byte_val)
    
    # Method 2: Run-length encoding
    runs = []
    current_val = binary_stream[0]
    current_run = 1
    for b in binary_stream[1:]:
        if b == current_val:
            current_run += 1
        else:
            runs.append((current_val, current_run))
            current_val = b
            current_run = 1
    runs.append((current_val, current_run))
    
    # Decode run lengths as values
    run_values = [r[1] for r in runs if r[0] == 1]  # Lengths of zero-delta runs
    
    return {
        "direct_byte_count": len(direct_bytes),
        "direct_bytes_sample": direct_bytes[:20],
        "run_count": len(runs),
        "zero_run_lengths": run_values[:30],
        "max_run_length": max(run_values) if run_values else 0,
        "run_length_entropy": float(stats.entropy(np.histogram(run_values, bins=20)[0] + 1)) if len(run_values) > 10 else 0
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("SECOND-PASS FORENSIC ANALYSIS")
    print("Investigating: 63% zero deltas, mirror patterns, XOR anomaly")
    print("=" * 70)
    
    # Load data
    sample_dirs = sorted(DATA_DIR.glob("sample_*"))[:5]
    
    all_results = []
    
    for sample_dir in sample_dirs:
        trades_files = list(sample_dir.glob("raw_ticks/*_trades.csv"))
        if not trades_files:
            continue
            
        df = pd.read_csv(trades_files[0])
        if "price" not in df.columns:
            continue
        
        date = sample_dir.name.replace("sample_", "")
        print(f"\n>>> {date}")
        
        # Run analyses
        zero_analysis = analyze_zero_deltas(df)
        mirror_analysis = analyze_mirror_patterns(df)
        xor_analysis = analyze_xor_vs_delta_anomaly(df)
        hidden_analysis = extract_hidden_channel(df)
        
        result = {
            "date": date,
            "zero_deltas": zero_analysis,
            "mirror_patterns": mirror_analysis,
            "xor_anomaly": xor_analysis,
            "hidden_channel": hidden_analysis
        }
        all_results.append(result)
        
        print(f"  Zero ratio: {zero_analysis['zero_ratio']:.1%}")
        print(f"  Max consecutive zeros: {zero_analysis['max_consecutive_zeros']}")
        print(f"  Mirror count: {mirror_analysis.get('mirror_count', 0)}")
        print(f"  Low bits sticky: {xor_analysis.get('low_bits_sticky', False)}")
    
    # Cross-day analysis
    print("\n" + "=" * 70)
    print("CROSS-DAY PATTERNS")
    print("=" * 70)
    
    if all_results:
        # Are zero ratios consistent across days?
        zero_ratios = [r["zero_deltas"]["zero_ratio"] for r in all_results]
        print(f"  Zero ratio range: {min(zero_ratios):.1%} - {max(zero_ratios):.1%}")
        print(f"  Zero ratio std: {np.std(zero_ratios):.3f}")
        
        # Are the patterns the same structure?
        max_runs = [r["zero_deltas"]["max_consecutive_zeros"] for r in all_results]
        print(f"  Max run range: {min(max_runs)} - {max(max_runs)}")
    
    # Save results
    with open(OUTPUT_DIR / "forensic_secondpass.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": all_results
        }, f, indent=2, default=str)
    
    # Generate report
    with open(OUTPUT_DIR / "forensic_secondpass_report.md", "w") as f:
        f.write("# Second-Pass Forensic Analysis\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Key Investigation Areas\n\n")
        f.write("1. **63% Zero Deltas** - Why do prices repeat so often?\n")
        f.write("2. **5.31% Mirror Patterns** - Systematic reversal patterns\n")
        f.write("3. **XOR Lower Entropy** - Bits flip predictably\n\n")
        
        f.write("## Zero Delta Analysis\n\n")
        if all_results:
            f.write("| Date | Zero Ratio | Max Run | Gaps Random? |\n")
            f.write("|------|-----------|---------|-------------|\n")
            for r in all_results:
                z = r["zero_deltas"]
                f.write(f"| {r['date']} | {z['zero_ratio']:.1%} | {z['max_consecutive_zeros']} | {'✓' if z['gaps_random'] else '⚠️'} |\n")
        
        f.write("\n## Interpretation\n\n")
        if all_results and all_results[0]["zero_deltas"]["zero_ratio"] > 0.5:
            f.write("> ⚠️ **ANOMALY**: Over 50% of price deltas are ZERO\n\n")
            f.write("This could indicate:\n")
            f.write("1. **Tick aggregation** - Multiple trades at same price collapsed\n")
            f.write("2. **Quote stickiness** - MM holding price steady\n")
            f.write("3. **Hidden channel** - Zero positions encode information\n")
    
    print("\n" + "=" * 70)
    print("SECOND-PASS ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
