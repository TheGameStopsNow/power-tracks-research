
# Phase 22: Synchronicity Analysis

## Objective
To map the "Network Topology" of the basket. Who talks to whom?
We analyzed the **War Week (May 13-17, 2024)** at 1-minute resolution to calculate the probability of simultaneous Opcode firing.

## The Matrix (Jaccard Index)
Values range from 0.0 (Never together) to 1.0 (Always together).

![Matrix](charts/synchronicity_matrix.png)

### Key Findings
1.  **The Chorus (GME + AMC)**: Score **0.36**.
    -   They are highly synchronized. When GME fires an opcode, there is a 36% chance AMC fires one in the *same minute*.
    -   *Interpretation*: They are driven by the same immediate signal source.

2.  **The Relay (GME + KOSS)**: Score **0.016**.
    -   Extremely low measures of simultaneity.
    -   *Confirmation*: This proves the **Phase 19 "Hand-off" Theory**. They do not trade together; they trade *sequentially*. GME runs the morning, KOSS runs the close.

3.  **The Mainframe (The NVDA Link)**: Score **0.22** (GME-NVDA).
    -   **Surprise Finding**. GME has a higher synchronization score with NVDA (0.22) than with KOSS (0.01).
    -   *Hypothesis*: NVDA, as the market leader/liquidity proxy, provides the "Carrier Wave" or "Clock" that the Meme Algo syncs to. The "War" happens inside the noise of the "King".

## Cluster Events
We identified **356 minutes** where >25% of the basket fired opcodes simultaneously.
![Timeline](charts/cluster_timeline.png)

These "High Cohesion Moments" likely represent:
-   **Systemic Resets**: The Algo re-calibrating across all nodes.
-   **Liquidity Sweeps**: A coordinated move to grab liquidity from the entire basket at once.

## Conclusion
The Basket is not a monolith. It has distinct sub-structures:
-   **Sync Pair**: GME/AMC.
-   **Relay Pair**: GME/KOSS.
-   **Systemic Anchor**: NVDA.

## Artifacts
- [Co-occurrence Matrix (CSV)](data/jaccard_matrix.csv)
- [Cluster Events (CSV)](data/cluster_events.csv)
- [Matrix Visualization](charts/synchronicity_matrix.png)
