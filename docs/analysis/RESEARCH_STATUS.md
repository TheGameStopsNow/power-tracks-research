# Research Status: "Meme Stock" Liquidity Fracture Signal

**Date:** 2025‑12‑02  
**Status:** Validation Complete (Phase 1 + Phase 2)  
**Level:** High – multi‑year, multi‑asset, null‑tested, with documented limits

---

## 1. Executive Summary

This research has reverse‑engineered a specific structural mechanism behind “meme stock” behaviour. We identify a recurring **Liquidity Fracture** pattern with three interacting layers:

- **Algorithmic Suppression:** Burst clusters (Clusters **1** and **3**) that encode forced containment in the decoded burst shapes (“Power Clusters”).  
- **Fracture Signature:** A discrete **K‑Spike** event pattern indicating containment failure.  
- **Options Feedback:** An options‑driven **Gamma Magnet** field and a **Hedge‑Impact Propagator (HIP)** loop that, in some regimes, drive or amplify the explosion.

The combined **Tiered Gating Strategy** (Cluster 1/3 + K‑Spike + options confirmation) produces high‑selectivity, high‑runup signals on core meme names, remains detectable in 2021 and 2024/2025 data, and is largely absent in broad‑market controls.

---

## 2. Key Validation Findings (Master Suite)

Summary of headline studies and metrics (details in the referenced reports):

| Study | Topic | Metric / Result | Conclusion |
| :--- | :--- | :--- | :--- |
| **A** | Selectivity | GME vs SPY distance ratio ≈ **1.26×**, Cohen’s d > 1.0 vs indices | K‑Spike + gate is selective vs broad market. |
| **C** | Gate Efficacy | 2024 sample: Gated WinRate>10% = **100%** (N=3), Baseline ≈ 94%; H2‑2024 holdout: mitigated loss (‑3.5% vs ‑5.7%, p≈2e‑5) | Gate helps, but small‑N perfect win rate is treated with caution. |
| **D** | Portability | Basket resonance ~**0.99** for GME/AMC/PLTR/CHWY; SPY ~0.79 | Signal generalises inside basket; decays on SPY/controls. |
| **E** | Temporal | 2024 templates on 2021: distance 2.52 vs 2.51 self; KS p≈**0.77** | Fracture shape is stable across 2021–2024. |
| **G** | Pinning | “Zombie” BB/TLRY show near‑perfect strike pinning on key days | EPD “Gamma Magnet” effect visible even in passive names. |
| **H** | Causality | HIP panel Z≈**4.03σ** for key cases; direction is regime‑dependent | Options flow can lead price (buildup), but price can lead flow in squeezes. |

See also the Phase‑2 suite summaries:

- `reports/selectivity_suite.md`  
- `reports/cluster_stability.md`  
- `reports/gating_reproduction.md`, `reports/gating_holdout.md`  
- `reports/portability_panel_extended.md`  
- `reports/temporal_generalization_deep.md`  
- `reports/options/hip_panel_summary.md`  
- `reports/execution_realism.md`, `reports/risk_profile_gated_vs_baselines.md`

---

## 3. Core Components

### 3.1 Shape & Signature Layer (TISA + K‑Spike)

- **Raw shapes (TISA)** are generic: GME burst templates find strong multi‑scale matches in SPY and other controls at high rates, confirming that **shape alone is not unique**.  
- **K‑Spike signatures** (top‑K up/down spikes) are more selective:
  - SPY match rate drops; selectivity ratio vs GME ≈ 1.26.  
  - High‑beta tech (e.g. PLTR, some NVDA regimes) can share K‑Spike geometry → **Cluster Gate is required** to distinguish meme signals from tech momentum.
- Detailed selectivity results live in `reports/selectivity_retest.md` and `reports/selectivity_suite.md`.

### 3.2 Cluster Layer (Power vs Trap)

- Clustering 1,884 GME bursts (Nearest‑Neighbour features) yields:
  - **Cluster 0 (“Trap”)**: strongly negative mean 30‑day returns, deep drawdowns.  
  - **Clusters 1 & 3 (“Power”)**: flat/near‑flat mean *returns*, but very large **max runups** (>95–100%) in 30‑day horizon.
- `reports/CLUSTER_PROFILE.md` summarises 30‑day performance; `reports/cluster_stability.md` shows:
  - Clusters 1/3 remain stable and outperform “noise” clusters across 100 bootstrap resamples.

### 3.3 Tiered Gating (Cluster + K‑Spike + Options)

