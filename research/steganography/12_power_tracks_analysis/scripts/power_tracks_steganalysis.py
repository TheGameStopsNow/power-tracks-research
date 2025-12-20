#!/usr/bin/env python3
"""
Phase 9: Power Tracks Binary Protocol Steganalysis
===================================================

Analyzes the Power Tracks frame format for steganographic capacity:
1. Frame encoding entropy vs theoretical maximum
2. XOR mask patterns (5 bits of potential hiding space)
3. CRC-7 slack bits analysis
4. Zig-zag encoding inefficiencies
5. Hidden capacity estimation
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
        """Fallback CRC-7 implementation."""
        crc = 0
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ 0x89
                else:
                    crc <<= 1
        return crc & 0x7F

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "samples"
OUTPUT_DIR = Path(__file__).resolve().parent / "results"


def analyze_frame_entropy(frame: bytes) -> dict:
    """Analyze entropy of a Power Track frame."""
    if len(frame) < 17:
        return {"error": "Frame too short"}
    
    # Header analysis (bytes 0-15)
    header = frame[:16]
    payload = frame[16:-1] if len(frame) > 17 else b''
    trailer = frame[-1]
    
    # Byte-level entropy
    byte_counts = np.bincount(list(frame), minlength=256)
    byte_probs = byte_counts / len(frame)
    byte_entropy = -np.sum(byte_probs[byte_probs > 0] * np.log2(byte_probs[byte_probs > 0]))
    max_byte_entropy = np.log2(256)  # 8 bits
    
    # Bit-level entropy
    bits = []
    for b in frame:
        for i in range(8):
            bits.append((b >> (7 - i)) & 1)
    bits = np.array(bits)
    bit_entropy = stats.entropy([bits.mean(), 1 - bits.mean()], base=2) if 0 < bits.mean() < 1 else 0
    
    # Theoretical minimum encoding size
    # For delta-encoded prices, theoretical minimum is ~log2(price_range)
    
    return {
        "frame_bytes": len(frame),
        "frame_bits": len(frame) * 8,
        "header_bytes": 16,
        "payload_bytes": len(payload),
        "byte_entropy": float(byte_entropy),
        "max_byte_entropy": float(max_byte_entropy),
        "entropy_ratio": float(byte_entropy / max_byte_entropy),
        "bit_entropy": float(bit_entropy),
        "ones_ratio": float(bits.mean()),
        "zeros_ratio": float(1 - bits.mean())
    }


def analyze_xor_mask_space(frame: bytes) -> dict:
    """Analyze XOR mask discovery space for hidden capacity."""
    valid_masks = []
    
    for mask in range(0x20):  # Test masks 0x00-0x1F
        unmasked = bytes(b ^ mask for b in frame)
        
        # Check if CRC validates with this mask
        if len(unmasked) >= 17:
            header_payload = unmasked[:-1]
            expected_crc = unmasked[-1] & 0x7F
            computed_crc = crc7(list(header_payload)) & 0x7F
            
            if computed_crc == expected_crc:
                valid_masks.append(mask)
    
    # Calculate hiding capacity
    # Each valid mask represents log2(n_valid_masks) bits of ambiguity
    n_valid = len(valid_masks)
    hiding_bits = np.log2(n_valid) if n_valid > 1 else 0
    
    return {
        "masks_tested": 32,
        "valid_masks": valid_masks,
        "n_valid_masks": n_valid,
        "mask_hiding_bits": float(hiding_bits),
        "mask_entropy": float(stats.entropy([1/n_valid]*n_valid, base=2)) if n_valid > 0 else 0
    }


def analyze_crc_slack(frame: bytes) -> dict:
    """Analyze CRC-7 for potential slack bits."""
    if len(frame) < 17:
        return {"error": "Frame too short"}
    
    trailer = frame[-1]
    crc_value = trailer & 0x7F  # 7 bits used for CRC
    slack_bit = (trailer >> 7) & 1  # 1 bit potentially unused
    
    # The trailer byte has 1 potentially unused bit (MSB)
    # This could encode 1 bit of hidden data
    
    return {
        "trailer_byte": trailer,
        "crc7_value": crc_value,
        "slack_bit": slack_bit,
        "potential_hiding_bits": 1,  # MSB of trailer
        "crc_valid": True  # Assuming frame passed validation
    }


def analyze_varint_inefficiency(frame: bytes) -> dict:
    """Analyze varint encoding for potential slack."""
    if len(frame) < 17:
        return {"error": "Frame too short"}
    
    payload = frame[16:-1]
    
    if len(payload) == 0:
        return {"error": "No payload"}
    
    # Count continuation bits (MSB of each byte)
    continuation_bits = [(b >> 7) & 1 for b in payload]
    
    # Analyze varint structure
    varints = []
    current_value = 0
    current_bytes = 0
    
    for b in payload:
        current_value |= (b & 0x7F) << (7 * current_bytes)
        current_bytes += 1
        if not (b & 0x80):  # End of varint
            varints.append({"value": current_value, "bytes": current_bytes})
            current_value = 0
            current_bytes = 0
    
    # Calculate encoding efficiency
    total_bits_used = len(payload) * 8
    data_bits = len(payload) * 7  # 7 bits per byte (1 bit for continuation)
    overhead_bits = total_bits_used - data_bits
    
    # Theoretical minimum: each varint needs ceil(log2(value+1)) bits
    theoretical_min = sum(max(1, int(np.ceil(np.log2(v["value"] + 1)))) for v in varints if v["value"] >= 0)
    slack_bits = data_bits - theoretical_min if theoretical_min > 0 else 0
    
    return {
        "payload_bytes": len(payload),
        "n_varints": len(varints),
        "total_bits": total_bits_used,
        "data_bits": data_bits,
        "overhead_bits": overhead_bits,
        "overhead_ratio": float(overhead_bits / total_bits_used) if total_bits_used > 0 else 0,
        "theoretical_min_bits": theoretical_min,
        "slack_bits": max(0, slack_bits),
        "continuation_bits": continuation_bits[:20]  # First 20
    }


def estimate_hiding_capacity(frame: bytes) -> dict:
    """Estimate total steganographic hiding capacity of a frame."""
    xor_analysis = analyze_xor_mask_space(frame)
    crc_analysis = analyze_crc_slack(frame)
    varint_analysis = analyze_varint_inefficiency(frame)
    entropy_analysis = analyze_frame_entropy(frame)
    
    # Sum up hiding capacity from different channels
    mask_bits = xor_analysis.get("mask_hiding_bits", 0)
    slack_bits = crc_analysis.get("potential_hiding_bits", 0)
    varint_slack = varint_analysis.get("slack_bits", 0) if "slack_bits" in varint_analysis else 0
    
    # Entropy slack: difference from maximum
    entropy_slack = (1 - entropy_analysis.get("entropy_ratio", 1)) * entropy_analysis.get("frame_bits", 0)
    
    total_capacity = mask_bits + slack_bits + varint_slack
    
    return {
        "xor_mask_bits": mask_bits,
        "crc_slack_bits": slack_bits,
        "varint_slack_bits": varint_slack,
        "entropy_slack_bits": float(entropy_slack),
        "total_hiding_bits": total_capacity,
        "total_hiding_bytes": total_capacity / 8,
        "frame_size_bits": entropy_analysis.get("frame_bits", 0),
        "hiding_ratio": float(total_capacity / entropy_analysis.get("frame_bits", 1))
    }


def encode_test_frame(prices: list) -> bytes:
    """Create a test frame from price data."""
    PRICE_SCALE = 10_000
    
    def zig_zag_encode(value: int) -> int:
        return (value << 1) ^ (value >> 63)
    
    def encode_varint(value: int) -> list:
        remaining = max(0, value)
        out = []
        while remaining >= 0x80:
            out.append(int((remaining & 0x7F) | 0x80))
            remaining >>= 7
        out.append(int(remaining))
        return out
    
    if len(prices) < 2:
        return b''
    
    anchor_price = int(prices[0] * PRICE_SCALE)
    
    # Build header (16 bytes)
    header = bytearray(16)
    header[0] = 0x1A  # Opcode
    header[1] = 1     # Version
    header[2:6] = (0).to_bytes(4, "little")  # Start time
    header[6:8] = (60).to_bytes(2, "little")  # Duration
    header[8] = 4     # Compression ratio
    header[9:13] = anchor_price.to_bytes(4, "little")
    header[13:16] = (1000).to_bytes(3, "little")  # Volume hint
    
    # Build payload
    payload_bytes = []
    prev = anchor_price
    for price in prices[1:]:
        target = int(price * PRICE_SCALE)
        delta = target - prev
        prev = target
        payload_bytes.extend(encode_varint(zig_zag_encode(delta)))
    
    # Build frame
    body = bytes(header) + bytes(payload_bytes)
    trailer = crc7(list(body)) & 0x7F
    frame = body + bytes([trailer])
    
    return frame


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("POWER TRACKS BINARY PROTOCOL STEGANALYSIS")
    print("=" * 70)
    
    # Generate test frames from actual data
    sample_dirs = sorted(DATA_DIR.glob("sample_*"))[:5]
    
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
        
        # Create test frame
        frame = encode_test_frame(prices)
        
        if len(frame) < 17:
            continue
        
        print(f"  Frame size: {len(frame)} bytes ({len(frame)*8} bits)")
        
        # Run analysis
        entropy = analyze_frame_entropy(frame)
        xor_mask = analyze_xor_mask_space(frame)
        crc_slack = analyze_crc_slack(frame)
        varint = analyze_varint_inefficiency(frame)
        capacity = estimate_hiding_capacity(frame)
        
        result = {
            "date": date,
            "frame_bytes": len(frame),
            "entropy": entropy,
            "xor_mask": xor_mask,
            "crc_slack": crc_slack,
            "varint": varint,
            "hiding_capacity": capacity
        }
        results.append(result)
        
        print(f"  Entropy ratio: {entropy['entropy_ratio']:.3f}")
        print(f"  Valid XOR masks: {xor_mask['n_valid_masks']}")
        print(f"  Total hiding capacity: {capacity['total_hiding_bits']:.1f} bits")
    
    # Summary
    hiding_bits = [r["hiding_capacity"]["total_hiding_bits"] for r in results]
    frame_sizes = [r["frame_bytes"] for r in results]
    
    summary = {
        "frames_analyzed": len(results),
        "mean_frame_bytes": float(np.mean(frame_sizes)),
        "mean_hiding_bits": float(np.mean(hiding_bits)),
        "max_hiding_bits": float(max(hiding_bits)),
        "mean_hiding_ratio": float(np.mean([r["hiding_capacity"]["hiding_ratio"] for r in results]))
    }
    
    # Save results
    with open(OUTPUT_DIR / "power_tracks_analysis.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
            "results": results
        }, f, indent=2, default=str)
    
    # Generate report
    with open(OUTPUT_DIR / "power_tracks_report.md", "w") as f:
        f.write("# Power Tracks Binary Protocol Steganalysis\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Summary\n\n")
        f.write(f"- Frames analyzed: {summary['frames_analyzed']}\n")
        f.write(f"- Mean frame size: {summary['mean_frame_bytes']:.0f} bytes\n")
        f.write(f"- **Mean hiding capacity: {summary['mean_hiding_bits']:.1f} bits**\n")
        f.write(f"- **Max hiding capacity: {summary['max_hiding_bits']:.1f} bits**\n")
        
        f.write("\n## Hiding Channels\n\n")
        f.write("| Channel | Bits Available | Description |\n")
        f.write("|---------|----------------|-------------|\n")
        
        # Average across results
        avg_xor = np.mean([r["xor_mask"]["mask_hiding_bits"] for r in results])
        avg_crc = np.mean([r["crc_slack"]["potential_hiding_bits"] for r in results])
        avg_varint = np.mean([r["varint"].get("slack_bits", 0) for r in results])
        
        f.write(f"| XOR Mask Ambiguity | {avg_xor:.2f} | Multiple valid masks |\n")
        f.write(f"| CRC Trailer Slack | {avg_crc:.2f} | Unused MSB in trailer |\n")
        f.write(f"| Varint Inefficiency | {avg_varint:.2f} | Suboptimal encoding |\n")
        f.write(f"| **Total** | **{avg_xor + avg_crc + avg_varint:.2f}** | Per frame |\n")
        
        f.write("\n## Per-Frame Results\n\n")
        f.write("| Date | Frame Bytes | Entropy Ratio | Hiding Bits |\n")
        f.write("|------|-------------|---------------|-------------|\n")
        for r in results:
            f.write(f"| {r['date']} | {r['frame_bytes']} | {r['entropy']['entropy_ratio']:.3f} | {r['hiding_capacity']['total_hiding_bits']:.1f} |\n")
        
        f.write("\n## Interpretation\n\n")
        if summary['mean_hiding_bits'] > 5:
            f.write("> ⚠️ **Significant hiding capacity detected in Power Track frames**\n\n")
            f.write("The frame format has inherent slack that could be exploited for covert communication.\n")
        else:
            f.write("> ✅ Frame format is efficiently encoded with minimal hiding capacity.\n")
    
    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print(f"Mean hiding capacity: {summary['mean_hiding_bits']:.1f} bits per frame")
    print("=" * 70)


if __name__ == "__main__":
    main()
