# Power Tracks Guide Book

> **Status**: Living Document
> **Version**: 1.0
> **Purpose**: A unified knowledge base for upgrading the Power Tracks Engine and Studio.

## 1. Introduction: The "Meme Fracture"

Power Tracks are not standard technical indicators. They are discrete, structural "fractures" in market liquidity, initially identified in meme stocks (GME, AMC, KOSS) but potentially present elsewhere.

**Research Hypothesis**: Specific high-frequency trading behaviors create unique "bursts" of activity that are effectively encoded instructions. These bursts are not random; they are algorithmic footprints that precede significant price movements.

**The Goal**: detect these bursts in real-time, decode their internal structure, and project the likely future price path.

---

## 2. Anatomy of a Power Track

A "Power Track" is defined by a specific set of signal characteristics observed in a sliding window of trade ticks.

### Detection Criteria
The Engine scans for a **Burst** that meets two simultaneous conditions:
1.  **Spectral Signature**:
    *   **Frequency Band**: 0.5 Hz – 3.0 Hz.
    *   **Power Threshold**: Significant concentration of energy (Typically ≥ 10,000 spectral power).
    *   *Meaning*: The trades are not random; they are arriving in a rhythmic, periodic cadence (every ~0.33 to 2 seconds).
2.  **Kinetic Energy (ROC)**:
    *   **Rate of Change**: Price moves ≥ 0.7% within a 5-second sub-window.
    *   *Meaning*: The rhythmic activity is accompanied by aggressive price action (volume accumulation/distribution).

### The "K-Spike" Signature
Beyond raw detection, bursts are validated using the **K-Spike** algorithm (`pipelines/01_selectivity`):
*   **Concept**: A "fingerprint" of the burst's steepest moves.
*   **Algorithm**:
    1.  Calculate 1st derivative (price differences).
    2.  Separate into **Up** (positive) and **Down** (negative) moves.
    3.  Select the **Top-K** largest moves by magnitude (typically K=3).
    4.  Create a feature vector: `[pos_1..k, z_height_1..k]` for both sides.
*   **Matching**: The vector is compared against a template using Euclidean distance. A low distance (p < 0.05) confirms the signal.

---

## 3. The Hidden Language (Decoding)

The Power Tracks protocol uses a strict **56-bit Frame** structure.

### Frame Format (56 bits)
Each frame typically consists of:
*   **Header (48 bits)**:
    *   `Opcode` (6 bits): Instruction type.
    *   `Version` (2 bits): Protocol version (usually 1).
    *   `Start Timestamp` (16 bits): MSB/LSB microsecond offset from session start.
    *   `Duration Scale` (6 bits) & `Compression` (2 bits): Time scaling context.
    *   `Anchor Price` (8 bits): Base reference price ($0.00 - $2.55 scale).
    *   `Volume Code` (6 bits) & `Parity` (2 bits).
*   **Trailer (8 bits)**:
    *   `CRC-7` (7 bits): Polynomial `0x09` ($x^7 + x^3 + 1$).
    *   `Stop Bit` (1 bit): Always 1.

### Opcodes (Instruction Set)
The encoded instructions define how the price path should unfold:
| Opcode | Mode | Description |
| :--- | :--- | :--- |
| `0x1A` | **VARINT** | Standard compressed integer encoding. |
| `0x1F` | **VARINT** | Alternative varint encoding. |
| `0x3F` | **MIRROR** | Sign-flipped replication of the previous path. |
| `0x91` | **CONT** | Path continuation (append to previous). |
| *Other* | **RAW** | Direct byte-to-price mapping. |

### Decryption (The "Key")
The stream is often XOR-masked. The Decoder attempts to "unlock" the message by testing masks from `0x00` to `0x1F`.
*   **Scoring**: The correct mask is identified by valid CRCs, monotonic timestamps, and plausible price deltas (Zig-Zag decoded).
*   **Decodability Score (D)**: The fraction of frames that decode successfully. A high D score indicates a "Scripted" event.

---

## 4. Taxonomy & Classification

Not all bursts are the same. We classify them to separate signal from noise.

### A. Clusters (Structural Types)
Research (`pipelines/02_clusters_gating`) identified three main structural groups using Nearest Neighbor clustering:

| Cluster | Nickname | Behavior | Mean Return | Max Runup | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **0** | **The Trap** | Mean reversion, often follows a run-up. | -29% | 47% | **AVOID** |
| **1** | **Power A** | Aggressive, sharp initiation. | -1% | 102% | **GO** |
| **3** | **Power B** | Sustained, broader accumulation. | -3% | 95% | **GO** |

### B. "Gating" Strategy
To ensure high-quality signals, we apply a **Gate**:
> **PASS CONDITION**: (Cluster == 1 OR 3) AND (Signature == K-Spike)

*   **K-Spike**: A specific "event signature" (discrete sequence of up/down moves) that validates the burst.
*   **Result**: 100% win rate in training set when gated.

