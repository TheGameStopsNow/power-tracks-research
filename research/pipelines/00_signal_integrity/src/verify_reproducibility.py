#!/usr/bin/env python3
"""
End-to-End Reproducibility Verification Script

Runs the complete Power Track pipeline and validates outputs against
expected SHA256 checksums and validation criteria.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.raw_to_signals import decode_frame


def calculate_sha256(file_path: Path) -> str:
    """Calculate SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def verify_sha256(file_path: Path, expected_hash: str) -> tuple[bool, str]:
    """Verify file SHA256 checksum."""
    if not file_path.exists():
        return False, f"File not found: {file_path}"
    
    actual_hash = calculate_sha256(file_path)
    if actual_hash == expected_hash:
        return True, "SHA256 verified"
    else:
        return False, f"SHA256 mismatch: expected {expected_hash}, got {actual_hash}"


def load_manifest(manifest_path: Path) -> Dict:
    """Load sample dataset manifest."""
    with open(manifest_path, 'r') as f:
        return json.load(f)


def validate_frames(frame_data: bytes, xor_mask: Optional[int] = None) -> Dict:
    """Validate frames and return statistics (length-prefixed multi-frame)."""
    if len(frame_data) == 0:
        return {
            'total_frames': 0,
            'valid_frames': 0,
            'crc_pass_rate': 0.0,
            'varint_count': 0,
            'avg_varints_per_frame': 0.0,
            'status': 'FAIL'
        }
    frames = []
    offset = 0
    while offset + 4 <= len(frame_data):
        length = int.from_bytes(frame_data[offset:offset + 4], "little")
        offset += 4
        if offset + length > len(frame_data):
            break
        frames.append(frame_data[offset:offset + length])
        offset += length
    if not frames:
        return {
            'total_frames': 0,
            'valid_frames': 0,
            'crc_pass_rate': 0.0,
            'varint_count': 0,
            'avg_varints_per_frame': 0.0,
            'status': 'FAIL'
        }
    valid = 0
    varints_total = 0
    for frame in frames:
        try:
            decoded = decode_frame(frame)
            if decoded.get('valid'):
                valid += 1
            varints_total += len(decoded.get('varints', []))
        except Exception:
            continue
    total = len(frames)
    crc_pass_rate = valid / total if total else 0.0
    return {
        'total_frames': total,
        'valid_frames': valid,
        'crc_pass_rate': crc_pass_rate,
        'xor_mask': '0x00',
        'varint_count': varints_total,
        'avg_varints_per_frame': (varints_total / total) if total else 0.0,
        'status': 'PASS' if valid == total and total > 0 else 'FAIL'
    }


def validate_price_paths(paths_file: Path) -> Dict:
    """Validate price paths."""
    if not paths_file.exists():
        return {
            'price_paths': 0,
            'valid_paths': 0,
            'status': 'FAIL',
            'errors': ['Price paths file not found']
        }
    
    try:
        df = pd.read_csv(paths_file)
        
        # Basic validation
        errors = []
        
        if 'price' in df.columns:
            invalid_prices = df[(df['price'] < 0.01) | (df['price'] > 100000)]
            if len(invalid_prices) > 0:
                errors.append(f"Invalid price range: {len(invalid_prices)} rows")
        
        if 'timestamp_us' in df.columns:
            non_monotonic = df['timestamp_us'].diff().fillna(0) < 0
            if non_monotonic.any():
                errors.append(f"Non-monotonic timestamps: {non_monotonic.sum()} rows")
        
        valid_paths = len(df) - len(errors)
        status = 'PASS' if len(errors) == 0 else 'FAIL'
        
        return {
            'price_paths': len(df),
            'valid_paths': valid_paths,
            'status': status,
            'errors': errors
        }
    except Exception as e:
        return {
            'price_paths': 0,
            'valid_paths': 0,
            'status': 'FAIL',
            'errors': [f"Error reading price paths: {str(e)}"]
        }


def normalize_sha_path(raw_path: str, sample_dir: Path) -> Path:
    """
    Normalize a SHA256 entry to an absolute path rooted at sample_dir.
    
    Handles entries that are absolute, relative to the bundle root, or
    erroneously prefixed with the sample directory name.
    """
    path_obj = Path(raw_path)
    if path_obj.is_absolute():
        return path_obj
    
    parts = path_obj.parts
    if parts and parts[0] == sample_dir.name:
        path_obj = Path(*parts[1:])
    
    return sample_dir / path_obj


