#!/usr/bin/env python3
"""
Raw → Frames → Signals Pipeline Script

Converts raw tick data to decoded frames and unfolded price paths.
"""

import argparse
import sys
from pathlib import Path
from typing import Optional, List, Dict, Tuple
import pandas as pd
import numpy as np
import sqlite3

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.test_crc import crc7


PRICE_SCALE = 10_000
MAX_BURST_POINTS = 256


def to_utc_ms(ts: str) -> int:
    """Convert timestamp string to UTC milliseconds since epoch."""
    return int(pd.to_datetime(ts, utc=True).timestamp() * 1000)


def normalize_window_ticks(df: pd.DataFrame) -> List[Dict]:
    """Normalize and sort ticks."""
    ticks = []
    for _, row in df.iterrows():
        try:
            ts = to_utc_ms(row["timestamp"])
        except Exception:
            continue
        price = float(row["price"])
        if not np.isfinite(price):
            continue
        volume = row.get("volume", 1)
        try:
            volume = float(volume)
        except Exception:
            volume = 1.0
        if volume <= 0:
            volume = 1.0
        ticks.append({"ts": ts, "price": price, "volume": volume})
    ticks.sort(key=lambda t: t["ts"])
    return ticks


def downsample_ticks(ticks: List[Dict], max_points: int = MAX_BURST_POINTS) -> List[Dict]:
    """Stride-based downsample, preserving last point (matches core implementation)."""
    if len(ticks) <= max_points:
        return ticks
    stride = max(1, len(ticks) // max_points)
    sampled = [ticks[i] for i in range(0, len(ticks), stride)]
    if sampled[-1]["ts"] != ticks[-1]["ts"]:
        sampled.append(ticks[-1])
    return sampled


def compute_start_time_ms(first_tick: Dict, detection_time: Optional[pd.Timestamp]) -> int:
    """Start time milliseconds since midnight UTC of detection date (fits in 32 bits)."""
    reference = detection_time or pd.to_datetime(first_tick["ts"], unit="ms", utc=True)
    midnight = pd.Timestamp(
        year=reference.year, month=reference.month, day=reference.day, tz="UTC"
    )
    delta_ms = max(0, first_tick["ts"] - int(midnight.timestamp() * 1000))
    return min(0xFFFFFFFF, int(delta_ms))


def compute_duration_seconds(start: Dict, end: Dict) -> int:
    duration = max(1, round((end["ts"] - start["ts"]) / 1000))
    return min(0xFFFF, duration)


def zig_zag_encode(value: int) -> int:
    return (value << 1) ^ (value >> 63)


def encode_varint(value: int) -> List[int]:
    remaining = max(0, value)
    out: List[int] = []
    while remaining >= 0x80:
        out.append(int((remaining & 0x7F) | 0x80))
        remaining >>= 7
    out.append(int(remaining))
    return out


def encode_frame(ticks: List[Dict], detection_time: Optional[str]) -> Tuple[bytes, Dict]:
    """Encode ticks into a single Power Track frame (mirror of core buildEncodedBurstFromWindowTicks)."""
    if len(ticks) < 2:
        raise ValueError("Need at least 2 ticks to encode a frame")

    sampled = downsample_ticks(ticks)
    if len(sampled) < 2:
        raise ValueError("Downsampled ticks insufficient")

    anchor_price = round(sampled[0]["price"] * PRICE_SCALE)
    header = bytearray(16)
    header[0] = 0x1A
    header[1] = 1
    header[2:6] = compute_start_time_ms(sampled[0], pd.to_datetime(detection_time, utc=True) if detection_time else None).to_bytes(4, "little")
    header[6:8] = compute_duration_seconds(sampled[0], sampled[-1]).to_bytes(2, "little")
    header[8] = 4
    header[9:13] = max(0, anchor_price).to_bytes(4, "little", signed=False)
    volume_hint = int(min(0xFFFFFF, round(sum(t["volume"] for t in sampled))))
    header[13] = volume_hint & 0xFF
    header[14] = (volume_hint >> 8) & 0xFF
    header[15] = (volume_hint >> 16) & 0xFF

    payload_bytes: List[int] = []
    prev = anchor_price
    for tick in sampled[1:]:
        target = round(tick["price"] * PRICE_SCALE)
        delta = target - prev
        prev = target
        payload_bytes.extend(encode_varint(zig_zag_encode(delta)))

    body = bytes(header) + bytes(payload_bytes)
    trailer_val = crc7(list(body)) & 0x7F
    frame = body + bytes([trailer_val])

    meta = {
        "frame_bits": len(frame) * 8,
        "offset_bits": 0,
        "bit_order": "big",
        "mask_key": 0,
        "trailer_bytes": 1,
        "header_bytes": len(header),
        "payload_offset": len(header),
        "anchor_price": anchor_price,
        "volume_hint": volume_hint,
        "sampled_points": len(sampled),
    }
    return frame, meta


def parse_varints(buffer: bytes) -> List[int]:
    vals: List[int] = []
    acc = 0
    shift = 0
    for b in buffer:
        acc |= (b & 0x7F) << shift
        if b & 0x80:
            shift += 7
            continue
        vals.append(acc)
        acc = 0
        shift = 0
    if shift != 0:
        vals.append(acc)
    return vals


def zig_zag_decode(value: int) -> int:
    return (value >> 1) ^ (-(value & 1))


def decode_frame(frame: bytes) -> Dict:
    if len(frame) < 17:
        raise ValueError("Frame too short")
    header = frame[:16]
    trailer = frame[-1]
    payload = frame[16:-1]
    expected_crc = trailer & 0x7F
    computed_crc = crc7(list(header + payload))
    varints = parse_varints(payload)
    deltas = [zig_zag_decode(v) for v in varints]
    anchor_price = int.from_bytes(header[9:13], "little", signed=False)
    prices = [anchor_price]
    for d in deltas:
        prices.append(prices[-1] + d)
    return {
        "opcode": header[0],
        "version": header[1],
        "start_time_ms": int.from_bytes(header[2:6], "little", signed=False),
        "duration_seconds": int.from_bytes(header[6:8], "little", signed=False),
        "compression_ratio": header[8],
        "anchor_price": anchor_price,
        "volume_hint": header[13] | (header[14] << 8) | (header[15] << 16),
        "varints": varints,
        "deltas": deltas,
        "prices": prices,
        "crc7_computed": computed_crc & 0x7F,
        "crc7_expected": expected_crc,
        "valid": (computed_crc & 0x7F) == expected_crc,
    }


def chunk_list(items: List[Dict], chunk_size: int) -> List[List[Dict]]:
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def process_raw_ticks(
    input_file: Path,
    output_file: Path,
    format_type: str = 'binary',
    detection_time: Optional[str] = None,
    max_ticks: Optional[int] = None,
    chunk_size: Optional[int] = None
):
    """Process raw tick data to extract frames (multi-frame burst)."""
    print(f"Reading raw ticks from: {input_file}")
    
    df = pd.read_csv(input_file)
    if max_ticks is not None and max_ticks > 0:
        df = df.head(max_ticks)
        print(f"Input capped to first {max_ticks:,} ticks for encoding (requested cap)")
    if "price" not in df.columns:
        raise ValueError("Input data must be tick-level trades with a 'price' column (minute bars detected).")
    
    ticks = normalize_window_ticks(df)
    if len(ticks) < 2:
        raise ValueError("Not enough ticks to encode frames.")
    
    chunk_sz = chunk_size or len(ticks)
    tick_chunks = chunk_list(ticks, chunk_sz)
    
    frames: List[bytes] = []
    meta_rows = []
    for idx, chunk in enumerate(tick_chunks):
        frame, meta = encode_frame(chunk, detection_time)
        frames.append(frame)
        meta_rows.append(
            {
                "frame_index": idx,
                "offset_bytes": 0,  # will fill later
                "length_bytes": len(frame),
                "opcode": frame[0],
                "version": frame[1],
                "start_time_us": int.from_bytes(frame[2:6], "little"),
                "duration_seconds": int.from_bytes(frame[6:8], "little"),
                "compression_ratio": frame[8],
                "anchor_price_usd": meta["anchor_price"] / PRICE_SCALE,
                "volume_hint": meta["volume_hint"],
                "crc7_computed": crc7(list(frame[:-1])) & 0x7F,
                "crc7_expected": frame[-1] & 0x7F,
                "valid": ((crc7(list(frame[:-1])) & 0x7F) == (frame[-1] & 0x7F)),
                "payload_bytes": len(frame) - 17,
                "sampled_points": meta["sampled_points"],
            }
        )
    
    # Write outputs with length-prefixed frames to allow multiple frames
    output_file.parent.mkdir(parents=True, exist_ok=True)
    offset = 0
    binary_blob = bytearray()
    for idx, frame in enumerate(frames):
        length_bytes = len(frame).to_bytes(4, "little")
        binary_blob.extend(length_bytes)
        binary_blob.extend(frame)
        meta_rows[idx]["offset_bytes"] = offset
        offset += 4 + len(frame)
    if format_type == 'binary':
        output_file.write_bytes(bytes(binary_blob))
        print(f"Wrote {len(binary_blob)} bytes to: {output_file} ({len(frames)} frame(s))")
        csv_path = output_file.with_suffix(".csv")
        pd.DataFrame(meta_rows).to_csv(csv_path, index=False)
        print(f"Wrote frame metadata CSV: {csv_path}")
    elif format_type == 'csv':
        pd.DataFrame(meta_rows).to_csv(output_file, index=False)
        print(f"Wrote frame metadata CSV: {output_file}")
    else:
        raise ValueError(f"Unknown format: {format_type}")


def decode_frames(input_file: Path, output_file: Path, _: Optional[int] = None):
    """Decode length-prefixed frames to price paths."""
    print(f"Reading frames from: {input_file}")
    
    data = input_file.read_bytes()
    if len(data) == 0:
        raise ValueError("Frames file is empty. Run the frame extractor first.")
    
    frames: List[bytes] = []
    offset = 0
    while offset + 4 <= len(data):
        length = int.from_bytes(data[offset : offset + 4], "little")
        offset += 4
        if offset + length > len(data):
            raise ValueError("Frame length prefix exceeds file size")
        frames.append(data[offset : offset + length])
        offset += length
    
    if not frames:
        raise ValueError("No frames parsed from file.")
    
    paths = []
    for frame_index, frame in enumerate(frames):
        decoded = decode_frame(frame)
        if not decoded["valid"]:
            raise ValueError(f"Frame {frame_index} CRC check failed.")
        prices = [p / PRICE_SCALE for p in decoded["prices"]]
        start_ms = decoded.get("start_time_ms", 0)
        duration_ms = decoded.get("duration_seconds", 0) * 1000
        steps = max(1, len(prices))
        for idx, price in enumerate(prices):
            # Linearly interpolate timestamps across the frame duration.
            if steps > 1 and duration_ms > 0:
                ts_ms = int(start_ms + (duration_ms * idx) / (steps - 1))
            else:
                ts_ms = start_ms
            paths.append({
                "frame_index": frame_index,
                "step_index": idx,
                "price": price,
                "delta": 0 if idx == 0 else prices[idx] - prices[idx - 1],
                "timestamp_ms": ts_ms,
                "timestamp_us": ts_ms * 1000
            })
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df_paths = pd.DataFrame(paths)
    df_paths.to_csv(output_file, index=False)
    try:
        df_paths.to_parquet(output_file.with_suffix(".parquet"), index=False)
    except Exception as exc:
        print(f"Warning: could not write Parquet ({exc})")
    try:
        sqlite_path = output_file.with_suffix(".sqlite")
        with sqlite3.connect(sqlite_path) as conn:
            df_paths.to_sql("price_paths", conn, if_exists="replace", index=False)
        print(f"Wrote SQLite: {sqlite_path}")
    except Exception as exc:
        print(f"Warning: could not write SQLite ({exc})")
    print(f"Wrote {len(paths)} price path points to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Convert raw tick data to decoded frames and price paths'
    )
    parser.add_argument(
        '--input',
        type=Path,
        required=True,
        help='Input file (CSV for raw ticks, binary for frames)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        required=True,
        help='Output file path'
    )
    parser.add_argument(
        '--format',
        choices=['binary', 'csv'],
        default='binary',
        help='Output format (default: binary)'
    )
    parser.add_argument(
        '--decode',
        action='store_true',
        help='Decode frames to price paths'
    )
    parser.add_argument(
        '--mask',
        type=lambda x: int(x, 0),
        help='XOR mask to use (e.g., 0x07)'
    )
    parser.add_argument(
        '--max-ticks',
        type=int,
        help='Optional cap on number of ticks to encode'
    )
    parser.add_argument(
        '--chunk-size',
        type=int,
        help='Optional chunk size (ticks per frame) for multi-frame output'
    )
    parser.add_argument(
        '--detection-time',
        help='Optional detection time (ISO8601) to anchor start_time_us'
    )
    
    args = parser.parse_args()
    
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    # Create output directory if needed
    args.output.parent.mkdir(parents=True, exist_ok=True)
    
    if args.decode:
        decode_frames(args.input, args.output, args.mask)
    else:
        process_raw_ticks(
            args.input,
            args.output,
            args.format,
            detection_time=args.detection_time,
            max_ticks=args.max_ticks,
            chunk_size=args.chunk_size
        )


if __name__ == '__main__':
    main()

