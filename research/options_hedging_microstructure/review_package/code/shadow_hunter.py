#!/usr/bin/env python3
"""
shadow_hunter.py — V4: Shadow Algorithm Hunter
================================================
Tape Painting & Cross-Tenor Skew Manipulation (Rule 10b-5)

Detects legally actionable manipulation patterns in tick-level options data:
  Test G: Tail-Banging       — Deep OTM 1-DTE block trades burning capital to warp IV surface
  Test H: Wash/Cross Trades  — Identical size+price+strike within seconds (pre-arranged crosses)
  Test I: Algorithmic Stepping— Sequential lot sizes (N, N-1, N-2...) on obscure exchanges
  Test J: Complex Order Book — Multi-leg spreads at same millisecond on dark venues
  Test K: Dark Venue Conc.   — UNK exchange routing proving institutional-only access

Uses tick-level options trade data from ThetaData parquet files.
Depends on manipulation_forensic.py for load_trades and constants.
"""

import sys, os, json, argparse
from pathlib import Path
from datetime import datetime, timedelta
from itertools import combinations
from collections import Counter

import numpy as np
import pandas as pd

# Ensure imports work from code/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from manipulation_forensic import (
    load_trades, EXCHANGE_MAP, SWEEP_CONDITIONS, COMPLEX_CONDITIONS
)

_SCRIPT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = _SCRIPT_DIR.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Standard lit exchange codes (original set when baselines were generated).
# Codes 42, 43, 60, 65, 69, 73 are dark/COB venues added to EXCHANGE_MAP
# for labeling but must NOT be treated as lit for dark-routing detection.
KNOWN_LIT_CODES = {
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
    16, 17, 18, 19, 24, 30, 31, 46, 47, 48, 140,
}
DARK_VENUE_LABEL = "DARK/COB"


def _exchange_name(code: int) -> str:
    return EXCHANGE_MAP.get(code, f"UNK_{code}")


def _prep_trades(symbol: str, date_str: str, spot_price: float = None) -> pd.DataFrame:
    """Load and enrich trades with DTE, OTM%, and capital calculations."""
    df = load_trades(symbol, date_str)
    if df.empty:
        return df
    
    # Parse expiration and calculate DTE
    df["exp_dt"] = pd.to_datetime(df["expiration"])
    trade_date = pd.Timestamp(date_str)
    df["dte"] = (df["exp_dt"] - trade_date).dt.days
    
    # Calculate capital spent and OTM percentage
    df["capital"] = df["size"] * df["price"] * 100  # dollar value
    if spot_price:
        df["otm_pct"] = np.where(
            df["right"] == "C",
            (df["strike"] - spot_price) / spot_price,
            (spot_price - df["strike"]) / spot_price
        )
    else:
        df["otm_pct"] = np.nan
    
    df["exch_name"] = df["exchange"].map(_exchange_name)
    df["is_dark"] = ~df["exchange"].isin(KNOWN_LIT_CODES)
    
    return df


# ═══════════════════════════════════════════════════════════════════════════
# TEST G: TAIL-BANGING DETECTOR
# ═══════════════════════════════════════════════════════════════════════════

