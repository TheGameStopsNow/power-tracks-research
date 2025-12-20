
#!/usr/bin/env python3
"""
Study 1.1: Selectivity Re-confirmation.
Verifies Study A with stricter nulls and an extended panel.

Panel:
- Target: GME
- Basket: AMC, KOSS, CHWY, BB, TLRY
- Control (Tech): NVDA, AAPL, MSFT, TSLA, PLTR
- Control (Index): SPY, IWM, QQQ, DIA

Metrics:
- Selectivity Score (Distance / GME_Distance)
- Cohen's d (Effect Size vs GME Self-Match)
"""

import subprocess
import json
import pandas as pd
import numpy as np
import os
from pathlib import Path

# Configuration
TARGET = "GME"
DATE = "2024-05-13"
BASKET = ["AMC", "KOSS", "CHWY", "BB", "TLRY"]
CONTROLS_TECH = ["NVDA", "AAPL", "MSFT", "TSLA", "PLTR"]
CONTROLS_INDEX = ["SPY", "IWM", "QQQ", "DIA"]
ALL_SYMBOLS = [TARGET] + BASKET + CONTROLS_TECH + CONTROLS_INDEX

def run_search(search_symbol):
    print(f"--- Searching GME templates in {search_symbol} ---")
    script_path = Path(__file__).resolve().parent / "tisa_spike_signature_search.py"
    cmd = [
        "python3", str(script_path),
        "--symbol", TARGET,
        "--date", DATE,
        "--bars-symbol", search_symbol,
        "--scan-start", DATE,
        "--scan-end", DATE,
        "--k-spikes", "3",
        "--null-shuffles", "10"
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        out_path = Path(__file__).resolve().parent.parent / "output" / f"tisa_spike_signatures_{TARGET}_vs_{search_symbol}_{DATE}.json"
        if out_path.exists():
            with open(out_path) as f:
                return json.load(f)
    except subprocess.CalledProcessError as e:
        print(f"Error running search for {search_symbol}: {e.stderr}")
    return []

def compute_cohens_d(group1, group2):
    # Calculate Cohen's d between two samples
    n1, n2 = len(group1), len(group2)
    var1, var2 = np.var(group1, ddof=1), np.var(group2, ddof=1)
    
    # Pooled standard deviation
    pooled_se = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))
    
    return (np.mean(group1) - np.mean(group2)) / pooled_se

def main():
    results = []
    gme_distances = []
    
    # 1. Run Search
    for sym in ALL_SYMBOLS:
        data = run_search(sym)
        if not data:
            print(f"No results for {sym}")
            continue
            
        distances = [d["realBest"] for d in data]
        if not distances: continue
        
        if sym == TARGET:
            gme_distances = distances
        
        mean_dist = np.mean(distances)
        std_dist = np.std(distances)
        
        group = "Target"
        if sym in BASKET: group = "Basket"
        elif sym in CONTROLS_TECH: group = "Control (Tech)"
        elif sym in CONTROLS_INDEX: group = "Control (Index)"
        
        entry = {
            "symbol": sym,
            "group": group,
            "mean_dist": mean_dist,
            "std_dist": std_dist,
            "n_templates": len(distances),
            "raw_distances": distances
        }
        results.append(entry)

    # 2. Compute Metrics
    if not gme_distances:
        print("Error: Baseline (GME) failed.")
        return

    base_mean = np.mean(gme_distances)
    
    for r in results:
        r["selectivity_score"] = r["mean_dist"] / base_mean
        
        # Cohen's d (Effect Size)
        # Positive d means the symbol has HIGHER distance (worse match) than GME.
        # This confirms selectivity.
        if r["symbol"] != TARGET:
            r["cohens_d"] = compute_cohens_d(r["raw_distances"], gme_distances)
        else:
            r["cohens_d"] = 0.0
            
        del r["raw_distances"] # Cleanup for JSON

    # 3. Save Report
    df = pd.DataFrame(results)
    df = df.sort_values("mean_dist")
    
    print("\n=== Study 1.1 Results: Selectivity Re-confirmation ===")
    print(df[["symbol", "group", "mean_dist", "selectivity_score", "cohens_d"]])
    
    out_dir = Path(__file__).resolve().parent.parent / "output"
    out_dir.mkdir(exist_ok=True)
    out_json = out_dir / "selectivity_suite.json"
    df.to_json(out_json, orient="records", indent=2)
    
    out_md = out_dir / "selectivity_suite.md"
    with open(out_md, "w") as f:
        f.write("# Study 1.1: Selectivity Re-confirmation\n\n")
        f.write(f"**Target**: {TARGET} (May 13, 2024)\n")
        f.write(f"**Baseline Distance**: {base_mean:.4f}\n\n")
        f.write("## Results Table\n")
        f.write("| Symbol | Group | Mean Dist | Selectivity | Cohen's d |\n")
        f.write("| :--- | :--- | :--- | :--- | :--- |\n")
        for _, row in df.iterrows():
            f.write(f"| {row['symbol']} | {row['group']} | {row['mean_dist']:.4f} | {row['selectivity_score']:.4f} | {row['cohens_d']:.2f} |\n")
            
        f.write("\n\n## Interpretation\n")
        f.write("*   **Cohen's d > 0.8**: Large Effect (Strong Selectivity).\n")
        f.write("*   **Cohen's d < 0.2**: Negligible Effect (Generic Pattern).\n")
        
    print(f"Saved Report to {out_md}")

if __name__ == "__main__":
    main()
