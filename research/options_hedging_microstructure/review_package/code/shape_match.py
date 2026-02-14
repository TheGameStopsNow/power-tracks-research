#!/usr/bin/env python3
"""
Phase 98b: Shape-to-Shape Matching
====================================
Tests whether options chain profiles match burst/market shapes directly,
rather than correlating sorted activity with time-series volume.

Three modes of attack:
  1. DUMMY TEST:     Does a simple ramp score the same as real options data?
  2. SPATIAL MATCH:  Sort options by STRIKE → compare to stock PRICE distribution
  3. TRANSFORM HUNT: Try flip/reverse/scale to find how options map to price action

Usage:
  python shape_match.py --ticker GME                    # Full analysis
  python shape_match.py --ticker GME --quick             # Sample 30 dates
  python shape_match.py --ticker GME --test dummy-only   # Just the dummy test

Outputs to results/phase98/
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from itertools import product

import numpy as np
import pandas as pd
from scipy import stats
from scipy.ndimage import zoom
from scipy.signal import correlate

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw" / "thetadata" / "trades"
BURST_DIR = Path(__file__).parent.parent.parent / "docs" / "analysis" / "diagnostics" / "edgx_bursts"
RESULTS_DIR = Path(__file__).parent.parent.parent / "results" / "phase98"

try:
    sys.path.insert(0, str(Path(__file__).parent.parent / "phase94_deep_sweep"))
    from deep_sweep import (
        compute_derived_columns,
        build_grouped_snapshot,
        get_available_sort_keys,
        extract_volume_shape,
        compute_correlation,
    )
except (ImportError, ModuleNotFoundError):
    # deep_sweep only needed for shape matching tests, not data loaders
    pass


# ============================================================================
# Data Loading (shared with cluster_bridge.py)
# ============================================================================

def load_trades(ticker: str, dates: list[str]) -> pd.DataFrame:
    frames = []
    for date in dates:
        path = DATA_DIR / f"root={ticker}" / f"date={date}"
        if path.exists():
            for f in path.glob("*.parquet"):
                try:
                    df = pd.read_parquet(f)
                except (PermissionError, OSError):
                    continue
                df["source_date"] = date
                frames.append(df)
    if not frames:
        return pd.DataFrame()
    trades = pd.concat(frames, ignore_index=True)
    if "strike" in trades.columns:
        trades["strike"] = pd.to_numeric(trades["strike"], errors="coerce")
    if "size" in trades.columns and "price" in trades.columns:
        trades["notional"] = trades["size"] * trades["price"] * 100
    if "right" in trades.columns:
        trades["right"] = trades["right"].astype(str).str.upper()
    return trades


def get_available_dates(ticker: str) -> list[str]:
    dates = set()
    ticker_path = DATA_DIR / f"root={ticker}"
    if ticker_path.exists():
        for d in ticker_path.glob("date=*"):
            dates.add(d.name.split("=")[1])
    return sorted(dates)


# ============================================================================
# Shape Extraction
# ============================================================================

def extract_strike_profile(opts: pd.DataFrame, metric: str = "total_size") -> tuple[np.ndarray, np.ndarray]:
    """
    Build a SPATIAL profile: for each strike price, aggregate a metric.
    Returns (strikes_sorted, values_sorted) — both sorted by strike price.

    This is the "terrain map" of the options chain.
    """
    if opts.empty or "strike" not in opts.columns:
        return np.array([]), np.array([])

    grouped = opts.groupby("strike").agg(
        total_size=("size", "sum"),
        trade_count=("size", "count"),
        mean_price=("price", "mean"),
    ).reset_index()
    grouped["total_notional"] = grouped["total_size"] * grouped["mean_price"] * 100

    grouped = grouped.sort_values("strike")
    strikes = grouped["strike"].values.astype(np.float64)

    if metric == "total_size":
        values = grouped["total_size"].values.astype(np.float64)
    elif metric == "trade_count":
        values = grouped["trade_count"].values.astype(np.float64)
    elif metric == "total_notional":
        values = grouped["total_notional"].values.astype(np.float64)
    else:
        values = grouped["total_size"].values.astype(np.float64)

    return strikes, values


def extract_stock_price_profile(opts: pd.DataFrame) -> np.ndarray:
    """
    Extract the trade-size profile ordered by time (chronological).
    This is what the market actually produced.
    """
    if opts.empty or "size" not in opts.columns:
        return np.array([])
    return opts["size"].values.astype(np.float64)


def extract_stock_price_distribution(opts: pd.DataFrame, n_bins: int = 50) -> tuple[np.ndarray, np.ndarray]:
    """
    Build a price-level distribution from stock/options trades.
    Bin trade sizes by price level → shows WHERE volume concentrates in price space.
    """
    if opts.empty or "price" not in opts.columns or "size" not in opts.columns:
        return np.array([]), np.array([])

    prices = opts["price"].values
    sizes = opts["size"].values

    bins = np.linspace(prices.min(), prices.max(), n_bins + 1)
    bin_indices = np.digitize(prices, bins) - 1
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)

    profile = np.zeros(n_bins)
    for i in range(len(prices)):
        profile[bin_indices[i]] += sizes[i]

    bin_centers = (bins[:-1] + bins[1:]) / 2
    return bin_centers, profile


def detrend_intraday(sizes: np.ndarray, n_bins: int = 100) -> np.ndarray:
    """
    Remove the intraday "smile" pattern (high open, low lunch, high close).
    Returns residuals: actual / smoothed_trend.
    """
    if len(sizes) < n_bins:
        return sizes

    # Create a smoothed version using binned averages
    bin_size = len(sizes) // n_bins
    smoothed = np.zeros_like(sizes, dtype=np.float64)
    for i in range(n_bins):
        start = i * bin_size
        end = start + bin_size if i < n_bins - 1 else len(sizes)
        mean_val = np.mean(sizes[start:end])
        smoothed[start:end] = mean_val if mean_val > 0 else 1.0

    residuals = sizes / smoothed
    return residuals


# ============================================================================
# Transform Library
# ============================================================================

def apply_transforms(shape: np.ndarray, transforms: list[str]) -> np.ndarray:
    """Apply a sequence of transforms to a shape."""
    result = shape.copy()
    for t in transforms:
        if t == "flip":
            result = result[::-1]  # Reverse order
        elif t == "negate":
            result = -result + result.max()  # Flip values
        elif t == "log":
            result = np.log1p(np.abs(result))
        elif t == "sqrt":
            result = np.sqrt(np.abs(result))
        elif t == "normalize":
            mn, mx = result.min(), result.max()
            if mx > mn:
                result = (result - mn) / (mx - mn)
        elif t == "cumsum":
            result = np.cumsum(result)
            if result[-1] > 0:
                result = result / result[-1]
        elif t == "diff":
            result = np.diff(result, prepend=result[0])
    return result


ALL_SINGLE_TRANSFORMS = ["identity", "flip", "negate", "log", "sqrt", "cumsum", "diff"]

# Also test combinations (the user hypothesizes: "sorted, flipped, then reversed")
COMBO_TRANSFORMS = [
    ["identity"],
    ["flip"],
    ["negate"],
    ["flip", "negate"],           # Flipped + reversed values
    ["negate", "flip"],           # Reversed values + flipped order
    ["log"],
    ["log", "flip"],
    ["sqrt"],
    ["sqrt", "flip"],
    ["cumsum"],
    ["cumsum", "flip"],
    ["diff"],
    ["normalize"],
    ["normalize", "flip"],
    ["normalize", "negate"],
    ["normalize", "flip", "negate"],  # The full "sort, flip, reverse" hypothesis
]


def zncc(a: np.ndarray, b: np.ndarray) -> float:
    """Zero-Normalized Cross-Correlation between two arrays."""
    if len(a) < 5 or len(b) < 5:
        return 0.0
    # Resample to same length
    if len(a) != len(b):
        b = zoom(b, len(a) / len(b))
    a = a - np.mean(a)
    b = b - np.mean(b)
    std_a = np.std(a)
    std_b = np.std(b)
    if std_a < 1e-12 or std_b < 1e-12:
        return 0.0
    return float(np.dot(a, b) / (len(a) * std_a * std_b))


def sliding_zncc(source: np.ndarray, target: np.ndarray, window: int = 0) -> float:
    """Best ZNCC from sliding source over target."""
    if window <= 0:
        window = len(source)
    if len(source) < 5 or len(target) < window:
        return zncc(source, target)

    best = 0.0
    step = max(1, (len(target) - window) // 50)  # ~50 positions
    for start in range(0, len(target) - window, step):
        segment = target[start:start + window]
        score = abs(zncc(source, segment))
        if score > best:
            best = score
    return best


# ============================================================================
# Test 1: The Dummy Test
# ============================================================================

def run_dummy_test(ticker: str, n_dates: int = 30) -> pd.DataFrame:
    """
    The critical validation: does a simple ramp score the same as real options data?
    If yes, the current signal is just detecting "volume increases toward close."
    """
    print("\n" + "=" * 70)
    print("TEST 1: DUMMY RAMP vs REAL OPTIONS FINGERPRINT")
    print("=" * 70)

    avail = get_available_dates(ticker)
    step = max(1, len(avail) // n_dates)
    sample_dates = avail[::step]

    # Create dummy fingerprints
    dummy_ramp = np.linspace(0, 1, 50)           # Simple line [0→1]
    dummy_expo = np.exp(np.linspace(0, 3, 50))    # Exponential ramp
    dummy_flat = np.ones(50)                       # Flat (null control)
    dummy_vshape = np.abs(np.linspace(-1, 1, 50))  # V-shape (open-close pattern)

    results = []

    for i, date in enumerate(sample_dates):
        opts = load_trades(ticker, [date])
        if opts.empty or "size" not in opts.columns:
            continue

        opts = compute_derived_columns(opts)
        snapshot = build_grouped_snapshot(opts)
        stock = opts["size"].values.astype(np.float64)
        if len(stock) < 50:
            continue

        # Real fingerprint (best grouped sort)
        sort_keys = get_available_sort_keys(opts, snapshot)
        best_real = 0.0
        best_label = ""
        for sk in sort_keys:
            if sk["source"] != "grouped":
                continue
            if sk["key"] not in snapshot.columns:
                continue
            for asc in [True, False]:
                sorted_df = snapshot.sort_values(by=sk["key"], ascending=asc)
                shape = extract_volume_shape(sorted_df)
                if shape is None or len(shape) < 5:
                    continue
                s = abs(compute_correlation(stock, shape, method="zncc"))
                if s > best_real:
                    best_real = s
                    best_label = f"{sk['label']} ({'Lo→Hi' if asc else 'Hi→Lo'})"

        # Dummy scores
        ramp_score = abs(zncc(zoom(dummy_ramp, len(stock)/50), stock))
        expo_score = abs(zncc(zoom(dummy_expo, len(stock)/50), stock))
        flat_score = abs(zncc(zoom(dummy_flat, len(stock)/50), stock))
        vshape_score = abs(zncc(zoom(dummy_vshape, len(stock)/50), stock))

        # Strike-spatial fingerprint (NEW: sorted by strike, not activity)
        strikes, strike_profile = extract_strike_profile(opts, "total_size")
        if len(strike_profile) >= 5:
            strike_score = abs(zncc(zoom(strike_profile, len(stock)/len(strike_profile)), stock))
        else:
            strike_score = 0.0

        # De-trended target
        detrended = detrend_intraday(stock)
        detrended_real = abs(zncc(zoom(dummy_ramp, len(detrended)/50), detrended))

        results.append({
            "date": date,
            "n_trades": len(stock),
            "real_best": best_real,
            "real_label": best_label,
            "dummy_ramp": ramp_score,
            "dummy_expo": expo_score,
            "dummy_flat": flat_score,
            "dummy_vshape": vshape_score,
            "strike_spatial": strike_score,
            "detrended_ramp": detrended_real,
        })

        print(f"  [{i+1}/{len(sample_dates)}] {date}: Real={best_real:.4f}  "
              f"Ramp={ramp_score:.4f}  Strike={strike_score:.4f}", end="\r")

    df = pd.DataFrame(results)
    if df.empty:
        print("\nNo results!")
        return df

    print("\n\n--- DUMMY TEST RESULTS ---")
    print(f"{'Metric':<25} {'Mean':>8} {'Median':>8} {'Std':>8}")
    print("-" * 55)
    for col in ["real_best", "dummy_ramp", "dummy_expo", "dummy_flat",
                 "dummy_vshape", "strike_spatial", "detrended_ramp"]:
        print(f"{col:<25} {df[col].mean():>8.4f} {df[col].median():>8.4f} {df[col].std():>8.4f}")

    # Key comparison
    real_vs_ramp_t, real_vs_ramp_p = stats.ttest_rel(df["real_best"], df["dummy_ramp"])
    print(f"\nReal vs Dummy Ramp: t={real_vs_ramp_t:.3f}, p={real_vs_ramp_p:.6f}")
    if real_vs_ramp_p < 0.05:
        print("  → Real options data scores SIGNIFICANTLY DIFFERENT from dummy ramp ✓")
    else:
        print("  → ⚠ Real options data scores NOT different from dummy ramp — artifact detected!")

    real_vs_strike_t, real_vs_strike_p = stats.ttest_rel(df["real_best"], df["strike_spatial"])
    print(f"\nReal (activity-sorted) vs Strike (spatial): t={real_vs_strike_t:.3f}, p={real_vs_strike_p:.6f}")

    return df


# ============================================================================
# Test 2: Spatial (Strike→Price) Shape Matching
# ============================================================================

def run_spatial_test(ticker: str, n_dates: int = 50) -> pd.DataFrame:
    """
    Test: Does the OPTIONS CHAIN SHAPE (sorted by strike) predict the
    STOCK TRADE SHAPE (price distribution)?

    This is structure→structure, not rank→time.
    """
    print("\n" + "=" * 70)
    print("TEST 2: SPATIAL MATCHING (OPTIONS CHAIN → STOCK PRICE DISTRIBUTION)")
    print("=" * 70)

    avail = get_available_dates(ticker)
    step = max(1, len(avail) // n_dates)
    sample_dates = avail[::step]

    results = []

    for i, src_date in enumerate(sample_dates):
        # Find next trading day
        idx = avail.index(src_date)
        if idx + 1 >= len(avail):
            continue
        tgt_date = avail[idx + 1]

        src_opts = load_trades(ticker, [src_date])
        tgt_opts = load_trades(ticker, [tgt_date])
        if src_opts.empty or tgt_opts.empty:
            continue

        # Source: options chain profile sorted by strike
        for metric in ["total_size", "trade_count", "total_notional"]:
            strikes, src_profile = extract_strike_profile(src_opts, metric)
            if len(src_profile) < 5:
                continue

            # Target 1: Time-series volume (current method)
            tgt_timeseries = extract_stock_price_profile(tgt_opts)
            if len(tgt_timeseries) < 50:
                continue

            # Target 2: Price-level distribution (spatial)
            tgt_prices, tgt_price_dist = extract_stock_price_distribution(tgt_opts)
            if len(tgt_price_dist) < 5:
                continue

            # Score each transform of the source against each target
            for transform_seq in COMBO_TRANSFORMS:
                t_label = "→".join(transform_seq)
                transformed = apply_transforms(src_profile, transform_seq)

                # VS time-series (old method)
                score_time = abs(zncc(zoom(transformed, len(tgt_timeseries)/len(transformed)),
                                      tgt_timeseries))
                # VS price distribution (new spatial method)
                score_spatial = abs(zncc(zoom(transformed, len(tgt_price_dist)/len(transformed)),
                                         tgt_price_dist))
                # VS detrended time-series
                detrended = detrend_intraday(tgt_timeseries)
                score_detrend = abs(zncc(zoom(transformed, len(detrended)/len(transformed)),
                                         detrended))

                results.append({
                    "source_date": src_date,
                    "target_date": tgt_date,
                    "metric": metric,
                    "transform": t_label,
                    "score_timeseries": score_time,
                    "score_spatial": score_spatial,
                    "score_detrended": score_detrend,
                    "n_strikes": len(src_profile),
                    "n_trades": len(tgt_timeseries),
                })

        print(f"  [{i+1}/{len(sample_dates)}] {src_date}→{tgt_date}", end="\r")

    df = pd.DataFrame(results)
    if df.empty:
        print("\nNo results!")
        return df

    print("\n\n--- SPATIAL TEST RESULTS ---")

    # Best transforms for each target type
    for target_type in ["score_timeseries", "score_spatial", "score_detrended"]:
        print(f"\n  Top transforms for {target_type}:")
        agg = df.groupby(["metric", "transform"])[target_type].agg(["mean", "median", "std"]).round(4)
        agg = agg.sort_values("mean", ascending=False).head(10)
        print(agg.to_string())

    # Key question: does spatial beat timeseries?
    best_per_pair = df.groupby(["source_date", "target_date"]).agg(
        best_timeseries=("score_timeseries", "max"),
        best_spatial=("score_spatial", "max"),
        best_detrended=("score_detrended", "max"),
    ).reset_index()

    print(f"\n  Overall comparison (best score per pair):")
    print(f"    Timeseries mean:  {best_per_pair['best_timeseries'].mean():.4f}")
    print(f"    Spatial mean:     {best_per_pair['best_spatial'].mean():.4f}")
    print(f"    Detrended mean:   {best_per_pair['best_detrended'].mean():.4f}")

    t_ts_sp, p_ts_sp = stats.ttest_rel(best_per_pair["best_timeseries"],
                                         best_per_pair["best_spatial"])
    print(f"\n    Timeseries vs Spatial: t={t_ts_sp:.3f}, p={p_ts_sp:.6f}")

    return df


# ============================================================================
# Test 3: Transform Hunt (Find the Masking Operation)
# ============================================================================

def run_transform_hunt(ticker: str, n_dates: int = 50) -> pd.DataFrame:
    """
    Hypothesis: Options are being "sorted, flipped, then reversed" to mask them
    before feeding into the market as price action.

    This test exhaustively searches transform combinations to find the best
    mapping from options chain → stock trade pattern.
    """
    print("\n" + "=" * 70)
    print("TEST 3: TRANSFORM HUNT (Finding the Masking Operation)")
    print("=" * 70)

    avail = get_available_dates(ticker)
    step = max(1, len(avail) // n_dates)
    sample_dates = avail[::step]

    # For each source→target pair, try ALL transforms and record the best
    results = []

    for i, src_date in enumerate(sample_dates):
        idx = avail.index(src_date)
        # Test against same-day AND next-day
        target_dates = []
        if idx + 1 < len(avail):
            target_dates.append(("next_day", avail[idx + 1]))
        target_dates.append(("same_day", src_date))

        src_opts = load_trades(ticker, [src_date])
        if src_opts.empty:
            continue

        # Build multiple source shapes
        src_shapes = {}

        # Shape 1: Strike profile (spatial)
        strikes, sp = extract_strike_profile(src_opts, "total_size")
        if len(sp) >= 5:
            src_shapes["strike_size"] = sp

        strikes, sp = extract_strike_profile(src_opts, "trade_count")
        if len(sp) >= 5:
            src_shapes["strike_count"] = sp

        strikes, sp = extract_strike_profile(src_opts, "total_notional")
        if len(sp) >= 5:
            src_shapes["strike_notional"] = sp

        # Shape 2: Call vs Put profiles
        calls = src_opts[src_opts["right"] == "CALL"] if "right" in src_opts.columns else pd.DataFrame()
        puts = src_opts[src_opts["right"] == "PUT"] if "right" in src_opts.columns else pd.DataFrame()

        if not calls.empty:
            s, cp = extract_strike_profile(calls, "total_size")
            if len(cp) >= 5:
                src_shapes["call_strike"] = cp
        if not puts.empty:
            s, pp = extract_strike_profile(puts, "total_size")
            if len(pp) >= 5:
                src_shapes["put_strike"] = pp

        # Shape 3: Net delta proxy (calls - puts at each strike)
        if not calls.empty and not puts.empty:
            call_grp = calls.groupby("strike")["size"].sum()
            put_grp = puts.groupby("strike")["size"].sum()
            all_strikes = sorted(set(call_grp.index) | set(put_grp.index))
            net_delta = np.array([
                call_grp.get(s, 0) - put_grp.get(s, 0) for s in all_strikes
            ], dtype=np.float64)
            if len(net_delta) >= 5:
                src_shapes["net_call_minus_put"] = net_delta

        for tgt_label, tgt_date in target_dates:
            tgt_opts = load_trades(ticker, [tgt_date])
            if tgt_opts.empty or "size" not in tgt_opts.columns:
                continue

            tgt_timeseries = tgt_opts["size"].values.astype(np.float64)
            if len(tgt_timeseries) < 50:
                continue

            # Also build detrended target
            tgt_detrended = detrend_intraday(tgt_timeseries)

            # Also build price-level target
            tgt_prices, tgt_price_dist = extract_stock_price_distribution(tgt_opts)

            for shape_name, src_shape in src_shapes.items():
                for transform_seq in COMBO_TRANSFORMS:
                    t_label = "→".join(transform_seq)
                    transformed = apply_transforms(src_shape, transform_seq)

                    # Test against multiple target representations
                    s_time = abs(zncc(
                        zoom(transformed, len(tgt_timeseries)/len(transformed)),
                        tgt_timeseries))
                    s_detrend = abs(zncc(
                        zoom(transformed, len(tgt_detrended)/len(transformed)),
                        tgt_detrended))
                    s_spatial = 0.0
                    if len(tgt_price_dist) >= 5:
                        s_spatial = abs(zncc(
                            zoom(transformed, len(tgt_price_dist)/len(transformed)),
                            tgt_price_dist))

                    results.append({
                        "source_date": src_date,
                        "target_date": tgt_date,
                        "target_type": tgt_label,
                        "source_shape": shape_name,
                        "transform": t_label,
                        "score_timeseries": s_time,
                        "score_spatial": s_spatial,
                        "score_detrended": s_detrend,
                    })

        print(f"  [{i+1}/{len(sample_dates)}] {src_date} "
              f"({len(src_shapes)} shapes × {len(COMBO_TRANSFORMS)} transforms)", end="\r")

    df = pd.DataFrame(results)
    if df.empty:
        print("\nNo results!")
        return df

    print(f"\n\nDone – {len(df)} total comparisons")

    # Find the winning combination
    for tgt_type in ["same_day", "next_day"]:
        tdf = df[df["target_type"] == tgt_type]
        if tdf.empty:
            continue

        print(f"\n{'='*70}")
        print(f"RESULTS: {tgt_type}")
        print(f"{'='*70}")

        for score_col in ["score_timeseries", "score_spatial", "score_detrended"]:
            print(f"\n  Top 10 combinations for {score_col} ({tgt_type}):")
            agg = tdf.groupby(["source_shape", "transform"])[score_col].agg(
                ["mean", "median", "std", "count"]).round(4)
            agg = agg.sort_values("mean", ascending=False).head(10)
            print(agg.to_string())

    return df


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Phase 98b: Shape-to-Shape Matching")
    parser.add_argument("--ticker", default="GME")
    parser.add_argument("--quick", action="store_true", help="Sample ~30 dates")
    parser.add_argument("--test", default="all",
                        choices=["all", "dummy-only", "spatial-only", "transform-only"],
                        help="Which tests to run")
    args = parser.parse_args()

    n_dates = 30 if args.quick else 60

    print("=" * 70)
    print("Phase 98b: Shape-to-Shape Matching")
    print("=" * 70)
    print(f"Ticker: {args.ticker}")
    print(f"Tests:  {args.test}")
    print(f"Dates:  ~{n_dates}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")

    all_results = {}

    # Test 1: Dummy
    if args.test in ("all", "dummy-only"):
        dummy_df = run_dummy_test(args.ticker, n_dates)
        if not dummy_df.empty:
            dummy_df.to_csv(RESULTS_DIR / f"dummy_test_{args.ticker}_{ts}.csv", index=False)
            all_results["dummy"] = dummy_df

    # Test 2: Spatial
    if args.test in ("all", "spatial-only"):
        spatial_df = run_spatial_test(args.ticker, n_dates)
        if not spatial_df.empty:
            spatial_df.to_csv(RESULTS_DIR / f"spatial_test_{args.ticker}_{ts}.csv", index=False)
            all_results["spatial"] = spatial_df

    # Test 3: Transform Hunt
    if args.test in ("all", "transform-only"):
        transform_df = run_transform_hunt(args.ticker, n_dates)
        if not transform_df.empty:
            transform_df.to_parquet(RESULTS_DIR / f"transform_hunt_{args.ticker}_{ts}.parquet",
                                    index=False)
            all_results["transform"] = transform_df

    print(f"\n{'='*70}")
    print(f"All results saved to {RESULTS_DIR}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
