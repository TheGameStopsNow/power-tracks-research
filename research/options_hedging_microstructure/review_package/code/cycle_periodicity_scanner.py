#!/usr/bin/env python3
"""
Cycle Periodicity Scanner — GME Macro-Cycle Analysis
=====================================================
Explores repeating cycles in daily return series, focusing on the
~370d (half-cycle) and ~741d (full-cycle) hypothesis.

Tests:
  1. FFT spectral power — finds dominant periodicities in the data
  2. Multi-lag ACF — tests for autocorrelation at specific day-offsets
  3. Rolling-window return cross-correlation — mirrors/reflections
  4. Blended Reflection Detection — does past structure play backward,
     blended with a current cadence?

Usage:
  cd /path/to/project
  source .venv/bin/activate
  python research/options_hedging_microstructure/cycle_periodicity_scanner.py
"""
import sys
import json
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

# ── Data paths ──────────────────────────────────────────────────────────
POLYGON_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "raw" / "polygon" / "trades"
)
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ── Reuse existing data loader ──────────────────────────────────────────
ENGINE_DIR = Path(__file__).parent.parent / "phase98_cluster_bridge"
sys.path.insert(0, str(ENGINE_DIR))
try:
    from temporal_convolution_engine import load_equity_day
except ImportError:
    print("⚠️  Could not import load_equity_day, falling back to direct parquet load")
    def load_equity_day(symbol, date_str):
        p = POLYGON_DIR / f"symbol={symbol}" / f"date={date_str}" / "part-0.parquet"
        if not p.exists():
            return pd.DataFrame()
        df = pd.read_parquet(p)
        if "timestamp" in df.columns:
            df["ts"] = pd.to_datetime(df["timestamp"])
        return df

SYMBOL = "GME"


# ═══════════════════════════════════════════════════════════════════════
# 1. Build daily return series from tick data
# ═══════════════════════════════════════════════════════════════════════
def build_daily_series(symbol: str) -> pd.DataFrame:
    """Build a daily OHLCV-like series from tick data."""
    sym_dir = POLYGON_DIR / f"symbol={symbol}"
    if not sym_dir.exists():
        raise FileNotFoundError(f"No data for {symbol}")

    dates = sorted(d.name.split("=")[1] for d in sym_dir.glob("date=*"))
    print(f"  Found {len(dates)} trading days ({dates[0]} → {dates[-1]})")

    rows = []
    for i, date_str in enumerate(dates):
        eq = load_equity_day(symbol, date_str)
        if eq.empty or "price" not in eq.columns or len(eq) < 10:
            continue
        prices = eq["price"].values
        rows.append({
            "date": pd.Timestamp(date_str),
            "open": prices[0],
            "high": prices.max(),
            "low": prices.min(),
            "close": prices[-1],
            "volume": len(prices),  # trade count as proxy
            "vwap": np.mean(prices),
        })
        if (i + 1) % 200 == 0:
            print(f"    ... loaded {i+1}/{len(dates)} days")

    df = pd.DataFrame(rows).set_index("date").sort_index()
    df["log_return"] = np.log(df["close"] / df["close"].shift(1))
    df["pct_return"] = df["close"].pct_change()
    print(f"  Built daily series: {len(df)} valid days")
    return df


