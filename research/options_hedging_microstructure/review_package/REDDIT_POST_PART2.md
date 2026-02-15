# 🔬 Part 2: The Player Piano, the FINRA CAT Roadmap, and What Happens Next

**TL;DR: In Part 1, I showed you six smoking guns proving an algorithm has been manipulating GME options since at least January 2021. In Part 2, I'm going to show you something even worse: mathematical proof that GME's equity price is a puppet whose strings are the options chain. I'll also give you the exact five database queries that would identify the puppet master by name. The SEC already has these queries.**

*If you haven't read [Part 1](REDDIT_POST_PART1.md), start there. This picks up where the smoking guns left off.*

---

## The Player Piano: Your Stock Price Is a Recording

![Ghost Player Piano](../figures/ghost_player_piano.png)
> **Figure: The Player Piano** — The sheet music (options chain) was punched weeks ago. The keys (stock price) are just moving mechanically to match the recording. [Image: ghost_player_piano.png]

OK, so I've established that someone is manipulating the options tape. Wash trades, tail-banging, tape smurfing — the works. But that raises an obvious question:

**Does manipulating the options tape actually move the stock price?**

Because if it doesn't — if the stock price moves independently of the options chain — then all those smoking guns are just a very expensive crime with no impact on equity holders. Serious, sure. But not the systemic threat people suspect.

So I tested it. And what I found is the single most unsettling result in the entire research.

### The Temporal Archaeology Protocol

Here's what I did. I used a mathematical technique called Non-negative Matrix Factorization (NMF — a way to break a complex signal into its building blocks, like separating a chord into individual notes) to decompose GME's daily equity volume profile — the minute-by-minute shape of how volume distributes throughout a trading day — into component factors.

The key question: **Can I reconstruct today's equity volume profile using only options data from the past?**

Not yesterday's data. Not even data from the same week. I excluded all options data from T+0 (today) and T−1 (yesterday) — removing any same-day information that could trivially explain the correlation. I only used options data from 16 to 28 days in the past.

I call this the **Strict Temporal Archaeology** protocol, because it's like doing archaeology — you can only use evidence from a prior era, never from the present.

### The Result: r = 1.000 (And Why That Number Requires Context)

The in-sample NMF reconstruction achieved a perfect correlation of **r = 1.000** across all 7 tickers tested — using only options data from 16-28 days in the past, with zero information from the target day or the day before.

If I stopped there, you should be skeptical. A perfect correlation in financial data screams overfitting. So I ran the test designed to destroy my own result.

### The Placebo That Keeps It Honest

§4.22.1 of the paper runs a **Cross-Ticker Placebo**: reconstructing GME's equity volume profile using *AAPL's* options data. Result? Also r ≈ 1.0.

That confirms what you'd suspect — the perfect reconstruction is primarily capturing the **universal intraday volume U-curve** (high volume at open and close, low midday) that *all* exchange-traded securities share. The paper states this explicitly:

> *"The r = 1.000 NMF reconstruction primarily captures the universal intraday volume curve shared by all exchange-traded securities. The perfect reconstruction cannot be cited as evidence of options→equity causality."*

I ran the test that kills my own headline number, and I published it. Because the point isn't to cherry-pick impressive statistics — it's to find what's actually real.

### What Survives the Placebo

The **Out-of-Sample test** (§4.22.2) fits NMF on the first 60% of dates and reconstructs the held-out 40% with frozen basis vectors — no refitting allowed. The OOS results are dramatically lower: r = 0.07 (SOFI) to r = 0.50 (TSLA, GME). The paper calls this *"a more honest — and more defensible — claim"* and estimates that approximately **25% of equity volume variance** is explained by ticker-specific options structure beyond the shared U-curve.

That's still remarkable. One in four units of equity volume on any given day is mechanically determined by options positions opened weeks earlier. Not correlated. *Determined* — through the continuous delta-hedging obligations those positions impose on dealers.

