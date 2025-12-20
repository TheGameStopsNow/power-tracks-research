# Phase 81: Precision (Universe)

## Goal
Refine the precision of the Prism Model by testing it against a broader "Universe" of tickers (TSLA, AMD). The goal is to ensure the signal is specific to the "Gamma Condition" and not just a proxy for high-beta sector correlations.

## Key Findings
- [Pending Execution]

## Artifacts
- `output/universe_greeks.csv`: Calculated Greek flows for TSLA/AMD.
- `output/precision_matrix.csv`: Confusion matrix of signal accuracy across tickers.

## Usage
```bash
# 1. Download Data
python download_data.py

# 2. Compute Greeks
python scripts/compute_greeks_universe.py

# 3. Detect Bursts & Fingerprint
python scripts/fingerprint_universe.py

# 4. Analyze Precision / Thresholds
python scripts/threshold_precision_universe.py
```

## Data
- **Universe Bars**: Polygon.io (TSLA, AMD).
- **Universe OPRA**: ThetaData (TSLA, AMD). **Requires 'OPRA' subscription package.**