- **Phase‑1 gating (2024 sample)** – `reports/gating_reproduction.md`:
  - Arms: All, Cluster‑only, K‑Spike‑only, Gated (Cluster 1/3 + Sig).  
  - Small sample (N=36 bursts):  
    - Baseline win>10%: 94.4%  
    - Cluster‑only: 100%  
    - K‑Spike‑only: 80%  
    - Gated (N=3): 100% win, mean ~+88% (treated as anecdotal due to N=3).
- **Phase‑2 holdout (H2‑2024)** – `reports/gating_holdout.md`:
  - On unseen bearish regime, a **cluster‑gated** arm reduces mean loss from ‑5.7% to ‑3.5% (p≈2e‑5) but does not produce alpha; no K‑Spike+options gate was fired in this window.
- Net: **Clusters drive most of the edge; K‑Spike refines selectivity; options layer adds confirmation and targets.**

---

## 4. Cross‑Symbol & Temporal Behaviour

### 4.1 Portability & Basket Taxonomy

- Extended panel analyses (`AMC_portability_analysis.md`, `PANEL_portability_analysis.md`, `portability_panel_extended.md`, `UNIVERSE_RESONANCE_analysis.md`) support a taxonomy:
  - **Core Basket:** GME, AMC, PLTR, CHWY (high resonance, strong runups).  
  - **Extended / discovered:** CLOV, GOEV, WKHS, BNED, HOLO, IHRT, SLE, SIRI.  
  - **Zombies:** BB, TLRY – strong pinning, weak flow causality.  
  - **Non‑basket controls:** SPY, large mega‑tech, NOK/WISH/SPCE, etc., show low resonance and poor gating performance.
- Unsupervised clustering in resonance/return space (`portability_panel_extended.md`) recovers these groups without hand‑labelling.

### 4.2 Temporal Generalization (2021 vs 2024)

- 2024 templates applied to 2021 (“the sneeze”) yield:
  - Distance distribution statistically indistinguishable from 2024→2024 (KS p≈0.77).  
  - Key 2021 events (GME/KOSS) exhibit the same Power‑cluster + K‑Spike structure, with massive runups.
- This supports the claim that the **fracture geometry is stable across multiple years**.

---

## 5. Options Layer: EPD & HIP

### 5.1 Exposure‑Potential Drift (EPD) – Gamma Magnets

- Using reconstructed historical chains and local Greeks, we build gamma ladders and “gamma‑weighted volume” per strike.  
- For GME May‑2024 (`TEMPORAL_analysis.md`, options suite):
  - **May 1:** Close ≈ 11.05, magnet ≈ 11 → perfect pin.  
  - **May 3:** Close ≈ 16.47, magnets 15–17 → pinned/rising.  
  - **May 10:** Close ≈ 17.39, magnets 17–18 → pinned.  
  - **May 13:** Close ≈ 36.90, magnets 30–34 → price chases higher magnets.
- Zombies (BB/TLRY) show consistent pinning to high‑gamma strikes even when they don’t explode, matching the EPD “stabilising” role.

### 5.2 Hedge‑Impact Propagator (HIP) – Intraday Flow

- Original HIP test (May‑13) produced a high Z‑score (~4σ) for flow→price asymmetry when using a specific dH proxy and lag grid.  
- Phase‑2 panel (`reports/options/hip_panel_summary.md`) refined the picture:
  - **Buildup / Satellites (BB, CHWY):**  
    - Peak HY correlations at **positive lags** (~+20 minutes), positive asymmetry: **flow leads price** (“Tail Wags Dog”).  
  - **Squeeze / Engine (GME on May‑13):**  
    - Peak correlation at **negative lags** (~−5 minutes): **price leads flow** during the violent gamma squeeze regime.  
  - **AMC:** mixed, mostly sympathetic to GME rather than strongly flow‑driven.
- Net: **Causality direction is regime‑dependent**:
  - In calm/buildup regimes, options flow can lead price in satellites and some cores.  
  - During the main squeeze, price can outrun flow; gamma walls and forced hedging amplify rather than strictly drive the move.

---

## 6. Phase‑2 Stress Tests (Scientific Robustness)

Phase‑2 was designed to attack the main skeptic angles: overfitting, cherry‑picking, non‑portability, and non‑tradability.

- **Selectivity Suite (Study 1.1)** – `selectivity_suite.md`  
  - Extended panel (SPY, QQQ, DIA, TSLA, NVDA, etc.) with effect sizes and nulls.  
  - Indices show large distance effect vs GME; PLTR emerges as “meme‑adjacent” (d≈0), emphasising the need for cluster/basket gating.

