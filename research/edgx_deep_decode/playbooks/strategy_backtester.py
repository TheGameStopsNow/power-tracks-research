#!/usr/bin/env python3
"""
Strategy Backtester
===================

Simulates trading execution based on signals from the Live Decoder.

Strategies:
1. The Bounce:
   - Entry: 0xA0 (Hard Floor) signal detected.
   - Confirmation: Next tick price > Floor Price (basic bounce).
   - Exit: Fixed profit target (1.5%) or Stop Loss (-0.5%).
   
2. The Hover:
   - Entry: 0x80 (Pivot) acting as mean reversion center.
   - Buy when Price < Pivot - 0.5%
   - Sell when Price > Pivot + 0.5%
"""

import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass
import pandas as pd
import numpy as np

# Import local modules
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_edgx_data, get_sample_dirs
from live_decoder import EDGXStream, LiveParser, SignalEvent, OP_FLOOR, OP_CEILING, OP_PIVOT, OP_LIFT

@dataclass
class Position:
    entry_price: float
    entry_time: pd.Timestamp
    direction: str # 'LONG' or 'SHORT'
    strategy: str
    size: int = 100
    # Metrics at entry
    entry_storm_score: float = 0.0
    entry_volatility: float = 0.0

@dataclass
class TradeRecord:
    strategy: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    pnl: float
    return_pct: float
    # Analysis Metrics
    entry_storm_score: float
    entry_volatility: float

