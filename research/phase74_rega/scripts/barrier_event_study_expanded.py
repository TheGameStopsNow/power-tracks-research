import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import json
import glob

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
SAMPLES_DIR = BASE_DIR / "data/samples"
TICKS_DIR = BASE_DIR / "data/ticks"
OUTPUT_DIR = BASE_DIR / "research/phase74_rega/results"

def get_tick_files():
    # 1. Old Samples
    pattern1 = str(SAMPLES_DIR / "sample_*/raw_ticks/GME_*_trades.csv")
    files1 = glob.glob(pattern1)
    
    # 2. New Ticks (Jan 2024 Control)
    # Format: data/ticks/YYYY-MM-DD/GME.csv
    pattern2 = str(TICKS_DIR / "*/*GME*.csv")
    files2 = glob.glob(pattern2)
    
    # Unique and sorted
    files = sorted(list(set(files1 + files2)))
    return files

def analyze_file(filepath):
    print(f"Analyzing {Path(filepath).name}...")
    try:
        df = pd.read_csv(filepath)
        
        # Normalize Index
        columns = [c.lower() for c in df.columns]
        df.columns = columns
        
        # Handle Timestamp variations
        if 'timestamp_us' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp_us'], unit='us')
        elif 'sip_timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['sip_timestamp'], unit='ns')
        else:
            # Fallback to mixed
            df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed')

        
        # Simple side classification
        df['delta'] = df['price'].diff()
        df['side'] = np.sign(df['delta']).fillna(0)
        
        # Identify Round Number Barriers ($1 increments? $5 is better for Gamma?)
        # GME strikes are often $1 or $0.5. Let's look for Integer crossings.
        
        # Crossings logic
        df['prev_price'] = df['price'].shift(1)
        
        # Crossing UP an integer
        # condition: floor(prev) < floor(curr) ?? No.
        # Strict equality check is rare.
        # Crossing K: prev < K <= curr
        
        # Let's find all integer levels crossed
        # Iterate? No, vectorized.
        # We can detect ANY integer cross.
        # (int)prev != (int)curr
        
        df['int_price'] = df['price'].astype(int)
        df['prev_int'] = df['int_price'].shift(1)
        
        # Mask where integer part changed
        # We only care about Upward crosses for "Breaking the Wall"
        cross_mask = (df['int_price'] > df['prev_int'].fillna(df['int_price']))
        
        # Filter for relevant strikes?
        # Let's verify commonly traded strikes.
        # Getting all integer crosses is fine.
        
        cross_indices = df.index[cross_mask]
        
        events = []
        
        for idx in cross_indices:
            t_event = df.loc[idx, 'timestamp']
            p_event = df.loc[idx, 'price']
            barrier = np.floor(p_event) # The level crossed (e.g. 29.99 -> 30.01, barrier is 30)
            
            # Post-Event Window
            # 3 Seconds for Flow
            t_end_flow = t_event + pd.Timedelta(seconds=3)
            # 30 Seconds for Price Evaluation (Suppression)
            t_end_price = t_event + pd.Timedelta(seconds=30)
            
            # Slice
            # Optimization: slice small chunk
            future_chunk = df.iloc[idx : idx+20000] # should be enough
            
            flow_df = future_chunk[future_chunk['timestamp'] <= t_end_flow]
            price_df = future_chunk[future_chunk['timestamp'] <= t_end_price]
            
            if len(flow_df) == 0:
                continue
                
            net_vol = (flow_df['volume'] * flow_df['side']).sum()
            total_vol = flow_df['volume'].sum()
            
            # Outcome
            p_final = price_df.iloc[-1]['price']
            ret_30s = (p_final - p_event) / p_event
            
            events.append({
                "date": str(t_event.date()),
                "timestamp": str(t_event),
                "barrier": barrier,
                "net_vol_3s": int(net_vol),
                "total_vol_3s": int(total_vol),
                "ret_30s": ret_30s
            })
            
        return events
        
    except Exception as e:
        print(f"Error analyzing {filepath}: {e}")
        return []

def main():
    if not OUTPUT_DIR.exists():
        os.makedirs(OUTPUT_DIR)
        
    files = get_tick_files()
    print(f"Found {len(files)} daily files.")
    
    all_events = []
    
    for f in files:
        # Filter for relevant periods only (Control: Jan 2024, Event: May 2024)
        if "2024-01" in f or "2024-05" in f:
            events = analyze_file(f)
            all_events.extend(events)
        
    print(f"Total Events: {len(all_events)}")

    
    # Analysis
    # Definition of "Suppression":
    # Strong Net Buying (Top Quartile) -> Negative Price Return
    
    ev_df = pd.DataFrame(all_events)
    if ev_df.empty:
        print("No events found.")
        return
        
    # Filter for "Burst" events (Net Vol > 1000 shares?)
    # or top quantile
    threshold = ev_df['net_vol_3s'].quantile(0.90)
    print(f"Burst Threshold (Top 10% Net Buy): {threshold:.0f} shares")
    
    bursts = ev_df[ev_df['net_vol_3s'] > threshold].copy()
    
    # Check Price Drift
    bursts['is_suppressed'] = bursts['ret_30s'] < 0
    suppression_rate = bursts['is_suppressed'].mean()
    
    print(f"\n--- Expanded Barrier Study Results ---")
    print(f"Total Barrier Crossings: {len(ev_df)}")
    print(f"Buy Bursts Analyzed (Top 10%): {len(bursts)}")
    print(f"Suppressed (Price fell after Buy Burst): {bursts['is_suppressed'].sum()}")
    print(f"Suppression Rate: {suppression_rate:.2%}")
    print(f"Baseline (Random) Rate expectation: ~50%?")
    
    # Baseline
    # Rate of Price Drop for ALL events?
    baseline_drop = (ev_df['ret_30s'] < 0).mean()
    print(f"Baseline Drop Rate (All Crossings): {baseline_drop:.2%}")
    
    # Save
    ev_df.to_csv(OUTPUT_DIR / "expanded_barrier_events.csv", index=False)
    
    # Plot
    plt.figure(figsize=(10, 6))
    plt.scatter(bursts['net_vol_3s'], bursts['ret_30s'] * 100, alpha=0.5, c=bursts['is_suppressed'], cmap='RdYlGn_r')
    plt.axhline(0, color='black', linestyle='--')
    plt.title(f"Barrier Response: Net Flow vs 30s Return (Top 10% Bursts)\nSuppression Rate: {suppression_rate:.1%}")
    plt.xlabel("Net Buy Flow (3s) [Shares]")
    plt.ylabel("Price Return (30s) [%]")
    plt.savefig(OUTPUT_DIR / "expanded_barrier_scatter.png")
    
    # Save Summary
    summary = {
        "n_events": len(ev_df),
        "n_bursts": len(bursts),
        "suppression_rate": suppression_rate,
        "baseline_rate": baseline_drop
    }
    with open(OUTPUT_DIR / "expanded_study_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

if __name__ == "__main__":
    main()