def tail_banging(symbol: str, date_str: str, spot_price: float,
                 min_otm_pct: float = 0.50, min_capital: float = 50_000,
                 max_dte: int = 1) -> dict:
    """
    Detect deep OTM, near-expiry block trades that burn capital to warp the IV surface.
    
    These are economically irrational: paying large premiums for options virtually
    guaranteed to expire worthless. The only rational motive is to force the SIP tape
    to print extreme IV at the tail, warping the entire volatility surface and 
    amplifying Vanna on warehoused LEAPS.
    
    Args:
        spot_price: Approximate stock price on the trade date
        min_otm_pct: Minimum out-of-the-money percentage (0.50 = 50% OTM)
        min_capital: Minimum capital spent per trade to flag ($)
        max_dte: Maximum DTE to consider (1 = expiring tomorrow or today)
    """
    df = _prep_trades(symbol, date_str, spot_price)
    if df.empty:
        return {"error": f"No data for {date_str}"}
    
    # Filter: calls, near-expiry, deep OTM
    mask = (
        (df["right"] == "C") &
        (df["dte"] <= max_dte) &
        (df["otm_pct"] >= min_otm_pct) &
        (df["capital"] >= min_capital)
    )
    tail_trades = df[mask].sort_values("capital", ascending=False).copy()
    
    total_call_vol = int(df[df["right"] == "C"]["size"].sum())
    tail_vol = int(tail_trades["size"].sum()) if not tail_trades.empty else 0
    tail_capital = float(tail_trades["capital"].sum()) if not tail_trades.empty else 0.0
    
    # Group by strike to find concentrated tail-banging
    strike_summary = {}
    if not tail_trades.empty:
        for strike, grp in tail_trades.groupby("strike"):
            strike_summary[str(strike)] = {
                "trades": len(grp),
                "volume": int(grp["size"].sum()),
                "capital_spent": float(grp["capital"].sum()),
                "price_range": [float(grp["price"].min()), float(grp["price"].max())],
                "exchanges": list(grp["exch_name"].unique()),
                "time_range": [str(grp["ts"].min()), str(grp["ts"].max())],
            }
    
    top_trades = []
    for _, row in tail_trades.head(10).iterrows():
        top_trades.append({
            "ts": str(row["ts"]),
            "size": int(row["size"]),
            "strike": float(row["strike"]),
            "price": float(row["price"]),
            "capital": float(row["capital"]),
            "otm_pct": f"{row['otm_pct']:.1%}",
            "dte": int(row["dte"]),
            "exchange": row["exch_name"],
            "condition": int(row["condition"]),
        })
    
    verdict = "TAIL-BANGING DETECTED" if tail_capital > 500_000 else (
              "TAIL-BANGING PRESENT" if tail_capital > 100_000 else
              "MINIMAL TAIL ACTIVITY")
    
    result = {
        "test": "G_tail_banging",
        "date": date_str,
        "spot_price": spot_price,
        "total_call_volume": total_call_vol,
        "tail_trades_count": len(tail_trades),
        "tail_volume": tail_vol,
        "tail_capital_burned": tail_capital,
        "pct_of_call_volume": f"{tail_vol / total_call_vol * 100:.2f}%" if total_call_vol else "N/A",
        "strike_concentration": strike_summary,
        "top_trades": top_trades,
        "verdict": verdict,
    }
    
    # Print results
    print(f"\n{'=' * 70}")
    print(f"  TEST G — TAIL-BANGING: {symbol} on {date_str}")
    print(f"  Spot ≈ ${spot_price:.2f} | OTM threshold ≥ {min_otm_pct:.0%}")
    print(f"{'=' * 70}")
    print(f"\n  Total call volume:     {total_call_vol:,}")
    print(f"  Deep OTM tail trades:  {len(tail_trades)} trades, {tail_vol:,} lots")
    print(f"  Capital burned:        ${tail_capital:,.2f}")
    print(f"  % of call volume:      {result['pct_of_call_volume']}")
    
    if strike_summary:
        print(f"\n  Strike concentration:")
        for strike, info in sorted(strike_summary.items(), key=lambda x: x[1]["capital_spent"], reverse=True):
            print(f"    ${strike}: {info['trades']} trades, {info['volume']:,} lots, "
                  f"${info['capital_spent']:,.0f} burned | Exchanges: {', '.join(info['exchanges'])}")
    
    if top_trades:
        print(f"\n  Top tail trades:")
        for t in top_trades[:5]:
            print(f"    {t['ts']}  {t['size']} lots  ${t['strike']}C  @${t['price']}  "
                  f"${t['capital']:,.0f}  {t['exchange']}  OTM={t['otm_pct']}")
    
    print(f"\n  VERDICT: {verdict}")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# TEST H: WASH/CROSS TRADE DETECTOR
# ═══════════════════════════════════════════════════════════════════════════