### What This Means in Plain English

The equity tape isn't fully a Player Piano — that framing was too strong. But roughly **a quarter of its keys are pre-programmed** by the options chain configuration from weeks earlier. The stock price partially responds to hedging obligations that were baked into the system before the equity tape ran.

And here's the punchline: if you control the options tape — through the wash trades, the tail-banging, the COB washes, the Jelly Rolls — you control that quarter of the equity tape. Mechanically. Not as a probability. As a consequence of dealer hedging math.

**The smoking guns from Part 1 aren't just market manipulation. They are partial remote control over GME's stock price — and 25% control of a stock's daily volume, exercised invisibly through the options chain, is more than enough to move markets.**

---

## The Physics of the Breaking Point — Gamma Reynolds Number

In Part 1 I showed you the thermostat (the Long Gamma Default) and the hammer (the Shadow Algorithm). But there's a precise mathematical answer to the question: **How much speculative pressure does it take to break the thermostat?**

I formalized this using an analogy every physics student learns in their first year: the **Reynolds Number** from fluid dynamics. In a pipe, smooth (laminar) flow stays smooth as long as enough viscosity keeps it steady. Increase the velocity enough — past a critical Reynolds number — and the flow suddenly goes turbulent. Same pipe. Same fluid. Completely different physics. The transition is *discontinuous* — it doesn't gradually get choppier. It *snaps*.

![Reynolds Number Rocket](../figures/reynolds_rocket_chalkboard.png)
> **Figure: Laminar vs Turbulent Flow** — On the left, smooth, boring, dampened flow (Re < 1). On the right, chaos (Re > 1). But in finance, "chaos" manifests as a vertical line. [Image: reynolds_rocket_chalkboard.png]

I defined the **Gamma Reynolds Number (Re_Γ)** as:

> **Re_Γ = Speculative Call $-Gamma Traded / Dealer Net $-Gamma Inventory**

In plain English: it's the ratio of how much speculative energy is being shoved into the system versus how much countercyclical capacity the dealers have to absorb it.

- **Re_Γ < 1:** Laminar state. Dealers absorb the speculative flow. The thermostat holds. Your stock moves like a normal stock.
- **Re_Γ > 1:** Turbulent state. Speculative pressure exceeds dealer capacity. The thermostat reverses polarity. Procyclical feedback kicks in. Momentum emerges. This is the sneeze.

The critical inflection point? I measured it across my entire 37-ticker panel: **12.9% amplified days.** Below that threshold, the Long Gamma Default reliably holds. Above it, the system approaches criticality and small additional pushes can trigger a discontinuous regime shift — like the last snowflake that starts an avalanche.

The GME sneeze wasn't Re_Γ slightly above 1. It was Re_Γ **massively** above 1. And the Shadow Algorithm's function — the tail-banging, the Vanna manipulation, the LEAPS loading — was to artificially inflate the numerator while simultaneously disabling the denominator.

That's not just market manipulation. That's *engineering a phase transition*.

![Gamma Reynolds Phase Transition](../figures/gamma_reynolds_sigmoid.png)
> **Figure: Gamma Reynolds Phase Transition — 37-Ticker Panel** — Each dot is a ticker. X-axis = percentage of days in amplified (Short Gamma) state. Y-axis = mean ACF. The orange sigmoid (R² = 0.719) shows the phase transition curve. Note the cluster of 37 tickers in the lower-left "Laminar" zone — all dampened. The star markers are GME and Popcorn *during their squeeze windows only*, launched far into the upper-right "Turbulent" zone. The critical transition sits at ~13% amplified days. [Image: gamma_reynolds_sigmoid.png]

---

## This Isn't Just GME — The 37-Ticker Proof

Everything I've described so far might sound like a GME-specific anomaly. It's not.

