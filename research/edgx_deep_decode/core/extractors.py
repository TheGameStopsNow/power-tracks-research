#!/usr/bin/env python3
"""
Signal Extractors for EDGX Data
=================================

Brute-force extraction of candidate bitstreams from EDGX tick data using
multiple encoding hypotheses: LSB, timing channels, sequence patterns, etc.
"""

from pathlib import Path
from typing import List, Dict, Tuple
import numpy as np
import pandas as pd
from scipy import stats


def extract_price_lsb(df: pd.DataFrame, precision: int = 2) -> List[int]:
    """
    Extract Least Significant Bit(s) from price data.
    
    Args:
        df: DataFrame with 'price' column
        precision: Number of decimal places to consider (1, 2, or 3)
                  1 = 1c precision (dimes)
                  2 = 0.1c precision (pennies)  
                  3 = 0.01c precision (sub-penny)
    
    Returns:
        List of bits (0 or 1)
    """
    if precision == 1:
        # Extract penny digit (10s of cents)
        int_prices = (df['price'] * 10).astype(int)
        bits = int_prices % 2
    elif precision == 2:
        # Extract cent digit
        int_prices = (df['price'] * 100).astype(int)
        bits = int_prices % 2
    elif precision == 3:
        # Extract sub-penny digit
        int_prices = (df['price'] * 1000).astype(int)
        bits = int_prices % 2
    else:
        raise ValueError("Precision must be 1, 2, or 3")
    
    return bits.tolist()


def extract_volume_lsb(df: pd.DataFrame) -> List[int]:
    """
    Extract LSB from volume data.
    
    Returns:
        List of bits (0 or 1)
    """
    volumes = df['volume'].astype(int)
    bits = volumes % 2
    return bits.tolist()


def extract_timestamp_lsb(df: pd.DataFrame, unit: str = 'microsecond') -> List[int]:
    """
    Extract LSB from timestamp jitter.
    
    Args:
        df: DataFrame with 'timestamp' column
        unit: Time unit to extract LSB from ('microsecond', 'nanosecond', 'millisecond')
    
    Returns:
        List of bits (0 or 1)
    """
    if unit == 'nanosecond':
        # Get nanosecond component
        nanos = df['timestamp'].dt.nanosecond
        bits = nanos % 2
    elif unit == 'microsecond':
        # Get microsecond component
        micros = df['timestamp'].dt.microsecond
        bits = micros % 2
    elif unit == 'millisecond':
        # Get millisecond component  
        millis = (df['timestamp'].dt.microsecond / 1000).astype(int)
        bits = millis % 2
    else:
        raise ValueError("Unit must be 'nanosecond', 'microsecond', or 'millisecond'")
    
    return bits.tolist()


def extract_size_sequence(df: pd.DataFrame, window: int = 8) -> np.ndarray:
    """
    Extract trade size sequences as potential encoding.
    
    Looks for patterns like: [100, 200, 100, 300] -> could encode bits
    
    Args:
        df: DataFrame with 'volume' column
        window: Sequence length to extract
    
    Returns:
        Array of size sequences (n_sequences, window)
    """
    volumes = df['volume'].values
    
    sequences = []
    for i in range(len(volumes) - window + 1):
        seq = volumes[i:i+window]
        sequences.append(seq)
    
    return np.array(sequences)


def extract_odd_lot_pattern(df: pd.DataFrame) -> Tuple[List[int], Dict]:
    """
    Check for odd-lot patterns (Fibonacci, Prime, etc.).
    
    Returns:
        (bits, metadata)
    """
    volumes = df['volume'].astype(int).values
    
    # Fibonacci sequence
    fib = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144]
    fib_mask = np.isin(volumes, fib)
    
    # Prime numbers up to 1000
    primes = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 
              59, 61, 67, 71, 73, 79, 83, 89, 97, 101, 103, 107, 109, 113]
    prime_mask = np.isin(volumes, primes)
    
    # Look for odd lots (< 100 shares)
    odd_lot_mask = volumes < 100
    
    metadata = {
        'fib_count': fib_mask.sum(),
        'fib_pct': (fib_mask.sum() / len(volumes)) * 100,
        'prime_count': prime_mask.sum(),
        'prime_pct': (prime_mask.sum() / len(volumes)) * 100,
        'odd_lot_count': odd_lot_mask.sum(),
        'odd_lot_pct': (odd_lot_mask.sum() / len(volumes)) * 100
    }
    
    # Encode as bits: 1 if special, 0 if normal
    bits = (fib_mask | prime_mask).astype(int).tolist()
    
    return bits, metadata


