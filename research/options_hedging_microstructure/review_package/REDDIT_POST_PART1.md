# I Analyzed 80 Million Trades Across 37 Tickers and Found Six Anomalies in GME Options That Have No Legitimate Market Explanation. Here's What I Found and How You Can Verify It.

**TL;DR: I spent months analyzing tick-level options data from both the January 2021 and June 2024 GME events. I found six specific patterns — wash trades, surveillance threshold evasion, synthetic delta transfers, and algorithmic signatures — that are inconsistent with any known legitimate trading strategy. The same algorithmic fingerprint appears in both events, 3.5 years apart. All findings are independently verifiable from public SIP data. The full replication package with code, data, and notebooks is linked at the bottom.**

---

## Part 1 of 2: The Machine Under the Market

I'm going to explain what I found, how I found it, and why I think it matters. I'll also explain what the data *doesn't* prove, because that matters too.

If you want the full 160,000-word paper with 32 tables, there's a link at the end. But this post is the summary — the six findings that I believe warrant serious examination.

---

## How Market Makers Actually Work (The 60-Second Version)

Here's the thing nobody tells you about market makers: **their default position is Long Gamma, not Short.**

Every DD you've read says market makers are short gamma and that's what causes the sneeze. Sometimes that's true — during a sneeze. But in *normal markets*, the opposite is happening.

Think about it. Every day in institutional finance:

- **Pension funds** sell covered calls against their stock holdings to generate income. The dealer *buys* those calls.
- **Insurance companies** buy protective puts to hedge their portfolios. The dealer *sells* those puts.
- **Yield hunters** sell options systematically to harvest theta.

In every one of these transactions, the dealer ends up **Net Long Gamma**. And here's what that means mechanically:

> When you're Long Gamma, your delta increases as the stock rises and decreases as it falls. To stay hedged, you have to **sell into rallies and buy into dips**. Every single time.

That's not a strategy. It's math. The effect is *dampening* — the market maker's hedging flow acts like shock absorbers, smoothing out every bump.

I measured this across **37 different tickers** over 6 years. The result:

**92.7% of trading days show dampening.** The average dampening signal (measured by autocorrelation, or ACF) is -0.203 across the entire panel. That means on a normal day, if the stock moves up in one 5-minute bar, the next bar is statistically likely to reverse — because the dealer's hedging kicked in and pushed it back.

This isn't a GME-specific phenomenon. It's how the entire U.S. equity market operates. Every single ticker in my 37-stock panel — mega-caps, mid-caps, meme stocks, ETFs — classifies as Long Gamma Default over its full observation window.

**The market's default state isn't chaos. It's mechanical stability.**

---

## What Happens When the Thermostat Breaks

That stability system has a breaking point.

When retail traders buy call options in overwhelming volume, the dealer ends up on the wrong side. Instead of buying calls from institutions, they're *selling* calls to retail. That puts them **Short Gamma** — the mirror image:

> When you're Short Gamma, rising prices force you to **buy more shares** (chasing the rally), and falling prices force you to **sell** (accelerating the crash). It amplifies everything.

I call the moment when Long Gamma flips to Short Gamma a **"Liquidity Phase Transition."** It's like water going from liquid to steam — same substance, completely different behavior.

During the January 2021 sneeze, GME's ACF hit **+0.107** (amplified). During its normal phase (2024-2026), it's **-0.154** (dampened). Same stock. Completely different physics.

The question is: **Was this transition driven purely by organic retail volume, or did someone engineer it?**

---

## Where the Energy Is Stored

Before I show you what I found in the options tape, you need to understand where the thermostat's power comes from. Because it's not where most people think.

When most people think about options activity, they picture the loudest trades: 0DTE calls, weekly puts, the gambling that makes the ticker tape blink. And by trade count, they'd be right — **60% of all GME options trades** are in the 0DTE and 1-7 day buckets.

But trade count is misleading. I computed something I call **Hedging Energy** — a measure that weights each trade by how long the dealer has to keep hedging it. A 0DTE call forces the dealer to hedge for a single session. A one-year LEAPS contract forces fractional delta-rebalancing across **250 trading sessions**.

When you weight by hedging duration instead of trade count, the picture inverts:

| Tenor | % of Trades | % of Hedging Energy |
|-------|:-----------:|:-------------------:|
| 0DTE | 11.1% | **0.1%** |
| 1-7 day | 48.9% | **9.0%** |
| 8-30 day | 24.8% | **21.7%** |
| 31-90 day | 8.7% | **24.1%** |
| 91-180 day | 2.9% | **18.1%** |
| 181-365 day | 1.9% | **23.7%** |
| 365+ day | 0.1% | **3.3%** |

