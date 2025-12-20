#!/usr/bin/env python3
"""
Sequential Hold Period Optimization (Corrected)
================================================

Tests specific hold periods with unrealistic compounding REMOVED.
Strict Rule: You cannot enter a new trade if you are already in one.
"""

import sys
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
EXPANDED_DIR = BASE_DIR / "data" / "expanded_bars"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "results"

def detect_burst_for_day(df: pd.DataFrame) -> dict:
    if len(df) < 100: return {"is_burst": False}
    
    mean_vol = df['volume'].mean()
    max_vol = df['volume'].max()
    volume_spike = max_vol / mean_vol if mean_vol > 0 else 0
    price_range = (df['high'].max() - df['low'].min()) / df['open'].iloc[0]
    
    is_burst = volume_spike > 2.5 and price_range > 0.03
    
    return {
        "is_burst": is_burst,
        "open": float(df['open'].iloc[0]),
        "close": float(df['close'].iloc[-1]),
    }

def run_sequential_backtest(symbol_dir: Path, hold_days_list: list) -> dict:
    csv_files = sorted(symbol_dir.glob("*.csv"))
    if not csv_files: return {"error": "No data"}
    
    # Load daily sequence
    daily_data = []
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            if 'close' not in df.columns: continue
            date_str = csv_file.stem.split("_")[1]
            burst_info = detect_burst_for_day(df)
            burst_info["date"] = date_str
            daily_data.append(burst_info)
        except: continue
        
    df_daily = pd.DataFrame(daily_data)
    df_daily['date'] = pd.to_datetime(df_daily['date'])
    df_daily = df_daily.sort_values('date').reset_index(drop=True)
    
    results = {}
    
    for hold_days in hold_days_list:
        trades = []
        position = None
        
        # State machine for single-slot portfolio
        for i, row in df_daily.iterrows():
            
            # 1. Manage existing position
            if position:
                days_held = (row['date'] - position['entry_date']).days
                
                # Exit condition
                if days_held >= hold_days:
                    exit_price = row['open']
                    # Cost: 0.1% entry, 0.1% exit
                    gross = (exit_price / position['entry_price']) - 1
                    net = gross - 0.002 
                    
                    trades.append({
                        "entry": position['entry_date'],
                        "exit": row['date'],
                        "return": net
                    })
                    position = None
            
            # 2. Check for entry (ONLY if flat)
            if position is None and row['is_burst']:
                position = {
                    "entry_date": row['date'],
                    "entry_price": row['close']
                }
                
        # Calculate stats
        if not trades:
            results[hold_days] = {"return": 0.0, "trades": 0}
            continue
            
        returns = [t['return'] for t in trades]
        total_return = np.prod([1 + r for r in returns]) - 1
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252/hold_days) if len(returns) > 1 else 0
        
        results[hold_days] = {
            "total_return": total_return,
            "trades": len(trades),
            "win_rate": np.mean([r > 0 for r in returns]),
            "sharpe": sharpe
        }
        
    return {"symbol": symbol_dir.name, "results": results}

def main():
    print("Running SEQUENTIAL backtest (No compounding of overlaps)...")
    sym_dir = EXPANDED_DIR / "GME"
    res = run_sequential_backtest(sym_dir, list(range(1, 21)))
    
    print(f"\n{'Hold':<5} | {'Trades':<6} | {'return':<8} | {'Sharpe':<6}")
    print("-" * 40)
    for h, r in sorted(res['results'].items()):
        print(f"{h:<5} | {r['trades']:<6} | {r['total_return']:>7.1%} | {r['sharpe']:>6.2f}")

if __name__ == "__main__":
    main()
