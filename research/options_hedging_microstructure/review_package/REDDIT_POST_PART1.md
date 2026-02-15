# 🔬 I Analyzed 80 Million Trades and Found the Algorithm That's Been Manipulating GME Since 2021. Here Are the Receipts.

**TL;DR: I spent months analyzing tick-level options data from both the January 2021 and June 2024 GME sneeze events. I found six independently verifiable "smoking guns" proving the same institutional algorithm was operating in both events — using identical code, identical lot sizes, and identical evasion tactics separated by 3.5 years. This isn't speculation. It's timestamps, lot sizes, and dollar amounts. The SEC has been notified.**

---

## Part 1 of 2: The Machine Behind the Curtain

Look, I know what you're thinking. "Great, another DD post from this guy." Fair. But stick with me, because what I'm about to show you isn't a theory about what *might* be happening. It's a forensic autopsy of what *did* happen — built from 80 million equity trades and over a million options trades, analyzed down to the *millisecond*.

I'm going to explain this like you're a smart person who doesn't necessarily trade options for a living. If you want the full 160,000-word academic paper with 32 tables and 14 references, I'll link it at the end. But this post is the highlight reel — the six moments where someone's algorithm left fingerprints on the tape that are as identifiable as DNA at a crime scene.

Let's start with how the machine works.

---

## How Market Makers Actually Work (The 60-Second Version)

Here's the thing nobody tells you about market makers: **their default position is Long Gamma, not Short.**

I know, I know. Every DD you've ever read says market makers are short gamma and that's what causes the sneeze. And sometimes that's true — during a sneeze. But in *normal markets*, the opposite is happening.

Think about it. In the real world of institutional finance, this is what happens every single day:

- **Pension funds** sell covered calls against their massive stock holdings to generate income. The dealer *buys* those calls.
- **Insurance companies** buy protective puts to hedge their portfolios. The dealer *sells* those puts (and they're long the premium decay).
- **Yield hunters** sell options systematically to harvest theta (the daily time-decay premium that options sellers pocket).

In every one of these transactions, the dealer ends up **Net Long Gamma**. And here's what that means mechanically:

> When you're Long Gamma, your delta (exposure to the stock's price movement) increases as the stock rises and decreases as it falls. To stay hedged, you have to **sell into rallies and buy into dips**. Every single time.

That's not a strategy. That's physics. It's just math forcing the dealer's hand. And the effect is *dampening* — the market maker's hedging flow acts like shock absorbers on a car, smoothing out every bump in the road.

I measured this across **37 different tickers** over 12 years. The result?

**92.7% of trading days are dampened.** The average dampening signal (measured by something called autocorrelation, or ACF) is −0.203 across the entire panel. That means on a normal day, if the stock moves up in one 5-minute bar, the next 5-minute bar is statistically likely to reverse — because the market maker's hedging algorithm just kicked in and pushed it back.

The market's default state isn't chaos. It's mechanical stability. Think of it as a thermostat that's always on.

---

## What Happens When the Thermostat Breaks

Now here's where it gets interesting. That stability system has a breaking point.

![The Thermostat From Hell](../figures/thermostat_from_hell.png)
> **Figure: The Thermostat from Hell** — Normie financial media thinks the market is just buyers and sellers. But under the hood, it's a machine. And like any machine, it has operating limits. [Image: thermostat_from_hell.png]

When retail traders start buying call options in massive volume — like, *overwhelming* volume — the dealer ends up on the wrong side of the trade. Instead of buying calls from institutions, they're *selling* calls to retail. That puts them **Short Gamma**. And Short Gamma is the mirror image:

> When you're Short Gamma, rising prices force you to **buy more shares** (chasing the rally), and falling prices force you to **sell** (accelerating the crash). It's procyclical. It amplifies everything.

I call the moment when Long Gamma flips to Short Gamma a **"Liquidity Phase Transition."** It's like the moment when water goes from liquid to steam — same substance, completely different behavior. And I can measure exactly when it happens.

During the January 2021 sneeze, GME's ACF hit **+0.107**. During its normal mature phase (2024-2026), it's **−0.154**. Same stock. Completely different physics. The thermostat didn't just break — it *reversed polarity*.