# ═══════════════════════════════════════════════════════════════════════
# 2. FFT Spectral Analysis — Find dominant periodicities
# ═══════════════════════════════════════════════════════════════════════
def spectral_analysis(returns: np.ndarray, label: str = "log_return") -> dict:
    """FFT-based spectral scan of the return series."""
    clean = returns[~np.isnan(returns)]
    n = len(clean)
    
    # Detrend
    clean = clean - np.mean(clean)
    
    # Apply Hann window to reduce spectral leakage
    window = np.hanning(n)
    windowed = clean * window
    
    fft = np.fft.rfft(windowed)
    power = np.abs(fft) ** 2
    freqs = np.fft.rfftfreq(n, d=1.0)  # d=1 trading day
    periods = np.where(freqs > 0, 1.0 / freqs, np.inf)
    
    # Skip DC component (index 0) and very low freq (period > n/2)
    mask = (periods > 5) & (periods < n / 2) & np.isfinite(periods)
    valid_power = power[mask]
    valid_periods = periods[mask]
    
    # Normalize power to percentage of total
    total_power = valid_power.sum()
    pct_power = valid_power / total_power * 100 if total_power > 0 else valid_power
    
    # Sort by power descending
    sort_idx = np.argsort(-valid_power)
    
    # Top 20 peaks
    peaks = []
    for idx in sort_idx[:20]:
        peaks.append({
            "period_days": round(float(valid_periods[idx]), 1),
            "power": float(valid_power[idx]),
            "pct_power": round(float(pct_power[idx]), 3),
        })
    
    # Specifically check the 370 and 741 range
    target_ranges = [
        ("~250 (1yr trading)", 240, 265),
        ("~370 (1yr calendar)", 355, 385),
        ("~500 (2yr trading)", 490, 520),
        ("~740 (2yr calendar)", 720, 760),
        ("~1110 (3yr calendar)", 1080, 1140),
        ("~125 (half-year)", 115, 135),
        ("~63 (quarterly)", 55, 70),
    ]
    
    target_results = {}
    for name, lo, hi in target_ranges:
        band_mask = (valid_periods >= lo) & (valid_periods <= hi)
        if band_mask.any():
            band_power = valid_power[band_mask]
            band_periods = valid_periods[band_mask]
            peak_idx = np.argmax(band_power)
            target_results[name] = {
                "peak_period": round(float(band_periods[peak_idx]), 1),
                "peak_power": float(band_power[peak_idx]),
                "pct_of_total": round(float(band_power[peak_idx] / total_power * 100), 3),
                "band_total_pct": round(float(band_power.sum() / total_power * 100), 3),
            }
        else:
            target_results[name] = {"peak_period": None, "pct_of_total": 0}
    
    return {
        "n_samples": n,
        "max_detectable_period": n / 2,
        "top_20_peaks": peaks,
        "target_bands": target_results,
    }


# ═══════════════════════════════════════════════════════════════════════
# 3. Multi-Lag ACF — Autocorrelation at specific offsets
# ═══════════════════════════════════════════════════════════════════════
def multi_lag_acf(returns: np.ndarray, lags: list[int]) -> dict:
    """Compute ACF at each specified lag."""
    clean = returns[~np.isnan(returns)]
    n = len(clean)
    mean = np.mean(clean)
    var = np.var(clean)
    
    if var < 1e-12:
        return {lag: np.nan for lag in lags}
    
    results = {}
    for lag in lags:
        if lag >= n:
            results[lag] = np.nan
            continue
        cov = np.mean((clean[:n-lag] - mean) * (clean[lag:] - mean))
        results[lag] = round(float(cov / var), 6)
    
    return results


def acf_range_scan(returns: np.ndarray, center: int, half_width: int = 30) -> list[dict]:
    """Scan ACF across a range of lags centered on a target period."""
    clean = returns[~np.isnan(returns)]
    n = len(clean)
    mean = np.mean(clean)
    var = np.var(clean)
    
    if var < 1e-12:
        return []
    
    results = []
    for lag in range(max(1, center - half_width), min(n, center + half_width + 1)):
        cov = np.mean((clean[:n-lag] - mean) * (clean[lag:] - mean))
        acf_val = cov / var
        results.append({
            "lag": lag,
            "acf": round(float(acf_val), 6),
        })
    
    return results


