#!/usr/bin/env python3
"""
Deep Forensic Analysis of Power Tracks
=======================================

This script approaches Power Tracks WITHOUT using documented encodings.
Goal: Independently discover what information is encoded and test if
the documented encoding is optimal or hiding something.

Questions to answer:
1. Are opcodes derived from data patterns or applied artificially?
2. Is there cryptographic structure (RSA, AES signatures)?
3. Is the zig-zag varint encoding optimal or wasteful?
4. What does raw entropy analysis reveal?
5. Are there repeating patterns suggesting a key?
"""

import sys
from pathlib import Path
from datetime import datetime
import json
import struct
import hashlib
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from scipy import stats
from collections import Counter

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "samples"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "results"


# ========================================================================
# PART 1: RAW DATA ANALYSIS (NO DOCUMENTATION)
# ========================================================================

def analyze_raw_bytes(df: pd.DataFrame) -> dict:
    """Analyze raw trade data as binary stream without any encoding assumptions."""
    
    # Convert prices to raw bytes
    prices = df["price"].dropna().values
    
    # Pack as raw binary (multiple representations)
    raw_float64 = b''.join(struct.pack('d', p) for p in prices[:1000])
    raw_float32 = b''.join(struct.pack('f', p) for p in prices[:1000])
    
    # Convert to cents (common representation)
    cents = (prices * 100).astype(int)
    raw_cents = b''.join(struct.pack('H', c % 65536) for c in cents[:1000])
    
    # Analyze bit patterns
    float64_bits = ''.join(format(b, '08b') for b in raw_float64)
    float32_bits = ''.join(format(b, '08b') for b in raw_float32)
    cents_bits = ''.join(format(b, '08b') for b in raw_cents)
    
    return {
        "float64": {
            "bytes": len(raw_float64),
            "entropy": calculate_entropy(raw_float64),
            "ones_ratio": float64_bits.count('1') / len(float64_bits),
        },
        "float32": {
            "bytes": len(raw_float32),
            "entropy": calculate_entropy(raw_float32),
            "ones_ratio": float32_bits.count('1') / len(float32_bits),
        },
        "cents": {
            "bytes": len(raw_cents),
            "entropy": calculate_entropy(raw_cents),
            "ones_ratio": cents_bits.count('1') / len(cents_bits),
        }
    }


def calculate_entropy(data: bytes) -> float:
    """Calculate Shannon entropy of byte stream."""
    if not data:
        return 0
    counts = Counter(data)
    total = len(data)
    probs = [c / total for c in counts.values()]
    return -sum(p * np.log2(p) for p in probs if p > 0)


# ========================================================================
# PART 2: CRYPTOGRAPHIC PATTERN DETECTION
# ========================================================================

def detect_crypto_signatures(data: bytes) -> dict:
    """Look for patterns suggesting cryptographic data."""
    
    results = {
        "has_high_entropy": False,
        "has_null_regions": False,
        "has_key_like_patterns": False,
        "has_block_alignment": False,
        "potential_signatures": []
    }
    
    # High entropy check (random-like = possible encryption)
    entropy = calculate_entropy(data)
    results["entropy"] = float(entropy)
    results["has_high_entropy"] = entropy > 7.5  # Near max 8.0
    
    # Check for null regions (padding common in crypto)
    null_runs = 0
    current_run = 0
    for b in data:
        if b == 0:
            current_run += 1
        else:
            if current_run > 8:
                null_runs += 1
            current_run = 0
    results["null_runs"] = null_runs
    results["has_null_regions"] = null_runs > 5
    
    # Check for 16/32/64 byte block alignment (AES, etc.)
    for block_size in [16, 32, 64, 128]:
        if len(data) % block_size == 0:
            results["potential_block_sizes"] = results.get("potential_block_sizes", [])
            results["potential_block_sizes"].append(block_size)
    results["has_block_alignment"] = len(results.get("potential_block_sizes", [])) > 0
    
    # Look for RSA/crypto magic bytes
    magic_patterns = {
        b'\x30\x82': "ASN.1 SEQUENCE (RSA key)",
        b'\x02\x01': "ASN.1 INTEGER",
        b'-----': "PEM format",
        b'ssh-': "SSH key format",
        b'\x00\x00\x00': "Possible key material"
    }
    
    for pattern, name in magic_patterns.items():
        if pattern in data:
            results["potential_signatures"].append(name)
            results["has_key_like_patterns"] = True
    
    # SHA256 hash of data (for fingerprinting)
    results["sha256"] = hashlib.sha256(data).hexdigest()[:16]
    
    return results


