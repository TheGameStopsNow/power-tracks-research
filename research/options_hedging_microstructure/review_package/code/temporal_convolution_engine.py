#!/usr/bin/env python3
"""
Temporal Convolution Engine — Phase 99 Core Analysis
=====================================================
Detects the temporal echo structure created by options hedging mechanics.

Core hypothesis: Each DTE bucket in the options chain acts as a delay line,
re-emitting past price action at timescales proportional to the DTE.
The "twist" happens because unwinding creates reversed echoes.

Analysis pipeline:
  1. Rolling autocorrelation shift detection (before vs after options)
  2. DTE-stratified cross-day lag analysis (the convolution kernel)
  3. Hurst exponent regime detection (memory injection by options)
  4. Reverse reconstruction: predict past from current chain
  5. Echo cascade tracking: Move → Echo → New Move chain
"""

from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.signal import correlate
from scipy.stats import norm as sp_norm

# Import from sibling modules
sys.path.insert(0, str(Path(__file__).parent))
from delta_hedge_pipeline import (
    compute_delta_exposure,
    add_expiration_and_gamma,
    classify_expiration,
    EXP_BUCKETS,
    EXP_COLORS,
    bs_delta_vectorized,
)
from ipo_origin_scanner import (
    get_stock_trade_dates,
    get_option_trade_dates,
    get_option_expirations,
    fetch_stock_trades_day,
    fetch_option_trades_bulk,
    THETA_EQUITY_DIR,
    THETA_OPTS_DIR,
)


# ============================================================================
# Data Loaders (ThetaData-native, not Polygon)
# ============================================================================

def load_equity_day(symbol: str, date_str: str) -> pd.DataFrame:
    """Load equity trades for a single day from local ThetaData cache."""
    date_clean = date_str.replace("-", "")
    date_hyphen = f"{date_clean[:4]}-{date_clean[4:6]}-{date_clean[6:8]}"

    # Try both formats
    for fmt in [date_hyphen, date_clean]:
        for base in [THETA_EQUITY_DIR, Path(__file__).parent.parent.parent / "data" / "raw" / "polygon" / "trades"]:
            for prefix in [f"symbol={symbol}", f"symbol={symbol.upper()}"]:
                path = base / prefix / f"date={fmt}"
                if path.exists():
                    frames = []
                    for f in path.glob("*.parquet"):
                        try:
                            frames.append(pd.read_parquet(f))
                        except Exception:
                            continue
                    if frames:
                        df = pd.concat(frames, ignore_index=True)
                        df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", utc=True)
                        df["ts"] = df["timestamp"]
                        return df.sort_values("timestamp").reset_index(drop=True)
    return pd.DataFrame()


def load_options_day(symbol: str, date_str: str) -> pd.DataFrame:
    """Load option trades for a single day from local ThetaData cache."""
    date_clean = date_str.replace("-", "")
    path = THETA_OPTS_DIR / f"root={symbol}" / f"date={date_clean}"
    if not path.exists():
        return pd.DataFrame()

    frames = []
    for f in path.glob("*.parquet"):
        try:
            frames.append(pd.read_parquet(f))
        except Exception:
            continue
    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", utc=True)
    if "strike" in df.columns:
        df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
    return df


def get_available_equity_dates(symbol: str) -> list[str]:
    """List locally cached equity trading days (normalized to YYYYMMDD)."""
    dates = set()
    for base in [THETA_EQUITY_DIR, Path(__file__).parent.parent.parent / "data" / "raw" / "polygon" / "trades"]:
        path = base / f"symbol={symbol}"
        if path.exists():
            for d in path.glob("date=*"):
                raw = d.name.split("=")[1]
                # Normalize to YYYYMMDD
                dates.add(raw.replace("-", ""))
    return sorted(dates)


def get_available_options_dates(symbol: str) -> list[str]:
    """List locally cached option trading days."""
    path = THETA_OPTS_DIR / f"root={symbol}"
    if not path.exists():
        return []
    return sorted(d.name.split("=")[1] for d in path.glob("date=*"))


# ============================================================================
# 1. Autocorrelation Shift Detection
# ============================================================================

def compute_return_autocorrelation(
    prices: pd.Series,
    timestamps: pd.Series,
    interval_sec: float = 300.0,
    max_lag: int = 50,
) -> np.ndarray:
    """
    Compute autocorrelation of returns at a given bar interval.

    Returns array of ACF values from lag 0 to max_lag.
    """
    # Resample to regular intervals
    df = pd.DataFrame({"ts": timestamps, "price": prices}).set_index("ts")
    bars = df.resample(f"{int(interval_sec)}s").last().dropna()
    returns = bars["price"].pct_change().dropna().values

    if len(returns) < max_lag + 10:
        return np.zeros(max_lag + 1)

    # Normalized autocorrelation
    n = len(returns)
    mean = returns.mean()
    var = np.var(returns)
    if var < 1e-12:
        return np.zeros(max_lag + 1)

    acf = np.zeros(max_lag + 1)
    for lag in range(max_lag + 1):
        acf[lag] = np.mean((returns[:n-lag] - mean) * (returns[lag:] - mean)) / var

    return acf


