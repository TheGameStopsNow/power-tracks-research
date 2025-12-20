#!/usr/bin/env python3
"""
Cross-Symbol Signal Correlation
===============================

Analyzes whether extracted bitstreams are correlated across different symbols
(e.g., GME, AMC, BB) to detect "broadcast" signaling.

NOTE: Requires raw tick data for multiple symbols. Currently optimized for use
when such data becomes available.
"""

from pathlib import Path
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from scipy import stats, signal
import warnings

# Import local modules
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
from core.extractors import extract_all_signals


def align_signals(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    signal_col: str = 'price',
    tolerance_ms: int = 10
) -> pd.DataFrame:
    """
    Align two tick streams by timestamp.
    Since raw ticks don't occur at exact same times, we resample to a
    high-frequency grid (e.g., 100ms) or match closest neighbors.
    """
    # Simply resample to 100ms grid and take last value
    df1_res = df1.set_index('timestamp').resample(f'{tolerance_ms}ms').last().ffill()
    df2_res = df2.set_index('timestamp').resample(f'{tolerance_ms}ms').last().ffill()
    
    # Align indices
    aligned = pd.merge(
        df1_res, df2_res, 
        left_index=True, right_index=True, 
        suffixes=('_1', '_2'),
        how='inner'
    )
    
    return aligned


def cross_correlate_bitstreams(
    bits1: List[int],
    bits2: List[int],
    max_lag: int = 100
) -> Dict:
    """
    Calculate cross-correlation between two binary streams.
    """
    # Ensure equal length
    min_len = min(len(bits1), len(bits2))
    b1 = np.array(bits1[:min_len])
    b2 = np.array(bits2[:min_len])
    
    # Pearson correlation at lag 0
    corr_0, p_val = stats.pearsonr(b1, b2)
    
    # Cross-correlation array
    xcorr = signal.correlate(b1 - 0.5, b2 - 0.5, mode='valid')
    xcorr /= (np.std(b1) * np.std(b2) * len(b1))
    
    # Find max lag
    lags = signal.correlation_lags(len(b1), len(b2), mode='valid')
    best_idx = np.argmax(np.abs(xcorr))
    max_corr = xcorr[best_idx]
    best_lag = lags[best_idx]
    
    return {
        'correlation_at_zero': corr_0,
        'p_value': p_val,
        'max_cross_corr': max_corr,
        'best_lag': best_lag
    }


def analyze_multisymbol_coherence(
    sample_dir: Path,
    symbols: List[str] = ['GME', 'AMC', 'KOSS'],
    extractor_names: List[str] = ['price_lsb_1c', 'price_lsb_01c']
):
    """
    Main runner for multi-symbol analysis.
    """
    print(f"Analyzing multi-symbol coherence in: {sample_dir.name}")
    
    data_store = {}
    
    # Load data for available symbols
    for sym in symbols:
        try:
            print(f"  Loading {sym}...")
            df = load_edgx_data(sample_dir, symbol=sym)
            if not df.empty:
                data_store[sym] = df
                print(f"    ✓ Loaded {len(df)} trades")
            else:
                print(f"    ✗ No GME-filtered EDGX trades found")
        except FileNotFoundError:
            print(f"    ✗ File not found for {sym}")
        except Exception as e:
            print(f"    Warning: Could not load {sym}: {e}")

    if len(data_store) < 2:
        print("\n⚠️  Insufficient data for cross-correlation (need at least 2 symbols)")
        return
    
    # Align and correlate
    keys = list(data_store.keys())
    primary = keys[0]
    others = keys[1:]
    
    for sec in others:
        print(f"\nCorrelating {primary} vs {sec}...")
        
        # 1. Extract signals locally for each
        # (This is imprecise because extraction usually relies on continuous implementation
        #  but we'll do it on the raw dfs)
        sig1 = extract_all_signals(data_store[primary])
        sig2 = extract_all_signals(data_store[sec])
        
        for name in extractor_names:
            if name in sig1 and name in sig2:
                res = cross_correlate_bitstreams(sig1[name], sig2[name])
                print(f"  Signal: {name}")
                print(f"    r = {res['correlation_at_zero']:.4f} (lag 0)")
                print(f"    Max r = {res['max_cross_corr']:.4f} @ lag {res['best_lag']}")
                
                if abs(res['max_cross_corr']) > 0.3:
                    print("    🚨 HIGH CORRELATION DETECTED")


if __name__ == "__main__":
    test_dir = get_sample_dirs()[-1]
    analyze_multisymbol_coherence(test_dir)
