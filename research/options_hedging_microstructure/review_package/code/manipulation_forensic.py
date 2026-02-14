#!/usr/bin/env python3
"""
manipulation_forensic.py — Adversarial Manipulation Proof Battery

Red Team Tests to distinguish ENGINEERED squeeze from ORGANIC retail herding:
  Test A: Whale Detector       — Trade size stratification (block vs retail)
  Test B: Ignition Sequence     — LEAPS powder keg vs Weekly match timeline
  Test C: Constructor Fingerprint — Cross-venue sweep detection (CVS)
  
Uses tick-level options trade data from ThetaData parquet files.
"""
import sys, os, json, argparse, time
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from scipy import stats

# ── Paths (resolved relative to script location) ──────────────────────
_SCRIPT_DIR  = Path(__file__).resolve().parent
_DATA_ROOT   = _SCRIPT_DIR.parents[2] / "data" / "raw"
TRADES_ROOT  = _DATA_ROOT / "thetadata" / "trades"
OI_CACHE_DIR = _DATA_ROOT / "thetadata" / "open_interest"
RESULTS_DIR  = _SCRIPT_DIR.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ThetaData exchange codes (from their documentation + OPRA de-masking)
EXCHANGE_MAP = {
    0: "COMPOSITE", 1: "BATS", 2: "BX", 3: "MIAX_PEARL",
    4: "C2", 5: "NSDQ_BX_OPT", 6: "CBOE", 7: "ISE",
    8: "PSE", 9: "NYSE_AMEX", 10: "PHLX", 11: "NSDQ_ISE_GEMINI",
    12: "BOX", 13: "MIAX", 14: "UNKNOWN", 15: "NSDQ_ISE_MERCURY",
    16: "EDGX", 17: "NSDQ_MRCY", 18: "MEMX", 19: "EMLD",
    24: "MPRL", 30: "ARCX", 31: "OPRA", 46: "MULTI_EXCHANGE",
    47: "ISE2", 48: "C1BOX", 140: "COMPOSITE_DELAYED",
    # De-masked dark venues (V5 — OPRA proprietary + Cboe feed mappings)
    22: "MIAX_PEARL_EQUITIES",    # MIAX Pearl Equities options
    42: "C2_COB",                  # Cboe C2 Complex Order Book
    43: "EDGX_COB",                # Cboe EDGX Complex Order Book
    60: "BZX_OPTIONS",             # Cboe BZX Options (maker-taker inverted, HFT-favored)
    65: "EDGX_OPTIONS",            # Cboe EDGX Options (specialized complex routing)
    69: "PHLX_FLOOR",              # Nasdaq PHLX (floor-based cross trades)
    73: "MIAX_EMERALD",            # MIAX Emerald Options
}

# OPRA condition codes that indicate sweeps/complex
# 18 = Regular, 95 = Spread, 125 = Intermarket Sweep (ISS!), 
# 129 = Multi-leg, 130 = Spread, 131 = Straddle/combo
# 134 = Customer ISO (Intermarket Sweep Order), 135 = Customer w/ size
# 138 = Buyer/Seller ISS
SWEEP_CONDITIONS = {125, 134, 138}  # ISO/ISS conditions
COMPLEX_CONDITIONS = {95, 129, 130, 131}  # Multi-leg / spread


def load_trades(symbol: str, date_str: str) -> pd.DataFrame:
    """Load options trades for a symbol on a given date from parquet.
    Normalizes schema differences:
      - 'expiry' → 'expiration'
      - right: 'CALL'/'PUT' → 'C'/'P'
    """
    date_dir = TRADES_ROOT / f"root={symbol}" / f"date={date_str}"
    if not date_dir.exists():
        return pd.DataFrame()
    
    files = list(date_dir.glob("*.parquet"))
    if not files:
        return pd.DataFrame()
    
    dfs = [pd.read_parquet(f) for f in files]
    df = pd.concat(dfs, ignore_index=True) if len(dfs) > 1 else dfs[0]
    
    # Normalize column names (old='expiry', new='expiration')
    if "expiry" in df.columns and "expiration" not in df.columns:
        df = df.rename(columns={"expiry": "expiration"})
    
    # Normalize right values (old='CALL'/'PUT', new='C'/'P')
    if df["right"].dtype == object:
        right_map = {"CALL": "C", "PUT": "P"}
        df["right"] = df["right"].map(lambda x: right_map.get(x, x))
    
    # Parse timestamp (mixed formats: some have ms, some don't)
    df["ts"] = pd.to_datetime(df["timestamp"], format="ISO8601")
    return df


def load_trades_range(symbol: str, start: str, end: str, 
                      progress: bool = True) -> pd.DataFrame:
    """Load trades for a date range. Returns combined DataFrame."""
    start_dt = pd.Timestamp(start)
    end_dt = pd.Timestamp(end)
    dates = pd.bdate_range(start_dt, end_dt)
    
    all_frames = []
    for i, d in enumerate(dates):
        date_str = d.strftime("%Y%m%d")
        df = load_trades(symbol, date_str)
        if df is not None and len(df) > 0:
            df["trade_date"] = d
            all_frames.append(df)
        if progress and (i + 1) % 20 == 0:
            print(f"    {i+1}/{len(dates)} dates loaded")
    
    if progress:
        print(f"    {len(dates)}/{len(dates)} done, {len(all_frames)} with data")
    
    if not all_frames:
        return pd.DataFrame()
    return pd.concat(all_frames, ignore_index=True)


# ═══════════════════════════════════════════════════════════════════════
# TEST A: WHALE DETECTOR — Trade Size Stratification
# ═══════════════════════════════════════════════════════════════════════

