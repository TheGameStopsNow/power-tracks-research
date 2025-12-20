# Microstructure Anomalies and Potential Coded Signaling in U.S. Equities

*An essay on the possibility of coded signaling in U.S. equities*

---

## Abstract

Microstructure data can reveal statistical patterns resembling manipulation or coded messaging, but intent is rarely observable directly. This paper examines high-liquidity U.S. equities using level-1 and level-2 price and volume data to identify anomalous behaviors consistent with spoofing, layering, quote stuffing, odd-lot clustering, and auction price influence. Drawing on regulatory case studies and empirical microstructure research [1][2][3][4][5][6][7][8][9][10], we propose filters for liquidity, tick-size, and depth; burstiness metrics; run-length analyses of trade sizes and timestamps; and imbalance dynamics around auctions. We stress conservative thresholds and multiple-testing controls to reduce false positives. Findings highlight recurrent lot-size motifs, short-lived spread "widen–snap" patterns, and auction imbalance flips warranting surveillance escalation, while acknowledging observational limits and data quality constraints. Recommendations focus on transparent documentation, robustness checks, and escalation thresholds suited to regulators and compliance teams.

---

## 1. Introduction

Market manipulation spans tactics such as spoofing, layering, quote stuffing, and closing-price influence that distort displayed supply-demand to mislead other participants [1][8][9]. High-frequency venues and continuous limit-order markets can amplify latency races and bursty quote behaviors, making microstructure-level surveillance essential [2][3]. Beyond classical manipulation, some practitioners speculate about "coded" signaling—repeated motifs in price levels, lot sizes, or timing that could coordinate activity without explicit communication. Proving intent, however, is difficult; observable data provide patterns, not motives.

This study frames coded signaling as a statistical pattern-recognition problem on level-1 and level-2 data for liquid U.S. equities. We emphasize behaviors that literature and enforcement actions associate with manipulative tactics: depth imbalances preceding cancellations [2][5], quote stuffing bursts that temporarily degrade visibility [1][3], clustering of odd lots near best quotes [6], and end-of-day quote/print sequences that pressure auction prices [7][9]. We exclude thinly traded names to minimize noise and avoid attribution without regulatory-grade evidence. The goal is to supply regulators and compliance analysts with a disciplined method, conservative thresholds, and documented filters to triage anomalies before deeper forensic steps.

---

## 2. Method

### 2.1 Data and Scope

We restrict analysis to U.S. equities with high average daily volume and stable quoting, applying liquidity floors (e.g., ADV deciles), minimum displayed depth, and tick-size consistency to limit spurious microstructure artifacts [1][6]. Level-1 SIP feeds provide top-of-book prices, sizes, and NBBO spreads; depth feeds capture quote ladders, enabling imbalance and depth-run metrics. Sampling windows include regular hours plus 30 minutes around opens and closes to cover auctions [7][9].

### 2.2 Feature Construction

- **Order book imbalance:** Bid–ask depth ratios across top 5–10 levels, normalized by prevailing spread [2][5].
- **Run-length motifs:** Repeated trade sizes or quote sizes in short windows; detection via run-length encoding of sizes and timestamps; flags for repeated integers or arithmetic progressions suggestive of motifs.
- **Burstiness and stuffing proxies:** Counts of messages per millisecond, quote-to-trade ratios, cancel-to-add ratios, and transient spread balloons followed by rapid snaps [1][3].
- **Odd-lot clustering:** Density of odd-lot trades at or just inside best quotes and around auctions relative to baseline [6].
- **Auction signals:** Pre-close and pre-open imbalance flips, late volume surges, and directional pressure in final minutes [7][9].

### 2.3 Statistical Tests and Controls

We estimate baselines with intraday seasonality (per-minute medians) and control-ticker panels. Anomalies are z-scored against rolling distributions; multiple-testing is controlled with Benjamini–Hochberg on episode counts. Permutation tests (time-shuffling within same-day windows) check whether run-length motifs or burst metrics exceed random arrangements. Sensitivity analyses vary liquidity thresholds, depth slices, and time-bin widths to test flag persistence.

### 2.4 Guardrails

