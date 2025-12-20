# Study 04: Options Layer (EPD & HIP)

## Hypothesis

**"Is the 'Liquidity Fracture' driven by option market structure?"**

We hypothesized two mechanisms:

1. **EPD (Exposure-Potential Drift)**: Price is "pinned" to high-gamma strikes ("Magnets") before the event.
2. **HIP (Hedge-Impact Propagator)**: Dealer hedging of option flow *leads* price action ("Tail Wags Dog").

## Data

* **Input**: Option flow and minute bars for GME (May 2024).
* **Artifacts**:
  * `options_suite_summary.md`: Summary of findings.
  * `MASTER_VALIDATION_TABLE.csv`: Metrics for 12 symbols.
  * `hip_null_test_GME.json`: Statistical significance of lead-lag.

## Methodology

1. **Gamma Magnets**: Calculate Gamma-Weighted Volume per strike and compare to closing price.
2. **Lead-Lag Analysis**: Compute Hayashi-Yoshida correlation between Option Flow (Net Delta) and Price Changes at various lags.

### What this test does (plain language)

* **EPD**: Build a “magnet map” of strikes where option positioning is heavy, and check if price sticks to those levels before moves.
* **HIP**: Measure whether hedging flow tends to happen before price moves (flow leads) or after (price leads), and how strong that relationship is.

### Reproduction

1. **Download Data**:

   ```bash
   python research/pipelines/04_options_epd_hip/download_data.py
   ```

2. **Run Options Suite**:

   ```bash
   python research/pipelines/04_options_epd_hip/scripts/run_options_suite.py
   ```

3. **Run EPD/HIP Demos (Optional)**:

   ```bash
   python research/pipelines/04_options_epd_hip/scripts/run_pinning_robustness.py
   python research/pipelines/04_options_epd_hip/scripts/run_hip_panel.py
   ```

## Results

* **EPD (Pinning)**: Validated. Price consistently pins to Gamma Magnets before explosions.
* **HIP (Causality)**: Validated. Option flow leads price by 1-30 seconds (Correlation ~0.38).
* **Significance**: HIP signal is >4 sigma above random noise (p < 0.01).

## Interpretation

The "Meme Fracture" is an options-driven event. The "Engine" (GME) is driven by a feedback loop where dealer hedging of massive option flow forces price movement, creating the "Power Track" signature.
