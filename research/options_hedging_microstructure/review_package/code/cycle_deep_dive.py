#!/usr/bin/env python3
"""
Cycle Periodicity Deep Dive — All Threads
==========================================
Comprehensive expansion of the initial scanner's four key findings.

Thread 1: FFT on multiple data series (price, volume, volatility, |returns|)
Thread 2: Rolling ACF heatmap — stability of the annual reversal signal
Thread 3: Mirror hypothesis — cycle-period sweep + multi-window analysis
Thread 4: Blended reflection — systematic cadence × offset sweep matrix
Thread 5: Multi-ticker panel — do other tickers show the same patterns?

Usage:
  cd /path/to/project
  source .venv/bin/activate
  python research/options_hedging_microstructure/cycle_deep_dive.py
"""
import sys
import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning)

# ── Paths ───────────────────────────────────────────────────────────────
POLYGON_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "raw" / "polygon" / "trades"
)
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

ENGINE_DIR = Path(__file__).parent.parent / "phase98_cluster_bridge"
sys.path.insert(0, str(ENGINE_DIR))
SYMBOL = "GME"

try:
    from temporal_convolution_engine import load_equity_day
except ImportError:
    def load_equity_day(symbol, date_str):
        p = POLYGON_DIR / f"symbol={symbol}" / f"date={date_str}" / "part-0.parquet"
        if not p.exists():
            return pd.DataFrame()
        return pd.read_parquet(p)


# ═══════════════════════════════════════════════════════════════════════
# SHARED UTILITIES
# ═══════════════════════════════════════════════════════════════════════
def build_daily_series(symbol: str, verbose: bool = True) -> pd.DataFrame:
    """Build daily series from tick data."""
    sym_dir = POLYGON_DIR / f"symbol={symbol}"
    if not sym_dir.exists():
        return pd.DataFrame()

    dates = sorted(d.name.split("=")[1] for d in sym_dir.glob("date=*"))
    if verbose:
        print(f"  {symbol}: {len(dates)} trading days ({dates[0]} → {dates[-1]})")

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
            "n_trades": len(prices),
            "vwap": np.mean(prices),
        })
        if verbose and (i + 1) % 500 == 0:
            print(f"    ... {i+1}/{len(dates)}")

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).set_index("date").sort_index()
    df["log_return"] = np.log(df["close"] / df["close"].shift(1))
    df["pct_return"] = df["close"].pct_change()
    df["abs_return"] = df["log_return"].abs()
    df["realized_vol"] = df["log_return"].rolling(21).std() * np.sqrt(252)
    df["log_volume"] = np.log1p(df["n_trades"])
    return df


def acf_at_lag(series: np.ndarray, lag: int) -> float:
    """Single-lag ACF, NaN-safe."""
    clean = series[~np.isnan(series)]
    n = len(clean)
    if lag >= n or n < 30:
        return np.nan
    mean = np.mean(clean)
    var = np.var(clean)
    if var < 1e-12:
        return np.nan
    return float(np.mean((clean[:n-lag] - mean) * (clean[lag:] - mean)) / var)


def rolling_acf(series: np.ndarray, lag: int, window: int = 252) -> np.ndarray:
    """Compute ACF at a given lag using a rolling window."""
    n = len(series)
    result = np.full(n, np.nan)
    for i in range(window + lag, n):
        chunk = series[i - window - lag: i]
        clean = chunk[~np.isnan(chunk)]
        if len(clean) < window // 2:
            continue
        m = np.mean(clean)
        v = np.var(clean)
        if v < 1e-12:
            continue
        nn = len(clean)
        if lag >= nn:
            continue
        result[i] = float(np.mean((clean[:nn-lag] - m) * (clean[lag:] - m)) / v)
    return result


