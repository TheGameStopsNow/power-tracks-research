#!/usr/bin/env python3
"""
Fine-Grained Hold Period Optimization
======================================

Tests hold periods from 1 to 30 days with fine granularity.
Also analyzes:
1. How much time you have to position (Entry Window Analysis)
2. True optimal hold period
3. Risk-adjusted returns across all periods
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
    """Detect if a burst occurred."""
    if len(df) < 100:
        return {"is_burst": False, "open": 0, "close": 0}
    
    mean_vol = df['volume'].mean()
    max_vol = df['volume'].max()
    volume_spike = max_vol / mean_vol if mean_vol > 0 else 0
    
    price_range = (df['high'].max() - df['low'].min()) / df['open'].iloc[0]
    
    is_burst = volume_spike > 2.5 and price_range > 0.03
    
    return {
        "is_burst": is_burst,
        "open": float(df['open'].iloc[0]),
        "close": float(df['close'].iloc[-1]),
        "high": float(df['high'].max()),
        "low": float(df['low'].min())
    }


def run_fine_grained_backtest(symbol_dir: Path, hold_days_list: list, transaction_cost: float = 0.001) -> dict:
    """
    Run backtest for multiple hold periods.
    """
    
    csv_files = sorted(symbol_dir.glob("*.csv"))
    if not csv_files:
        return {"error": "No data"}
    
    # Load all daily data
    daily_data = []
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            if 'close' not in df.columns:
                continue
            
            date_str = csv_file.stem.split("_")[1]
            burst_info = detect_burst_for_day(df)
            burst_info["date"] = date_str
            daily_data.append(burst_info)
        except:
            continue
    
    if not daily_data:
        return {"error": "No valid data"}
    
    df_daily = pd.DataFrame(daily_data)
    df_daily['date'] = pd.to_datetime(df_daily['date'])
    df_daily = df_daily.sort_values('date').reset_index(drop=True)
    
    # Results for each hold period
    results_by_period = {}
    
    for hold_days in hold_days_list:
        # Trading simulation
        trades = []
        position = None
        
        for i, row in df_daily.iterrows():
            # Check if we need to exit existing position
            if position is not None:
                days_held = (row['date'] - position['entry_date']).days
                if days_held >= hold_days:
                    # Exit position
                    exit_price = row['open']
                    gross_return = (exit_price / position['entry_price']) - 1
                    net_return = gross_return - (2 * transaction_cost)
                    
                    trades.append({
                        "entry_date": position['entry_date'],
                        "entry_price": position['entry_price'],
                        "exit_date": row['date'],
                        "exit_price": exit_price,
                        "days_held": days_held,
                        "gross_return": gross_return,
                        "net_return": net_return,
                        "win": net_return > 0
                    })
                    position = None
            
            # Check for new entry signal
            if position is None and row['is_burst']:
                position = {
                    "entry_date": row['date'],
                    "entry_price": row['close']
                }
        
        if not trades:
            results_by_period[hold_days] = {"error": "No trades"}
            continue
        
        # Calculate statistics
        trades_df = pd.DataFrame(trades)
        
        total_trades = len(trades_df)
        winning_trades = trades_df['win'].sum()
        win_rate = winning_trades / total_trades
        
        total_return = (1 + trades_df['net_return']).prod() - 1
        avg_return = trades_df['net_return'].mean()
        std_return = trades_df['net_return'].std()
        sharpe = (avg_return / std_return) * np.sqrt(252 / hold_days) if std_return > 0 else 0
        
        # Max drawdown
        cumulative = (1 + trades_df['net_return']).cumprod()
        rolling_max = cumulative.cummax()
        drawdowns = cumulative / rolling_max - 1
        max_drawdown = drawdowns.min()
        
        results_by_period[hold_days] = {
            "total_trades": total_trades,
            "winning_trades": int(winning_trades),
            "win_rate": float(win_rate),
            "total_return": float(total_return),
            "avg_return_per_trade": float(avg_return),
            "std_return": float(std_return),
            "sharpe_ratio": float(sharpe),
            "max_drawdown": float(max_drawdown)
        }
    
    return {
        "symbol": symbol_dir.name,
        "results": results_by_period
    }


def analyze_entry_window(symbol_dir: Path) -> dict:
    """
    Analyze how much time you have to position after first burst signal.
    """
    
    csv_files = sorted(symbol_dir.glob("*.csv"))
    if not csv_files:
        return None
    
    # Load all daily data
    daily_data = []
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            if 'close' not in df.columns:
                continue
            
            date_str = csv_file.stem.split("_")[1]
            burst_info = detect_burst_for_day(df)
            burst_info["date"] = date_str
            daily_data.append(burst_info)
        except:
            continue
    
    if not daily_data:
        return None
    
    df_daily = pd.DataFrame(daily_data)
    df_daily['date'] = pd.to_datetime(df_daily['date'])
    df_daily = df_daily.sort_values('date').reset_index(drop=True)
    
    # Find "Burst Regime" periods (consecutive burst days)
    df_daily['burst_streak'] = 0
    streak = 0
    for i, row in df_daily.iterrows():
        if row['is_burst']:
            streak += 1
        else:
            streak = 0
        df_daily.at[i, 'burst_streak'] = streak
    
    # Statistics
    max_streak = df_daily['burst_streak'].max()
    avg_streak = df_daily[df_daily['is_burst']]['burst_streak'].mean()
    
    # How often do you get 2+ days in a row?
    multi_day_bursts = (df_daily['burst_streak'] >= 2).sum()
    
    return {
        "max_consecutive_bursts": int(max_streak),
        "avg_burst_streak": float(avg_streak),
        "days_with_2plus_streak": int(multi_day_bursts),
        "percent_2plus": float(multi_day_bursts / len(df_daily))
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("FINE-GRAINED HOLD PERIOD OPTIMIZATION")
    print("=" * 70)
    
    if not EXPANDED_DIR.exists():
        print(f"No data at {EXPANDED_DIR}")
        return
    
    # Test GME with fine granularity
    gme_dir = EXPANDED_DIR / "GME"
    
    if not gme_dir.exists():
        print("GME data not found")
        return
    
    # Test hold periods: 1, 2, 3, ..., 30 days
    hold_periods = list(range(1, 31))
    
    print("\n>>> Running GME backtest for 1-30 day holds...")
    results = run_fine_grained_backtest(gme_dir, hold_periods)
    
    if "error" in results:
        print(f"Error: {results['error']}")
        return
    
    # Print results
    print("\n" + "=" * 70)
    print("RESULTS BY HOLD PERIOD")
    print("=" * 70)
    print(f"{'Hold':<5} | {'Trades':<6} | {'Win%':<6} | {'Return':<8} | {'Sharpe':<7} | {'MaxDD':<7}")
    print("-" * 70)
    
    for hold, res in sorted(results["results"].items()):
        if "error" not in res:
            print(f"{hold:<5} | {res['total_trades']:<6} | {res['win_rate']:.1%}  | "
                  f"{res['total_return']:>7.1%} | {res['sharpe_ratio']:>6.2f} | {res['max_drawdown']:>6.1%}")
    
    # Find optimal by different metrics
    valid_results = {k: v for k, v in results["results"].items() if "error" not in v}
    
    best_sharpe = max(valid_results.items(), key=lambda x: x[1]['sharpe_ratio'])
    best_return = max(valid_results.items(), key=lambda x: x[1]['total_return'])
    best_win_rate = max(valid_results.items(), key=lambda x: x[1]['win_rate'])
    
    print("\n" + "=" * 70)
    print("OPTIMAL HOLD PERIODS")
    print("=" * 70)
    print(f"Best Sharpe: {best_sharpe[0]} days (Sharpe={best_sharpe[1]['sharpe_ratio']:.2f})")
    print(f"Best Return: {best_return[0]} days (Return={best_return[1]['total_return']:.1%})")
    print(f"Best Win Rate: {best_win_rate[0]} days (WR={best_win_rate[1]['win_rate']:.1%})")
    
    # Entry Window Analysis
    print("\n" + "=" * 70)
    print("ENTRY WINDOW ANALYSIS")
    print("How much time do you have to position?")
    print("=" * 70)
    
    entry_analysis = analyze_entry_window(gme_dir)
    
    if entry_analysis:
        print(f"Max consecutive burst days: {entry_analysis['max_consecutive_bursts']}")
        print(f"Average burst streak: {entry_analysis['avg_burst_streak']:.1f} days")
        print(f"Days with 2+ consecutive bursts: {entry_analysis['days_with_2plus_streak']} ({entry_analysis['percent_2plus']:.1%})")
        print(f"\n>>> You typically have {entry_analysis['avg_burst_streak']:.1f} days to enter a position.")
    
    # Save results
    with open(OUTPUT_DIR / "hold_period_optimization.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "symbol": "GME",
            "results_by_period": results["results"],
            "optimal_sharpe": {"hold_days": best_sharpe[0], **best_sharpe[1]},
            "optimal_return": {"hold_days": best_return[0], **best_return[1]},
            "entry_window": entry_analysis
        }, f, indent=2, default=str)
    
    # Generate report
    with open(OUTPUT_DIR / "hold_period_report.md", "w") as f:
        f.write("# Hold Period Optimization\n\n")
        f.write("## Full Spectrum Analysis (1-30 days)\n\n")
        f.write("| Hold | Trades | Win Rate | Total Return | Sharpe | Max DD |\n")
        f.write("|------|--------|----------|--------------|--------|--------|\n")
        
        for hold, res in sorted(results["results"].items()):
            if "error" not in res:
                f.write(f"| {hold}d | {res['total_trades']} | {res['win_rate']:.1%} | "
                       f"{res['total_return']:.1%} | {res['sharpe_ratio']:.2f} | {res['max_drawdown']:.1%} |\n")
        
        f.write(f"\n## Optimal Strategies\n\n")
        f.write(f"- **Best Sharpe**: {best_sharpe[0]} days (Sharpe {best_sharpe[1]['sharpe_ratio']:.2f})\n")
        f.write(f"- **Best Return**: {best_return[0]} days (Return {best_return[1]['total_return']:.1%})\n")
        f.write(f"- **Best Win Rate**: {best_win_rate[0]} days (WR {best_win_rate[1]['win_rate']:.1%})\n")
        
        f.write(f"\n## Entry Window\n\n")
        f.write(f"- Average burst streak: **{entry_analysis['avg_burst_streak']:.1f} days**\n")
        f.write(f"- Max consecutive bursts: {entry_analysis['max_consecutive_bursts']} days\n")
        f.write(f"- You typically have {entry_analysis['avg_burst_streak']:.1f} days to enter after first signal\n")
    
    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
