
#!/usr/bin/env python3
"""
Study 3.2: HIP Intraday Flow Generalization.
Tests Flow->Price Causality (HIP) across the panel.

Method:
1. Load aggregated Delta Hedging Flow (`dH`) from parquet.
2. Load Minute Bars (`close`).
3. Resample Flow to 1-minute (sum).
4. Compute Cross-Correlation for lags -30 to +30 minutes.
5. Metrics:
   - Peak Correlation
   - Lag at Peak (Positive = Flow Leads Price)
   - Asymmetry (Positive Lag Mass / Total Mass)
"""

import pandas as pd
import numpy as np
import os
from pathlib import Path

def analyze_hip(symbol, date="2024-05-13"):
    base_dir = Path(__file__).resolve().parent.parent
    flow_path = base_dir / "data" / "flow" / f"{symbol}_{date}_flow.parquet"
    bars_path = base_dir / "data" / "minute_bars" / f"{symbol}_{date}_minute.csv"
    
    if not flow_path.exists() or not bars_path.exists():
        return None
        
    # 1. Load Data
    bars = pd.read_csv(bars_path)
    # ... (skipping unchanged) ...

    # ... (in main) ...
    out_dir = base_dir / "output"
    out_dir.mkdir(exist_ok=True)
    out_json = out_dir / "hip_panel_summary.json"
    df.to_json(out_json, orient="records", indent=2)
    
    out_md = out_dir / "hip_panel_summary.md"
    with open(out_md, "w") as f:
        f.write("# Study 3.2: HIP Intraday Flow Generalization\n\n")
        f.write("**Date**: 2024-05-13\n\n")
        f.write("## Causality Metrics\n")
        f.write("| Symbol | Max Corr | Lag (min) | Asymmetry |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        for _, row in df.iterrows():
            lag_str = f"+{row['max_lag']}" if row['max_lag'] > 0 else str(row['max_lag'])
            f.write(f"| {row['symbol']} | {row['max_corr']:.4f} | {lag_str} | {row['asymmetry']:.4f} |\n")
            
        f.write("\n\n## Interpretation\n")
        f.write("*   **Positive Lag**: Flow leads Price (Tail Wags Dog).\n")
        f.write("*   **Positive Asymmetry**: Causality is directional (Flow -> Price).\n")
            
    print(f"Saved Report to {out_md}")

if __name__ == "__main__":
    main()
