# Study 03: Portability & Temporal Generalization

## Hypothesis

**"Is this signal unique to GME in 2024, or does it work across the 'Meme Basket' and in historical squeezes?"**

We tested the GME-derived "Gated" signal on other assets (AMC, KOSS, TSLA, etc.) and on the 2021 "Sneeze" data to validate its robustness and universality.

## Data

* **Input**: Minute bars for Panel Symbols (2024) and GME/KOSS (2021).
* **Artifacts**:
  * `PANEL_portability_analysis.md`: Performance across 27 symbols.
  * `TEMPORAL_analysis.md`: Performance on 2021 data.
  * `UNIVERSE_DYNAMICS.md`: The "Fracture Hierarchy".

## Methodology

1. **Cross-Symbol**: Apply the *exact* GME 2024 gate (Cluster 1/3 + Sig) to other symbols without retraining.
2. **Temporal**: Apply the *exact* 2024 gate to 2021 data.

### What this test does (plain language)

* Re-use the GME gate “as-is” on other symbols to see who resonates (basket vs controls).
* Re-use the same gate on 2021 (“the sneeze”) to see if the pattern was already present back then.
* Summarize which symbols win (basket) and which fail (controls), and show that the fracture shape is stable across years.

### Reproduction

1. **Download Data**:

   ```bash
   python research/pipelines/03_portability_temporal/download_data.py
   ```

2. **Run Portability Panel**:

   ```bash
   python research/pipelines/03_portability_temporal/scripts/run_portability_panel_extended.py
   ```

3. **Run Temporal Generalization**:

   ```bash
   python research/pipelines/03_portability_temporal/scripts/run_temporal_generalization_deep.py
   ```

## Results

* **Portability**:
  * **KOSS**: 97% Win Rate, +194% Max Runup. **Confirmed.**
  * **AMC**: 93% Win Rate. **Confirmed.**
  * **TSLA/BB**: Mixed/Failed. **Rejected.**
* **Temporal (2021)**:
  * **KOSS (2021)**: 100% Win Rate, +1508% Runup. **Timeless.**
  * **GME (2021)**: 100% Win Rate, +539% Runup. **Timeless.**

## Interpretation

The signal captures a specific "Liquidity Fracture" mechanic that is shared by the core basket (GME, KOSS, AMC) and is structurally invariant over time (2021 vs 2024). It is NOT a general market pattern.