def detect_acf_shift(
    symbol: str,
    equity_dates: list[str],
    options_start_date: str,
    interval_sec: float = 300.0,
    max_lag: int = 50,
    window_days: int = 20,
) -> dict:
    """
    Compare autocorrelation structure before vs after options listing.

    Returns dict with 'before_acf', 'after_acf', 'shift' arrays.
    """
    # Normalize the options start date
    try:
        opts_dt = datetime.strptime(options_start_date, "%Y-%m-%d")
    except ValueError:
        opts_dt = datetime.strptime(options_start_date, "%Y%m%d")

    before_acfs = []
    after_acfs = []

    for date in equity_dates:
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            dt = datetime.strptime(date, "%Y%m%d")

        eq = load_equity_day(symbol, date)
        if eq.empty or len(eq) < 100:
            continue

        acf = compute_return_autocorrelation(eq["price"], eq["ts"], interval_sec, max_lag)

        if dt < opts_dt:
            before_acfs.append(acf)
        else:
            after_acfs.append(acf)

        # Limit sample size
        if len(before_acfs) >= window_days and len(after_acfs) >= window_days:
            break

    result = {
        "before_acf": np.mean(before_acfs, axis=0) if before_acfs else np.zeros(max_lag + 1),
        "after_acf": np.mean(after_acfs, axis=0) if after_acfs else np.zeros(max_lag + 1),
        "n_before": len(before_acfs),
        "n_after": len(after_acfs),
    }
    result["shift"] = result["after_acf"] - result["before_acf"]

    return result


# ============================================================================
# 2. DTE-Stratified Cross-Day Echo Kernel
# ============================================================================

def time_bin_profile(
    timestamps: pd.Series,
    values: pd.Series,
    n_bins: int = 128,
    agg: str = "sum",
) -> np.ndarray:
    """Bin a time series into n_bins equal intervals."""
    ts = pd.to_datetime(timestamps, utc=True)
    t_min, t_max = ts.min(), ts.max()
    span = (t_max - t_min).total_seconds()
    if span <= 0:
        return np.zeros(n_bins)

    t_norm = (ts - t_min).dt.total_seconds() / span
    bins = np.clip((t_norm * n_bins).astype(int), 0, n_bins - 1)

    profile = np.zeros(n_bins)
    vals = values.values

    if agg == "sum":
        np.add.at(profile, bins.values, vals)
    elif agg == "count":
        np.add.at(profile, bins.values, np.ones(len(vals)))
    elif agg == "mean":
        counts = np.zeros(n_bins)
        np.add.at(profile, bins.values, vals)
        np.add.at(counts, bins.values, np.ones(len(vals)))
        profile = np.divide(profile, counts, where=counts > 0, out=profile)

    return profile


def zncc_1d(a: np.ndarray, b: np.ndarray) -> float:
    """Zero-mean normalized cross-correlation."""
    a = a - a.mean()
    b = b - b.mean()
    norm = np.sqrt(np.sum(a**2) * np.sum(b**2))
    if norm < 1e-12:
        return 0.0
    return float(np.sum(a * b) / norm)


def cross_correlate_profiles(
    profile_a: np.ndarray,
    profile_b: np.ndarray,
    max_lag: int = 50,
) -> tuple[np.ndarray, np.ndarray]:
    """Cross-correlate two profiles with normalization."""
    a = profile_a - profile_a.mean()
    b = profile_b - profile_b.mean()

    norm = np.sqrt(np.sum(a**2) * np.sum(b**2))
    if norm < 1e-12:
        lags = np.arange(-max_lag, max_lag + 1)
        return lags, np.zeros(len(lags))

    full_corr = correlate(a, b, mode="full")
    full_corr /= norm
    mid = len(full_corr) // 2
    start = max(0, mid - max_lag)
    end = min(len(full_corr), mid + max_lag + 1)

    lags = np.arange(start - mid, end - mid)
    return lags, full_corr[start:end]