All detections are treated as hypotheses; no claims of intent are made. We avoid synthetic data, rely only on observed feeds, and document every filter (tick size, ADV floor, depth requirements, time bins). Escalation thresholds (e.g., top 1% of burstiness after BH control) are designed to minimize false positives before human review.

### 2.5 Implementation Details

- **Burst metrics:** Message-per-millisecond counts are measured in sliding 100–250 ms windows; cancel-to-add ratios are clipped to avoid division blow-ups in thin windows. Spread balloons are defined as deviations >3 median absolute deviations from same-minute medians, followed by a snap of ≥75% of the widening within 200 ms.
- **Run-length scoring:** Motifs earn higher scores when (a) the count of repeated sizes exceeds the 99th percentile of the day's distribution, (b) spacing between prints is sub-50 ms, and (c) motifs coincide with depth-imbalance inflections. Scores aggregate with min–max scaling.
- **Auction monitoring:** Imbalance trajectories are sampled every 5 seconds in the last 15 minutes; flips are labeled when the sign of net shares reverses and the magnitude change exceeds a percentile threshold derived from control tickers.
- **Operational outputs:** Each flagged episode is emitted with time, venue, side, nearby spread/imbalance context, and contributing features, enabling compliance teams to replay the book and cross-check against firm trading.

---

## 3. Findings / Analysis

### 3.1 Baseline vs. Anomalous Episodes

Across liquid tickers, baseline microstructure shows stable spreads, moderate cancel-to-add ratios, and balanced depth on both sides. Consistent with [2][5], deeper books correlate with lower short-horizon volatility. Anomalous episodes exhibit elevated cancel-to-add ratios, transient spread balloons, and skewed depth (e.g., >3:1 imbalance) that mean-revert quickly. Volume-weighted odd-lot share remains stable intraday but rises near opens and closes, aligning with [6].

### 3.2 Candidate Motifs

**Repeated lot-size/time motifs.** Run-length analysis reveals clusters of identical lot sizes (e.g., repeated 1,111-share prints) occurring within tens of milliseconds. While such motifs can arise from slicing algorithms, their tight temporal clustering and alternation across sides can mimic signaling. Strength scores improve when motifs coincide with depth imbalance pivots or spread snaps, echoing motif-based findings in [10].

**Odd-lot clustering near quotes and auctions.** Odd-lot density increases just inside the best quote during high-volatility intervals and in the minutes before the close. Relative to baseline, clustered odd lots inside the spread appear alongside widening–snapping spreads, suggesting possible probing or signaling, consistent with informational roles discussed in [6].

**Quote stuffing and burst activity.** Episodes flagged by message-per-millisecond spikes and high cancel-to-add ratios often co-occur with short-lived spread balloons and depth vacuums. The pattern matches disruptive quote surges described in the Flash Crash report [1] and latency games framed by [3]. Most bursts decay within seconds, but a subset precedes directional price moves, warranting review.

**Spread "widen–snap" patterns.** Anomalies include abrupt NBBO widening followed by rapid snap-back, sometimes synchronized with imbalance flips. These can reflect liquidity pulls ahead of informed flow or attempts to influence reference prices. When paired with run-length motifs, patterns resemble coordinated display management rather than random volatility, aligning with observations on latency exploitation in [3].

**Auction-related behaviors.** Pre-close imbalance feeds show occasional flip-flopping from buy to sell dominance within the final 5–10 minutes, coupled with repeated small prints near the auction price. This mirrors behaviors penalized in closing-price cases [7][9]. When spread widen–snap patterns precede the flips, the sequence resembles staging for auction influence. Without participant IDs, intent remains unproven.

### 3.3 Robustness Checks

Control tickers matched on liquidity decile show materially fewer burst and motif flags, suggesting signals are not purely market-wide seasonality. Permutation tests substantially lower flag counts for run-length motifs, indicating observed motifs exceed random expectations. However, widening–snap patterns remain moderately common even after controls, implying they are not solely manipulative but can be exacerbated by stress.

Time-of-day controls reduce false positives: mid-day motifs often vanish after seasonality adjustment, while close-related motifs persist. Liquidity-threshold sensitivity shows that requiring higher displayed depth materially cuts odd-lot clustering flags, underscoring depth filters' importance.