# ═══════════════════════════════════════════════════════════════════════
# THREAD 1: FFT on multiple data series + rolling spectral windows
# ═══════════════════════════════════════════════════════════════════════
def thread1_fft_multi_series(daily: pd.DataFrame) -> dict:
    """FFT spectral analysis on returns, |returns|, volume, and volatility."""
    print("\n" + "="*80)
    print("  THREAD 1: FFT on Multiple Data Series")
    print("="*80)

    series_map = {
        "log_return": daily["log_return"].dropna().values,
        "abs_return": daily["abs_return"].dropna().values,
        "log_volume": daily["log_volume"].dropna().values,
        "realized_vol": daily["realized_vol"].dropna().values,
        "close_price": daily["close"].dropna().values,
    }

    # Also add detrended close (remove linear trend)
    close = daily["close"].dropna().values
    x = np.arange(len(close))
    slope, intercept = np.polyfit(x, close, 1)
    series_map["detrended_close"] = close - (slope * x + intercept)

    target_bands = [
        ("~63 (quarterly)", 55, 70),
        ("~125 (half-year)", 115, 135),
        ("~250 (1yr trading)", 240, 265),
        ("~370 (1yr calendar)", 355, 385),
        ("~500 (2yr trading)", 490, 520),
        ("~740 (2yr calendar)", 720, 760),
    ]

    all_results = {}

    for series_name, data in series_map.items():
        clean = data[~np.isnan(data)]
        n = len(clean)
        if n < 100:
            continue

        # Detrend and window
        clean = clean - np.mean(clean)
        window = np.hanning(n)
        fft = np.fft.rfft(clean * window)
        power = np.abs(fft) ** 2
        freqs = np.fft.rfftfreq(n, d=1.0)
        periods = np.where(freqs > 0, 1.0 / freqs, np.inf)

        mask = (periods > 5) & (periods < n / 2) & np.isfinite(periods)
        valid_power = power[mask]
        valid_periods = periods[mask]
        total = valid_power.sum()

        # Top 10 peaks
        sort_idx = np.argsort(-valid_power)[:10]
        top_peaks = [(round(float(valid_periods[i]), 1),
                       round(float(valid_power[i] / total * 100), 3))
                      for i in sort_idx]

        # Target bands
        bands = {}
        for name, lo, hi in target_bands:
            bm = (valid_periods >= lo) & (valid_periods <= hi)
            if bm.any():
                bp = valid_power[bm]
                bper = valid_periods[bm]
                pi = np.argmax(bp)
                bands[name] = {
                    "peak_period": round(float(bper[pi]), 1),
                    "pct": round(float(bp[pi] / total * 100), 3),
                }
            else:
                bands[name] = {"peak_period": None, "pct": 0}

        all_results[series_name] = {"n": n, "top_10": top_peaks, "bands": bands}

        # Console output
        print(f"\n  ── {series_name} (n={n}) ──")
        print(f"    Top 5: {', '.join(f'{p[0]:.0f}d ({p[1]:.2f}%)' for p in top_peaks[:5])}")
        for bname, bdata in bands.items():
            if bdata["pct"] > 0:
                print(f"    {bname}: {bdata['peak_period']:.0f}d @ {bdata['pct']:.3f}%")

    # ── Rolling spectral windows ──
    print(f"\n  ── Rolling Spectral Windows (504-day windows, stepped by 126d) ──")
    returns = daily["log_return"].dropna().values
    n = len(returns)
    win_size = 504
    step = 126
    rolling_results = []

    for start in range(0, n - win_size, step):
        chunk = returns[start:start + win_size]
        chunk = chunk - np.mean(chunk)
        w = np.hanning(len(chunk))
        fft = np.fft.rfft(chunk * w)
        power = np.abs(fft) ** 2
        freqs = np.fft.rfftfreq(len(chunk), d=1.0)
        periods = np.where(freqs > 0, 1.0 / freqs, np.inf)

        mask = (periods > 5) & (periods < len(chunk) / 2) & np.isfinite(periods)
        vp = power[mask]
        vper = periods[mask]
        total = vp.sum()

        if total < 1e-12:
            continue

        # Find peak in each target band
        window_bands = {}
        for bname, lo, hi in target_bands[:4]:  # only short bands fit in 504-day window
            bm = (vper >= lo) & (vper <= hi)
            if bm.any():
                bp = vp[bm]
                bper_arr = vper[bm]
                pi = np.argmax(bp)
                window_bands[bname] = round(float(bp[pi] / total * 100), 3)
            else:
                window_bands[bname] = 0

        # Top peak
        top_idx = np.argmax(vp)
        top_period = round(float(vper[top_idx]), 1)

        start_date = daily.index[start].strftime("%Y-%m-%d") if start < len(daily.index) else "?"
        end_idx = min(start + win_size, len(daily.index) - 1)
        end_date = daily.index[end_idx].strftime("%Y-%m-%d")

        rolling_results.append({
            "window": f"{start_date} → {end_date}",
            "top_period": top_period,
            "bands": window_bands,
        })
        print(f"    {start_date}→{end_date}: top={top_period:.0f}d, "
              f"quarterly={window_bands.get('~63 (quarterly)', 0):.2f}%, "
              f"annual={window_bands.get('~250 (1yr trading)', 0):.2f}%")

    all_results["rolling_spectral"] = rolling_results
    return all_results