class BacktestEngine:
    def __init__(self, initial_capital: float = 10000.0):
        self.capital = initial_capital
        self.positions: List[Position] = []
        self.closed_trades: List[TradeRecord] = []
        self.current_price = 0.0
        self.current_time = None
        
        # Volatility Tracking
        self.price_history: List[float] = [] # Last 100 prices
        
        # --- Strategy State: Deep Value ---
        self.monitor_deep_value = False
        self.deep_value_limit_price = 0.0
        self.deep_value_expiry = None
        
        # --- Strategy State: Trend Follow ---
        self.monitor_trend = False
        self.trend_ceiling_time = None
        
        # --- Parameters ---
        # Deep Value
        self.flush_depth_pct = 0.005 # Buy 0.5% below floor
        self.flush_expiry_sec = 1800 # Order active for 30 mins
        self.value_stop_pct = 0.01   # Wide stop 1%
        self.value_take_pct = 0.03   # Big target 3%
        self.min_volatility = 0.15   # Volatility Filter (New)
        
        # Trend Follow
        self.trend_window_sec = 60   # Lift must happen within 60s of Ceiling
        self.trend_stop_pct = 0.003  # Tight stop 0.3%
        self.trend_take_pct = 0.01   # Quick scalp 1%
        
    def _update_metrics(self, price: float):
        self.price_history.append(price)
        if len(self.price_history) > 100:
            self.price_history.pop(0)
            
    def get_volatility(self) -> float:
        if len(self.price_history) < 2:
            return 0.0
        return np.std(self.price_history)

    def process_tick(self, tick, event: Optional[SignalEvent], parser: LiveParser):
        self.current_price = tick.price
        self.current_time = tick.timestamp
        self._update_metrics(tick.price)
        
        # 1. Manage Pending Orders (Deep Value)
        if self.monitor_deep_value:
            # Check expiry
            if self.deep_value_expiry and tick.timestamp > self.deep_value_expiry:
                self.monitor_deep_value = False
            # Check Fill
            elif tick.price <= self.deep_value_limit_price:
                self._enter_position("DeepValue", "LONG", tick.price, tick.timestamp, parser.storm_score)
                self.monitor_deep_value = False # Filled
        
        # 2. Manage Trend Window
        if self.monitor_trend and self.trend_ceiling_time:
             if (tick.timestamp - self.trend_ceiling_time).total_seconds() > self.trend_window_sec:
                 self.monitor_trend = False # Window closed
        
        # 3. Manage Open Positions
        self._manage_positions(tick)
        
        # 4. Check for Signals
        if event:
            self._handle_signals(tick, event, parser)
            
    def _handle_signals(self, tick, event: SignalEvent, parser: LiveParser):
        # --- DEEP VALUE SETUP ---
        if event.opcode == OP_FLOOR:
            # CHECK VOLATILITY FILTER
            current_vol = self.get_volatility()
            if current_vol >= self.min_volatility:
                # When Floor detected, set a limit order LOWER
                limit_price = tick.price * (1.0 - self.flush_depth_pct)
                self.monitor_deep_value = True
                self.deep_value_limit_price = limit_price
                self.deep_value_expiry = tick.timestamp + pd.Timedelta(seconds=self.flush_expiry_sec)
                # print(f"[{tick.timestamp}] FLOOR @ {tick.price} (Vol: {current_vol:.3f}). Set Limit Buy @ {limit_price:.2f}")
            else:
                pass 
                # print(f"[{tick.timestamp}] FLOOR ignored (Low Vol: {current_vol:.3f})")

        # --- TREND FOLLOW SETUP ---
        elif event.opcode == OP_CEILING:
            # Ceiling detected, watch for Breakout Lift
            self.monitor_trend = True
            self.trend_ceiling_time = tick.timestamp
            
        elif event.opcode == OP_LIFT:
            # If inside Trend Window (post-Ceiling), BUY
            if self.monitor_trend:
                self._enter_position("TrendFollow", "LONG", tick.price, tick.timestamp, parser.storm_score)
                self.monitor_trend = False # Consumed
        
    def _enter_position(self, strategy: str, direction: str, price: float, timestamp, storm_score: float):
        # One pos per strategy
        if len([p for p in self.positions if p.strategy == strategy]) > 0:
            return

        pos = Position(
            entry_price=price,
            entry_time=timestamp,
            direction=direction,
            strategy=strategy,
            size=100,
            entry_storm_score=storm_score,
            entry_volatility=self.get_volatility()
        )
        self.positions.append(pos)
        print(f"[{timestamp}] *** ENTER {strategy} *** {direction} @ {price:.2f} | Storm: {storm_score:.2f} | Vol: {pos.entry_volatility:.4f}")

    def _manage_positions(self, tick):
        active_positions = []
        
        for pos in self.positions:
            is_closed = False
            pnl = 0.0
            stop = 0.0
            take = 0.0
            
            # Set params based on strategy
            if pos.strategy == "DeepValue":
                stop_pct = self.value_stop_pct
                take_pct = self.value_take_pct
            else: # TrendFollow
                stop_pct = self.trend_stop_pct
                take_pct = self.trend_take_pct
            
            if pos.direction == "LONG":
                stop = pos.entry_price * (1.0 - stop_pct)
                take = pos.entry_price * (1.0 + take_pct)
                
                if tick.price <= stop:
                    pnl = (stop - pos.entry_price) * pos.size
                    self._close_position(pos, stop, pnl, "STOP")
                    is_closed = True
                elif tick.price >= take:
                    pnl = (take - pos.entry_price) * pos.size
                    self._close_position(pos, take, pnl, "TARGET")
                    is_closed = True
            
            if not is_closed:
                active_positions.append(pos)
                
        self.positions = active_positions

    def _close_position(self, pos: Position, exit_price: float, pnl: float, reason: str):
        record = TradeRecord(
            strategy=pos.strategy,
            entry_time=pos.entry_time,
            exit_time=self.current_time,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            pnl=pnl,
            return_pct=(exit_price - pos.entry_price) / pos.entry_price,
            entry_storm_score=pos.entry_storm_score,
            entry_volatility=pos.entry_volatility
        )
        self.closed_trades.append(record)
        print(f"[{self.current_time}] CLOSE {pos.strategy} ({reason}) @ {exit_price:.2f} | PnL: ${pnl:.2f}")

    def results_summary(self):
        if not self.closed_trades:
            return "No trades executed."
            
        df = pd.DataFrame([vars(t) for t in self.closed_trades])
        
        summary = "Strategy Results\n================\n"
        
        for strategy in df['strategy'].unique():
            s_df = df[df['strategy'] == strategy]
            total_pnl = s_df['pnl'].sum()
            win_rate = len(s_df[s_df['pnl'] > 0]) / len(s_df)
            avg_return = s_df['return_pct'].mean()
            
            summary += f"\nStrategy: {strategy}\n"
            summary += f"  Trades: {len(s_df)}\n"
            summary += f"  PnL:    ${total_pnl:.2f}\n"
            summary += f"  WinRate:{win_rate:.1%}\n"
            summary += f"  AvgRet: {avg_return:.2%}\n"
            
        total_pnl = df['pnl'].sum()
        summary += f"\nTOTAL PnL: ${total_pnl:.2f}\n"
        return summary