def look_for_repeating_keys(data: bytes, key_lengths: list = [8, 16, 32, 64, 128]) -> dict:
    """Test if data XORed with repeating key produces structure."""
    
    results = {}
    
    for key_len in key_lengths:
        if len(data) < key_len * 2:
            continue
        
        # Assume first key_len bytes might be the key
        potential_key = data[:key_len]
        
        # XOR rest of data with potential key
        decoded = bytes(
            data[i] ^ potential_key[i % key_len]
            for i in range(key_len, len(data))
        )
        
        # Check if decoded data has more structure
        decoded_entropy = calculate_entropy(decoded)
        original_entropy = calculate_entropy(data[key_len:])
        
        # Check for ASCII text after decoding
        ascii_chars = sum(1 for b in decoded if 32 <= b < 127)
        ascii_ratio = ascii_chars / len(decoded)
        
        results[key_len] = {
            "original_entropy": float(original_entropy),
            "decoded_entropy": float(decoded_entropy),
            "entropy_reduction": float(original_entropy - decoded_entropy),
            "ascii_ratio": float(ascii_ratio),
            "has_text": ascii_ratio > 0.7
        }
    
    return results


# ========================================================================
# PART 3: ALTERNATIVE DECODING METHODS
# ========================================================================

def test_alternative_encodings(prices: list) -> dict:
    """Test if there are better encodings than zig-zag varint."""
    
    PRICE_SCALE = 10_000
    scaled = [int(p * PRICE_SCALE) for p in prices]
    
    # Method 1: Delta encoding (documented approach)
    deltas = [scaled[i] - scaled[i-1] for i in range(1, len(scaled))]
    
    # Method 2: Double delta (acceleration)
    if len(deltas) > 1:
        double_deltas = [deltas[i] - deltas[i-1] for i in range(1, len(deltas))]
    else:
        double_deltas = []
    
    # Method 3: XOR encoding
    xor_values = [scaled[i] ^ scaled[i-1] for i in range(1, len(scaled))]
    
    # Method 4: Fractional only (cents)
    cents_only = [int(p * 100) % 100 for p in prices]
    
    # Compare entropy of each
    def bits_to_encode(values):
        if not values:
            return 0
        max_val = max(abs(v) for v in values)
        if max_val == 0:
            return 1
        return max(1, int(np.ceil(np.log2(max_val + 1))))
    
    return {
        "delta": {
            "mean": float(np.mean(deltas)) if deltas else 0,
            "std": float(np.std(deltas)) if deltas else 0,
            "max_bits_needed": bits_to_encode(deltas),
            "entropy": float(stats.entropy(np.histogram(deltas, bins=50)[0] + 1))
        },
        "double_delta": {
            "mean": float(np.mean(double_deltas)) if double_deltas else 0,
            "std": float(np.std(double_deltas)) if double_deltas else 0,
            "max_bits_needed": bits_to_encode(double_deltas),
            "entropy": float(stats.entropy(np.histogram(double_deltas, bins=50)[0] + 1)) if double_deltas else 0
        },
        "xor": {
            "mean": float(np.mean(xor_values)) if xor_values else 0,
            "std": float(np.std(xor_values)) if xor_values else 0,
            "max_bits_needed": bits_to_encode(xor_values),
            "entropy": float(stats.entropy(np.histogram(xor_values, bins=50)[0] + 1))
        },
        "cents_only": {
            "unique_values": len(set(cents_only)),
            "max_bits_needed": 7,  # 0-99 fits in 7 bits
            "entropy": float(stats.entropy(np.histogram(cents_only, bins=100)[0] + 1))
        }
    }


