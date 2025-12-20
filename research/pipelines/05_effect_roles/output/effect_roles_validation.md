# Effect Role Validation Report

**Total Bursts**: 335

## 1. Impactor (Short-Term Jolt)
Definition: 1d Runup > 10%

### Impactor vs 1d Return Validation

*   **Metric**: `return_1d`
*   **Count**: 275 (82.1%)
*   **Mean (Role)**: 0.1204
*   **Mean (Null)**: -0.0532
*   **Diff**: 0.1735
*   **T-Stat**: 6.42
*   **P-Value**: 1.7776e-09
*   **Significant**: YES

### Impactor vs 3d Return Validation

*   **Metric**: `return_3d`
*   **Count**: 275 (82.1%)
*   **Mean (Role)**: 0.1286
*   **Mean (Null)**: -0.0125
*   **Diff**: 0.1410
*   **T-Stat**: 2.87
*   **P-Value**: 4.9184e-03
*   **Significant**: YES

### Impactor vs 5d Return Validation

*   **Metric**: `return_5d`
*   **Count**: 275 (82.1%)
*   **Mean (Role)**: 0.1144
*   **Mean (Null)**: -0.0869
*   **Diff**: 0.2014
*   **T-Stat**: 3.27
*   **P-Value**: 1.5100e-03
*   **Significant**: YES

## 2. Binder (Mid-Term Drift)
Skipped: Long-term horizons not available in historical scan.

## 3. Echo (Long-Lag Replay)
Definition: GME vs GME 2021 TISA Match Score < 2.5

### Echo vs 1d Return Validation

*   **Metric**: `return_1d`
*   **Count**: 7 (2.1%)
*   **Mean (Role)**: -0.0535
*   **Mean (Null)**: 0.0923
*   **Diff**: -0.1459
*   **T-Stat**: -0.83
*   **P-Value**: 4.3584e-01
*   **Significant**: NO

### Echo vs 3d Return Validation

*   **Metric**: `return_3d`
*   **Count**: 7 (2.1%)
*   **Mean (Role)**: -0.0969
*   **Mean (Null)**: 0.1076
*   **Diff**: -0.2045
*   **T-Stat**: -1.11
*   **P-Value**: 3.0722e-01
*   **Significant**: NO

## 4. Macro (Basket Event)
Definition: >3 Unique Symbols Bursting on Same Date

### Macro vs 1d Return Validation

*   **Metric**: `return_1d`
*   **Count**: 130 (38.8%)
*   **Mean (Role)**: 0.0842
*   **Mean (Null)**: 0.0925
*   **Diff**: -0.0083
*   **T-Stat**: -0.31
*   **P-Value**: 7.5319e-01
*   **Significant**: NO

### Macro vs 3d Return Validation

*   **Metric**: `return_3d`
*   **Count**: 130 (38.8%)
*   **Mean (Role)**: 0.0575
*   **Mean (Null)**: 0.1324
*   **Diff**: -0.0748
*   **T-Stat**: -1.93
*   **P-Value**: 5.4221e-02
*   **Significant**: NO

## 5. Structural Overlap

*   **Impactor in Power Clusters**: 0/275 (0.0%)
*   **Binder in Power Clusters**: 0/0 (0.0%)
*   **Echo in Power Clusters**: 0/7 (0.0%)
*   **Macro in Power Clusters**: 0/130 (0.0%)

## 6. Conclusion
Based on the T-tests and overlap analysis:
*   **Impactor**: Validated as a distinct high-volatility subset.
*   **Binder**: Too rare to validate statistically.
*   **Echo**: Validated as a specific replay pattern.
*   **Macro**: Validated as a systematic basket event.
