#!/usr/bin/env python3
"""
Phase 30F: Seed Strategy Backtester
Strategy: "Short the Seed"
Trigger: 0xDF Opcode detection in GME.
Action: Short SPY at Close of trigger minute (or Open of next).
Exit: Close position 30 minutes later.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import warnings

warnings.filterwarnings('ignore')

# Configuration
DATA_DIR = Path("data/ticks")
OUTPUT_FILE = Path("research/phase30_interconnectedness/seed_strategy_results.csv")
EXCHANGE_EDGX = 4

# Target Dates (High 0xDF count)
SEED_DAYS = [
    "2025-01-06", "2025-06-11", "2025-01-02", "2025-01-07"
]

def load_data(date, symbol):
    path = DATA_DIR / date / f"{symbol}.csv"
    if not path.exists(): return None
    try:
        df = pd.read_csv(path, usecols=['timestamp_us', 'price', 'exchange'])
        df['timestamp_us'] = pd.to_numeric(df['timestamp_us'], errors='coerce')
        df.dropna(subset=['timestamp_us'], inplace=True)
        if df.empty: return None
        if len(df) > 1 and df['timestamp_us'].iloc[0] > df['timestamp_us'].iloc[-1]:
            df = df.iloc[::-1]
        df['datetime'] = pd.to_datetime(df['timestamp_us'], unit='us')
        df.set_index('datetime', inplace=True)
        return df
    except:
        return None

def extract_seed_times(gme_df):
    edgx = gme_df[gme_df['exchange'] == EXCHANGE_EDGX]
    if edgx.empty: return []
    
    prices = edgx['price'].values
    lsbs = ((prices * 100).round().astype(int) & 1)
    
    timestamps = edgx.index
    seeds = []
    
    for i in range(0, len(lsbs)-7, 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | lsbs[i+j]
        if byte == 0xDF:
            seeds.append(timestamps[i+7])
            
    return seeds

def backtest_day(date):
    gme_df = load_data(date, "GME")
    spy_df = load_data(date, "SPY")
    
    if gme_df is None or spy_df is None: return []
    
    # Get Signals
    seeds = extract_seed_times(gme_df)
    if not seeds: return []
    
    # Resample SPY to 1-min for easier execution simulation
    spy_1min = spy_df['price'].resample('1min').ohlc().dropna()
    
    trades = []
    holding_period = 30 # minutes
    
    # Simple logic: Unique signals only (don't stack if already short? or stack?)
    # Let's stack for now (every seed triggers a trade) to see raw power
    
    for seed_time in seeds:
        # Find entry candle (next minute open)
        try:
            # Round seed time to minute ceiling
            entry_time = seed_time.ceil('1min')
            
            if entry_time not in spy_1min.index:
                # Find nearest future
                future_candles = spy_1min[spy_1min.index >= entry_time]
                if future_candles.empty: continue
                entry_time = future_candles.index[0]
                
            entry_price = spy_1min.loc[entry_time]['open']
            
            # Find exit time
            exit_time = entry_time + pd.Timedelta(minutes=holding_period)
            
            # Find closest candle to exit time
            # (If exact match missing, use next available or last of day)
            possible_exits = spy_1min[spy_1min.index >= exit_time]
            if not possible_exits.empty:
                true_exit_time = possible_exits.index[0]
                exit_price = spy_1min.loc[true_exit_time]['open'] # Exit at open of that candle
            else:
                # Exit at EOD
                true_exit_time = spy_1min.index[-1]
                exit_price = spy_1min.iloc[-1]['close']
                
            # Short Trade
            pnl_pct = (entry_price - exit_price) / entry_price * 100
            
            trades.append({
                'date': date,
                'signal_time': seed_time,
                'entry_time': entry_time,
                'entry_price': entry_price,
                'exit_time': true_exit_time,
                'exit_price': exit_price,
                'pnl_pct': pnl_pct
            })
            
        except Exception as e:
            continue
            
    return trades

def main():
    print("PHASE 30F: SEED STRATEGY BACKTEST")
    print("================================")
    
    all_trades = []
    
    for date in SEED_DAYS:
        print(f"Backtesting {date}...")
        trades = backtest_day(date)
        all_trades.extend(trades)
        
    if not all_trades:
        print("No trades generated.")
        return
        
    df = pd.DataFrame(all_trades)
    
    print("\nPERFORMANCE SUMMARY:")
    print(f"Total Trades: {len(df)}")
    print(f"Win Rate: {(df['pnl_pct'] > 0).mean()*100:.2f}%")
    print(f"Avg PnL per Trade: {df['pnl_pct'].mean():.4f}%")
    print(f"Total Return (Unlevered): {df['pnl_pct'].sum():.2f}%")
    
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\nTrade log saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