def extract_inter_arrival_bits(df: pd.DataFrame, threshold_us: int = 1000) -> List[int]:
    """
    Extract bits from inter-arrival time modulation.
    
    Hypothesis: The *gap* between trades encodes information.
    Fast gap (< threshold) = 0, Slow gap (>= threshold) = 1
    
    Args:
        df: DataFrame with 'timestamp' column
        threshold_us: Threshold in microseconds
    
    Returns:
        List of bits
    """
    df = df.sort_values('timestamp').copy()
    
    # Calculate inter-arrival times in microseconds
    time_deltas = df['timestamp'].diff().dt.total_seconds() * 1_000_000
    
    # Convert to bits
    bits = (time_deltas >= threshold_us).astype(int).tolist()[1:]  # Skip first NaN
    
    return bits


def extract_all_signals(df: pd.DataFrame) -> Dict[str, List[int]]:
    """
    Extract ALL candidate bitstreams from a DataFrame.
    
    This is the brute-force approach - extract everything and let
    cryptanalysis sort it out.
    
    Returns:
        Dictionary of {signal_name: bitstream}
    """
    signals = {}
    
    # Price LSBs at different precisions
    signals['price_lsb_1c'] = extract_price_lsb(df, precision=1)
    signals['price_lsb_01c'] = extract_price_lsb(df, precision=2)
    signals['price_lsb_001c'] = extract_price_lsb(df, precision=3)
    
    # Volume LSB
    signals['volume_lsb'] = extract_volume_lsb(df)
    
    # Timestamp LSBs  
    signals['timestamp_us_lsb'] = extract_timestamp_lsb(df, unit='microsecond')
    signals['timestamp_ns_lsb'] = extract_timestamp_lsb(df, unit='nanosecond')
    
    # Odd lot patterns
    odd_lot_bits, odd_lot_meta = extract_odd_lot_pattern(df)
    signals['odd_lot_pattern'] = odd_lot_bits
    
    # Inter-arrival timing
    signals['timing_1ms'] = extract_inter_arrival_bits(df, threshold_us=1000)
    signals['timing_10ms'] = extract_inter_arrival_bits(df, threshold_us=10000)
    
    return signals


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
    
    print("=" * 70)
    print("EDGX SIGNAL EXTRACTOR")
    print("=" * 70)
    
    # Test on most recent sample
    sample_dirs = get_sample_dirs()
    if not sample_dirs:
        print("No sample directories found")
        sys.exit(1)
    
    test_dir = sample_dirs[-1]
    print(f"\\nAnalyzing: {test_dir.name}")
    
    # Load EDGX data (take first 10000 trades for testing)
    df_edgx = load_edgx_data(test_dir, symbol="GME").head(10000)
    print(f"Loaded {len(df_edgx)} EDGX trades")
    
    # Extract all signals
    print("\\nExtracting candidate bitstreams...")
    signals = extract_all_signals(df_edgx)
    
    print(f"\\nExtracted {len(signals)} candidate signals:")
    for name, bits in signals.items():
        if len(bits) > 0:
            ones_ratio = sum(bits) / len(bits)
            print(f"  {name:20s}: {len(bits):6d} bits, ones_ratio={ones_ratio:.3f}")
    
    # Save extracted bits
    output_dir = BASE_DIR / "research" / "edgx_deep_decode" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save as CSV for inspection
    max_len = max(len(bits) for bits in signals.values())
    
    # Pad shorter sequences with NaN
    padded_signals = {}
    for name, bits in signals.items():
        padded = bits + [np.nan] * (max_len - len(bits))
        padded_signals[name] = padded
    
    df_signals = pd.DataFrame(padded_signals)
    df_signals.to_csv(output_dir / f"extracted_signals_{test_dir.name}.csv", index=False)
    
    print(f"\\nSaved to: {output_dir / f'extracted_signals_{test_dir.name}.csv'}")
