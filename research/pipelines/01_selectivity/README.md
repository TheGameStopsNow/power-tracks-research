# Study 01: Selectivity (Shapes vs. Signatures)

## Hypothesis

**"Are 'Power Track' shapes unique to GME, or are they generic market patterns?"**

Initial testing suggested that raw shape matching (TISA) was too broad, identifying "matches" in SPY and other unrelated assets. We hypothesized that a discrete "Event Signature" (K-Spike) would be required to isolate the true signal.

## Data

* **Input**: Minute bars for GME and SPY (2024).
* **Artifacts**:
  * `selectivity_suite.json`: Summary of match rates.
  * `tisa_multiscale_GME_vs_SPY_*.json`: Raw TISA match logs.
  * `tisa_spike_signatures_GME_vs_SPY_*.json`: K-Spike signature logs.

## Methodology

We compared two detection methods against a control group (SPY):

1. **Raw Shape Match (TISA)**: Dynamic Time Warping distance < Threshold.
2. **Event Signature (K-Spike)**: Discrete sequence of price/volume events.

### What this test does (plain language)

* Take GME burst shapes and search for “look‑alikes” in SPY and other symbols.
* First pass (TISA) asks: does the *overall shape* look similar? Result: yes, too often (generic).
* Second pass (K‑Spike) asks: do the *key spikes* line up? Result: far fewer hits (selective).

### Reproduction

1. **Download Data**:

   ```bash
   python research/pipelines/01_selectivity/download_data.py
   ```

2. **Run Analysis**:

   ```bash
   python research/pipelines/01_selectivity/scripts/run_selectivity_suite.py
   ```

## Results

* **Raw Shape Match**: Found "strong" matches in SPY on 67% of tested days (p < 0.01). **Result: GENERIC.**
* **K-Spike Signature**: Rejected 82% of SPY cases (p > 0.4). **Result: SELECTIVE.**

## Interpretation

The "shape" of a squeeze is not unique; volatility looks like volatility. However, the *micro-structure* of the GME event (the K-Spike sequence) is highly specific and effectively filters out generic market noise.