Read that bottom row again. The 181-365 day bucket holds **23.7% of all hedging energy** from just **1.9% of trades**. Longer-dated options (91+ days) collectively carry **45% of total hedging energy from just 5% of trade volume.**

I call this the **Inventory Battery Effect.** LEAPS function like batteries — they charge slowly when institutional investors accumulate long-dated positions, and discharge as those positions approach expiration. The energy is stored as persistent delta-hedge obligations on the dealer's balance sheet.

Here's where it connects to the sneeze: the January 2021 event was the **only event in my entire 1,531-day dataset where the full tenor stack activated simultaneously** — energy blazed across all 7 buckets at once. Every other event only activates the short-dated tenors. When the sneeze happened, the energy cascade went all the way up to the longest-dated LEAPS.

Even more telling: during the quiet years of 2022-2023, LEAPS energy *persisted* at the 181-365 day level even when short-dated activity went cold. Someone was maintaining those long-dated positions through the entire dormant period.

**Whoever controls the LEAPS inventory controls 45% of the thermostat's power source.**

---

## The Shadow Algorithm

What I'm about to show you are the six specific findings that I believe cannot be explained by legitimate trading activity. I'll describe each one, explain why I believe it's anomalous, and you can decide for yourself whether you agree.

I ran five forensic tests against tick-level GME options data from both the January 2021 and June 2024 events. The data comes from ThetaData's SIP feed, which records every single options trade with millisecond timestamps, exchange codes, lot sizes, and condition flags.

### Test 1: Tail-Banging — Burning Money to Contaminate Pricing Models

On January 28, 2021 — the most volatile day of the sneeze — someone executed **518 trades** on deep OTM 1-DTE calls, spending a total of **$69.8 million** on contracts virtually guaranteed to expire worthless within hours.

The peak strike: **$570 calls** when GME was trading at $194. That's 194% out of the money with one day to live.

Nobody buys these for speculation or hedging. They're worth pennies and they'll be zero by tomorrow.

So why spend $69.8 million on them?

**Because every trade prints to the SIP tape.** When a $570 call trades at any price above zero, it forces the options pricing model to calculate an implied volatility for that strike. When you're 194% OTM with 1 DTE, that IV exceeds **1,000%**.

Market makers use automated pricing models (SABR/SVI) that calibrate the volatility surface using *every print on the tape*. Those 518 trades contaminated the entire volatility surface for GME options, affecting the price of every other contract on the chain.

The contamination was positioned to inflate Vanna exposure on warehoused LEAPS — making the gamma mechanics even more volatile.

**Cost: $69.8M. This is consistent with a deliberate IV injection campaign, not speculation.**

### Test 2: Wash Trades — Printing Volume on Tape

Wash trading: you buy and sell the same contract to yourself, in the same quantity, at the same price, within fractions of a second. You don't gain or lose money. But the trade *prints to the tape*, creating artificial volume.

I built a detector that identifies pairs of trades matching on lot size, price, strike, and expiration, executing within 5 seconds of each other.

The results:

| Date | Wash Pairs | Sub-Second (< 1s gap) |
|------|:----------:|:---------------------:|
| Jan 26, 2021 | **100** | 78 |
| Jan 27, 2021 | 101 | 57 |
| Jan 28, 2021 | 103 | 29 |
| Jan 29, 2021 | 42 | 19 |
| Jun 4, 2024 | 14 | 6 |
| **Jun 7, 2024** | **265** | **216** |

That last row: **265 wash trade pairs in a single session**, with **216 executing in under one second**. These are identical-size, identical-price prints on the same contract appearing across exchanges within fractions of a second.

For context, I ran the same detector against control tickers in the 37-stock panel. The wash pair frequency for GME during these events is multiple standard deviations above the panel baseline. This isn't normal market making.

### Test 3: 30% of the Volume Was on Dark Venue Exchanges

Not all options exchanges are created equal. Some — the ones with exchange codes like UNK_60, UNK_65, UNK_73 — don't show up in most retail data feeds.

| Event | Total Options Volume | Dark Venue Volume | Dark % |
|-------|:-------------------:|:-----------------:|:------:|
| **Jan 2021** (6 dates) | 8,056,797 | 2,505,062 | **31.1%** |
| **Jun 2024** (8 dates) | 3,314,219 | 975,222 | **29.4%** |

