#!/usr/bin/env python3
"""
Frame Detection for EDGX Signals
==================================

Searches for frame synchronization markers (Start-of-Frame / End-of-Frame)
in extracted bitstreams. Uses correlation-based detection and pattern matching.
"""

from pathlib import Path
from typing import List, Tuple, Dict, Optional
import numpy as np
import pandas as pd
from scipy import signal
from collections import Counter


def find_sync_markers(
    bits: List[int],
    marker_length: int = 8,
    min_occurrences: int = 5,
    max_candidates: int = 10
) -> List[Tuple[str, int, List[int]]]:
    """
    Search for potential Start-of-Frame (SOF) markers.
    
    A good SOF marker appears frequently and at regular intervals.
    
    Args:
        bits: Bitstream to analyze
        marker_length: Length of marker to search for
        min_occurrences: Minimum times a pattern must appear
        max_candidates: Maximum number of candidates to return
    
    Returns:
        List of (pattern, count, positions)
    """
    bits_str = ''.join(map(str, bits))
    
    # Count all patterns of marker_length
    pattern_positions = {}
    for i in range(len(bits) - marker_length + 1):
        pattern = bits_str[i:i+marker_length]
        if pattern not in pattern_positions:
            pattern_positions[pattern] = []
        pattern_positions[pattern].append(i)
    
    # Filter by minimum occurrences
    candidates = [
        (pattern, len(positions), positions)
        for pattern, positions in pattern_positions.items()
        if len(positions) >= min_occurrences
    ]
    
    # Sort by occurrence count
    candidates.sort(key=lambda x: x[1], reverse=True)
    
    return candidates[:max_candidates]


def analyze_marker_spacing(positions: List[int]) -> Dict:
    """
    Analyze spacing between marker occurrences to detect frame structure.
    
    Regular spacing suggests frame boundaries.
    """
    if len(positions) < 2:
        return {'regularity': 0, 'mean_spacing': 0, 'std_spacing': 0}
    
    spacings = np.diff(positions)
    
    # Calculate coefficient of variation
    mean_spacing = spacings.mean()
    std_spacing = spacings.std()
    
    if mean_spacing > 0:
        cv = std_spacing / mean_spacing  # Lower CV = more regular
        regularity = 1.0 / (1.0 + cv)  # Normalize to 0-1 scale
    else:
        regularity = 0
    
    return {
        'regularity': float(regularity),
        'mean_spacing': float(mean_spacing),
        'std_spacing': float(std_spacing),
        'min_spacing': int(spacings.min()) if len(spacings) > 0 else 0,
        'max_spacing': int(spacings.max()) if len(spacings) > 0 else 0,
        'spacing_histogram': Counter(spacings).most_common(5)
    }


def extract_frames(
    bits: List[int],
    sof_pattern: str,
    frame_length: Optional[int] = None
) -> List[List[int]]:
    """
    Extract frames using a detected SOF marker.
    
    Args:
        bits: Full bitstream
        sof_pattern: Start-of-frame pattern (binary string)
        frame_length: Fixed frame length (if known), or None for variable
    
    Returns:
        List of extracted frames
    """
    bits_str = ''.join(map(str, bits))
    sof_len = len(sof_pattern)
    
    # Find all SOF positions
    positions = []
    idx = 0
    while True:
        idx = bits_str.find(sof_pattern, idx)
        if idx == -1:
            break
        positions.append(idx)
        idx += 1
    
    if len(positions) < 2:
        return []
    
    frames = []
    
    if frame_length is not None:
        # Fixed-length frames
        for pos in positions:
            if pos + frame_length <= len(bits):
                frame = bits[pos:pos + frame_length]
                frames.append(frame)
    else:
        # Variable-length frames (use spacing to next SOF)
        for i in range(len(positions) - 1):
            start = positions[i]
            end = positions[i + 1]
            frame = bits[start:end]
            frames.append(frame)
    
    return frames


