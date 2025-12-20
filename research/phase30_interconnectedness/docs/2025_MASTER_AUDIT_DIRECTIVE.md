# DIRECTIVE: PHASE 30D - 2025 MASTER AUDIT & GME DEEP DIVE

**Status:** PENDING EXECUTION
**Priority:** CRITICAL
**Target:** 2025 Full Year Dataset (Jan 2 - Dec 10)

---

## 1. SITUATION REPORT (CONTEXT)
We have successfully downloaded the entire 2025 trading year (236 days). Preliminary analysis (`2025_YEAR_IN_REVIEW.md`) indicated a massive shift in *volume-based* signal activity from GME to TSLA/MSFT.
However, **volume is not validity**. 
A quiet signal is still a signal. We need to determine if GME is "dead" (no signals) or "dormant" (active grammar, low volume - i.e., "Zombie Mode").

**Working Hypothesis:** The "Algorithm" didn't leave GME; it just went underground (Steganography). TSLA is the distraction; GME remains the primary control variable.

---

## 2. MISSION OBJECTIVES
1.  **GME Master Audit:** Scan **every single day** of 2025 for GME. Do not skip low-volume days. We are looking for **Opcode Density** spikes that don't show up on volume radars.
2.  **The "Hollow Shell" Test:** Compare GME's opcode vocabulary in 2025 against the 2021 baseline. Is the "War Grammar" (`0xA0`/`0x98`) still resident in the code?
3.  **Basket Correlation:** Cross-reference GME silent days against TSLA/MSFT "loud" days. Does GME whisper when TSLA shouts?
4.  **Zombie Detection:** Identify days with <100k volume but >10% Opcode Density. These are "heartbeat" checks.

---

## 3. ASSETS & INTELLIGENCE

### Data Repository
**Path:** `/Users/mThe Author/Documents/GitHub/power-tracks-research/data/ticks/`
**Structure:**
- `2025-01-02/` -> `GME.csv`, `TSLA.csv`, `AMC.csv`...
- ...
- `2025-12-10/`
**Format:** CSV (timestamp_us, price, ... exchange)
**Key Venue:** Exchange Code `4` (EDGX)

### Tools & Weaponry
1.  **Opcode Decoder:** 
    *   `research/phase30_interconnectedness/decode_2025_opcodes.py` (Validates Opcode Density)
2.  **Pattern Scanner:**
    *   `tools/scan_2025.py` (Finds 7-4-1 Patterns)
3.  **Reference Library:**
    *   `research/edgx_deep_decode/DIRECTIVE.md` (The Rosetta Stone)
    *   `research/phase30_interconnectedness/tsla_2025_vocab_summary.txt` (The New Baseline)

---

## 4. EXECUTION PLAN (NEXT SESSION)

### STEP 1: The GME "Pulse Check"
Run `decode_2025_opcodes.py` targeting **GME** specifically across a random sampling of 20 dates spread throughout the year (Jan, Apr, Jul, Oct, Dec).
*   **Goal:** Calculate Average Opcode Density.
*   **Threshold:** If > 5%, the line is active.

### STEP 2: The "Hidden Message" Scan
Modify the decoder to hunt for **rare opcodes** (`0xDF`, `0xA0` sequence bursts) in GME data specifically.
*   **Logic:** Even if volume is low, a single 1-second burst of `0xA0` commands indicates active suppression.

### STEP 3: The Correlation Matrix
Load the full 2025 Signal Log (`research/phase30_interconnectedness/2025_signal_log.csv`).
*   Filter for GME events.
*   Overlay with TSLA events.
*   **Question:** Do GME signals *precede* TSLA volatility? (The Leader-Lag Hypothesis).

