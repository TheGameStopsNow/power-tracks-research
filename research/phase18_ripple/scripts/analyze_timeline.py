
import pandas as pd
import numpy as np
from pathlib import Path

# Load Data
BASE_DIR = Path(__file__).parent
matrix_path = BASE_DIR / "data/daily_density_matrix.csv"
df = pd.read_csv(matrix_path, index_col=0)

# Define Periods
PRE_EVENT = [
    "2024-04-29", "2024-04-30", "2024-05-01", "2024-05-02", "2024-05-03",
    "2024-05-06", "2024-05-07", "2024-05-08", "2024-05-09", "2024-05-10"
]

EVENT = [
    "2024-05-13", "2024-05-14", "2024-05-15", "2024-05-16", "2024-05-17"
]

POST_EVENT = [
    "2024-05-20", "2024-05-21", "2024-05-22", "2024-05-23", "2024-05-24",
    "2024-05-27", "2024-05-28", "2024-05-29", "2024-05-30", "2024-05-31"
]

def scan_period(period_name, dates):
    print(f"\n--- {period_name} Analysis ---")
    
    # Filter for valid dates in this period that exist in our data
    valid_dates = [d for d in dates if d in df.index]
    
    if not valid_dates:
        print("No data found for this period.")
        return

    sub_df = df.loc[valid_dates]
    
    # 1. High Density Anomalies (Raw threshold > 5% which is high context)
    # Most "Peace" density is ~3-4%. 
    # Let's verify what "Normal" is first.
    
    # Calculate global mean/std excluding zeros
    all_vals = df.values.flatten()
    all_vals = all_vals[all_vals > 0]
    global_mean = np.mean(all_vals)
    global_std = np.std(all_vals)
    
    threshold = global_mean + (2 * global_std)
    print(f"Global Baseline: {global_mean:.2%} +/- {global_std:.2%}")
    print(f"Anomaly Threshold (>2 Sigma): {threshold:.2%}")
    
    count = 0
    for date in valid_dates:
        row = sub_df.loc[date]
        for sym, val in row.items():
            if sym == "SYSTEM_TOTAL": continue
            if val > threshold:
                print(f"  [{date}] {sym}: {val:.2%} (Z={((val-global_mean)/global_std):.1f})")
                count += 1
                
    if count == 0:
        print("  No significant anomalies detected.")

def main():
    scan_period("PRE-EVENT (Apr 29 - May 10)", PRE_EVENT)
    scan_period("POST-EVENT (May 20 - May 31)", POST_EVENT)

if __name__ == "__main__":
    main()
