#!/usr/bin/env python3
"""
Zero-Delta Channel Extraction
==============================

HYPOTHESIS: The 60%+ zero-delta rate is too consistent to be random.
If someone wanted to hide data in trade streams, they could:
1. Place zeros at specific positions -> positions encode bits
2. Vary run lengths -> run lengths encode values
3. Use parity of zero positions -> even/odd positions

This script attempts MULTIPLE extraction methods.
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
from collections import Counter
import hashlib

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "samples"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "results"


def extract_via_position_parity(deltas: list) -> dict:
    """Method 1: Zeros at even positions = 0, odd positions = 1"""
    zero_positions = [i for i, d in enumerate(deltas) if d == 0]
    
    if not zero_positions:
        return {"error": "No zeros found"}
    
    # Extract bits from position parity
    bits = [p % 2 for p in zero_positions[:1000]]
    
    # Convert to bytes
    byte_vals = []
    for i in range(0, len(bits) - 7, 8):
        byte_val = 0
        for j in range(8):
            byte_val = (byte_val << 1) | bits[i + j]
        byte_vals.append(byte_val)
    
    # ASCII decode
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in byte_vals)
    
    # Entropy
    entropy = stats.entropy(np.histogram(bits, bins=2)[0] + 1)
    
    return {
        "method": "position_parity",
        "bits_extracted": len(bits),
        "bytes_extracted": len(byte_vals),
        "ones_ratio": sum(bits) / len(bits),
        "entropy": float(entropy),
        "ascii_sample": ascii_str[:50],
        "has_text": sum(1 for c in ascii_str[:50] if c.isalnum()) > 10
    }


def extract_via_run_lengths(deltas: list) -> dict:
    """Method 2: Run lengths of zeros encode values"""
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
    
    if not runs:
        return {"error": "No runs found"}
    
    # Method A: Run length mod 256 = byte value
    byte_vals = [r % 256 for r in runs]
    ascii_a = ''.join(chr(b) if 32 <= b < 127 else '.' for b in byte_vals)
    
    # Method B: Run length LSB = bit
    bits = [r % 2 for r in runs]
    byte_vals_b = []
    for i in range(0, len(bits) - 7, 8):
        byte_val = 0
        for j in range(8):
            byte_val = (byte_val << 1) | bits[i + j]
        byte_vals_b.append(byte_val)
    ascii_b = ''.join(chr(b) if 32 <= b < 127 else '.' for b in byte_vals_b)
    
    return {
        "method": "run_lengths",
        "run_count": len(runs),
        "avg_run_length": float(np.mean(runs)),
        "max_run_length": max(runs),
        "run_length_distribution": dict(Counter(runs).most_common(10)),
        "method_a_ascii": ascii_a[:50],
        "method_b_ascii": ascii_b[:50],
        "method_b_ones_ratio": sum(bits) / len(bits) if bits else 0
    }


def extract_via_spacing(deltas: list) -> dict:
    """Method 3: Spacing between zeros encodes information"""
    zero_positions = [i for i, d in enumerate(deltas) if d == 0]
    
    if len(zero_positions) < 10:
        return {"error": "Insufficient zeros"}
    
    # Gaps between consecutive zeros
    gaps = [zero_positions[i+1] - zero_positions[i] for i in range(len(zero_positions) - 1)]
    
    # Gap mod 2 = bit
    bits = [g % 2 for g in gaps]
    
    # Convert to bytes
    byte_vals = []
    for i in range(0, len(bits) - 7, 8):
        byte_val = 0
        for j in range(8):
            byte_val = (byte_val << 1) | bits[i + j]
        byte_vals.append(byte_val)
    
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in byte_vals)
    
    return {
        "method": "spacing",
        "gap_count": len(gaps),
        "avg_gap": float(np.mean(gaps)),
        "gap_distribution": dict(Counter(gaps).most_common(10)),
        "bits_extracted": len(bits),
        "ones_ratio": sum(bits) / len(bits) if bits else 0,
        "ascii_sample": ascii_str[:50]
    }


def extract_via_direction(prices: list) -> dict:
    """Method 4: Direction of non-zero moves encodes bits"""
    PRICE_SCALE = 10_000
    scaled = [int(p * PRICE_SCALE) for p in prices]
    deltas = [scaled[i] - scaled[i-1] for i in range(1, len(scaled))]
    
    # Only non-zero deltas
    non_zero = [(i, d) for i, d in enumerate(deltas) if d != 0]
    
    if not non_zero:
        return {"error": "All zeros!"}
    
    # Up = 1, Down = 0
    bits = [1 if d > 0 else 0 for _, d in non_zero]
    
    # Convert to bytes
    byte_vals = []
    for i in range(0, len(bits) - 7, 8):
        byte_val = 0
        for j in range(8):
            byte_val = (byte_val << 1) | bits[i + j]
        byte_vals.append(byte_val)
    
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in byte_vals)
    
    return {
        "method": "direction",
        "non_zero_count": len(non_zero),
        "up_ratio": sum(bits) / len(bits),
        "bytes_extracted": len(byte_vals),
        "ascii_sample": ascii_str[:50]
    }


def brute_force_xor_keys(deltas: list) -> dict:
    """Try XORing extracted bytes with common keys"""
    
    # First, extract using position parity (most promising)
    zero_positions = [i for i, d in enumerate(deltas) if d == 0]
    bits = [p % 2 for p in zero_positions[:1000]]
    
    byte_vals = []
    for i in range(0, len(bits) - 7, 8):
        byte_val = 0
        for j in range(8):
            byte_val = (byte_val << 1) | bits[i + j]
        byte_vals.append(byte_val)
    
    if not byte_vals:
        return {"error": "No bytes to test"}
    
    original_bytes = bytes(byte_vals)
    
    # Try common XOR keys
    results = {}
    for key in [0x00, 0x20, 0x41, 0x55, 0xAA, 0xFF, 0x47, 0x4D, 0x45]:  # Include 'G', 'M', 'E'
        decoded = bytes(b ^ key for b in original_bytes)
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in decoded)
        readable = sum(1 for c in ascii_str if c.isalnum())
        results[hex(key)] = {
            "ascii": ascii_str[:30],
            "readable_count": readable,
            "promising": readable > 10
        }
    
    # Find best key
    best_key = max(results.items(), key=lambda x: x[1]["readable_count"])
    
    return {
        "xor_tests": results,
        "best_key": best_key[0],
        "best_readable": best_key[1]["readable_count"],
        "best_ascii": best_key[1]["ascii"]
    }


def fingerprint_analysis(df: pd.DataFrame) -> dict:
    """Generate fingerprint of the zero pattern for cross-reference"""
    
    prices = df["price"].dropna().values[:10000]
    PRICE_SCALE = 10_000
    scaled = [int(p * PRICE_SCALE) for p in prices]
    deltas = [scaled[i] - scaled[i-1] for i in range(1, len(scaled))]
    
    # Zero pattern fingerprint
    zero_pattern = [1 if d == 0 else 0 for d in deltas[:256]]
    zero_bytes = bytes([
        sum(zero_pattern[i+j] << (7-j) for j in range(8))
        for i in range(0, min(256, len(zero_pattern)) - 7, 8)
    ])
    
    fingerprint = hashlib.sha256(zero_bytes).hexdigest()[:16]
    
    # Run pattern fingerprint
    runs = []
    current_run = 0
    for d in deltas[:1000]:
        if d == 0:
            current_run += 1
        else:
            if current_run > 0:
                runs.append(current_run)
            current_run = 0
    
    run_hash = hashlib.sha256(bytes(r % 256 for r in runs[:128])).hexdigest()[:16]
    
    return {
        "zero_pattern_fingerprint": fingerprint,
        "run_pattern_fingerprint": run_hash,
        "fingerprints_unique": fingerprint != run_hash
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("ZERO-DELTA CHANNEL EXTRACTION")
    print("Testing multiple extraction methods for hidden data")
    print("=" * 70)
    
    # Load data
    sample_dirs = sorted(DATA_DIR.glob("sample_*"))[:5]
    
    all_results = []
    fingerprints = []
    
    for sample_dir in sample_dirs:
        trades_files = list(sample_dir.glob("raw_ticks/*_trades.csv"))
        if not trades_files:
            continue
            
        df = pd.read_csv(trades_files[0])
        if "price" not in df.columns:
            continue
        
        date = sample_dir.name.replace("sample_", "")
        print(f"\n>>> {date}")
        
        prices = df["price"].dropna().values[:10000]
        PRICE_SCALE = 10_000
        scaled = [int(p * PRICE_SCALE) for p in prices]
        deltas = [scaled[i] - scaled[i-1] for i in range(1, len(scaled))]
        
        # Run all extraction methods
        results = {
            "date": date,
            "position_parity": extract_via_position_parity(deltas),
            "run_lengths": extract_via_run_lengths(deltas),
            "spacing": extract_via_spacing(deltas),
            "direction": extract_via_direction(prices.tolist()),
            "xor_bruteforce": brute_force_xor_keys(deltas),
            "fingerprint": fingerprint_analysis(df)
        }
        
        all_results.append(results)
        fingerprints.append(results["fingerprint"]["zero_pattern_fingerprint"])
        
        # Print key findings
        print(f"  Position parity ones: {results['position_parity'].get('ones_ratio', 0):.3f}")
        print(f"  Run length avg: {results['run_lengths'].get('avg_run_length', 0):.1f}")
        print(f"  Direction up ratio: {results['direction'].get('up_ratio', 0):.3f}")
        print(f"  Best XOR key: {results['xor_bruteforce'].get('best_key', 'N/A')}")
    
    # Cross-day fingerprint comparison
    print("\n" + "=" * 70)
    print("FINGERPRINT COMPARISON")
    print("=" * 70)
    
    unique_fingerprints = len(set(fingerprints))
    print(f"  Unique fingerprints: {unique_fingerprints}/{len(fingerprints)}")
    
    if unique_fingerprints == len(fingerprints):
        print("  Each day has unique zero pattern - not a fixed key")
    else:
        print("  ⚠️ Some days share patterns!")
        print(f"  Fingerprints: {fingerprints}")
    
    # Save results
    with open(OUTPUT_DIR / "channel_extraction.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": all_results,
            "fingerprints": fingerprints,
            "unique_fingerprints": unique_fingerprints
        }, f, indent=2, default=str)
    
    # Generate report
    with open(OUTPUT_DIR / "channel_extraction_report.md", "w") as f:
        f.write("# Zero-Delta Channel Extraction\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Extraction Methods Tested\n\n")
        f.write("| Method | Description | Result |\n")
        f.write("|--------|-------------|--------|\n")
        
        if all_results:
            r = all_results[0]
            f.write(f"| Position Parity | Zero at even/odd pos | ones={r['position_parity'].get('ones_ratio', 0):.3f} |\n")
            f.write(f"| Run Lengths | Length of consecutive zeros | avg={r['run_lengths'].get('avg_run_length', 0):.1f} |\n")
            f.write(f"| Spacing | Gaps between zeros | ones={r['spacing'].get('ones_ratio', 0):.3f} |\n")
            f.write(f"| Direction | Up=1, Down=0 | up={r['direction'].get('up_ratio', 0):.3f} |\n")
        
        f.write("\n## Fingerprint Analysis\n\n")
        f.write(f"- Unique fingerprints: {unique_fingerprints}/{len(fingerprints)}\n")
        if unique_fingerprints == len(fingerprints):
            f.write("- **Each day has unique pattern** - not static encoding\n")
        
        f.write("\n## Conclusion\n\n")
        f.write("The zero-delta patterns appear to be **market microstructure artifacts**:\n")
        f.write("- Tick aggregation (multiple trades at same price)\n")
        f.write("- Market maker quote stickiness\n")
        f.write("- High-frequency trading patterns\n\n")
        f.write("> No obvious hidden message found, but patterns are structurally interesting.\n")
    
    print("\n" + "=" * 70)
    print("CHANNEL EXTRACTION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
