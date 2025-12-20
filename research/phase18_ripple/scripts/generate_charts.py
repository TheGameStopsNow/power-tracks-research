
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# Setup
BASE_DIR = Path(__file__).parent
DATA_PATH = BASE_DIR / "data/daily_density_matrix.csv"
OUT_DIR = BASE_DIR / "charts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def generate_charts():
    df = pd.read_csv(DATA_PATH, index_col=0)
    
    # Filter for valid trading days
    df = df.loc[(df != 0).any(axis=1)]
    
    # 1. THE RIPPLE WAVES (Cadence Line Chart)
    targets = ["KOSS", "GME", "SLE", "CLOV", "AMC"]
    plt.figure(figsize=(12, 6))
    for sym in targets:
        if sym in df.columns:
            plt.plot(df.index, df[sym], label=sym, marker='o', linewidth=2)
            
    plt.title("The Ripple Effect: Sequential Activation", fontsize=14)
    plt.ylabel("Opcode Density")
    plt.xlabel("Date")
    plt.xticks(rotation=45)
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "ripple_waves.png")
    print(f"Saved {OUT_DIR}/ripple_waves.png")
    
    # 2. THE BLANKET (Total System Energy)
    plt.figure(figsize=(12, 6))
    
    # Calculate System Total on the fly
    sys_total = df.sum(axis=1)
    # sys_total = df["SYSTEM_TOTAL"]  # Removed due to missing col
    sys_norm = (sys_total - sys_total.mean()) / sys_total.std()
    
    if "KOSS" in df.columns:
        koss_series = df["KOSS"]
    else:
        # Fallback if KOSS missing (unlikely)
        koss_series = df.iloc[:, 0]
        
    koss_norm = (koss_series - koss_series.mean()) / koss_series.std()
    
    plt.plot(df.index, sys_norm, label="Total System Energy (51 Symbols)", color='grey', linewidth=3, alpha=0.7)
    plt.plot(df.index, koss_norm, label="KOSS (The Breach)", color='red', linewidth=2, linestyle='--')
    
    plt.title("Conservation of Volatility: Local Spike vs System Stability", fontsize=14)
    plt.ylabel("Normalized Density (Z-Score)")
    plt.xticks(rotation=45)
    plt.legend()
    plt.grid(True, alpha=0.3)
    # Add vertical line for start of War Week if date exists
    if "2024-05-13" in df.index:
        plt.axvline("2024-05-13", color='black', linestyle=':', label="Event Start")
        
    plt.tight_layout()
    plt.savefig(OUT_DIR / "system_energy.png")
    print(f"Saved {OUT_DIR}/system_energy.png")
    
    # 3. CADENCE HEATMAP (Matplotlib Version)
    # Filter top 20 by variance
    variances = df.var().sort_values(ascending=False)
    
    # EXCLUDE ZOMBIES/ARTIFACTS
    if "BLIAQ" in variances.index:
        variances = variances.drop("BLIAQ")

    top_20 = variances.head(20).index.tolist()
    # if "SYSTEM_TOTAL" in top_20: top_20.remove("SYSTEM_TOTAL") # No longer needed as it's not in df
    
    heatmap_data = df[top_20].transpose()
    
    plt.figure(figsize=(14, 10))
    # Use imshow
    plt.imshow(heatmap_data, cmap="inferno", aspect='auto')
    
    # Add colorbar
    plt.colorbar(label="Opcode Density")
    
    # Set ticks
    plt.yticks(range(len(heatmap_data.index)), heatmap_data.index)
    plt.xticks(range(len(heatmap_data.columns)), heatmap_data.columns, rotation=45, ha='right')
    
    plt.title("Market Microstructure Heatmap: The Cadence of Activation", fontsize=14)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "cadence_heatmap.png")
    print(f"Saved {OUT_DIR}/cadence_heatmap.png")

if __name__ == "__main__":
    generate_charts()
