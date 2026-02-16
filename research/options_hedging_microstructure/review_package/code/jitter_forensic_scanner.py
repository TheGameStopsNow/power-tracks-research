#!/usr/bin/env python3
"""
jitter_fingerprint_scanner.py — Cross-Date SOR Jitter Matching
================================================================
Scans all available GME trading dates for block-size triplets that match
the TWAP jitter patterns found in the Reddit post ([150,154,150], [100,102,100]).

Logic:
  1. For each date, load block trades (≥ min_size lots).
  2. Extract all consecutive 3-trade windows within a time_window.
  3. Normalize each triplet into a canonical "jitter fingerprint":
     - Base size = first trade's size
     - Deltas = (size[1]-size[0], size[2]-size[1])
     - Pattern type: "ABA" (return to base), "STEP" (monotonic), etc.
  4. Collect fingerprints across all dates.
  5. Find fingerprints that appear on multiple dates, especially dates
     far apart in time.

Usage:
    python jitter_fingerprint_scanner.py [--min-size 50] [--max-jitter 10]
                                          [--time-window 120] [--min-dates 2]
"""

import sys, json, argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import numpy as np
import pandas as pd

# Import from review_package/code where manipulation_forensic.py lives
_REVIEW_CODE = str(Path(__file__).resolve().parents[2] / "options_hedging_microstructure" / "review_package" / "code")
sys.path.insert(0, _REVIEW_CODE)

from manipulation_forensic import load_trades, EXCHANGE_MAP, TRADES_ROOT

_SCRIPT_DIR = Path(__file__).resolve().parent
RESULTS_DIR = _SCRIPT_DIR.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def _exchange_name(code: int) -> str:
    return EXCHANGE_MAP.get(code, f"UNK_{code}")


def get_all_dates(symbol: str) -> list[str]:
    """Get all available trading dates for a symbol."""
    root = TRADES_ROOT / f"root={symbol}"
    if not root.exists():
        return []
    dates = sorted([
        d.name.replace("date=", "")
        for d in root.iterdir()
        if d.is_dir() and d.name.startswith("date=")
    ])
    return dates


def _scan_block_sequence(blocks_df, max_jitter: int, time_window_sec: float,
                         date_str: str, scan_mode: str,
                         contract_key: str = None) -> list[dict]:
    """
    Core triplet scanner over a pre-sorted DataFrame of block trades.
    
    Args:
        blocks_df: DataFrame of block trades, already sorted by timestamp
        max_jitter: Maximum allowed size difference between consecutive trades
        time_window_sec: Maximum time span across the 3 trades
        date_str: The trading date string
        scan_mode: "per_contract" or "cross_contract" — for tagging output
        contract_key: Optional string describing the contract group
    """
    if len(blocks_df) < 3:
        return []

    triplets = []
    sizes = blocks_df["size"].values
    timestamps = blocks_df["ts"].values
    exchanges = blocks_df["exchange"].values

    # For per-contract mode, pull contract info from the first row
    # For cross-contract mode, pull from each individual row
    strikes = blocks_df["strike"].values if "strike" in blocks_df.columns else None
    rights = blocks_df["right"].values if "right" in blocks_df.columns else None

    for i in range(len(blocks_df) - 2):
        s0, s1, s2 = int(sizes[i]), int(sizes[i+1]), int(sizes[i+2])

        # Check jitter constraint
        d1 = abs(s1 - s0)
        d2 = abs(s2 - s1)

        if d1 > max_jitter or d2 > max_jitter:
            continue
        if d1 == 0 and d2 == 0:
            continue  # Exact same sizes — wash-trade territory, not jitter

        # Check time window
        t0 = pd.Timestamp(timestamps[i])
        t2 = pd.Timestamp(timestamps[i+2])
        span_sec = (t2 - t0).total_seconds()
        if span_sec > time_window_sec:
            continue

        # Build fingerprint
        base = min(s0, s1, s2)
        offsets = (s0 - base, s1 - base, s2 - base)

        # Pattern classification
        if s0 == s2 and s1 != s0:
            pattern = "ABA"
        elif s0 < s1 < s2 or s0 > s1 > s2:
            pattern = "STEP"
        elif s0 == s1 or s1 == s2:
            pattern = "FLAT_STEP"
        else:
            pattern = "ZIGZAG"

        exch_list = [
            _exchange_name(int(exchanges[i])),
            _exchange_name(int(exchanges[i+1])),
            _exchange_name(int(exchanges[i+2]))
        ]

        entry = {
            "sizes": [s0, s1, s2],
            "fingerprint": f"[{s0},{s1},{s2}]",
            "pattern": pattern,
            "jitter_max": max(d1, d2),
            "base_size": base,
            "offsets": list(offsets),
            "time_span_sec": round(span_sec, 3),
            "exchanges": exch_list,
            "timestamps": [str(pd.Timestamp(timestamps[i+k])) for k in range(3)],
            "date": date_str,
            "scan_mode": scan_mode,
        }

        # Add contract info
        if contract_key:
            entry["contract"] = contract_key
        if strikes is not None:
            entry["strikes"] = [float(strikes[i+k]) for k in range(3)]
        if rights is not None:
            entry["rights"] = [str(rights[i+k]) for k in range(3)]

        triplets.append(entry)

    return triplets


