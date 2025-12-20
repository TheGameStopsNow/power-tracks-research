#!/usr/bin/env python3
"""
Tradability Backtest
=====================

Tests if burst detection leads to tradable signals:
1. Simple strategy: Enter at burst detection, exit after N days
2. Calculate returns, Sharpe ratio, max drawdown
3. Compare to buy-and-hold
4. Factor in realistic transaction costs
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
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
        "low": float(df['low'].min()),
        "volume": float(df['volume'].sum())
    }


def run_backtest(symbol_dir: Path, hold_days: int = 5, transaction_cost: float = 0.001) -> dict:
    """
    Simple backtest: Buy on burst signal, hold for N days, sell.
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
    
    # Trading simulation
    trades = []
    position = None
    
    for i, row in df_daily.iterrows():
        # Check if we need to exit existing position
        if position is not None:
            days_held = (row['date'] - position['entry_date']).days
            if days_held >= hold_days:
                # Exit position
                exit_price = row['open']  # Exit at next day open
                gross_return = (exit_price / position['entry_price']) - 1
                net_return = gross_return - (2 * transaction_cost)  # Entry + exit costs
                
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
                "entry_price": row['close']  # Enter at burst day close
            }
    
    if not trades:
        return {
            "symbol": symbol_dir.name,
            "hold_days": hold_days,
            "error": "No trades generated"
        }
    
    # Calculate statistics
    trades_df = pd.DataFrame(trades)
    
    # Basic metrics
    total_trades = len(trades_df)
    winning_trades = trades_df['win'].sum()
    win_rate = winning_trades / total_trades
    
    # Return metrics
    total_return = (1 + trades_df['net_return']).prod() - 1
    avg_return = trades_df['net_return'].mean()
    std_return = trades_df['net_return'].std()
    sharpe = (avg_return / std_return) * np.sqrt(252 / hold_days) if std_return > 0 else 0
    
    # Max drawdown (simplified)
    cumulative = (1 + trades_df['net_return']).cumprod()
    rolling_max = cumulative.cummax()
    drawdowns = cumulative / rolling_max - 1
    max_drawdown = drawdowns.min()
    
    # Buy and hold comparison
    first_price = df_daily['open'].iloc[0]
    last_price = df_daily['close'].iloc[-1]
    buy_hold_return = (last_price / first_price) - 1
    
    # Calculate days in market
    total_days_in_market = trades_df['days_held'].sum()
    total_days = (df_daily['date'].iloc[-1] - df_daily['date'].iloc[0]).days
    time_in_market = total_days_in_market / total_days if total_days > 0 else 0
    
    return {
        "symbol": symbol_dir.name,
        "hold_days": hold_days,
        "total_trades": total_trades,
        "winning_trades": int(winning_trades),
        "win_rate": float(win_rate),
        "total_return": float(total_return),
        "avg_return_per_trade": float(avg_return),
        "std_return": float(std_return),
        "sharpe_ratio": float(sharpe),
        "max_drawdown": float(max_drawdown),
        "buy_hold_return": float(buy_hold_return),
        "time_in_market": float(time_in_market),
        "alpha": float(total_return - buy_hold_return * time_in_market),
        "trades": trades  # Raw trade data
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("TRADABILITY BACKTEST")
    print("Testing if burst signals are profitable")
    print("=" * 70)
    
    if not EXPANDED_DIR.exists():
        print(f"No data at {EXPANDED_DIR}")
        return
    
    symbol_dirs = [d for d in EXPANDED_DIR.iterdir() if d.is_dir()]
    
    if not symbol_dirs:
        print("No symbol data found")
        return
    
    # Test multiple hold periods
    hold_periods = [1, 3, 5, 10, 20]
    
    all_results = {}
    
    for symbol_dir in sorted(symbol_dirs):
        print(f"\n>>> {symbol_dir.name}")
        
        symbol_results = {}
        for hold_days in hold_periods:
            result = run_backtest(symbol_dir, hold_days=hold_days)
            symbol_results[hold_days] = result
            
            if "error" not in result:
                print(f"  {hold_days}-day hold: {result['total_trades']} trades, "
                      f"WR={result['win_rate']:.1%}, "
                      f"Return={result['total_return']:.1%}, "
                      f"Sharpe={result['sharpe_ratio']:.2f}")
        
        all_results[symbol_dir.name] = symbol_results
    
    # Find best strategy
    print("\n" + "=" * 70)
    print("BEST STRATEGIES")
    print("=" * 70)
    
    best_by_sharpe = []
    for symbol, periods in all_results.items():
        for hold_days, result in periods.items():
            if "error" not in result and result.get("sharpe_ratio", 0) > 0:
                best_by_sharpe.append({
                    "symbol": symbol,
                    "hold_days": hold_days,
                    "sharpe": result["sharpe_ratio"],
                    "return": result["total_return"],
                    "win_rate": result["win_rate"],
                    "trades": result["total_trades"]
                })
    
    if best_by_sharpe:
        best_by_sharpe.sort(key=lambda x: x["sharpe"], reverse=True)
        print("\nTop 10 by Sharpe Ratio:")
        for i, strat in enumerate(best_by_sharpe[:10], 1):
            print(f"  {i}. {strat['symbol']} {strat['hold_days']}-day: "
                  f"Sharpe={strat['sharpe']:.2f}, Return={strat['return']:.1%}, "
                  f"WR={strat['win_rate']:.1%}, N={strat['trades']}")
    
    # Save results
    # Convert to JSON-serializable format
    json_results = {}
    for symbol, periods in all_results.items():
        json_results[symbol] = {}
        for hold_days, result in periods.items():
            # Remove raw trades data for JSON
            result_clean = {k: v for k, v in result.items() if k != 'trades'}
            json_results[symbol][str(hold_days)] = result_clean
    
    with open(OUTPUT_DIR / "tradability_backtest.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": json_results,
            "best_strategies": best_by_sharpe[:10] if best_by_sharpe else []
        }, f, indent=2, default=str)
    
    # Generate report
    with open(OUTPUT_DIR / "tradability_report.md", "w") as f:
        f.write("# Tradability Backtest\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Strategy\n\n")
        f.write("- **Entry**: Buy at close of burst detection day\n")
        f.write("- **Exit**: Sell at open after N days\n")
        f.write("- **Transaction cost**: 0.1% per trade (round trip: 0.2%)\n\n")
        
        f.write("## Results Summary\n\n")
        f.write("| Symbol | Hold | Trades | Win Rate | Return | Sharpe | Max DD |\n")
        f.write("|--------|------|--------|----------|--------|--------|--------|\n")
        
        for strat in best_by_sharpe[:15]:
            symbol = strat['symbol']
            hold_days = strat['hold_days']
            result = all_results[symbol][hold_days]
            f.write(f"| {symbol} | {hold_days}d | {result['total_trades']} ")
            f.write(f"| {result['win_rate']:.1%} | {result['total_return']:.1%} ")
            f.write(f"| {result['sharpe_ratio']:.2f} | {result['max_drawdown']:.1%} |\n")
        
        f.write("\n## Key Findings\n\n")
        if best_by_sharpe:
            best = best_by_sharpe[0]
            f.write(f"- **Best strategy**: {best['symbol']} with {best['hold_days']}-day hold\n")
            f.write(f"- **Sharpe ratio**: {best['sharpe']:.2f}\n")
            f.write(f"- **Total return**: {best['return']:.1%}\n")
            f.write(f"- **Win rate**: {best['win_rate']:.1%}\n")
    
    print("\n" + "=" * 70)
    print("BACKTEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