def wash_cross_detector(symbol: str, date_str: str, 
                        time_window_sec: int = 30,
                        min_size: int = 100) -> dict:
    """
    Detect potential wash trades / pre-arranged crosses.
    
    Wash trades are identified by: identical lot size, identical price,
    identical strike, within a tight time window. In a volatile market,
    pinning the exact same price on sequential block trades implies
    pre-arrangement, not organic discovery.
    """
    df = _prep_trades(symbol, date_str)
    if df.empty:
        return {"error": f"No data for {date_str}"}
    
    # Focus on block-size trades
    blocks = df[df["size"] >= min_size].sort_values("ts").copy()
    
    wash_pairs = []
    # Compare each trade with the next N trades within the time window
    for i in range(len(blocks)):
        curr = blocks.iloc[i]
        for j in range(i + 1, min(i + 20, len(blocks))):
            other = blocks.iloc[j]
            time_diff = (other["ts"] - curr["ts"]).total_seconds()
            
            if time_diff > time_window_sec:
                break  # Past the window
            
            if (curr["size"] == other["size"] and
                curr["price"] == other["price"] and
                curr["strike"] == other["strike"] and
                curr["right"] == other["right"]):
                
                wash_pairs.append({
                    "ts_1": str(curr["ts"]),
                    "ts_2": str(other["ts"]),
                    "time_gap_sec": round(time_diff, 3),
                    "size": int(curr["size"]),
                    "price": float(curr["price"]),
                    "strike": float(curr["strike"]),
                    "right": curr["right"],
                    "capital_each": float(curr["size"] * curr["price"] * 100),
                    "exchange_1": _exchange_name(int(curr["exchange"])),
                    "exchange_2": _exchange_name(int(other["exchange"])),
                    "condition_1": int(curr["condition"]),
                    "condition_2": int(other["condition"]),
                    "same_exchange": curr["exchange"] == other["exchange"],
                    "dte": int(curr["dte"]) if ("dte" in curr.index and pd.notna(curr["dte"])) else None,
                })
    
    total_wash_capital = sum(p["capital_each"] * 2 for p in wash_pairs)
    
    # Sub-second pairs are especially suspicious
    sub_second = [p for p in wash_pairs if p["time_gap_sec"] < 1.0]
    
    verdict = ("WASH TRADES DETECTED — HIGH CONFIDENCE" if len(wash_pairs) >= 5 else
               "SUSPICIOUS PAIRS FOUND" if wash_pairs else
               "NO WASH PATTERNS")
    
    result = {
        "test": "H_wash_cross",
        "date": date_str,
        "total_block_trades": len(blocks),
        "wash_pairs_found": len(wash_pairs),
        "sub_second_pairs": len(sub_second),
        "total_wash_capital": total_wash_capital,
        "pairs": wash_pairs[:20],  # Cap output
        "verdict": verdict,
    }
    
    print(f"\n{'=' * 70}")
    print(f"  TEST H — WASH/CROSS TRADES: {symbol} on {date_str}")
    print(f"  Min block size: {min_size} | Time window: {time_window_sec}s")
    print(f"{'=' * 70}")
    print(f"\n  Block trades analyzed: {len(blocks):,}")
    print(f"  Wash pairs found:     {len(wash_pairs)}")
    print(f"  Sub-second pairs:     {len(sub_second)} (highest suspicion)")
    print(f"  Total wash capital:   ${total_wash_capital:,.2f}")
    
    if wash_pairs:
        print(f"\n  Wash/Cross pairs:")
        for p in wash_pairs[:10]:
            gap_flag = " ⚠️ SUB-SECOND" if p["time_gap_sec"] < 1.0 else ""
            cross_flag = " 🔀 DIFF VENUE" if not p["same_exchange"] else ""
            print(f"    {p['size']} lots  ${p['strike']}{p['right']}  @${p['price']}  "
                  f"Δt={p['time_gap_sec']:.3f}s  ${p['capital_each']:,.0f}ea  "
                  f"{p['exchange_1']}→{p['exchange_2']}{gap_flag}{cross_flag}")
    
    print(f"\n  VERDICT: {verdict}")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# TEST I: ALGORITHMIC STEPPING DETECTOR
# ═══════════════════════════════════════════════════════════════════════════

