# Phase 86: Reversal Dynamics (741 Simulation)

## Goal
To simulate the "741" price reversal mechanics using an autoregressive model with specific lag coefficients, verifying if these dynamics can reproduce the observed price action in target securities.

## Key Findings
- **Reversal Patterns**: The simulation reproduces characteristic "pop-and-drop" or "drift" patterns based on specific lag sets (e.g., 1, 4, 7).
- **Bidirectional Causality**: The tool includes checks for forward vs reverse causality.

## Artifacts
- This phase primarily runs as an interactive Streamlit app.
- `output/`: (Optional) Saved simulation run data or charts.

## Usage
Run the Streamlit application:

```bash
streamlit run scripts/simulate_741_app.py
```

## Data
- **Live Data**: Uses `yfinance` to fetch real-time data for comparison (e.g., GME, BTC).
- No local raw data download is strictly required, but `download_data.py` is provided for consistency.