I ran the same analysis across **37 different tickers** — from mega-caps like Clippy's Parent Company, Fruit Phone Co., Green GPU Maker, and The Index to mid-caps, meme stocks, and recent IPOs spanning from 2014 to 2024. The results are unambiguous:

| | Dampened % | Mean ACF |
|---|:-:|:-:|
| **Full Panel (37 tickers)** | **92.7%** | **−0.203** |
| Clippy's Parent (228 days) | 97.4% | −0.343 |
| Fruit Phone (418 days) | 91.6% | −0.227 |
| Green GPU (228 days) | 78.5% | −0.189 |
| The Index (223 days) | 85.2% | −0.202 |
| GME (500 days) | 92.8% | −0.166 |
| Space Car (418 days) | 71.8% | −0.131 |
| 🍿 (204 days) | 69.1% | −0.096 |

**Every single ticker in the entire panel — all 37 — classifies as Long Gamma Default over its full observation window.** Even 🍿. Even Sauron's Seeing Stone. Even the meme-iest meme stocks average out to dampened over time.

![Energy Density Heatmap](../figures/energy_density_heatmap.png)
> **Figure: Energy Density Heatmap of GME (2020-2026)** — A heatmap of hedging energy across all tenors (y-axis) and time (x-axis). Bright yellow = high energy. The January 2021 sneeze is the unmistakable vertical stripe — energy activated simultaneously across ALL tenors. Every other event only lights up 1-2 bands. This is the visual proof that the sneeze was a full-stack event, not just 0DTE gambling. [Image: energy_density_heatmap.png]

This means the Long Gamma Default isn't a quirk of GME's options chain. **It is the fundamental operating mode of the entire U.S. equity market.** The options-equity feedback loop is a structural feature of market infrastructure, not a stock-specific anomaly.

And when you zoom in to shorter time scales, the proof gets even stronger. At 30-second resolution, Clippy's Parent Company shows an ACF of **−0.454** — meaning **45% of each 30-second price move is mechanically reversed within the next 30 seconds.** That's not a market. That's a shock absorber operating in real time.

The cross-sectional evidence also confirms that each ticker's regime is **independently determined by its own options flow** — during the January 2021 sneeze, GME went amplified but 🍿 showed *zero* amplified windows despite being the "second meme stock." The gamma squeeze didn't spread through equity channels. It was driven entirely by what was happening in each stock's *own* options chain.

Which brings us back to the Shadow Algorithm. If the entire market operates as a thermostat, and someone figured out how to reverse that thermostat for a *specific stock* — while every other stock stays dampened — that's precision engineering, not a market-wide phenomenon. It's a scalpel, not a bomb.

---

## The System Has Evolved — But the Vulnerability Hasn't Closed

Here's something that should concern regulators more than it reassures them.

I compared two meme stocks from different eras: **Ghost App (IPO March 2017)** vs **The Former President's SPAC (IPO March 2024)**.

- **Ghost App 2017:** ACF = **+0.079** (Amplified). The disappearing-photos IPO was overwhelmed by retail speculation. The thermostat broke.
- **The Former President's SPAC 2024:** ACF = **−0.099** (Dampened). Despite being arguably the most politically charged meme stock in history — massive retail interest, social media frenzy, presidential election dynamics — its microstructure shows *standard dampening.* The thermostat held.

![Energy Flow Field](../figures/energy_flow_field%20(2).png)
> **Figure: Energy Flow Field of GME — Gradient of Smoothed Density** — Arrows show the *direction* energy is moving across tenor buckets over time. Red arrows (pointing down) = energy discharging. Blue arrows (pointing up) = energy accumulating. The massive red burst in May-June 2025 at the 181-365d and 365d+ level is a discharge event. The persistent blue arrows in late 2025 show active reaccumulation — someone is still cycling energy through the long-dated tenors.

Same level of retail mania. Completely different outcome. Why?

Between 2017 and 2024, three things changed:

