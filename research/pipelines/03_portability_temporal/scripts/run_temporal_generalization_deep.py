
#!/usr/bin/env python3
"""
Study 2.2: Timelessness Deep Dive.
KS Test for 2021 vs 2024 signal distributions.

Method:
1. Load 2024->2024 Distances (Baseline) from Study 1.1.
2. Run 2024->2021 Search (Target) to get raw distances.
3. Compute KS Test.
4. Metrics: KS Statistic, p-value.
"""

import subprocess
import json
import pandas as pd
import numpy as np
from scipy.stats import ks_2samp
import os
from pathlib import Path

# Configuration
SYMBOL = "GME"
TEMPLATE_DATE = "2024-05-13"
TEST_START = "2021-01-25"
TEST_END = "2021-01-29"

def run_search(start, end):
    print(f"--- Searching 2024 Templates in {start} to {end} ---")
    base_dir = Path(__file__).resolve().parent.parent
    tisa_script = base_dir.parent / "01_selectivity" / "scripts" / "tisa_spike_signature_search.py"
    
    cmd = [
        "python3", str(tisa_script),
        "--symbol", SYMBOL,
        "--date", TEMPLATE_DATE,
        "--bars-symbol", SYMBOL,
        "--scan-start", start,
        "--scan-end", end,
        "--k-spikes", "3",
        "--null-shuffles", "10",
        "--root", str(base_dir / "data" / "power_tracks"),
        "--bars", str(base_dir / "data" / "minute_bars")
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        # TISA writes to 01_selectivity/output by default relative to itself
        # This means tisa_script.parent.parent / "output".
        
        tisa_out_dir = tisa_script.parent.parent / "output"
        default_out = tisa_out_dir / f"tisa_spike_signatures_{SYMBOL}_vs_{SYMBOL}_{TEMPLATE_DATE}.json"
        
        if default_out.exists():
            with open(default_out) as f:
                return json.load(f)
    except subprocess.CalledProcessError as e:
        print(f"Error: {e.stderr}")
    return []

# ... (skipping main implementation for brevity if unchanged logic, but replacing it to ensure correct main structure) ...

def main():
    base_dir = Path(__file__).resolve().parent.parent
    # 1. Load 2024 Baseline (Study 1.1)
    # We'll re-run 2024 search quickly (single day).
    
    print("Getting 2024 Baseline...")
    data_2024 = run_search(TEMPLATE_DATE, TEMPLATE_DATE)
    dist_2024 = [d["realBest"] for d in data_2024]
    
    # 2. Run 2021 Target
    print("Getting 2021 Target...")
    data_2021 = run_search(TEST_START, TEST_END)
    dist_2021 = [d["realBest"] for d in data_2021]
    
    if not dist_2024 or not dist_2021:
        print("Error: Missing data.")
        return
        
    # 3. KS Test
    ks_stat, p_val = ks_2samp(dist_2024, dist_2021)
    
    print("\n=== Study 2.2 Results: Timelessness Deep Dive ===")
    print(f"2024 Mean Dist: {np.mean(dist_2024):.4f} (N={len(dist_2024)})")
    print(f"2021 Mean Dist: {np.mean(dist_2021):.4f} (N={len(dist_2021)})")
    print(f"KS Statistic: {ks_stat:.4f}")
    print(f"P-Value: {p_val:.4f}")
    
    interp = "Distributions are Identical (p > 0.05)" if p_val > 0.05 else "Distributions are Different (p < 0.05)"
    
    out_dir = base_dir / "output"
    out_dir.mkdir(exist_ok=True)
    out_md = out_dir / "temporal_generalization_deep.md"
    with open(out_md, "w") as f:
        f.write("# Study 2.2: Timelessness Deep Dive\n\n")
        f.write(f"**Comparison**: 2024 Self-Match vs 2021 Cross-Match\n")
        f.write(f"**KS Statistic**: {ks_stat:.4f}\n")
        f.write(f"**P-Value**: {p_val:.4f}\n")
        f.write(f"**Conclusion**: {interp}\n\n")
        f.write("## Statistics\n")
        f.write(f"*   **2024 Mean**: {np.mean(dist_2024):.4f}\n")
        f.write(f"*   **2021 Mean**: {np.mean(dist_2021):.4f}\n")
        
    print(f"Saved Report to {out_md}")

if __name__ == "__main__":
    main()
