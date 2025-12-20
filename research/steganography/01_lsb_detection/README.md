# Phase 1: LSB Detection in Price Data

## Hypothesis

Least significant bits of price data may exhibit non-random patterns indicative of intentional encoding.

## Method

1. Extract LSB sequences from price time series
2. Apply chi-square tests for frequency distribution anomalies
3. Measure entropy across different time windows
4. Compare against null hypothesis (random LSB distribution)

## Data

- GME minute bars (existing Power Tracks dataset)
- SPY minute bars (control)
- Multi-symbol basket for cross-validation

## Metrics

- Chi-square p-values for LSB frequency
- Shannon entropy per trading session
- Autocorrelation of LSB sequences
- Kolmogorov-Smirnov test against uniform distribution

## Deliverables

- [ ] LSB extraction script
- [ ] Statistical analysis notebook
- [ ] Results summary with visualizations
- [ ] Detection threshold recommendations

## Status

⚪ Pending Phase 0 completion
