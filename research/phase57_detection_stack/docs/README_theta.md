# ThetaData Gamma Analysis Workflow

This directory contains the scripts and data for calculating Gamma Exposure (GEX) for GME using a ThetaData **Standard Subscription**.

## Problem & Solution
Standard subscriptions do not have access to bulk historical Greeks (especially Gamma, which is Professional tier).
However, we can:
1. Fetch Bulk Open Interest (OI) using `/v3/option/history/open_interest`.
2. Fetch Contract Lists using `/v3/option/list/contracts/quote`.
3. Iteratively fetch Implied Volatility (IV) for each contract using `/v3/option/history/greeks/implied_volatility`.
4. Calculate Gamma locally using Black-Scholes.

## Scripts

### 1. `fetch_theta_iterative.py`
**Usage**: `python3 fetch_theta_iterative.py`
- Connects to local Theta Terminal (port 25503).
- Fetches OI (Bulk) and IV (Sequential) for configured dates.
- Saves raw CSVs to `data/theta/raw/`.
- **Note**: This takes ~5-10 minutes per day due to rate limiting/sequential fetching.

### 2. `process_theta_gamma.py`
**Usage**: `python3 process_theta_gamma.py`
- Reads `iv_*.csv` and `oi_*.csv`.
- Merges data on Expiration/Strike/Right.
- Calculates Gamma and GEX.
- Saves aggregated daily metrics to `data/theta/processed/daily_gamma_metrics.csv`.

## Output
The final output `daily_gamma_metrics.csv` contains:
- `net_gamma_gex`: Total Net Gamma Exposure (assuming Dealers are Short OI).
- `call_gex` / `put_gex`.
- `total_oi`.
- `avg_iv`.

## Status
- **Raw Data**: In `data/theta/raw`.
- **Processed Data**: In `data/theta/processed`.
