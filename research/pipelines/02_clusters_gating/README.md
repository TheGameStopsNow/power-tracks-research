# Study 02: Clusters & Gating

## Hypothesis

**"Can we predict the quality of a burst based on its structural cluster?"**

We hypothesized that not all bursts are equal. By clustering the 1,884 historical bursts, we aimed to identify specific "Power Clusters" that reliably precede runups, and "Trap Clusters" that precede mean reversion.

## Data

* **Input**: `reports/forward_returns_midterm_GME_clustered.json` (1,884 bursts).
* **Artifacts**:
  * `CLUSTER_PROFILE.md`: Performance stats per cluster.
  * `GATING_ANALYSIS.md`: Performance of the "Gated" strategy.
  * `gating_reproduction.json`: Validation metrics.

## Methodology

1. **Clustering**: Applied Nearest Neighbor clustering to the burst dataset.
2. **Gating**: Defined a "Gate" requiring:
   * Cluster = 1 OR 3 ("Power Clusters").
   * Signature = K-Spike (p <= 0.01).

### What this test does (plain language)

* Group bursts by how they “look” structurally (clusters).
* Find which groups tend to win (big runups) vs. lose (traps).
* Add a gate: only fire when a burst is both a Power cluster *and* passes the K‑Spike test (so it’s structurally strong *and* has the right spike pattern).

### Reproduction

1. **Download Data**:

   ```bash
   python research/pipelines/02_clusters_gating/download_data.py
   ```

2. **Analyze Cluster Stability**:

   ```bash
   python research/pipelines/02_clusters_gating/scripts/run_cluster_stability.py
   ```

3. **Run Gating Analysis**:

   ```bash
   python research/pipelines/02_clusters_gating/scripts/run_gating_reproduction.py
   ```

## Results

* **Cluster 0 ("The Trap")**: -29% Mean Return, 47% Max Runup. **Avoid.**
* **Cluster 1 ("Power A")**: -1% Mean Return, 102% Max Runup. **High Potential.**
* **Cluster 3 ("Power B")**: -3% Mean Return, 95% Max Runup. **High Potential.**
* **Gated Strategy**: When filtering for Cluster 1/3 + K-Spike:
  * **Win Rate**: 100% (n=58).
  * **Mean Return**: +8% (vs -22% baseline).
  * **Max Runup**: +113%.

## Interpretation

Structure predicts outcome. By filtering for specific structural types (Clusters 1 & 3), we can drastically improve the signal-to-noise ratio and avoid the common "Trap" (Cluster 0).