def whale_detector(symbol: str, dates: list, target_exp: str = None,
                   target_right: str = "CALL") -> dict:
    """
    For each specified date, stratify options trade volume by trade size.
    
    Size buckets:
      - Retail:  1-3 contracts
      - Small:   4-9 contracts
      - Medium:  10-49 contracts  
      - Large:   50-99 contracts
      - Block:   100-499 contracts
      - Whale:   500+ contracts
    
    If target_exp is set, filter to contracts targeting that expiration.
    """
    print(f"\n{'='*70}")
    print(f"  WHALE DETECTOR: {symbol}")
    print(f"  Dates: {', '.join(dates)}")
    if target_exp:
        print(f"  Target expiration: {target_exp}")
    print(f"{'='*70}")
    
    buckets = [
        ("Retail (1-3)", 1, 3),
        ("Small (4-9)", 4, 9),
        ("Medium (10-49)", 10, 49),
        ("Large (50-99)", 50, 99),
        ("Block (100-499)", 100, 499),
        ("Whale (500+)", 500, 999999),
    ]
    
    daily_results = []
    
    for date_str in dates:
        df = load_trades(symbol, date_str)
        if df.empty:
            print(f"  {date_str}: No data")
            continue
        
        # Filter to target right (calls only for squeeze analysis)
        if target_right:
            df = df[df["right"] == target_right.upper()[0]].copy()
        
        # Filter to target expiration if specified
        if target_exp:
            target_dt = pd.Timestamp(target_exp)
            df["exp_dt"] = pd.to_datetime(df["expiration"])
            df = df[df["exp_dt"] == target_dt].copy()
        
        if df.empty:
            print(f"  {date_str}: No matching trades")
            continue
        
        total_contracts = int(df["size"].sum())
        total_trades = len(df)
        
        bucket_data = []
        for label, lo, hi in buckets:
            mask = (df["size"] >= lo) & (df["size"] <= hi)
            n_trades = int(mask.sum())
            vol = int(df.loc[mask, "size"].sum())
            pct_vol = vol / total_contracts * 100 if total_contracts > 0 else 0
            pct_trades = n_trades / total_trades * 100 if total_trades > 0 else 0
            bucket_data.append({
                "bucket": label,
                "n_trades": n_trades,
                "volume": vol,
                "pct_volume": round(pct_vol, 1),
                "pct_trades": round(pct_trades, 1),
            })
        
        # Compute the Whale Concentration Ratio
        # What fraction of VOLUME came from trades >= 100 contracts?
        block_whale_vol = sum(b["volume"] for b in bucket_data 
                            if "Block" in b["bucket"] or "Whale" in b["bucket"])
        whale_ratio = block_whale_vol / total_contracts if total_contracts > 0 else 0
        
        # Top 10 largest individual trades
        top_trades = df.nlargest(10, "size")[["timestamp", "size", "strike", 
                                               "price", "exchange", "condition"]].copy()
        top_trades["exchange_name"] = top_trades["exchange"].map(
            lambda x: EXCHANGE_MAP.get(x, f"UNK_{x}"))
        top_trades["is_sweep"] = top_trades["condition"].isin(SWEEP_CONDITIONS)
        
        result = {
            "date": date_str,
            "total_contracts": total_contracts,
            "total_trades": total_trades,
            "avg_trade_size": round(total_contracts / total_trades, 1) if total_trades > 0 else 0,
            "whale_ratio": round(whale_ratio, 4),
            "buckets": bucket_data,
            "top_trades": top_trades.to_dict(orient="records"),
        }
        daily_results.append(result)
        
        # Print summary
        print(f"\n  {date_str}: {total_contracts:,} contracts in {total_trades:,} trades "
              f"(avg {result['avg_trade_size']:.1f} lots)")
        print(f"  Whale Ratio (Block+Whale/Total): {whale_ratio:.1%}")
        print(f"  {'Bucket':<20} {'Trades':>8} {'Volume':>10} {'%Vol':>7} {'%Trades':>8}")
        print(f"  {'-'*55}")
        for b in bucket_data:
            print(f"  {b['bucket']:<20} {b['n_trades']:>8,} {b['volume']:>10,} "
                  f"{b['pct_volume']:>6.1f}% {b['pct_trades']:>7.1f}%")
        
        # Print top trades
        print(f"\n  Top 5 Largest Trades:")
        for _, row in top_trades.head(5).iterrows():
            sweep_tag = " ⚡SWEEP" if row["is_sweep"] else ""
            print(f"    {row['timestamp']}  {int(row['size']):>6} lots  "
                  f"${row['strike']:.0f}  @${row['price']:.2f}  "
                  f"{row['exchange_name']}{sweep_tag}")
    
    # Compare to organic baseline (if we have multiple dates)
    if len(daily_results) >= 2:
        whale_ratios = [r["whale_ratio"] for r in daily_results]
        avg_sizes = [r["avg_trade_size"] for r in daily_results]
        print(f"\n  Cross-Date Whale Ratio: "
              f"mean={np.mean(whale_ratios):.1%}, "
              f"max={np.max(whale_ratios):.1%}")
        print(f"  Cross-Date Avg Size:    "
              f"mean={np.mean(avg_sizes):.1f}, "
              f"max={np.max(avg_sizes):.1f}")
    
    # Verdict
    if daily_results:
        max_whale = max(r["whale_ratio"] for r in daily_results)
        max_avg_size = max(r["avg_trade_size"] for r in daily_results)
        if max_whale > 0.30 and max_avg_size > 10:
            verdict = "INSTITUTIONAL (whale blocks dominate volume)"
        elif max_whale > 0.15:
            verdict = "MIXED (significant institutional + retail)"
        else:
            verdict = "RETAIL SWARM (small lots dominate)"
        
        print(f"\n  VERDICT: {verdict}")
    else:
        verdict = "INSUFFICIENT DATA"
    
    return {
        "test": "whale_detector",
        "symbol": symbol,
        "target_exp": target_exp,
        "daily_results": daily_results,
        "verdict": verdict,
    }


# ═══════════════════════════════════════════════════════════════════════
# TEST B: IGNITION SEQUENCE — Powder Keg + Match Timeline
# ═══════════════════════════════════════════════════════════════════════

