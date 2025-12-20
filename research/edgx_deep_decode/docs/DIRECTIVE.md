# Research Directive: Operation Glasshouse Phase II
**Status**: ACTIVE
**Clearance**: LEVEL 5 (DEEP CODE)
**Date**: December 9, 2025

---

## 1. State of the Art (The Axioms)
Operation Glasshouse (Phase I) successfully reverse-engineered the hidden control logic of the EDGX Book Feed. We have established the following **Axioms**:

1.  **The EDGX Feed is a Volatility State Machine**: It is not a passive stream of trades; it is an active broadcast of the algorithm's internal state constraints.
2.  **The Grammar is Regime-Adaptive**:
    - **War Grammar (Storm)**: Uses Hard Floors (`0xA0`) and Hard Ceilings (`0x98`) to enforce LULD bands.
    - **Peace Grammar (Calm)**: Uses Pivots (`0x80`) and Station-Keeping (`0x10`) to maintain VWAP.
3.  **The Holographic Principle**: Micro-scale signal bursts (e.g., the `0xDF` Seed) contain compressed fractal templates that play out over macro-scale timeframes (Days, Weeks, Quarters).

## 2. Strategic Objective
**Mission**: Transition from **Forensic Decoding** (Post-Hoc Analysis) to **Predictive Operations** (Real-Time actionable Intelligence).

We must build systems that can read the "Machine Language" as it is spoken, not days later.

## 3. The Roadmap (Phase II Tasks)

### Track A: Real-Time Theory
*   **Objective**: Build a "Heads-Up Display" for the Invisible tracks.
*   **Action Items**:
    1.  **Build `live_decoder.py`**: A low-latency parser that connects to the EDGX feed and flags `0xA0` (Floor) and `0x98` (Ceiling) events in real-time.
    2.  **Develop `Regime_Detector`**: A sliding-window classifier that calculates the "Grammar Score" (Bifurcation vs Compression) to identify the onset of a "Storm" before price reacts.

### Track B: Systematic Alpha
*   **Objective**: Monetize the decoded sequence logic.
*   **Strategy 1 (The Bounce)**: Buy on `0xA0` (Terminal Floor) confirmations during High Volatility.
    *   *Backtest Logic*: Entry on `0xA0` paired with `0x01` (Lift). Stop below the `0xA0` price level.
*   **Strategy 2 (The Hover)**: Mean-reversion trading around `0x80` (Pivot) during "Peace Grammar" regimes.
*   **Action Items**:
    1.  Implement `strategy_backtester.py`.
    2.  Quantify Win-Rate and Sharpe Ratio for "Grammar-Based" signals vs raw technical indicators.

### Track C: Fractal Surveillance
*   **Objective**: Map the "Long-Range Echoes" of major signal events.
*   **Action Items**:
    1.  **Maintain a "Seed Catalog"**: Automatically extract unique shapes from high-intensity signal bursts.
    2.  **Daily TISA Scan**: Run `tisa_extended.py` nightly to match today's seed against historical patterns (Is today a replay of Jan 2021? May 2024?).

## 4. Operational Guidelines
-   **Trust the Signal, Not the Noise**: Price is the shadow; the Opcode is the object. Focus analysis on the *type* of command being issued (`0xA0` vs `0x80`), not just the price level.
-   **Context is King**: A `0x80` signal means one thing in May (Resistance) and another in August (Pivot). Always determine the **Regime** first.

---
**Directive Issued By**: ANTIGRAVITY
**End of Transmission**
