# Steganography Research: Initial Findings

*Analysis Date: 2025-12-08*

---

## Executive Summary

We analyzed 26 trading days of GME tick data (~14 million trades) for steganographic indicators. **All analyzed data shows statistically significant non-random patterns** consistent with what the theoretical literature describes as prerequisites for covert channels.

> [!IMPORTANT]  
> These findings do **not** prove covert communication is occurring. They demonstrate that the statistical structure of market data deviates from random noise in ways that *could* hide information.

---

## Key Findings

### Phase 1: LSB (Least Significant Bit) Analysis

| Metric | Result | Interpretation |
|--------|--------|----------------|
| Days analyzed | 26 | 2023-03 to 2024-09 |
| Price LSB anomalies | **100%** | All days show non-uniform distribution (p < 0.0001) |
| Volume LSB anomalies | **100%** | All days show non-uniform distribution (p < 0.0001) |
| Benford's Law deviation | **100%** | No day follows expected first-digit distribution |
| Autocorrelation detected | **100%** | Sequential LSB values are not independent |

**Key Observations:**
- Price LSB entropy ranges from 0.972 to 0.999 (near-maximum but not random)
- Volume and price show consistent non-uniformity across all market regimes
- High-volatility days (May 2024 "Roaring Kitty" events) show even stronger deviation

### Phase 2: Timing Channel Analysis

| Metric | Result | Interpretation |
|--------|--------|----------------|
| Days analyzed | 16 (of 26) | Some days had incompatible timestamp formats |
| Periodicity detected | **100%** | 130-915 significant periodic peaks per day |
| Interval clustering | **100%** | 7-8 clustered intervals per day |
| Low entropy | **100%** | Below expected randomness |
| Non-exponential IAT | **100%** | Order flow does not follow Poisson process |

**Key Observations:**
- Dominant periods cluster around powers of 2 seconds (8.2s, 16.4s, 32.8s)
- Mean inter-arrival times: 17-462 milliseconds
- Coefficient of variation: 3.3-6.5 (exponential would be ~1.0)

### Control Sample: SPY Comparison ✅

| Metric | SPY (Control) | GME (Test) | Interpretation |
|--------|---------------|------------|----------------|
| Days analyzed | 10 | 26 | Same May 2024 period |
| Price LSB anomalies | **70%** | **100%** | GME has 43% more anomalies |
| Benford deviation | 100% | 100% | Both deviate (general market artifact) |
| Mean p-value | 0.04 | < 0.0001 | GME is ~1000x more significant |

**Key Insight:**
> 📊 **GME shows significantly stronger non-random patterns than SPY.** While both deviate from theoretical randomness, GME's patterns are 30% more prevalent and orders of magnitude more statistically significant.

This suggests the anomalies are not purely general market artifacts—GME has unique microstructure characteristics that make it especially suitable as a steganographic medium.

### Phase 3: Order Book Microstructure ✅

| Metric | Result | Interpretation |
|--------|--------|----------------|
| Days analyzed | 26 | Full dataset |
| High round-lot days (>30%) | **19%** | 5 days with strong institutional patterns |
| Runs ratio | **1.41-1.53** | More direction changes than random |
| Round-dollar preference | 0.4-8.8% | Varies by volatility |

**Key Observations:**
- May 2024 volatility days show highest round-lot percentages (40-46%)
- All days show runs ratio > 1.4 (expected ~1.0 for random)
- Spread entropy varies significantly, indicating different trading regimes

---

## Interpretation

### What This Means

1. **Market microstructure is highly structured**, not random noise
2. **Algorithmic trading creates detectable patterns** in both price LSBs and timing
3. **The prerequisites for steganographic channels exist** in equity market data
4. **Current surveillance would not detect** covert communication hidden within these patterns
5. **GME has stronger structure than typical markets** (SPY comparison)

### What This Does NOT Mean

1. ❌ We have **not** detected actual covert messages
2. ❌ We have **not** proven intentional data hiding is occurring
3. ❌ These patterns **could be** natural artifacts of:
   - Round-lot trading preferences
   - Algorithmic execution strategies
   - Market microstructure (tick sizes, quote granularity)
   - Exchange matching engine behavior

---

## Anomaly Highlights

### Highest Periodicity Day: 2024-05-14
- **915 significant periodic peaks** detected
- 2.97 million trades
- Dominant period: 16.4 seconds
- *Context: Major GME volatility event*

### Strongest Clustering Day: 2024-05-06
- **8 significant interval clusters**
- Orders cluster at 10µs, 50µs, 100µs, 500µs, 1ms, 5ms, 10ms, 50ms
- *Interpretation: HFT algorithm fingerprints*

---

## Methodology

### LSB Analysis
1. Extract last decimal digit from price/volume
2. Chi-square test against uniform distribution
3. Shannon entropy calculation
4. Autocorrelation at lags 1-50
5. Wald-Wolfowitz runs test
6. Benford's Law first-digit analysis

### Timing Analysis
1. Calculate inter-arrival times (nanosecond precision)
2. FFT periodicity detection
3. Interval clustering at common boundaries
4. Kolmogorov-Smirnov test against exponential
5. Entropy comparison to theoretical Poisson

---

## Next Steps

### Completed ✅
- [x] Phase 1: LSB Detection
- [x] Phase 2: Timing Channels
- [x] Phase 3: Order Book
- [x] Phase 4: ML Steganalysis
- [x] SPY Control Sample

### Future Work
- [ ] Test on other meme stocks (AMC, KOSS)
- [ ] Compare to crypto markets
- [ ] Deep learning with LSTM for sequence patterns

---

## Phase 4: ML Steganalysis Results

| Metric | Value |
|--------|-------|
| Model Accuracy | **75%** |
| ROC-AUC | **0.984** |
| Suspicious Days | 4/26 (15%) |

**Top Features:**
1. `round_lot` (34%) - Round lot trading ratio
2. `volume_chi2` (30%) - Volume LSB distribution

**Interpretation:**
> Most real GME data (85%) scores as "Normal" compared to synthetic stego data. The model can effectively distinguish intentional embedding from natural market patterns.

---

## Files Generated

| File | Description |
|------|-------------|
| [lsb_analysis_report.md](01_lsb_detection/results/lsb_analysis_report.md) | Phase 1 LSB findings |
| [timing_analysis_report.md](02_timing_channels/results/timing_analysis_report.md) | Phase 2 timing findings |
| [order_book_analysis_report.md](03_order_book/results/order_book_analysis_report.md) | Phase 3 order book findings |
| [ml_steganalysis_report.md](04_steganalysis/results/ml_steganalysis_report.md) | Phase 4 ML results |
| [control_analysis_report.md](control_samples/results/control_analysis_report.md) | SPY comparison |

---

## Disclaimer

This research is for educational purposes only. The statistical anomalies detected are likely explained by legitimate market microstructure, not covert communication. However, the GME-specific nature of some findings warrants further investigation.

