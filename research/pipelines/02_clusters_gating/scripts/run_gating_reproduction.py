
#!/usr/bin/env python3
"""
Study C: Gate Efficacy (Cluster + K-Spike).
Tests if the "Gated" signal outperforms its components.

Method:
1. Sample 50 random GME bursts from `data/power_tracks/GME`.
2. For each burst:
   - Extract Cluster (Impactor/Binder -> Signal, Others -> Noise).
   - Run K-Spike Detection (p-value).
   - Compute 20-Day Max Return from Minute Bars.
3. Define 4 Arms:
   - Arm 1: All Bursts (Baseline).
   - Arm 2: Cluster Signal Only.
   - Arm 3: K-Spike Signal Only (p < 0.05).
   - Arm 4: Gated (Cluster + K-Spike).
4. Metric: Win Rate (>10% Return).
"""

import os
import json
import random
import subprocess
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

# Configuration
SYMBOL = "GME"
SAMPLE_SIZE = 50
# Bars assumed to be in the local Phase data folder
BARS_DIR = "data/minute_bars"

def get_cluster_label(summary):
    # Map text labels to Cluster IDs
    # Impactor/Binder -> Signal (1/3)
    # Echo/Macro/Unknown -> Noise (0)
    c = summary.get("clusters", {}).get("primary", "unknown")
    if c in ["impactor", "binder"]:
        return "Signal"
    return "Noise"

def compute_return(date_str, bars_df):
    # 20-Day Max Return
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except:
        return 0.0
        
    start_ts = dt
    end_ts = dt + timedelta(days=20)
    
    # Filter bars
    mask = (bars_df["timestamp"] >= start_ts) & (bars_df["timestamp"] <= end_ts)
    window = bars_df[mask]
    
    if window.empty:
        return 0.0
        
    start_price = window.iloc[0]["close"]
    max_price = window["close"].max()
    
    return (max_price - start_price) / start_price

def run_tisa(track_id, date_str):
    # Run TISA for specific track
    # We use tisa_spike_signature_search.py from 01_selectivity
    base_dir = Path(__file__).resolve().parent.parent
    tisa_script = base_dir.parent / "01_selectivity" / "scripts" / "tisa_spike_signature_search.py"
    
    cmd = [
        "python3", str(tisa_script),
        "--symbol", SYMBOL,
        "--date", date_str,
        "--bars-symbol", SYMBOL,
        "--scan-start", date_str,
        "--scan-end", date_str,
        "--k-spikes", "3",
        "--null-shuffles", "10",
        "--root", str(base_dir / "data" / "power_tracks"),
        "--bars", str(base_dir / "data" / "minute_bars")
    ]
    
    try:
        # Check if report already exists to avoid re-running
        # TISA output logic might need to be checked. It writes to ../01_selectivity/output by default 
        # unless we redirect it. This script previously expected reports/ in CWD.
        # tisa script now writes to its own ../output relative to itself.
        # This is strictly tricky if we want to read it back here.
        # TISA script doesn't take --output-dir argument yet.
        # We might need to look in 01_selectivity/output/
        
        tisa_out_dir = tisa_script.parent.parent / "output"
        report_path = tisa_out_dir / f"tisa_spike_signatures_{SYMBOL}_vs_{SYMBOL}_{date_str}.json"
        
        if not report_path.exists():
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            
        if report_path.exists():
            with open(report_path) as f:
                data = json.load(f)
            # Find our track
            for entry in data:
                if entry["trackId"] == track_id:
                    return entry["pValue"]
    except Exception as e:
        print(f"TISA Error: {e}")
        
    return 1.0 # Default to high p-value (fail)

def main():
    base_dir = Path(__file__).resolve().parent.parent
    # 1. Load All Tracks
    root = base_dir / "data" / "power_tracks" / SYMBOL
    if not root.exists():
        print(f"Error: {root} does not exist. Run download_data.py first.")
        return
        
    tracks = [d for d in root.iterdir() if d.is_dir()]
    
    # 2. Sample
    if len(tracks) > SAMPLE_SIZE:
        sample = random.sample(tracks, SAMPLE_SIZE)
    else:
        sample = tracks
        
    print(f"Processing {len(sample)} bursts...")
    
    # Load Bars Cache (to avoid reloading for every burst)
    
    results = []
    
    for i, track_dir in enumerate(sample):
        print(f"[{i+1}/{len(sample)}] Processing {track_dir.name}...")
        
        try:
            with open(track_dir / "summary.json") as f:
                summary = json.load(f)
                
            date_str = summary.get("date")
            det_time = summary.get("detection_time")
            if not date_str or not det_time: continue
            
            # Cluster
            cluster = get_cluster_label(summary)
            
            # K-Spike
            p_value = run_tisa(track_dir.name, date_str)
            
            # Return
            max_ret = 0.0
            # Simple stitching
            current_date = datetime.strptime(date_str, "%Y-%m-%d")
            prices = []
            for d in range(20):
                d_str = (current_date + timedelta(days=d)).strftime("%Y-%m-%d")
                p = base_dir / "data" / "minute_bars" / f"{SYMBOL}_{d_str}_minute.csv"
                if p.exists():
                    df = pd.read_csv(p)
                    # Parse timestamp
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    prices.extend(df["close"].tolist())
            
            if prices:
                start_price = prices[0]
                max_price = max(prices)
                max_ret = (max_price - start_price) / start_price
            
            results.append({
                "track_id": track_dir.name,
                "cluster": cluster,
                "p_value": p_value,
                "return_20d": max_ret
            })
            
        except Exception as e:
            print(f"Error processing {track_dir.name}: {e}")
            
    # 3. Analyze Arms
    df = pd.DataFrame(results)
    
    arms = {
        "Baseline (All)": df,
        "Cluster Only": df[df["cluster"] == "Signal"],
        "K-Spike Only": df[df["p_value"] < 0.05],
        "Gated (Both)": df[(df["cluster"] == "Signal") & (df["p_value"] < 0.05)]
    }
    
    report_rows = []
    for name, arm_df in arms.items():
        n = len(arm_df)
        if n == 0:
            win_rate = 0.0
            mean_ret = 0.0
        else:
            win_rate = (arm_df["return_20d"] > 0.10).mean()
            mean_ret = arm_df["return_20d"].mean()
            
        report_rows.append({
            "Arm": name,
            "N": n,
            "Win Rate (>10%)": win_rate,
            "Mean Return": mean_ret
        })
        
    res_df = pd.DataFrame(report_rows)
    print("\n=== Study C Results: Gate Efficacy ===")
    print(res_df)
    
    out_dir = base_dir / "output"
    out_dir.mkdir(exist_ok=True)
    out_json = out_dir / "gating_reproduction.json"
    res_df.to_json(out_json, orient="records", indent=2)
    
    out_md = out_dir / "gating_reproduction.md"
    with open(out_md, "w") as f:
        f.write("# Study C: Gate Efficacy\n\n")
        f.write(f"**Sample Size**: {len(df)}\n\n")
        f.write("## Results Table\n")
        # Manual Markdown Table
        f.write("| Arm | N | Win Rate (>10%) | Mean Return |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        for _, row in res_df.iterrows():
            f.write(f"| {row['Arm']} | {row['N']} | {row['Win Rate (>10%)']:.1%} | {row['Mean Return']:.1%} |\n")
            
    print(f"Saved Report to {out_md}")

if __name__ == "__main__":
    main()