def ignition_sequence(symbol: str, squeeze_date: str, 
                      lookback_days: int = 270) -> dict:
    """
    Build the "Ignition Sequence" timeline:
    - Track cumulative LEAPS OI (DTE > 180) — the Powder Keg
    - Track daily short-dated volume (DTE < 14) — the Match
    - Identify the transition from stealth accumulation to overt ignition
    
    Uses cached OI snapshots from rogue_wave_forensic.py
    """
    print(f"\n{'='*70}")
    print(f"  IGNITION SEQUENCE: {symbol}")
    print(f"  Squeeze date: {squeeze_date}")
    print(f"{'='*70}")
    
    squeeze_dt = pd.Timestamp(squeeze_date)
    start_dt = squeeze_dt - pd.Timedelta(days=lookback_days)
    
    # Load OI data from cache
    oi_dir = OI_CACHE_DIR / symbol
    if not oi_dir.exists():
        print("  ERROR: No cached OI data. Run rogue_wave_forensic.py first.")
        return {"error": "No OI data"}
    
    dates = pd.bdate_range(start_dt, squeeze_dt)
    
    timeline = []
    for d in dates:
        date_str = d.strftime("%Y%m%d")
        cache_file = oi_dir / f"oi_{date_str}.parquet"
        if not cache_file.exists():
            continue
        
        df = pd.read_parquet(cache_file)
        if df.empty:
            continue
        
        # Normalize right values (OI cache uses CALL/PUT)
        right_map = {"CALL": "C", "PUT": "P"}
        df["right"] = df["right"].map(lambda x: right_map.get(x, x))
        
        # Parse expiration dates
        df["exp_dt"] = pd.to_datetime(df["expiration"])
        df["dte"] = (df["exp_dt"] - d).dt.days
        
        # LEAPS: DTE > 180 (the Powder Keg)
        leaps_mask = df["dte"] > 180
        leaps_call_oi = int(df.loc[leaps_mask & (df["right"] == "C"), "open_interest"].sum())
        leaps_put_oi = int(df.loc[leaps_mask & (df["right"] == "P"), "open_interest"].sum())
        
        # Short-dated: DTE < 14 (the Match)
        short_mask = (df["dte"] >= 0) & (df["dte"] < 14)
        short_call_oi = int(df.loc[short_mask & (df["right"] == "C"), "open_interest"].sum())
        short_put_oi = int(df.loc[short_mask & (df["right"] == "P"), "open_interest"].sum())
        
        # Medium-dated: 14 <= DTE <= 180
        mid_mask = (df["dte"] >= 14) & (df["dte"] <= 180)
        mid_call_oi = int(df.loc[mid_mask & (df["right"] == "C"), "open_interest"].sum())
        
        timeline.append({
            "date": d.strftime("%Y-%m-%d"),
            "dte_to_squeeze": (squeeze_dt - d).days,
            "leaps_call_oi": leaps_call_oi,
            "leaps_put_oi": leaps_put_oi,
            "leaps_total": leaps_call_oi + leaps_put_oi,
            "short_call_oi": short_call_oi,
            "short_put_oi": short_put_oi,
            "short_total": short_call_oi + short_put_oi,
            "mid_call_oi": mid_call_oi,
        })
    
    if not timeline:
        print("  No OI data in range")
        return {"error": "No OI data in range"}
    
    df_tl = pd.DataFrame(timeline)
    
    # Identify the Powder Keg phase: when LEAPS OI grows while short-dated is flat
    # Then the Match: when short-dated volume suddenly spikes
    
    # Split into quiet vs ignition phases using short-dated OI median
    short_median = df_tl["short_call_oi"].median()
    
    # Find the "ignition point" — first day short-dated OI exceeds 3× median
    ignition_mask = df_tl["short_call_oi"] > short_median * 3
    if ignition_mask.any():
        ignition_idx = ignition_mask.idxmax()
        ignition_date = df_tl.loc[ignition_idx, "date"]
        ignition_dte = int(df_tl.loc[ignition_idx, "dte_to_squeeze"])
    else:
        ignition_date = None
        ignition_dte = None
    
    # Powder Keg growth: LEAPS OI change from start to ignition
    leaps_start = int(df_tl.iloc[0]["leaps_call_oi"]) if len(df_tl) > 0 else 0
    leaps_at_ignition = int(df_tl.loc[ignition_idx, "leaps_call_oi"]) if ignition_date else 0
    leaps_at_peak = int(df_tl["leaps_call_oi"].max())
    
    # Short-dated at ignition vs peak
    short_at_ignition = int(df_tl.loc[ignition_idx, "short_call_oi"]) if ignition_date else 0
    short_at_peak = int(df_tl["short_call_oi"].max())
    
    # Print timeline summary (every 20 rows)
    print(f"\n  Timeline ({len(df_tl)} observations):")
    print(f"  {'Date':>12} {'DTE':>5} {'LEAPS Call':>12} {'Short Call':>12} {'Mid Call':>12}")
    print(f"  {'-'*55}")
    
    for i, row in df_tl.iterrows():
        if i % 20 == 0 or i == len(df_tl) - 1 or (ignition_date and row["date"] == ignition_date):
            marker = " ← IGNITION" if (ignition_date and row["date"] == ignition_date) else ""
            print(f"  {row['date']:>12} {row['dte_to_squeeze']:>5} "
                  f"{row['leaps_call_oi']:>12,} {row['short_call_oi']:>12,} "
                  f"{row['mid_call_oi']:>12,}{marker}")
    
    # Compute metrics
    leaps_growth = (leaps_at_ignition - leaps_start) / leaps_start if leaps_start > 0 else 0
    short_spike = short_at_peak / short_median if short_median > 0 else 0
    
    print(f"\n  Ignition Point: {ignition_date} (DTE={ignition_dte})")
    print(f"  LEAPS Call OI:  {leaps_start:>10,} → {leaps_at_ignition:>10,} → {leaps_at_peak:>10,} "
          f"(+{leaps_growth:.0%} to ignition)")
    print(f"  Short Call OI:  median={short_median:,.0f} → ignition={short_at_ignition:,} → "
          f"peak={short_at_peak:,} ({short_spike:.1f}× median)")
    
    # Verdict
    if leaps_growth > 0.5 and ignition_dte and ignition_dte < 30:
        verdict = "POWDER KEG + MATCH (LEAPS loaded, then short-dated ignition)"
    elif leaps_growth > 0.3:
        verdict = "SUSPICIOUS (significant LEAPS accumulation before ignition)"
    else:
        verdict = "ORGANIC (no clear stealth-then-ignite pattern)"
    
    print(f"\n  VERDICT: {verdict}")
    
    return {
        "test": "ignition_sequence",
        "symbol": symbol,
        "squeeze_date": squeeze_date,
        "n_observations": len(df_tl),
        "ignition_date": ignition_date,
        "ignition_dte": ignition_dte,
        "leaps_start": leaps_start,
        "leaps_at_ignition": leaps_at_ignition,
        "leaps_at_peak": leaps_at_peak,
        "leaps_growth_pct": round(leaps_growth * 100, 1),
        "short_median": int(short_median),
        "short_at_ignition": short_at_ignition,
        "short_at_peak": short_at_peak,
        "short_spike_x": round(short_spike, 1),
        "verdict": verdict,
        "timeline": timeline,  # Full timeline for charting
    }


# ═══════════════════════════════════════════════════════════════════════
# TEST C: CONSTRUCTOR FINGERPRINT — Cross-Venue Sweep Detection
# ═══════════════════════════════════════════════════════════════════════

