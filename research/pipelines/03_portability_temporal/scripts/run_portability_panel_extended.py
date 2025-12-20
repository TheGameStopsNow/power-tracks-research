
#!/usr/bin/env python3
"""
Study 2.1: Full Portability Panel (Extended).
Validates the "Basket Taxonomy" via unsupervised clustering.

Method:
1. Load results from Study 1.1 (Selectivity Suite).
2. Features: [Resonance Score, Cohen's d].
3. Unsupervised Clustering (K-Means, K=3).
4. Map clusters to Roles:
   - Engine/Satellite (High Resonance)
   - Control (Low Resonance)
   - Outlier (if any)
"""

import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
import json
import os
from pathlib import Path

def main():
    # 1. Load Study 1.1 Results
    base_dir = Path(__file__).resolve().parent.parent
    src = base_dir.parent / "01_selectivity" / "output" / "selectivity_suite.json"
    
    if not src.exists():
        print(f"Error: {src} not found. Run Study 1.1 first.")
        return
        
    with open(src) as f:
        data = json.load(f)

    # ... (skipping lines) ...

    out_dir = base_dir / "output"
    out_dir.mkdir(exist_ok=True)
    out_json = out_dir / "portability_panel_extended.json"
    df.to_json(out_json, orient="records", indent=2)
    
    out_md = out_dir / "portability_panel_extended.md"
    with open(out_md, "w") as f:
        f.write("# Study 2.1: Full Portability Panel\n\n")
        f.write("## Taxonomy Clustering (K=3)\n")
        f.write("| Symbol | Group | Resonance | Cohen's d | Inferred Role |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        for _, row in df.iterrows():
            f.write(f"| {row['symbol']} | {row['group']} | {row['resonance_score']:.4f} | {row['cohens_d']:.2f} | {row['inferred_role']} |\n")
            
    print(f"Saved Report to {out_md}")

if __name__ == "__main__":
    main()