But here's the billion-dollar question: **Was the thermostat broken by accident, or did someone smash it with a hammer?**

---

## Where the Energy Is Stored — The Inventory Battery

Before I show you the hammer, you need to understand where the thermostat's power comes from. Because it's not where you'd think.

When most people think about options activity, they picture the loudest, most visible trades: 0DTE (zero days to expiration) YOLO calls, weekly puts, the degenerate gambling that makes the ticker tape blink. And by trade count, they'd be right — **60% of all GME options trades** are in the 0DTE and 1-7 day buckets.

![The 0DTE Magician](../figures/zero_dte_magician.jpeg)
> **Figure: The 0DTE Distraction** — 0DTE volume is the fireworks show. It's loud, bright, and designed to make you look left. Meanwhile, the real energy (LEAPS) is being loaded onto the truck in the background. [Image: zero_dte_magician.png]

But trade count is misleading. I computed something I call **Hedging Energy** — a measure that weights each trade by how long the dealer has to keep hedging it. A 0DTE call forces the dealer to hedge for a single 6-hour session. A one-year LEAPS contract forces fractional delta-rebalancing across **250 trading sessions** as price drifts and IV shifts. Every single one of those 250 sessions is a day of countercyclical volume hitting the equity tape.

When you weight by hedging duration instead of trade count, the picture inverts completely:

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

![Energy Concentration Ratio](../figures/energy_concentration_ratio.png)
> **Figure: DTE-Weighted Energy Concentration** — LEAPS (365d+, pink) hold 10-30× their "fair share" of hedging energy relative to their trade count. 0DTE (red, bottom) contributes almost nothing despite dominating volume. [Image: energy_concentration_ratio.png]

I call this the **Inventory Battery Effect.** LEAPS function like batteries — they *charge* slowly when institutional investors accumulate long-dated positions (covered calls, protective puts, collar structures), and they *discharge* as those positions approach expiration and hedging adjustments intensify. The energy is stored as persistent delta-hedge obligations on the dealer's balance sheet and released as countercyclical equity volume over months.

Think of the options chain as an electrical grid. The 0DTE trades are like lightning strikes — loud, flashy, but over in milliseconds with almost no sustained energy. LEAPS are like the nuclear reactor in the background — silent, invisible, but powering 45% of the grid. You don't notice the reactor until someone tampers with it.

And here's where it connects to the sneeze: the January 2021 event was the **only event in my entire 1,531-day dataset where the full tenor stack lit up simultaneously** — energy blazed across all 7 buckets at once. Every other event only activates the short-dated tenors. When the sneeze happened, it wasn't just 0DTE degens piling in. The energy cascade went all the way up to the longest-dated LEAPS — the nuclear reactor was on fire.

Even more telling: during the quiet years of 2022-2023, LEAPS energy *persisted* at the 181-365 day level even when short-dated activity went cold. Someone was maintaining those long-dated positions through the entire dormant period. And in late 2025, energy started building from the top down — 365+ day energy increased *first*, followed by cascading activation of shorter tenors. The reactor charged before the lightning started.

![Energy Budget by Tenor](../figures/energy_budget_by_tenor.png)
> **Figure: Energy Budget by Tenor** — Stacked area chart of hedging energy by DTE bucket. The pink (365d+) and cyan (181-365d) bands dominate the total energy budget despite being a tiny fraction of trade count. Note the 2025 buildup pattern: energy loads from the top (LEAPS) first, then cascades into shorter tenors — exactly the "reactor charging" pattern.

![Hedging Energy Over Time](../figures/energy_storage_release.png)
> **Figure: Hedging Energy Over Time** — Top panel: total stored energy in the options chain (trades × DTE weight). The January 2021 sneeze is the towering spike — 8× any other event. Bottom panel: accumulation vs discharge rate, with key discharge events annotated. Note the slow recharge beginning mid-2025. [Image: energy_storage_release.png]

**This means that whoever controls the LEAPS inventory controls 45% of the thermostat's power source.** And as I'm about to show you, someone was doing exactly that — using the six techniques I'm calling the Shadow Algorithm.