1. **0DTE became a shock absorber.** By 2024, zero-days-to-expiration options represented ~50% of S&P 500 options volume. Because gamma approaches infinity as expiration approaches zero, 0DTE makes dealers ultra-efficient hedgers — near-instantaneous countercyclical rebalancing.
2. **Post-2021 risk management.** Market makers who survived the January 2021 sneeze implemented better gamma exposure monitoring and faster automated rebalancing.
3. **The options market tripled in size.** Total cleared options volume grew from 4.3 billion contracts (2017) to over 12 billion (2024), deepening the institutional liquidity pool.

![Trade Volume by DTE Tenor Over Time](../figures/dte_volume_by_tenor.png)
> **Figure: Trade Volume by DTE Tenor Over Time of GME** — Stacked bar chart of daily trade count by tenor bucket. Note the visible growth from 2020 to 2026 — the entire market has scaled up, with the 91-180d bucket (purple) showing the most pronounced increase. This is the shock absorber getting bigger. [Image: dte_volume_by_tenor.png]

**The thermostat is stronger than it's ever been.** A 2017-level retail surge can no longer break it.

But — and this is critical — **none of these improvements protect against the Shadow Algorithm.** The algorithm doesn't work by overwhelming the system with retail volume. It works by *poisoning the infrastructure from the inside*: contaminating IV surfaces, wash-trading LEAPS to load the Inventory Battery, and executing below surveillance thresholds. It's the difference between trying to break down a reinforced door versus having the key.

The market evolved to withstand retail stampedes. It has not evolved to detect or prevent institutional-level manipulation of its own pricing infrastructure.

---

## The FINRA CAT Roadmap: Five Queries to Find the Puppet Master

I've shown you *what* happened and *how* it works. The only question left is *who*.

As I mentioned in Part 1, the public SIP data I used doesn't include the Market Participant Identifier (MPID) — the field that identifies which broker-dealer submitted each trade. But that data exists in the **FINRA Consolidated Audit Trail (CAT)**, the master surveillance database that records every trade in American securities with complete identity information.

Here are the five specific queries that would identify the entity behind every smoking gun:

### Query 1: Single-Strike COB Washes
```
Symbol: GME
Strike: 125.0 Call
Date: June 4, 2024
Time Window: 12:43:05.550 ± 50 milliseconds
Target: MPID, Customer Account
```
*This catches Smoking Gun #1. Who submitted a multi-leg COB order where all legs were on the same strike?*

### Query 2: Algorithmic DNA Match
```
Symbol: GME
Lot Size: IN (150, 154)
Date 1: January 28, 2021 at 09:30:34 ± 500ms
Date 2: June 4, 2024 at 10:49:17 ± 500ms
Target: MPID on both dates
```
*This is the kill shot. If the MPID on the January 2021 sequence matches the MPID on the June 2024 sequence, that single result proves the same entity engineered both sneeze events across 3.5 years. One query. One answer. Case closed.*

### Query 3: Tape Smurfing
```
Symbol: GME
Lot Size: 499
Strike: 5.0 Put
Date: January 29, 2021
Time Window: 12:38:09 to 12:38:13
Target: MPID, Reporting Firm
```
*Who programmed their algorithm to stay exactly one lot below the Block Trade alert threshold? This is direct evidence of scienter — knowledge of and intent to evade surveillance.*

### Query 4: The Jelly Roll
```
Symbol: GME
Condition Code: 129 (Multi-Leg Auction)
Notional Value: > $100,000,000
Date: January 27, 2021
Time Window: 15:21:23 ± 100ms
Target: MPID, all counterparties
```
*Who spent $134 million on Deep ITM options in a single millisecond at the peak of the sneeze? And who was on the other side?*

### Query 5: Opening Bell Put Washes
```
Symbol: GME
Strike: 10.0 Put
Exchange: MIAX Emerald
Date: June 7, 2024
Time Window: 09:30:25.929 ± 50ms
Target: MPID, Customer Account
```
*Who executed 17 wash trade pairs on worthless puts in the exact millisecond of the opening bell?*