Nearly **one-third of all options volume** in both events was routed through venues that retail traders can't access. These include Cboe BZX Options, whose maker-taker inverted fee model actually **pays the order submitter** for providing liquidity.

If this were purely a retail phenomenon, you wouldn't expect 30% of volume routing through institutional-only dark exchanges. That's worth examining.

### Test 4: The Shadow Channel — IV Injection Followed by LEAPS Loading

After tail-banging events inject artificial IV onto the tape, I detected a pattern of LEAPS accumulation appearing **7-9 minutes later** on the same strike region.

| Event | Mean Lag After IV Injection | Standard Deviation |
|-------|:--------------------------:|:------------------:|
| Jan 2021 | **7.3 minutes** | +/-3.1 min |
| Jun 2024 | **9.4 minutes** | +/-2.9 min |

The lag is consistent and narrow. The pattern is consistent with a two-step strategy: inject IV with worthless short-dated prints, wait for market maker models to recalibrate, then acquire LEAPS at the newly inflated prices.

---

## Six Anomalies That Warrant Examination

Everything above is concerning, but you could argue it's aggressive market making. The next six findings are different. Each one describes a specific trade or sequence that I believe is inconsistent with any known legitimate trading strategy. I'll explain why for each one, and you can evaluate the evidence yourself.

### Anomaly 1: Single-Strike Complex Order Book Washes

Complex Order Books (COBs) are designed for multi-leg strategies — buying a $20 call and selling a $25 call simultaneously. The whole point is that the legs have *different* strikes.

I found COB orders where **all legs target the same strike**. That means the buy and sell sides cross atomically — same contract, same strike — with zero delta exposure, zero risk, and zero directional purpose.

Examples from the data:

- **Jun 4, 2024, 12:43:05.550** — ISE Gemini, 2 legs, $125 Calls, sizes [160, 160] = 320 contracts
- **Jun 7, 2024, 15:04:19.233** — CBOE, 2 legs, $28 Calls, sizes [496, 496] = 992 contracts
- **Jan 28, 2021, 09:44:42.714** — BZX Options, **9 legs**, $0.50 Calls (spot ~$194), sizes [1,5,10,61,89,90,117,446] = 820 contracts

That last one: a **nine-leg** complex order on **$0.50 calls** when GME was at **$194**. Those calls are so far out of the money they're effectively worthless. And someone routed them as a multi-leg "strategy" with 8 different lot sizes, all on the same strike.

I cannot identify a legitimate multi-leg options strategy that requires 9 legs on a single strike. If someone can, I'd genuinely like to hear it. The only function I can identify is printing artificial volume on the SIP tape.

### Anomaly 2: The Algorithmic DNA Match — Same Code, 3.5 Years Later

When institutional traders execute large block orders, they use Smart Order Routers (SORs) with specific "jitter" patterns — varying lot sizes by +/-2 or +/-4 contracts to disguise the order as multiple independent trades.

I built a detector for these sequential TWAP patterns. I found the same jitter sequences appearing **3 years and 4 months apart**:

| Sequence | January 28, 2021 | June 4, 2024 |
|----------|-----------------|--------------:|
| **[150, 154, 150]** | 09:30:34 — NYSE_AMEX -> NYSE_AMEX -> BX_OPT | 10:49:17 — PHLX -> BATS -> BX_OPT |
| **[100, 102, 100]** | 09:56:47 — NYSE_AMEX -> BX_OPT -> BZX_OPT | 09:59:15 — NYSE_AMEX -> ISE -> NYSE_AMEX |

Same +/-2/+/-4 jitter logic. Same set of dark execution venues. **Separated by 1,254 days.**

Retail traders don't use sub-lot jitter algorithms. This is consistent with the **same institutional entity** — running the **same Prime Brokerage Smart Order Router software** — operating in both events.

### Anomaly 3: 499 Lots — Exactly One Below a Round Number

On January 29, 2021, between 12:38:09.579 and 12:38:12.265 — a **three-second window** — 16 separate wash trade pairs were executed on $5.0 Puts at $0.43. Every single one was exactly **499 lots**. They rotated between MULTI_EXCHANGE and ISE venues. The first pair had a timestamp gap of **one millisecond**.

Why 499?

Exchange-level surveillance systems use alert thresholds to flag unusually large transactions. **The exact thresholds are intentionally not published.** But the behavioral pattern speaks for itself: 16 consecutive trades all sized at exactly 499 lots — not 498, not 497, not 500 — is consistent with precise knowledge of a round-number surveillance boundary.