def run_batch_backtest():
    print("=" * 60)
    print("SYSTEMATIC ALPHA: BATCH ROBUSTNESS TEST (ALL SAMPLES)")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    if not sample_dirs:
        print("No data found.")
        return
        
    results = []
    
    print(f"Found {len(sample_dirs)} historical samples.")
    print("-" * 60)
    print(f"{'Date':<15} | {'DeepVal PnL':<12} | {'Trades':<8} | {'Win Rate':<8}")
    print("-" * 60)
    
    total_deep_value_pnl = 0.0
    total_trades = 0
    
    for sample_dir in sample_dirs:
        try:
            # Load Data
            df = load_edgx_data(sample_dir, symbol='GME')
            if len(df) < 1000:
                continue
                
            # Init Engine
            stream = EDGXStream(df)
            parser = LiveParser()
            engine = BacktestEngine(initial_capital=10000.0)
            
            # Run
            for tick in stream.stream():
                event = parser.process_tick(tick)
                engine.process_tick(tick, event, parser)
                
            # Extract Day Results
            trades = [t for t in engine.closed_trades if t.strategy == "DeepValue"]
            day_pnl = sum(t.pnl for t in trades)
            day_count = len(trades)
            day_wins = len([t for t in trades if t.pnl > 0])
            win_rate = (day_wins / day_count) if day_count > 0 else 0.0
            
            total_deep_value_pnl += day_pnl
            total_trades += day_count
            
            print(f"{sample_dir.name:<15} | ${day_pnl:>10.2f} | {day_count:>8} | {win_rate:>7.1%}")
            
            results.append({
                'date': sample_dir.name,
                'pnl': day_pnl,
                'trades': day_count
            })
            
        except Exception as e:
            # print(f"Skipping {sample_dir.name}: {e}")
            pass
            
    print("-" * 60)
    print("BATCH SUMMARY")
    print("-" * 60)
    print(f"Total Samples: {len(results)}")
    print(f"Total Trades:  {total_trades}")
    print(f"Total PnL:     ${total_deep_value_pnl:.2f}")
    if total_trades > 0:
        print(f"Avg PnL/Trade: ${total_deep_value_pnl/total_trades:.2f}")
        
    # Export for analysis if requested
    if "--analyze" in sys.argv:
        all_trades = []
        for sample_dir in sample_dirs:
            try:
                # We need to re-run or store trade records better. 
                # For now, let's just stick to the summary logic above unless we refactor to keep all records.
                # Actually, simpler: let's just re-run the BEST day for detailed logging.
                pass 
            except:
                pass
        print("\n[Analysis] Use --single --analyze on a specific day for detailed CSV.")

def run_analysis_mode():
    print("=" * 60)
    print("ANALYSIS MODE: GENERATING TRADE METRICS")
    print("=" * 60)
    
    sample_dirs = get_sample_dirs()
    # Pick the Best Day: 2024-05-14
    target_dir = next((d for d in sample_dirs if "2024-05-14" in d.name), None)
    
    if not target_dir:
        print("Target sample 2024-05-14 not found.")
        return

    print(f"Analyzing {target_dir.name}...")
    df = load_edgx_data(target_dir, symbol='GME')
    
    stream = EDGXStream(df)
    parser = LiveParser()
    engine = BacktestEngine(initial_capital=10000.0)
    
    for tick in stream.stream():
        event = parser.process_tick(tick)
        engine.process_tick(tick, event, parser)
        
    # Export Trades
    trades = [vars(t) for t in engine.closed_trades if t.strategy == "DeepValue"]
    if trades:
        out_df = pd.DataFrame(trades)
        out_file = "deep_value_analysis.csv"
        out_df.to_csv(out_file, index=False)
        print(f"Saved {len(trades)} trades to {out_file}")
        
        # Simple Correlation Check
        print("\n[Correlation Analysis]")
        print(f"Win Rate: {len(out_df[out_df['pnl']>0]) / len(out_df):.1%}")
        out_df['win'] = (out_df['pnl'] > 0).astype(int)
        
        print(f"Corr (Win vs Storm): {out_df['win'].corr(out_df['entry_storm_score']):.3f}")
        print(f"Corr (Win vs Vol):   {out_df['win'].corr(out_df['entry_volatility']):.3f}")
        
        print("\n[Storm Score Segments]")
        print(out_df.groupby(pd.cut(out_df['entry_storm_score'], bins=[0, 0.3, 0.6, 1.0]))['pnl'].mean())

if __name__ == "__main__":
    if "--batch" in sys.argv:
        run_batch_backtest()
    elif "--analyze" in sys.argv:
        run_analysis_mode()
    else:
        run_backtest()
