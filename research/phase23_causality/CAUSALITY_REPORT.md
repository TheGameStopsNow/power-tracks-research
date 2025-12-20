
# Phase 23: Causality & Sequencing

## Objective
To determine the **Order of Operations** in the market network.
Does GME start the fire, or does it just burn the brightest?
We applied **Lagged Cross-Correlation Analysis** to Opcode Density (1-minute resolution) during the War Week (May 13-17).

## The Influence Map
Who leads whom? Arrows indicate significant predictive power (p < 0.05).

![Influence Graph](charts/influence_graph.png)

### Key Findings

1.  **The Leader: AMC**
    -   **Link**: AMC -> GME (Lag: 3 mins, Corr: 0.44)
    -   **Finding**: AMC density spikes *before* GME density.
    -   *Interpretation*: In this specific window, AMC acted as the "Canary". The Algo activated there first, then rolled capital into GME 3 minutes later.

2.  **The Follower: GME**
    -   **Status**: **Reactive Node**.
    -   GME is strongly predicted by AMC and NVDA, but GME itself does *not* strongly predict other major nodes.
    -   *Conclusion*: GME is the **Target**, not the Source. It is the destination for the liquidity/signal.

3.  **The Systemic Driver: NVDA**
    -   **Link**: NVDA -> SPY (Lag: 5 mins, Corr: 0.35)
    -   **Link**: NVDA -> GME (Lag: 3 mins, Corr: 0.22)
    -   **Finding**: NVDA moves the entire board. Its density predicts SPY (the market) and GME (the anomaly).
    -   *Hypothesis*: NVDA provides the "Risk-On" signal globally. Without NVDA activation, the Meme Algo cannot fire.

## Structural Implications
The "War Algo" is not isolated.
-   It waits for **NVDA** (The Green Light).
-   It tests **AMC** (The Probe).
-   If successful, it commits to **GME** (The Main Event).
-   Finally, it hands off to **KOSS** (The Cleanup / Relay - Phase 19/22 findings).

## Artifacts
- [Lead-Lag Matrix (CSV)](data/lead_lag_results.csv)
- [Influence Graph (PNG)](charts/influence_graph.png)