def compute_rolling_echo_kernel(
    symbol: str,
    n_bins: int = 64,
    max_lag_bins: int = 30,
    fixed_iv: float = 0.80,
    day_offsets: list[int] | None = None,
    max_days: int = 200,
    progress_callback=None,
) -> dict:
    """
    The core temporal convolution detector.

    For each equity day, cross-correlate its volume profile against the
    hedge profile from day+offset, stratified by DTE bucket.

    This reveals the "echo kernel" — at what lag does each DTE bucket's
    hedging activity best predict equity volume?

    Returns
    -------
    dict with:
        'kernel': DataFrame — offset × DTE bucket correlation matrix
        'detail': list of per-day-pair results
        'equity_dates': list
        'options_dates': list
    """
    if day_offsets is None:
        day_offsets = [-30, -14, -7, -5, -3, -2, -1, 0, 1, 2, 3, 5, 7, 14, 30]

    eq_dates = get_available_equity_dates(symbol)
    opt_dates = get_available_options_dates(symbol)

    if not eq_dates or not opt_dates:
        return {"kernel": pd.DataFrame(), "detail": [], "equity_dates": eq_dates, "options_dates": opt_dates}

    # Use sorted date indices for offset lookup
    all_dates_sorted = sorted(set(eq_dates) | set(opt_dates))
    date_index = {d: i for i, d in enumerate(all_dates_sorted)}

    detail = []
    kernel_data = {offset: {bucket: [] for bucket in EXP_BUCKETS + ["ALL"]} for offset in day_offsets}

    target_eq_dates = eq_dates[:max_days]
    total = len(target_eq_dates)

    for i, eq_date in enumerate(target_eq_dates):
        eq_df = load_equity_day(symbol, eq_date)
        if eq_df.empty or len(eq_df) < 50:
            continue

        eq_profile = time_bin_profile(eq_df["ts"], eq_df["size"], n_bins, agg="sum")

        eq_idx = date_index.get(eq_date)
        if eq_idx is None:
            continue

        for offset in day_offsets:
            target_idx = eq_idx + offset
            if target_idx < 0 or target_idx >= len(all_dates_sorted):
                continue
            opt_date = all_dates_sorted[target_idx]

            opts_df = load_options_day(symbol, opt_date)
            if opts_df.empty or len(opts_df) < 10:
                continue

            # Need equity on the options date for delta computation
            opts_eq = load_equity_day(symbol, opt_date)
            if opts_eq.empty:
                continue

            try:
                delta_df = compute_delta_exposure(opts_df, opts_eq, opt_date, fixed_iv=fixed_iv)
                if delta_df.empty:
                    continue
                enriched = add_expiration_and_gamma(delta_df)
            except Exception:
                continue

            # Cross-correlate by DTE bucket
            for bucket in EXP_BUCKETS:
                sub = enriched[enriched["exp_class"] == bucket]
                if len(sub) < 5:
                    continue
                hedge_profile = time_bin_profile(sub["ts"], sub["abs_hedge"], n_bins, agg="sum")
                zncc = zncc_1d(hedge_profile, eq_profile)
                kernel_data[offset][bucket].append(zncc)

            # ALL buckets combined
            all_profile = time_bin_profile(enriched["ts"], enriched["abs_hedge"], n_bins, agg="sum")
            all_zncc = zncc_1d(all_profile, eq_profile)
            kernel_data[offset]["ALL"].append(all_zncc)

            detail.append({
                "eq_date": eq_date,
                "opt_date": opt_date,
                "offset": offset,
                "zncc_all": all_zncc,
            })

        if progress_callback:
            progress_callback((i + 1) / total)

    # Build kernel matrix
    rows = []
    for offset in day_offsets:
        row = {"offset": offset}
        for bucket in EXP_BUCKETS + ["ALL"]:
            vals = kernel_data[offset][bucket]
            row[bucket] = float(np.mean(vals)) if vals else np.nan
            row[f"{bucket}_n"] = len(vals)
        rows.append(row)

    kernel_df = pd.DataFrame(rows).set_index("offset")

    return {
        "kernel": kernel_df,
        "detail": detail,
        "equity_dates": eq_dates,
        "options_dates": opt_dates,
    }


# ============================================================================
# 3. Hurst Exponent / Memory Detection
# ============================================================================