# ========================================================================
# PART 4: OPCODE ANALYSIS
# ========================================================================

def analyze_opcodes_from_data(prices: list) -> dict:
    """Reverse-engineer what opcodes SHOULD be used based on data characteristics."""
    
    PRICE_SCALE = 10_000
    scaled = [int(p * PRICE_SCALE) for p in prices]
    deltas = [scaled[i] - scaled[i-1] for i in range(1, len(scaled))]
    
    # Classify each delta
    classifications = {
        "zero": 0,           # No change
        "small_pos": 0,      # 1-127 (1 byte varint)
        "small_neg": 0,      # -1 to -127
        "medium": 0,         # 128-16383 (2 byte varint)
        "large": 0,          # > 16383 (3+ byte varint)
        "mirror": 0          # Same magnitude, opposite sign as previous
    }
    
    prev_delta = 0
    for d in deltas:
        if d == 0:
            classifications["zero"] += 1
        elif 1 <= d <= 127:
            classifications["small_pos"] += 1
        elif -127 <= d <= -1:
            classifications["small_neg"] += 1
        elif abs(d) <= 16383:
            classifications["medium"] += 1
        else:
            classifications["large"] += 1
        
        # Check for mirror pattern
        if d == -prev_delta and d != 0:
            classifications["mirror"] += 1
        
        prev_delta = d
    
    total = len(deltas)
    
    # Suggest optimal opcode distribution
    return {
        "delta_classifications": classifications,
        "percentages": {k: round(100 * v / total, 2) for k, v in classifications.items()},
        "suggested_opcodes": {
            "SINGLE_BYTE": classifications["zero"] + classifications["small_pos"] + classifications["small_neg"],
            "VARINT": classifications["medium"],
            "EXTENDED": classifications["large"],
            "MIRROR": classifications["mirror"]
        },
        "optimal_encoding": "delta" if classifications["medium"] + classifications["large"] < total * 0.3 else "raw"
    }


# ========================================================================
# PART 5: XOR MASK ANALYSIS
# ========================================================================

def analyze_xor_mask_patterns(dfs: list, dates: list) -> dict:
    """Analyze if XOR masks across days show patterns suggesting a key schedule."""
    
    # For each day, determine implied XOR mask from price patterns
    daily_patterns = []
    
    for df, date in zip(dfs, dates):
        if df.empty:
            continue
            
        prices = df["price"].dropna().values[:100]
        if len(prices) < 10:
            continue
        
        # LSB patterns
        cents = (prices * 100).astype(int) % 100
        lsb = cents % 2
        
        # Pack LSBs into bytes
        lsb_bytes = []
        for i in range(0, len(lsb) - 7, 8):
            byte_val = 0
            for j in range(8):
                byte_val = (byte_val << 1) | lsb[i + j]
            lsb_bytes.append(byte_val)
        
        if lsb_bytes:
            # Look for common XOR mask
            # If data is masked, XORing with itself should show pattern
            xor_adjacent = [lsb_bytes[i] ^ lsb_bytes[i+1] for i in range(len(lsb_bytes) - 1)]
            common_xor = max(set(xor_adjacent), key=xor_adjacent.count) if xor_adjacent else 0
            
            daily_patterns.append({
                "date": date,
                "lsb_bytes_sample": lsb_bytes[:8],
                "common_xor": common_xor,
                "xor_frequency": xor_adjacent.count(common_xor) / len(xor_adjacent) if xor_adjacent else 0
            })
    
    # Look for pattern across days
    if len(daily_patterns) >= 3:
        common_xors = [d["common_xor"] for d in daily_patterns]
        xor_sequence = common_xors
        
        # Check if XORs form a pattern (incrementing, etc.)
        diffs = [xor_sequence[i+1] - xor_sequence[i] for i in range(len(xor_sequence) - 1)]
        is_arithmetic = len(set(diffs)) == 1 if diffs else False
        
        return {
            "daily_patterns": daily_patterns,
            "xor_sequence": xor_sequence,
            "is_arithmetic_sequence": is_arithmetic,
            "sequence_diff": diffs[0] if is_arithmetic and diffs else None,
            "suggests_key_schedule": is_arithmetic
        }
    
    return {"daily_patterns": daily_patterns, "insufficient_data": True}


