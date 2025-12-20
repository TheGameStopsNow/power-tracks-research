# Phase 77: Greek Echo

## Goal
Compute and analyze Greek flows (Delta, Gamma, Charm) for OPRA options trades to fingerprint "bursts" of activity and build predictive models for price impact.

## Key Findings
- **Analysis pending**: Run `compute_greeks.py` to generate flows.

## Artifacts
- `output/opra_with_greeks.csv`: OPRA trades annotated with IV and Greeks.
- `output/greek_flows_1s.csv`: 1-second aggregated Greek flow metrics.
- `output/burst_fingerprints_enhanced.csv`: Detected bursts with Greek profiles.

## Usage
1. Ensure Phase 75 Data is available:
   ```bash
   python ../phase75_predictability/download_data.py
   ```

2. Run Greek Computation:
   ```bash
   python scripts/compute_greeks.py
   ```

3. Run Burst Fingerprinting:
   ```bash
   python scripts/fingerprint_bursts.py
   ```

## Data
- **Input**: Phase 75 OPRA Ticks (`research/phase75_predictability/data/opra_ticks`).
- **Derived**: Delta, Gamma, Charm flows.
