# Phase 79: Control (Low Gamma)

## Goal
Validate the "Gamma Hypothesis" by applying the Prism Strategy (refined in Phase 78) to a "Low Gamma" control period (Jan-Apr 2024). The hypothesis predicts that the Alpha signal observed in May 2024 (High Gamma) should significantly degrade or disappear in the Low Gamma regime, confirming that the signal is a function of Gamma Pressure and not a generic market property.

## Key Findings
- [Pending Execution]

## Artifacts
- `output/control_test_results.csv`: Performance metrics by regime.
- `output/control_test_plot.png`: Visual comparison of strategy vs benchmark in High vs Low Gamma regimes.

## Usage
```bash
# Verify dependencies
python download_data.py

# Run Control Test
python scripts/control_test.py
```

## Data
- **Source**: Internal (Phase 77).
- **File**: `../phase77_greek_echo/output/burst_fingerprints_enhanced.csv`
