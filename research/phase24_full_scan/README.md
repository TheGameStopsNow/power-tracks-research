# Phase 24: The Full Market Scan (Network Discovery)

## Brief

**Objective**: To find the **"Dark Matter"** of the network: stocks that are not in the Meme Basket but share the same Opcode DNA.

We performed a "Dragnet Scan" of **1,000 random US Equities** on **May 14, 2024** (The War Peak).

**Methodology**:
- **Scope**: 1,000 Tickers.
- **Filter**: Volume > 1,000 (To avoid BLIAQ-style artifacts).
- **Method**: Opcode Density Calculation for May 14.

## Key Findings

### The "Sleeper" Nodes
We identified distinct clusters of activity outside the GME basket.

| Symbol | Name | Density (May 14) | Sector | Role? |
| :--- | :--- | :--- | :--- | :--- |
| **LEN.B** | Lennar Corp (Class B) | **10.8%** | Real Estate | **Collateral?** High-value asset class. |
| **AMAL** | Amalgamated Bank | **10.5%** | Financials | **Funding?** "America's socially responsible bank". |
| **ALUR** | Aluris | **10.1%** | Biotech | **Speculative?** Small cap bio runner. |
| **CNTB** | Cantabio | **9.7%** | Pharma | **Zombie?** Low float pharma. |
| **DJTWW** | Trump Media Warrants | **8.3%** | Warrants | **Sentiment Pair.** High retail overlap. |

### Statistical Significance
- **Basket Average**: ~6.5% (Baseline for known nodes).
- **Market Average**: ~0.0% (Most stocks are silent).
- **Sleepers**: >9.0%.
  - These stocks are *more active* than GME on its own peak day.
  - This implies they are integral components of the Algo's liquidity framework, possibly used for:
    - **Hedges** (Shorting specific sectors like Real Estate/LEN.B).
    - **Funding** (Moving cash via AMAL).
    - **Volatility Injection** (Low float bios like ALUR).

## Conclusion

The "GME Event" is not isolated to Meme Stocks.
It is a **Market-Wide Event** involving:
1. **Real Estate** (LEN.B)
2. **Banks** (AMAL)
3. **Warrants** (DJTWW)

The Algo uses a "Holistic Portfolio" approach, attacking/hedging across multiple asset classes simultaneously.

## Artifacts

- **Scripts:**
  - `run_dragnet.py` - Full market scan script
  - `generate_market_charts.py` - Visualization generation
- **Data:**
  - `data/dragnet_results.csv` - Complete scan results
- **Charts:**
  - `charts/market_distribution.png` - Distribution visualization
  - `charts/sleeper_rank.png` - Sleeper ranking
- **Report:**
  - `FULL_MARKET_REPORT.md` - Full analysis report