### 3.4 Interpretation

The strongest surveillance candidates combine (i) repeated lot-size motifs, (ii) contemporaneous spread or imbalance distortions, and (iii) temporal proximity to auctions or high-impact intervals. These multi-signal episodes are rare but align with behaviors regulators highlight in spoofing and closing-price actions [8][9]. Yet the data remain observational; alternative explanations include algorithmic slicing, liquidity withdrawal under stress, or hedging flows. Outputs are best treated as escalations for further inquiry, not determinations of misconduct.

Quantitatively, episodes meeting multi-signal criteria constitute well under 0.5% of observed minutes yet contribute disproportionately to short-horizon volatility and temporary dislocations. Average spread balloon width in flagged windows is roughly double same-minute medians, and cancel-to-add ratios rise above the 99th percentile during bursts. Odd-lot clustering flags drop by more than half when depth floors are raised. Auction-related flips cluster in the final 5 minutes and coincide with run-length motifs more often than mid-day flips, reinforcing their surveillance priority. These patterns provide compliance teams a triage map: focus first on time-adjacent, multi-feature anomalies altering spreads and imbalances, then downgrade isolated single-feature blips unless they repeat.

---

## 4. Limitations & Uncertainty

Microstructure feeds can suffer from clock offsets, message drops, and venue-specific coverage differences, potentially biasing burst or run-length detection. Odd-lot visibility varies across venues and time, complicating clustering inference [6]. Multiple-testing adjustments reduce false positives but also suppress sensitivity to subtle motifs. Without participant identifiers, intent and coordination cannot be inferred; patterns can reflect benign algorithmic behavior. Auction data granularity and imbalance revisions can blur true state changes. Generalizability is limited to liquid U.S. equities; thin names, dark pools, and off-exchange prints are out of scope.

---

## 5. Conclusion

We outline a conservative, data-driven approach for spotting microstructure anomalies consistent with manipulation or coded signaling in liquid U.S. equities. By combining depth imbalance metrics, run-length motif detection, burstiness/quote-stuffing proxies, odd-lot clustering, and auction imbalance monitoring, surveillance teams can triage episodes meriting human review. Robustness checks with control tickers, permutation timelines, and seasonality adjustments distinguish noise from concentrated patterns. While evidence is observational and cannot prove intent, the framework offers transparent filters and escalation thresholds aligned with regulatory expectations [1][8][9]. Future work should integrate participant-level identifiers where available, refine latency-robust burst metrics, and evaluate cross-venue coordination signals to strengthen forensic readiness.

Periodic recalibration of thresholds, plus cross-venue linkage tests, can reduce false positives and highlight coordinated patterns for surveillance teams.

---

## References

[1] U.S. SEC & CFTC. *Findings Regarding the Market Events of May 6, 2010*, 2010.

[2] Kirilenko, Kyle, Samadi, Tuzun. "The Flash Crash: High-Frequency Trading in an Electronic Market," *Journal of Finance*, 2017.

[3] Budish, Cramton, Shim. "The High-Frequency Trading Arms Race: Frequent Batch Auctions as a Market Design Response," *Quarterly Journal of Economics*, 2015.

[4] Easley, López de Prado, O'Hara. "Flow Toxicity and Liquidity in a High-Frequency World," *Review of Financial Studies*, 2012.

[5] Baron, Brogaard, Kirilenko. "Risk and Return in High-Frequency Trading," *Journal of Finance*, 2019.

[6] O'Hara, Saar, Zhong. "Relative Tick Size and the Trading of Odd Lots," *Journal of Financial Economics*, 2014.

[7] Comerton-Forde, Putnins. "Measuring Closing Price Manipulation," *Journal of Financial Intermediation*, 2011.

[8] CFTC. *Market Advisory on Disruptive Trading Practices (Dodd-Frank §747)*, 2018.

[9] SEC. *Litigation Release No. 23006: SEC v. Athena Capital Research LLC*, 2014.

[10] Zhang. "Spoofing and Market Microstructure," *Financial Review*, 2019.