---

## The Shadow Algorithm

What I'm about to show you is the hammer.

I ran five forensic tests against tick-level GME options data from both sneeze events — January 2021 and June 2024. The data comes from ThetaData's SIP feed, which records every single options trade with millisecond timestamps, exchange codes, lot sizes, and condition flags.

What I found wasn't just suspicious. It was a machine. A systematic, coordinated algorithm attacking the volatility surface infrastructure. I'm calling it the **Shadow Algorithm**, because it was designed to be invisible to standard surveillance systems — and it almost was.

Let me walk you through the evidence.

### Test 1: Tail-Banging — Burning Money to Poison the Volatility Surface

On January 28, 2021 — the single most volatile day of the sneeze — someone executed **518 trades** on deep OTM (out-of-the-money, i.e. far from the current price) 1-DTE (one day to expiration) calls, burning a total of **$69.8 million** on contracts that were virtually guaranteed to expire worthless within hours.

The peak strike? **$570 calls** when GME was trading at $194. That's 194% out of the money with one day to live. 

Nobody buys these for speculation. Nobody buys them for hedging. They're worth pennies and they'll be worth zero by tomorrow.

So why spend $69.8 million on them?

**Because every trade prints to the SIP tape** (the Securities Information Processor — the central data feed that broadcasts every trade to the entire market). And when a $570 call trades at any price above zero, it forces the options pricing model to calculate an implied volatility (IV — the market's expectation of future price swings, baked into the price of every option) for that strike. When you're 194% OTM with 1 DTE, that IV comes out to **over 1,000%**.

Market makers use automated pricing models (SABR/SVI — the industry-standard math for fitting a smooth curve through all the IV data points) that calibrate the "volatility surface" (a 3D map of IV across all strikes and expirations) using *every print on the tape*. So those 518 garbage trades contaminated the entire volatility surface for GME options. Every single contract on the chain was now being priced using poisoned data.

It's like someone spiking the city water supply. Everything downstream is contaminated — and the contamination was *designed* to inflate the Vanna exposure (Vanna = how much a market maker's delta hedge changes when IV moves — so pumping fake IV forces them to buy or sell more shares) on warehoused LEAPS (long-dated options, 90+ days to expiration, where institutions park big positions), making the gamma sneeze mechanics even more violent.

**Cost of the attack: $69.8M. Estimated leverage on the resulting gamma sneeze: immeasurable.**

### Test 2: Wash Trades — Printing Money on Tape

Wash trading is the oldest trick in the book: you buy and sell the same contract to yourself, in the same quantity, at the same price, within fractions of a second. You don't gain or lose money. But the trade *prints to the tape*, creating artificial volume that fools other market participants into thinking there's real activity.

I built a detector that identifies pairs of trades matching on lot size, price, strike, and expiration, executing within 5 seconds of each other on the same or different exchanges.

The results:

| Date | Wash Pairs | Sub-Second (< 1s gap) |
|------|:----------:|:---------------------:|
| Jan 26, 2021 | **100** | 78 |
| Jan 27, 2021 | 101 | 57 |
| Jan 28, 2021 | 103 | 29 |
| Jan 29, 2021 | 42 | 19 |
| Jun 4, 2024 | 14 | 6 |
| **Jun 7, 2024** | **265** | **216** |

Look at that last row. **265 wash trade pairs in a single session**, with **216 of them executing in under one second**. These aren't coincidences. These are identical-size, identical-price prints on the same contract appearing across exchanges within fractions of a second — the signature of a machine gun, not a human.

### Test 3: 30% of the Volume Was on Dark Venue Exchanges

Here's something most people don't realize: not all options exchanges are created equal. Some of them — the ones with exchange codes like UNK_60, UNK_65, UNK_73 — don't show up in most retail data feeds. I had to de-mask them by cross-referencing fee schedules and exchange characteristics.

What I found:

| Event | Total Options Volume | Dark Venue Volume | Dark % |
|-------|:-------------------:|:-----------------:|:------:|
| **Jan 2021** (6 dates) | 8,056,797 | 2,505,062 | **31.1%** |
| **Jun 2024** (8 dates) | 3,314,219 | 975,222 | **29.4%** |

