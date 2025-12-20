#!/usr/bin/env python3
"""
Price Action Correlation for EDGX Signals
==========================================

Correlates extracted bitstreams with future price movements to identify
if signals contain predictive information.
"""

from pathlib import Path
from typing import List, Dict, Tuple
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt


def calculate_future_returns(
    df: pd.DataFrame,
    forward_windows: List[int] = [60, 300, 900, 3600, 86400]
) -> pd.DataFrame:
    """
    Calculate forward-looking returns using efficient merge_asof.
    """
    df = df.copy()
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    # Ensure timestamp is datetime
    if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
    for window_sec in forward_windows:
        target_time = df['timestamp'] + pd.Timedelta(seconds=window_sec)
        
        # Create a lookupdf with future targets
        lookup_df = pd.DataFrame({'target_time': target_time})
        
        # Use asof merge to find the closest price AFTER the target time
        # direction='forward' means we look for the first timestamp >= target_time
        merged = pd.merge_asof(
            lookup_df, 
            df[['timestamp', 'price']], 
            left_on='target_time', 
            right_on='timestamp', 
            direction='forward',
            suffixes=('', '_future')
        )
        
        # Calculate return
        col_name = f'fwd_return_{window_sec}s'
        df[col_name] = (merged['price'] - df['price']) / df['price']
    
    return df



def correlate_signal_with_returns(
    bits: List[int],
    df: pd.DataFrame,
    forward_windows: List[int] = [60, 300, 900]
) -> Dict:
    """
    Test if extracted bitstream correlates with future price movements.
    
    Args:
        bits: Extracted bitstream aligned with df
        df: DataFrame with price and timestamp data (must have forward returns)
        forward_windows: Windows to test (must match df columns)
    
    Returns:
        Dictionary with correlation results
    """
    # Ensure bits and df are same length
    min_len = min(len(bits), len(df))
    bits = bits[:min_len]
    df = df.head(min_len)
    
    bits_array = np.array(bits, dtype=float)
    
    results = {}
    
    for window_sec in forward_windows:
        col_name = f'fwd_return_{window_sec}s'
        
        if col_name not in df.columns:
            continue
        
        returns = df[col_name].values
        
        # Remove NaN values
        mask = ~np.isnan(returns)
        bits_clean = bits_array[mask]
        returns_clean = returns[mask]
        
        if len(returns_clean) < 10:
            continue
        
        # Pearson correlation
        corr, pval = stats.pearsonr(bits_clean, returns_clean)
        
        # Point-biserial (since bits are binary)
        # Group returns by bit value
        returns_0 = returns_clean[bits_clean == 0]
        returns_1 = returns_clean[bits_clean == 1]
        
        # Statistical test
        if len(returns_0) > 0 and len(returns_1) > 0:
            tstat, ttest_pval = stats.ttest_ind(returns_0, returns_1)
            
            mean_return_0 = returns_0.mean()
            mean_return_1 = returns_1.mean()
            
            results[f'{window_sec}s'] = {
                'correlation': float(corr),
                'p_value': float(pval),
                'significant': pval < 0.05,
                'mean_return_bit0': float(mean_return_0),
                'mean_return_bit1': float(mean_return_1),
                'return_differential': float(mean_return_1 - mean_return_0),
                't_statistic': float(tstat),
                't_test_pvalue': float(ttest_pval),
                'n_bit0': len(returns_0),
                'n_bit1': len(returns_1)
            }
    
    return results


def analyze_signal_predictiveness(
    signal_name: str,
    bits: List[int],
    df: pd.DataFrame
) -> Dict:
    """
    Comprehensive analysis of whether a signal predicts future prices.
    
    Returns:
        Full analysis including correlations, t-tests, and visualizations
    """
    # Calculate forward returns
    print(f"  Calculating forward returns...")
    df_with_returns = calculate_future_returns(df, forward_windows=[60, 300, 900, 3600])
    
    # Correlate signal with returns
    print(f"  Testing correlations...")
    correlations = correlate_signal_with_returns(
        bits,
        df_with_returns,
        forward_windows=[60, 300, 900, 3600]
    )
    
    # Summary
    analysis = {
        'signal_name': signal_name,
        'n_bits': len(bits),
        'correlations': correlations,
        'max_abs_correlation': 0.0,
        'best_window': None,
        'predictive': False
    }
    
    if correlations:
        # Find strongest correlation
        max_corr_window = max(correlations.items(), key=lambda x: abs(x[1]['correlation']))
        analysis['best_window'] = max_corr_window[0]
        analysis['max_abs_correlation'] = abs(max_corr_window[1]['correlation'])
        
        # Determine if predictive (any significant correlation)
        sig_correlations = [k for k, v in correlations.items() if v['significant']]
        analysis['predictive'] = len(sig_correlations) > 0
        analysis['significant_windows'] = sig_correlations
    
    return analysis


