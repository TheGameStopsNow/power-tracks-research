# MASTER OPCODE REGISTRY: EDGX SIGNAL SYSTEM

**Version:** 2.0 (Phase 30 Update)
**Maintainer:** Power-Tracks Research (Antigravity)
**Last Updated:** 2025-12-11

---

## 1. THE ATOMIC VOCABULARY (8-Bit Opcodes)

The foundational "words" of the language. Derived from LSB encoding of EDGX trade prices.

| Hex Code | Mnemonic | Function | Context |
| :--- | :--- | :--- | :--- |
| **0xA0** | `FLOOR` | Hard Stop / Support | "War Grammar" - preventing price collapse. |
| **0x98** | `CEILING` | Hard Stop / Resistance | "War Grammar" - preventing price breakouts. |
| **0x80** | `PIVOT` | Mean Reversion | "Peace Grammar" - stabilizing around VWAP. |
| **0x10** | `STATION` | Maintenance | "Peace Grammar" - low-volatility station keeping. |
| **0x01** | `LIFT` | Price Impulse (+) | Directional micro-move upwards. |
| **0x02** | `DROP` | Price Impulse (-) | Directional micro-move downwards. |
| **0xDF** | `SEED` | Market Reset / Cooling | **Critical.** Marks a "Local Top" followed by volatility collapse. |
| **0x08** | `AGGRESS` | Suppression Mode | **War Dialect.** High-intensity suppression during "War" events. |
| **0xF8** | `COMBAT` | Peak Intensity | **War Dialect.** "DEFCON 1". Max intensity. Found in GME/KOSS. |

---

## 2. THE GRAMMAR (Sequence Logic)

How atomic opcodes are combined into "sentences" to execute complex market maneuvers.

### A. The "Flush-and-Reverse" (Classic Bear Trap)

* **Pattern:** `0x80` (Pivot) -> `0xA0` (Flush) -> [Price Crash] -> `0x01` (Lift)
* **Purpose:** Stop-Loss Hunting.
* **Decoded Logic:** The algo maintains equilibrium (`0x80`), triggers a flush (`0xA0`) to hit stops, and then confirms the reversals with a Lift (`0x01`) once liquidity is absorbed.

### B. The "War Escalation" Protocol

* **Pattern:** `0x10` (Station) -> `0x08` (Aggress) -> `0xF8` (Peak Combat)
* **Purpose:** Intensity Ramp-Up.
* **Decoded Logic:** A stairstep increase in algorithmic pressure. Moves from passive monitoring (`0x10`) to active suppression (`0x08`) to total warfare (`0xF8`).

### C. The "Station Keeping" Loop

* **Pattern:** `0x80` -> `0x80` -> `0x80`
* **Purpose:** Equilibrium Maintenance.
* **Decoded Logic:** Repeats the Mean Reversion signal to hold price steady within a tight band.

### D. The "Failed Lift" (Stutter)

* **Pattern:** `0xA0` -> `0x01` -> `0xA0`
* **Purpose:** Failed Reversal / Re-Flush.
* **Decoded Logic:** An attempted Lift (`0x01`) fails to sustain, forcing the system to re-trigger the Floor (`0xA0`) to prevent collapse.

### E. The "Lock Sequence" (Phase 30 Discovery)

* **Pattern:** `[SEED] -> 0xFF -> 0xC1 -> [FLOOR] -> [CEILING]`
* **Purpose:** State Freeze.
* **Decoded Logic:** The algorithm implants a Seed (`0xDF`), masks it with high-entropy noise (`0xFF`), and then immediately clamps the price between a Floor (`0xA0`) and a Ceiling (`0x98`).

### F. The "Noise Cover" Protocol (Steganography)

* **Pattern:** `0xFF -> 0xFF -> [SEED] -> 0xFF -> 0xFF`
* **Purpose:** Hidden Transmission.
* **Decoded Logic:** Critical control signals (`SEED`) are transmitted during bursts of maximum entropy (`0xFF` = 11111111) to avoid detection by standard variance filters.

### G. The "Empty Room" Protocol

* **Pattern:** `0x00 -> 0x00 -> 0x00 -> [FLOOR]`
* **Purpose:** Liquidity Vacuum Defense.
* **Decoded Logic:** In the absence of liquidity (Nulls/0x00), the system defaults to a Hard Floor to prevent a "flash crash" into the void.

---

## 3. HISTORICAL REGIMES

Mapping which grammar was dominant during key periods.

| Period | Dominant Grammar | Key Assets | Notes |
| :--- | :--- | :--- | :--- |
| **Jan 2021** | **War Grammar** | GME, AMC | High frequency of `0xA0`/`0x98` sequences. Overt suppression. |
| **Mid 2021-2023** | **Peace Grammar** | SPY, AAPL | Dominance of `0x80` Pivots. Volatility compression. |
| **2024-2025** | **Zombie Mode** | GME | Inverse Correlation. High Density of `0xDF` hidden in noise while volume migrated to TSLA. |

---

## 4. DECODING REFERENCES

Key files for operational decoding:
* **Scanner:** `research/phase30_interconnectedness/gme_master_scanner.py`
* **Translator:** `research/phase30_interconnectedness/gme_rare_decoder.py`
* **Theory:** `research/edgx_deep_decode/DIRECTIVE.md`