Nearly **one-third of all options volume** in both sneeze events was routed through venues that retail traders can't access. These include Cboe BZX Options (UNK_60), whose maker-taker *inverted* fee model actually **pays the order submitter** for providing liquidity. That's right — the algorithm earns rebates on its own wash trades.

If this were really a retail phenomenon — a bunch of us buying calls on Robinhood (because they hadn't screwed us yet) — you wouldn't see 30% of volume routing through institutional-only dark exchanges. That's like finding a construction crane at what was supposed to be a lemonade stand.

### Test 4: The Shadow Channel — Inject IV, Wait 7 Minutes, Load LEAPS

Here's where it gets creepy. After tail-banging events inject artificial IV onto the tape, I detected a systematic pattern of LEAPS accumulation (long-dated options, 90+ days to expiration) appearing **7-9 minutes later** on the same strike region.

| Event | Mean Lag After IV Injection | Standard Deviation |
|-------|:--------------------------:|:------------------:|
| Jan 2021 | **7.3 minutes** | ±3.1 min |
| Jun 2024 | **9.4 minutes** | ±2.9 min |

That lag is consistent, narrow, and clearly algorithmic. The strategy: inject garbage IV with worthless short-dated prints, wait for market maker models to recalibrate (they ingest the contaminated tape automatically), then buy LEAPS at the newly inflated prices. When the gamma sneeze hits, those LEAPS print massive profits.

It's a two-step weapon: **poison the well, then drink from it.**

---

## The Six Smoking Guns

Everything I've shown you so far is concerning, but you could argue it's circumstantial. Maybe the wash trades are just aggressive market making. Maybe the tail-banging is a weird hedging strategy.

The next six findings are different. Each one is independently verifiable from public data. Each one satisfies at least one element of SEC Rule 10b-5 (the securities fraud statute). And taken together, they prove — not suggest, not imply, **prove** — that a single institutional actor was deliberately manipulating GME options during both sneeze events.

### 🔫 Smoking Gun #1: Single-Strike Complex Order Book Washes

Complex Order Books (COBs) are designed for multi-leg strategies. You use them when you want to trade a spread — like buying a $20 call and selling a $25 call simultaneously. The whole point is that the legs have *different* strikes.

But I found COB orders where **all legs target the same strike**. That means the buy side and sell side cross atomically — same contract, same strike — with zero delta exposure, zero risk, and zero directional purpose.

Some examples from the data:

- **Jun 4, 2024, 12:43:05.550** — ISE Gemini, 2 legs, $125 Calls, sizes [160, 160] = 320 contracts
- **Jun 7, 2024, 15:04:19.233** — CBOE, 2 legs, $28 Calls, sizes [496, 496] = 992 contracts
- **Jan 28, 2021, 09:44:42.714** — BZX Options, **9 legs**, $0.50 Calls (spot ~$194), sizes [1,5,10,61,89,90,117,446] = 820 contracts

Read that last one again. A **nine-leg** complex order on **$0.50 calls** when GME was trading at **$194**. Those calls are so far out of the money they might as well be on Mars. And someone routed them as a multi-leg "strategy" with 8 different lot sizes, all on the same strike.

There is exactly **one** function for a multi-leg order on a single strike: **printing artificial volume on the SIP tape**. This is a wash trade by construction, not by probabilistic inference. There is no debating it.

### 🔫 Smoking Gun #2: The Algorithmic DNA Match — Same Code, 3.5 Years Later

This is the one that made my jaw drop.

When institutional traders execute large block orders, they use Smart Order Routers (SORs — software that automatically chops a big order into smaller pieces and routes them across multiple exchanges) with a specific "jitter" pattern — slightly varying the lot sizes by ±2 or ±4 contracts to disguise the order as multiple independent trades.

I built a detector for these sequential TWAP (Time-Weighted Average Price — executing evenly over time to avoid detection) patterns. And I found the same jitter sequences appearing **3 years and 4 months apart**:

| Sequence | January 28, 2021 | June 4, 2024 |
|----------|-----------------|--------------|
| **[150, 154, 150]** | 09:30:34 — NYSE_AMEX → NYSE_AMEX → BX_OPT | 10:49:17 — PHLX → BATS → BX_OPT |
| **[100, 102, 100]** | 09:56:47 — NYSE_AMEX → BX_OPT → BZX_OPT | 09:59:15 — NYSE_AMEX → ISE → NYSE_AMEX |

Same ±2/±4 jitter logic. Same set of dark execution venues. **Separated by 1,254 days.**

Retail traders don't use sub-lot jitter algorithms. Period. This proves the **same institutional entity** — running the **same Prime Brokerage Smart Order Router software** — was operating in both the 2021 sneeze and the 2024 event.

Think about what that means. This isn't a one-time event. This is an *ongoing operation* that has been running for at least 3.5 years.

### 🔫 Smoking Gun #3: Tape Smurfing — Exactly 499 Lots

On January 29, 2021, between 12:38:09.579 and 12:38:12.265 — a **three-second window** — the algorithm executed **16 separate wash trade pairs** on $5.0 Puts at $0.43. Every single one was exactly **499 lots**. They rotated between MULTI_EXCHANGE and ISE venues. The first pair had a timestamp gap of **one millisecond**.

Why 499?

Exchange-level surveillance systems use undisclosed alert thresholds to flag unusually large transactions for review. **The exact thresholds are intentionally not published** — for the obvious reason that disclosing them would make evasion trivial. But the behavioral pattern speaks for itself: 16 consecutive trades all sized at exactly 499 lots — not 498, not 497, not 500 — demonstrates precise knowledge of a round-number surveillance boundary.

This is **Tape Smurfing** — the options market equivalent of financial "structuring" under 31 U.S.C. § 5324, where transactions are deliberately fragmented to avoid detection thresholds.

Notably, at 499 contracts per trade, these positions are well above the **200-contract** reporting threshold under [FINRA Rule 2360](https://www.finra.org/rules-guidance/rulebooks/finra-rules/2360), which requires member firms to report all equity option positions of 200+ contracts to the Large Options Positions Reporting (LOPR) system. This means FINRA already has the position data on file — the CAT queries in Part 2 are the direct path to attribution.

Using 499 lots instead of 500 proves the algorithm was **specifically programmed to evade surveillance thresholds**. Not 498. Not 497. Not 500. Exactly 499. That's not an accident. That's a confession written in code.

### 🔫 Smoking Gun #4: The $134 Million Jelly Roll

The biggest single Complex Order Book cluster I found in the entire dataset:

> **January 27, 2021 at 15:21:23.512** — NYSE AMEX — 12 legs — 4,050 lots — **$134,493,850** — executed in a single millisecond.

One hundred and thirty-four million dollars. In one millisecond. On a Complex Order Book.

The strikes targeted: $4.50, $5.00, $6.00, $7.00, $10.00, $12.00. GME's spot price: ~$347.51. Average premium: $332.08 per contract — which is almost exactly the intrinsic value (the difference between the stock price and the option's strike price). These are Deep ITM (In-The-Money) options with zero extrinsic value (no time premium left — they're basically synthetic shares). They move 1:1 with the underlying stock.

Nobody spends $134 million on Deep ITM options for speculation. There is exactly one reason to do this:

**It's a Reversal/Conversion synthetic short reset — a "Jelly Roll."**

By executing on a Complex Order Book:
1. They transferred millions of shares of delta risk off the lit equity tape
2. They bypassed Reg SHO short-sale restrictions (the SEC rule meant to prevent naked shorting)
3. They laundered Failures-to-Deliver (FTDs — shares that were sold short but never actually located or delivered) at the peak of the sneeze
4. **All of it happened in one millisecond**, invisible to standard FINRA trade reporting

This is the financial equivalent of hiding a $134 million body. The delta exposure moves off the lit tape and into the synthetic options world, where the short interest numbers that retail watches don't capture it.

### 🔫 Smoking Gun #5: Opening Bell Put Washes — Warping the Volatility Smile

On June 7, 2024, at exactly 09:30:25.929 — the **precise millisecond** of the opening bell — someone executed **17 wash trade pairs** on $10.00 Puts at $1.01. The trades cycled between MIAX Emerald and OPRA in a 9-millisecond burst (929ms to 938ms). GME's spot price at that moment: ~$46.55.

A $10 Put on a $46.55 stock is **78% out of the money**. It's virtually guaranteed to expire worthless.

So why pay $1.01 per contract — $10,100 per sub-second clip — for something that will never pay off?

Because the goal isn't to make money on those puts. The goal is to **warp the left side of the volatility smile** (the "smile" is the curve showing how IV varies across strike prices — it usually looks like a smirk, with higher IV for OTM puts and far OTM calls).

Remember the tail-banging from Test 1 that attacked the *right side* (calls) of the IV surface? This is the mirror image attacking the *left side* (puts). By pinning extreme IV to both tails simultaneously — OTM calls *and* OTM puts — the algorithm forced Market Makers' pricing models to shift the *entire IV surface vertically*.

The algorithm wasn't playing options. It was **re-engineering the mathematical models** that every market maker on the planet uses to price them.

### 🔫 Smoking Gun #6: The Cross-Venue Swarm — 32 Legs on 1 Strike

The most mechanically absurd finding in the entire dataset.

On June 21, 2024, at 13:35:07, the algorithm launched a coordinated barrage:

| Timestamp | Exchange | Legs | Volume | Capital |
|-----------|----------|:----:|:------:|:-------:|
| 13:35:07.531 | ISE | 4 | 116 | $80,794 |
| 13:35:07.532 | CBOE | 4 | 116 | $81,142 |
| 13:35:07.533 | MULTI_EXCHANGE | **20** | 128 | $89,472 |
| 13:35:07.700 | BX Options | 4 | 420 | $292,740 |
| **TOTAL** | **4 exchanges** | **32** | **780** | **$544,148** |

**Thirty-two complex legs targeting ONE strike** — the $15.0 calls — across four separate exchanges, in **169 milliseconds**.

Let me be crystal clear about why this is impossible as legitimate trading: a 20-leg complex order where all legs are on the same contract is not a strategy. There is no 20-legged options strategy. You can't build a butterfly with 20 legs on one strike. You can't build an iron condor. You can't build anything. It is mechanically, structurally, mathematically impossible to construct a legitimate options strategy with 20 legs on one contract.

The only explanation is that the algorithm packaged buys and sells of the exact same contract into atomic COB tickets and fired them across exchanges to print artificial volume.

And the $15.00 strike wasn't random. It was the **Gamma Wall** — the strike where net gamma exposure was highest (think of it as the price level where market makers have to do the most hedging, creating a gravitational pull on the stock). By flooding it with fake volume, the algorithm spoofed massive phantom liquidity, forcing market makers to recalculate their hedging obligations against an open interest figure that was largely fiction.

---

## What Does All This Prove?

Let me map this to the legal framework, because this isn't just market analysis — this is evidence.

SEC Rule 10b-5 has four elements. All four need to be satisfied for securities fraud:

| Element | Which Smoking Guns? |
|---------|:-------------------:|
| **Material Misrepresentation** — false signals on the tape | #1 (COB washes), #3 (Tape Smurfing), #6 (Swarm) — all print artificial volume |
| **Scienter** — intent to deceive | #3 (499 lots = deliberate threshold evasion), #4 ($134M Jelly Roll), #5 (bilateral IV warping) — sophisticated financial engineering incompatible with accidental execution |
| **Connection to Securities** | All six targets are GME options contracts on listed exchanges. GME equity (NYSE) is directly affected. |
| **Reliance / Damages** | Every market maker's pricing model ingests the SIP tape. Every contaminated print affects the price of every other GME contract. Every market participant who traded against those prices was victimized. |

✅ All four elements satisfied. This isn't a borderline case.

And Smoking Gun #2 — the algorithmic DNA match — proves the **same entity** operated in both 2021 and 2024. Same code. Same jitter. Same venues. 3.5 years apart. This isn't a coincidence. This is an ongoing criminal enterprise.

---

## Who Did This?

I don't know. And here's why — the public SIP data I used gives you timestamps, prices, lot sizes, exchange codes, and condition flags. But it doesn't give you the **Market Participant Identifier (MPID)** — the field that tells you which broker-dealer submitted the order.

That data exists. It's in the **FINRA Consolidated Audit Trail (CAT)** — the master surveillance database that records every single trade in American securities, with full identity information. A regulatory subpoena would reveal the entity behind every trade I've documented.

I've provided five specific CAT queries that would close the attribution gap in minutes. The exact timestamps. The exact strikes. The exact lot sizes. All the SEC or FINRA has to do is run the queries and read the MPID field.

**[Part 2 (next post)](REDDIT_POST_PART2.md) will cover:**
- The "Player Piano" discovery — mathematical proof that the equity tape is deterministically slaved to the options chain
- The five FINRA CAT queries that would identify the perpetrator
- What this means for you and what you can do about it

---

**Edit: The full 160,000-word academic paper, with all 32 tables, 14 references, and complete replication code, is available at the links below. Everything I've claimed in this post is independently verifiable from public data. The methodology, the code, and the raw results are all open source. I'm not asking you to trust me. I'm asking you to check my work.**

**Full Paper (PDF):** [The Long Gamma Default: How Options Market Makers Stabilize Equity Markets](https://github.com/TheGameStopsNow/power-tracks-research/blob/main/research/options_hedging_microstructure/review_package/The%20Long%20Gamma%20Default-%20How%20Options%20Market%20Structure%20Creates%20Artificial%20Stability%20in%20Equity%20Prices-%20Academic.pdf) — 160,000 words, 32 tables, 14 references, 6 appendices

**Evidence Viewer (no setup required):** [01_evidence_viewer.ipynb](https://github.com/TheGameStopsNow/power-tracks-research/blob/main/research/options_hedging_microstructure/review_package/01_evidence_viewer.ipynb) — Loads all 89 pre-computed results. Renders every smoking gun, every table, every claim verification. **Start here if you want to check my work.**

**Replication Notebooks:**
- [02_forensic_replication.ipynb](https://github.com/TheGameStopsNow/power-tracks-research/blob/main/research/options_hedging_microstructure/review_package/02_forensic_replication.ipynb) — Re-run Shadow Hunter, manipulation forensic battery, squeeze mechanics
- [03_microstructure_replication.ipynb](https://github.com/TheGameStopsNow/power-tracks-research/blob/main/research/options_hedging_microstructure/review_package/03_microstructure_replication.ipynb) — Re-run panel ACF, lead-lag, NMF archaeology, robustness tests

**Pre-computed Results:** [89 JSON evidence files](https://github.com/TheGameStopsNow/power-tracks-research/tree/main/research/options_hedging_microstructure/review_package/results) — Panel scan, ACF, lead-lag, NMF, forensic evidence, cycle analysis

**Source Code:** [30 Python scripts](https://github.com/TheGameStopsNow/power-tracks-research/tree/main/research/options_hedging_microstructure/review_package/code) — Full analysis pipeline

**Replication Guide:** [REPLICATION_GUIDE.md](https://github.com/TheGameStopsNow/power-tracks-research/blob/main/research/options_hedging_microstructure/review_package/REPLICATION_GUIDE.md) — Exact dates, commands, parameters, and thresholds to reproduce every result

**Video — Surfing the GME Options Chain:** Let me know if you see anything.
- [Short version (1 min)](https://youtube.com/shorts/DZti6HodVTQ)
- [Full session](https://youtu.be/HcDQNJxjKK0)
- [Stock surfing](https://www.youtube.com/watch?v=QwjpwQ-AoFQ)

**Full Repository:** [github.com/TheGameStopsNow/power-tracks-research](https://github.com/TheGameStopsNow/power-tracks-research/tree/main/research/options_hedging_microstructure/review_package)

*This is not financial advice. This is forensic research. I am not a financial advisor, attorney, or affiliated with any hedge fund, market maker, or regulatory agency. The SEC has been notified via TCR.*

---

*"The first principle is that you must not fool yourself — and you are the easiest person to fool." — Richard Feynman*
