
import pandas as pd
from pathlib import Path
import matplotlib.pyplot as plt

# Paths
PHASE_DIR = Path(__file__).resolve().parent.parent
# Note: This assumes GME_... file is in real_ticks. Use standard if possible.
REAL_TICKS_FILE = PHASE_DIR / "real_ticks" / "GME_2021-03-08_real_trades.csv"
OUTPUT_REPORT = PHASE_DIR / "output" / "REVERSE_SIGNAL_147.md"

def analyze_reverse_signal():
    print("Scanning for REVERSE SIGNAL (1-4-7) on Real Ticks...")
    
    if not Path(REAL_TICKS_FILE).exists():
        print("Real ticks file not found.")
        return

    # Load Data
    df = pd.read_csv(REAL_TICKS_FILE)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    # Polygon sorted check
    # df = df.sort_values('timestamp').reset_index(drop=True)
    
    # 1. Identify Reverse Signals (0.01 -> 0.04 -> 0.07)
    df['delta'] = df['price'].diff().abs().round(2)
    
    d0 = df['delta']
    d1 = df['delta'].shift(-1)
    d2 = df['delta'].shift(-2)
    
    # 1 -> 4 -> 7
    mask = (d0 == 0.01) & (d1 == 0.04) & (d2 == 0.07)
    signal_indices = df[mask].index
    
    print(f"Found {len(signal_indices)} REVERSE signals (1-4-7).")
    
    results = []
    
    # Market Close
    last_price = df.iloc[-1]['price']
    
    for idx in signal_indices:
        row = df.loc[idx]
        ts = row['timestamp']
        price = row['price']
        
        # Define Targets
        t_10s = ts + pd.Timedelta(seconds=10)
        t_1h = ts + pd.Timedelta(hours=1)
        t_4h = ts + pd.Timedelta(hours=4)
        
        # Helper (same as before)
        def get_price_at(t_target):
            subset = df[df['timestamp'] >= t_target]
            if subset.empty: return last_price
            return subset.iloc[0]['price']

        p_10s = get_price_at(t_10s)
        p_1h = get_price_at(t_1h)
        p_eod = last_price
        
        results.append({
            'timestamp': ts,
            'price': price,
            'ret_10s': (p_10s - price) / price,
            'ret_1h': (p_1h - price) / price,
            'ret_eod': (p_eod - price) / price
        })
        
    res_df = pd.DataFrame(results)
    
    with open(OUTPUT_REPORT, 'w') as f:
        f.write("# REVERSE SIGNAL (1-4-7) ANALYSIS\n")
        f.write(f"**Hypothesis:** If 7-4-1 starts the run, does 1-4-7 end it?\n")
        f.write(f"**Signal Count:** {len(res_df)}\n\n")
        
        if res_df.empty:
            f.write("No signals found.\n")
        else:
            f.write("## Summary Statistics\n")
            f.write("| Horizon | Avg Return | Min Return | Win Rate (Short) |\n")
            f.write("| --- | --- | --- | --- |\n")
            
            for p in ['10s', '1h', 'eod']:
                col = f'ret_{p}'
                avg = res_df[col].mean()
                mn = res_df[col].min()
                # For a "Top" signal, we want NEGATIVE returns. 
                # "Win Rate (Short)" = % of times return is negative
                wins = (res_df[col] < 0).mean()
                f.write(f"| T+{p} | {avg:.2%} | {mn:.2%} | {wins:.0%} |\n")
                
            f.write("\n## Signal Examples\n")
            f.write("| Timestamp | Price | 1h Return | EOD Return |\n")
            f.write("| --- | --- | --- | --- |\n")
            for _, r in res_df.head(10).iterrows():
                f.write(f"| {r['timestamp']} | ${r['price']:.2f} | {r['ret_1h']:.2%} | {r['ret_eod']:.2%} |\n")

    print(f"Analysis complete. Saved to {OUTPUT_REPORT}")

if __name__ == "__main__":
    analyze_reverse_signal()