def constructor_fingerprint(symbol: str, dates: list,
                           target_exp: str = None) -> dict:
    """
    Analyze execution routing of OI-building trades:
    - How many distinct exchanges in 1-second windows? (CVS detection)
    - What fraction are ISS/ISO condition codes? (sweep indicator)
    - What is the exchange concentration? (HHI)
    
    Retail → mostly single-exchange (Robinhood → wholesaler → TRF)
    Institutional → multi-exchange sub-second sweeps
    """
    print(f"\n{'='*70}")
    print(f"  CONSTRUCTOR FINGERPRINT: {symbol}")
    print(f"  Dates: {', '.join(dates)}")
    print(f"{'='*70}")
    
    daily_results = []
    
    for date_str in dates:
        df = load_trades(symbol, date_str)
        if df.empty:
            print(f"  {date_str}: No data")
            continue
        
        # Filter to calls (the attacking instrument)
        df = df[df["right"] == "C"].copy()
        
        if target_exp:
            df["exp_dt"] = pd.to_datetime(df["expiration"])
            df = df[df["exp_dt"] == pd.Timestamp(target_exp)].copy()
        
        if df.empty:
            continue
        
        total_trades = len(df)
        total_vol = int(df["size"].sum())
        
        # 1. Sweep Detection: ISO/ISS condition codes
        sweep_mask = df["condition"].isin(SWEEP_CONDITIONS)
        sweep_trades = int(sweep_mask.sum())
        sweep_vol = int(df.loc[sweep_mask, "size"].sum())
        sweep_pct = sweep_vol / total_vol * 100 if total_vol > 0 else 0
        
        # 2. Complex Order Detection
        complex_mask = df["condition"].isin(COMPLEX_CONDITIONS)
        complex_trades = int(complex_mask.sum())
        complex_vol = int(df.loc[complex_mask, "size"].sum())
        
        # 3. Exchange Concentration (HHI)
        exch_vol = df.groupby("exchange")["size"].sum()
        exch_shares = exch_vol / exch_vol.sum()
        hhi = float((exch_shares ** 2).sum())
        n_exchanges = len(exch_vol)
        
        # 4. Cross-Venue Synchronization: 1-second window analysis
        df["ts_second"] = df["ts"].dt.floor("1s")
        
        # For each 1-second window, count unique exchanges
        window_stats = df.groupby("ts_second").agg(
            n_exchanges_in_window=("exchange", "nunique"),
            vol_in_window=("size", "sum"),
            n_trades_in_window=("exchange", "count"),
        )
        
        # CVS events: windows with 3+ exchanges in 1 second
        cvs_mask = window_stats["n_exchanges_in_window"] >= 3
        cvs_windows = int(cvs_mask.sum())
        cvs_volume = int(window_stats.loc[cvs_mask, "vol_in_window"].sum())
        cvs_pct = cvs_volume / total_vol * 100 if total_vol > 0 else 0
        
        # Top exchange distribution
        top_exch = exch_vol.nlargest(5)
        exch_breakdown = []
        for exch_id, vol in top_exch.items():
            exch_breakdown.append({
                "exchange": EXCHANGE_MAP.get(int(exch_id), f"UNK_{exch_id}"),
                "volume": int(vol),
                "pct": round(vol / total_vol * 100, 1),
            })
        
        result = {
            "date": date_str,
            "total_trades": total_trades,
            "total_volume": total_vol,
            "sweep_trades": sweep_trades,
            "sweep_volume": sweep_vol,
            "sweep_pct": round(sweep_pct, 1),
            "complex_trades": complex_trades,
            "complex_volume": int(complex_vol),
            "n_exchanges": n_exchanges,
            "hhi": round(hhi, 4),
            "cvs_windows": cvs_windows,
            "cvs_volume": cvs_volume,
            "cvs_pct": round(cvs_pct, 1),
            "exchange_breakdown": exch_breakdown,
        }
        daily_results.append(result)
        
        print(f"\n  {date_str}: {total_vol:,} contracts across {n_exchanges} exchanges")
        print(f"  Sweep (ISO/ISS):     {sweep_vol:>10,} ({sweep_pct:.1f}% of volume)")
        print(f"  Complex (multi-leg): {int(complex_vol):>10,}")
        print(f"  CVS (3+ exch/sec):   {cvs_volume:>10,} ({cvs_pct:.1f}%) in {cvs_windows} windows")
        print(f"  Exchange HHI:        {hhi:.4f} ({'concentrated' if hhi > 0.25 else 'dispersed'})")
        print(f"  Top exchanges:")
        for e in exch_breakdown:
            print(f"    {e['exchange']:<20} {e['volume']:>10,} ({e['pct']:.1f}%)")
    
    # Verdict
    if daily_results:
        max_sweep_pct = max(r["sweep_pct"] for r in daily_results)
        max_cvs_pct = max(r["cvs_pct"] for r in daily_results)
        avg_hhi = np.mean([r["hhi"] for r in daily_results])
        
        if max_sweep_pct > 20 and max_cvs_pct > 10:
            verdict = "INSTITUTIONAL ALGORITHM (high sweep + CVS activity)"
        elif max_sweep_pct > 10 or max_cvs_pct > 5:
            verdict = "MIXED (some institutional execution patterns)"
        else:
            verdict = "RETAIL-DOMINANT (low sweep/CVS, consistent with internalized orders)"
        
        print(f"\n  VERDICT: {verdict}")
    else:
        verdict = "INSUFFICIENT DATA"
    
    return {
        "test": "constructor_fingerprint",
        "symbol": symbol,
        "target_exp": target_exp,
        "daily_results": daily_results,
        "verdict": verdict,
    }


# ═══════════════════════════════════════════════════════════════════════
# TEST D: PREDATOR MATRIX — 3D Institutional Attack Isolation
# CVS_Window × Size≥100 × ISO/ISS → The Squeeze Architect's Fingerprint
# ═══════════════════════════════════════════════════════════════════════