# ═══════════════════════════════════════════════════════════════════════
# THREAD 2: Rolling ACF Heatmap — Annual Reversal Stability
# ═══════════════════════════════════════════════════════════════════════
def thread2_rolling_acf(daily: pd.DataFrame) -> dict:
    """Is the annual reversal signal stable across time?"""
    print("\n" + "="*80)
    print("  THREAD 2: Rolling ACF — Annual Reversal Stability")
    print("="*80)

    returns = daily["log_return"].values
    dates = daily.index

    # Test multiple lags with rolling windows
    test_lags = [1, 5, 21, 63, 126, 252, 355, 370, 504]
    window_sizes = [252, 504]

    all_results = {}

    for win_size in window_sizes:
        print(f"\n  ── Window = {win_size} trading days ──")
        lag_series = {}

        for lag in test_lags:
            if lag >= win_size:
                continue
            r_acf = rolling_acf(returns, lag, win_size)
            valid_mask = ~np.isnan(r_acf)
            valid_acf = r_acf[valid_mask]

            if len(valid_acf) < 10:
                continue

            # Split into regimes
            positive_pct = float(np.mean(valid_acf > 0) * 100)
            negative_pct = float(np.mean(valid_acf < 0) * 100)

            # Temporal stability: split into thirds
            third = len(valid_acf) // 3
            early = float(np.mean(valid_acf[:third]))
            mid = float(np.mean(valid_acf[third:2*third]))
            late = float(np.mean(valid_acf[2*third:]))

            result = {
                "lag": lag,
                "window": win_size,
                "mean": round(float(np.mean(valid_acf)), 6),
                "std": round(float(np.std(valid_acf)), 6),
                "positive_pct": round(positive_pct, 1),
                "negative_pct": round(negative_pct, 1),
                "early_third_mean": round(early, 6),
                "mid_third_mean": round(mid, 6),
                "late_third_mean": round(late, 6),
                "max": round(float(np.max(valid_acf)), 4),
                "min": round(float(np.min(valid_acf)), 4),
                "n_windows": len(valid_acf),
            }
            lag_series[lag] = result

            stability = "STABLE" if np.std([early, mid, late]) < abs(np.mean(valid_acf)) * 0.5 else "UNSTABLE"
            print(f"    Lag={lag:4d}: mean={result['mean']:+.4f}, "
                  f"neg={negative_pct:5.1f}%, "
                  f"early/mid/late={early:+.4f}/{mid:+.4f}/{late:+.4f} "
                  f"→ {stability}")

        all_results[f"window_{win_size}"] = lag_series

    # ── Deep dive on lag=355 rolling ──
    print(f"\n  ── Deep Dive: Lag=355, Window=252 — Time Epoch Analysis ──")
    r355 = rolling_acf(returns, 355, 252)
    valid_mask = ~np.isnan(r355)

    if valid_mask.any():
        # Create epoch analysis
        epochs = []
        valid_dates = dates[valid_mask]
        valid_vals = r355[valid_mask]

        # Group by year
        for year in range(valid_dates[0].year, valid_dates[-1].year + 1):
            year_mask = np.array([d.year == year for d in valid_dates])
            if year_mask.any():
                year_vals = valid_vals[year_mask]
                epochs.append({
                    "year": year,
                    "mean_acf": round(float(np.mean(year_vals)), 4),
                    "std_acf": round(float(np.std(year_vals)), 4),
                    "pct_negative": round(float(np.mean(year_vals < 0) * 100), 1),
                    "n": int(year_mask.sum()),
                })
                direction = "⬇" if float(np.mean(year_vals)) < 0 else "⬆"
                print(f"    {year}: ACF₃₅₅ = {float(np.mean(year_vals)):+.4f} "
                      f"(σ={float(np.std(year_vals)):.4f}, "
                      f"negative={float(np.mean(year_vals < 0)*100):.0f}%) {direction}")

        all_results["lag355_by_year"] = epochs

    return all_results