def algo_stepping(symbol: str, date_str: str, spot_price: float = None,
                  min_sequence_len: int = 3, max_step: int = 5,
                  min_size: int = 100) -> dict:
    """
    Detect algorithmic stepping patterns: sequential lot sizes (N, N-1, N-2...)
    across deep OTM strikes on obscure exchanges.
    
    A TWAP/VWAP algorithm methodically pinging strikes to keep the MM's
    volatility curve propped up manifests as stepped lot sizes.
    """
    df = _prep_trades(symbol, date_str, spot_price)
    if df.empty:
        return {"error": f"No data for {date_str}"}
    
    # Focus on block trades, sorted by time
    blocks = df[df["size"] >= min_size].sort_values("ts").copy()
    
    # Look for sequences of trades where sizes step by 1
    stepping_sequences = []
    
    sizes = blocks["size"].values
    timestamps = blocks["ts"].values
    exchanges = blocks["exchange"].values
    strikes = blocks["strike"].values
    
    i = 0
    while i < len(sizes) - min_sequence_len + 1:
        # Try to build a stepping sequence from position i
        seq = [i]
        for j in range(i + 1, min(i + 15, len(sizes))):
            step = abs(int(sizes[seq[-1]]) - int(sizes[j]))
            if 1 <= step <= max_step:
                seq.append(j)
        
        if len(seq) >= min_sequence_len:
            seq_trades = []
            for idx in seq:
                row = blocks.iloc[idx]
                seq_trades.append({
                    "ts": str(row["ts"]),
                    "size": int(row["size"]),
                    "strike": float(row["strike"]),
                    "price": float(row["price"]),
                    "exchange": _exchange_name(int(row["exchange"])),
                    "condition": int(row["condition"]),
                })
            
            # Check if same exchange dominates
            seq_exchanges = [t["exchange"] for t in seq_trades]
            dominant_exch = Counter(seq_exchanges).most_common(1)[0]
            
            stepping_sequences.append({
                "length": len(seq),
                "sizes": [int(sizes[idx]) for idx in seq],
                "dominant_exchange": dominant_exch[0],
                "exchange_concentration": dominant_exch[1] / len(seq),
                "trades": seq_trades,
                "time_span_sec": (pd.Timestamp(seq_trades[-1]["ts"]) - 
                                  pd.Timestamp(seq_trades[0]["ts"])).total_seconds(),
            })
            i = seq[-1] + 1  # Skip past sequence
        else:
            i += 1
    
    # Filter to sequences on dark/UNK venues
    dark_sequences = [s for s in stepping_sequences 
                      if "UNK" in s["dominant_exchange"]]
    
    verdict = ("ALGORITHMIC STEPPING DETECTED" if len(stepping_sequences) >= 3 else
               "STEPPING PATTERNS FOUND" if stepping_sequences else
               "NO STEPPING DETECTED")
    
    result = {
        "test": "I_algo_stepping",
        "date": date_str,
        "total_sequences": len(stepping_sequences),
        "dark_venue_sequences": len(dark_sequences),
        "sequences": stepping_sequences[:10],
        "verdict": verdict,
    }
    
    print(f"\n{'=' * 70}")
    print(f"  TEST I — ALGORITHMIC STEPPING: {symbol} on {date_str}")
    print(f"  Min sequence length: {min_sequence_len} | Max step: {max_step}")
    print(f"{'=' * 70}")
    print(f"\n  Stepping sequences found: {len(stepping_sequences)}")
    print(f"  On dark/UNK venues:       {len(dark_sequences)}")
    
    for seq in stepping_sequences[:5]:
        sizes_str = " → ".join(str(s) for s in seq["sizes"])
        print(f"\n    [{seq['length']} trades] sizes: {sizes_str}")
        print(f"    Venue: {seq['dominant_exchange']} ({seq['exchange_concentration']:.0%}) | "
              f"Span: {seq['time_span_sec']:.1f}s")
        for t in seq["trades"][:5]:
            print(f"      {t['ts']}  {t['size']} lots  ${t['strike']}  @${t['price']}  {t['exchange']}")
    
    print(f"\n  VERDICT: {verdict}")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# TEST J: COMPLEX ORDER BOOK (COB) ROUTING
# ═══════════════════════════════════════════════════════════════════════════