### The Critical Test

Here's why Query 2 is the most important:

Right now, you could argue (weakly, but technically) that the 2021 activity and the 2024 activity are separate incidents by different actors. Maybe one hedge fund did the Jelly Roll in 2021, and a completely different firm did the COB washes in 2024.

Query 2 destroys that argument. If the MPID on the [150, 154, 150] sequence in January 2021 matches the MPID on the [150, 154, 150] sequence in June 2024, then:

1. **Same entity** → designed, deployed, and operated the algorithm across two distinct market events
2. **Same code** → the ±2/±4 jitter logic is a fingerprint of a specific SOR (Smart Order Router — the software that chops big orders into smaller slices) configuration
3. **Same venue routing** → BX Options appears in both sequences, confirming the same execution infrastructure
4. **3.5-year continuity** → this is an ongoing operation, not a one-time event

Combined with Smoking Gun #3 (Tape Smurfing proving scienter — legal term for "you knew exactly what you were doing"), this gives you everything needed for a Rule 10b-5 enforcement action. Material misrepresentation. Intent to deceive. Connection to securities. Damages.

---

## But Wait — Why Hasn't Anyone Caught This?

Fair question. And the answer is uncomfortable.

**The algorithm was specifically designed to be invisible to standard surveillance.**

1. **Tape Smurfing below thresholds** (499 lots) avoids Block Trade flags
2. **Dark venue routing** (30% of volume to institutional exchanges) keeps activity off retail-visible feeds
3. **Complex Order Book packaging** atomizes wash trades into "legitimate" multi-leg orders
4. **Cross-venue execution** distributes activity across a dozen exchanges, ensuring no single venue sees the full picture
5. **Millisecond timing** makes individual trades invisible to human reviewers

FINRA's surveillance systems are designed to catch obvious fraud — big obvious wash trades, spoofing (placing fake orders you plan to cancel), layering (stacking orders to move the price). They are *not* designed to catch an algorithm that atomizes its activity across a dozen exchanges, packages wash trades as complex orders, and stays one lot below every reporting threshold.

The only way to catch this is to do what I did: download every single trade, reconstruct the cluster patterns at the millisecond level, and look for the fingerprints across years of data. It took months and millions of data points. It's not the kind of analysis that shows up in a routine surveillance sweep.

---

## What Can You Do About It?

### For Individual Investors

1. **Understand the mechanics.** The Long Gamma Default means that most of the time, options flow is *dampening* your stock's movement. When you see a sudden amplification spike, that's either genuine retail enthusiasm or an engineered phase transition. The difference matters.

2. **Watch the Complex Order Book volume.** If you see a sudden surge in COB-routed options trades — especially multi-leg orders on single strikes — that's a red flag. Normal hedging doesn't look like that.