### C. Effect Roles (Functional Context)
Research (`pipelines/05_effect_roles`) assigns functional roles based on context:

| Role | Description | Typical Outcome |
| :--- | :--- | :--- |
| **Impactor** | Short-term volatility driver. Explodes immediately. | High +Returns (Buy quality) |
| **Binder** | Mid-term trend driver | Slow drift upward. |
| **Echo** | Long-lag replay of a past event. | **TRAP** (-5.4% returns). |
| **Macro** | Basket-wide simultaneous bursts. | Dampener (lower returns than isolated). |

---

## 5. Universe Dynamics (The "Fracture Hierarchy")

Power Tracks are not isolated to one symbol. They propagate across a specific "Basket" of assets.

### A. Universe Types
Research (`pipelines/03_portability_temporal`) classifies symbols into three tiers:
1.  **Core**: The primary basket (GME, AMC, KOSS). The signal is robust and portable here.
2.  **Satellite**: Adjacent assets (CHWY, CLOV, WKHS) that often exhibit the same fracture but with different timing.
3.  **Hidden**: Assets that move in sympathy but are less reliable.

### B. Leader-Follower Dynamics ("Canaries")
Contrary to popular belief, **GME is often the last to move** (the "Anchor").
*   **Canaries (Leaders)**: Smaller caps like **KOSS** and **CHWY** frequently initiate the fracture event.
    *   *Observation*: In May 2024, KOSS/CHWY led the basket by **4-10 minutes** before GME reacted.
*   **Satellite Propagation**: The signal often ripples from Satellite Leaders -> Core Anchors.
    *   *Lag Time*: Satellite bursts typically precede Core bursts by **3-9 minutes**.
*   **Strategy**: Monitor KOSS/CHWY for "Canary" bursts to predict imminent GME moves.

---

## 6. The Options Layer (EPD & HIP)

The "Engine" driving these tracks is hypothesized to be the options market (`pipelines/04_options_epd_hip`).

### A. EPD (Exposure-Potential Drift) - "Gamma Magnets"
*   **Mechanism**: Dealers have massive gamma exposure at specific strikes. Before a fracture, price is effectively "pinned" to these strikes to minimize delta-hedging costs.
*   **Validation**: Price action consistently pins to high Gamma-Weighted Volume strikes before exploding (p < 0.05).

### B. HIP (Hedge-Impact Propagator) - "Tail Wags Dog"
*   **Mechanism**: Option flow (Net Delta) drives price action via dealer hedging.
*   **Lead-Lag**: Option flow **leads** price changes by **1-30 seconds**.
    *   **Correlation**: Hayashi-Yoshida correlation ~0.38 (statistically significant, p < 0.01).
    *   *Significance*: This confirms the move is structural/mechanical, not sentiment-based.

---

## 7. Macro Dynamics

Day-to-day bursts are often chapters in a larger book.

### Stitching
The Engine "stitches" daily tracks into **Macro Tracks** if they align:
1.  **Decode Alignment**: Does today's burst match the price/time projection of a previous burst?
2.  **Mask Consistency**: Is the XOR mask stable (within ±1 drift)?
3.  **Family**: Do they share opcode sequences?

### Corridors
Stitched tracks form a **Price Corridor**—a multi-day or multi-week envelope of expected price action. This allows the system to differentiate between a random move and a "scripted" move that is strictly following a macro plan.

---

## 8. System Implementation Guide

### Engine Upgrades
To support this research, the Engine must:
*   [ ] **Enforce Gating**: Implement the `Cluster 1/3 + K-Spike` logic as a hard filter or high-priority tag.
*   [ ] **Compute "D" Score**: Real-time calculation of Decodability to feed the forecast model.
*   [ ] **Macro-Stitcher**: Run the `MacroStitcher` logic daily to maintain long-term corridors.
*   [ ] **Basket Monitor**: Ingest feeds for "Canary" symbols (KOSS, CHWY) to trigger early warnings for GME.

### Studio Upgrades
The UI should visualize these classifications:
*   [ ] **Tags**: Explicitly label tracks as "Impactor", "Echo", or "Trap" (Cluster 0).
*   [ ] **Gated vs. Raw**: Allow users to toggle between "All Detections" and "Gated Signals".
*   [ ] **IVCM Forecast**: Display the composite forecast which blends the Track projections with volatility (ATR/IV) and Decodability confidence.
*   [ ] **Magnet Map**: Visualize "Gamma Magnets" (high gamma strikes) alongside the price chart.

---

## 9. Glossary

*   **IVCM**: Implied Volatility Corridor Model (Forecasting engine).
*   **TISA**: Time-Invariant Shape Analysis (Shape matching).
*   **EPD**: Effective Price Discovery (often "Gamma Magnets" in options).
*   **HIP**: Hedging Impact Probability (Flow causality).
*   **Fracture**: A liquidity failure event characteristic of the meme basket.