def hurst_exponent(ts: np.ndarray, max_lag: int = 100) -> float:
    """
    Estimate Hurst exponent using R/S analysis.

    H > 0.5 → trend-following (momentum, hedge amplification)
    H = 0.5 → random walk
    H < 0.5 → mean-reverting (dampening, gamma hedging)
    """
    n = len(ts)
    if n < max_lag + 10:
        return 0.5

    lags = range(2, min(max_lag, n // 4))
    rs_values = []
    lag_values = []

    for lag in lags:
        subseries = [ts[i:i+lag] for i in range(0, n - lag, lag)]
        if len(subseries) < 2:
            continue

        rs_list = []
        for sub in subseries:
            if len(sub) < 2:
                continue
            mean = sub.mean()
            cumdev = np.cumsum(sub - mean)
            R = cumdev.max() - cumdev.min()
            S = sub.std()
            if S > 0:
                rs_list.append(R / S)

        if rs_list:
            rs_values.append(np.mean(rs_list))
            lag_values.append(lag)

    if len(lag_values) < 3:
        return 0.5

    # Fit log-log regression
    log_lags = np.log(lag_values)
    log_rs = np.log(rs_values)

    try:
        H = np.polyfit(log_lags, log_rs, 1)[0]
    except (np.linalg.LinAlgError, ValueError):
        H = 0.5

    return float(np.clip(H, 0, 1))


def rolling_hurst(
    symbol: str,
    dates: list[str],
    interval_sec: float = 60.0,
    window_size: int = 20,
    step: int = 5,
) -> pd.DataFrame:
    """
    Compute rolling Hurst exponent over trading days.

    Returns DataFrame with columns: center_date, H, n_days
    """
    # Collect return series per day
    daily_returns = {}
    for date in dates:
        eq = load_equity_day(symbol, date)
        if eq.empty or len(eq) < 50:
            continue

        df = pd.DataFrame({"ts": eq["ts"], "price": eq["price"]}).set_index("ts")
        bars = df.resample(f"{int(interval_sec)}s").last().dropna()
        rets = bars["price"].pct_change().dropna().values
        if len(rets) > 10:
            daily_returns[date] = rets

    sorted_dates = sorted(daily_returns.keys())
    if len(sorted_dates) < window_size:
        return pd.DataFrame()

    results = []
    for i in range(0, len(sorted_dates) - window_size + 1, step):
        window_dates = sorted_dates[i:i+window_size]
        combined = np.concatenate([daily_returns[d] for d in window_dates])
        H = hurst_exponent(combined)
        results.append({
            "center_date": window_dates[window_size // 2],
            "window_start": window_dates[0],
            "window_end": window_dates[-1],
            "H": H,
            "n_points": len(combined),
        })

    return pd.DataFrame(results)


# ============================================================================
# 4. Reverse Reconstruction: Predict Past from Current Chain
# ============================================================================

def reconstruct_past_from_chain(
    symbol: str,
    chain_date: str,
    lookback_days: list[int] | None = None,
    n_bins: int = 64,
    fixed_iv: float = 0.80,
) -> dict:
    """
    Can the current options chain predict past price moves?

    For a given date's options positioning, compute the implied
    hedge pressure profile, then compare against equity profiles
    from past N days.

    If the chain "remembers" past moves, correlations with past
    days should be unexpectedly high.
    """
    if lookback_days is None:
        lookback_days = [1, 2, 3, 5, 7, 10, 14, 21, 30, 45, 60]

    # Load current day's options and compute hedge profile
    opts = load_options_day(symbol, chain_date)
    eq_chain_day = load_equity_day(symbol, chain_date)
    if opts.empty or eq_chain_day.empty:
        return {"error": "No data for chain date"}

    try:
        delta_df = compute_delta_exposure(opts, eq_chain_day, chain_date, fixed_iv=fixed_iv)
        enriched = add_expiration_and_gamma(delta_df)
    except Exception as e:
        return {"error": str(e)}

    # Compute the "implied" profile from current chain
    chain_profile = time_bin_profile(enriched["ts"], enriched["abs_hedge"], n_bins, agg="sum")

    # Compute per-DTE-bucket profiles
    bucket_profiles = {}
    for bucket in EXP_BUCKETS:
        sub = enriched[enriched["exp_class"] == bucket]
        if len(sub) >= 5:
            bucket_profiles[bucket] = time_bin_profile(sub["ts"], sub["abs_hedge"], n_bins, agg="sum")

    # Get date list for lookback
    all_dates = sorted(get_available_equity_dates(symbol))
    try:
        chain_idx = all_dates.index(chain_date.replace("-", ""))
    except ValueError:
        try:
            chain_idx = all_dates.index(chain_date)
        except ValueError:
            return {"error": f"Chain date not in available dates"}

    results = {
        "chain_date": chain_date,
        "chain_profile": chain_profile.tolist(),
        "lookback_results": [],
    }

    for lb in lookback_days:
        target_idx = chain_idx - lb
        if target_idx < 0:
            continue

        past_date = all_dates[target_idx]
        past_eq = load_equity_day(symbol, past_date)
        if past_eq.empty or len(past_eq) < 50:
            continue

        past_profile = time_bin_profile(past_eq["ts"], past_eq["size"], n_bins, agg="sum")

        # Compare chain profile vs past equity profile
        zncc_all = zncc_1d(chain_profile, past_profile)

        # Per-bucket comparison
        bucket_zncc = {}
        for bucket, bp in bucket_profiles.items():
            bucket_zncc[bucket] = zncc_1d(bp, past_profile)

        results["lookback_results"].append({
            "lookback_days": lb,
            "past_date": past_date,
            "zncc_all": zncc_all,
            "bucket_zncc": bucket_zncc,
        })

    return results


# ============================================================================
# 5. Echo Cascade Tracker
# ============================================================================

def detect_echo_events(
    symbol: str,
    dates: list[str],
    correlation_threshold: float = 0.4,
    n_bins: int = 64,
    lag_range: tuple[int, int] = (3, 30),
) -> list[dict]:
    """
    Find pairs of days where the equity profile shows high correlation
    (potential echo of a past move).

    Returns list of detected echo events with metadata.
    """
    # Precompute daily equity profiles
    profiles = {}
    for date in dates:
        eq = load_equity_day(symbol, date)
        if eq.empty or len(eq) < 50:
            continue
        profiles[date] = time_bin_profile(eq["ts"], eq["size"], n_bins, agg="sum")

    profile_dates = sorted(profiles.keys())
    echoes = []

    for i, date_a in enumerate(profile_dates):
        for j in range(i + lag_range[0], min(i + lag_range[1], len(profile_dates))):
            date_b = profile_dates[j]
            prof_a = profiles[date_a]
            prof_b = profiles[date_b]

            # Check both normal and reversed correlation
            zncc_normal = zncc_1d(prof_a, prof_b)
            zncc_reversed = zncc_1d(prof_a, prof_b[::-1])

            if abs(zncc_normal) >= correlation_threshold or abs(zncc_reversed) >= correlation_threshold:
                echoes.append({
                    "origin_date": date_a,
                    "echo_date": date_b,
                    "lag_days": j - i,
                    "zncc_normal": zncc_normal,
                    "zncc_reversed": zncc_reversed,
                    "is_reversed": abs(zncc_reversed) > abs(zncc_normal),
                    "best_zncc": max(abs(zncc_normal), abs(zncc_reversed)),
                })

    # Sort by strength
    echoes.sort(key=lambda e: e["best_zncc"], reverse=True)
    return echoes


def track_echo_cascade(
    symbol: str,
    seed_date: str,
    max_depth: int = 5,
    correlation_threshold: float = 0.35,
    n_bins: int = 64,
    search_window: int = 60,
) -> list[dict]:
    """
    Starting from a seed date, track the cascade of echoes forward in time.

    Move₁ → Echo₁ → Move₂ → Echo₂ → ...

    Each step: find the best-correlated future day within search_window.
    """
    all_dates = sorted(get_available_equity_dates(symbol))
    cascade = []
    current_date = seed_date

    for depth in range(max_depth):
        eq = load_equity_day(symbol, current_date)
        if eq.empty or len(eq) < 50:
            break

        current_profile = time_bin_profile(eq["ts"], eq["size"], n_bins, agg="sum")

        try:
            current_idx = all_dates.index(current_date)
        except ValueError:
            break

        # Search forward for echo
        best = {"date": None, "zncc": 0, "reversed": False, "lag": 0}
        for offset in range(3, min(search_window, len(all_dates) - current_idx)):
            future_date = all_dates[current_idx + offset]
            future_eq = load_equity_day(symbol, future_date)
            if future_eq.empty or len(future_eq) < 50:
                continue

            future_profile = time_bin_profile(future_eq["ts"], future_eq["size"], n_bins, agg="sum")
            zncc_normal = zncc_1d(current_profile, future_profile)
            zncc_reversed = zncc_1d(current_profile, future_profile[::-1])

            if abs(zncc_normal) > best["zncc"]:
                best = {"date": future_date, "zncc": abs(zncc_normal),
                        "reversed": False, "lag": offset, "raw_zncc": zncc_normal}
            if abs(zncc_reversed) > best["zncc"]:
                best = {"date": future_date, "zncc": abs(zncc_reversed),
                        "reversed": True, "lag": offset, "raw_zncc": zncc_reversed}

        if best["date"] is None or best["zncc"] < correlation_threshold:
            cascade.append({
                "depth": depth,
                "source_date": current_date,
                "echo_date": None,
                "status": "chain_broken",
            })
            break

        # Check if echo has associated options activity
        opts = load_options_day(symbol, best["date"])
        has_options = not opts.empty and len(opts) > 10

        cascade.append({
            "depth": depth,
            "source_date": current_date,
            "echo_date": best["date"],
            "lag_days": best["lag"],
            "zncc": best["raw_zncc"],
            "reversed": best["reversed"],
            "echo_has_options": has_options,
            "echo_options_count": len(opts) if has_options else 0,
        })

        current_date = best["date"]

    return cascade


# ============================================================================
# Visualization
# ============================================================================

def render_echo_kernel(kernel_df: pd.DataFrame, symbol: str = "") -> plt.Figure:
    """Heatmap of the temporal convolution kernel."""
    fig, axes = plt.subplots(1, 2, figsize=(16, 6), gridspec_kw={"width_ratios": [3, 1]})
    fig.patch.set_facecolor("#111")

    for ax in axes:
        ax.set_facecolor("black")
        ax.tick_params(colors="white")
        for s in ax.spines.values():
            s.set_color("#333")

    # Heatmap
    ax = axes[0]
    buckets = [c for c in EXP_BUCKETS + ["ALL"] if c in kernel_df.columns]
    data = kernel_df[buckets].values

    im = ax.imshow(data.T, aspect="auto", cmap="RdYlGn", vmin=-0.3, vmax=0.3,
                   origin="lower")
    ax.set_xticks(range(len(kernel_df)))
    ax.set_xticklabels(kernel_df.index, rotation=45, fontsize=8)
    ax.set_yticks(range(len(buckets)))
    ax.set_yticklabels(buckets, fontsize=10)
    ax.set_xlabel("Day Offset (Options relative to Equity)", color="white", fontsize=10)
    ax.set_ylabel("DTE Bucket", color="white", fontsize=10)
    ax.set_title(f"{symbol} Echo Kernel: Options→Equity Temporal Convolution",
                color="white", fontsize=13, fontweight="bold")
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="Mean ZNCC")

    # Line plot per bucket
    ax2 = axes[1]
    for bucket in buckets:
        if bucket in kernel_df.columns:
            vals = kernel_df[bucket].values
            color = EXP_COLORS.get(bucket, "#ffffff")
            ax2.plot(vals, kernel_df.index, color=color, marker="o", markersize=4,
                    label=bucket, linewidth=1.5)

    ax2.axvline(0, color="gray", linewidth=0.5, linestyle="--")
    ax2.set_xlabel("Mean ZNCC", color="white", fontsize=10)
    ax2.set_ylabel("Day Offset", color="white", fontsize=10)
    ax2.legend(facecolor="#222", edgecolor="#555", labelcolor="white", fontsize=8)
    ax2.set_title("Profile by Bucket", color="white", fontsize=11, fontweight="bold")

    fig.tight_layout()
    return fig


def render_hurst_timeline(
    hurst_df: pd.DataFrame,
    options_start: str = "",
    symbol: str = "",
) -> plt.Figure:
    """Plot rolling Hurst exponent with options listing marker."""
    fig, ax = plt.subplots(figsize=(14, 5))
    fig.patch.set_facecolor("#111")
    ax.set_facecolor("black")
    ax.tick_params(colors="white")
    for s in ax.spines.values():
        s.set_color("#333")

    dates = pd.to_datetime(hurst_df["center_date"])
    H = hurst_df["H"].values

    # Color by regime
    colors = np.where(H > 0.55, "#ff6b6b",  # momentum
              np.where(H < 0.45, "#4ecdc4",  # mean-reverting
                       "#888888"))            # neutral

    ax.scatter(dates, H, c=colors, s=20, alpha=0.7)
    ax.plot(dates, H, color="white", linewidth=0.5, alpha=0.3)

    ax.axhline(0.5, color="yellow", linewidth=1, linestyle="--", alpha=0.6, label="H=0.5 (Random Walk)")
    ax.fill_between(dates, 0.45, 0.55, alpha=0.1, color="gray", label="Neutral zone")

    if options_start:
        try:
            opts_dt = pd.to_datetime(options_start)
            ax.axvline(opts_dt, color="#ff9900", linewidth=2, linestyle="--",
                      alpha=0.8, label=f"Options listing: {options_start}")
        except Exception:
            pass

    ax.set_xlabel("Date", color="white", fontsize=11)
    ax.set_ylabel("Hurst Exponent", color="white", fontsize=11)
    ax.set_title(f"{symbol} — Rolling Hurst Exponent (Memory Detection)",
                color="white", fontsize=13, fontweight="bold")
    ax.legend(facecolor="#222", edgecolor="#555", labelcolor="white", fontsize=9)
    ax.set_ylim(0.2, 0.8)

    fig.tight_layout()
    return fig


def render_cascade(cascade: list[dict], symbol: str = "") -> plt.Figure:
    """Visualize an echo cascade as a chain diagram."""
    n = len(cascade)
    if n == 0:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "No cascade data", ha="center", va="center")
        return fig

    fig, ax = plt.subplots(figsize=(14, 4))
    fig.patch.set_facecolor("#111")
    ax.set_facecolor("black")
    ax.tick_params(colors="white")
    for s in ax.spines.values():
        s.set_color("#333")

    for i, step in enumerate(cascade):
        x = i * 2
        color = "#4ecdc4" if not step.get("reversed", False) else "#ff6b6b"

        # Node
        ax.scatter([x], [0], s=200, color=color, zorder=5, edgecolors="white", linewidth=1)
        ax.text(x, -0.15, step.get("source_date", "?")[-5:],
                ha="center", va="top", color="white", fontsize=8)

        if step.get("echo_date"):
            # Arrow to next
            ax.annotate(
                "", xy=(x + 1.5, 0), xytext=(x + 0.3, 0),
                arrowprops=dict(arrowstyle="->", color=color, lw=1.5),
            )
            label = f"lag={step.get('lag_days', '?')}d\nZNCC={step.get('zncc', 0):.2f}"
            if step.get("reversed"):
                label += "\n(REVERSED)"
            ax.text(x + 0.9, 0.08, label, ha="center", fontsize=7, color=color)

    ax.set_xlim(-0.5, n * 2)
    ax.set_ylim(-0.35, 0.3)
    ax.set_title(f"{symbol} — Echo Cascade Chain", color="white", fontsize=13, fontweight="bold")
    ax.axis("off")

    fig.tight_layout()
    return fig


# ============================================================================
# Streamlit App
# ============================================================================

def run_streamlit_app():
    """Streamlit UI for the Temporal Convolution Engine."""
    import streamlit as st

    st.set_page_config(page_title="Temporal Convolution Engine", layout="wide")
    st.title("🌊 Temporal Convolution Engine")
    st.markdown("""
    **Detect Options→Equity Echo Structure from IPO Origin**

    Analyze how options hedging creates temporal echoes, reversed reflections,
    and cascading feedback loops in equity price action.
    """)

    # Sidebar
    symbol = st.sidebar.text_input("Symbol", value="ARM").upper()
    fixed_iv = st.sidebar.slider("Fixed IV", 0.10, 2.0, 0.80, 0.05)
    n_bins = st.sidebar.slider("Time bins", 32, 256, 64)

    # Check data availability
    eq_dates = get_available_equity_dates(symbol)
    opt_dates = get_available_options_dates(symbol)
    st.sidebar.metric("Equity days (local)", len(eq_dates))
    st.sidebar.metric("Option days (local)", len(opt_dates))

    if not eq_dates:
        st.warning(f"No local data for {symbol}. Use the IPO Origin Scanner to fetch data first.")
        st.stop()

    # --- Tabs ---
    tab_acf, tab_kernel, tab_hurst, tab_reverse, tab_cascade = st.tabs([
        "📈 ACF Shift", "🌊 Echo Kernel", "📊 Hurst Memory",
        "🔄 Reverse Reconstruction", "🔗 Echo Cascade",
    ])

    with tab_acf:
        st.subheader("Autocorrelation Shift: Before vs After Options")
        if opt_dates:
            options_start = opt_dates[0]
            st.info(f"Options listing detected: {options_start}")

            if st.button("Run ACF Analysis"):
                with st.spinner("Computing ACF..."):
                    result = detect_acf_shift(symbol, eq_dates, options_start)

                fig, ax = plt.subplots(figsize=(12, 5))
                fig.patch.set_facecolor("#111")
                ax.set_facecolor("black")
                ax.tick_params(colors="white")
                lags = np.arange(len(result["before_acf"]))
                ax.plot(lags, result["before_acf"], color="#4ecdc4", label=f"Before options (n={result['n_before']})")
                ax.plot(lags, result["after_acf"], color="#ff6b6b", label=f"After options (n={result['n_after']})")
                ax.fill_between(lags, result["shift"], alpha=0.3, color="yellow", label="Shift (after - before)")
                ax.axhline(0, color="gray", linewidth=0.5, linestyle="--")
                ax.legend(facecolor="#222", edgecolor="#555", labelcolor="white")
                ax.set_xlabel("Lag (5min bars)", color="white")
                ax.set_ylabel("Autocorrelation", color="white")
                ax.set_title(f"{symbol} — Return ACF Before vs After Options", color="white", fontweight="bold")
                for s in ax.spines.values():
                    s.set_color("#333")
                fig.tight_layout()
                st.pyplot(fig)

    with tab_kernel:
        st.subheader("Temporal Echo Kernel")
        st.markdown("Cross-day correlation between options hedge flow and equity volume, stratified by DTE bucket.")

        col1, col2 = st.columns(2)
        with col1:
            max_days = st.number_input("Max days to analyze", 20, 500, 100)
        with col2:
            max_lag = st.number_input("Max lag (bins)", 10, 100, 30)

        if st.button("Compute Echo Kernel", type="primary"):
            progress = st.progress(0)
            with st.spinner("Computing kernel..."):
                result = compute_rolling_echo_kernel(
                    symbol, n_bins=n_bins, max_lag_bins=max_lag,
                    fixed_iv=fixed_iv, max_days=max_days,
                    progress_callback=lambda p: progress.progress(p),
                )

            if not result["kernel"].empty:
                fig = render_echo_kernel(result["kernel"], symbol)
                st.pyplot(fig)

                st.subheader("Kernel Data")
                st.dataframe(result["kernel"].style.background_gradient(cmap="RdYlGn", axis=None))
                st.metric("Total day-pairs analyzed", len(result["detail"]))

    with tab_hurst:
        st.subheader("Hurst Exponent — Memory Detection")
        st.markdown("H > 0.5 = momentum (hedge amplification) | H < 0.5 = mean-reversion (gamma dampening)")

        window = st.slider("Window size (days)", 10, 50, 20)
        step = st.slider("Step size (days)", 1, 10, 5)

        if st.button("Compute Rolling Hurst"):
            with st.spinner("Computing Hurst exponents..."):
                hurst_df = rolling_hurst(symbol, eq_dates, window_size=window, step=step)

            if not hurst_df.empty:
                options_start = opt_dates[0] if opt_dates else ""
                fig = render_hurst_timeline(hurst_df, options_start, symbol)
                st.pyplot(fig)

                # Summary stats
                col1, col2, col3 = st.columns(3)
                col1.metric("Mean H", f"{hurst_df['H'].mean():.3f}")
                col2.metric("Min H", f"{hurst_df['H'].min():.3f}")
                col3.metric("Max H", f"{hurst_df['H'].max():.3f}")

    with tab_reverse:
        st.subheader("Reverse Reconstruction: Past from Current Chain")
        st.markdown("Can today's options chain predict *past* equity activity?")

        if opt_dates:
            chain_date = st.selectbox("Chain date", opt_dates[-30:] if len(opt_dates) > 30 else opt_dates)

            if st.button("Run Reverse Reconstruction"):
                with st.spinner("Reconstructing..."):
                    result = reconstruct_past_from_chain(symbol, chain_date, fixed_iv=fixed_iv, n_bins=n_bins)

                if "error" not in result and result.get("lookback_results"):
                    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
                    fig.patch.set_facecolor("#111")

                    for ax in axes:
                        ax.set_facecolor("black")
                        ax.tick_params(colors="white")
                        for s in ax.spines.values():
                            s.set_color("#333")

                    # Left: ZNCC vs lookback
                    lbs = [r["lookback_days"] for r in result["lookback_results"]]
                    zncc_all = [r["zncc_all"] for r in result["lookback_results"]]
                    axes[0].bar(lbs, zncc_all, color="#ff6b6b", alpha=0.8)
                    axes[0].axhline(0, color="gray", linewidth=0.5)
                    axes[0].set_xlabel("Lookback (days)", color="white")
                    axes[0].set_ylabel("ZNCC with chain", color="white")
                    axes[0].set_title("Chain vs Past Equity Correlation", color="white", fontweight="bold")

                    # Right: Per-bucket breakdown
                    for r in result["lookback_results"]:
                        for bucket, val in r.get("bucket_zncc", {}).items():
                            color = EXP_COLORS.get(bucket, "#888")
                            axes[1].scatter(r["lookback_days"], val, color=color, s=30, alpha=0.7)

                    axes[1].axhline(0, color="gray", linewidth=0.5)
                    axes[1].set_xlabel("Lookback (days)", color="white")
                    axes[1].set_ylabel("ZNCC by DTE bucket", color="white")
                    axes[1].set_title("Per-Bucket Reverse Correlation", color="white", fontweight="bold")

                    # Legend
                    for bucket in EXP_BUCKETS:
                        axes[1].scatter([], [], color=EXP_COLORS[bucket], label=bucket)
                    axes[1].legend(facecolor="#222", edgecolor="#555", labelcolor="white", fontsize=8)

                    fig.tight_layout()
                    st.pyplot(fig)

    with tab_cascade:
        st.subheader("Echo Cascade Tracker")
        st.markdown("Track chains of echoes: Move₁ → Echo₁ → Move₂ → Echo₂ → ...")

        seed_date = st.selectbox("Seed date", eq_dates[:100] if len(eq_dates) > 100 else eq_dates)
        max_depth = st.slider("Max cascade depth", 2, 10, 5)
        threshold = st.slider("Correlation threshold", 0.1, 0.8, 0.35, 0.05)

        if st.button("Track Cascade"):
            with st.spinner("Tracking cascade..."):
                cascade = track_echo_cascade(
                    symbol, seed_date, max_depth=max_depth,
                    correlation_threshold=threshold, n_bins=n_bins,
                )

            if cascade:
                fig = render_cascade(cascade, symbol)
                st.pyplot(fig)

                st.subheader("Cascade Detail")
                st.dataframe(pd.DataFrame(cascade))


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Temporal Convolution Engine")
    parser.add_argument("--mode", choices=["app", "kernel", "hurst", "cascade"], default="app")
    parser.add_argument("--symbol", type=str, default="ARM")
    args = parser.parse_args()

    if args.mode == "app":
        run_streamlit_app()
    else:
        print(f"Run with: streamlit run {__file__}")