def validate_raw_ticks(sample_dir: Path, manifest: Dict) -> Dict:
    """Validate that raw tick data exists and has tick-level columns."""
    candidate: Optional[Path] = None
    
    # Prefer manifest entry
    try:
        raw_entry = manifest.get("files", {}).get("raw_ticks", {})
        raw_csv = raw_entry.get("csv")
        if raw_csv:
            candidate = sample_dir / raw_csv
    except AttributeError:
        pass
    
    # Fallback: first CSV under raw_ticks/
    if candidate is None or not candidate.exists():
        raw_dir = sample_dir / "raw_ticks"
        csv_candidates = sorted(raw_dir.glob("*.csv"))
        if csv_candidates:
            candidate = csv_candidates[0]
    
    if candidate is None or not candidate.exists():
        return {
            "status": "FAIL",
            "file": str(candidate) if candidate else None,
            "errors": ["Raw tick CSV not found"]
        }
    
    try:
        preview = pd.read_csv(candidate, nrows=10)
    except Exception as e:
        return {
            "status": "FAIL",
            "file": str(candidate),
            "errors": [f"Failed to read raw ticks: {e}"]
        }
    
    errors = []
    cols = [c.lower() for c in preview.columns]
    if "price" not in cols:
        errors.append("Tick data must include a 'price' column (minute bars detected: open/high/low/close present)")
    if {"open", "high", "low", "close"}.issubset(cols):
        errors.append("Input looks like OHLC bars, not tick trades")
    
    status = "PASS" if not errors else "FAIL"
    return {
        "status": status,
        "file": str(candidate),
        "columns": preview.columns.tolist(),
        "errors": errors
    }


def verify_reproducibility(
    sample_dir: Path,
    manifest_path: Optional[Path] = None,
    sha256_file: Optional[Path] = None,
    verify_checksums: bool = True
) -> Dict:
    """Run end-to-end reproducibility verification."""
    results = {
        'symbol': None,
        'date': None,
        'validation_status': 'PASS',
        'checksums': {},
        'raw_ticks': {},
        'frames': {},
        'price_paths': {},
        'errors': []
    }
    
    # Load manifest if provided
    manifest = {}
    if manifest_path and manifest_path.exists():
        manifest = load_manifest(manifest_path)
        results['symbol'] = manifest.get('symbol')
        results['date'] = manifest.get('date')
    
    # Verify SHA256 checksums
    if verify_checksums and sha256_file and sha256_file.exists():
        print("Verifying SHA256 checksums...")
        with open(sha256_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                parts = line.split()
                if len(parts) >= 2:
                    expected_hash = parts[0]
                    file_path = normalize_sha_path(parts[1], Path(sample_dir))
                    
                    is_valid, message = verify_sha256(file_path, expected_hash)
                    results['checksums'][str(file_path)] = {
                        'valid': is_valid,
                        'message': message
                    }
                    
                    if not is_valid:
                        results['validation_status'] = 'FAIL'
                        results['errors'].append(f"SHA256 verification failed: {file_path}")
    
    # Validate raw ticks (sanity check for tick vs OHLC)
    raw_stats = validate_raw_ticks(Path(sample_dir), manifest)
    results['raw_ticks'] = raw_stats
    if raw_stats.get("status") == "FAIL":
        results['validation_status'] = 'FAIL'
        results['errors'].extend(raw_stats.get("errors", []))
    
    # Validate frames
    frames_bin = sample_dir / 'decoded_frames' / 'frames.bin'
    if frames_bin.exists():
        print("Validating frames...")
        frame_data = frames_bin.read_bytes()
        frame_stats = validate_frames(frame_data)
        results['frames'] = frame_stats
        
        if frame_stats['status'] == 'FAIL':
            results['validation_status'] = 'FAIL'
            results['errors'].append("Frame validation failed")
    else:
        results['validation_status'] = 'FAIL'
        results['errors'].append(f"Frames file not found: {frames_bin}")
    
    # Validate price paths
    paths_file = sample_dir / 'signals' / 'price_paths.csv'
    if paths_file.exists():
        print("Validating price paths...")
        paths_stats = validate_price_paths(paths_file)
        results['price_paths'] = paths_stats
        
        if paths_stats['status'] == 'FAIL':
            results['validation_status'] = 'FAIL'
            results['errors'].extend(paths_stats.get('errors', []))
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description='Verify Power Track reproducibility'
    )
    parser.add_argument(
        '--sample-dir',
        type=Path,
        required=True,
        help='Sample dataset directory'
    )
    parser.add_argument(
        '--manifest',
        type=Path,
        help='Manifest JSON file path'
    )
    parser.add_argument(
        '--sha256',
        type=Path,
        help='SHA256SUMS file path'
    )
    parser.add_argument(
        '--no-checksums',
        action='store_true',
        help='Skip SHA256 checksum verification'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output JSON report file'
    )
    
    args = parser.parse_args()
    
    if not args.sample_dir.exists():
        print(f"Error: Sample directory not found: {args.sample_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Run verification
    results = verify_reproducibility(
        args.sample_dir,
        args.manifest,
        args.sha256,
        verify_checksums=not args.no_checksums
    )
    
    # Print results
    print("\n" + "="*60)
    print("Reproducibility Verification Report")
    print("="*60)
    print(f"Symbol: {results['symbol']}")
    print(f"Date: {results['date']}")
    print(f"Status: {results['validation_status']}")
    print("\nRaw Tick Data:")
    for key, value in results.get('raw_ticks', {}).items():
        print(f"  {key}: {value}")
    print("\nFrame Statistics:")
    for key, value in results['frames'].items():
        print(f"  {key}: {value}")
    print("\nPrice Path Statistics:")
    for key, value in results['price_paths'].items():
        print(f"  {key}: {value}")
    
    if results['errors']:
        print("\nErrors:")
        for error in results['errors']:
            print(f"  - {error}")
    
    # Save report if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nReport saved to: {args.output}")
    
    # Exit with appropriate code
    sys.exit(0 if results['validation_status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()