# ═══════════════════════════════════════════════════════════════════════
# 4. Rolling-Window Cross-Correlation — Reflection Detection
# ═══════════════════════════════════════════════════════════════════════
def reflection_scan(returns: np.ndarray, offset: int, window: int = 60) -> dict:
    """
    Test whether the return series at day d mirrors (time-reverses) the
    series at day d + offset. Uses rolling windows.
    
    For each window position, compute:
      - Forward correlation:  corr(segment_a, segment_b)
      - Mirror correlation:   corr(segment_a, reverse(segment_b))
      - Flip correlation:     corr(segment_a, -segment_b)
      - Mirror-flip:          corr(segment_a, -reverse(segment_b))
    """
    clean = returns[~np.isnan(returns)]
    n = len(clean)
    
    if offset + window >= n:
        return {"error": f"offset {offset} + window {window} exceeds data length {n}"}
    
    n_windows = n - offset - window
    if n_windows < 10:
        return {"error": "insufficient data for this offset"}
    
    forward_corrs = []
    mirror_corrs = []
    flip_corrs = []
    mirror_flip_corrs = []
    
    for i in range(0, n_windows, max(1, window // 4)):  # step by quarter-window
        a = clean[i:i+window]
        b = clean[i+offset:i+offset+window]
        
        if len(a) != window or len(b) != window:
            continue
        
        # Normalize
        a_norm = (a - a.mean())
        b_norm = (b - b.mean())
        
        a_std = np.std(a_norm)
        b_std = np.std(b_norm)
        if a_std < 1e-12 or b_std < 1e-12:
            continue
        
        a_norm = a_norm / a_std
        b_norm = b_norm / b_std
        
        # Forward: do they repeat?
        forward = float(np.mean(a_norm * b_norm))
        # Mirror: does b play backward?
        mirror = float(np.mean(a_norm * b_norm[::-1]))
        # Flip: does b invert?
        flip = float(np.mean(a_norm * (-b_norm)))
        # Mirror-flip: does b play backward AND inverted?
        mirror_flip = float(np.mean(a_norm * (-b_norm[::-1])))
        
        forward_corrs.append(forward)
        mirror_corrs.append(mirror)
        flip_corrs.append(flip)
        mirror_flip_corrs.append(mirror_flip)
    
    if not forward_corrs:
        return {"error": "no valid windows"}
    
    def stats(arr):
        a = np.array(arr)
        return {
            "mean": round(float(np.mean(a)), 4),
            "median": round(float(np.median(a)), 4),
            "std": round(float(np.std(a)), 4),
            "p95": round(float(np.percentile(a, 95)), 4),
            "p99": round(float(np.percentile(a, 99)), 4),
            "pct_above_0.3": round(float(np.mean(np.abs(a) > 0.3) * 100), 1),
            "n_windows": len(a),
        }
    
    return {
        "offset": offset,
        "window": window,
        "forward": stats(forward_corrs),
        "mirror": stats(mirror_corrs),
        "flip": stats(flip_corrs),
        "mirror_flip": stats(mirror_flip_corrs),
    }


# ═══════════════════════════════════════════════════════════════════════
# 5. Blended Reflection Scanner
# ═══════════════════════════════════════════════════════════════════════
def blended_reflection_scan(
    returns: np.ndarray,
    cycle_period: int,
    window: int = 60,
    blend_cadences: list[int] | None = None,
) -> dict:
    """
    Test the 'blended reflection' hypothesis:
    Does the market replay past moves in reverse, but blend them with
    a current-period cadence to mask the unwinding?
    
    For each window at offset=cycle_period:
      1. Compute the mirror correlation (as in reflection_scan)
      2. For each blend_cadence c, subsample every c-th return and
         test whether the subsampled series shows stronger mirror signal
    
    If blending is occurring, subsampled series at the 'right' cadence
    should show HIGHER mirror correlation than the raw series.
    """
    clean = returns[~np.isnan(returns)]
    n = len(clean)
    
    if blend_cadences is None:
        blend_cadences = [2, 3, 4, 5, 7, 10, 14, 21]
    
    if cycle_period + window >= n:
        return {"error": "insufficient data"}
    
    n_windows = n - cycle_period - window
    
    results_by_cadence = {}
    
    for cadence in [1] + blend_cadences:  # 1 = raw (no cadence filter)
        mirror_corrs = []
        mirror_flip_corrs = []
        
        for i in range(0, n_windows, max(1, window // 4)):
            a_full = clean[i:i+window]
            b_full = clean[i+cycle_period:i+cycle_period+window]
            
            if len(a_full) != window or len(b_full) != window:
                continue
            
            # Subsample at cadence
            a = a_full[::cadence]
            b = b_full[::cadence]
            
            if len(a) < 5 or len(b) < 5:
                continue
            
            min_len = min(len(a), len(b))
            a = a[:min_len]
            b = b[:min_len]
            
            a_std = np.std(a)
            b_std = np.std(b)
            if a_std < 1e-12 or b_std < 1e-12:
                continue
            
            a_n = (a - a.mean()) / a_std
            b_n = (b - b.mean()) / b_std
            
            mirror = float(np.mean(a_n * b_n[::-1]))
            mirror_flip = float(np.mean(a_n * (-b_n[::-1])))
            
            mirror_corrs.append(mirror)
            mirror_flip_corrs.append(mirror_flip)
        
        if mirror_corrs:
            results_by_cadence[cadence] = {
                "cadence": cadence,
                "label": "raw" if cadence == 1 else f"every-{cadence}th",
                "mirror_mean": round(float(np.mean(mirror_corrs)), 4),
                "mirror_flip_mean": round(float(np.mean(mirror_flip_corrs)), 4),
                "mirror_p95": round(float(np.percentile(np.abs(mirror_corrs), 95)), 4),
                "n_windows": len(mirror_corrs),
            }
    
    # Find the cadence with strongest mirror signal
    if results_by_cadence:
        best_cadence = max(
            results_by_cadence.values(),
            key=lambda r: abs(r["mirror_mean"])
        )
    else:
        best_cadence = None
    
    return {
        "cycle_period": cycle_period,
        "window": window,
        "results_by_cadence": results_by_cadence,
        "best_cadence": best_cadence,
    }


# ═══════════════════════════════════════════════════════════════════════
# 6. Multi-Cycle Phase Analysis
# ═══════════════════════════════════════════════════════════════════════
def multi_cycle_phase_analysis(
    returns: np.ndarray,
    cycle_period: int,
    window: int = 60,
) -> dict:
    """
    Given a cycle period, segment the data into successive cycles
    and analyze the phase relationship between them:
    
    Cycle 1 vs Cycle 2: forward, mirror, flip, mirror-flip
    Cycle 2 vs Cycle 3: forward, mirror, flip, mirror-flip
    Cycle 1 vs Cycle 3: forward, mirror, flip, mirror-flip
    
    This tests the three-phase hypothesis:
    Cycle 1 = Forward, Cycle 2 = Mirror, Cycle 3 = Flip/Reset
    """
    clean = returns[~np.isnan(returns)]
    n = len(clean)
    
    n_cycles = n // cycle_period
    if n_cycles < 2:
        return {"error": f"only {n_cycles} complete cycles, need ≥ 2"}
    
    cycles = []
    for c in range(n_cycles):
        start = c * cycle_period
        end = start + cycle_period
        cycles.append(clean[start:end])
    
    # Partial last cycle
    remainder = clean[n_cycles * cycle_period:]
    remainder_pct = round(len(remainder) / cycle_period * 100, 1) if cycle_period > 0 else 0
    
    def correlate_segments(a, b):
        """Full-segment correlations (forward, mirror, flip, mirror-flip)."""
        min_len = min(len(a), len(b))
        a = a[:min_len]
        b = b[:min_len]
        
        a_std = np.std(a)
        b_std = np.std(b)
        if a_std < 1e-12 or b_std < 1e-12:
            return {"forward": 0, "mirror": 0, "flip": 0, "mirror_flip": 0}
        
        a_n = (a - a.mean()) / a_std
        b_n = (b - b.mean()) / b_std
        
        return {
            "forward": round(float(np.corrcoef(a_n, b_n)[0, 1]), 4),
            "mirror": round(float(np.corrcoef(a_n, b_n[::-1])[0, 1]), 4),
            "flip": round(float(np.corrcoef(a_n, -b_n)[0, 1]), 4),
            "mirror_flip": round(float(np.corrcoef(a_n, -b_n[::-1])[0, 1]), 4),
        }
    
    # Compute pairwise cycle correlations
    comparisons = {}
    for i in range(len(cycles)):
        for j in range(i + 1, len(cycles)):
            key = f"cycle_{i+1}_vs_{j+1}"
            comparisons[key] = correlate_segments(cycles[i], cycles[j])
            
            # Also test half-cycle correlations
            half = cycle_period // 2
            comparisons[f"{key}_first_half"] = correlate_segments(
                cycles[i][:half], cycles[j][:half]
            )
            comparisons[f"{key}_second_half"] = correlate_segments(
                cycles[i][half:], cycles[j][half:]
            )
    
    # Per-cycle price trajectory summary
    cycle_stats = []
    for c_idx, cyc in enumerate(cycles):
        cum_ret = np.exp(np.cumsum(cyc)) - 1  # cumulative return
        cycle_stats.append({
            "cycle": c_idx + 1,
            "n_days": len(cyc),
            "total_return": round(float(cum_ret[-1] * 100), 1),
            "max_drawup": round(float(cum_ret.max() * 100), 1),
            "max_drawdown": round(float(cum_ret.min() * 100), 1),
            "mean_daily_vol": round(float(np.std(cyc) * 100), 4),
        })
    
    return {
        "cycle_period": cycle_period,
        "n_complete_cycles": len(cycles),
        "remainder_days": len(remainder),
        "remainder_pct": remainder_pct,
        "cycle_stats": cycle_stats,
        "comparisons": comparisons,
    }


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════
def main():
    print(f"\n{'='*80}")
    print(f"  CYCLE PERIODICITY SCANNER — {SYMBOL}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*80}\n")
    
    # ── 1. Build daily series ───────────────────────────────────────
    print("▸ Building daily return series from tick data...")
    daily = build_daily_series(SYMBOL)
    returns = daily["log_return"].values
    
    all_results = {"symbol": SYMBOL, "n_days": len(daily),
                   "date_range": f"{daily.index[0].date()} → {daily.index[-1].date()}"}
    
    # ── 2. FFT Spectral Analysis ────────────────────────────────────
    print("\n▸ Running FFT spectral analysis...")
    spectral = spectral_analysis(returns, "log_return")
    all_results["spectral"] = spectral
    
    print(f"\n  Top 20 Spectral Peaks (by power):")
    print(f"  {'Rank':>4}  {'Period (days)':>14}  {'% of Total':>12}")
    print(f"  {'─'*4}  {'─'*14}  {'─'*12}")
    for i, peak in enumerate(spectral["top_20_peaks"], 1):
        marker = ""
        p = peak["period_days"]
        if 355 <= p <= 385:
            marker = "  ◄ ~370d"
        elif 720 <= p <= 760:
            marker = "  ◄ ~741d"
        elif 240 <= p <= 265:
            marker = "  ◄ ~252d (1yr trading)"
        elif 490 <= p <= 520:
            marker = "  ◄ ~504d (2yr trading)"
        elif 1080 <= p <= 1140:
            marker = "  ◄ ~3yr"
        print(f"  {i:4d}  {p:14.1f}  {peak['pct_power']:11.3f}%{marker}")
    
    print(f"\n  Target Band Analysis:")
    for name, data in spectral["target_bands"].items():
        if data.get("peak_period"):
            print(f"    {name:30s} → Peak at {data['peak_period']:.1f}d, {data['pct_of_total']:.3f}% of total")
        else:
            print(f"    {name:30s} → No signal in band")
    
    # ── 3. Multi-Lag ACF ────────────────────────────────────────────
    print("\n▸ Computing multi-lag ACF at specific offsets...")
    target_lags = [1, 5, 21, 63, 126, 252, 370, 504, 741, 1000, 1100]
    acf_results = multi_lag_acf(returns, target_lags)
    all_results["acf_specific_lags"] = acf_results
    
    print(f"\n  Specific Lag ACF:")
    print(f"  {'Lag':>6}  {'ACF':>10}  {'Interpretation'}")
    print(f"  {'─'*6}  {'─'*10}  {'─'*30}")
    label_map = {
        1: "1 day", 5: "1 week", 21: "1 month", 63: "1 quarter",
        126: "6 months", 252: "1 yr (trading)", 370: "1 yr (calendar)",
        504: "2 yr (trading)", 741: "2 yr (calendar)", 1000: "~4 yr",
        1100: "~4.4 yr",
    }
    for lag in target_lags:
        val = acf_results.get(lag, np.nan)
        if not np.isnan(val):
            strength = "STRONG" if abs(val) > 0.1 else "moderate" if abs(val) > 0.05 else "weak"
            direction = "positive" if val > 0 else "negative"
            print(f"  {lag:6d}  {val:+10.6f}  {label_map.get(lag, '')} — {strength} {direction}")
    
    # ── 4. ACF Range Scan around 741 ────────────────────────────────
    print("\n▸ Scanning ACF across lag range 700–780 (around 741)...")
    range_scan_741 = acf_range_scan(returns, center=741, half_width=40)
    all_results["acf_range_741"] = range_scan_741
    
    if range_scan_741:
        peak = max(range_scan_741, key=lambda x: abs(x["acf"]))
        print(f"\n  Peak ACF in [700, 780] range:")
        print(f"    Lag={peak['lag']}, ACF={peak['acf']:+.6f}")
        print(f"\n  Full range scan:")
        print(f"  {'Lag':>6}  {'ACF':>10}")
        print(f"  {'─'*6}  {'─'*10}")
        for r in range_scan_741:
            marker = " ◄" if r["lag"] == peak["lag"] else ""
            star = " ★" if r["lag"] == 741 else ""
            print(f"  {r['lag']:6d}  {r['acf']:+10.6f}{star}{marker}")
    
    # ── 4b. ACF Range Scan around 370 ───────────────────────────────
    print("\n▸ Scanning ACF across lag range 340–400 (around 370)...")
    range_scan_370 = acf_range_scan(returns, center=370, half_width=30)
    all_results["acf_range_370"] = range_scan_370
    
    if range_scan_370:
        peak370 = max(range_scan_370, key=lambda x: abs(x["acf"]))
        print(f"\n  Peak ACF in [340, 400] range:")
        print(f"    Lag={peak370['lag']}, ACF={peak370['acf']:+.6f}")
        # Print just highlights
        print(f"\n  Top 5 by |ACF| in this range:")
        top5 = sorted(range_scan_370, key=lambda x: abs(x["acf"]), reverse=True)[:5]
        for r in top5:
            star = " ★" if r["lag"] == 370 else ""
            print(f"    Lag={r['lag']:4d}, ACF={r['acf']:+.6f}{star}")

    # ── 5. Reflection Scan at key offsets ───────────────────────────
    print("\n▸ Running reflection scan at key offsets...")
    reflection_offsets = [252, 370, 504, 741]
    reflection_results = {}
    
    for offset in reflection_offsets:
        print(f"\n  Offset = {offset} days ({label_map.get(offset, '')}):")
        result = reflection_scan(returns, offset, window=60)
        reflection_results[offset] = result
        
        if "error" not in result:
            print(f"    Forward:     mean={result['forward']['mean']:+.4f}, p95={result['forward']['p95']:.4f}")
            print(f"    Mirror:      mean={result['mirror']['mean']:+.4f}, p95={result['mirror']['p95']:.4f}")
            print(f"    Flip:        mean={result['flip']['mean']:+.4f}, p95={result['flip']['p95']:.4f}")
            print(f"    Mirror-Flip: mean={result['mirror_flip']['mean']:+.4f}, p95={result['mirror_flip']['p95']:.4f}")
            
            # Which mode is strongest?
            modes = {
                "forward": abs(result["forward"]["mean"]),
                "mirror": abs(result["mirror"]["mean"]),
                "flip": abs(result["flip"]["mean"]),
                "mirror_flip": abs(result["mirror_flip"]["mean"]),
            }
            strongest = max(modes, key=modes.get)
            print(f"    → Strongest mode: {strongest.upper()} ({modes[strongest]:.4f})")
        else:
            print(f"    {result['error']}")
    
    all_results["reflection"] = {str(k): v for k, v in reflection_results.items()}
    
    # ── 6. Blended Reflection at 741 ────────────────────────────────
    print("\n▸ Running blended reflection analysis at 741d offset...")
    blended = blended_reflection_scan(
        returns, cycle_period=741, window=60,
        blend_cadences=[2, 3, 4, 5, 7, 10, 14, 21]
    )
    all_results["blended_reflection_741"] = blended
    
    if "error" not in blended:
        print(f"\n  Cadence Stripping Results (offset=741d):")
        print(f"  {'Cadence':>10}  {'Mirror Mean':>12}  {'MirrorFlip Mean':>16}  {'Mirror p95':>11}  {'Windows':>8}")
        print(f"  {'─'*10}  {'─'*12}  {'─'*16}  {'─'*11}  {'─'*8}")
        for c, data in sorted(blended["results_by_cadence"].items()):
            label = data["label"]
            print(f"  {label:>10}  {data['mirror_mean']:+12.4f}  {data['mirror_flip_mean']:+16.4f}  {data['mirror_p95']:11.4f}  {data['n_windows']:8d}")
        
        if blended["best_cadence"]:
            bc = blended["best_cadence"]
            print(f"\n  → Best cadence for mirror detection: {bc['label']} (|mirror| = {abs(bc['mirror_mean']):.4f})")
    
    # ── 7. Multi-Cycle Phase Analysis ───────────────────────────────
    print("\n▸ Running multi-cycle phase analysis...")
    cycle_periods_to_test = [370, 504, 741]
    phase_results = {}
    
    for period in cycle_periods_to_test:
        print(f"\n  ── Cycle period = {period}d ──")
        result = multi_cycle_phase_analysis(returns, period)
        phase_results[period] = result
        
        if "error" in result:
            print(f"    {result['error']}")
            continue
        
        print(f"    Complete cycles: {result['n_complete_cycles']}, remainder: {result['remainder_days']}d ({result['remainder_pct']}%)")
        
        # Cycle summaries
        print(f"\n    {'Cycle':>6}  {'Days':>5}  {'Return':>8}  {'Drawup':>8}  {'Drawdown':>10}  {'Vol':>8}")
        print(f"    {'─'*6}  {'─'*5}  {'─'*8}  {'─'*8}  {'─'*10}  {'─'*8}")
        for cs in result["cycle_stats"]:
            print(f"    {cs['cycle']:6d}  {cs['n_days']:5d}  {cs['total_return']:+7.1f}%  {cs['max_drawup']:+7.1f}%  {cs['max_drawdown']:+9.1f}%  {cs['mean_daily_vol']:7.4f}%")
        
        # Inter-cycle correlations (full cycle only, skip halves for console)
        print(f"\n    Inter-cycle correlations:")
        print(f"    {'Pair':>20}  {'Forward':>8}  {'Mirror':>8}  {'Flip':>8}  {'MirFlip':>8}  {'Strongest'}")
        print(f"    {'─'*20}  {'─'*8}  {'─'*8}  {'─'*8}  {'─'*8}  {'─'*12}")
        for key, comp in result["comparisons"].items():
            if "_half" in key:
                continue  # skip half-cycle for console, still saved in JSON
            modes = {
                "forward": abs(comp["forward"]),
                "mirror": abs(comp["mirror"]),
                "flip": abs(comp["flip"]),
                "mirror_flip": abs(comp["mirror_flip"]),
            }
            strongest = max(modes, key=modes.get)
            print(f"    {key:>20}  {comp['forward']:+8.4f}  {comp['mirror']:+8.4f}  {comp['flip']:+8.4f}  {comp['mirror_flip']:+8.4f}  {strongest}")
    
    all_results["multi_cycle_phase"] = {str(k): v for k, v in phase_results.items()}
    
    # ── Save Results ────────────────────────────────────────────────
    out_path = RESULTS_DIR / "cycle_periodicity_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n\n  📁 Full results saved to {out_path.name}")
    
    # ── Summary ─────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"  SUMMARY")
    print(f"{'='*80}")
    print(f"  Data: {SYMBOL}, {all_results['n_days']} trading days ({all_results['date_range']})")
    print(f"  FFT Top-3 periods: {', '.join(f'{p['period_days']:.0f}d' for p in spectral['top_20_peaks'][:3])}")
    
    if range_scan_741:
        print(f"  ACF peak near 741: lag={peak['lag']}, ACF={peak['acf']:+.6f}")
    if range_scan_370:
        print(f"  ACF peak near 370: lag={peak370['lag']}, ACF={peak370['acf']:+.6f}")
    
    for offset in [741, 370]:
        r = reflection_results.get(offset, {})
        if "error" not in r:
            modes = {
                "forward": abs(r["forward"]["mean"]),
                "mirror": abs(r["mirror"]["mean"]),
                "flip": abs(r["flip"]["mean"]),
                "mirror_flip": abs(r["mirror_flip"]["mean"]),
            }
            strongest = max(modes, key=modes.get)
            print(f"  Reflection at {offset}d: strongest={strongest} ({modes[strongest]:.4f})")
    
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
