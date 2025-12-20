# Phase 80: Generality (NVDA)

## Goal
Verify the universality of the discovered "Prism" mechanic (Gamma/IV/Charm feedback loops) by testing it on a completely independent asset: NVIDIA (NVDA). NVDA was chosen for its high liquidity, high retail participation, and massive options volume during the test period (Feb-Apr 2024).

## Key Findings
- [Pending Execution]

## Artifacts
- `output/nvda_greeks.csv`: Calculated Greek flows.
- `output/nvda_bursts.csv`: Identified burst events.
- `output/universality_verification.png`: Performance chart of Prism Strategy on NVDA.

## Usage
```bash
# 1. Download Data (Polygon + Theta)
python download_data.py

# 2. Compute Greeks
python scripts/compute_greeks_nvda.py

# 3. Detect Bursts
python scripts/fingerprint_bursts_nvda.py

# 4. Verify Universality / Run Strategy
python scripts/verify_universality.py
```

## Data
- **NVDA Bars**: Polygon.io (Minute agglomerates).
- **NVDA OPRA**: ThetaData (Individual options trades). **Requires 'OPRA' subscription package.**