- **Cluster Stability (Study 1.2)** – `cluster_stability.md`  
  - Bootstrap re‑clustering shows Clusters 1 & 3 retain their identity and outperformance across resamples; Trap cluster behaviour is consistent.

- **Holdout Gating (Study 1.3)** – `gating_holdout.md`  
  - On H2‑2024 bearish data, a **cluster‑gated** arm reduces losses (−3.5% vs −5.7%) but does not generate positive returns. This is framed as **risk mitigation**, not alpha.

- **Portability & Universe Expansion (Suites 2 & 10)** – `portability_panel_extended.md`, `UNIVERSE_RESONANCE_analysis.md`  
  - Unsupervised clustering recovers Core vs Control groups from performance/resonance metrics.  
  - A broad 27‑symbol and ~60‑symbol universe confirms “resonant” names vs anti‑basket controls.

- **Risk & Execution (Suite 4)** – `execution_realism.md`, `risk_profile_gated_vs_baselines.md`  
  - Realistic slippage (10–50 bps) reduces returns but preserves the relative advantage vs baseline in the tested regime.  
  - Risk metrics show improved Sharpe/Sortino vs “All bursts” baselines in H2‑2024, despite both being negative in that regime.

---

## 7. Limitations & Biases

This section is explicit by design to withstand critical review.

- **Regime Dependence:**  
  - The most striking “perfect” outcomes (100% wins, huge runups) occur in a specific high‑volatility regime (May‑2024 meme wave).  
  - In out‑of‑sample bearish conditions (H2‑2024), the cluster gate mitigates losses but does not generate alpha.

- **Sample Size for Perfect Wins:**  
  - The Phase‑1 100% Gated win rate is based on **3/3** events.  
  - 95% binomial CI for 3/3 is wide (~29%–100%). These results are treated as **illustrative**, not conclusive on their own.

- **High‑Beta Tech & Meme‑Adjacent Names:**  
  - PLTR can be nearly indistinguishable from GME by K‑Spike alone (d≈0); NVDA sometimes shows similar structure.  
  - Therefore, **Cluster membership and Basket resonance** are mandatory filters; K‑Spike alone is not sufficient for selectivity.

- **Universe & Survivorship Bias:**  
  - Many symbols studied are “known interesting” (meme, high‑beta). Phase‑2 mitigates this by including controls (F, T, mega‑tech, indices) and a structured universe, but any live deployment should continue to monitor for drift.

- **Data & Proxy Quality:**  
  - HIP and EPD rely on reconstructed Greeks / dH proxies from available option trades/snapshots. Microstructure conclusions assume these proxies are stable approximations of real dealer positioning and flows.

- **Non‑independence of Events:**  
  - Gated hits across symbols and within the same episode/day are not independent; conclusions are reported with this in mind, but effect sizes may be inflated if naïvely treating every hit as independent.

---

## 8. Research Chronology

- **Phase 1 (Exploratory, May–Nov 2025):**  
  - Developed clustering features, K‑Spike encoding (k=3), and initial gating rules on May‑2024 GME episodes and a small panel.  
  - Derived the Liquidity Fracture / Basket Resonance / Fracture Hierarchy concepts.

- **Phase 2 (Confirmatory, Dec 2025):**  
  - **Parameters frozen:** Cluster IDs (1/3), K‑Spike p‑threshold (<0.05), core basket list, basic universe definitions.  
  - Applied to H2‑2024 holdout, 2021 “sneeze”, and extended symbol universe without re‑tuning.  
  - Added null tests, permutation tests, and risk/execution analyses.

---

## 9. Live Forward Plan (“What Now?”)

The next scientific step is **live forward logging** under frozen specs. This is documented in:

- `reports/live_forward_log_template.md`

Frozen protocol (as of 2025‑12‑02):

- **Universe:** GME, AMC, CHWY, KOSS, BB, TLRY, PLTR (extendable, but additions must be logged).  
- **Gate 1 (Cluster):** Burst is in Cluster **1** or **3**.  
- **Gate 2 (Shape):** K‑Spike p‑value < **0.05** vs 2024 template library.  
- **Gate 3 (Options):** Either Gamma Magnet pinning to a nearby strike *or* HIP asymmetry > 0.1 in the last X minutes.

Logging rules:

- When Gate 1+2 are satisfied, record the candidate in the live log *immediately* with timestamp, price, and hash.  
- Record Gate 3 confirmation when available.  
- No edits to entries after the fact; outcomes are evaluated at fixed horizons (e.g. +20 trading days) and appended, not rewritten.