def cob_routing(symbol: str, date_str: str, 
                min_legs: int = 2) -> dict:
    """
    Detect multi-leg complex orders executed simultaneously on dark venues.
    
    OPRA condition 130 = Spread, 129 = Multi-leg, 95 = Spread.
    Trades at the EXACT same millisecond, same exchange, different strikes
    = Complex Order Book fills. Retail does not route to COBs.
    """
    df = _prep_trades(symbol, date_str)
    if df.empty:
        return {"error": f"No data for {date_str}"}
    
    # Filter to complex/spread conditions
    complex_mask = df["condition"].isin(COMPLEX_CONDITIONS)
    complex_df = df[complex_mask].copy()
    
    all_trades = len(df)
    complex_trades = len(complex_df)
    complex_volume = int(complex_df["size"].sum()) if not complex_df.empty else 0
    
    # Group by exact timestamp + exchange to find simultaneous multi-leg fills
    cob_clusters = []
    if not complex_df.empty:
        for (ts, exch), grp in complex_df.groupby(["ts", "exchange"]):
            if len(grp) >= min_legs:
                strikes = sorted(grp["strike"].unique().tolist())
                cob_clusters.append({
                    "ts": str(ts),
                    "exchange": _exchange_name(int(exch)),
                    "exchange_code": int(exch),
                    "legs": len(grp),
                    "unique_strikes": len(strikes),
                    "strikes": strikes[:6],
                    "total_volume": int(grp["size"].sum()),
                    "capital": float((grp["size"] * grp["price"] * 100).sum()),
                    "conditions": sorted(grp["condition"].unique().tolist()),
                    "sizes": sorted(grp["size"].unique().tolist()),
                    "is_dark": int(exch) not in KNOWN_LIT_CODES,
                })
    
    # Sort by volume
    cob_clusters.sort(key=lambda x: x["total_volume"], reverse=True)
    
    dark_clusters = [c for c in cob_clusters if c["is_dark"]]
    total_cob_volume = sum(c["total_volume"] for c in cob_clusters)
    dark_cob_volume = sum(c["total_volume"] for c in dark_clusters)
    
    # Exchange breakdown for COB routing
    exch_breakdown = {}
    for c in cob_clusters:
        name = c["exchange"]
        if name not in exch_breakdown:
            exch_breakdown[name] = {"clusters": 0, "volume": 0, "capital": 0.0}
        exch_breakdown[name]["clusters"] += 1
        exch_breakdown[name]["volume"] += c["total_volume"]
        exch_breakdown[name]["capital"] += c["capital"]
    
    verdict = ("COB ROUTING — INSTITUTIONAL DARK POOL" if dark_cob_volume > 10000 else
               "COB ROUTING PRESENT" if cob_clusters else
               "NO COB ROUTING DETECTED")
    
    result = {
        "test": "J_cob_routing",
        "date": date_str,
        "total_trades": all_trades,
        "complex_trades": complex_trades,
        "complex_volume": complex_volume,
        "cob_clusters": len(cob_clusters),
        "dark_clusters": len(dark_clusters),
        "total_cob_volume": total_cob_volume,
        "dark_cob_volume": dark_cob_volume,
        "exchange_breakdown": exch_breakdown,
        "top_clusters": cob_clusters[:15],
        "verdict": verdict,
    }
    
    print(f"\n{'=' * 70}")
    print(f"  TEST J — COMPLEX ORDER BOOK ROUTING: {symbol} on {date_str}")
    print(f"{'=' * 70}")
    print(f"\n  Total trades:       {all_trades:,}")
    print(f"  Complex/spread:     {complex_trades:,} trades ({complex_volume:,} lots)")
    print(f"  COB clusters:       {len(cob_clusters)} (same-ms, same-exchange, multi-strike)")
    print(f"  Dark venue COBs:    {len(dark_clusters)} clusters, {dark_cob_volume:,} lots")
    
    if exch_breakdown:
        print(f"\n  COB Exchange breakdown:")
        for name, info in sorted(exch_breakdown.items(), key=lambda x: x[1]["volume"], reverse=True):
            dark_flag = " ← DARK" if "UNK" in name else ""
            print(f"    {name}: {info['clusters']} clusters, {info['volume']:,} lots, "
                  f"${info['capital']:,.0f}{dark_flag}")
    
    if cob_clusters:
        print(f"\n  Top COB clusters:")
        for c in cob_clusters[:8]:
            dark_flag = " ⚫ DARK" if c["is_dark"] else ""
            strikes_str = ", ".join(f"${s}" for s in c["strikes"])
            print(f"    {c['ts']}  {c['legs']} legs  {c['total_volume']:,} lots  "
                  f"${c['capital']:,.0f}  {c['exchange']}  [{strikes_str}]{dark_flag}")
    
    print(f"\n  VERDICT: {verdict}")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# TEST K: DARK VENUE CONCENTRATION ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

