
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# Setup
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUT_DIR = BASE_DIR / "charts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

def generate_charts():
    # 1. Co-occurrence Matrix Heatmap
    matrix_path = DATA_DIR / "jaccard_matrix.csv"
    if matrix_path.exists():
        df = pd.read_csv(matrix_path, index_col=0)
        
        plt.figure(figsize=(10, 8))
        im = plt.imshow(df, cmap="viridis", vmin=0, vmax=0.5)
        
        # Add labels
        plt.xticks(range(len(df.columns)), df.columns, rotation=45)
        plt.yticks(range(len(df.index)), df.index)
        
        # Annotate
        for i in range(len(df.index)):
            for j in range(len(df.columns)):
                text = plt.text(j, i, f"{df.iloc[i, j]:.2f}",
                               ha="center", va="center", color="w", fontsize=9)
                               
        plt.colorbar(im, label="Jaccard Probability")
        plt.title("Synchronicity Matrix\nProbability of Simultaneous Opcode Firing", fontsize=14)
        plt.tight_layout()
        plt.savefig(OUT_DIR / "synchronicity_matrix.png")
        print(f"Saved {OUT_DIR}/synchronicity_matrix.png")
        
    # 2. Cluster Event Timeline
    cluster_path = DATA_DIR / "cluster_events.csv"
    if cluster_path.exists():
        df_c = pd.read_csv(cluster_path, index_col=0)
        df_c.index = pd.to_datetime(df_c.index)
        
        plt.figure(figsize=(12, 6))
        plt.scatter(df_c.index, df_c['active_count'], c=df_c['active_count'], cmap='plasma', alpha=0.6, s=50)
        plt.title("Cluster Events: Moments of High Network Cohesion", fontsize=14)
        plt.ylabel("Active Symbols (Count)")
        plt.xlabel("Date (May 13-17 War Week)")
        plt.colorbar(label="Active Count")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(OUT_DIR / "cluster_timeline.png")
        print(f"Saved {OUT_DIR}/cluster_timeline.png")

if __name__ == "__main__":
    generate_charts()