# ═══════════════════════════════════════════════════════════════════════
# THREAD 3: Mirror Hypothesis — Fine-Grained Sweep
# ═══════════════════════════════════════════════════════════════════════
def thread3_mirror_sweep(daily: pd.DataFrame) -> dict:
    """Sweep cycle periods from 200 to 800 and test mirror strength at each."""
    print("\n" + "="*80)
    print("  THREAD 3: Mirror Hypothesis — Cycle Period Sweep")
    print("="*80)

    returns = daily["log_return"].dropna().values
    n = len(returns)

    # ── Sweep cycle periods ──
    test_periods = list(range(200, 810, 10))
    windows_to_test = [30, 60, 120]

    all_results = {}

    for window in windows_to_test:
        print(f"\n  ── Window = {window}d ──")
        sweep_results = []

        for period in test_periods:
            if period + window >= n:
                continue

            n_windows = n - period - window
            forward_corrs = []
            mirror_corrs = []
            flip_corrs = []
            mflip_corrs = []

            for i in range(0, n_windows, max(1, window // 4)):
                a = returns[i:i+window]
                b = returns[i+period:i+period+window]
                if len(a) != window or len(b) != window:
                    continue

                a_s = np.std(a)
                b_s = np.std(b)
                if a_s < 1e-12 or b_s < 1e-12:
                    continue

                an = (a - a.mean()) / a_s
                bn = (b - b.mean()) / b_s

                forward_corrs.append(float(np.mean(an * bn)))
                mirror_corrs.append(float(np.mean(an * bn[::-1])))
                flip_corrs.append(float(np.mean(an * (-bn))))
                mflip_corrs.append(float(np.mean(an * (-bn[::-1]))))

            if not forward_corrs:
                continue

            fw = np.abs(np.mean(forward_corrs))
            mr = np.abs(np.mean(mirror_corrs))
            fl = np.abs(np.mean(flip_corrs))
            mf = np.abs(np.mean(mflip_corrs))
            modes = {"forward": fw, "mirror": mr, "flip": fl, "mirror_flip": mf}
            strongest = max(modes, key=modes.get)

            sweep_results.append({
                "period": period,
                "forward": round(float(np.mean(forward_corrs)), 5),
                "mirror": round(float(np.mean(mirror_corrs)), 5),
                "flip": round(float(np.mean(flip_corrs)), 5),
                "mirror_flip": round(float(np.mean(mflip_corrs)), 5),
                "strongest": strongest,
                "strongest_val": round(float(modes[strongest]), 5),
            })

        all_results[f"window_{window}"] = sweep_results

        # Find peaks
        if sweep_results:
            # Sort by |mirror|
            by_mirror = sorted(sweep_results, key=lambda x: abs(x["mirror"]), reverse=True)
            print(f"\n    Top 5 periods by |mirror| correlation:")
            for r in by_mirror[:5]:
                print(f"      Period={r['period']:4d}d: mirror={r['mirror']:+.5f}, "
                      f"forward={r['forward']:+.5f}, strongest={r['strongest']}")

            # Sort by |mirror_flip|
            by_mflip = sorted(sweep_results, key=lambda x: abs(x["mirror_flip"]), reverse=True)
            print(f"\n    Top 5 periods by |mirror_flip| correlation:")
            for r in by_mflip[:5]:
                print(f"      Period={r['period']:4d}d: mirror_flip={r['mirror_flip']:+.5f}, "
                      f"forward={r['forward']:+.5f}, strongest={r['strongest']}")

            # How many are mirror-dominant?
            mirror_count = sum(1 for r in sweep_results if r["strongest"] in ("mirror", "mirror_flip"))
            forward_count = sum(1 for r in sweep_results if r["strongest"] in ("forward", "flip"))
            print(f"\n    Overall: {mirror_count} mirror-dominant, {forward_count} forward-dominant out of {len(sweep_results)} periods")

    # ── Statistical significance test ──
    print(f"\n  ── Statistical Significance: Monte Carlo Shuffled Baseline ──")
    n_shuffles = 200
    window = 60
    test_offsets = [252, 355, 504, 711]

    significance_results = {}

    for offset in test_offsets:
        if offset + window >= n:
            continue

        # Real mirror correlation
        real_mirrors = []
        n_w = n - offset - window
        for i in range(0, n_w, window // 4):
            a = returns[i:i+window]
            b = returns[i+offset:i+offset+window]
            if len(a) != window or len(b) != window:
                continue
            a_s, b_s = np.std(a), np.std(b)
            if a_s < 1e-12 or b_s < 1e-12:
                continue
            an = (a - a.mean()) / a_s
            bn = (b - b.mean()) / b_s
            real_mirrors.append(float(np.mean(an * bn[::-1])))

        real_mean = np.mean(real_mirrors) if real_mirrors else 0

        # Shuffle test
        shuffle_means = []
        for _ in range(n_shuffles):
            shuffled = returns.copy()
            np.random.shuffle(shuffled)
            shuf_mirrors = []
            for i in range(0, min(n_w, 500), window // 4):
                a = shuffled[i:i+window]
                b = shuffled[i+offset:i+offset+window]
                if len(a) != window or len(b) != window:
                    continue
                a_s, b_s = np.std(a), np.std(b)
                if a_s < 1e-12 or b_s < 1e-12:
                    continue
                an = (a - a.mean()) / a_s
                bn = (b - b.mean()) / b_s
                shuf_mirrors.append(float(np.mean(an * bn[::-1])))
            if shuf_mirrors:
                shuffle_means.append(np.mean(shuf_mirrors))

        if shuffle_means:
            null_mean = np.mean(shuffle_means)
            null_std = np.std(shuffle_means)
            z_score = (real_mean - null_mean) / null_std if null_std > 0 else 0
            p_value = 2 * (1 - min(0.9999, abs(z_score) / 4))  # rough p

            significance_results[offset] = {
                "real_mirror_mean": round(float(real_mean), 5),
                "null_mean": round(float(null_mean), 5),
                "null_std": round(float(null_std), 5),
                "z_score": round(float(z_score), 3),
                "significant": abs(z_score) > 1.96,
            }
            sig = "✓ SIGNIFICANT" if abs(z_score) > 1.96 else "✗ not significant"
            print(f"    Offset={offset:4d}: real={real_mean:+.5f}, null={null_mean:+.5f}±{null_std:.5f}, "
                  f"z={z_score:+.3f} {sig}")

    all_results["significance"] = significance_results
    return all_results


# ═══════════════════════════════════════════════════════════════════════
# THREAD 4: Blended Reflection — Cadence × Offset Matrix
# ═══════════════════════════════════════════════════════════════════════
def thread4_blended_sweep(daily: pd.DataFrame) -> dict:
    """Systematic sweep of cadence × offset combinations."""
    print("\n" + "="*80)
    print("  THREAD 4: Blended Reflection — Cadence × Offset Sweep")
    print("="*80)

    returns = daily["log_return"].dropna().values
    n = len(returns)
    window = 60

    offsets = [252, 355, 370, 504, 600, 700, 741, 800]
    cadences = [1, 2, 3, 4, 5, 6, 7, 10, 14, 21]

    matrix = {}

    for offset in offsets:
        if offset + window >= n:
            continue

        n_w = n - offset - window
        cadence_results = {}

        for cadence in cadences:
            mirror_corrs = []
            mflip_corrs = []

            for i in range(0, n_w, window // 4):
                a_full = returns[i:i+window]
                b_full = returns[i+offset:i+offset+window]
                if len(a_full) != window or len(b_full) != window:
                    continue

                a = a_full[::cadence]
                b = b_full[::cadence]
                ml = min(len(a), len(b))
                if ml < 5:
                    continue
                a, b = a[:ml], b[:ml]

                a_s, b_s = np.std(a), np.std(b)
                if a_s < 1e-12 or b_s < 1e-12:
                    continue

                an = (a - a.mean()) / a_s
                bn = (b - b.mean()) / b_s
                mirror_corrs.append(float(np.mean(an * bn[::-1])))
                mflip_corrs.append(float(np.mean(an * (-bn[::-1]))))

            if mirror_corrs:
                cadence_results[cadence] = {
                    "mirror_mean": round(float(np.mean(mirror_corrs)), 4),
                    "mflip_mean": round(float(np.mean(mflip_corrs)), 4),
                    "max_abs": round(float(max(abs(np.mean(mirror_corrs)), abs(np.mean(mflip_corrs)))), 4),
                }

        matrix[offset] = cadence_results

    # Print matrix
    print(f"\n  Mirror Mean Matrix (offset × cadence):")
    print(f"  {'Offset':>6}", end="")
    for c in cadences:
        label = "raw" if c == 1 else f"e{c}th"
        print(f"  {label:>6}", end="")
    print()
    print(f"  {'─'*6}", end="")
    for _ in cadences:
        print(f"  {'─'*6}", end="")
    print()

    for offset in offsets:
        if offset not in matrix:
            continue
        print(f"  {offset:6d}", end="")
        for c in cadences:
            val = matrix[offset].get(c, {}).get("mirror_mean", 0)
            # Highlight strong signals
            if abs(val) > 0.03:
                print(f"  {val:+6.3f}*", end="")
            else:
                print(f"  {val:+6.3f} ", end="")
        print()

    # Find the global peak
    best = {"offset": 0, "cadence": 0, "val": 0}
    for offset, cr in matrix.items():
        for cadence, data in cr.items():
            if data["max_abs"] > abs(best["val"]):
                best = {"offset": offset, "cadence": cadence, "val": data["max_abs"],
                        "mirror": data["mirror_mean"], "mflip": data["mflip_mean"]}

    print(f"\n  → Global peak: offset={best['offset']}d, cadence=every-{best['cadence']}th, "
          f"mirror={best.get('mirror', 0):+.4f}, mirror_flip={best.get('mflip', 0):+.4f}")

    return {"matrix": {str(k): v for k, v in matrix.items()}, "best": best}


# ═══════════════════════════════════════════════════════════════════════
# THREAD 5: Multi-Ticker Panel
# ═══════════════════════════════════════════════════════════════════════
def thread5_panel_scan() -> dict:
    """Run key tests across all available tickers."""
    print("\n" + "="*80)
    print("  THREAD 5: Multi-Ticker Panel Scan")
    print("="*80)

    tickers = sorted(
        d.name.split("=")[1]
        for d in POLYGON_DIR.glob("symbol=*")
        if d.is_dir()
    )
    print(f"  Found {len(tickers)} tickers")

    panel_results = {}
    panel_summary = []

    for symbol in tickers:
        print(f"\n  ── {symbol} ──")
        daily = build_daily_series(symbol, verbose=False)
        if daily.empty or len(daily) < 400:
            print(f"    ⚠ Insufficient data ({len(daily)} days)")
            continue

        returns = daily["log_return"].dropna().values
        n = len(returns)

        # Key tests
        acf_355 = acf_at_lag(returns, 355) if n > 400 else np.nan
        acf_252 = acf_at_lag(returns, 252) if n > 300 else np.nan
        acf_504 = acf_at_lag(returns, 504) if n > 550 else np.nan

        # Mirror test at 504d offset (need enough data)
        mirror_504 = np.nan
        mirror_flip_504 = np.nan
        if n > 564:
            window = 60
            mirrors = []
            mflips = []
            for i in range(0, n - 504 - window, window // 4):
                a = returns[i:i+window]
                b = returns[i+504:i+504+window]
                if len(a) != window or len(b) != window:
                    continue
                a_s, b_s = np.std(a), np.std(b)
                if a_s < 1e-12 or b_s < 1e-12:
                    continue
                an = (a - a.mean()) / a_s
                bn = (b - b.mean()) / b_s
                mirrors.append(float(np.mean(an * bn[::-1])))
                mflips.append(float(np.mean(an * (-bn[::-1]))))
            if mirrors:
                mirror_504 = float(np.mean(mirrors))
                mirror_flip_504 = float(np.mean(mflips))

        # Blended mirror at best cadence (every-5th) for 504d
        blended_mirror = np.nan
        if n > 564:
            mirrors = []
            for i in range(0, n - 504 - window, window // 4):
                a = returns[i:i+window:5]
                b = returns[i+504:i+504+window:5]
                ml = min(len(a), len(b))
                if ml < 5:
                    continue
                a, b = a[:ml], b[:ml]
                a_s, b_s = np.std(a), np.std(b)
                if a_s < 1e-12 or b_s < 1e-12:
                    continue
                an = (a - a.mean()) / a_s
                bn = (b - b.mean()) / b_s
                mirrors.append(float(np.mean(an * bn[::-1])))
            if mirrors:
                blended_mirror = float(np.mean(mirrors))

        row = {
            "symbol": symbol,
            "n_days": n,
            "date_range": f"{daily.index[0].date()} → {daily.index[-1].date()}",
            "acf_252": round(float(acf_252), 5) if not np.isnan(acf_252) else None,
            "acf_355": round(float(acf_355), 5) if not np.isnan(acf_355) else None,
            "acf_504": round(float(acf_504), 5) if not np.isnan(acf_504) else None,
            "mirror_504_raw": round(float(mirror_504), 5) if not np.isnan(mirror_504) else None,
            "mirror_504_e5": round(float(blended_mirror), 5) if not np.isnan(blended_mirror) else None,
        }
        panel_results[symbol] = row
        panel_summary.append(row)

        print(f"    n={n}, ACF₂₅₂={row['acf_252']}, ACF₃₅₅={row['acf_355']}, "
              f"ACF₅₀₄={row['acf_504']}, mirror₅₀₄={row['mirror_504_raw']}, "
              f"blended={row['mirror_504_e5']}")

    # Summary statistics
    print(f"\n  {'='*70}")
    print(f"  Panel Summary ({len(panel_summary)} tickers)")
    print(f"  {'='*70}")

    def panel_stat(key):
        vals = [r[key] for r in panel_summary if r[key] is not None]
        if not vals:
            return "N/A"
        arr = np.array(vals)
        neg_pct = np.mean(arr < 0) * 100
        return (f"mean={np.mean(arr):+.5f}, median={np.median(arr):+.5f}, "
                f"negative={neg_pct:.0f}%, n={len(vals)}")

    for key in ["acf_252", "acf_355", "acf_504", "mirror_504_raw", "mirror_504_e5"]:
        print(f"  {key:>18}: {panel_stat(key)}")

    # Rank by |ACF₃₅₅|
    ranked = sorted([r for r in panel_summary if r["acf_355"] is not None],
                    key=lambda x: abs(x["acf_355"]), reverse=True)
    if ranked:
        print(f"\n  Top 10 tickers by |ACF₃₅₅|:")
        for r in ranked[:10]:
            print(f"    {r['symbol']:6s}: ACF₃₅₅={r['acf_355']:+.5f}, "
                  f"mirror₅₀₄={r['mirror_504_raw']}, blended={r['mirror_504_e5']}")

    return {"panel": panel_results, "summary": panel_summary}


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════
def main():
    print(f"\n{'#'*80}")
    print(f"  CYCLE PERIODICITY DEEP DIVE — {SYMBOL}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*80}\n")

    # Build daily series
    print("▸ Building daily series for GME...")
    daily = build_daily_series(SYMBOL)

    all_results = {
        "symbol": SYMBOL,
        "n_days": len(daily),
        "date_range": f"{daily.index[0].date()} → {daily.index[-1].date()}",
        "timestamp": datetime.now().isoformat(),
    }

    # Thread 1: FFT multi-series
    all_results["thread1_fft"] = thread1_fft_multi_series(daily)

    # Thread 2: Rolling ACF
    all_results["thread2_rolling_acf"] = thread2_rolling_acf(daily)

    # Thread 3: Mirror sweep
    all_results["thread3_mirror"] = thread3_mirror_sweep(daily)

    # Thread 4: Blended sweep
    all_results["thread4_blended"] = thread4_blended_sweep(daily)

    # Thread 5: Multi-ticker panel
    all_results["thread5_panel"] = thread5_panel_scan()

    # Save
    out_path = RESULTS_DIR / "cycle_deep_dive_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n\n  📁 Full results saved to {out_path.name}")


if __name__ == "__main__":
    main()