def dark_venue_analysis(symbol: str, dates: list) -> dict:
    """
    Cross-date analysis of UNK/dark venue routing.
    
    Standard lit exchanges = OPRA codes 1-19, 24, 30, 31.
    Codes in 40s/60s = Complex Order Books, Price Improvement Auctions,
    or maker-taker inverted venues. Retail does not access these.
    """
    date_results = []
    all_exch_volume = Counter()
    dark_exch_volume = Counter()
    
    for date_str in dates:
        df = _prep_trades(symbol, date_str)
        if df.empty:
            continue
        
        total_vol = int(df["size"].sum())
        
        # Exchange breakdown
        exch_groups = df.groupby("exchange")["size"].sum()
        lit_vol = 0
        dark_vol = 0
        
        for exch_code, vol in exch_groups.items():
            name = _exchange_name(int(exch_code))
            all_exch_volume[name] += int(vol)
            
            if int(exch_code) in KNOWN_LIT_CODES:
                lit_vol += int(vol)
            else:
                dark_vol += int(vol)
                dark_exch_volume[name] += int(vol)
        
        # Condition breakdown for dark venue trades
        dark_trades = df[~df["exchange"].isin(KNOWN_LIT_CODES)]
        cond_breakdown = {}
        if not dark_trades.empty:
            for cond, grp in dark_trades.groupby("condition"):
                cond_name = {18: "Regular", 95: "Spread", 125: "ISO/ISS",
                            129: "Multi-leg", 130: "Spread", 131: "Straddle",
                            134: "Customer ISO", 138: "Buyer/Seller ISS"
                            }.get(int(cond), f"Cond_{cond}")
                cond_breakdown[cond_name] = int(grp["size"].sum())
        
        date_results.append({
            "date": date_str,
            "total_volume": total_vol,
            "lit_volume": lit_vol,
            "dark_volume": dark_vol,
            "dark_pct": f"{dark_vol / total_vol * 100:.1f}%" if total_vol else "N/A",
            "dark_condition_breakdown": cond_breakdown,
        })
    
    total_across = sum(d["total_volume"] for d in date_results)
    dark_across = sum(d["dark_volume"] for d in date_results)
    
    verdict = ("INSTITUTIONAL DARK ROUTING — HIGH CONCENTRATION" if dark_across / max(total_across, 1) > 0.10 else
               "DARK ROUTING PRESENT" if dark_across > 0 else
               "NO DARK ROUTING")
    
    result = {
        "test": "K_dark_venue",
        "symbol": symbol,
        "dates": dates,
        "date_results": date_results,
        "dark_exchange_totals": dict(dark_exch_volume.most_common()),
        "all_exchange_totals": dict(all_exch_volume.most_common(20)),
        "total_volume": total_across,
        "total_dark_volume": dark_across,
        "dark_pct": f"{dark_across / total_across * 100:.1f}%" if total_across else "N/A",
        "verdict": verdict,
    }
    
    print(f"\n{'=' * 70}")
    print(f"  TEST K — DARK VENUE CONCENTRATION: {symbol}")
    print(f"  Dates: {', '.join(dates)}")
    print(f"{'=' * 70}")
    print(f"\n  Total volume:  {total_across:,}")
    print(f"  Dark volume:   {dark_across:,} ({result['dark_pct']})")
    
    print(f"\n  Per-date breakdown:")
    for d in date_results:
        print(f"    {d['date']}: {d['total_volume']:,} total, "
              f"{d['dark_volume']:,} dark ({d['dark_pct']})")
        if d["dark_condition_breakdown"]:
            conds = ", ".join(f"{k}: {v:,}" for k, v in 
                            sorted(d["dark_condition_breakdown"].items(), 
                                   key=lambda x: x[1], reverse=True)[:5])
            print(f"             Dark conditions: {conds}")
    
    print(f"\n  Dark exchange totals:")
    for exch, vol in dark_exch_volume.most_common():
        print(f"    {exch}: {vol:,} lots")
    
    print(f"\n  VERDICT: {verdict}")
    return result


