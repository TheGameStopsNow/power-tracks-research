# Operation Glasshouse - Quick Start Guide

## Overview
This folder contains all the code needed to reproduce the Operation Glasshouse research findings: a profitable trading strategy based on decoded LSB signals in EDGX market data.

## Files Included

### Core Python Modules
- **`loader.py`** - Utility functions for loading EDGX tick data from CSV files
- **`packet_decoder.py`** - Legacy decoder for batch LSB analysis
- **`live_decoder.py`** - Real-time opcode detection engine (LSB extraction, byte formation, regime detection)
- **`strategy_backtester.py`** - Trading strategy simulator with batch testing capability

### Documentation
- **`FULL_REPORT.md`** - Complete research documentation (this is the main document)

## Quick Start

### 1. Prerequisites
```bash
# Ensure you have Python 3.8+ and required libraries
pip install pandas numpy
```

### 2. Data Requirements
You need EDGX tick data in CSV format with these columns:
- `timestamp` (datetime)
- `price` (float)
- `size` (int)
- `venue` (string, filtered to 'EDGX')

Data should be located at:
```
../../../data/samples/sample_YYYY-MM-DD
```

### 3. Running a Single Backtest
```bash
cd .
python3 strategy_backtester.py
```

This will run the "Deep Value" strategy on the most recent sample date.

### 4. Running Batch Analysis (All Dates)
```bash
python3 strategy_backtester.py --batch
```

Expected output:
```
============================================================
SYSTEMATIC ALPHA: BATCH ROBUSTNESS TEST (ALL SAMPLES)
============================================================
Found 26 historical samples.
------------------------------------------------------------
Date            | DeepVal PnL  | Trades   | Win Rate
------------------------------------------------------------
sample_2024-05-14 | $ 15621.62 |      336 |   47.6%
...
------------------------------------------------------------
Total PnL:     $36567.51
Avg PnL/Trade: $26.44
```

## Strategy Logic Summary

### The "Deep Value Flush" Strategy
1. **Signal**: Detect `0xA0` opcode (formed from 8 consecutive price LSBs)
2. **Entry**: Place limit buy order at signal_price × 0.995 (-0.5%)
3. **Exit**: 
   - Take profit at +3% from entry
   - Stop loss at -1% from entry
   - Order expires after 30 minutes

### Why It Works
The `0xA0` opcode is a "flush signal" - algorithms broadcast this before pushing the price down to trigger stop-losses. By placing a limit order below the signal, we capture the mean reversion that follows.

## Key Results

- **26 trading days tested** (2023-2024)
- **1,383 total trades executed**
- **$36,567.51 total profit** (in simulation)
- **$26.44 average profit per trade**
- **Best day**: May 14, 2024 (+$15,621 during peak GME volatility)

## Understanding the Code

### Signal Flow
```
CSV Data → EDGXStream → LiveParser → SignalEvent → BacktestEngine → Trade Records
```

### Main Classes

**`EDGXStream`** (live_decoder.py)
- Simulates live data feed by replaying historical ticks

**`LiveParser`** (live_decoder.py)
- Extracts LSBs from tick prices
- Forms bytes every 8 ticks
- Detects known opcodes (`0xA0`, `0x98`, `0x80`, `0x10`, `0x01`)
- Calculates market regime (STORM/CALM/TRANSITION)

**`BacktestEngine`** (strategy_backtester.py)
- Manages trading positions
- Implements entry/exit logic
- Tracks P&L and trade statistics

## Next Steps

1. **Read `FULL_REPORT.md`** for complete methodology and findings
2. **Modify strategy parameters** in `strategy_backtester.py`:
   - `flush_depth_pct` (default: 0.5%)
   - `value_stop_pct` (default: 1%)
   - `value_take_pct` (default: 3%)
3. **Test on other symbols** by modifying the `symbol='GME'` parameter
4. **Implement paper trading** to validate in real-time conditions

## Important Notes

⚠️ **This is research code** - not production-ready for live trading
⚠️ **Backtests exclude transaction costs** (slippage, fees, spread)
⚠️ **Past performance ≠ future results** - especially in changed market conditions

## Questions?

Refer to the FULL_REPORT.md for:
- Detailed methodology
- Phase-by-phase development timeline
- Technical architecture diagrams
- Complete results analysis
- Limitations and recommendations

---

**Project**: Operation Glasshouse  
**Status**: Research Complete ✓  
**Date**: December 2025
