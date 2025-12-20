
import pandas as pd
import numpy as np
from pathlib import Path
import random

# Configuration
SIGNAL_LOG = Path("research/phase30_interconnectedness/signal_log.csv")
DATA_DIR = Path("data/ticks")
OUTPUT_STATS = Path("research/phase30_interconnectedness/impact_stats.md")

# Windows to measure return
WINDOWS_SEC = [1, 10, 60]

def load_tick_data(date, symbol):
    """Loads tick data for a specific date and symbol."""
    path = DATA_DIR / date / f"{symbol}.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
        df.sort_values("timestamp_us", inplace=True)
        return df
    except Exception:
        return None

def get_price_at_time(df, target_us):
    """Finds price at or immediately after target_us."""
    # Using searchsorted for speed
    idx = df['timestamp_us'].searchsorted(target_us)
    if idx < len(df):
        return df.iloc[idx]['price']
    return None

def calculate_returns(df, start_us, windows_sec):
    """Calculates % return for future windows."""
    start_price = get_price_at_time(df, start_us)
    if not start_price:
        return {w: np.nan for w in windows_sec}
        
    results = {}
    for w in windows_sec:
        target_us = start_us + (w * 1_000_000)
        future_price = get_price_at_time(df, target_us)
        if future_price:
            # Absolute percent return (volatility magnitude)
            # or Directional return? 
            # If 7-4-1 is a launch key, we expect directional UP? 
            # Or just volatility? Let's measure Absolute Return (Volatility) and Signed Return.
            ret = (future_price - start_price) / start_price
            results[w] = ret
        else:
            results[w] = np.nan
            
    return results

def main():
    if not SIGNAL_LOG.exists():
        print("Signal log not found.")
        return

    signals = pd.read_csv(SIGNAL_LOG)
    
    # We need to process by (Date, Symbol) to avoid reloading heavy CSVs repeatedly
    # But actually, we need to load the *target* symbol for cross-impact.
    
    # Let's focus on SELF-IMPACT first: Does GME signal predict GME price?
    # And CROSS-IMPACT: Does GME signal predict KOSS price?
    
    impact_data = []
    
    # Group signals by Date
    for date, group in signals.groupby("date"):
        print(f"Processing Impact for {date}...")
        
        # Cache tick data for this date
        tick_cache = {}
        
        # Get unique symbols in this date's data folder
        available_syms = [f.stem for f in (DATA_DIR / date).glob("*.csv")]
        
        # Load all relevant tick data into memory (might be heavy, strict optimization needed if > 16GB RAM)
        # Using a lazy load approach
        
        for idx, row in group.iterrows():
            trigger_sym = row['symbol']
            trigger_ts = row['timestamp_us']
            
            # 1. Self-Impact
            if trigger_sym not in tick_cache:
                 tick_cache[trigger_sym] = load_tick_data(date, trigger_sym)
                 
            if tick_cache[trigger_sym] is not None:
                rets = calculate_returns(tick_cache[trigger_sym], trigger_ts, WINDOWS_SEC)
                for w, r in rets.items():
                    impact_data.append({
                        "type": "SELF",
                        "trigger": trigger_sym,
                        "target": trigger_sym,
                        "window_sec": w,
                        "return": r,
                        "is_signal": True
                    })
            
            # 2. Random Baseline (Null Hypothesis)
            # Pick a random time in the same day for comparison
            # We want to compare Signal vs Random noise
            if tick_cache[trigger_sym] is not None:
                random_ts = random.randint(tick_cache[trigger_sym]['timestamp_us'].min(), tick_cache[trigger_sym]['timestamp_us'].max())
                rand_rets = calculate_returns(tick_cache[trigger_sym], random_ts, WINDOWS_SEC)
                for w, r in rand_rets.items():
                    impact_data.append({
                        "type": "SELF",
                        "trigger": trigger_sym,
                        "target": trigger_sym,
                        "window_sec": w,
                        "return": r,
                        "is_signal": False # Baseline
                    })

            # 3. Cross-Impact (GME -> KOSS)
            # Only if trigger is GME
            if trigger_sym == "GME":
                target = "KOSS"
                if target in available_syms:
                    if target not in tick_cache:
                        tick_cache[target] = load_tick_data(date, target)
                        
                    if tick_cache[target] is not None:
                        rets = calculate_returns(tick_cache[target], trigger_ts, WINDOWS_SEC)
                        for w, r in rets.items():
                            impact_data.append({
                                "type": "CROSS",
                                "trigger": "GME",
                                "target": target,
                                "window_sec": w,
                                "return": r,
                                "is_signal": True
                            })
                            
                        # Baseline for cross
                        random_ts = random.randint(tick_cache[target]['timestamp_us'].min(), tick_cache[target]['timestamp_us'].max())
                        rand_rets = calculate_returns(tick_cache[target], random_ts, WINDOWS_SEC)
                        for w, r in rand_rets.items():
                            impact_data.append({
                                "type": "CROSS",
                                "trigger": "GME",
                                "target": target,
                                "window_sec": w,
                                "return": r,
                                "is_signal": False
                            })

    # Compile Stats
    df_res = pd.DataFrame(impact_data)
    
    # Save Raw Data for Significance Testing
    RAW_OUTPUT = Path("research/phase30_interconnectedness/impact_raw_returns.csv")
    df_res.to_csv(RAW_OUTPUT, index=False)
    print(f"Saved raw returns to {RAW_OUTPUT}")
    
    # We want to see if Signal Return > Random Return (statistically significant)
    # Group by [Type, Trigger, Target, Window, IsSignal]
    
    summary = df_res.groupby(['type', 'trigger', 'target', 'window_sec', 'is_signal'])['return'].describe()
    
    print(summary)
    
    with open(OUTPUT_STATS, "w") as f:
        f.write("# Signal Impact Analysis\n\n")
        f.write("Comparing returns after verified signals vs random baseline.\n\n")
        
        f.write("## Summary Statistics\n")
        f.write("```\n")
        f.write(summary.to_string())
        f.write("\n```\n")
        
        # Calculate Alpha (Signal Mean - Baseline Mean)
        f.write("\n## Alpha (Predictive Power)\n")
        pivot = df_res.pivot_table(index=['type', 'trigger', 'target', 'window_sec'], columns='is_signal', values='return', aggfunc='mean')
        pivot.rename(columns={False: "Baseline_Mean", True: "Signal_Mean"}, inplace=True)
        pivot['Alpha'] = pivot['Signal_Mean'] - pivot['Baseline_Mean']
        pivot['Alpha_x_10000'] = pivot['Alpha'] * 10000 # Basis points
        
        f.write("```\n")
        f.write(pivot.to_string())
        f.write("\n```\n")

if __name__ == "__main__":
    main()
