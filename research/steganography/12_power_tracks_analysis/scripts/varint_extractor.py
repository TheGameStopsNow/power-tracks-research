#!/usr/bin/env python3
"""
Varint Slack Bit Extractor
==========================

Extracts potential hidden bits from the varint encoding slack
in Power Track frames. Tests if extracted bits contain patterns.
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

# Add pipeline paths
PIPELINE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "pipelines" / "00_signal_integrity"
sys.path.insert(0, str(PIPELINE_DIR))
sys.path.insert(0, str(PIPELINE_DIR / "tests"))

try:
    from test_crc import crc7
except ImportError:
    def crc7(data):
        crc = 0
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ 0x89
                else:
                    crc <<= 1
        return crc & 0x7F

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent  # Go up to repo root
DATA_DIR = BASE_DIR / "data" / "samples"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "results"
DATA_OUTPUT = OUTPUT_DIR # Consolidate outputs

# Debug: Print paths
print(f"BASE_DIR: {BASE_DIR}")
print(f"DATA_DIR: {DATA_DIR}")
print(f"DATA_DIR exists: {DATA_DIR.exists()}")


def zig_zag_encode(value: int) -> int:
    return (value << 1) ^ (value >> 63)


def zig_zag_decode(value: int) -> int:
    return (value >> 1) ^ (-(value & 1))


def encode_varint(value: int) -> list:
    remaining = max(0, value)
    out = []
    while remaining >= 0x80:
        out.append(int((remaining & 0x7F) | 0x80))
        remaining >>= 7
    out.append(int(remaining))
    return out


def decode_varint(data: bytes) -> tuple:
    """Decode a single varint, return (value, bytes_consumed)."""
    value = 0
    shift = 0
    for i, b in enumerate(data):
        value |= (b & 0x7F) << shift
        if not (b & 0x80):
            return value, i + 1
        shift += 7
    return value, len(data)


def extract_varint_slack(prices: list, encoded_varints: bytes) -> dict:
    """Extract slack bits by comparing actual encoding to optimal."""
    
    PRICE_SCALE = 10_000
    
    # Calculate deltas
    deltas = []
    prev = int(prices[0] * PRICE_SCALE)
    for price in prices[1:]:
        target = int(price * PRICE_SCALE)
        deltas.append(target - prev)
        prev = target
    
    # Optimal encoding (theoretical minimum)
    optimal_bits = 0
    for delta in deltas:
        encoded = zig_zag_encode(delta)
        # Minimum bits needed to represent this value
        if encoded == 0:
            optimal_bits += 1
        else:
            optimal_bits += max(1, int(np.ceil(np.log2(encoded + 1))))
    
    # Actual encoding
    actual_bits = len(encoded_varints) * 7  # 7 data bits per byte
    
    # Slack
    slack_bits = actual_bits - optimal_bits
    
    # Extract the "slack" as potential hidden bits
    # These are bits that could encode different values with same varint length
    hidden_bits = []
    
    offset = 0
    for delta in deltas:
        if offset >= len(encoded_varints):
            break
            
        varint_val, bytes_used = decode_varint(encoded_varints[offset:])
        
        # Calculate the range of values that would use same byte count
        max_for_bytes = (1 << (7 * bytes_used)) - 1
        min_for_bytes = 0 if bytes_used == 1 else (1 << (7 * (bytes_used - 1)))
        
        # The "slack" is where in this range the value falls
        if max_for_bytes > min_for_bytes:
            position = (varint_val - min_for_bytes) / (max_for_bytes - min_for_bytes)
            # Extract as a bit sequence
            slack_value = int(position * 255)  # Normalize to 0-255
            for i in range(8):
                hidden_bits.append((slack_value >> (7 - i)) & 1)
        
        offset += bytes_used
    
    return {
        "n_deltas": len(deltas),
        "optimal_bits": optimal_bits,
        "actual_bits": actual_bits,
        "slack_bits": slack_bits,
        "extracted_bits": hidden_bits[:256],  # First 256 bits
        "bits_entropy": float(stats.entropy([sum(hidden_bits)/max(1,len(hidden_bits)), 
                                              1 - sum(hidden_bits)/max(1,len(hidden_bits))], base=2))
                        if hidden_bits else 0
    }


def analyze_extracted_bits(bits: list) -> dict:
    """Analyze extracted bits for patterns."""
    if len(bits) < 16:
        return {"error": "Insufficient bits"}
    
    bits = np.array(bits)
    
    # 1. Bit balance (should be ~0.5 for random)
    ones_ratio = bits.mean()
    
    # 2. Chi-square test for uniformity
    observed = np.bincount(bits, minlength=2)
    expected = np.full(2, len(bits) / 2)
    chi2, pval = stats.chisquare(observed, expected)
    
    # 3. Runs test for randomness
    runs = 1
    for i in range(1, len(bits)):
        if bits[i] != bits[i-1]:
            runs += 1
    
    n0, n1 = (bits == 0).sum(), (bits == 1).sum()
    expected_runs = 1 + 2 * n0 * n1 / len(bits)
    runs_ratio = runs / expected_runs if expected_runs > 0 else 1
    
    # 4. Try ASCII decoding
    ascii_text = ""
    for i in range(0, min(128, len(bits) - 7), 8):
        byte_val = 0
        for j in range(8):
            byte_val = (byte_val << 1) | bits[i + j]
        if 32 <= byte_val < 127:
            ascii_text += chr(byte_val)
        else:
            ascii_text += "."
    
    # 5. Autocorrelation
    if len(bits) > 10:
        autocorr = np.corrcoef(bits[:-1], bits[1:])[0, 1]
    else:
        autocorr = 0
    
    return {
        "n_bits": len(bits),
        "ones_ratio": float(ones_ratio),
        "chi2": float(chi2),
        "chi2_pvalue": float(pval),
        "random_by_chi2": bool(pval > 0.05),
        "runs": runs,
        "runs_ratio": float(runs_ratio),
        "autocorrelation": float(autocorr) if not np.isnan(autocorr) else 0,
        "ascii_attempt": ascii_text[:32],
        "has_readable_ascii": any(c.isalnum() for c in ascii_text[:32])
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_OUTPUT.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("VARINT SLACK BIT EXTRACTOR")
    print("=" * 70)
    
    sample_dirs = sorted(DATA_DIR.glob("sample_*"))
    
    all_extracted_bits = []
    results = []
    
    for sample_dir in sample_dirs:
        trades_files = list(sample_dir.glob("raw_ticks/*_trades.csv"))
        if not trades_files:
            continue
        
        date = sample_dir.name.replace("sample_", "")
        print(f"\n>>> {date}")
        
        df = pd.read_csv(trades_files[0])
        
        if "price" not in df.columns:
            continue
        
        # Take sample prices
        prices = df["price"].dropna().head(100).tolist()
        
        if len(prices) < 10:
            continue
        
        # Encode frame and extract varints
        PRICE_SCALE = 10_000
        
        anchor_price = int(prices[0] * PRICE_SCALE)
        
        # Build payload varints
        payload_bytes = []
        prev = anchor_price
        for price in prices[1:]:
            target = int(price * PRICE_SCALE)
            delta = target - prev
            prev = target
            payload_bytes.extend(encode_varint(zig_zag_encode(delta)))
        
        encoded_varints = bytes(payload_bytes)
        
        # Extract slack
        slack_result = extract_varint_slack(prices, encoded_varints)
        
        # Analyze extracted bits
        bit_analysis = analyze_extracted_bits(slack_result["extracted_bits"])
        
        result = {
            "date": date,
            "n_prices": len(prices),
            "slack_extraction": slack_result,
            "bit_analysis": bit_analysis
        }
        results.append(result)
        
        all_extracted_bits.extend(slack_result["extracted_bits"])
        
        print(f"  Slack: {slack_result['slack_bits']} bits")
        print(f"  Extracted: {len(slack_result['extracted_bits'])} bits")
        print(f"  Random: {bit_analysis.get('random_by_chi2', 'N/A')}")
        print(f"  ASCII: {bit_analysis.get('ascii_attempt', '')[:16]}...")
    
    # Aggregate analysis
    print("\n" + "=" * 70)
    print("AGGREGATE ANALYSIS")
    print("=" * 70)
    
    if all_extracted_bits:
        aggregate = analyze_extracted_bits(all_extracted_bits)
        print(f"Total bits extracted: {len(all_extracted_bits)}")
        print(f"Ones ratio: {aggregate['ones_ratio']:.4f}")
        print(f"Random by chi2: {aggregate['random_by_chi2']}")
        print(f"Autocorrelation: {aggregate['autocorrelation']:.4f}")
        print(f"ASCII attempt: {aggregate['ascii_attempt'][:32]}")
    else:
        aggregate = {}
    
    # Save results
    with open(OUTPUT_DIR / "varint_extraction.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "aggregate": aggregate,
            "daily_results": results
        }, f, indent=2, default=str)
    
    # Save extracted bits
    with open(DATA_OUTPUT / "extracted_bits.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "all_bits": all_extracted_bits[:10000],  # First 10k bits
            "n_total": len(all_extracted_bits)
        }, f, indent=2)
    
    # Generate report
    with open(OUTPUT_DIR / "varint_extraction_report.md", "w") as f:
        f.write("# Varint Slack Bit Extraction\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Summary\n\n")
        f.write(f"- Days analyzed: {len(results)}\n")
        f.write(f"- Total bits extracted: {len(all_extracted_bits)}\n")
        
        if aggregate:
            f.write(f"- Ones ratio: {aggregate['ones_ratio']:.4f} (expected: 0.5)\n")
            f.write(f"- Random by chi²: {aggregate['random_by_chi2']}\n")
            f.write(f"- Autocorrelation: {aggregate['autocorrelation']:.4f}\n")
        
        f.write("\n## Daily Results\n\n")
        f.write("| Date | Prices | Slack Bits | Extracted | Random? |\n")
        f.write("|------|--------|------------|-----------|--------|\n")
        for r in results:
            random_str = "✓" if r["bit_analysis"].get("random_by_chi2") else ""
            f.write(f"| {r['date']} | {r['n_prices']} | {r['slack_extraction']['slack_bits']} | {len(r['slack_extraction']['extracted_bits'])} | {random_str} |\n")
        
        f.write("\n## Interpretation\n\n")
        if aggregate.get("random_by_chi2"):
            f.write("> ✅ Extracted bits appear random (no hidden message detected)\n")
        else:
            f.write("> ⚠️ **Extracted bits show non-random patterns** - possible hidden data\n")
    
    print("\n" + "=" * 70)
    print("EXTRACTION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
