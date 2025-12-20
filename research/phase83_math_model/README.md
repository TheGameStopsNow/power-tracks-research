# Phase 83: Mathematical Model (Prism Equation)

## Goal
To formalize the empirical findings of the "Prism Mechanic" into a continuous mathematical equation that describes the interaction between Gamma (Lens), IV (Coupling), and Charm (Accelerant).

## Key Findings
- **Prism Equation Defined**: $E[R] = \beta_0 + \beta_1 \ln(1+|\Gamma|) \cdot \frac{1}{1+e^{-k(IV-IV_{critical})}} \cdot (1 + \gamma \cdot \text{sgn}(\text{Charm}))$
- **Critical Threshold**: Confirmed mathematically.
- **Charm Sensitivity**: Quantified as an accelerant factor.

## Artifacts
- `output/model_fit_scatter.png`: Visualization of the model fit.
- `output/prism_equation_params.txt`: Best-fit parameters (beta, k, gamma).
- `docs/prism_theory.md`: Theoretical derivation.

## Usage
Run the fitting script to optimize parameters against Phase 77 data:

```bash
python scripts/fit_prism_equation.py
```

## Data
This phase depends on processed data from **Phase 77**:
- `research/phase77_greek_echo/results/burst_fingerprints_enhanced.csv`

Ensure Phase 77 is complete before running this study.
