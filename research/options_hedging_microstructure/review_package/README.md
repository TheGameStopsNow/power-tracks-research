# Review Package — Options Hedging & Market Microstructure

> **Self-contained replication and evidence package for forensic analysis of options-equity feedback mechanisms and adversarial manipulation of the volatility surface infrastructure.**

---

## Package Contents

### 📄 Manuscripts

| File | Description |
|------|-------------|
| **[`final.md`](./final.md)** | Full research paper (parent directory). Covers ACF spectrum analysis, NMF temporal archaeology, DTE stratification, and adversarial forensic findings (§4.23–4.25). |
| **`REPLICATION_GUIDE.md`** | **Exact dates, commands, and parameters to reproduce every test.** Start here for replication. |

---

### 📓 Jupyter Notebooks

| Notebook | Requirements | Description |
|----------|-------------|-------------|
| **`01_evidence_viewer.ipynb`** | **None** — zero setup | Loads all 89 pre-computed JSON results. Renders smoking guns, panel ACF, manipulation forensic battery, squeeze mechanics, NMF archaeology, and claim verification matrix. **Start here.** |
| **`02_forensic_replication.ipynb`** | ThetaData + Polygon API | Re-runs Shadow Hunter, Manipulation Forensic, Squeeze Mechanics, and Counterfactual Analysis. Falls back to pre-computed results if data is unavailable. |
| **`03_microstructure_replication.ipynb`** | Polygon + ThetaData API | Re-runs Panel ACF Scan, ACF Engines, Lead-Lag, NMF Archaeology, Robustness, and Stacking Resonance. Falls back to pre-computed results if data is unavailable. |

---

### 📊 Data Outputs

| File | Description |
|------|-------------|
| **`data_outputs/SUMMARY_TABLES.md`** | Consolidated summary of all key statistical tables referenced in the paper. |

---

### 🔬 Evidence & Briefings

| File | Description |
|------|-------------|
| **`BRIEFING.md`** | Executive briefing document summarizing the six smoking guns, the Rule 10b-5 element analysis, and the FINRA CAT attribution roadmap. |

---

### 📢 Reddit Post Series

| File | Characters | Description |
|------|:----------:|-------------|
| **`REDDIT_POST_PART1.md`** | ~23,600 | Part 1: Long Gamma Default mechanism, Shadow Algorithm forensics (tail-banging, wash trades, dark venues, Vanna lag), all six smoking guns with timestamps and dollar amounts, 10b-5 element mapping. |
| **`REDDIT_POST_PART2.md`** | ~12,000 | Part 2: Player Piano discovery (r = 1.000), five FINRA CAT attribution queries, why surveillance missed it, and actionable items. |
| **`REDDIT_COMPILED.md`** | ~35,600 | Both parts concatenated into a single document for reference. |

---

### 💻 Code (`code/`)

All Python scripts used to generate the results referenced in the paper. Requires a ThetaData V3 API subscription for data access and a Python 3.10+ environment.

#### Core Forensic Analysis
| Script | Description |
|--------|-------------|
| `manipulation_forensic.py` | **Primary forensic engine.** Runs all five adversarial tests: tail-banging detection, wash/cross trade pairing, COB cluster analysis, dark venue de-masking, and Vanna lag channel detection. Generates the evidence for §4.23. |
| `shadow_hunter.py` | **Six smoking guns detector.** Identifies single-strike COB washes, algorithmic DNA matches, tape smurfing, Jelly Roll synthetic shorts, opening bell put washes, and cross-venue swarm attacks. Generates evidence for §4.24. |
| `squeeze_mechanics_forensic.py` | Squeeze mechanics analysis — models the gamma feedback loop through the January 2021 and June 2024 events. |
| `rogue_wave_forensic.py` | Rogue wave detection — identifies anomalous volume bursts and their relationship to options chain configurations. |

#### ACF & Microstructure Engines
| Script | Description |
|--------|-------------|
| `phase3_acf_engines.py` | Core ACF computation engine — computes 1-minute return autocorrelation across configurable bin widths. |
| `phase3_remaining.py` | Extended ACF analysis — multi-lag, multi-scale, and rolling-window computations. |
| `gamma_spectrogram.py` | Interactive Streamlit app for visualizing gamma spectrograms across expiration dates. |
| `gamma_reynolds_chart.py` | Computes and charts the Gamma Reynolds Number ($Re_\Gamma$) for regime classification. |
| `gamma_channel_test.py` | Tests the gamma channel hypothesis — does options flow drive equity microstructure changes? |
| `panel_scan.py` | Panel scan across 37 tickers — computes ACF statistics for the full cross-sectional sample. |

#### Causal & Predictive Analysis
| Script | Description |
|--------|-------------|
| `phase4_causal.py` | Lead-lag and Granger causality tests between options flow and equity ACF regime shifts. |
| `phase5_paradigm.py` | NMF temporal archaeology — decomposes equity volume profiles into options-driven basis vectors. Implements the Strict Temporal Archaeology protocol. |
| `phase6_robustness.py` | Robustness tests — cross-ticker placebo, out-of-sample NMF, lead-lag placebo, impulse response kernels. |
| `predictive_tests.py` | Out-of-sample predictive tests — ACF magnitude prediction, realized volatility forecasting, and volume profile matching. |
| `counterfactual_analysis.py` | Counterfactual analysis — what would equity microstructure look like without options hedging? |
| `magnitude_prediction_test.py` | Continuous ACF magnitude prediction using lagged options features. |

