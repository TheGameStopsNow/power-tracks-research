# Compiled Data Outputs — Summary Tables

## 1. Panel ACF Results (Top 15 by Observation Count)

| Ticker | Obs Days | Mean ACF₁ | % Dampened | Regime |
|--------|:--------:|:---------:|:----------:|:------:|
| GME | 1,531 | −0.154 | 76% | Dampened (post-squeeze) |
| TSLA | 1,200+ | −0.203 | 91% | Dampened |
| AAPL | 1,200+ | −0.245 | 95% | Dampened |
| MSFT | 1,200+ | −0.188 | 93% | Dampened |
| NVDA | 1,200+ | −0.213 | 94% | Dampened |
| AMD | 800+ | −0.198 | 92% | Dampened |
| AMZN | 1,200+ | −0.231 | 94% | Dampened |
| META | 1,000+ | −0.207 | 93% | Dampened |
| DJT | 200+ | −0.168 | 85% | Dampened |
| AMC | 400+ | −0.143 | 78% | Dampened |
| SNAP | 600+ | −0.176 | 89% | Dampened |
| PLTR | 500+ | −0.191 | 91% | Dampened |
| SPY | 1,200+ | −0.288 | 97% | Strongly Dampened |
| SOFI | 300+ | −0.162 | 86% | Dampened |
| RDDT | 100+ | −0.195 | 91% | Dampened |

**Panel mean ACF₁ = −0.203 across all 37 tickers**

---

## 2. Stacking Resonance (8 Tickers)

| Ticker | Exps | ACF₁ Hi Stack | ACF₁ Lo Stack | Δ ACF | p-value | Direction | Charm Matches | Disp% |
|--------|:----:|:-------------:|:-------------:|:-----:|:-------:|:---------:|:------------:|:-----:|
| **GME** | 252 | −0.250 | −0.150 | **−0.101** | **0.008** | **Dampen** | 3/10 | 88% |
| **AAPL** | 89 | −0.217 | −0.255 | **+0.038** | **0.044** | **Amplify** | 10/10 | 94% |
| TSLA | 100 | −0.128 | −0.129 | +0.001 | 0.978 | Neutral | 5/10 | 60% |
| NVDA | 64 | −0.197 | −0.196 | −0.001 | 0.972 | Neutral | 6/10 | 95% |
| PLTR | 41 | −0.055 | −0.078 | +0.023 | 0.693 | Neutral | 0/5 | 90% |
| **AMD** | 26 | −0.241 | −0.124 | **−0.118** | **0.016** | **Dampen** | 7/10 | 88% |
| SPY | 34 | −0.140 | −0.173 | +0.034 | 0.169 | Mild Amp | 3/10 | 88% |
| SNAP | 17 | −0.198 | −0.209 | +0.012 | 0.667 | Neutral | 2/10 | 94% |

**Key**: GME/AMD show significant dampening under stacking; AAPL shows significant amplification. Dispersion buying is universal (60-95%).

---

## 3. Squeeze Mechanics — GME (Black-Scholes Delta)

### Jan 2021 Squeeze Window
- Dealer mean Bδ: **−0.45** (significantly short gamma)
- Breach rate: **63.9%** (vs. 25.1% counterfactual, Z=7.15)
- Wall-approach accuracy: 100% hold in 5-day window
- Counter-direction flip rate: 89%

### Post-Squeeze (2024-2026)
- Dealer mean Bδ: **−0.18** (moderately long gamma)
- Breach rate: 31% (consistent with dampening)
- Counterfactual difference: 44σ

---

## 4. Spear Tip Pattern Scanner — GME

### Jan 2021 (Target: 20210129)
- **Gini coefficient**: 0.838 → ENGINEERED
- First OI date: Dec 11, 2020
- Peak OI: 449,758 (Jan 27, 2021)
- **51.8% of OI added in final 7 days**
- Largest injection: +151,578 contracts on Jan 26 (DTE=3)
- Put OI dominated at peak (297,624 puts vs 152,134 calls)
- Top call strikes: $200, $115, $60

### Jun 2024 (Target: 20240621)
- **Gini coefficient**: 0.880 → ENGINEERED
- Peak OI: 1,082,082 (Jun 21, 2024)
- **42.1% of OI at T-30 to T-7, stepped buildup pattern**
- Largest injection: +121,028 contracts on Jun 18 (DTE=3)
- Call OI dominated at peak (731,483 calls vs 350,599 puts)
- Top call strike: $125 with 132,309 OI

---

## 5. Vanna Shock Amplifier — GME

### Jan 2021
- LEAPS contracts (DTE>180): 197
- Total LEAPS OI: 125,127
- Pre-squeeze LEAPS delta: +4,564,077 shares
- Peak-squeeze LEAPS delta: +5,660,304 shares
- **Forced hedging: +1,096,227 shares (1.2× amplification)**
- Top shock: $30C (DTE=183), δ 0.73→1.00, +55K shares

### Jun 2024
- LEAPS contracts (DTE>180): 259
- Total LEAPS OI: 110,724
- Pre-squeeze LEAPS delta: +1,799,664 shares
- Peak-squeeze LEAPS delta: +6,580,947 shares
- **Forced hedging: +4,781,283 shares (3.7× amplification)**
- Top shock: $60C (DTE=238), δ 0.09→0.90 (9.7×), +1,410,200 shares
- **$125C (DTE=238): δ 0.007→0.830 (120.6×), +358,452 shares**

---

## 6. Counterfactual Analysis

Randomized 10,000 expiration schedules and compared to real:
- Real breach rate: 63.9%
- Counterfactual mean: 25.1%
- **Z-score: 7.15** (p < 10⁻¹²)
- Dealer delta deviation: 44σ above counterfactual

---

## 7. Robustness Results

| Test | Result | Interpretation |
|------|--------|---------------|
| Cross-ticker placebo | r ≈ 1.000 carrier wave | Universal structure, not ticker-specific |
| Strict archaeology (OOS) | r = 0.25-0.50 for residuals | Options history predicts 25-50% of unique variance |
| Lead-lag placebo | No cross-ticker signal | Causal link is ticker-specific, not market-wide |
| Variance ratio | Consistent with mean-reversion at 2-20 periods | Dampening operates across scales |
| Bootstrap CI | 95% CI excludes zero for all tickers | Panel result is robust to resampling |
| Wall fatigue | 100% hold rate in approach window | Gamma walls are persistent within event |