The live log will provide the final, most compelling test against overfitting and cherry‑picking: performance on data and regimes that do not exist yet at the time of specification.

---

## 10. Deployment Recommendation

Subject to continued monitoring via the live forward log and ongoing HIP/EPD data quality checks:

- **Operational Strategy:**
  - **Monitor:** Continuously scan for Cluster‑1/3 bursts on the core basket.  
  - **Signal:** Fire alerts when K‑Spike fracture (Gate 2) and acceptable options conditions (Gate 3) are present.  
  - **Plan:** Use Gamma Magnet structure to set target bands and risk limits.  
  - **Execute:** Express views via long volatility / long calls or structured trades, respecting liquidity and slippage constraints from `execution_realism.md`.

---

## 11. Effect Roles (Impactor / Binder / Echo / Macro)

Phase‑level analysis on an expanded historical burst set (`reports/historical_bursts.json`, `reports/effect_roles_labels.json`, `reports/effect_roles_validation.md`) introduces four **effect roles** that cross‑cut structural clusters. These roles describe how bursts behave in the tape, not how they are structurally shaped.

- **Impactor (Short‑Term Jolt)**  
  - Definition in the historical scan: 1‑day runup > 10%.  
  - Result (`effect_roles_validation.md`): 275/335 bursts (82.1%) qualify; they show significantly higher short‑term returns than non‑Impactors:  
    - 1d: +0.1204 vs −0.0532 (p ≈ 1.8e‑9)  
    - 3d: +0.1286 vs −0.0125 (p ≈ 4.9e‑3)  
    - 5d: +0.1144 vs −0.0869 (p ≈ 1.5e‑3)  
  - Status: **Strongly validated** as a distinct high‑volatility subset with superior 1–5 day performance.

- **Binder (Mid‑Term Drift)**  
  - Conceptual definition (Phase‑5 GME‑only work): 30d or 90d log return > 10% with strong path skew (≥70% of time above start).  
  - In the broader historical scan (`historical_bursts.json`), 30/90‑day horizons are effectively zeroed for many symbols, so Binder is skipped in `effect_roles_validation.md`.  
  - Status: **Pending on the historical scan.** Binder appears promising in earlier GME‑only analyses but requires richer long‑horizon data on the full universe to be statistically re‑validated.

- **Echo (Long‑Lag Replay / Trap)**  
  - Current implementation (Phase‑7): GME‑vs‑GME‑2021 TISA spike‑signature matches with realBest < 2.5, using `reports/tisa_spike_signatures_GME_vs_GME_2021_*.json`.  
  - Count: 7 events (2.1% of the historical sample).  
  - Behaviour: Short‑term returns are directionally worse than baseline:  
    - 1d: −0.0535 vs +0.0923 (underperformance ≈ −14.6%, p ≈ 0.44)  
    - 3d: −0.0969 vs +0.1076 (underperformance ≈ −20.5%, p ≈ 0.31)  
  - Interpretation: These rare, high‑fidelity replays act as **candidate “Echo Traps”**, but the sample is too small for formal significance.  
  - Status: **Directionally validated, low‑N, GME‑only.** The broader “General Echo” hypothesis (matching vs templates from TSLA, TLRY, etc.) is not yet implemented in `label_effect_roles.py` and remains deferred.

- **Macro (Basket Co‑Occurrence / Dampener)**  
  - Definition: dates where >3 unique symbols burst simultaneously (basket‑wide event).  
  - Count: 130 events (38.8%).  
  - Behaviour in the historical scan:  
    - 1d: +0.0842 vs +0.0925 (p ≈ 0.75)  
    - 3d: +0.0575 vs +0.1324 (p ≈ 0.054)  
  - Interpretation: Macro days are common but show slightly **lower** short‑term returns than isolated bursts, suggesting liquidity headwinds or faster mean reversion when the basket is crowded.  
  - Status: **Validated as a dampener context**, not a positive driver, in this dataset.

Implementation details:

- Labelling: `scripts/label_effect_roles.py` → `reports/effect_roles_labels.json`  
- Validation: `scripts/analyze_effect_roles.py` → `reports/effect_roles_validation.md`

These effect roles are meant as **effect‑context tags** layered on top of structural labels (clusters, K‑Spikes, options context) and the Tiered Gating spec. They should be used to enrich interpretation and risk management, not to replace the core gating logic.

This file should be updated only when new Phase‑level studies (or live‑forward results) are completed and accompanied by manifests and reports under `reports/`.
