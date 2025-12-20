#!/usr/bin/env python3
"""
Inspect 2-Day Strategy Trades
==============================

Deep dive into the specific trades that generate the 750% return claim.
"""

import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
EXPANDED_DIR = BASE_DIR / "data" / "expanded_bars"

def detect_burst_for_day(df: pd.DataFrame) -> dict:
    if len(df) < 100: return {"is_burst": False}
    
    mean_vol = df['volume'].mean()
    max_vol = df['volume'].max()
    volume_spike = max_vol / mean_vol if mean_vol > 0 else 0
    price_range = (df['high'].max() - df['low'].min()) / df['open'].iloc[0]
    is_burst = volume_spike > 2.5 and price_range > 0.03
    
    return {
        "is_burst": is_burst,
        "date": df['timestamp'].iloc[0].split(" ")[0] if 'timestamp' in df else "",
        "open": float(df['open'].iloc[0]),
        "close": float(df['close'].iloc[-1]),
    }

def run_inspection():
    gme_dir = EXPANDED_DIR / "GME"
    csv_files = sorted(gme_dir.glob("*.csv"))
    
    daily_data = []
    print("Loading data...")
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            if 'close' not in df.columns: continue
            
            # Extract date from filename if needed or use internal
            date_str = csv_file.stem.split("_")[1]
            burst_info = detect_burst_for_day(df)
            burst_info["date"] = date_str
            daily_data.append(burst_info)
        except: continue
        
    df = pd.DataFrame(daily_data)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    
    print(f"Loaded {len(df)} days: {df['date'].min().date()} to {df['date'].max().date()}")
    
    # 2-Day Hold Logic
    hold_days = 2
    trades = []
    position = None
    
    equity = 1.0
    equity_curve = []
    
    for i, row in df.iterrows():
        # Exit?
        if position:
            days_held = (row['date'] - position['entry_date']).days
            if days_held >= hold_days:
                exit_price = row['open']
                gross = (exit_price / position['entry_price']) - 1
                net = gross - 0.002 # Transaction cost
                
                # Compound equity
                equity *= (1 + net)
                
                trades.append({
                    "entry_date": position['entry_date'],
                    "entry_price": position['entry_price'],
                    "exit_date": row['date'],
                    "exit_price": exit_price,
                    "return": net,
                    "equity_after": equity
                })
                position = None
        
        # Enter?
        if position is None and row['is_burst']:
            position = {
                "entry_date": row['date'],
                "entry_price": row['close']
            }
            equity_curve.append({"date": row['date'], "equity": equity, "action": "buy"})
            
    df_trades = pd.DataFrame(trades)
    
    print("\n" + "="*50)
    print("TRADE INSPECTION (2-Day Sequential)")
    print("="*50)
    print(f"Total Trades: {len(df_trades)}")
    print(f"Final Equity: {equity:.2f}x (+{(equity-1)*100:.1f}%)")
    
    print("\n>>> TOP 10 WINNING TRADES")
    print(df_trades.sort_values("return", ascending=False).head(10)[['entry_date', 'exit_date', 'return', 'equity_after']].to_string())
    
    print("\n>>> TOP 10 LOSING TRADES")
    print(df_trades.sort_values("return", ascending=True).head(10)[['entry_date', 'exit_date', 'return', 'equity_after']].to_string())

    # Check for May 2024 run
    print("\n>>> May 2024 Performance")
    may_2024 = df_trades[(df_trades['entry_date'] >= '2024-05-01') & (df_trades['entry_date'] <= '2024-05-31')]
    if not may_2024.empty:
        print(may_2024[['entry_date', 'exit_date', 'return', 'equity_after']].to_string())
    else:
        print("No trades in May 2024")

if __name__ == "__main__":
    run_inspection()
