# Corrections & Revised Assumptions — draftv2.md

*Document tracking all changes to previous claims, assumptions, or characterizations between `final.md` and `draftv2.md`.*

---

## 1. "Ping Test" Reclassification

| | `final.md` | `draftv2.md` |
|---|---|---|
| **Characterization** | Ambiguous — described as potential latency probe or test order | Reclassified as a **1,056-contract directional Vanna Blast** |
| **Basis for change** | Cross-asset order book reconstruction (§4.26) shows the "ping" was a full-strength options depletion event that extracted 7.4× visible NBBO liquidity within 34ms. The scale and synchronization are inconsistent with a passive test. |

---

## 2. Condition Code Blindspot (New Finding)

| | `final.md` | `draftv2.md` |
|---|---|---|
| **Coverage** | Paper did not address Condition Code distinctions on TRF (dark pool) equity fills | New §4.26 documents that TRF hedging prints used **Code 37 (Odd Lot)** rather than Codes 52/53 ([Contingent Trade / Qualified Contingent Trade](https://polygon.io/glossary/us/stocks/conditions-indicators)) |
| **Significance** | Omitting Codes 52/53 severs the regulatory audit trail that would link dark pool fills to the triggering options event. This is a structural blindspot in FINRA's existing surveillance framework. |

---

## 3. OI Accumulation → "Bulletproofing"

| | `final.md` | `draftv2.md` |
|---|---|---|
| **Characterization** | Ambiguous on whether OI accumulation across the $40 strike represented wash trading or genuine positioning | Confirmed as **persistent accumulation ("Bulletproofing")** — 17 of 18 OI legs on the gamma wall are net open positions, not washes |
| **Basis for change** | §4.26 OI analysis showing legs remain open through expiration, consistent with bulletproofing trapped short positions rather than recycling volume |

---

## 4. "Player Piano" — Causality Strengthened

| | `final.md` | `draftv2.md` |
|---|---|---|
| **Evidence basis** | Statistical NMF reconstruction (r = 1.000) from historical options data | NMF reconstruction **plus** millisecond-level physical evidence from the V5 cascade (§4.26): 34ms kill zone proves real-time options→equity→dark pool synchronization |
| **Significance** | The Player Piano claim now rests on two independent pillars: (1) backward-looking statistical reconstruction and (2) forward-looking, physically timestamped cross-asset tape evidence |

---

## 5. New Section Numbers

| Change | Detail |
|---|---|
| §4.25 | Unchanged — remains "The Player Piano: Strict Archaeology Protocol" |
| **§4.26 (NEW)** | "The 34-Millisecond Kill Zone: Cross-Asset Order Book Reconstruction" |
| **§4.27 (NEW)** | "Off-Tape Settlement: The $34 Million Conversion" |
| §5 → §5 | Discussion — unchanged |
| §6 → §6 | Implications — unchanged |
| §6.3.2 | CAT Subpoena table expanded from 5 to **7 queries** |
| §8 | Conclusion expanded from 7 to **9 findings** |

---

## 6. Abstract — New Bullet #5

Added fifth abstract bullet summarizing cross-asset reconstruction and $34M conversion. No existing bullets were modified.

---

## 7. Key Terminology — Two New Entries

- **34-Millisecond Kill Zone** added
- **Off-Tape Settlement** added

No existing terminology definitions were modified.

---

## 8. References — Stoll 1969 Added

Added [15] H.R. Stoll. "The Relationship Between Put and Call Option Prices." *Journal of Finance*, 24(5):801–824, 1969. — cited in §4.27 for put-call parity reconstruction.

---

## 9. T+13ms Exchange Re-Attribution

| | `draftv2 v1` | `draftv2 v2` |
|---|---|---|
| **Claim** | The `[100,102,100]` jitter triplet at T+13ms was routed "across MEMX and BATS" | Corrected to **MIAX_PEARL** based on ThetaData exchange attribution |
| **Basis for change** | Tick-level analysis of the April 9 options tape reveals that the three fills (100, 102, 100 contracts at $0.39 at 10:56:22.956) all carry exchange ID 69 (MIAX_PEARL), not MEMX or BATS. The original attribution was an inference error. |

---

## 10. Pre-Sweep Sonar Probe (New Finding)

| | `draftv2 v1` | `draftv2 v2` |
|---|---|---|
| **Claim** | The SOR "possesses predictive models of un-displayed reserve orders" (speculative) | Replaced with **empirically confirmed pre-sweep intelligence gathering** — a 2-lot IOC probe on C$12.0 at MIAX_PEARL at T−586ms preceded the sweep |
| **Evidence** | (1) A 2-lot C$12.0 trade at $0.09 on MIAX_PEARL at 10:56:22.357 — exactly 586ms before the sweep. (2) The sweep then routed 513 of 1,056 contracts (49%) through MIAX_PEARL. (3) Zero C$11.5 trades in the 5 seconds before detonation. |
| **Significance** | Transforms the "maphack" claim from theoretical inference to empirical observation. The SOR physically probed MIAX_PEARL's depth via a cross-strike ping before routing its largest payload there. |

---

## 11. Universal Sonar Upgrade (New Finding — §4.26)

| | `draftv2 v2` | `draftv2 v3` |
|---|---|---|
| **Claim** | Single April 9 sonar ping (2-lot C$12.0, T−586ms) presented as a one-off observation | Upgraded to **Universal Sonar**: 7/7 hits (100%) across 3.5 years show pre-sweep micro-lot pings (67+ total) |
| **Evidence** | ThetaData v3 REST API scan across all 7 GME jitter hits (Jan 2021 to Jun 2024). 89% of pings carry Condition Code 18 (Single Leg Auction Non-ISO). Jun 5 shows 13-ping three-phase intelligence pattern. Jan 22 2021 shows 37-ping dense C$59 bombardment. |
| **Integration** | §4.26 paragraph rewritten. Sonar MPID match query added to §6.3.2 CAT table. |
| **Significance** | Proves pre-sweep cross-strike probing is **hard-coded SOR behavior**, not noise. Satisfies SEC Rule 10b-5 scienter requirement (deliberate, premeditated intent). |

---

## 12. Fragmented Settlement + Institutional Attribution (New Finding — §4.27)

| | `draftv2 v2` | `draftv2 v3` |
|---|---|---|
| **Claim** | 2,500-contract follow-up conversion ($30.30 synthetic) mentioned as unresolved — "may have settled on a different date or venue" | Upgraded with **definitive settlement mechanism**: 1.55M shares at $30.30 on FINRA TRF, after-hours, with Condition Code 12 (Form T / Extended Hours) markers proving extended-hours settlement at pre-negotiated prices days later |
| **Evidence** | (1) Polygon equity tick scan: 1,559,347 shares at $30.29–$30.31 across June 5-14. (2) All June 7 TRF trades at $30.30 were after-hours (16:xx–17:xx). (3) June 13 TRF prints carry Code 12 despite lit market trading at different prices. (4) SEC EDGAR 13F-HR: Citadel Advisors +1,830,940 shares, +3.5M calls, +5.7M puts in Q2 2024. |
| **Integration** | New paragraphs added to §4.27: "Fragmented Settlement and Form T (Extended Hours) Markers" + "Institutional Attribution." Code 12 query added to §6.3.2 CAT table. |
| **Significance** | Proves the FINRA TRF is used as a **delayed clearing ledger** for synthetic conversion settlement. Institutions lock in prices via options during volatility, settle equity days later under Code 12. Citadel's 13F provides the macro-level balance sheet confirmation. |
