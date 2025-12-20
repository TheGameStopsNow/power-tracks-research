#!/usr/bin/env python3
"""
Burst Detector for EDGX Data
==============================

Identifies "burst storms" - high-frequency clusters of trades that may contain
covert signaling. Based on statistical anomalies in volume and inter-arrival times.
"""

from pathlib import Path
from typing import List, Tuple
import numpy as np
import pandas as pd
from scipy import stats


def detect_burst_storms(
    df: pd.DataFrame,
    volume_threshold: float = 2.5,
    time_window_ms: int = 100,
    min_trades: int = 10
) -> pd.DataFrame:
    """
    Detect burst storms in EDGX trade data.
    
    A "burst storm" is defined as:
    - High-frequency trading cluster (many trades in short time)
    - Volume spike relative to background
    - Price volatility anomaly
    
    Args:
        df: DataFrame with columns [timestamp, price, volume, venue]
        volume_threshold: Volume spike multiplier vs. rolling average
        time_window_ms: Time window in milliseconds for burst detection
        min_trades: Minimum number of trades to constitute a burst
    
    Returns:
        DataFrame with burst windows: [burst_id, start_time, end_time, n_trades, metrics]
    """
    
    # Ensure data is sorted
    df = df.sort_values('timestamp').copy()
    
    # Calculate inter-arrival times (in milliseconds)
    df['time_delta_ms'] = df['timestamp'].diff().dt.total_seconds() * 1000
    
    # Rolling volume statistics
    df['volume_rolling_mean'] = df['volume'].rolling(window=100, min_periods=10).mean()
    df['volume_spike'] = df['volume'] / df['volume_rolling_mean']
    
    # Price change rate
    df['price_change'] = df['price'].diff().abs() / df['price']
    
    # Identify candidate burst points (high volume, fast trades)
    df['is_burst_point'] = (
        (df['time_delta_ms'] < time_window_ms) &
        (df['volume_spike'] > volume_threshold)
    )
    
    # Group consecutive burst points into storms
    df['burst_group'] = (df['is_burst_point'] != df['is_burst_point'].shift()).cumsum()
    
    # Filter only actual bursts
    burst_groups = df[df['is_burst_point']].groupby('burst_group')
    
    bursts = []
    for burst_id, group in burst_groups:
        if len(group) >= min_trades:
            bursts.append({
                'burst_id': burst_id,
                'start_time': group['timestamp'].min(),
                'end_time': group['timestamp'].max(),
                'duration_ms': (group['timestamp'].max() - group['timestamp'].min()).total_seconds() * 1000,
                'n_trades': len(group),
                'total_volume': group['volume'].sum(),
                'price_min': group['price'].min(),
                'price_max': group['price'].max(),
                'price_range_pct': ((group['price'].max() - group['price'].min()) / group['price'].mean()) * 100,
                'avg_volume_spike': group['volume_spike'].mean(),
                'max_volume_spike': group['volume_spike'].max()
            })
    
    return pd.DataFrame(bursts)


def isolate_burst_data(
    df: pd.DataFrame,
    burst: pd.Series,
    pre_buffer_ms: int = 1000,
    post_buffer_ms: int = 1000
) -> pd.DataFrame:
    """
    Isolate tick data for a specific burst with buffer.
    
    Args:
        df: Full EDGX dataset
        burst: Single row from detect_burst_storms output
        pre_buffer_ms: Milliseconds before burst to include
        post_buffer_ms: Milliseconds after burst to include
    
    Returns:
        Filtered DataFrame containing only the burst window
    """
    start_buffered = burst['start_time'] - pd.Timedelta(milliseconds=pre_buffer_ms)
    end_buffered = burst['end_time'] + pd.Timedelta(milliseconds=post_buffer_ms)
    
    mask = (df['timestamp'] >= start_buffered) & (df['timestamp'] <= end_buffered)
    return df[mask].copy()


def find_concurrent_bursts(
    bursts_df: pd.DataFrame,
    time_threshold_ms: int = 5000
) -> List[List[int]]:
    """
    Find bursts that occur within a short time window (possible coordinated signaling).
    
    Args:
        bursts_df: Output from detect_burst_storms
        time_threshold_ms: Maximum time gap to consider bursts "concurrent"
    
    Returns:
        List of burst_id clusters
    """
    if bursts_df.empty:
        return []
    
    bursts_sorted = bursts_df.sort_values('start_time')
    
    clusters = []
    current_cluster = [bursts_sorted.iloc[0]['burst_id']]
    last_time = bursts_sorted.iloc[0]['start_time']
    
    for idx in range(1, len(bursts_sorted)):
        burst = bursts_sorted.iloc[idx]
        time_gap = (burst['start_time'] - last_time).total_seconds() * 1000
        
        if time_gap <= time_threshold_ms:
            current_cluster.append(burst['burst_id'])
        else:
            if len(current_cluster) > 1:
                clusters.append(current_cluster)
            current_cluster = [burst['burst_id']]
        
        last_time = burst['start_time']
    
    if len(current_cluster) > 1:
        clusters.append(current_cluster)
    
    return clusters


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
    
    print("=" * 70)
    print("EDGX BURST STORM DETECTOR")
    print("=" * 70)
    
    # Test on most recent sample
    sample_dirs = get_sample_dirs()
    if not sample_dirs:
        print("No sample directories found")
        sys.exit(1)
    
    test_dir = sample_dirs[-1]
    print(f"\\nAnalyzing: {test_dir.name}")
    
    # Load EDGX data
    df_edgx = load_edgx_data(test_dir, symbol="GME")
    print(f"Loaded {len(df_edgx)} EDGX trades")
    
    # Detect bursts
    bursts = detect_burst_storms(df_edgx)
    
    print(f"\\nDetected {len(bursts)} burst storms")
    
    if len(bursts) > 0:
        print("\\nTop 5 bursts by trade count:")
        print(bursts.nlargest(5, 'n_trades')[['burst_id', 'start_time', 'n_trades', 'duration_ms', 'price_range_pct']])
        
        # Check for concurrent bursts
        concurrent = find_concurrent_bursts(bursts)
        print(f"\\nFound {len(concurrent)} concurrent burst clusters")
        
        # Save results
        output_dir = BASE_DIR / "research" / "edgx_deep_decode" / "results"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        bursts.to_csv(output_dir / f"bursts_{test_dir.name}.csv", index=False)
        print(f"\\nResults saved to {output_dir}")
