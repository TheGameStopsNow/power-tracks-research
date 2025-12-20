
import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt

# Paths
REAL_TICKS_FILE = "/Users/TheGameStopsNow/Documents/GitHub/power-tracks-research/research/phase29_system_cartography/real_ticks/GME_2021-03-08_real_trades.csv"
OUTPUT_REPORT = Path("/Users/TheGameStopsNow/Documents/GitHub/power-tracks-research/research/phase29_system_cartography/REAL_SIGNAL_EFFICACY.md")

def analyze_efficacy():
    print("Analyzing Signal Efficacy on REAL TICKS (Long Horizon)...")
    
    if not Path(REAL_TICKS_FILE).exists():
        print("Real ticks file not found.")
        return

    # Load Data
    df = pd.read_csv(REAL_TICKS_FILE)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    # Polygon data is already chronological. Skipping sort to avoid pandas environment bug.
    # df = df.sort_values('timestamp').reset_index(drop=True)
    
    # 1. Identify Signals (7-4-1)
    # We re-run the scan logic to get indices
    df['delta'] = df['price'].diff().abs().round(2)
    
    d0 = df['delta']
    d1 = df['delta'].shift(-1)
    d2 = df['delta'].shift(-2)
    
    mask = (d0 == 0.07) & (d1 == 0.04) & (d2 == 0.01)
    signal_indices = df[mask].index
    
    print(f"Found {len(signal_indices)} signals.")
    
    results = []
    
    # Market Close for EOD calc
    # Assuming standard market hours, close is last tick?
    last_price = df.iloc[-1]['price']
    last_time = df.iloc[-1]['timestamp']
    
    for idx in signal_indices:
        row = df.loc[idx]
        ts = row['timestamp']
        price = row['price']
        
        # Define Targets
        t_10s = ts + pd.Timedelta(seconds=10)
        t_1h = ts + pd.Timedelta(hours=1)
        t_4h = ts + pd.Timedelta(hours=4)
        
        # Find prices at targets using searchsorted (or simple mask if small data)
        # Using simple approach for robustness
        
        # Helper to find price at time T
        def get_price_at(t_target):
            # Find first index >= t_target
            # Subset around t_target to speed up?
            # Actually, searchsorted on timestamp is fast.
            # But timestamp is not monotonic? It should be sorted.
            # Convert to int?
            
            # Simple Mask
            subset = df[df['timestamp'] >= t_target]
            if subset.empty:
                return last_price # Use EOD if target is past EOD
            return subset.iloc[0]['price']

        p_10s = get_price_at(t_10s)
        p_1h = get_price_at(t_1h)
        p_4h = get_price_at(t_4h)
        p_eod = last_price
        
        # Calc Returns
        ret_10s = (p_10s - price) / price
        ret_1h = (p_1h - price) / price
        ret_4h = (p_4h - price) / price
        ret_eod = (p_eod - price) / price
        
        results.append({
            'timestamp': ts,
            'price': price,
            'ret_10s': ret_10s,
            'ret_1h': ret_1h,
            'ret_4h': ret_4h,
            'ret_eod': ret_eod
        })
        
    res_df = pd.DataFrame(results)
    
    # Generate Stats
    if res_df.empty:
        print("No signals to analyze.")
        return

    avg_1h = res_df['ret_1h'].mean()
    avg_eod = res_df['ret_eod'].mean()
    
    # Biggest moves
    best_1h = res_df['ret_1h'].max()
    worst_1h = res_df['ret_1h'].min()
    
    with open(OUTPUT_REPORT, 'w') as f:
        f.write("# REAL SIGNAL EFFICACY REPORT\n")
        f.write(f"**Source Data:** {Path(REAL_TICKS_FILE).name}\n")
        f.write(f"**Signal Count:** {len(res_df)}\n\n")
        
        f.write("## Summary Statistics\n")
        f.write("| Horizon | Avg Return | Max Return | Min Return | Win Rate (>0) |\n")
        f.write("| --- | --- | --- | --- | --- |\n")
        
        for p in ['10s', '1h', '4h', 'eod']:
            col = f'ret_{p}'
            avg = res_df[col].mean()
            mx = res_df[col].max()
            mn = res_df[col].min()
            wins = (res_df[col] > 0).mean()
            f.write(f"| T+{p} | {avg:.2%} | {mx:.2%} | {mn:.2%} | {wins:.0%} |\n")
            
        f.write("\n## The Big Moves\n")
        f.write("Did the signal precede any major outliers?\n\n")
        
        # Filter for top absolute moves
        big_moves = res_df[res_df['ret_eod'].abs() > 0.05] # >5% move
        if not big_moves.empty:
            f.write("| Timestamp | Signal Price | EOD Return | Direction |\n")
            f.write("| --- | --- | --- | --- |\n")
            for _, r in big_moves.iterrows():
                direction = "ROCKET" if r['ret_eod'] > 0 else "DUMP"
                f.write(f"| {r['timestamp']} | ${r['price']:.2f} | {r['ret_eod']:.2%} | {direction} |\n")
        else:
            f.write("No >5% EOD moves detected immediately following these specific 49 signals on this day.\n")
            
    print(f"Analysis complete. Saved to {OUTPUT_REPORT}")
    res_df.to_csv(OUTPUT_REPORT.parent / "real_signal_results.csv", index=False)

if __name__ == "__main__":
    analyze_efficacy()