def correlation_scan(
    bits: List[int],
    template_length: int = 16,
    top_n: int = 5
) -> List[Tuple[int, float]]:
    """
    Use cross-correlation to find repeating patterns.
    
    This is more robust than simple pattern matching for noisy signals.
    
    Returns:
        List of (lag, correlation_coefficient)
    """
    bits_array = np.array(bits, dtype=float)
    
    # Try different template positions
    correlations = []
    
    # Sample templates from different positions
    n_samples = min(10, len(bits) // template_length)
    
    for i in range(n_samples):
        template_start = i * (len(bits) // n_samples)
        template = bits_array[template_start:template_start + template_length]
        
        # Cross-correlate with entire signal
        corr = np.correlate(bits_array, template, mode='valid')
        
        # Find peaks
        peaks, _ = signal.find_peaks(corr, height=template_length * 0.7)
        
        for peak in peaks:
            if peak > template_start + template_length:  # Don't count self-correlation
                correlations.append((peak - template_start, corr[peak] / template_length))
    
    # Sort by correlation strength
    correlations.sort(key=lambda x: x[1], reverse=True)
    
    return correlations[:top_n]


def detect_frame_structure(bits: List[int]) -> Dict:
    """
    Comprehensive frame structure detection.
    
    Returns:
        Dictionary with detected structure parameters
    """
    results = {
        'bitstream_length': len(bits),
        'sync_markers': [],
        'correlation_peaks': [],
        'recommended_frame_length': None,
        'confidence': 0.0
    }
    
    # Method 1: Pattern-based sync marker detection
    for marker_len in [8, 12, 16, 24, 32]:
        candidates = find_sync_markers(bits, marker_length=marker_len, min_occurrences=3)
        
        for pattern, count, positions in candidates[:3]:
            spacing = analyze_marker_spacing(positions)
            
            # Convert spacing_histogram to JSON-safe format
            spacing_safe = {
                'regularity': spacing['regularity'],
                'mean_spacing': spacing['mean_spacing'],
                'std_spacing': spacing['std_spacing'],
                'min_spacing': spacing['min_spacing'],
                'max_spacing': spacing['max_spacing'],
                'spacing_histogram': [(int(k), int(v)) for k, v in spacing['spacing_histogram']]
            }
            
            results['sync_markers'].append({
                'pattern': pattern,
                'length': marker_len,
                'occurrences': count,
                'regularity': spacing['regularity'],
                'mean_spacing': spacing['mean_spacing'],
                'spacing_stats': spacing_safe
            })
    
    # Method 2: Correlation-based detection
    corr_peaks = correlation_scan(bits, template_length=16)
    results['correlation_peaks'] = [
        {'lag': int(lag), 'correlation': float(corr)}
        for lag, corr in corr_peaks
    ]
    
    # Determine most likely frame length
    if results['sync_markers']:
        best_marker = max(results['sync_markers'], key=lambda x: x['regularity'] * x['occurrences'])
        
        if best_marker['regularity'] > 0.5:  # Strong regularity
            results['recommended_frame_length'] = int(best_marker['mean_spacing'])
            results['confidence'] = best_marker['regularity']
            results['best_sof_pattern'] = best_marker['pattern']
    
    return results


if __name__ == "__main__":
    import sys
    import json
    ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT))
    from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
    from core.extractors import extract_all_signals
    
    print("=" * 70)
    print("EDGX FRAME DETECTION")
    print("=" * 70)
    
    # Load data
    sample_dirs = get_sample_dirs()
    test_dir = sample_dirs[-1]
    
    print(f"\nAnalyzing: {test_dir.name}")
    
    df_edgx = load_edgx_data(test_dir, symbol="GME").head(50000)
    signals = extract_all_signals(df_edgx)
    
    output_dir = BASE_DIR / "research" / "edgx_deep_decode" / "results"
    
    # Analyze the most suspicious signal: price_lsb_1c
    print("\n" + "=" * 70)
    print("ANALYZING: price_lsb_1c (highest autocorrelation)")
    print("=" * 70)
    
    bits = signals['price_lsb_1c']
    
    structure = detect_frame_structure(bits)
    
    print(f"\nBitstream length: {structure['bitstream_length']} bits")
    
    print(f"\nTop sync marker candidates:")
    for marker in sorted(structure['sync_markers'], key=lambda x: x['regularity'], reverse=True)[:5]:
        print(f"  Pattern: {marker['pattern']} ({marker['length']} bits)")
        print(f"    Occurrences: {marker['occurrences']}")
        print(f"    Regularity: {marker['regularity']:.4f}")
        print(f"    Mean spacing: {marker['mean_spacing']:.1f} bits")
    
    if structure['recommended_frame_length']:
        print(f"\n✓ FRAME STRUCTURE DETECTED")
        print(f"  Frame length: {structure['recommended_frame_length']} bits")
        print(f"  Confidence: {structure['confidence']:.4f}")
        print(f"  SOF pattern: {structure['best_sof_pattern']}")
        
        # Extract frames
        frames = extract_frames(bits, structure['best_sof_pattern'])
        print(f"\n  Extracted {len(frames)} frames")
        
        if frames:
            print(f"  Frame lengths: min={min(len(f) for f in frames)}, max={max(len(f) for f in frames)}, mean={np.mean([len(f) for f in frames]):.1f}")
    else:
        print(f"\n✗ No clear frame structure detected")
    
    # Save results
    with open(output_dir / f"frame_detection_{test_dir.name}.json", 'w') as f:
        # Convert to JSON-safe format
        safe_results = {
            'bitstream_length': structure['bitstream_length'],
            'sync_markers': structure['sync_markers'],
            'correlation_peaks': structure['correlation_peaks'],
            'recommended_frame_length': structure['recommended_frame_length'],
            'confidence': float(structure['confidence']) if structure['confidence'] else 0
        }
        json.dump(safe_results, f, indent=2)
    
    print(f"\nResults saved to: {output_dir}/frame_detection_{test_dir.name}.json")
