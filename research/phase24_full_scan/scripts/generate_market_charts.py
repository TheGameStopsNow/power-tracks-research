
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# Setup
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUT_DIR = BASE_DIR / "charts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def generate_charts():
    # Load Results
    res_path = DATA_DIR / "dragnet_results.csv"
    if not res_path.exists():
        print("Results not found")
        return
        
    df = pd.read_csv(res_path)
    
    # 1. Density Distribution (Histogram)
    plt.figure(figsize=(12, 6))
    plt.hist(df['density'], bins=50, color='purple', alpha=0.7, log=True)
    plt.title("Market-Wide Opcode Density Distribution (Probe: May 14)", fontsize=14)
    plt.xlabel("Opcode Density")
    plt.ylabel("Number of Symbols (Log Scale)")
    plt.axvline(0.065, color='red', linestyle='--', label="Basket Average (~6.5%)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "market_distribution.png")
    print(f"Saved {OUT_DIR}/market_distribution.png")
    
    # 2. Top sleeprs Bar Chart
    top_20 = df.head(20)
    plt.figure(figsize=(14, 8))
    plt.bar(top_20['symbol'], top_20['density'], color='teal')
    plt.title("The Hidden Network: Top 20 'Sleeper' Nodes (May 14)", fontsize=14)
    plt.ylabel("Opcode Density")
    plt.xlabel("Symbol")
    plt.xticks(rotation=45)
    plt.grid(True, axis='y', alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "sleeper_rank.png")
    print(f"Saved {OUT_DIR}/sleeper_rank.png")

if __name__ == "__main__":
    generate_charts()
