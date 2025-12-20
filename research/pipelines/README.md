# Power Tracks Research: The "Meme Fracture"

This directory contains the complete research history of the Power Tracks Engine.

## Prerequisites

> **New to Power Tracks?**
> If you are looking for a high-level explanation of the concepts, start with our **[Labs](../00_getting-started/01_magic_demo.ipynb)** before diving into the research.

## Setup

To reproduce the research, you need to fetch the underlying data (which cannot be shared directly).

1.  **Configure API Key**:
    Ensure you have a `.env` file in the repo root with `POLYGON_API_KEY=your_key`.

2.  **Fetch Data**:
    Run the setup script from this directory:
    ```bash
    cd research
    python3 setup_data.py
    ```

   The script reads `docs/raw_data_manifest.json` and downloads every referenced raw slice (bars, trades, options) into the gitignored locations used by each pipeline/test. Use `--study <name>` to limit downloads or `--dry-run` to preview.


## Key Concepts (Plain Language)

- **Burst / Power Track**: A decoded spike of price/volume activity (a “shape” the engine extracts from raw data).
- **TISA (shape match)**: A math tool that measures how similar two price paths are. Good for finding look‑alikes; too generic by itself.
- **K‑Spike (event signature)**: A simplified fingerprint of a burst (top up/down moves and their timing). Much more selective than raw shape.
- **Cluster**: Grouping bursts by their structural traits. Clusters 1 & 3 are “Power”; Cluster 0 is a “Trap.”
- **Gate**: A filter that only fires when multiple conditions are true (e.g., Power Cluster + K‑Spike + options confirmation).
- **Gamma Magnet (EPD)**: A price level where option positions make dealers keep price pinned (like a magnet).
- **HIP (Flow Causality)**: Checking whether option hedging flow tends to happen before (or after) price moves.
- **Effect Roles**: Context labels for how a burst behaves in the tape: Impactor (short‑term jolt), Binder (mid‑term drift), Echo (rare replay, often a trap), Macro (basket‑wide day, often dampened).

## Recommended Reading Order

To understand the engine's logic, we recommend following this path:

0.  **[00_signal_integrity](00_signal_integrity/README.md)**: **The Foundation.**
    *   *Hypothesis*: Can we verify the signal at the binary frame level?
    *   *Outcome*: A self-contained bundle for verifying the 56-bit frame format and CRC integrity.
1.  **[01_selectivity](01_selectivity/README.md)**: **The First Filter.**
    *   *Hypothesis*: Are "Power Track" shapes unique to GME?
    *   *Outcome*: Raw shapes are generic (found in SPY), but the "K-Spike" event signature is highly selective.
2.  **[02_clusters_gating](02_clusters_gating/README.md)**: **The Signal.**
    *   *Hypothesis*: Can we filter noise using structural clustering?
    *   *Outcome*: Clusters 1 & 3 ("Power Clusters") combined with K-Spike signatures yield perfect wins in the small 2024 training set (N=3 gated) and mitigate losses in the H2‑2024 holdout (cluster‑only, no K‑Spike fired).
3.  **[03_portability_temporal](03_portability_temporal/README.md)**: **The Validation.**
    *   *Hypothesis*: Does this signal work on other symbols and in other years?
    *   *Outcome*: Validated on AMC/KOSS (Basket) and 2021 Data ("Timeless"). Discovered the "Fracture Hierarchy" (Canary -> Spark -> Anchor).
4.  **[04_options_epd_hip](04_options_epd_hip/README.md)**: **The Mechanic.**
    *   *Hypothesis*: Is this driven by option market structure?
    *   *Outcome*: Validated "Gamma Magnets" (EPD) and "Flow Causality" (HIP). Option flow leads price.
5.  **[05_effect_roles](05_effect_roles/README.md)**: **The Context.**
    *   *Hypothesis*: Can we classify events into functional roles?
    *   *Outcome*: Defined Impactor (Jolt), Binder (Drift), Echo (Trap), and Macro (Dampener) roles.


## Frozen Specifications

The engine operates on these validated parameters:

*   **Power Clusters**: `1` (Aggressive) and `3` (Sustained).
*   **Trap Cluster**: `0` (Avoid).
*   **Event Signature**: `K-Spike` (Discrete Event Sequence).
*   **Significance Threshold**: `p <= 0.05` (for Gating).
*   **Gamma Magnets**: Strikes with high Gamma-Weighted Volume.

## Limitations & Caveats

*   **Regime Dependence**: The "Meme Fracture" is a specific liquidity failure mode. It may not persist if market structure changes fundamentally (e.g., T+1 settlement impact).
*   **Data Proxies**: Historical option open interest is approximated using "Gamma-Weighted Volume" due to data availability.
*   **Sample Size**: Some validations (e.g., Echo, 2021 KOSS) rely on small sample sizes due to the rarity of these extreme events.
*   **Macro Dampening**: "Macro" days (basket-wide bursts) tend to have slightly lower returns than isolated idiosyncratic bursts, likely due to liquidity dispersion.
*   **Effect Roles (Impactor/Binder/Echo/Macro)**: Impactor is strongly validated; Binder needs long-horizon data for the full universe; Echo is rare, GME‑only, and directionally negative (low N); Macro behaves as a dampener in the historical scan.

## Quick Start

Navigate to each folder for specific reproduction commands. Every folder README documents:
- Hypothesis
- Data (paths, dates, symbols)
- Method (scripts + example commands)
- Results (key metrics with p‑values/CIs)
- Interpretation & caveats
- Interpretation & caveats

---

## ⚠️ Disclaimer

**EDUCATIONAL PURPOSE ONLY.**

This software is provided for **educational and research purposes only**. It is intended to demonstrate high-frequency data analysis, signal processing, and software engineering concepts.

*   **No Warranty**: This software is provided "as is", without warranty of any kind, express or implied.
*   **Not Financial Advice**: Nothing in this repository constitutes financial, investment, legal, or tax advice.
*   **Research Only**: Do not use this software to trade with actual money. Use simulated accounts ("paper trading") only.
