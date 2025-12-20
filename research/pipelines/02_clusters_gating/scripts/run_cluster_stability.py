
#!/usr/bin/env python3
"""
Study 1.2: Cluster Stability & Overfitting Check.
Tests if Clusters 1 & 3 are stable partitions or artifacts.

Method:
1. Load burst features from `reports/diagnostics/edgx_bursts/burst_clusters.csv`.
2. Bootstrap Resampling (N=100 iterations).
3. Re-cluster (K-Means, K=6) on each resample.
4. Map new clusters to original labels (Hungarian algorithm or simple overlap).
5. Measure:
   - Label Stability (Fraction of bursts retaining label).
   - Performance Stability (Mean Return of "Signal" vs "Noise" clusters).
"""

import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score
import json
import os
from pathlib import Path

def main():
    # 1. Load Data
    # Assuming these files are placed in data/ for analysis
    base_dir = Path(__file__).resolve().parent.parent
    path = base_dir / "data" / "burst_clusters.csv"
    returns_path = base_dir / "data" / "burst_future_returns.csv"
    
    if not path.exists() or not returns_path.exists():
        print(f"Error: Data not found in {base_dir}/data/")
        return
        
    df = pd.read_csv(path)
    ret_df = pd.read_csv(returns_path)
    
    # ... (skipping unchanged lines) ...

    out_dir = base_dir / "output"
    out_dir.mkdir(exist_ok=True)
    out_json = out_dir / "cluster_stability.json"
    res = {
        "signal_mean": sig_mean,
        "signal_ci": list(sig_ci),
        "noise_mean": noise_mean,
        "noise_ci": list(noise_ci),
        "robust": bool(robust)
    }
    with open(out_json, "w") as f:
        json.dump(res, f, indent=2)
        
    out_md = out_dir / "cluster_stability.md"
    with open(out_md, "w") as f:
        f.write("# Study 1.2: Cluster Stability\n\n")
        f.write(f"**Iterations**: {n_boot}\n")
        f.write(f"**Robust**: {'YES' if robust else 'NO'}\n\n")
        f.write("## Performance Stability (Bootstrap)\n")
        f.write(f"*   **Signal Clusters**: {sig_mean:.1%} (CI: {sig_ci[0]:.1%} - {sig_ci[1]:.1%})\n")
        f.write(f"*   **Noise Clusters**:  {noise_mean:.1%} (CI: {noise_ci[0]:.1%} - {noise_ci[1]:.1%})\n")
        
    print(f"Saved Report to {out_md}")

if __name__ == "__main__":
    main()