At 499 contracts per trade, these positions exceed the **200-contract** reporting threshold under [FINRA Rule 2360](https://www.finra.org/rules-guidance/rulebooks/finra-rules/2360), which requires member firms to report equity option positions of 200+ contracts to the Large Options Positions Reporting (LOPR) system. FINRA already has this position data on file.

The consistent use of exactly 499 lots — one below 500 — across 16 consecutive trades is consistent with deliberate threshold evasion. This is the options market equivalent of financial "structuring" under 31 U.S.C. section 5324.

### Anomaly 4: The $134 Million Single-Millisecond COB Cluster

The largest single Complex Order Book cluster in the dataset:

> **January 27, 2021 at 15:21:23.512** — NYSE AMEX — 12 legs — 4,050 lots — **$134,493,850** — executed in a single millisecond.

$134 million. In one millisecond. On a Complex Order Book.

The strikes targeted: $4.50, $5.00, $6.00, $7.00, $10.00, $12.00. GME's spot price: ~$347.51. Average premium: $332.08 per contract — almost exactly the intrinsic value of Deep ITM options. These contracts move 1:1 with the underlying stock with zero extrinsic value.

Spending $134 million on Deep ITM options doesn't have a speculative rationale. This is consistent with the mechanical signature of a **Reversal/Conversion synthetic short reset ("Jelly Roll")**. By executing on a Complex Order Book:

1. Delta risk moves off the lit equity tape
2. Reg SHO short-sale restrictions are bypassed
3. Failures-to-Deliver (FTDs) can be rolled at the peak of the squeeze
4. All of it executes in one millisecond, outside the scope of standard trade reporting surveillance

### Anomaly 5: Opening Bell Put Washes

On June 7, 2024 at 09:30:25.929 — the precise millisecond of the opening bell — **17 wash trade pairs** were executed on $10.00 Puts at $1.01, cycling between MIAX Emerald and OPRA in a 9-millisecond burst. GME's spot price: ~$46.55. A $10 Put on a $46.55 stock is **78% out of the money**.

Paying $1.01 per contract for a 78% OTM put is inconsistent with any hedging or speculative purpose I can identify. The only function I can see is **warping the left side of the volatility smile** — injecting extreme IV at the put tail to complement the call-tail injection from the tail-banging documented in Test 1.

By pinning extreme IV to both tails simultaneously — OTM calls *and* OTM puts — the result is forcing Market Makers' SABR/SVI models to shift the entire IV surface vertically.

### Anomaly 6: The Cross-Venue Swarm — 32 Legs on 1 Strike

The most mechanically unusual finding in the dataset.

On June 21, 2024, at 13:35:07, a coordinated barrage:

| Timestamp | Exchange | Legs | Volume | Capital |
|-----------|----------|:----:|:------:|:-------:|
| 13:35:07.531 | ISE | 4 | 116 | $80,794 |
| 13:35:07.532 | CBOE | 4 | 116 | $81,142 |
| 13:35:07.533 | MULTI_EXCHANGE | **20** | 128 | $89,472 |
| 13:35:07.700 | BX Options | 4 | 420 | $292,740 |
| **TOTAL** | **4 exchanges** | **32** | **780** | **$544,148** |

**Thirty-two complex legs targeting the same strike** — $15.0 calls — across four exchanges, in **169 milliseconds**.

A 20-leg complex order where all legs are on the same contract is not a strategy I can identify. There's no butterfly, iron condor, or any other multi-leg structure that requires 20 legs on one contract. If one exists, I'd like to learn about it.

The $15.00 strike was the **Gamma Wall** — the strike where net gamma exposure was highest, creating maximum hedging pressure. Flooding it with artificial volume creates phantom liquidity, forcing market makers to recalculate hedging obligations against inflated open interest figures.

---

## What This Evidence Shows — and What It Doesn't

Let me be direct about the boundaries of what I can claim.

**What the data shows:**

These six anomalies are individually unusual. Taken together, they form a pattern that I believe is inconsistent with normal market activity. Specifically:

- Single-strike COB orders have no multi-leg strategy justification I can identify
- 499-lot sizing is consistent with deliberate surveillance threshold evasion
- Identical algorithmic jitter across 3.5 years is consistent with the same institutional SOR
- $134M in Deep ITM options in one millisecond is consistent with a synthetic short reset, not speculation
- Opening bell put washes on 78% OTM contracts are consistent with IV surface manipulation

All of these can be verified from public SIP data.

**What the data doesn't show:**

I don't have the Market Participant Identifier (MPID) — the field that tells you which broker-dealer submitted each trade. That data exists in the FINRA Consolidated Audit Trail (CAT). Without it, I can describe the *what* and the *how*, but not the *who*. I've described five specific CAT queries in Part 2 that would close that attribution gap.

I'm not in a position to make legal conclusions. What I can say is that these patterns satisfy the technical criteria that, in my assessment, warrant regulatory examination. I've submitted a TCR to the SEC with the full manuscript.

**Context that matters:**

These findings don't exist in isolation. They sit within a broader analysis:

- **37-ticker control panel** showing GME's behavior is anomalous relative to the broader market
- **Lead-lag analysis** showing options lead equity by a median of 87.5 seconds
- **NMF reconstruction** showing approximately 25% of equity volume variance is mechanically determined by options chain configuration from weeks earlier (after controlling for the universal intraday U-curve)
- **DJT natural experiment** — a 2024 meme stock with comparable retail mania but standard dampening, suggesting the system held for a stock that wasn't experiencing these specific anomalies

---

**[Part 2 (next post)](REDDIT_POST_PART2.md) will cover:**
- The "Player Piano" discovery — how approximately 25% of equity volume is mechanically pre-programmed by the options chain (and why the in-sample r = 1.000 isn't the real number)
- The five FINRA CAT queries that would identify the entity behind these trades
- What this means for you and what you can do about it

---

**Full Paper (PDF):** [The Long Gamma Default: How Options Market Makers Stabilize Equity Markets](https://github.com/TheGameStopsNow/power-tracks-research/blob/main/research/options_hedging_microstructure/review_package/The%20Long%20Gamma%20Default-%20How%20Options%20Market%20Structure%20Creates%20Artificial%20Stability%20in%20Equity%20Prices-%20Academic.pdf) — 160,000 words, 32 tables, 14 references, 6 appendices

**Evidence Viewer (no setup required):** [01_evidence_viewer.ipynb](https://github.com/TheGameStopsNow/power-tracks-research/blob/main/research/options_hedging_microstructure/review_package/01_evidence_viewer.ipynb) — Loads all 89 pre-computed results. Renders every anomaly, every table, every claim verification. **Start here if you want to check my work.**

**Replication Notebooks:**
- [02_forensic_replication.ipynb](https://github.com/TheGameStopsNow/power-tracks-research/blob/main/research/options_hedging_microstructure/review_package/02_forensic_replication.ipynb) — Re-run Shadow Hunter, manipulation forensic battery, squeeze mechanics
- [03_microstructure_replication.ipynb](https://github.com/TheGameStopsNow/power-tracks-research/blob/main/research/options_hedging_microstructure/review_package/03_microstructure_replication.ipynb) — Re-run panel ACF, lead-lag, NMF archaeology, robustness tests

**Pre-computed Results:** [89 JSON evidence files](https://github.com/TheGameStopsNow/power-tracks-research/tree/main/research/options_hedging_microstructure/review_package/results) — Panel scan, ACF, lead-lag, NMF, forensic evidence, cycle analysis

**Source Code:** [30 Python scripts](https://github.com/TheGameStopsNow/power-tracks-research/tree/main/research/options_hedging_microstructure/review_package/code) — Full analysis pipeline

**Replication Guide:** [REPLICATION_GUIDE.md](https://github.com/TheGameStopsNow/power-tracks-research/blob/main/research/options_hedging_microstructure/review_package/REPLICATION_GUIDE.md) — Exact dates, commands, parameters, and thresholds to reproduce every result

**Video — Surfing the GME Options Chain:**
- [Short version (1 min)](https://youtube.com/shorts/DZti6HodVTQ)
- [Full session](https://youtu.be/HcDQNJxjKK0)
- [Stock surfing](https://www.youtube.com/watch?v=QwjpwQ-AoFQ)

**Full Repository:** [github.com/TheGameStopsNow/power-tracks-research](https://github.com/TheGameStopsNow/power-tracks-research/tree/main/research/options_hedging_microstructure/review_package)

*This is not financial advice. This is forensic research. I am not a financial advisor, attorney, or affiliated with any hedge fund, market maker, or regulatory agency. The SEC has been notified via TCR.*

---

*"The first principle is that you must not fool yourself — and you are the easiest person to fool." — Richard Feynman*
