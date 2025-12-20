
# Phase 14: The Micro-Structure Genome Project

## Objective
To sequence the linguistic structure of the "Rosetta Stone" signals and map the directional influence topology of the market.
(i.e., Do stocks "speak" in complex sentences? And who speaks first?)

## Part A: Genome Sequencing (Viral Motifs)
We mined millions of events for repeating 4-byte and 5-byte Opcode sequences.

### 1. The "Universal Grammar" (Peace)
These motifs appear in **10-12 different tickers** (SPY, AAPL, U, etc.). They represent the standard "Heartbeat" of the HFT network.
-   `00-00-00-00` / `FF-FF-FF-FF`: **Null/Silence**. The dominant state of the machine is waiting.
-   `80-00-00-00`: **Pivot-Silence**. A single direction change followed by observation.
-   `10-00-00-00`: **Station-Keeping**.

### 2. The "War Dialect" (GME Exclusive)
These motifs appeared in **GME** (and partially GROV) but **NOT** in SPY or AAPL.
-   `08-00-00-00-00`: **The "0x08" Marker**. This opcode is prevalent in GME but absent in the Broad Market.
-   `F8-00-00-00-00`: **The "0xF8" Marker**.
-   **Hypothesis**: These are "War Opcodes" specific to the aggressive algo active on Meme stocks. They are likely aggressive limit-ordersweeps not used in index arbitrage.

## Part B: Influence Topology (The Chain of Command)
We attempted to map directional influence ($A \to B$) using Lagged Cross-Correlation on a 100ms grid.

| Source | Target | Lag | Correlation | Interpretation |
| :--- | :--- | :--- | :--- | :--- |
| **SPY** | **AAPL** | **0 ms** | **High** | **Lockstep**. They move in exact unison (faster than 100ms). |
| **SPY** | **GME** | N/A | Low | **Decoupled**. No predictive influence found. |
| **GME** | **GROV** | N/A | Low | **Independent**. Even two "War" stocks fight their own battles. |

### Conclusion
-   The "Genomic Structure" of the market is bifurcated.
-   **Peace Stocks** speak a simple, synchronized language (`80`, `10`) in perfect lockstep.
-   **War Stocks** speak a complex, exotic dialect (`08`, `F8`) and operate in isolation, disconnected from the central nervous system.

## Artifacts
- [Genome Script](../../tools/run_genome_project.py)
- [Raw Edges](data/influence_edges.csv)
