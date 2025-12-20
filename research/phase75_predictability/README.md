# Phase 75: Predictability (Hayashi-Yoshida)

## Goal
Analyze the lead-lag relationship between Options Delta Flow and Stock Price for GME, specifically testing if options flow anticipates price movements using the Hayashi-Yoshida estimator.

## Key Findings
- **Analysis pending**: Run `run_study.py` to generate HY Lead-Lag plots.

## Artifacts
- `output/gme_option_trades_*.csv`: Fetched OPRA tick data.
- `output/hy_lead_lag.png`: Lead-Lag correlation plot.

## Usage
1. Download Data:
   ```bash
   python download_data.py
   ```
   *Note: Requires Polygon.io API Key (Stocks Developer+ for Trades).*

2. Run Analysis:
   ```bash
   python scripts/causality_hy.py
   ```

## Data
- **Source**: Polygon.io (OPRA Options Trades).
- **Date**: May 2024 (High Volatility Event).
