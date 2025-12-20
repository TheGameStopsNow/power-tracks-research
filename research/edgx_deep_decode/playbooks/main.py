#!/usr/bin/env python3
"""
EDGX Deep Decode Main Pipeline
===============================

Orchestrates the full brute-force decoding pipeline from data loading
through cryptanalysis.
"""

from pathlib import Path
import json
import sys
import warnings
warnings.filterwarnings('ignore')

# Add this directory to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
from core.burst_detector import detect_burst_storms, isolate_burst_data
from core.extractors import extract_all_signals
from core.analysis import comprehensive_analysis, generate_spectrogram


def sanitize_for_json(obj):
    """Convert numpy types to Python types for JSON serialization."""
    import numpy as np
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    elif isinstance(obj, (np.integer, np.floating)):
        return float(obj) if np.isfinite(obj) else None
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, float) and not np.isfinite(obj):
        return None
    return obj


def main():
    print("=" * 80)
    print("OPERATION GLASSHOUSE - EDGX DEEP DECODE")
    print("=" * 80)
    
    # Setup
    sample_dirs = get_sample_dirs()
    if not sample_dirs:
        print("ERROR: No sample directories found")
        return 1
    
    # Use the most recent sample
    test_dir = sample_dirs[-1]
    date_str = test_dir.name.replace('sample_', '')
    
    print(f"\n📅 Date: {date_str}")
    print(f"🎯 Target: EDGX Exchange (Venue ID 4)")
    print(f"🔎 Symbol: GME")
    
    # Output directory
    output_dir = BASE_DIR / "research" / "edgx_deep_decode" / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # PHASE 1: Load Data
    print("\n" + "=" * 80)
    print("PHASE 1: DATA LOADING")
    print("=" * 80)
    
    df_edgx = load_edgx_data(test_dir, symbol="GME")
    print(f"✓ Loaded {len(df_edgx):,} EDGX trades")
    print(f"  Time range: {df_edgx['timestamp'].min()} to {df_edgx['timestamp'].max()}")
    print(f"  Price range: ${df_edgx['price'].min():.2f} - ${df_edgx['price'].max():.2f}")
    
    # PHASE 2: Detect Bursts
    print("\n" + "=" * 80)
    print("PHASE 2: BURST STORM DETECTION")
    print("=" * 80)
    
    bursts = detect_burst_storms(df_edgx)
    print(f"✓ Detected {len(bursts)} burst storms")
    
    if len(bursts) > 0:
        print(f"\n  Top burst: {bursts.iloc[0]['n_trades']} trades in {bursts.iloc[0]['duration_ms']:.0f}ms")
        bursts.to_csv(output_dir / f"bursts_{date_str}.csv", index=False)
    
    # PHASE 3: Extract Signals (use subset for speed)
    print("\n" + "=" * 80)
    print("PHASE 3: SIGNAL EXTRACTION")
    print("=" * 80)
    
    # Use first 50k trades for analysis
    df_subset = df_edgx.head(50000)
    print(f"Analyzing subset: {len(df_subset):,} trades")
    
    signals = extract_all_signals(df_subset)
    print(f"✓ Extracted {len(signals)} candidate bitstreams")
    
    # PHASE 4: Cryptanalysis
    print("\n" + "=" * 80)
    print("PHASE 4: CRYPTANALYSIS")
    print("=" * 80)
    
    results = []
    non_random_count = 0
    
    for name, bits in signals.items():
        if len(bits) < 100:
            continue
        
        analysis = comprehensive_analysis(bits, name)
        results.append(analysis)
        
        # Check for non-randomness
        is_non_random = (
            not analysis['random_by_chi2'] or 
            analysis['max_pattern_length'] > 16 or
            abs(analysis['ones_ratio'] - 0.5) > 0.1
        )
        
        if is_non_random:
            non_random_count += 1
    
    print(f"✓ Analyzed {len(results)} signals")
    print(f"⚠️  {non_random_count}/{len(results)} signals show NON-RANDOM patterns")
    
    # Summary table
    print("\n" + "-" * 80)
    print(f"{'Signal':\u003c25} | {'Bits':\u003c7} | {'Entropy':\u003c7} | {'Chi² Rand':\u003c10} | {'Max AutoCorr':\u003c12}")
    print("-" * 80)
    
    for r in sorted(results, key=lambda x: x['max_autocorr'], reverse=True):
        print(f"{r['name']:\u003c25} | {r['n_bits']:\u003c7} | {r['entropy']:.4f} | "
              f"{'✓' if r['random_by_chi2'] else '✗':\u003c10} | {r['max_autocorr']:.4f}")
    
    # Save results
    sanitized_results = sanitize_for_json(results)
    with open(output_dir / f"cryptanalysis_{date_str}.json", 'w') as f:
        json.dump(sanitized_results, f, indent=2)
    
    # Generate spectrograms
    print("\n" + "=" * 80)
    print("GENERATING VISUAL ARTIFACTS")
    print("=" * 80)
    
    for name, bits in signals.items():
        if len(bits) >= 1000:
            output_path = output_dir / f"spectrogram_{name}_{date_str}.png"
            generate_spectrogram(bits, output_path)
            print(f"  ✓ {output_path.name}")
    
    # FINAL REPORT
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"\n📊 Results saved to: {output_dir}")
    print(f"\n🔍 KEY FINDINGS:")
    print(f"   • {non_random_count}/{len(results)} signals are NON-RANDOM")
    print(f"   • Strongest autocorrelation: {max(r['max_autocorr'] for r in results):.4f}")
    print(f"   • Longest repeating pattern: {max(r['max_pattern_length'] for r in results)} bits")
    
    # Highlight most suspicious signals
    suspicious = sorted(results, key=lambda x: x['max_autocorr'], reverse=True)[:3]
    print(f"\n🚨 Most suspicious signals:")
    for idx, sig in enumerate(suspicious, 1):
        print(f"   {idx}. {sig['name']:20s} (autocorr={sig['max_autocorr']:.4f})")
    
    print("\n" + "=" * 80)
    print("OPERATION GLASSHOUSE - COMPLETE")
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