# ═══════════════════════════════════════════════════════════════════════════
# RUNNER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def run_jan_2021(symbol="GME"):
    """Run the V4 Shadow Hunter battery for Jan 2021."""
    results = {"event": "Jan 2021 Squeeze — V4 Shadow Hunter", "symbol": symbol, "tests": {}}
    
    # Spot prices (approximate close prices)
    spots = {
        "20210122": 65.01, "20210125": 76.79, "20210126": 147.98,
        "20210127": 347.51, "20210128": 193.60, "20210129": 325.00,
    }
    dates = list(spots.keys())
    
    # Test G: Tail-Banging (focus on Jan 27-29 when prices were extreme)
    for date_str in ["20210127", "20210128", "20210129"]:
        key = f"tail_banging_{date_str}"
        results["tests"][key] = tail_banging(symbol, date_str, spots[date_str])
    
    # Test H: Wash/Cross Trades (all dates)
    for date_str in ["20210126", "20210127", "20210128", "20210129"]:
        key = f"wash_cross_{date_str}"
        results["tests"][key] = wash_cross_detector(symbol, date_str)
    
    # Test I: Algorithmic Stepping (Jan 28-29)
    for date_str in ["20210128", "20210129"]:
        key = f"stepping_{date_str}"
        results["tests"][key] = algo_stepping(symbol, date_str, spots[date_str])
    
    # Test J: COB Routing (all dates)
    for date_str in dates:
        key = f"cob_routing_{date_str}"
        results["tests"][key] = cob_routing(symbol, date_str)
    
    # Test K: Dark Venue Analysis
    results["tests"]["dark_venue"] = dark_venue_analysis(symbol, dates)
    
    return results


def run_jun_2024(symbol="GME"):
    """Run the V4 Shadow Hunter battery for Jun 2024."""
    results = {"event": "Jun 2024 Squeeze — V4 Shadow Hunter", "symbol": symbol, "tests": {}}
    
    # Spot prices (approximate)
    spots = {
        "20240604": 24.23, "20240607": 46.55, "20240610": 30.14,
        "20240611": 26.89, "20240617": 28.44, "20240618": 28.22,
        "20240620": 23.74, "20240621": 28.27,
    }
    dates = list(spots.keys())
    
    # Test G: Tail-Banging (focus on Jun 4 & 7 — key days)
    for date_str in ["20240604", "20240607"]:
        key = f"tail_banging_{date_str}"
        results["tests"][key] = tail_banging(symbol, date_str, spots[date_str])
    
    # Test H: Wash/Cross Trades
    for date_str in dates:
        key = f"wash_cross_{date_str}"
        results["tests"][key] = wash_cross_detector(symbol, date_str)
    
    # Test I: Algorithmic Stepping
    for date_str in ["20240604", "20240607"]:
        key = f"stepping_{date_str}"
        results["tests"][key] = algo_stepping(symbol, date_str, spots[date_str])
    
    # Test J: COB Routing
    for date_str in dates:
        key = f"cob_routing_{date_str}"
        results["tests"][key] = cob_routing(symbol, date_str)
    
    # Test K: Dark Venue Analysis
    results["tests"]["dark_venue"] = dark_venue_analysis(symbol, dates)
    
    return results


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="V4 Shadow Algorithm Hunter")
    parser.add_argument("--event", choices=["jan2021", "jun2024", "both"], default="both")
    parser.add_argument("--ticker", default="GME")
    args = parser.parse_args()
    
    results = {}
    
    if args.event in ("jan2021", "both"):
        r = run_jan_2021(args.ticker)
        results["jan_2021"] = r
    
    if args.event in ("jun2024", "both"):
        r = run_jun_2024(args.ticker)
        results["jun_2024"] = r
    
    # Save results
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = RESULTS_DIR / f"shadow_hunter_{args.ticker}_{ts}.json"
    
    # Make JSON-serializable
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n  Results saved to: {Path(out_file).name}")
