
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from pathlib import Path

# Setup
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUT_DIR = BASE_DIR / "charts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def generate_animation():
    csv_path = DATA_DIR / "energy_surface_15m.csv"
    if not csv_path.exists():
        print("Data not found")
        return
        
    df = pd.read_csv(csv_path)
    # Pivot: Time x Symbol
    pivot = df.pivot_table(index='timestamp', columns='symbol', values='density', fill_value=0)
    pivot = pivot.sort_index()
    
    # Sort columns by importance similar to stack
    cols = list(pivot.columns)
    priority = ["GME", "AMC", "KOSS", "LEN.B", "AMAL", "DJTWW"]
    cols.sort(key=lambda x: priority.index(x) if x in priority else 99)
    # Keep only columns with significant data?
    # No, show all Top 20
    pivot = pivot[cols]
    
    # Matplotlib Animation
    fig, ax = plt.subplots(figsize=(15, 6))
    
    # Init Bar Chart (Heatmap might be hard to read if 1D strip)
    # Let's do a Bar Chart Race style or just dynamic bars
    # X = Stock, Y = Density
    
    stocks = pivot.columns
    x_pos = np.arange(len(stocks))
    
    bars = ax.bar(x_pos, pivot.iloc[0], color='teal')
    
    ax.set_ylim(0, 0.45) # Fixed Y axis (Max density ~45% observed)
    ax.set_xticks(x_pos)
    ax.set_xticklabels(stocks, rotation=45, ha='right')
    ax.set_ylabel("Opcode Density")
    ax.set_title("Market Flow: Opcode Density Evolution")
    
    # Text annotation for timestamp
    time_text = ax.text(0.02, 0.95, '', transform=ax.transAxes, fontsize=12, fontweight='bold')
    
    def update(frame):
        # Frame is index integer
        row = pivot.iloc[frame]
        timestamp = pivot.index[frame]
        
        # Update bars
        for bar, val, name in zip(bars, row, stocks):
            bar.set_height(val)
            # Color code: Core=Blue, Sleepers=Orange?
            if name in ["GME", "AMC", "KOSS"]:
                bar.set_color('dodgerblue')
            elif name in ["LEN.B", "AMAL"]:
                bar.set_color('orange')
            else:
                bar.set_color('lightgrey')
                
        time_text.set_text(f"Time: {timestamp}")
        return bars + (time_text,)
        
    ani = animation.FuncAnimation(fig, update, frames=len(pivot), blit=True, interval=100)
    
    # Save
    save_path = OUT_DIR / "market_flow.gif"
    print(f"Rendering {len(pivot)} frames to GIF...")
    ani.save(save_path, writer='pillow', fps=10)
    print(f"Saved {save_path}")

if __name__ == "__main__":
    generate_animation()
