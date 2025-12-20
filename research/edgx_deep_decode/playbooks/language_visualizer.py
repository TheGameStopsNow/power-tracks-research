#!/usr/bin/env python3
"""
Language Visualizer (Phase 28)
==============================

Visualizes the "Grammar" of the EDGX signals overlaid on Price Action.
Generates: 'storm_vs_calm_grammar.png'

Goal: Show how the "State Machine" (Floor, Pivot, Ceiling) activates during the Storm (May 2024)
vs how it compresses during the Calm (Aug 2024).
"""

from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import sys

# Import local modules
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs
from core.extractors import extract_all_signals
from adversarial_decoding import bits_to_bytes
from extended_analysis import parse_messages

def plot_grammar():
    print("=" * 60)
    print("LANGUAGE VISUALIZER: CHARTING THE MACHINE")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    
    # Select Representative Days
    # Storm: May 14, 2024 (High Vol)
    # Calm: Aug 05, 2024 (Low Vol)
    
    storm_day = next((d for d in sample_dirs if "2024-05-14" in d.name), None)
    calm_day = next((d for d in sample_dirs if "2024-08-05" in d.name), None)
    
    if not storm_day or not calm_day:
        print("Required samples not found.")
        return

    days = [("The Storm (May 14)", storm_day), ("The Calm (Aug 05)", calm_day)]
    
    fig, axes = plt.subplots(2, 1, figsize=(15, 10), sharex=False)
    plt.subplots_adjust(hspace=0.3)
    
    for i, (label, d) in enumerate(days):
        ax = axes[i]
        print(f"Processing {label}...")
        
        df = load_edgx_data(d, symbol='GME')
        
        # Plot Price Line (Gray)
        # Resample to 1-min for clean line
        df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_convert('US/Eastern')
        price_line = df.set_index('timestamp')['price'].resample('1min').last().dropna()
        
        ax.plot(price_line.index, price_line.values, color='gray', alpha=0.5, label='Price', linewidth=1)
        
        # Extract Signals
        signals = extract_all_signals(df)
        byte_stream = bits_to_bytes(signals['price_lsb_1c'])
        msgs = parse_messages(byte_stream, df)
        
        # Overlay States
        # Floor: 0xA0 (Green)
        # Pivot: 0x80 (Blue)
        # Ceiling: 0x98 / 0x3E (Red)
        
        floors = []
        pivots = []
        ceilings = []
        
        for m in msgs:
            if pd.notnull(m['header_type']):
                op = int(m['header_type'])
                ts = pd.to_datetime(m['timestamp']).tz_convert('US/Eastern')
                price = m['price']
                
                if op == 0xA0:
                    floors.append((ts, price))
                elif op == 0x80:
                    pivots.append((ts, price))
                elif op in [0x98, 0x3E, 0xD7]: # Extended Ceiling set
                    ceilings.append((ts, price))
                    
        # Plot Overlays
        if floors:
            fx, fy = zip(*floors)
            ax.scatter(fx, fy, color='green', marker='^', s=100, label='Floor (0xA0)', zorder=5)
            
        if pivots:
            px, py = zip(*pivots)
            ax.scatter(px, py, color='blue', marker='o', s=50, label='Pivot (0x80)', zorder=4)
            
        if ceilings:
            cx, cy = zip(*ceilings)
            ax.scatter(cx, cy, color='red', marker='v', s=100, label='Ceiling (0x98/0x3E)', zorder=5)
            
        ax.set_title(f"{label} - Grammar Overlay", fontsize=12, fontweight='bold')
        ax.set_ylabel("Price ($)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        
    out_path = Path(__file__).parent / "storm_vs_calm_grammar.png"
    plt.savefig(out_path)
    print(f"Saved chart to {out_path}")

if __name__ == "__main__":
    plot_grammar()