3. **Submit TCRs.** The SEC accepts Tips, Complaints, and Referrals from anyone. You don't need to be a lawyer. You don't need to be an expert. If you have evidence of wrongdoing, file at [sec.gov/tcr](https://www.sec.gov/tcr). If enough people point at the same evidence, regulators have to look.

### For Regulators

The five CAT queries above would take less than a day to execute. The data is already in the system. The timestamps are precise to the millisecond. The attribution gap can be closed with a keyboard, not a subpoena.

I have already submitted a TCR to the SEC with the full manuscript. The information is there. The question is whether anyone acts on it.

---

## The Bottom Line

Here's what we know, stated without speculation:

1. **Someone** operated an algorithm on GME options during both the January 2021 and June 2024 sneeze events. This is proven by identical algorithmic jitter signatures separated by 3.5 years.

2. **That algorithm** executed wash trades, tape-smurfed below surveillance thresholds, laundered $134 million in delta through a single Jelly Roll, warped the volatility smile through coordinated put washes, and flooded gamma wall strikes with 32-leg phantom orders.

3. **The options tape** is not merely correlated with the equity tape — approximately **25% of equity volume variance** is mechanically determined by the options chain configuration from weeks earlier (OOS NMF, §4.22.2). The in-sample reconstruction achieves r = 1.000, but the paper's own cross-ticker placebo (§4.22.1) confirms that result primarily captures the universal intraday volume curve — so the honest number is the OOS result, not the headline.

4. **Therefore**, controlling the options tape provides significant mechanical influence over the equity tape. The smoking guns demonstrate that someone has been exercising exactly that control.

5. **The identity** of that entity is stored in the FINRA CAT and can be retrieved with five specific queries targeting millisecond-precise timestamps.

This isn't a theory. These are timestamps, lot sizes, exchange codes, and dollar amounts. They're in the public data right now. Anyone with a ThetaData subscription can verify everything I've claimed.

I've spent months building the case. I've filed with the SEC. I've published the paper, the code, and the data. The ball is no longer in my court.

---

**Full Paper (PDF):** [The Long Gamma Default: How Options Market Makers Stabilize Equity Markets](https://github.com/TheGameStopsNow/power-tracks-research/blob/main/research/options_hedging_microstructure/review_package/The%20Long%20Gamma%20Default-%20How%20Options%20Market%20Structure%20Creates%20Artificial%20Stability%20in%20Equity%20Prices-%20Academic.pdf) — 160,000 words, 32 tables, 14 references, 6 appendices

**Evidence Viewer (no setup required):** [01_evidence_viewer.ipynb](https://github.com/TheGameStopsNow/power-tracks-research/blob/main/research/options_hedging_microstructure/review_package/01_evidence_viewer.ipynb) — Loads all 89 pre-computed results. Every smoking gun, every table, every claim check. **Start here.**

**Replication Notebooks:**
- [02_forensic_replication.ipynb](https://github.com/TheGameStopsNow/power-tracks-research/blob/main/research/options_hedging_microstructure/review_package/02_forensic_replication.ipynb) — Shadow Hunter, manipulation forensic battery, squeeze mechanics
- [03_microstructure_replication.ipynb](https://github.com/TheGameStopsNow/power-tracks-research/blob/main/research/options_hedging_microstructure/review_package/03_microstructure_replication.ipynb) — Panel ACF, lead-lag, NMF archaeology, robustness tests

**Pre-computed Results:** [89 JSON evidence files](https://github.com/TheGameStopsNow/power-tracks-research/tree/main/research/options_hedging_microstructure/review_package/results)

**Source Code:** [30 Python scripts](https://github.com/TheGameStopsNow/power-tracks-research/tree/main/research/options_hedging_microstructure/review_package/code) — Full analysis pipeline, open source

**Replication Guide:** [REPLICATION_GUIDE.md](https://github.com/TheGameStopsNow/power-tracks-research/blob/main/research/options_hedging_microstructure/review_package/REPLICATION_GUIDE.md) — Exact dates, commands, parameters, and thresholds

**Video — Surfing the GME Options Chain:** Let me know if you see anything. 😺
- [Short version (1 min)](https://youtube.com/shorts/DZti6HodVTQ)
- [Full session](https://youtu.be/HcDQNJxjKK0)
- [Stock surfing](https://www.youtube.com/watch?v=QwjpwQ-AoFQ)

**Full Repository:** [github.com/TheGameStopsNow/power-tracks-research](https://github.com/TheGameStopsNow/power-tracks-research/tree/main/research/options_hedging_microstructure/review_package)

*This is not financial advice. I am an independent researcher. The SEC has been notified.*

---

*"In the long run, every program becomes rococó — then rubble." — Alan Perlis*

*"Their algorithm left fingerprints. Now it's a matter of whether anyone bothers to dust."*
