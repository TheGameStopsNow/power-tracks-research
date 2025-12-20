#!/usr/bin/env python3
"""
State Reconstruction (Virtual Machine)
======================================

Attempts to reconstruct the internal state of the synchronization protocol.
Treats opcodes as instructions acting on a virtual 8-bit register.

Hypothesis:
    The stream synchronizes a set of flags (Bitmask).
    Opcode `0x01` sets Bit 0. Opcode `0x80` sets Bit 7.
    Padding (`0x00`/`0xFF`) might be distinct states or NO-OPs.

Logic Models:
    1. Bitwise OR (Cumulative Flags): State |= Opcode.
    2. Toggle (Switching): State ^= Opcode.
    3. Set/Clear: High bit sets, Low bit clears? (Complex).
"""

from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# Import local modules
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs, BASE_DIR
from core.extractors import extract_all_signals
from semantic_mapper import map_opcodes_to_history # Useful for alignment

def run_state_simulation(events_df: pd.DataFrame) -> pd.DataFrame:
    """
    Simulates the state evolution.
    """
    df = events_df.copy()
    opcodes = df['opcode'].values
    
    # Model 1: Bitwise OR with Decay
    # If we just OR everything, it stays at 0xFF forever.
    # Maybe 0x00 clears the state?
    
    states_or = np.zeros(len(df), dtype=int)
    current_state = 0
    
    for i, op in enumerate(opcodes):
        if op == 0x00:
            # Hypothesis: 0x00 is a "Clear" or "Reset" or "Idle"
            # Let's try: 0x00 decays the state (clears it)
            current_state = 0
        elif op == 0xFF:
            # 0xFF might be "All On" or Padding
            pass 
        else:
            # Active Opcode: Set bits
            current_state |= op
            
        states_or[i] = current_state
        
    df['state_or_reset'] = states_or
    
    # Model 2: Toggle
    states_toggle = np.zeros(len(df), dtype=int)
    current_state = 0
    for i, op in enumerate(opcodes):
        if op in [0x00, 0xFF]: 
            pass # Ignore padding
        else:
            current_state ^= op
        states_toggle[i] = current_state
        
    df['state_toggle'] = states_toggle
    
    return df

def plot_state_evolution(df: pd.DataFrame, output_path: Path):
    plt.figure(figsize=(12, 10))
    
    # Price (Top)
    plt.subplot(3, 1, 1)
    plt.plot(df['timestamp'], df['price'], color='black', linewidth=1)
    plt.title("Reference Price")
    plt.ylabel("Price")
    plt.grid(True, alpha=0.3)
    
    # OR Model (Middle)
    plt.subplot(3, 1, 2)
    plt.plot(df['timestamp'], df['state_or_reset'], color='blue', drawstyle='steps-post', linewidth=0.8)
    plt.title("Virtual State (Model: Bitwise OR + Reset on 0x00)")
    plt.ylabel("Register Value (0-255)")
    plt.grid(True, alpha=0.3)
    
    # Toggle Model (Bottom)
    plt.subplot(3, 1, 3)
    plt.plot(df['timestamp'], df['state_toggle'], color='green', drawstyle='steps-post', linewidth=0.8)
    plt.title("Virtual State (Model: XOR Toggle)")
    plt.ylabel("Register Value (0-255)")
    plt.xlabel("Time")
    plt.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path)
    print(f"  Saved state plot to {output_path}")

def analyze_state_correlation(df: pd.DataFrame):
    """
    Check if the State Value correlates with Volatility (Absolute Returns).
    """
    # Calculate realized volatility (rolling std of returns)
    df['returns'] = df['price'].pct_change()
    df['volatility'] = df['returns'].rolling(30).std() * 10000 # bps
    
    # Correlation
    c_or = df['volatility'].corr(df['state_or_reset'])
    c_toggle = df['volatility'].corr(df['state_toggle'])
    
    print("\n[State-Market Correlation]")
    print(f"  OR-Reset Model vs Volatility: {c_or:.4f}")
    print(f"  Toggle Model vs Volatility:   {c_toggle:.4f}")

def run_reconstruction():
    print("=" * 60)
    print("STATE MACHINE RECONSTRUCTION")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    target_dir = next((d for d in sample_dirs if "2024-09-05" in d.name), None)
    
    print(f"Reconstructing {target_dir.name}...")
    
    # Load and map opcodes
    df_raw = load_edgx_data(target_dir, symbol='GME')
    events = map_opcodes_to_history(df_raw)
    
    if events.empty:
        print("No events found.")
        return
        
    print(f"  Simulating state across {len(events)} events...")
    
    # Run Simulation
    events = run_state_simulation(events)
    
    # Plot
    out_dir = BASE_DIR / "research" / "edgx_deep_decode" / "results"
    plot_state_evolution(events, out_dir / "state_reconstruction.png")
    
    # Correlation
    analyze_state_correlation(events)

if __name__ == "__main__":
    run_reconstruction()