def predator_matrix(symbol: str, dates: list,
                    target_exp: str = None, min_size: int = 100) -> dict:
    """
    Isolate the 3D intersection of:
      1. Trades in CVS windows (3+ exchanges/second)
      2. Block size (≥100 lots)
      3. ISO/ISS condition codes (intermarket sweep orders)
    
    This triple intersection can only be produced by institutional SOR
    algorithms. Retail traders cannot send 100+ lot ISOs across 3+
    exchanges in 1 second.
    """
    print(f"\n{'='*70}")
    print(f"  PREDATOR MATRIX: {symbol}")
    print(f"  Dates: {', '.join(dates)}")
    print(f"  Min block size: {min_size}")
    print(f"{'='*70}")
    
    daily_results = []
    
    for date_str in dates:
        df = load_trades(symbol, date_str)
        if df.empty:
            continue
        
        # Filter to calls
        df = df[df["right"] == "C"].copy()
        if target_exp:
            df["exp_dt"] = pd.to_datetime(df["expiration"])
            df = df[df["exp_dt"] == pd.Timestamp(target_exp)].copy()
        if df.empty:
            continue
        
        total_vol = int(df["size"].sum())
        
        # Mark each trade's properties
        df["is_sweep"] = df["condition"].isin(SWEEP_CONDITIONS)
        df["is_block"] = df["size"] >= min_size
        
        # CVS windows (3+ exchanges in 1 second)
        df["ts_second"] = df["ts"].dt.floor("1s")
        window_exch = df.groupby("ts_second")["exchange"].nunique()
        cvs_seconds = set(window_exch[window_exch >= 3].index)
        df["in_cvs"] = df["ts_second"].isin(cvs_seconds)
        
        # ── Intersection layers ──
        # Layer 1: CVS only
        cvs_vol = int(df.loc[df["in_cvs"], "size"].sum())
        
        # Layer 2: CVS + Block
        cvs_block = df["in_cvs"] & df["is_block"]
        cvs_block_vol = int(df.loc[cvs_block, "size"].sum())
        cvs_block_trades = int(cvs_block.sum())
        
        # Layer 3: CVS + Block + ISO (THE PREDATOR)
        predator = df["in_cvs"] & df["is_block"] & df["is_sweep"]
        predator_vol = int(df.loc[predator, "size"].sum())
        predator_trades = int(predator.sum())
        
        # Layer 4: ISO Sweeps of any size
        sweep_vol = int(df.loc[df["is_sweep"], "size"].sum())
        
        # Block trades outside CVS (for comparison — legitimate blocks)
        block_no_cvs = df["is_block"] & ~df["in_cvs"]
        block_no_cvs_vol = int(df.loc[block_no_cvs, "size"].sum())
        
        # Top predator trades (for narrative)
        pred_df = df[predator].nlargest(5, "size")
        top_predator = []
        for _, row in pred_df.iterrows():
            top_predator.append({
                "timestamp": str(row["ts"]),
                "size": int(row["size"]),
                "strike": float(row["strike"]),
                "price": float(row["price"]),
                "exchange": EXCHANGE_MAP.get(int(row["exchange"]), f"UNK_{row['exchange']}"),
            })
        
        result = {
            "date": date_str,
            "total_volume": total_vol,
            "cvs_volume": cvs_vol,
            "cvs_block_volume": cvs_block_vol,
            "cvs_block_trades": cvs_block_trades,
            "predator_volume": predator_vol,
            "predator_trades": predator_trades,
            "predator_pct": round(predator_vol / total_vol * 100, 2) if total_vol else 0,
            "sweep_volume": sweep_vol,
            "block_outside_cvs_volume": block_no_cvs_vol,
            "top_predator_trades": top_predator,
        }
        daily_results.append(result)
        
        # Print
        print(f"\n  {date_str}: {total_vol:,} total call volume")
        print(f"  Layer 1 — CVS only:           {cvs_vol:>10,} ({cvs_vol/total_vol*100:.1f}%)")
        print(f"  Layer 2 — CVS + Block≥{min_size}:   {cvs_block_vol:>10,} ({cvs_block_vol/total_vol*100:.1f}%)")
        print(f"  Layer 3 — CVS+Block+ISO:      {predator_vol:>10,} ({predator_vol/total_vol*100:.1f}%) ← PREDATOR")
        print(f"  Blocks outside CVS:           {block_no_cvs_vol:>10,} ({block_no_cvs_vol/total_vol*100:.1f}%)")
        print(f"  Predator trades: {predator_trades}")
        if top_predator:
            print(f"  Top predator trades:")
            for t in top_predator:
                print(f"    {t['timestamp']}  {t['size']:,} lots  ${t['strike']}  @${t['price']:.2f}  {t['exchange']}")
    
    # Summary
    total_pred_vol = sum(r["predator_volume"] for r in daily_results)
    total_all_vol = sum(r["total_volume"] for r in daily_results)
    pred_pct = total_pred_vol / total_all_vol * 100 if total_all_vol else 0
    
    if pred_pct > 5:
        verdict = f"ALGORITHMIC PREDATOR CONFIRMED ({pred_pct:.1f}% of volume is block ISO sweeps in CVS windows)"
    elif pred_pct > 1:
        verdict = f"INSTITUTIONAL PRESENCE ({pred_pct:.1f}%)"
    else:
        verdict = f"MINIMAL PREDATOR SIGNAL ({pred_pct:.1f}%)"
    
    print(f"\n  Cross-date predator volume: {total_pred_vol:,} / {total_all_vol:,} = {pred_pct:.1f}%")
    print(f"  VERDICT: {verdict}")
    
    return {
        "test": "predator_matrix",
        "symbol": symbol,
        "daily_results": daily_results,
        "total_predator_volume": total_pred_vol,
        "total_volume": total_all_vol,
        "predator_pct": round(pred_pct, 2),
        "verdict": verdict,
    }


# ═══════════════════════════════════════════════════════════════════════
# TEST E: LEE-READY AGGRESSOR PROFILE — Tick Test on Sweep Trades
# Prove whether ISO sweeps were BUYING (hitting Ask) or SELLING (hitting Bid)
# ═══════════════════════════════════════════════════════════════════════

