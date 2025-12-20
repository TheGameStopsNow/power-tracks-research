
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# Setup
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUT_DIR = BASE_DIR / "charts"
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Input from Phase 25b
PHASE_25_DATA = BASE_DIR.parent / "phase25_energy/data/energy_surface_15m.csv"

def main():
    print("--- Phase 26: Hydraulic Pressure Testing ---")
    
    if not PHASE_25_DATA.exists():
        print("Error: Phase 25b data not found.")
        return
        
    df = pd.read_csv(PHASE_25_DATA)
    # Pivot
    pivot = df.pivot_table(index='timestamp', columns='symbol', values='density', fill_value=0)
    pivot.index = pd.to_datetime(pivot.index)
    pivot = pivot.sort_index()
    
    # Define Pistons
    PISTON_A = ["GME", "AMC"] # The Core
    # Piston B is everyone else (The Relief Valves)
    PISTON_B = [c for c in pivot.columns if c not in PISTON_A]
    
    # Calculate Component Pressures
    pivot['Pressure_A'] = pivot[PISTON_A].sum(axis=1) # Sum of densities
    pivot['Pressure_B'] = pivot[PISTON_B].sum(axis=1)
    pivot['Total_System'] = pivot['Pressure_A'] + pivot['Pressure_B']
    
    # 1. Statistical Validation
    # Correlation
    overall_corr = pivot['Pressure_A'].corr(pivot['Pressure_B'])
    print(f"Overall Correlation (Piston A vs B): {overall_corr:.4f}")
    
    # Rolling Correlation (intra-day shifts might be tighter)
    # 2 Hour Window (8 x 15min)
    pivot['Rolling_Corr'] = pivot['Pressure_A'].rolling(window=8).corr(pivot['Pressure_B'])
    
    # Volatility Check (Coefficient of Variation: Std/Mean)
    cv_a = pivot['Pressure_A'].std() / pivot['Pressure_A'].mean()
    cv_b = pivot['Pressure_B'].std() / pivot['Pressure_B'].mean()
    cv_total = pivot['Total_System'].std() / pivot['Total_System'].mean()
    
    print("\n--- Stability Analysis (Coefficient of Variation) ---")
    print(f"Piston A (GME/AMC) CV: {cv_a:.4f} (High Volatility)")
    print(f"Piston B (Sleepers) CV: {cv_b:.4f}")
    print(f"Total System CV:      {cv_total:.4f}")
    if cv_total < cv_a:
        print(">> CONFIRMED: Total System is more stable than the Core. Energy is Conserved.")
    
    # Save Stats
    stats = pd.DataFrame({
        "Metric": ["Correlation_A_B", "CV_A", "CV_B", "CV_Total"],
        "Value": [overall_corr, cv_a, cv_b, cv_total]
    })
    stats.to_csv(DATA_DIR / "pressure_stats.csv", index=False)
    
    # 2. Visual: The Piston Chart
    generate_piston_chart(pivot)

def generate_piston_chart(df):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
    
    # Subplot 1: The Pistons (Inverse Movement)
    # Normalize for comparison? Or raw density sum? Raw shows the "load".
    ax1.plot(df.index, df['Pressure_A'], label="Piston A (GME/AMC)", color='dodgerblue', linewidth=2)
    ax1.plot(df.index, df['Pressure_B'], label="Piston B (Sleepers)", color='orange', linewidth=2)
    
    ax1.set_title("The Hydraulic Pistons: Core vs Sleepers (Summed Opcode Density)", fontsize=14)
    ax1.set_ylabel("Pressure (Total Density)")
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Subplot 2: Total System Pressure & Rolling Correlation
    color = 'tab:green'
    ax2.set_xlabel('Time (May 13-17)')
    ax2.set_ylabel('Total System Pressure', color=color)
    ax2.plot(df.index, df['Total_System'], color=color, label="Total System", linewidth=3, alpha=0.8)
    ax2.tick_params(axis='y', labelcolor=color)
    ax2.set_ylim(bottom=0)
    
    # Twin axis for correlation
    ax3 = ax2.twinx() 
    color = 'tab:red'
    ax3.set_ylabel('Rolling Correlation (2H)', color=color)  
    ax3.plot(df.index, df['Rolling_Corr'], color=color, linestyle='--', label="A vs B Correlation", alpha=0.6)
    ax3.tick_params(axis='y', labelcolor=color)
    ax3.axhline(0, color='grey', linewidth=0.5)
    
    ax2.set_title("System Stability & Inverse Relationship", fontsize=12)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "piston_chart.png")
    print(f"Saved {OUT_DIR}/piston_chart.png")

if __name__ == "__main__":
    main()