# ========================================================================
# MAIN ANALYSIS
# ========================================================================

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("DEEP FORENSIC ANALYSIS OF POWER TRACKS")
    print("Approaching WITHOUT documentation to discover hidden structure")
    print("=" * 70)
    
    results = {}
    
    # Load sample data
    sample_dirs = sorted(DATA_DIR.glob("sample_*"))[:10]
    dfs = []
    dates = []
    
    for sample_dir in sample_dirs:
        trades_files = list(sample_dir.glob("raw_ticks/*_trades.csv"))
        if trades_files:
            df = pd.read_csv(trades_files[0])
            if "price" in df.columns:
                dfs.append(df)
                dates.append(sample_dir.name.replace("sample_", ""))
    
    if not dfs:
        print("No data found!")
        return
    
    print(f"\nLoaded {len(dfs)} days of data")
    
    # ============================================================
    # PART 1: RAW DATA ANALYSIS
    # ============================================================
    print("\n" + "=" * 70)
    print("PART 1: RAW DATA ANALYSIS (No encoding assumptions)")
    print("=" * 70)
    
    raw_analysis = analyze_raw_bytes(dfs[0])
    results["raw_analysis"] = raw_analysis
    
    for encoding, data in raw_analysis.items():
        print(f"  {encoding}: entropy={data['entropy']:.3f}, ones_ratio={data['ones_ratio']:.3f}")
    
    # ============================================================
    # PART 2: CRYPTOGRAPHIC PATTERN DETECTION
    # ============================================================
    print("\n" + "=" * 70)
    print("PART 2: CRYPTOGRAPHIC PATTERN DETECTION")
    print("=" * 70)
    
    # Convert first 1000 prices to bytes
    prices = dfs[0]["price"].dropna().values[:1000]
    price_bytes = b''.join(struct.pack('d', p) for p in prices)
    
    crypto_analysis = detect_crypto_signatures(price_bytes)
    results["crypto_detection"] = crypto_analysis
    
    print(f"  Entropy: {crypto_analysis['entropy']:.3f} (max 8.0)")
    print(f"  High entropy (crypto-like): {crypto_analysis['has_high_entropy']}")
    print(f"  Block alignment: {crypto_analysis.get('potential_block_sizes', [])}")
    print(f"  Potential signatures: {crypto_analysis['potential_signatures']}")
    
    # Test for repeating key
    key_analysis = look_for_repeating_keys(price_bytes)
    results["key_analysis"] = key_analysis
    
    print("\n  Key detection tests:")
    for key_len, data in key_analysis.items():
        if data["entropy_reduction"] > 0.5 or data["has_text"]:
            print(f"    {key_len}-byte key: entropy_reduction={data['entropy_reduction']:.3f}, has_text={data['has_text']}")
    
    # ============================================================
    # PART 3: ALTERNATIVE ENCODING METHODS
    # ============================================================
    print("\n" + "=" * 70)
    print("PART 3: ALTERNATIVE ENCODING METHODS")
    print("=" * 70)
    
    encoding_analysis = test_alternative_encodings(prices.tolist())
    results["encoding_analysis"] = encoding_analysis
    
    print("  Encoding efficiency comparison:")
    for method, data in encoding_analysis.items():
        print(f"    {method}: bits_needed={data.get('max_bits_needed', 'N/A')}, entropy={data.get('entropy', 0):.3f}")
    
    # ============================================================
    # PART 4: OPCODE DERIVATION
    # ============================================================
    print("\n" + "=" * 70)
    print("PART 4: OPCODE DERIVATION FROM DATA")
    print("=" * 70)
    
    opcode_analysis = analyze_opcodes_from_data(prices.tolist())
    results["opcode_derivation"] = opcode_analysis
    
    print("  Delta classifications:")
    for cls, pct in opcode_analysis["percentages"].items():
        print(f"    {cls}: {pct}%")
    print(f"  Optimal encoding: {opcode_analysis['optimal_encoding']}")
    
    # ============================================================
    # PART 5: XOR MASK PATTERNS ACROSS DAYS
    # ============================================================
    print("\n" + "=" * 70)
    print("PART 5: XOR MASK PATTERN ANALYSIS")
    print("=" * 70)
    
    xor_analysis = analyze_xor_mask_patterns(dfs, dates)
    results["xor_mask_analysis"] = xor_analysis
    
    if "suggests_key_schedule" in xor_analysis:
        print(f"  Suggests key schedule: {xor_analysis['suggests_key_schedule']}")
        if xor_analysis.get("xor_sequence"):
            print(f"  XOR sequence: {xor_analysis['xor_sequence'][:5]}...")
    else:
        print("  Insufficient data for pattern analysis")
    
    # ============================================================
    # SUMMARY
    # ============================================================
    print("\n" + "=" * 70)
    print("FORENSIC SUMMARY")
    print("=" * 70)
    
    summary = {
        "crypto_detected": crypto_analysis["has_high_entropy"] or crypto_analysis["has_key_like_patterns"],
        "key_schedule_detected": xor_analysis.get("suggests_key_schedule", False),
        "alternative_encoding_better": encoding_analysis["double_delta"]["entropy"] < encoding_analysis["delta"]["entropy"],
        "opcode_inefficiency": opcode_analysis["percentages"].get("mirror", 0) > 5,
        "hidden_channel_capacity_bits": sum(1 for k, v in opcode_analysis["percentages"].items() if v < 1)
    }
    results["summary"] = summary
    
    print(f"  Cryptographic patterns detected: {summary['crypto_detected']}")
    print(f"  Key schedule detected: {summary['key_schedule_detected']}")
    print(f"  Alternative encoding better: {summary['alternative_encoding_better']}")
    print(f"  Opcode inefficiency (mirror patterns): {summary['opcode_inefficiency']}")
    
    # Save results
    with open(OUTPUT_DIR / "forensic_analysis.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": results
        }, f, indent=2, default=str)
    
    # Generate report
    with open(OUTPUT_DIR / "forensic_analysis_report.md", "w") as f:
        f.write("# Deep Forensic Analysis of Power Tracks\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        f.write("> **Approach**: Analyzed data WITHOUT using documented encodings to discover hidden structure.\n\n")
        
        f.write("## Key Findings\n\n")
        f.write(f"| Question | Finding |\n")
        f.write(f"|----------|--------|\n")
        f.write(f"| Cryptographic patterns? | {'⚠️ YES' if summary['crypto_detected'] else '✅ NO'} |\n")
        f.write(f"| Key schedule detected? | {'⚠️ YES' if summary['key_schedule_detected'] else '✅ NO'} |\n")
        f.write(f"| Better encoding exists? | {'⚠️ YES' if summary['alternative_encoding_better'] else '✅ NO'} |\n")
        f.write(f"| Opcode inefficiency? | {'⚠️ YES' if summary['opcode_inefficiency'] else '✅ NO'} |\n")
        
        f.write("\n## Raw Data Analysis\n\n")
        f.write("| Format | Entropy | Ones Ratio |\n")
        f.write("|--------|---------|------------|\n")
        for encoding, data in raw_analysis.items():
            f.write(f"| {encoding} | {data['entropy']:.3f} | {data['ones_ratio']:.3f} |\n")
        
        f.write("\n## Encoding Comparison\n\n")
        f.write("| Method | Bits Needed | Entropy |\n")
        f.write("|--------|-------------|--------|\n")
        for method, data in encoding_analysis.items():
            f.write(f"| {method} | {data.get('max_bits_needed', 'N/A')} | {data.get('entropy', 0):.3f} |\n")
        
        f.write("\n## Interpretation\n\n")
        if summary['crypto_detected'] or summary['key_schedule_detected']:
            f.write("> ⚠️ **Potential hidden structure detected** - Requires deeper investigation\n")
        else:
            f.write("> ✅ **No obvious cryptographic or key-based patterns detected**\n")
            f.write("> The encoding appears to be functional rather than steganographic.\n")
    
    print("\n" + "=" * 70)
    print("FORENSIC ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
