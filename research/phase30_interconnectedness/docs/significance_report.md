# Statistical Significance Report

## 1. Signal Clustering (Permutation Test)
- **H0:** Signals are uniformly distributed across tickers.
- **Observed CV:** 2.0345
- **Simulated CV (99th):** 0.0295
- **p-value:** < 0.0001
- **Verdict:** SIGNIFICANT clustering.

## 2. Causality Significance (Bootstrap)
- **Test:** GME -> KOSS (10s Return)
- **Sample Size:** 3075 signal events, 3075 baseline
- **Observed Alpha:** -0.000281
- **p-value:** 0.017800
- **Verdict:** NOT SIGNIFICANT
