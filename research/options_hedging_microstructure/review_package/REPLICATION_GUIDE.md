# Replication Guide — Exact Dates, Times, Parameters & Evidence

> **Purpose**: This guide provides the exact dates, timestamps, custom settings,
> detection thresholds, and evidence snippets needed to reproduce every result
> in the paper and briefing. Pre-computed JSON results are included in `results/`
> for verification without data.

---

## Data Requirements

All scripts expect tick-level trade data in Hive-partitioned Parquet format:

```text
data/raw/
├── polygon/trades/            # Equity tick data (Polygon.io)
│   └── symbol=<TICKER>/
│       └── date=<YYYY-MM-DD>/
│           └── part-0.parquet     # columns: timestamp, price, size
└── thetadata/trades/          # Options tick data (ThetaData)
    └── root=<TICKER>/
        └── date=<YYYYMMDD>/
            └── part-0.parquet     # columns: timestamp, price, size,
                                   #   strike, right, expiration,
                                   #   condition, exchange
```

**Data sources:**

- **Equity**: [Polygon.io](https://polygon.io) — set `POLYGON_API_KEY` env var
- **Options**: [ThetaData](https://thetadata.net) — run Theta Terminal on `localhost:25510`

---

## 1. Exchange & Condition Code Maps

All forensic scripts share these constants. You **must** use these exact mappings
to reproduce results.

### EXCHANGE_MAP (OPRA Venue Codes)

```python
EXCHANGE_MAP = {
    0: "COMPOSITE",      1: "BATS",            2: "BX",
    3: "MIAX_PEARL",     4: "C2",              5: "NSDQ_BX_OPT",
    6: "CBOE",           7: "ISE",             8: "PSE",
    9: "NYSE_AMEX",     10: "PHLX",           11: "NSDQ_ISE_GEMINI",
   12: "BOX",           13: "MIAX",           14: "UNKNOWN",
   15: "NSDQ_ISE_MERCURY", 16: "EDGX",        17: "NSDQ_MRCY",
   18: "MEMX",          19: "EMLD",           24: "MPRL",
   30: "ARCX",          31: "OPRA",           46: "MULTI_EXCHANGE",
   47: "ISE2",          48: "C1BOX",         140: "COMPOSITE_DELAYED",
   # De-masked dark venues (V5 — OPRA proprietary + Cboe feed mappings)
   22: "MIAX_PEARL_EQUITIES",
   42: "C2_COB",           # Cboe C2 Complex Order Book
   43: "EDGX_COB",         # Cboe EDGX Complex Order Book
   60: "BZX_OPTIONS",      # Cboe BZX Options (maker-taker inverted, HFT-favored)
   65: "EDGX_OPTIONS",     # Cboe EDGX Options (specialized complex routing)
   69: "PHLX_FLOOR",       # Nasdaq PHLX (floor-based cross trades)
   73: "MIAX_EMERALD",     # MIAX Emerald Options
}
```

### OPRA Condition Codes

| Code | Meaning | Category |
| ---- | ------- | -------- |
| 18 | Regular Trade | Standard |
| 95 | Spread | Complex |
| 125 | Intermarket Sweep (ISS) | Sweep |
| 129 | Multi-leg | Complex |
| 130 | Spread | Complex |
| 131 | Straddle/combo | Complex |
| 134 | Customer ISO | Sweep |
| 135 | Customer w/ size | Standard |
| 138 | Buyer/Seller ISS | Sweep |

**Detection sets used in all scripts:**

```python
SWEEP_CONDITIONS  = {125, 134, 138}
COMPLEX_CONDITIONS = {95, 129, 130, 131}
```

---

## 2. Event Dates & Times

### Event 1: GME January 2021 Squeeze

| Date | YYYYMMDD | Market Hours (ET) | Significance |
| ---- | -------- | ----------------- | ------------ |
| 2021-01-22 | 20210122 | 09:30–16:00 | Buildup week begins |
| 2021-01-25 | 20210125 | 09:30–16:00 | Monday surge |
| 2021-01-26 | 20210126 | 09:30–16:00 | Massive OI injection (+151,578 contracts) |
| 2021-01-27 | 20210127 | 09:30–16:00 | Highest closing price ($347.51) |
| 2021-01-28 | 20210128 | 09:30–16:00 | Intraday peak ($483), buy restrictions |
| 2021-01-29 | 20210129 | 09:30–16:00 | Options expiration (target expiry) |

- **Target Expiration**: `20210129`
- **Ignition Lookback**: 270 calendar days before 2021-01-29

### Event 2: GME June 2024 Squeeze

| Date | YYYYMMDD | Market Hours (ET) | Significance |
| ---- | -------- | ----------------- | ------------ |
| 2024-06-04 | 20240604 | 09:30–16:00 | Early buildup — 17 wash pairs detected |
| 2024-06-07 | 20240607 | 09:30–16:00 | Peak activity: 265 wash pairs, 31K COB clusters |
| 2024-06-10 | 20240610 | 09:30–16:00 | Continued accumulation |
| 2024-06-11 | 20240611 | 09:30–16:00 | Continued accumulation |
| 2024-06-17 | 20240617 | 09:30–16:00 | Final week buildup |
| 2024-06-18 | 20240618 | 09:30–16:00 | Largest OI injection (+121,028 contracts, DTE=3) |
| 2024-06-20 | 20240620 | 09:30–16:00 | Pre-expiration |
| 2024-06-21 | 20240621 | 09:30–16:00 | Options expiration (target expiry) |

- **Target Expiration**: `20240621`
- **Ignition Lookback**: 270 calendar days before 2024-06-21

### Event 3: DJT SPAC Merger (Wall Fatigue Cross-Validation)

| Date | Significance |
| ---- | ------------ |
| 2024-03-26 | Peak price (~$66 from ~$22) |
| Window: 30 days before through 30 days after peak |

---

## 3. Script-Level Parameters

### 3.1 Shadow Hunter (`shadow_hunter.py`)

```bash
python code/shadow_hunter.py --ticker GME
```

| Parameter | Value | Location |
| --------- | ----- | -------- |
| `min_size` (wash cross) | 100 contracts | `detect_wash_cross()` |
| `min_size` (tail banging) | 100 contracts | `detect_tail_banging()` |
| Tail OTM threshold | >50% OTM | hardcoded |
| Sub-second window | <1.0 second | `time_gap_sec < 1.0` |
| COB cluster detection | condition ∈ COMPLEX_CONDITIONS | `detect_cob_routing()` |
| Dark venue threshold | exchange code ∉ KNOWN_LIT_CODES | `detect_dark_venue()` |
| Dates scanned (Jun 2024) | 20240604, 20240607, 20240610, 20240611, 20240617, 20240618, 20240620, 20240621 | hardcoded |

**Pre-computed results**: `results/shadow_hunter_GME_20260212_145136.json`

---

### 3.2 Manipulation Forensic (`manipulation_forensic.py`)

```bash
python code/manipulation_forensic.py --event both --ticker GME
# Or individually:
python code/manipulation_forensic.py --event jan2021 --ticker GME
python code/manipulation_forensic.py --event jun2024 --ticker GME
```

| Parameter | Value | Location |
| --------- | ----- | -------- |
| `min_size` (block trade) | 100 contracts | `detect_predator_matrix()` |
| CVS threshold | ≥3 exchanges within 1 second | `detect_constructor_fingerprint()` |
| Ignition lookback | 270 calendar days | `detect_ignition_sequence()` |
| LEAPS DTE | >180 days | `detect_ignition_sequence()` |
| Short-dated DTE | <14 days | `detect_ignition_sequence()` |
| Sweep conditions | {125, 134, 138} | `SWEEP_CONDITIONS` |
| Complex conditions | {95, 129, 130, 131} | `COMPLEX_CONDITIONS` |
| Vanna lag window | minute-level resolution | `detect_vanna_lag()` |
| Target exp (Jan) | 20210129 | `--event jan2021` |
| Target exp (Jun) | 20240621 | `--event jun2024` |

**Pre-computed results**:

- `results/manipulation_forensic_GME_20260212_135324.json` (Jan 2021)
- `results/manipulation_forensic_GME_20260212_135336.json` (Jun 2024)

---

### 3.3 Squeeze Mechanics (`squeeze_mechanics_forensic.py`)

```bash
python code/squeeze_mechanics_forensic.py
```

| Parameter | Value |
| --------- | ----- |
| `PEAK_DATE` | `"2021-01-28"` (intraday peak, hit $483) |
| `PEAK_CLOSE_DATE` | `"2021-01-27"` (highest close, $347.51) |
| Delta model | Black-Scholes with vectorized IV |
| Wall approach threshold | <15% distance from close |
| Wall min volume | >100 contracts |

**Pre-computed results**: `results/squeeze_mechanics_GME_20260212_104815.json`

---

### 3.4 ACF Engines (`phase3_acf_engines.py`, `phase3_remaining.py`)

```bash
python code/phase3_acf_engines.py
python code/phase3_remaining.py
```

| Parameter | Value |
| --------- | ----- |
| ACF interval | 60 seconds |
| Max lag | 10 (engines), 20 (panel) |
| Intraday windows | `["09:30-10:00", "10:00-11:00", "11:00-12:00", "12:00-13:00", "13:00-14:00", "14:00-15:00", "15:00-15:30", "15:30-16:00"]` |
| Min observations per window | `max_lag + 5` |

**Pre-computed results**: `results/intraday_acf_*.json`, `results/multiscale_acf_*.json`

---

### 3.5 Panel Scan (`panel_scan.py`)

```bash
python code/panel_scan.py
```

| Parameter | Value |
| --------- | ----- |
| ACF interval | 60 seconds (default) |
| Max lag | 20 |
| Max days per ticker | 500 |

**Ticker list** (37 total):

```text
AAPL  AMD   AMC   AMZN  BABA  BB    BBBY  CHWY  COIN  DIS
DJT   F     FUBO  GME   GOOG  GOOGL HOOD  INTC  IWM   KOSS
META  MSFT  MSTR  MU    NFLX  NOK   NVDA  PLTR  QQQ   RDDT
RIVN  SNAP  SOFI  SPY   SQ    TSLA  WISH
```

**Pre-computed results**: `results/panel_scan_results.json`

---

### 3.6 NMF Temporal Archaeology (`phase5_paradigm.py`)

```bash
python code/phase5_paradigm.py
```

| Parameter | Value |
| --------- | ----- |
| `n_components` | 5 |
| `init` | `"nndsvd"` |
| `max_iter` | 500 |
| `random_state` | 42 |
| Variants | Standard, Strict (residual removal), Residual-only |
| Tickers | GME, TSLA, AAPL, DJT, PLTR, SOFI, CHWY |

**Pre-computed results**: `results/phase5a_kernel_*.json`, `results/phase5b_heatmap_*.json`, `results/phase5c_archaeology_*.json`

---

### 3.7 Counterfactual Analysis (`counterfactual_analysis.py`)

```bash
python code/counterfactual_analysis.py
```

| Parameter | Value |
| --------- | ----- |
| Squeeze center date | `2021-01-28` |
| Window before | 90 days |
| Window after | 20 days |
| Counterfactual 1 | center=`2022-03-15`, ±90/20 days |
| Counterfactual 2 | center=`2023-03-15`, ±90/20 days |
| Counterfactual 3 | center=`2024-03-15`, ±90/20 days |

**Pre-computed results**: `results/counterfactual_GME_20260212_111301.json`

---

### 3.8 Stacking Resonance (`stacking_resonance_test.py`)

```bash
python code/stacking_resonance_test.py --ticker GME
python code/stacking_resonance_test.py --ticker AAPL
python code/stacking_resonance_test.py --ticker TSLA
python code/stacking_resonance_test.py --ticker NVDA
python code/stacking_resonance_test.py --ticker PLTR
python code/stacking_resonance_test.py --ticker AMD
python code/stacking_resonance_test.py --ticker SPY
python code/stacking_resonance_test.py --ticker SNAP
```

| Parameter | Value |
| --------- | ----- |
| ACF interval | 60 seconds |
| ACF max lag | 5 |

**Pre-computed results**: `results/stacking_resonance_*_*.json`

---

### 3.9 Predictive Tests (`predictive_tests.py`, `magnitude_prediction_test.py`)

```bash
python code/predictive_tests.py
python code/magnitude_prediction_test.py
```

| Parameter | Value |
| --------- | ----- |
| Max days per ticker | 500 |
| NMF n_components | min(5, min_train ÷ 5) |
| NMF max_iter | 300 |
| NMF random_state | 42 |
| Tickers | TSLA, DJT, AAPL, MSFT, NVDA, AMC, SNAP, PLTR |

**Pre-computed results**: `results/predictive_tests_*.json`, `results/magnitude_prediction_*.json`

---

### 3.10 Remaining Scripts

```bash
python code/phase4_causal.py          # Lead-lag + Granger (GME, TSLA, DJT)
python code/phase6_robustness.py      # Cross-ticker placebo, OOS NMF, impulse
python code/cycle_periodicity_scanner.py
python code/cycle_deep_dive.py
python code/blended_reflection_pursuit.py
python code/rogue_wave_forensic.py --ticker GME
python code/multi_event_wall_fatigue.py
python code/meteorology_test.py
python code/gamma_reynolds_chart.py
python code/gamma_channel_test.py
streamlit run code/gamma_spectrogram.py   # Interactive app
```

---

## 4. Smoking Gun Evidence Snippets

The following are actual data extracts from the pre-computed results. These
are the key forensic findings referenced in the paper and briefing.

### Smoking Gun 1: Single-Strike COB Wash Trades (Jun 4, 2024)

**Source**: `results/shadow_hunter_GME_20260212_145136.json` → `wash_cross_20240604`

**Summary**: 17 wash pairs found, 16 sub-second, $673,812 total wash capital.

Sample pairs:

```text
Timestamp 1                    Timestamp 2                    Size  Strike  Right  Gap(s)  Exchange  Cond
─────────────────────────────  ─────────────────────────────  ────  ──────  ─────  ──────  ────────  ────
2024-06-04 09:30:02.721000     2024-06-04 09:30:02.721000     100   $10    P      0.000   OPRA      18
2024-06-04 09:34:57.342000     2024-06-04 09:34:57.342000     195   $5     P      0.000   UNK_65    18
2024-06-04 10:17:11.302000     2024-06-04 10:17:11.303000     100   $20    P      0.001   UNK_43    18
```

> **Pattern**: Identical size, price, strike, exchange, condition — only
> timestamps differ by 0–17ms. Same-exchange wash = self-dealing.

---

### Smoking Gun 2: Wash Trade Epidemic (Jun 7, 2024 — Peak Day)

**Source**: `results/shadow_hunter_GME_20260212_145136.json` → `wash_cross_20240607`

**Summary**: 265 wash pairs, 216 sub-second, **$25,942,068** total wash capital.

Sample pairs from the opening bell cluster:

```text
Timestamp 1                    Timestamp 2                    Size  Strike  Right  Gap(s)  Exchange       Cond
─────────────────────────────  ─────────────────────────────  ────  ──────  ─────  ──────  ─────────────  ────
2024-06-07 09:30:25.929000     2024-06-07 09:30:25.929000     100   $10    P      0.000   MIAX_EMERALD   18
2024-06-07 09:30:25.929000     2024-06-07 09:30:25.938000     100   $10    P      0.009   MIAX_EMERALD   18
2024-06-07 09:30:25.929000     2024-06-07 09:30:25.938000     100   $10    P      0.009   MIAX_EMERALD   18
2024-06-07 09:30:25.929000     2024-06-07 09:30:25.938000     100   $10    P      0.009   MIAX_EMERALD   18
2024-06-07 09:30:25.929000     2024-06-07 09:30:25.938000     100   $10    P      0.009   MIAX_EMERALD   18
```

> **Pattern**: 17× $10 Put washes within a 9ms window at market open
> on MIAX Emerald (exchange code 73). All condition=18 (regular trade).

---

### Smoking Gun 3: COB Routing & Dark Volume (Jun 7, 2024)

**Source**: `results/shadow_hunter_GME_20260212_145136.json` → `cob_routing_20240607`

```json
{
  "cob_clusters": 31074,
  "complex_trades": 99712,
  "complex_volume": 438424,
  "dark_clusters": 9867,
  "dark_cob_volume": 94596,
  "total_cob_volume": 355623,
  "total_trades": 506506,
  "verdict": "COB ROUTING — INSTITUTIONAL DARK POOL"
}
```

> **Key stat**: 31,074 COB clusters out of 506,506 total trades (6.1%).
> Complex volume = 438,424 contracts — nearly half a million.

---

### Smoking Gun 4: Algorithmic Stepping / DNA Fingerprint (Jun 4 & Jun 7)

**Source**: `results/shadow_hunter_GME_20260212_145136.json` → `stepping_20240604`, `stepping_20240607`

```text
Jun 4:  13 algorithmic stepping sequences detected (2 dark-venue)
Jun 7:  72 algorithmic stepping sequences detected (16 dark-venue)
```

> **Pattern**: Identical lot-size patterns (e.g., [150, 154, 150])
> repeating across 3.5 years, fingerprinting the same algorithm.

---

### Smoking Gun 5: Dark Venue Routing (Aggregate Jun 2024)

**Source**: `results/shadow_hunter_GME_20260212_145136.json` → `dark_venue`

```json
{
  "dark_pct": "29.4%",
  "total_dark_volume": 975222,
  "total_volume": 3314219,
  "all_exchange_totals": {
    "ISE": 688215,
    "UNK_65": 316986,
    "NSDQ_BX_OPT": 281804,
    "NYSE_AMEX": 266815,
    "UNK_43": 230604
  },
  "dark_exchange_totals": {
    "UNK_65 (EDGX_OPTIONS)": 316986,
    "UNK_43 (EDGX_COB)": 230604,
    "UNK_60 (BZX_OPTIONS)": 140429,
    "UNK_69 (PHLX_FLOOR)": 117924,
    "UNK_73 (MIAX_EMERALD)": 71108
  },
  "verdict": "INSTITUTIONAL DARK ROUTING — HIGH CONCENTRATION"
}
```

> **Key stat**: 29.4% of all GME options volume across the 8-day
> window routed through dark/unmapped venues.

---

### Smoking Gun 6: Tail Banging (Jun 7, 2024)

**Source**: `results/shadow_hunter_GME_20260212_145136.json` → `tail_banging_20240607`

```json
{
  "spot_price": 46.55,
  "total_call_volume": 1290705,
  "tail_trades_count": 5,
  "tail_volume": 2645,
  "tail_capital_burned": 390681.0,
  "top_trades": [
    {"ts": "2024-06-07 09:44:56.330000", "size": 991, "strike": 100.0,
     "price": 1.51, "capital": 149641.0, "otm_pct": "114.8%", "dte": 0,
     "exchange": "MULTI_EXCHANGE", "condition": 18},
    {"ts": "2024-06-07 09:44:36.703000", "size": 400, "strike": 100.0,
     "price": 1.60, "capital": 64000.0, "otm_pct": "114.8%", "dte": 0,
     "exchange": "ISE", "condition": 18},
    {"ts": "2024-06-07 09:44:53.269000", "size": 388, "strike": 100.0,
     "price": 1.60, "capital": 62080.0, "otm_pct": "114.8%", "dte": 0,
     "exchange": "ISE", "condition": 18}
  ],
  "verdict": "TAIL-BANGING PRESENT"
}
```

> **Key stat**: 991-lot trade at $100 strike (114.8% OTM) on 0-DTE
> at 09:44:56 — $149,641 burned on an option that will expire worthless
> in hours. Purpose: force dealers to buy shares to hedge.

---

### Key Manipulation Forensic Findings

**Source**: `results/manipulation_forensic_GME_20260212_135336.json` (Jun 2024)

| Test | Verdict | Key Metric |
| ---- | ------- | ---------- |
| A: Whale Detector | MIXED | Institutional + retail |
| B: Ignition Sequence | ORGANIC | No stealth-then-ignite |
| C: Constructor Fingerprint | INSTITUTIONAL ALGORITHM | High sweep + CVS activity |
| D: Predator Matrix | MINIMAL | 0.7% predator signal |
| E: Lee-Ready Aggressor | DEFENSIVE SELLER | 55% sell-side (hitting Bid) |
| F: Vanna Lag | **VANNA ARB DETECTED** | LEAPS trail short-dated by **9 min**, r=+0.2 |

---

### Key Squeeze Mechanics Finding

**Source**: `results/squeeze_mechanics_GME_20260212_104815.json`

| Metric | Squeeze | Counterfactual | Z-Score |
| ------ | ------- | -------------- | ------- |
| Wall breach rate | 63.9% | 25.1% | 7.15 |

---

## 5. Verifying Pre-Computed Results

All 113 pre-computed JSON results are in `results/`. To inspect any result:

```bash
python -m json.tool results/<filename>.json | head -50
```

### Key Result Files

| Result File | Key Finding |
| ----------- | ----------- |
| `shadow_hunter_GME_20260212_145136.json` | All smoking guns with full evidence payloads |
| `manipulation_forensic_GME_20260212_135324.json` | Jan 2021: 78 sub-second wash pairs, 21K+ COB clusters |
| `manipulation_forensic_GME_20260212_135336.json` | Jun 2024: 265 wash pairs, 216 sub-second |
| `panel_scan_results.json` | 37-ticker panel: mean ACF₁ = −0.203, all dampened |
| `stacking_resonance_GME_20260212_091722.json` | Stacking Δ ACF = −0.101, p = 0.008 |
| `squeeze_mechanics_GME_20260212_104815.json` | 63.9% breach rate vs 25.1% counterfactual (Z = 7.15) |
| `counterfactual_GME_20260212_111301.json` | Full squeeze vs counterfactual comparison |
| `phase4a_leadlag_GME.json` | Lead-lag and Granger causality results |
| `phase5c_archaeology_GME.json` | NMF temporal reconstruction |

---

## 6. Environment Setup

```bash
pip install -r requirements.txt
```

For full replication (not just viewing results):

```bash
export POLYGON_API_KEY=<your_key>
# Ensure ThetaData Theta Terminal is running on localhost:25510
```
