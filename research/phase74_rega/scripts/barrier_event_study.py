import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import json

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
INPUT_FILE = BASE_DIR / "data/samples/sample_2024-05-17/raw_ticks/GME_2024-05-17_trades.csv"
OUTPUT_DIR = BASE_DIR / "research/phase74_rega/results"

BARRIER_LEVEL = 32.00
WINDOW_SECONDS = 3

def load_data():
    print(f"Loading {INPUT_FILE}...")
    df = pd.read_csv(INPUT_FILE)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

def classify_side(df):
    """
    Simple tick test: 
    Price > Prev -> Buy (1)
    Price < Prev -> Sell (-1)
    Price == Prev -> 0 (or continuation of last side - naive approach: 0)
    """
    df['delta'] = df['price'].diff()
    # Fill na
    df['side'] = np.sign(df['delta']).fillna(0)
    # Forward fill 0s? Conventional tick test does.
    # But for "Net Burst", maybe just explicit moves matter?
    # Let's simple-check: User saw "40k NET shares".
    # This implies aggressive buying.
    # We will use explicit side 1/-1.
    return df

def find_crossings(df):
    # Find indices where Price crosses BARRIER_LEVEL from below
    # cond: (prev_price < 32) & (curr_price >= 32)
    
    # Shift approach is slow on 1M rows? No, it's fast.
    prev_price = df['price'].shift(1)
    
    # Crossing UP
    crossing_mask = (prev_price < BARRIER_LEVEL) & (df['price'] >= BARRIER_LEVEL)
    cross_indices = df.index[crossing_mask]
    
    events = []
    
    print(f"Found {len(cross_indices)} potential barrier crossings.")
    
    for idx in cross_indices:
        t_event = df.loc[idx, 'timestamp']
        p_event = df.loc[idx, 'price']
        
        # Debounce?
        # If we crossed 1 sec ago, ignore?
        # Let's capture all, then see if they cluster.
        
        # Define window [t, t + 3s]
        t_end = t_event + pd.Timedelta(seconds=WINDOW_SECONDS)
        
        # Slice window
        # Mask is efficient if df is time-sorted (it is)
        # But iterating 1M rows is slow if we do it stupidly.
        # We can use searchsorted? df is sorted by index?
        # Assuming sorted by timestamp. The csv looked sorted.
        
        # Simple slice using timestamp index would be best but we have RangeIndex.
        # Let's filter:
        # Optimization: Don't scan WHOLE df. Scan from idx forward.
        # Or just use boolean mask on valid range if total events is small.
        # If 100 events, full scan is 100 * 1M ops = 100M. Python handles 100M bools in seconds.
        # But "df['timestamp'] <= t_end" is slow if done 100 times.
        # Let's assume idx is close.
        # Just searching forward 10000 rows is enough for 3 seconds usually.
        
        # Dynamic slice
        # Max ticks in 3s? 
        # GME 2024-05-17 was huge volume. 
        # Rows 1-800 covered 8:00:00 to 8:01:01 (1 min = 800 rows).
        # Actually line 800 is 08:01:01.
        # So 3 seconds is ~40 rows?
        # Wait, that's pre-market. 
        # In market hours, it could be thousands.
        # Let's just slice df[idx : idx+5000] and filter by time.
        
        future_chunk = df.iloc[idx : idx+10000]
        window_df = future_chunk[future_chunk['timestamp'] <= t_end]
        
        total_vol = window_df['volume'].sum()
        
        # Net Vol: sum(volume * side)
        net_vol = (window_df['volume'] * window_df['side']).sum()
        
        # Price change
        p_final = window_df['price'].iloc[-1]
        
        events.append({
            "timestamp": str(t_event),
            "cross_price": p_event,
            "final_price": p_final,
            "total_volume": int(total_vol),
            "net_volume": int(net_vol),
            "n_ticks": len(window_df)
        })
        
    return events

def main():
    if not OUTPUT_DIR.exists():
        os.makedirs(OUTPUT_DIR)
        
    df = load_data()
    df = classify_side(df)
    
    events = find_crossings(df)
    
    # Save
    with open(OUTPUT_DIR / "barrier_events.json", "w") as f:
        json.dump(events, f, indent=2)
        
    print(f"Saved {len(events)} events to {OUTPUT_DIR}/barrier_events.json")
    
    # Print the "Big One" if it exists
    # Look for max Net Volume
    if events:
        max_event = max(events, key=lambda x: x['net_volume'])
        print("\n--- Largest Barrier Response ---")
        print(f"Time: {max_event['timestamp']}")
        print(f"Net Vol (3s): {max_event['net_volume']}")
        print(f"Total Vol (3s): {max_event['total_volume']}")
        print(f"Price Move: {max_event['cross_price']} -> {max_event['final_price']}")

if __name__ == "__main__":
    main()