def plot_signal_return_relationship(
    signal_name: str,
    bits: List[int],
    df: pd.DataFrame,
    output_path: Path
):
    """
    Visualize relationship between signal and forward returns.
    """
    df_with_returns = calculate_future_returns(df, forward_windows=[60, 300, 900])
    
    min_len = min(len(bits), len(df_with_returns))
    bits = bits[:min_len]
    df_plot = df_with_returns.head(min_len).copy()
    df_plot['signal'] = bits
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f'Signal-Return Relationship: {signal_name}', fontsize=14, fontweight='bold')
    
    windows = [('fwd_return_60s', '1 min'), ('fwd_return_300s', '5 min'), ('fwd_return_900s', '15 min')]
    
    for idx, (col, label) in enumerate(windows):
        ax = axes[idx // 2, idx % 2]
        
        df_clean = df_plot[[col, 'signal']].dropna()
        
        if len(df_clean) > 0:
            returns_0 = df_clean[df_clean['signal'] == 0][col] * 100
            returns_1 = df_clean[df_clean['signal'] == 1][col] * 100
            
            ax.hist([returns_0, returns_1], bins=50, alpha=0.7, label=['Bit=0', 'Bit=1'])
            ax.axvline(returns_0.mean(), color='blue', linestyle='--', linewidth=2, label=f'Mean (0): {returns_0.mean():.3f}%')
            ax.axvline(returns_1.mean(), color='orange', linestyle='--', linewidth=2, label=f'Mean (1): {returns_1.mean():.3f}%')
            ax.set_xlabel(f'Forward Return ({label})')
            ax.set_ylabel('Count')
            ax.set_title(f'{label} Forward Returns')
            ax.legend()
            ax.grid(True, alpha=0.3)
    
    # Fourth plot: signal over time
    ax = axes[1, 1]
    sample_size = min(1000, len(df_plot))
    df_sample = df_plot.head(sample_size)
    
    ax.plot(df_sample.index, df_sample['signal'], alpha=0.7, linewidth=0.5)
    ax.set_xlabel('Trade Index')
    ax.set_ylabel('Signal Value')
    ax.set_title('Signal Bitstream (first 1000 trades)')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()


if __name__ == "__main__":
    import sys
    import json
    ROOT = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(ROOT))
    from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
    from core.extractors import extract_all_signals
    
    print("=" * 70)
    print("EDGX PRICE ACTION CORRELATION")
    print("=" * 70)
    
    # Load data
    sample_dirs = get_sample_dirs()
    test_dir = sample_dirs[-1]
    date_str = test_dir.name.replace('sample_', '')
    
    print(f"\nAnalyzing: {date_str}")
    
    # Load MORE data for better statistics (need future prices)
    df_edgx = load_edgx_data(test_dir, symbol="GME").head(100000)
    print(f"Loaded {len(df_edgx)} EDGX trades")
    
    # Extract signals
    signals = extract_all_signals(df_edgx)
    
    output_dir = BASE_DIR / "research" / "edgx_deep_decode" / "results"
    
    # Analyze top 3 most suspicious signals
    top_signals = ['price_lsb_1c', 'timing_1ms', 'price_lsb_01c']
    
    all_results = {}
    
    for signal_name in top_signals:
        if signal_name not in signals:
            continue
        
        print(f"\n{'=' * 70}")
        print(f"ANALYZING: {signal_name}")
        print(f"{'=' * 70}")
        
        bits = signals[signal_name]
        
        analysis = analyze_signal_predictiveness(signal_name, bits, df_edgx)
        all_results[signal_name] = analysis
        
        print(f"\nResults:")
        print(f"  Predictive: {analysis['predictive']}")
        print(f"  Max |correlation|: {analysis['max_abs_correlation']:.4f}")
        
        if analysis['correlations']:
            print(f"\n  Correlation breakdown:")
            for window, stats in analysis['correlations'].items():
                sig_marker = "**" if stats['significant'] else "  "
                print(f"    {window:8s}: r={stats['correlation']:+.4f}, p={stats['p_value']:.4f} {sig_marker}")
                print(f"              Return diff: {stats['return_differential']*100:+.4f}%")
        
        # Generate plot
        plot_path = output_dir / f"signal_returns_{signal_name}_{date_str}.png"
        plot_signal_return_relationship(signal_name, bits, df_edgx, plot_path)
        print(f"\n  ✓ Plot saved: {plot_path.name}")
    
    # Save results
    with open(output_dir / f"price_correlation_{date_str}.json", 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    
    predictive_signals = [k for k, v in all_results.items() if v['predictive']]
    
    if predictive_signals:
        print(f"\n🚨 {len(predictive_signals)}/{len(all_results)} signals show PREDICTIVE power:")
        for sig in predictive_signals:
            print(f"   • {sig}: max |r|={all_results[sig]['max_abs_correlation']:.4f}")
    else:
        print(f"\n✓ No signals show statistically significant predictive power")
    
    print(f"\nResults saved to: {output_dir}")
