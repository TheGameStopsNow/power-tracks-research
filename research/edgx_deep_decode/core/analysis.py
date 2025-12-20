#!/usr/bin/env python3
"""
Cryptanalysis Tools for EDGX Signal Extraction
================================================

Statistical and cryptanalytic tests on extracted bitstreams to identify
non-random patterns that may indicate covert signaling.
"""

from pathlib import Path
from typing import List, Dict, Tuple
import numpy as np
import pandas as pd
from scipy import stats
from collections import Counter
import matplotlib.pyplot as plt


def calculate_entropy(bits: List[int]) -> float:
    """
    Calculate Shannon entropy of a bitstream.
    
    Perfect random binary stream = 1.0 bit/bit
    Non-random = < 1.0
    
    Args:
        bits: List of 0s and 1s
    
    Returns:
        Entropy in bits
    """
    if len(bits) == 0:
        return 0.0
    
    bits_array = np.array(bits)
    ones_ratio = bits_array.mean()
    
    if ones_ratio == 0 or ones_ratio == 1:
        return 0.0
    
    entropy = -ones_ratio * np.log2(ones_ratio) - (1 - ones_ratio) * np.log2(1 - ones_ratio)
    return entropy


def find_repeating_patterns(bits: List[int], min_length: int = 8, max_length: int = 64) -> Dict:
    """
    Search for repeating subsequences in the bitstream.
    
    Args:
        bits: List of bits
        min_length: Minimum pattern length to search
        max_length: Maximum pattern length to search
    
    Returns:
        Dictionary with pattern statistics
    """
    bits_str = ''.join(map(str, bits))
    
    patterns_found = {}
    
    for length in range(min_length, min(max_length + 1, len(bits) // 2)):
        pattern_counts = Counter()
        
        for i in range(len(bits_str) - length + 1):
            pattern = bits_str[i:i+length]
            pattern_counts[pattern] += 1
        
        # Find patterns that repeat more than expected by chance
        repeating = [p for p, count in pattern_counts.items() if count > 2]
        
        if repeating:
            patterns_found[length] = {
                'n_unique': len(pattern_counts),
                'n_repeating': len(repeating),
                'top_pattern': pattern_counts.most_common(1)[0] if pattern_counts else None
            }
    
    return patterns_found


def chi_square_test(bits: List[int]) -> Tuple[float, float]:
    """
    Chi-square test for uniformity.
    
    H0: Bits are uniformly distributed (random)
    
    Returns:
        (chi2_statistic, p_value)
    """
    bits_array = np.array(bits)
    observed = np.bincount(bits_array, minlength=2)
    expected = np.array([len(bits) / 2, len(bits) / 2])
    
    chi2, pval = stats.chisquare(observed, expected)
    return float(chi2), float(pval)


def runs_test(bits: List[int]) -> Dict:
    """
    Runs test for randomness.
    
    A "run" is a sequence of identical bits.
    Random data should have a predictable number of runs.
    
    Returns:
        Dictionary with test results
    """
    bits_array = np.array(bits)
    
    # Count runs
    runs = 1
    for i in range(1, len(bits_array)):
        if bits_array[i] != bits_array[i-1]:
            runs += 1
    
    # Expected runs for random sequence
    n0 = (bits_array == 0).sum()
    n1 = (bits_array == 1).sum()
    n = len(bits_array)
    
    if n0 == 0 or n1 == 0:
        return {'runs': runs, 'expected_runs': 0, 'z_score': np.nan, 'p_value': np.nan}
    
    expected_runs = 1 + (2 * n0 * n1) / n
    variance_runs = (2 * n0 * n1 * (2 * n0 * n1 - n)) / (n * n * (n - 1))
    
    if variance_runs > 0:
        z_score = (runs - expected_runs) / np.sqrt(variance_runs)
        p_value = 2 * (1 - stats.norm.cdf(abs(z_score)))
    else:
        z_score = np.nan
        p_value = np.nan
    
    return {
        'runs': runs,
        'expected_runs': expected_runs,
        'z_score': z_score,
        'p_value': p_value,
        'is_random': p_value > 0.05 if not np.isnan(p_value) else None
    }


def autocorrelation_test(bits: List[int], max_lag: int = 100) -> np.ndarray:
    """
    Calculate autocorrelation to detect periodicity.
    
    Args:
        bits: Bitstream
        max_lag: Maximum lag to test
    
    Returns:
        Array of autocorrelation values for each lag
    """
    bits_array = np.array(bits, dtype=float)
    bits_centered = bits_array - bits_array.mean()
    
    autocorr = []
    for lag in range(1, min(max_lag, len(bits) // 2)):
        corr = np.corrcoef(bits_centered[:-lag], bits_centered[lag:])[0, 1]
        autocorr.append(corr if not np.isnan(corr) else 0)
    
    return np.array(autocorr)


def comprehensive_analysis(bits: List[int], name: str = "bitstream") -> Dict:
    """
    Run comprehensive cryptanalysis on a bitstream.
    
    Returns:
        Dictionary with all test results
    """
    if len(bits) < 16:
        return {'error': 'Insufficient data', 'n_bits': len(bits)}
    
    bits_array = np.array(bits)
    
    # Basic statistics
    ones_ratio = bits_array.mean()
    entropy = calculate_entropy(bits)
    
    # Chi-square test
    chi2, chi2_pval = chi_square_test(bits)
    
    # Runs test
    runs_result = runs_test(bits)
    
    # Pattern detection
    patterns = find_repeating_patterns(bits)
    
    # Autocorrelation
    autocorr = autocorrelation_test(bits)
    
    # Look for long repeating sequences (CRITICAL for detecting encoding)
    max_repeat = 0
    if patterns:
        for length, stats_dict in patterns.items():
            if stats_dict['top_pattern']:
                max_repeat = max(max_repeat, length)
    
    return {
        'name': name,
        'n_bits': len(bits),
        'ones_ratio': float(ones_ratio),
        'entropy': float(entropy),
        'chi2_statistic': chi2,
        'chi2_pvalue': chi2_pval,
        'random_by_chi2': chi2_pval > 0.05,
        'runs_test': runs_result,
        'max_pattern_length': max_repeat,
        'n_pattern_lengths': len(patterns),
        'max_autocorr': float(np.max(np.abs(autocorr))) if len(autocorr) > 0 else 0,
        'autocorr_lag_at_max': int(np.argmax(np.abs(autocorr))) + 1 if len(autocorr) > 0 else 0
    }


def generate_spectrogram(bits: List[int], output_path: Path):
    """
    Generate visual spectrogram of bitstream.
    
    Maps bits to a 2D image to look for visual patterns.
    """
    # Reshape bits into 2D grid
    width = int(np.sqrt(len(bits)))
    height = len(bits) // width
    
    bits_2d = np.array(bits[:width * height]).reshape(height, width)
    
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.imshow(bits_2d, cmap='binary', interpolation='nearest', aspect='auto')
    ax.set_title(f'Bitstream Spectrogram ({len(bits)} bits)')
    ax.set_xlabel('Bit Position (width)')
    ax.set_ylabel('Sequence Number')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


if __name__ == "__main__":
    import sys
    import json
    sys.path.insert(0, str(Path(__file__).parent))
    from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
    from core.extractors import extract_all_signals
    
    print("=" * 70)
    print("EDGX CRYPTANALYSIS")
    print("=" * 70)
    
    # Load most recent data
    sample_dirs = get_sample_dirs()
    test_dir = sample_dirs[-1]
    
    print(f"\\nAnalyzing: {test_dir.name}")
    
    # Load EDGX data
    df_edgx = load_edgx_data(test_dir, symbol="GME").head(50000)
    print(f"Loaded {len(df_edgx)} EDGX trades")
    
    # Extract signals
    print("\\nExtracting signals...")
    signals = extract_all_signals(df_edgx)
    
    # Analyze each signal
    print("\\nCryptanalysis Results:")
    print("=" * 70)
    
    results = []
    for name, bits in signals.items():
        if len(bits) < 100:
            continue
        
        analysis = comprehensive_analysis(bits, name)
        results.append(analysis)
        
        print(f"\\n{name}:")
        print(f"  Bits: {analysis['n_bits']}")
        print(f"  Ones Ratio: {analysis['ones_ratio']:.4f} (expect 0.5 for random)")
        print(f"  Entropy: {analysis['entropy']:.4f} (max 1.0)")
        print(f"  Random (chi²): {analysis['random_by_chi2']}")
        print(f"  Random (runs): {analysis['runs_test'].get('is_random', 'N/A')}")
        print(f"  Max Pattern Length: {analysis['max_pattern_length']}")
        print(f"  Max Autocorr: {analysis['max_autocorr']:.4f} @ lag {analysis['autocorr_lag_at_max']}")

        
        # Flag suspicious signals
        if not analysis['random_by_chi2'] or analysis['max_pattern_length'] > 16:
            print(f"  ⚠️  NON-RANDOM SIGNAL DETECTED!")
    
    # Save results
    output_dir = BASE_DIR / "research" / "edgx_deep_decode" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_dir / f"cryptanalysis_{test_dir.name}.json", 'w') as f:
        json.dump(results, f, indent=2)
    
    # Generate spectrograms for suspicious signals
    print("\\n" + "=" * 70)
    print("Generating spectrograms...")
    
    for name, bits in signals.items():
        if len(bits) >= 1000:
            output_path = output_dir / f"spectrogram_{name}_{test_dir.name}.png"
            generate_spectrogram(bits, output_path)
            print(f"  {name}: {output_path.name}")
    
    print(f"\\nResults saved to: {output_dir}")
