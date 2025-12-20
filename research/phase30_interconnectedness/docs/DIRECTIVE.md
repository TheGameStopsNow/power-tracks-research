
# Phase 30: The Neural Network (Cross-Symbol Signal Propagation)

## Context
In **Phase 29**, we validated the existence of the "Launch Key" (`0.07 -> 0.04 -> 0.01` Price Delta) in GME's real tape, confirming it precedes volatility expansion with 100% accuracy on March 8, 2021.
In **Phase 16 (Galaxy)**, we identified a "Classified Cluster" of tickers (KOSS, OPEN, CLOV) that exhibit similar algorithmic density to GME.

## Objective
To map the **causal latency** and **synchronization mechanics** of the "Launch Key" across the entire "Basket." We are testing the hypothesis that GME (or KOSS) acts as the **Pattern Generator** for the rest of the network.

## The Experiment ("Operation Synapse")

### 1. Data Acquisition (Real Ticks Only)
We will fetch Granular Trade Data (Ticks) for the "Infected Cluster" identified in Phase 16:
*   **Primary:** GME, KOSS
*   **Secondary:** CLOV, OPEN, EXPR, BB
*   **Control:** SPY, AAPL

**Target Dates:**
*   Jan 28, 2021 (The Big Bang)
*   March 8, 2021 (The Validation Day)
*   May 13-14, 2024 (The Return)

### 2. The "Ping" Scan
We will scan *every* ticker for the **7-4-1 Signal** (`0.07 -> 0.04 -> 0.01`) and the **Reverse Signal** (`0.01 -> 0.04 -> 0.07`).
*   *Hypothesis:* Do they all fire the signal? Or only the "Master Node"?
*   *Output:* A timestamped log of every "Ping" in the network.

### 3. Latency Mapping (The Speed of Contagion)
If GME fires a 7-4-1 at `12:00:00.050`, when does KOSS react?
*   We will calculate the `Delta-t` between signals across symbols.
*   We will measure the "Reaction Time" of the Basket to a GME Signal.

### 4. Legacy Integration (The Unified Theory)
We will specifically validate the conclusions from previous phases:
*   **From Phase 8:** Validate that "Micro-Analysis" (Ticks) succeeds where "Macro-Analysis" (Bars) failed in detecting cross-symbol sync.
*   **From Phase 14:** Check for correlation between the **7-4-1 Price Signal** and the **0x08 War Opcode**. Are they the same event viewed through different lenses?
*   **From Phase 15:** Confirm that **AAPL/MSFT** ("The Immune System") show ZERO 7-4-1 activity, serving as the negative control.

### 5. The Neural Map
We will construct a directed graph where:
*   **Nodes:** Tickers
*   **Edges:** Validated Signal Influence (Lead-Lag relationships)
*   **Metric:** Signal Propagation Speed (in ms).

## Success Criteria
*   **Definitive Proof** of whether the Basket is "Centralized" (One Leader) or "Decentralized" (Swarm Logic).
*   **Identification** of the "Prime Node" (The ticker that signals *first*).

## Implementation Plan
1.  `tools/fetch_cluster_ticks.py`: Mass downloader for Polygon V3 Trades.
2.  `research/phase30/scan_network.py`: Distributed scanner for the 7-4-1 pattern AND 0x08 Opcodes.
3.  `research/phase30/map_latency.py`: Cross-correlation engine for sparse signal events.
