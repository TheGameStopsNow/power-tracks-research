# Phase 57: Detection Stack (Adversarial Steganography)

## Hypothesis
If a covert channel exists in modern high-frequency trading data, it behaves like an adversarial steganography system:
1.  **Low Rate**: Hides in the noise floor.
2.  **Spread Spectrum**: Distributed across features (time, venue, size).
3.  **Regime Conditioned**: Only active when natural market volatility masks the signal.

## Methodology
The "Detection Stack" is a layered harness designed to reject the null hypothesis (random microstructure noise) at increasing levels of sophistication.

### Layer 0: Data Harness & Conditioning
Normalizes trade data and segments it into "Regimes" (Quiet, Normal, High Stress) using the `StressModel`. This prevents false positives caused by natural market bursts.

### Layer 1: Point Process Residuals (Timing)
Models trade arrival times using a Hawkes Process. Residuals (transformed time) should be Uniform on [0,1]. Deviations indicate unexplained timing structure (clock-like behavior).

### Layer 2: Cyclostationarity (Periodicity)
Spectral analysis of event intensity to find stable "carrier frequencies" (e.g., 2Hz, 10Hz) that persist across days, conditioning on time-of-day.

### Layer 3: Cross-Venue Latency (Routing)
Analyzes the lag distribution between exchanges (e.g., NYSE vs. EDGX). Looks for state-switching in latency modes (binary signaling via routing delays).

### Layer 4: Motif Mining (Symbolic)
Searches for recurrent symbolic sequences (e.g., Price Up -> Price Down -> Size Big) that appear significantly more often than in randomized surrogates (Permutation Testing).

## Usage
Run the harness on a target ticker and date range:
```bash
python detection_harness.py --ticker GME --date 2024-05-14
```

## Data
Data is downloaded to `data/`. Run:
```bash
python download_data.py
```

## Structure
*   **`detection_harness.py`**: Main entry point.
*   **`scripts/`**: Auxiliary fetch/probe scripts.
*   **`output/`**: Simulation results and reports.
*   **`docs/`**: Detailed documentation.

## Interpreting Results

### Layer 1: Hawkes Residuals
*   **Metric**: KS P-Value against Uniform[0,1].
*   **Interpretation**: If p < 0.05, the trade arrival times contain structure *not* explained by simple burstiness (Hawkes Process). This usually indicates "clocked" algos or complex orchestration.

### Layer 2: Cyclostationarity
*   **Metric**: Max Signal-to-Noise Ratio (SNR) of spectral peaks.
*   **Interpretation**: High SNR (>10.0) at specific frequencies (e.g., 5Hz, 10Hz) suggests a rigid periodic component, potentially a synchronization carrier.

### Layer 3: Cross-Venue Latency
*   **Metric**: Divergence between Mode and Median lag.
*   **Interpretation**: In pure noise/routing delay, Mode ≈ Median. Significant divergence or multi-modality suggests "State Switching" (e.g., sometimes V1 leads V2, sometimes lag is extended), which could encode bits.
