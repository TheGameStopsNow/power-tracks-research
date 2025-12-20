#!/usr/bin/env python3
"""
Standalone CRC Verifier Script

Verifies CRC checksums on Power Track frames using CRC-7, CRC-16-CCITT,
and CRC-16-X25 algorithms for comparison.
"""

import argparse
import sys
from pathlib import Path
from typing import Sequence

# Import CRC functions from test suite
sys.path.insert(0, str(Path(__file__).parent.parent / 'tests'))
from test_crc import crc7, crc16_ccitt, crc16_x25


def verify_frame_crc7(frame_bytes: bytes, xor_mask: int = 0x00) -> tuple[bool, int, int]:
    """
    Verify CRC-7 on a Power Track frame.
    
    Args:
        frame_bytes: Raw frame bytes (7+ bytes)
        xor_mask: XOR mask to apply before validation
        
    Returns:
        Tuple of (is_valid, computed_crc, expected_crc)
    """
    if len(frame_bytes) < 7:
        return False, 0, 0
    
    # Apply XOR mask
    unmasked = bytes(b ^ xor_mask for b in frame_bytes)
    
    # Extract header (bytes 0-5)
    header = unmasked[:6]
    
    # Extract expected CRC from trailer (byte 6, bits 7-1)
    trailer_byte = unmasked[6]
    expected_crc = (trailer_byte >> 1) & 0x7F
    
    # Compute CRC-7 over header
    computed_crc = crc7(header)
    
    # If there's a payload, include it in CRC calculation
    if len(unmasked) > 7:
        payload = unmasked[6:-1]  # Exclude trailer byte
        computed_crc = crc7(list(header) + list(payload))
    
    is_valid = computed_crc == expected_crc
    
    return is_valid, computed_crc, expected_crc


def discover_xor_mask(frame_bytes: bytes, mask_range: range = range(0x00, 0x20)) -> int | None:
    """
    Discover XOR mask by testing CRC validation.
    
    Args:
        frame_bytes: Raw frame bytes
        mask_range: Range of masks to test (default 0x00-0x1F)
        
    Returns:
        Best mask key or None if none found
    """
    best_mask = None
    best_score = -1
    
    for mask in mask_range:
        is_valid, _, _ = verify_frame_crc7(frame_bytes, mask)
        if is_valid:
            # If multiple masks work, prefer lower values
            if best_mask is None or mask < best_mask:
                best_mask = mask
                best_score = 1
    
    return best_mask


def main():
    parser = argparse.ArgumentParser(
        description='Verify CRC checksums on Power Track frames'
    )
    parser.add_argument(
        'input',
        type=Path,
        help='Input file containing frame data (binary)'
    )
    parser.add_argument(
        '--mask',
        type=lambda x: int(x, 0),  # Support hex (0x07) and decimal
        default=0x00,
        help='XOR mask to apply (default: 0x00, use --discover to auto-detect)'
    )
    parser.add_argument(
        '--discover',
        action='store_true',
        help='Automatically discover XOR mask'
    )
    parser.add_argument(
        '--compare-all',
        action='store_true',
        help='Compare CRC-7, CRC-16-CCITT, and CRC-16-X25'
    )
    parser.add_argument(
        '--frame-size',
        type=int,
        default=7,
        help='Frame size in bytes (default: 7)'
    )
    
    args = parser.parse_args()
    
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    # Read frame data
    frame_data = args.input.read_bytes()
    
    if len(frame_data) < args.frame_size:
        print(f"Error: File too small ({len(frame_data)} bytes < {args.frame_size} bytes)", file=sys.stderr)
        sys.exit(1)
    
    # Discover mask if requested
    mask = args.mask
    if args.discover:
        discovered_mask = discover_xor_mask(frame_data[:args.frame_size])
        if discovered_mask is not None:
            mask = discovered_mask
            print(f"Discovered XOR mask: 0x{mask:02X}")
        else:
            print("Warning: Could not discover XOR mask, using 0x00", file=sys.stderr)
    
    # Verify CRC-7
    is_valid, computed_crc, expected_crc = verify_frame_crc7(frame_data[:args.frame_size], mask)
    
    print(f"\nCRC-7 Verification")
    print(f"===================")
    print(f"XOR Mask: 0x{mask:02X}")
    print(f"Expected CRC-7: 0x{expected_crc:02X}")
    print(f"Computed CRC-7: 0x{computed_crc:02X}")
    print(f"Valid: {'YES' if is_valid else 'NO'}")
    
    # Compare with other CRC types if requested
    if args.compare_all:
        unmasked = bytes(b ^ mask for b in frame_data[:args.frame_size])
        header = unmasked[:6]
        
        crc16_ccitt_val = crc16_ccitt(list(header))
        crc16_x25_val = crc16_x25(list(header))
        
        print(f"\nCRC Comparison")
        print(f"==============")
        print(f"CRC-7:        0x{computed_crc:02X}")
        print(f"CRC-16-CCITT: 0x{crc16_ccitt_val:04X}")
        print(f"CRC-16-X25:   0x{crc16_x25_val:04X}")
    
    sys.exit(0 if is_valid else 1)


if __name__ == '__main__':
    main()


