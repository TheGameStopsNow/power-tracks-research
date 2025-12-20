# Phase 76: Echo Quant (Multi-Template)

## Goal
Quantify the predictive power of "Echo" patterns (fractal repetitions of price action) by extracting templates from major GME events and testing their recurrence across 4 years of history.

## Key Findings
- **Analysis pending**: Run `run_study.py` to generate forward return statistics.

## Artifacts
- `data/bars/GME_*.csv`: Historical minute bars.
- `output/forward_returns_comparison.png`: Return distribution plots.
- `output/echo_matches_with_returns.csv`: CSV of detected echoes.

## Usage
1. Download Data:
   ```bash
   python download_data.py
   ```
   *Note: Fetches GME minute bars for 2021-2022.*

2. Run Analysis:
   ```bash
   python scripts/echo_quant_analysis.py
   ```

## Data
- **Source**: Polygon.io (Minute Aggregates).
- **Range**: 2021-2024 (2021-2022 fetched here, assumes 2023-2024 might exist or be fetched).