def extract_jitter_triplets(symbol: str, date_str: str,
                            min_size: int = 50,
                            max_jitter: int = 10,
                            time_window_sec: float = 120.0,
                            per_contract: bool = True) -> list[dict]:
    """
    Extract all block-trade triplets where sizes differ by small jitter amounts.

    Two scan modes (both enabled by default):
      1. PER-CONTRACT: Group trades by (strike, right, expiration) FIRST, then
         scan within each contract. This avoids organic noise from other contracts
         breaking the triplet detection on high-volume days.
      2. CROSS-CONTRACT: Scan the full block tape in timestamp order (original
         behavior). Finds SOR-spread patterns that deliberately hit different
         strikes.

    Returns list of dicts with fingerprint info.
    """
    df = load_trades(symbol, date_str)
    if df.empty:
        return []

    # Filter to block trades
    blocks = df[df["size"] >= min_size].sort_values("ts").reset_index(drop=True)

    if len(blocks) < 3:
        return []

    triplets = []
    seen_keys = set()  # Deduplicate across modes

    # ── MODE 1: Per-contract scanning ──
    # Group by (strike, right, expiration) to isolate each contract's tape.
    # This prevents organic noise from other strikes from breaking detection.
    if per_contract:
        # Determine expiration column name
        exp_col = "expiration" if "expiration" in blocks.columns else "expiry"
        group_cols = ["strike", "right"]
        if exp_col in blocks.columns:
            group_cols.append(exp_col)

        for group_key, contract_df in blocks.groupby(group_cols):
            contract_blocks = contract_df.sort_values("ts").reset_index(drop=True)
            if len(contract_blocks) < 3:
                continue

            if isinstance(group_key, tuple):
                contract_str = "/".join(str(g) for g in group_key)
            else:
                contract_str = str(group_key)

            contract_triplets = _scan_block_sequence(
                contract_blocks, max_jitter, time_window_sec,
                date_str, scan_mode="per_contract",
                contract_key=contract_str,
            )

            for t in contract_triplets:
                # Deduplicate by (fingerprint, first_timestamp)
                dedup_key = (t["fingerprint"], t["timestamps"][0])
                if dedup_key not in seen_keys:
                    seen_keys.add(dedup_key)
                    triplets.append(t)

    # ── MODE 2: Cross-contract scanning (original behavior) ──
    # Scan the full tape in timestamp order. Catches patterns that
    # deliberately hit different strikes as part of a synthetic build.
    cross_triplets = _scan_block_sequence(
        blocks, max_jitter, time_window_sec,
        date_str, scan_mode="cross_contract",
    )

    for t in cross_triplets:
        dedup_key = (t["fingerprint"], t["timestamps"][0])
        if dedup_key not in seen_keys:
            seen_keys.add(dedup_key)
            triplets.append(t)

    return triplets