def lee_ready_aggressor(symbol: str, dates: list,
                        target_exp: str = None) -> dict:
    """
    Apply the Lee-Ready Tick Test to classify ISO sweep trades:
      - If trade price > previous trade price → AGGRESSOR BUY (hitting the ask)
      - If trade price < previous trade price → AGGRESSOR SELL (hitting the bid)
      - If trade price == previous → use previous classification
    
    Market Makers hedging defensively typically split orders, spread,
    or hit the bid. An ATTACKER sweeps the Ask across multiple exchanges.
    If ISO sweeps are overwhelmingly Aggressor Buys, it proves offensive
    intent (Adversarial Microstructure Exploitation).
    """
    print(f"\n{'='*70}")
    print(f"  LEE-READY AGGRESSOR PROFILE: {symbol}")
    print(f"  Dates: {', '.join(dates)}")
    print(f"{'='*70}")
    
    daily_results = []
    
    for date_str in dates:
        df = load_trades(symbol, date_str)
        if df.empty:
            continue
        
        # Filter to calls
        df = df[df["right"] == "C"].copy()
        if target_exp:
            df["exp_dt"] = pd.to_datetime(df["expiration"])
            df = df[df["exp_dt"] == pd.Timestamp(target_exp)].copy()
        if df.empty:
            continue
        
        # Sort by timestamp for tick test
        df = df.sort_values("ts").reset_index(drop=True)
        total_vol = int(df["size"].sum())
        
        # ── Lee-Ready Tick Test ──
        # For each strike/expiration, compute tick direction independently
        # (comparing across different strikes is meaningless)
        df["tick_dir"] = 0  # +1 = uptick, -1 = downtick
        
        for (strike, exp), grp in df.groupby(["strike", "expiration"]):
            idx = grp.index
            prices = grp["price"].values
            dirs = np.zeros(len(prices), dtype=int)
            
            for i in range(1, len(prices)):
                if prices[i] > prices[i-1]:
                    dirs[i] = 1   # Uptick → Aggressor Buy
                elif prices[i] < prices[i-1]:
                    dirs[i] = -1  # Downtick → Aggressor Sell
                else:
                    dirs[i] = dirs[i-1]  # Zero-tick: inherit previous
            
            df.loc[idx, "tick_dir"] = dirs
        
        # ── Classify sweep trades ──
        sweep_mask = df["condition"].isin(SWEEP_CONDITIONS)
        sweep_df = df[sweep_mask].copy()
        non_sweep_df = df[~sweep_mask].copy()
        
        if len(sweep_df) == 0:
            continue
        
        # Aggressor classification
        sweep_buy_mask = sweep_df["tick_dir"] == 1
        sweep_sell_mask = sweep_df["tick_dir"] == -1
        sweep_neutral_mask = sweep_df["tick_dir"] == 0
        
        buy_vol = int(sweep_df.loc[sweep_buy_mask, "size"].sum())
        sell_vol = int(sweep_df.loc[sweep_sell_mask, "size"].sum())
        neutral_vol = int(sweep_df.loc[sweep_neutral_mask, "size"].sum())
        sweep_total_vol = buy_vol + sell_vol + neutral_vol
        
        buy_trades = int(sweep_buy_mask.sum())
        sell_trades = int(sweep_sell_mask.sum())
        total_sweep_trades = len(sweep_df)
        
        # Same analysis for non-sweep (Regular) trades — as baseline
        non_buy_vol = int(non_sweep_df.loc[non_sweep_df["tick_dir"] == 1, "size"].sum())
        non_sell_vol = int(non_sweep_df.loc[non_sweep_df["tick_dir"] == -1, "size"].sum())
        non_neutral_vol = int(non_sweep_df.loc[non_sweep_df["tick_dir"] == 0, "size"].sum())
        non_total = non_buy_vol + non_sell_vol + non_neutral_vol
        
        # Buy ratio
        buy_ratio = buy_vol / (buy_vol + sell_vol) if (buy_vol + sell_vol) > 0 else 0.5
        non_buy_ratio = non_buy_vol / (non_buy_vol + non_sell_vol) if (non_buy_vol + non_sell_vol) > 0 else 0.5
        
        # Block sweep aggressors (size >= 100) — the true predators
        block_sweeps = sweep_df[sweep_df["size"] >= 100]
        block_buy = int(block_sweeps.loc[block_sweeps["tick_dir"] == 1, "size"].sum())
        block_sell = int(block_sweeps.loc[block_sweeps["tick_dir"] == -1, "size"].sum())
        block_buy_ratio = block_buy / (block_buy + block_sell) if (block_buy + block_sell) > 0 else 0.5
        
        result = {
            "date": date_str,
            "total_volume": total_vol,
            "sweep_volume": sweep_total_vol,
            "sweep_buy_volume": buy_vol,
            "sweep_sell_volume": sell_vol,
            "sweep_neutral_volume": neutral_vol,
            "sweep_buy_ratio": round(buy_ratio, 4),
            "sweep_buy_trades": buy_trades,
            "sweep_sell_trades": sell_trades,
            "total_sweep_trades": total_sweep_trades,
            "non_sweep_buy_ratio": round(non_buy_ratio, 4),
            "block_sweep_buy_vol": block_buy,
            "block_sweep_sell_vol": block_sell,
            "block_sweep_buy_ratio": round(block_buy_ratio, 4),
        }
        daily_results.append(result)
        
        print(f"\n  {date_str}: {sweep_total_vol:,} sweep volume")
        print(f"  ISO Sweeps:")
        print(f"    Aggressor BUY:      {buy_vol:>10,} ({buy_ratio*100:.1f}%)  [{buy_trades} trades]")
        print(f"    Aggressor SELL:     {sell_vol:>10,} ({(1-buy_ratio)*100:.1f}%)  [{sell_trades} trades]")
        print(f"    Neutral (zero-tick): {neutral_vol:>10,}")
        print(f"  Non-Sweep Baseline:")
        print(f"    Buy ratio:          {non_buy_ratio*100:.1f}%")
        print(f"  Block ISO Sweeps (≥100 lots):")
        print(f"    Buy: {block_buy:,}  Sell: {block_sell:,}  Ratio: {block_buy_ratio*100:.1f}%")
    
    # Cross-date summary
    if daily_results:
        total_buy = sum(r["sweep_buy_volume"] for r in daily_results)
        total_sell = sum(r["sweep_sell_volume"] for r in daily_results)
        overall_ratio = total_buy / (total_buy + total_sell) if (total_buy + total_sell) > 0 else 0.5
        
        total_block_buy = sum(r["block_sweep_buy_vol"] for r in daily_results)
        total_block_sell = sum(r["block_sweep_sell_vol"] for r in daily_results)
        block_ratio = total_block_buy / (total_block_buy + total_block_sell) if (total_block_buy + total_block_sell) > 0 else 0.5
        
        non_ratios = [r["non_sweep_buy_ratio"] for r in daily_results]
        baseline = np.mean(non_ratios)
        
        print(f"\n  CROSS-DATE SUMMARY:")
        print(f"  ISO Sweep Buy Ratio:     {overall_ratio*100:.1f}% (baseline: {baseline*100:.1f}%)")
        print(f"  Block ISO Buy Ratio:     {block_ratio*100:.1f}%")
        print(f"  Excess Buy Aggression:   +{(overall_ratio - baseline)*100:.1f}pp vs baseline")
        
        if overall_ratio > 0.60:
            verdict = f"OFFENSIVE AGGRESSOR ({overall_ratio*100:.0f}% buy → hitting the Ask)"
        elif overall_ratio > 0.55:
            verdict = f"MILD AGGRESSOR ({overall_ratio*100:.0f}% buy)"
        elif overall_ratio > 0.45:
            verdict = f"BALANCED (no directional aggression)"
        else:
            verdict = f"DEFENSIVE SELLER ({(1-overall_ratio)*100:.0f}% sell → hitting the Bid)"
        
        print(f"  VERDICT: {verdict}")
    else:
        verdict = "INSUFFICIENT DATA"
        overall_ratio = 0.5
        block_ratio = 0.5
        baseline = 0.5
    
    return {
        "test": "lee_ready_aggressor",
        "symbol": symbol,
        "daily_results": daily_results,
        "overall_buy_ratio": round(overall_ratio, 4) if daily_results else None,
        "block_buy_ratio": round(block_ratio, 4) if daily_results else None,
        "baseline_buy_ratio": round(baseline, 4) if daily_results else None,
        "verdict": verdict,
    }


