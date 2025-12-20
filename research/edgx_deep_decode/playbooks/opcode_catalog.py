#!/usr/bin/env python3
"""
Opcode Catalog
==============

Scans all available historical sample directories to build a master catalog
of the sparse protocol's vocabulary.

1. Iterates through data/samples/sample_*
2. Extracts price_lsb_1c
3. Decodes to bytes (skip=8)
4. Aggregates global frequency counts
"""

from pathlib import Path
from typing import Dict, List, Counter as CounterType
from collections import Counter
import json
import pandas as pd
import matplotlib.pyplot as plt

# Import local modules
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
from core.extractors import extract_all_signals
from adversarial_decoding import bits_to_bytes, attempt_ascii_decode


def scan_all_dates(
    symbol: str = 'GME',
    signal_name: str = 'price_lsb_1c'
) -> Dict:
    sample_dirs = get_sample_dirs()
    print(f"Scanning {len(sample_dirs)} directories for {symbol}/{signal_name}...")
    
    global_counter = Counter()
    date_counters = {}
    total_bytes = 0
    
    for d in sample_dirs:
        date_str = d.name.replace('sample_', '')
        try:
            # Need to handle potential errors gracefully to keep scanning
            df = load_edgx_data(d, symbol=symbol)
            if df.empty:
                continue
                
            signals = extract_all_signals(df)
            if signal_name not in signals:
                continue
                
            bits = signals[signal_name]
            bytes_list = bits_to_bytes(bits)
            
            # Update counters
            c = Counter(bytes_list)
            global_counter.update(c)
            date_counters[date_str] = dict(c.most_common(10))
            total_bytes += len(bytes_list)
            
            print(f"  ✓ {date_str}: {len(bytes_list)} bytes")
            
        except Exception as e:
            print(f"  ✗ {date_str}: Error ({e})")
            
    return {
        'total_bytes': total_bytes,
        'unique_opcodes': len(global_counter),
        'global_counts': dict(global_counter.most_common()),
        'date_snapshots': date_counters
    }


def generate_catalog_report(results: Dict, output_dir: Path):
    print(f"\nGenerating Opcode Catalog Report...")
    
    # 1. JSON Dump
    with open(output_dir / "master_vocabulary.json", 'w') as f:
        json.dump(results, f, indent=2)
        
    # 2. Visualization
    counts = results['global_counts']
    top_n = dict(list(counts.items())[:20])
    
    # Convert keys to Hex strings for display
    hex_keys = [f"0x{k:02X}" for k in top_n.keys()]
    values = list(top_n.values())
    pcts = [v / results['total_bytes'] * 100 for v in values]
    
    plt.figure(figsize=(12, 8))
    # Replace seaborn barplot with matplotlib bar
    plt.bar(hex_keys, pcts)
    plt.title(f"Master Opcode Vocabulary (Top 20) - {results['total_bytes']} bytes analyzed")
    plt.ylabel("Frequency (%)")
    plt.xlabel("Opcode (Hex)")
    plt.xticks(rotation=45)

    
    for i, v in enumerate(pcts):
        plt.text(i, v + 0.5, f"{v:.1f}%", ha='center')
        
    plt.tight_layout()
    plt.savefig(output_dir / "opcode_catalog.png")
    print(f"  ✓ Saved visualization to {output_dir / 'opcode_catalog.png'}")
    
    # 3. Print Summary
    print("\n" + "=" * 60)
    print("MASTER VOCABULARY SUMMARY")
    print("=" * 60)
    print(f"Total Bytes Processed: {results['total_bytes']:,}")
    print(f"Unique Opcodes Found:  {results['unique_opcodes']} / 256")
    print("\nTop 10 Opcodes:")
    print(f"{'Hex':<6} | {'Int':<5} | {'Count':<10} | {'%':<6} | {'ASCII'}")
    print("-" * 45)
    
    for k, v in list(counts.items())[:10]:
        char_val = chr(int(k)) if 32 <= int(k) <= 126 else '.'
        pct = v / results['total_bytes'] * 100
        print(f"0x{int(k):02X}   | {k:<5} | {v:<10} | {pct:.1f}% | {char_val}")


if __name__ == "__main__":
    output_dir = BASE_DIR / "research" / "edgx_deep_decode" / "results"
    output_dir.mkdir(exist_ok=True)
    
    catalog = scan_all_dates()
    generate_catalog_report(catalog, output_dir)