def scan_all_dates(symbol: str = "GME",
                   min_size: int = 50,
                   max_jitter: int = 6,
                   time_window_sec: float = 120.0,
                   min_dates_for_match: int = 2,
                   sample_every_n: int = 1) -> dict:
    """
    Scan all available dates for jitter triplets and find cross-date matches.
    
    Args:
        sample_every_n: Process every Nth date (for speed). 1 = all dates.
    """
    all_dates = get_all_dates(symbol)
    if sample_every_n > 1:
        all_dates = all_dates[::sample_every_n]
    
    print(f"\n{'='*70}")
    print(f"  JITTER FINGERPRINT SCANNER — {symbol}")
    print(f"  Dates: {len(all_dates)} | Min size: {min_size} | Max jitter: ±{max_jitter}")
    print(f"  Time window: {time_window_sec}s | Min dates for match: {min_dates_for_match}")
    print(f"{'='*70}\n")
    
    # Phase 1: Extract triplets from all dates
    fingerprint_registry = defaultdict(list)  # fingerprint_key -> list of occurrences
    total_triplets = 0
    dates_with_triplets = 0
    
    for i, date_str in enumerate(all_dates):
        if i % 50 == 0:
            print(f"  Scanning {i+1}/{len(all_dates)}: {date_str}...", flush=True)
        
        try:
            triplets = extract_jitter_triplets(
                symbol, date_str,
                min_size=min_size,
                max_jitter=max_jitter,
                time_window_sec=time_window_sec,
            )
        except Exception as e:
            print(f"    Error on {date_str}: {e}")
            continue
        
        if triplets:
            dates_with_triplets += 1
            total_triplets += len(triplets)
            
            for t in triplets:
                key = t["fingerprint"]
                fingerprint_registry[key].append(t)
    
    print(f"\n  Phase 1 complete: {total_triplets} triplets from {dates_with_triplets} dates")
    print(f"  Unique fingerprints: {len(fingerprint_registry)}")
    
    # Phase 2: Find cross-date matches
    cross_date_matches = {}
    
    for fp_key, occurrences in fingerprint_registry.items():
        # Get unique dates for this fingerprint
        dates_seen = sorted(set(o["date"] for o in occurrences))
        
        if len(dates_seen) >= min_dates_for_match:
            # Calculate date span
            first_date = pd.Timestamp(dates_seen[0])
            last_date = pd.Timestamp(dates_seen[-1])
            span_days = (last_date - first_date).days
            
            cross_date_matches[fp_key] = {
                "fingerprint": fp_key,
                "sizes": occurrences[0]["sizes"],
                "pattern": occurrences[0]["pattern"],
                "jitter_max": occurrences[0]["jitter_max"],
                "dates_count": len(dates_seen),
                "total_occurrences": len(occurrences),
                "date_span_days": span_days,
                "first_date": dates_seen[0],
                "last_date": dates_seen[-1],
                "dates": dates_seen,
                # Keep a sample of occurrences (up to 20)
                "sample_occurrences": occurrences[:20],
            }
    
    # Sort by date span (widest first) then by occurrence count
    ranked = sorted(
        cross_date_matches.values(),
        key=lambda x: (x["date_span_days"], x["dates_count"]),
        reverse=True,
    )
    
    # Phase 3: Print results
    print(f"\n{'='*70}")
    print(f"  PHASE 2: CROSS-DATE MATCHES (fingerprints seen on {min_dates_for_match}+ dates)")
    print(f"{'='*70}")
    print(f"\n  Total cross-date fingerprints: {len(ranked)}")
    
    # Focus on ABA patterns (most suspicious — return to base)
    aba_matches = [r for r in ranked if r["pattern"] == "ABA"]
    print(f"  ABA patterns (return-to-base): {len(aba_matches)}")
    
    print(f"\n  --- TOP 30 by date span (widest first) ---")
    for r in ranked[:30]:
        print(f"\n    {r['fingerprint']}  [{r['pattern']}]  "
              f"jitter=±{r['jitter_max']}  "
              f"seen on {r['dates_count']} dates  "
              f"({r['total_occurrences']} total)  "
              f"span={r['date_span_days']} days")
        # Show first and last occurrence details
        first = r["sample_occurrences"][0]
        last = [o for o in r["sample_occurrences"] if o["date"] == r["last_date"]]
        last = last[0] if last else r["sample_occurrences"][-1]
        
        print(f"      First: {first['date']}  {' -> '.join(first['exchanges'])}  "
              f"span={first['time_span_sec']:.1f}s")
        if last["date"] != first["date"]:
            print(f"      Last:  {last['date']}  {' -> '.join(last['exchanges'])}  "
                  f"span={last['time_span_sec']:.1f}s")
    
    # Special: check for the known fingerprints from the post
    known_fps = ["[150,154,150]", "[100,102,100]"]
    print(f"\n  --- KNOWN FINGERPRINTS FROM POST ---")
    for kfp in known_fps:
        if kfp in fingerprint_registry:
            occs = fingerprint_registry[kfp]
            dates_seen = sorted(set(o["date"] for o in occs))
            print(f"\n    {kfp}: found on {len(dates_seen)} dates")
            for o in occs:
                print(f"      {o['date']}  {o['timestamps'][0]}  "
                      f"{' -> '.join(o['exchanges'])}  span={o['time_span_sec']:.1f}s")
        else:
            print(f"\n    {kfp}: NOT FOUND in scan")
    
    # Build output
    result = {
        "scanner": "jitter_fingerprint_v1",
        "symbol": symbol,
        "parameters": {
            "min_size": min_size,
            "max_jitter": max_jitter,
            "time_window_sec": time_window_sec,
            "min_dates_for_match": min_dates_for_match,
            "sample_every_n": sample_every_n,
        },
        "dates_scanned": len(all_dates),
        "dates_with_triplets": dates_with_triplets,
        "total_triplets": total_triplets,
        "unique_fingerprints": len(fingerprint_registry),
        "cross_date_matches": len(ranked),
        "aba_matches": len(aba_matches),
        "top_matches": ranked[:50],
        "known_fingerprint_results": {
            kfp: {
                "found": kfp in fingerprint_registry,
                "dates_count": len(set(o["date"] for o in fingerprint_registry.get(kfp, []))),
                "occurrences": fingerprint_registry.get(kfp, []),
            }
            for kfp in known_fps
        },
    }
    
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cross-Date Jitter Fingerprint Scanner")
    parser.add_argument("--ticker", default="GME")
    parser.add_argument("--min-size", type=int, default=50,
                        help="Minimum trade size (lots) to consider")
    parser.add_argument("--max-jitter", type=int, default=6,
                        help="Maximum jitter between consecutive trades")
    parser.add_argument("--time-window", type=float, default=120.0,
                        help="Maximum time span (seconds) for a triplet")
    parser.add_argument("--min-dates", type=int, default=2,
                        help="Minimum dates a fingerprint must appear on")
    parser.add_argument("--sample", type=int, default=1,
                        help="Process every Nth date (for speed)")
    args = parser.parse_args()
    
    result = scan_all_dates(
        symbol=args.ticker,
        min_size=args.min_size,
        max_jitter=args.max_jitter,
        time_window_sec=args.time_window,
        min_dates_for_match=args.min_dates,
        sample_every_n=args.sample,
    )
    
    # Save results
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = RESULTS_DIR / f"jitter_fingerprint_{args.ticker}_{ts}.json"
    
    with open(out_file, "w") as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n  Results saved to: {out_file.name}")
    print(f"  Cross-date matches: {result['cross_date_matches']}")
    print(f"  ABA patterns: {result['aba_matches']}")