#### Cycle & Pattern Analysis
| Script | Description |
|--------|-------------|
| `cycle_periodicity_scanner.py` | FFT-based cycle detection across price, volume, and volatility series. |
| `cycle_deep_dive.py` | Deep dive into detected periodicities — rolling spectral windows, mirror hypothesis testing, Monte Carlo significance. |
| `blended_reflection_pursuit.py` | Blended reflection hypothesis — systematic cadence × offset sweep matrix. |
| `stacking_resonance_test.py` | Tests whether multiple expiration stacking creates resonance effects in equity microstructure. |
| `multi_event_wall_fatigue.py` | Multi-event gamma wall fatigue analysis across repeated expiration cycles. |
| `meteorology_test.py` | "Weather map" analysis — spatial patterns in the ACF spectrum across strike and DTE dimensions. |

#### Data Utilities
| Script | Description |
|--------|-------------|
| `fetch_early_data.py` | Fetches historical equity data for early trading dates. |
| `fetch_gap_data.py` | Fills data gaps in the historical record. |

---

### 📁 Results (`results/`)

89 JSON files containing all pre-computed analysis outputs. Key files:

#### Forensic Evidence (GME)
| File Pattern | Description |
|-------------|-------------|
| `manipulation_forensic_GME_*.json` | Raw forensic test outputs — tail-bangs, wash pairs, COB clusters, dark venue volumes. Multiple runs with progressively refined detection parameters. |
| `shadow_hunter_GME_*.json` | Six smoking guns extraction — full evidence payloads with timestamps, lot sizes, exchange codes, and dollar amounts. |
| `squeeze_mechanics_GME_*.json` | Squeeze mechanics model outputs — gamma feedback loop quantification. |
| `rogue_wave_GME_*.json` | Rogue wave detection results. |

#### ACF & Cross-Sectional
| File Pattern | Description |
|-------------|-------------|
| `intraday_acf_*.json` | Per-ticker intraday ACF results (AAPL, AMC, DJT, GME, MSFT, TSLA). |
| `multiscale_acf_*.json` | Multi-scale ACF (30s, 1m, 5m, 15m, 30m bins) per ticker. |
| `panel_scan_results.json` | Full 37-ticker panel scan — ACF statistics for cross-sectional analysis. |

#### Causal & NMF
| File Pattern | Description |
|-------------|-------------|
| `phase4a_leadlag_*.json` | Lead-lag analysis per ticker. |
| `phase4b_shadow_GME.json` | Shadow channel (Vanna lag) raw detection data. |
| `phase5a_kernel_*.json` | Temporal convolution kernels per ticker. |
| `phase5b_heatmap_*.json` | NMF heatmap data per ticker. |
| `phase5c_archaeology_*.json` | NMF temporal archaeology results — standard, strict, and residual variants. |

#### Robustness & Predictive
| File Pattern | Description |
|-------------|-------------|
| `phase6a_cross_ticker_placebo.json` | Cross-ticker NMF placebo test. |
| `phase6b_oos_nmf.json` | Out-of-sample NMF reconstruction results. |
| `phase6c_leadlag_placebo.json` | Lead-lag placebo test results. |
| `phase6d_impulse_kernel.json` | Impulse response kernel analysis. |
| `predictive_tests_*.json` | Out-of-sample prediction results. |
| `counterfactual_GME_*.json` | Counterfactual analysis outputs. |

#### Cycle & Pattern
| File Pattern | Description |
|-------------|-------------|
| `cycle_periodicity_results.json` | FFT periodicity detection results. |
| `cycle_deep_dive_results.json` | Deep periodicity analysis outputs. |
| `blended_reflection_results.json` | Cadence × offset sweep matrix results. |
| `stacking_resonance_*.json` | Per-ticker stacking resonance test outputs. |
| `multi_event_wall_fatigue_*.json` | Gamma wall fatigue analysis. |
| `decay_curves.json` | Temporal decay curve data. |
| `volume_proxy_scatter.json` | Volume proxy scatter data. |
| `contagion_GME.json` | Cross-ticker contagion analysis. |

---

### 🖼️ Figures (`figures/`)

20 visualization assets: technical charts (energy concentration, gamma Reynolds, density heatmaps, DTE volume, flow fields) and conceptual illustrations.

---

## Requirements

```bash
pip install -r requirements.txt
```

- **Python 3.10+**
- **ThetaData V3 API** subscription (for data access; pre-computed results are included)
- **Polygon.io API** (for equity data; set `POLYGON_API_KEY` env var)
- See `requirements.txt` for full dependency list

## Quick Start

```bash
# 1. View pre-computed results (no API needed)
python -m json.tool results/shadow_hunter_GME_20260212_145136.json | head -100

# 2. Read the replication guide for exact dates and commands
cat REPLICATION_GUIDE.md

# 3. Run forensic analysis (requires ThetaData + Polygon APIs)
python code/manipulation_forensic.py --event both --ticker GME
python code/shadow_hunter.py --ticker GME

# 4. Launch interactive gamma spectrogram
streamlit run code/gamma_spectrogram.py
```

## Key Event Dates for Replication

| Event | Ticker | Key Dates | Target Expiry |
|-------|--------|-----------|---------------|
| Jan 2021 Squeeze | GME | 2021-01-22 through 2021-01-29 | 20210129 |
| Jun 2024 Squeeze | GME | 2024-06-04 through 2024-06-21 | 20240621 |
| DJT SPAC Merger | DJT | 2024-03-26 (peak) | N/A |

> See **`REPLICATION_GUIDE.md`** for complete date tables, exact commands, and parameter settings.

---

## License

This research is released for independent verification and academic review. All analysis is reproducible from public market data.