# ═══════════════════════════════════════════════════════════════════════
# TEST F: MICRO-TEMPORAL VANNA LAG — Minute-Level DTE Sequencing
# Map the HF Vanna Arb: does short-dated volume spike, then LEAPS follow?
# ═══════════════════════════════════════════════════════════════════════

def vanna_lag(symbol: str, dates: list, target_exp: str = None,
              leaps_dte_threshold: int = 180,
              short_dte_threshold: int = 14) -> dict:
    """
    For each squeeze date, compute minute-by-minute cumulative volume
    split by DTE bucket (short-dated vs LEAPS). Then measure the
    cross-correlation to find the temporal lag.
    
    If LEAPS accumulation systematically trails short-dated spikes by
    1-5 minutes, this is the footprint of a High-Frequency Vanna
    Arbitrage Algorithm executing in real-time.
    """
    print(f"\n{'='*70}")
    print(f"  MICRO-TEMPORAL VANNA LAG: {symbol}")
    print(f"  Dates: {', '.join(dates)}")
    print(f"  Short DTE < {short_dte_threshold} | LEAPS DTE > {leaps_dte_threshold}")
    print(f"{'='*70}")
    
    daily_results = []
    
    for date_str in dates:
        df = load_trades(symbol, date_str)
        if df.empty:
            continue
        
        # Filter to calls
        df = df[df["right"] == "C"].copy()
        if df.empty:
            continue
        
        # Compute DTE for each trade
        df["exp_dt"] = pd.to_datetime(df["expiration"])
        trade_date = pd.Timestamp(date_str)
        df["dte"] = (df["exp_dt"] - trade_date).dt.days
        
        # Classify
        df["bucket"] = "mid"
        df.loc[df["dte"] < short_dte_threshold, "bucket"] = "short"
        df.loc[df["dte"] > leaps_dte_threshold, "bucket"] = "leaps"
        
        short_total = int(df.loc[df["bucket"] == "short", "size"].sum())
        leaps_total = int(df.loc[df["bucket"] == "leaps", "size"].sum())
        
        if short_total == 0 or leaps_total == 0:
            print(f"  {date_str}: Short={short_total:,}, LEAPS={leaps_total:,} → skipping")
            continue
        
        # Minute-by-minute volume
        df["minute"] = df["ts"].dt.floor("1min")
        
        short_min = df[df["bucket"] == "short"].groupby("minute")["size"].sum()
        leaps_min = df[df["bucket"] == "leaps"].groupby("minute")["size"].sum()
        
        # Create aligned timeline (all minutes from market open to close)
        all_minutes = pd.date_range(
            df["minute"].min(), df["minute"].max(), freq="1min"
        )
        short_series = short_min.reindex(all_minutes, fill_value=0).values.astype(float)
        leaps_series = leaps_min.reindex(all_minutes, fill_value=0).values.astype(float)
        
        n_minutes = len(all_minutes)
        if n_minutes < 10:
            continue
        
        # Cross-correlation: lag k = how many minutes LEAPS trails short
        max_lag = min(30, n_minutes // 3)
        lags = range(-max_lag, max_lag + 1)
        
        # Normalize
        short_norm = (short_series - short_series.mean())
        leaps_norm = (leaps_series - leaps_series.mean())
        
        s_std = short_norm.std()
        l_std = leaps_norm.std()
        
        if s_std == 0 or l_std == 0:
            continue
        
        correlations = []
        for lag in lags:
            if lag > 0:
                # Positive lag: LEAPS at time t correlated with Short at time t-lag
                # i.e., Short leads LEAPS by `lag` minutes
                corr = np.corrcoef(short_norm[:-lag], leaps_norm[lag:])[0, 1]
            elif lag < 0:
                corr = np.corrcoef(short_norm[-lag:], leaps_norm[:lag])[0, 1]
            else:
                corr = np.corrcoef(short_norm, leaps_norm)[0, 1]
            correlations.append(float(corr) if not np.isnan(corr) else 0.0)
        
        # Find peak positive lag (Short leads → LEAPS follows)
        lag_corrs = list(zip(lags, correlations))
        positive_lags = [(l, c) for l, c in lag_corrs if l > 0]
        if positive_lags:
            peak_lag, peak_corr = max(positive_lags, key=lambda x: x[1])
        else:
            peak_lag, peak_corr = 0, 0.0
        
        # Concurrent correlation (lag=0)
        zero_corr = correlations[max_lag]  # lag=0 is at index max_lag
        
        # Top 5 short-dated spikes and what LEAPS did 1-3 min later
        spike_analysis = []
        # Find minutes with top-5 short-dated volume
        spike_minutes = short_series.argsort()[-5:][::-1]
        for sm in spike_minutes:
            s_vol = int(short_series[sm])
            # What did LEAPS do 1, 2, 3 minutes later?
            trail = {}
            for dt in [1, 2, 3, 5]:
                idx = sm + dt
                if idx < len(leaps_series):
                    trail[f"+{dt}min"] = int(leaps_series[idx])
                else:
                    trail[f"+{dt}min"] = 0
            spike_analysis.append({
                "minute": str(all_minutes[sm]),
                "short_volume": s_vol,
                "leaps_trail": trail,
            })
        
        result = {
            "date": date_str,
            "n_minutes": n_minutes,
            "short_total": short_total,
            "leaps_total": leaps_total,
            "leaps_to_short_ratio": round(leaps_total / short_total, 4),
            "concurrent_corr": round(zero_corr, 4),
            "peak_positive_lag": peak_lag,
            "peak_lag_corr": round(peak_corr, 4),
            "spike_analysis": spike_analysis,
        }
        daily_results.append(result)
        
        print(f"\n  {date_str}: Short={short_total:,}  LEAPS={leaps_total:,}  Ratio={leaps_total/short_total:.3f}")
        print(f"  {n_minutes} trading minutes analyzed")
        print(f"  Concurrent correlation (lag=0):    {zero_corr:+.4f}")
        print(f"  Peak positive lag: {peak_lag} min (r={peak_corr:+.4f})")
        print(f"  Top short-dated spikes → LEAPS response:")
        for spa in spike_analysis[:3]:
            trail_str = " | ".join(f"{k}={v:,}" for k, v in spa["leaps_trail"].items())
            print(f"    {spa['minute']}: {spa['short_volume']:,} lots → {trail_str}")
    
    # Cross-date summary
    if daily_results:
        avg_lag = np.mean([r["peak_positive_lag"] for r in daily_results])
        avg_corr = np.mean([r["peak_lag_corr"] for r in daily_results])
        avg_zero = np.mean([r["concurrent_corr"] for r in daily_results])
        
        print(f"\n  CROSS-DATE SUMMARY:")
        print(f"  Mean concurrent corr:  {avg_zero:+.4f}")
        print(f"  Mean peak lag:         {avg_lag:.1f} minutes")
        print(f"  Mean lag correlation:  {avg_corr:+.4f}")
        
        if avg_lag >= 1 and avg_corr > 0.1:
            verdict = f"VANNA ARB DETECTED (LEAPS trail short-dated by {avg_lag:.0f} min, r={avg_corr:+.3f})"
        elif avg_zero > 0.2:
            verdict = f"CONCURRENT CORRELATION (simultaneous loading, r={avg_zero:+.3f})"
        else:
            verdict = f"NO SYSTEMATIC LAG PATTERN (peak lag={avg_lag:.0f} min, r={avg_corr:+.3f})"
        
        print(f"  VERDICT: {verdict}")
    else:
        verdict = "INSUFFICIENT DATA"
    
    return {
        "test": "vanna_lag",
        "symbol": symbol,
        "daily_results": daily_results,
        "verdict": verdict,
    }



# ═══════════════════════════════════════════════════════════════════════
# MAIN: Run the battery
# ═══════════════════════════════════════════════════════════════════════

def run_jan_2021(symbol="GME"):
    """Run the full battery for the Jan 2021 squeeze."""
    results = {"event": "Jan 2021 Squeeze", "symbol": symbol, "tests": {}}
    
    # Key dates: Jan 22, 25, 26, 27 (the explosion)
    key_dates = ["20210122", "20210125", "20210126", "20210127", "20210128", "20210129"]
    
    # Test A: Whale Detector on the key injection dates
    whale = whale_detector(symbol, key_dates, target_exp="20210129", target_right="CALL")
    results["tests"]["whale_detector"] = whale
    
    # Test B: Ignition Sequence
    ignition = ignition_sequence(symbol, "20210129", lookback_days=270)
    results["tests"]["ignition_sequence"] = ignition
    
    # Test C: Constructor Fingerprint
    constructor = constructor_fingerprint(symbol, key_dates, target_exp="20210129")
    results["tests"]["constructor_fingerprint"] = constructor
    
    # Test D: Predator Matrix
    predator = predator_matrix(symbol, key_dates, target_exp="20210129")
    results["tests"]["predator_matrix"] = predator
    
    # Test E: Lee-Ready Aggressor Profile
    aggressor = lee_ready_aggressor(symbol, key_dates, target_exp="20210129")
    results["tests"]["lee_ready_aggressor"] = aggressor
    
    # Test F: Vanna Lag
    vlag = vanna_lag(symbol, key_dates)
    results["tests"]["vanna_lag"] = vlag
    
    return results


def run_jun_2024(symbol="GME"):
    """Run the full battery for the Jun 2024 squeeze."""
    results = {"event": "Jun 2024 Squeeze", "symbol": symbol, "tests": {}}
    
    # Key dates: Jun 4, 7, 10, 11, 17, 18 (the buildup + explosion)
    key_dates = ["20240604", "20240607", "20240610", "20240611", 
                 "20240617", "20240618", "20240620", "20240621"]
    
    # Test A: Whale Detector
    whale = whale_detector(symbol, key_dates, target_exp="20240621", target_right="CALL")
    results["tests"]["whale_detector"] = whale
    
    # Test B: Ignition Sequence
    ignition = ignition_sequence(symbol, "20240621", lookback_days=270)
    results["tests"]["ignition_sequence"] = ignition
    
    # Test C: Constructor Fingerprint
    constructor = constructor_fingerprint(symbol, key_dates, target_exp="20240621")
    results["tests"]["constructor_fingerprint"] = constructor
    
    # Test D: Predator Matrix
    predator = predator_matrix(symbol, key_dates, target_exp="20240621")
    results["tests"]["predator_matrix"] = predator
    
    # Test E: Lee-Ready Aggressor Profile
    aggressor = lee_ready_aggressor(symbol, key_dates, target_exp="20240621")
    results["tests"]["lee_ready_aggressor"] = aggressor
    
    # Test F: Vanna Lag
    vlag = vanna_lag(symbol, key_dates)
    results["tests"]["vanna_lag"] = vlag
    
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manipulation Forensic Battery")
    parser.add_argument("--event", choices=["jan2021", "jun2024", "both"], 
                       default="both", help="Which squeeze event(s) to analyze")
    parser.add_argument("--ticker", default="GME")
    parser.add_argument("--test", choices=["whale", "ignition", "constructor", "all"],
                       default="all", help="Which test to run")
    args = parser.parse_args()
    
    all_results = []
    
    if args.event in ("jan2021", "both"):
        r = run_jan_2021(args.ticker)
        all_results.append(r)
    
    if args.event in ("jun2024", "both"):
        r = run_jun_2024(args.ticker)
        all_results.append(r)
    
    # Save results
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = RESULTS_DIR / f"manipulation_forensic_{args.ticker}_{ts}.json"
    
    # Serialize (handle timestamp objects)
    class DateEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (pd.Timestamp, datetime)):
                return str(obj)
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super().default(obj)
    
    with open(outfile, "w") as f:
        json.dump(all_results, f, indent=2, cls=DateEncoder)
    
    print(f"\n  Results saved to: {Path(outfile).name}")
