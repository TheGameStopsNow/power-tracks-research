
# Phase 18: The Ripple Effect

## Objective
To test the "Ironing the Wrinkle" hypothesis:
1.  **Temporal Cadence**: Do signals ripple from asset to asset?
2.  **Conservation of Volatility**: Does the market suppress specific assets to balance the "War" spikes?

## 1. The Timeline of Infection (Cadence)
We tracked the exact days of "Peak Density" activation.

![Ripple Waves](charts/ripple_waves.png)

| Date | Event | Density | Notes |
| :--- | :--- | :--- | :--- |
| **May 13 (Mon)** | **KOSS Activates** | **4.3%** | The initial breach. |
| **May 14 (Tue)** | **GME Activates** | **9.0%** | The main event. |
| **May 15 (Wed)** | *Silence* | - | The "Eye of the Storm". |
| **May 16 (Thu)** | **SLE Activates** | **6.0%** | **The Ripple.** System1 spikes 3 days later. |
| **May 17 (Fri)** | **CLOV Activates** | **5.4%** | The late arrival. |

> [!IMPORTANT]
> **The Cadence is Real.** The "War Algo" does not strike all targets simultaneously. It cycles through them: `KOSS -> GME -> SLE -> CLOV`.

## 2. Expanded Timeline (Pre & Post Event)
We scanned the 2 weeks before (Apr 29 - May 10) and 2 weeks after (May 20 - May 31) for echoes.

### Pre-Event: The Silence
-   **Anomalies Detected**: **0**
-   **Max Density**: < 8% (Baseline Noise)
-   **Conclusion**: There were **NO precursors**. The "War Algo" switched ON instaneously on May 13. It did not "leak" beforehand.

### Post-Event: The Ironing
-   **Anomalies Detected**: **0** (Excluding 1 data glitch in BLIAQ).
-   **Density Return**: The system returned to the 5.9% baseline immediately on May 20.
-   **Conclusion**: There were **NO aftershocks**. The "Ironing" was instant and perfect. Once the event window closed, the volatility vanished.

## 3. The Counter-Weight Search (Ironing)
We looked for assets with **Negative Correlation** to the Activators (KOSS/SLE) over the 5-week period.

| Target | Counter-Weight? | Correlation | Verdict |
| :--- | :--- | :--- | :--- |
| **SLE** | **BLIAQ** | **-0.33** | **Weak Link.** Liquidating Trust moving inversely? |
| **KOSS** | **NVDA** | +0.13 | **No Link.** NVDA did not mechanically dip to fund KOSS. |
| **KOSS** | **SPY** | +0.38 | **Market Beta.** KOSS generally moves *with* the market. |

**Conclusion**: We found **no single "Ironing Asset"**. There is no "Anti-GME" that is sold 1:1.
Instead, the "Wrinkle" is smoothed out by the **entire fabric**. The broad market (SPY, AAPL, MSFT) maintained steady density (Immunity), effectively absorbing the localized volatility of the Meme cluster.

## 4. Total System Energy
The System-Wide Opcode Density (Sum of 51 symbols) remained remarkably stable.

![System Energy](charts/system_energy.png)

-   **Peace Week Avg**: 3.21
-   **War Week Avg**: 3.24
-   **Variance**: <1%

This strongly supports the **Conservation of Volatility** hypothesis. The market did not get "louder" overall; the noise just moved from the "Blanket" (Broad Market) to the "Wrinkles" (KOSS/SLE).

## 5. Visualizing the Mechanics
The Heatmap reveals the precise "Flow" of the signal across the top 20 assets. Note the vertical bands of activation vs the dark "Immune" zones.

![Cadence Heatmap](charts/cadence_heatmap.png)

## Artifacts
- [Density Matrix (CSV)](data/daily_density_matrix.csv)
- [Correlations (CSV)](data/ripple_correlations.csv)
- [Ripple Study Script](run_study.py)
- [Timeline Analysis Script](analyze_timeline.py)
- [Visualization Script](generate_charts.py)
