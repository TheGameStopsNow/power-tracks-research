#!/usr/bin/env python3
"""
Phase 5: The Paradigm Shift
============================
5A – Measure Temporal Convolution Kernel (DTE-stratified echo lags)
5B – Standing Wave Heatmap (n² date-pair burst shape match)
5C – Temporal Archaeology (NMF decomposition of equity from options)

These build on the Phase 4 causal proof to show that the options chain
doesn't just dampen equity prices in real-time — it leaves temporal echoes
whose structure encodes expiration cycles.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------

POLYGON_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw" / "polygon" / "trades"
THETA_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw" / "thetadata" / "trades"
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def _load_equity_day(ticker: str, date_str: str) -> pd.DataFrame:
    """Load equity trades for one day. date_str = YYYY-MM-DD."""
    path = POLYGON_ROOT / f"symbol={ticker}" / f"date={date_str}" / "part-0.parquet"
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_parquet(path)
    df = df.rename(columns={"timestamp": "ts", "price": "eq_price", "size": "eq_size"})
    df = df.sort_values("ts").reset_index(drop=True)
    df = df[(df["ts"].dt.hour >= 9) & (df["ts"].dt.hour < 16)]
    df = df[~((df["ts"].dt.hour == 9) & (df["ts"].dt.minute < 30))]
    return df[["ts", "eq_price", "eq_size"]]


def _load_options_day(ticker: str, date_str: str) -> pd.DataFrame:
    """Load options trades for one day. date_str = YYYY-MM-DD."""
    date_key = date_str.replace("-", "")
    path = THETA_ROOT / f"root={ticker}" / f"date={date_key}" / "part-0.parquet"
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_parquet(path)
    df["ts"] = pd.to_datetime(df["timestamp"], format="ISO8601")
    df = df.sort_values("ts").reset_index(drop=True)
    df = df[(df["ts"].dt.hour >= 9) & (df["ts"].dt.hour < 16)]
    df = df[~((df["ts"].dt.hour == 9) & (df["ts"].dt.minute < 30))]
    # Normalize schema
    if "expiration" not in df.columns and "expiry" in df.columns:
        df = df.rename(columns={"expiry": "expiration"})
    if df["right"].dtype == object:
        df["right"] = df["right"].str[0]
    cols = ["ts", "strike", "right", "size", "price"]
    if "expiration" in df.columns:
        cols.append("expiration")
    return df[cols]


def _overlap_dates(ticker: str, n: int = 50) -> list[str]:
    """Find dates with both equity + options data."""
    eq_dir = POLYGON_ROOT / f"symbol={ticker}"
    opts_dir = THETA_ROOT / f"root={ticker}"
    if not eq_dir.exists() or not opts_dir.exists():
        return []
    eq = {d.name.replace("date=", "") for d in eq_dir.iterdir() if d.is_dir()}
    opts_raw = {d.name.replace("date=", "") for d in opts_dir.iterdir() if d.is_dir()}
    opts = {f"{d[:4]}-{d[4:6]}-{d[6:8]}" for d in opts_raw if len(d) == 8}
    return sorted(eq & opts)[-n:]


# ---------------------------------------------------------------------------
# 5A: Convolution Kernel — DTE-Stratified Echo Lag
# ---------------------------------------------------------------------------

def _classify_dte(expiration_str: str, trade_date_str: str) -> str:
    """Classify option DTE into bucket: 0DTE, Weekly, Monthly, LEAPS."""
    try:
        if isinstance(expiration_str, str) and len(expiration_str) == 8:
            exp = pd.Timestamp(f"{expiration_str[:4]}-{expiration_str[4:6]}-{expiration_str[6:8]}")
        else:
            exp = pd.Timestamp(str(expiration_str))
        trade = pd.Timestamp(trade_date_str)
        dte = (exp - trade).days
    except Exception:
        return "UNKNOWN"
    if dte <= 0:
        return "0DTE"
    elif dte <= 7:
        return "WEEKLY"
    elif dte <= 45:
        return "MONTHLY"
    else:
        return "LEAPS"


def _time_profile(df: pd.DataFrame, n_bins: int = 64) -> np.ndarray:
    """Bin trades into n_bins equal time intervals, return volume profile."""
    if len(df) == 0:
        return np.zeros(n_bins)
    ts = df["ts"].values.astype("int64")
    t_min, t_max = ts.min(), ts.max()
    if t_max == t_min:
        result = np.zeros(n_bins)
        result[0] = df["eq_size"].sum() if "eq_size" in df.columns else df["size"].sum()
        return result
    bins = np.linspace(t_min, t_max, n_bins + 1)
    idx = np.clip(np.searchsorted(bins, ts, side="right") - 1, 0, n_bins - 1)
    sizes = df["eq_size"].values if "eq_size" in df.columns else df["size"].values
    profile = np.zeros(n_bins)
    np.add.at(profile, idx, sizes)
    return profile


def _zncc(a: np.ndarray, b: np.ndarray) -> float:
    """Zero-mean normalized cross-correlation."""
    a = a - a.mean()
    b = b - b.mean()
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom < 1e-12:
        return 0.0
    return float(np.dot(a, b) / denom)


def run_convolution_kernel(ticker: str, max_dates: int = 30, n_bins: int = 64) -> dict:
    """
    Phase 5A: For each day, stratify options by DTE bucket, compute
    volume profiles, then cross-correlate with equity volume profiles
    at day offsets [0, 1, 2, 5, 10, 20].
    
    If options with longer DTE show peak correlation at longer offsets,
    the convolution kernel exists.
    """
    print(f"\n{'='*60}")
    print(f"5A: Convolution Kernel — {ticker}")
    print(f"{'='*60}")

    dates = _overlap_dates(ticker, max_dates)
    print(f"  Overlapping dates: {len(dates)}")
    if len(dates) < 5:
        return {"error": "Not enough overlapping dates"}

    day_offsets = [0, 1, 2, 5, 10, 20]
    dte_buckets = ["0DTE", "WEEKLY", "MONTHLY", "LEAPS"]
    
    # kernel[bucket][offset] = list of correlations
    kernel = {b: {o: [] for o in day_offsets} for b in dte_buckets}
    
    for i, date_str in enumerate(dates):
        if i % 5 == 0:
            print(f"  Processing date {i+1}/{len(dates)}: {date_str}")
        
        try:
            opts_df = _load_options_day(ticker, date_str)
        except FileNotFoundError:
            continue
            
        if "expiration" not in opts_df.columns:
            continue
            
        # Stratify options by DTE
        opts_df["dte_bucket"] = opts_df["expiration"].apply(
            lambda e: _classify_dte(e, date_str)
        )
        
        # Get options volume profile per bucket
        bucket_profiles = {}
        for bucket in dte_buckets:
            subset = opts_df[opts_df["dte_bucket"] == bucket]
            if len(subset) < 10:
                continue
            bucket_profiles[bucket] = _time_profile(subset, n_bins)
        
        if not bucket_profiles:
            continue
        
        # Cross-correlate with equity at day offsets
        for offset in day_offsets:
            target_idx = i + offset
            if target_idx >= len(dates):
                continue
            target_date = dates[target_idx]
            
            try:
                eq_df = _load_equity_day(ticker, target_date)
            except FileNotFoundError:
                continue
                
            eq_profile = _time_profile(eq_df, n_bins)
            
            for bucket, opts_profile in bucket_profiles.items():
                corr = _zncc(opts_profile, eq_profile)
                kernel[bucket][offset].append(corr)
    
    # Compute mean correlations
    result = {}
    print(f"\n  === CONVOLUTION KERNEL ===")
    print(f"  {'Bucket':>8}  " + "  ".join(f"T+{o}" for o in day_offsets))
    for bucket in dte_buckets:
        row = {}
        vals = []
        for offset in day_offsets:
            if kernel[bucket][offset]:
                mean_corr = float(np.mean(kernel[bucket][offset]))
                row[f"T+{offset}"] = round(mean_corr, 4)
                vals.append(f"{mean_corr:>6.4f}")
            else:
                row[f"T+{offset}"] = None
                vals.append(f"{'N/A':>6}")
        result[bucket] = row
        print(f"  {bucket:>8}  " + "  ".join(vals))
    
    # Find peak lag per bucket
    print(f"\n  === PEAK LAG PER BUCKET ===")
    for bucket in dte_buckets:
        offsets_with_data = [(o, result[bucket].get(f"T+{o}")) for o in day_offsets 
                           if result[bucket].get(f"T+{o}") is not None]
        if offsets_with_data:
            peak_offset, peak_corr = max(offsets_with_data, key=lambda x: abs(x[1]))
            result[bucket]["peak_lag"] = peak_offset
            result[bucket]["peak_corr"] = peak_corr
            print(f"  {bucket:>8}: peak at T+{peak_offset} (corr = {peak_corr:.4f})")
    
    return result


# ---------------------------------------------------------------------------
# 5B: Standing Wave Heatmap — n² Date-Pair Shape Match
# ---------------------------------------------------------------------------

def run_standing_wave_heatmap(ticker: str, max_dates: int = 50, n_bins: int = 64) -> dict:
    """
    Phase 5B: Compute equity volume profile similarity for all date pairs.
    
    Output: N×N correlation matrix. Look for:
    - Diagonal bands at ~30-day intervals (monthly options cycle)
    - Perpendicular bands (source dates that echo forward)
    """
    print(f"\n{'='*60}")
    print(f"5B: Standing Wave Heatmap — {ticker}")
    print(f"{'='*60}")
    
    dates = _overlap_dates(ticker, max_dates)
    print(f"  Dates: {len(dates)}")
    n = len(dates)
    
    if n < 5:
        return {"error": "Not enough dates"}
    
    # Precompute all profiles
    profiles = {}
    for i, d in enumerate(dates):
        try:
            eq_df = _load_equity_day(ticker, d)
            profiles[d] = _time_profile(eq_df, n_bins)
        except FileNotFoundError:
            pass
    
    valid_dates = [d for d in dates if d in profiles]
    n = len(valid_dates)
    print(f"  Valid dates with profiles: {n}")
    print(f"  Computing {n}×{n} = {n*n} correlations...")
    
    # Compute n² correlation matrix
    corr_matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            corr_matrix[i, j] = _zncc(profiles[valid_dates[i]], profiles[valid_dates[j]])
    
    # Analyze diagonal bands
    offdiag_means = {}
    for lag in range(1, min(n, 60)):
        vals = [corr_matrix[i, i + lag] for i in range(n - lag)]
        if vals:
            offdiag_means[lag] = float(np.mean(vals))
    
    # Find periodic peaks
    print(f"\n  === OFF-DIAGONAL CORRELATION BY LAG ===")
    print(f"  {'Lag':>4}  {'Mean Corr':>10}  {'Pattern':>10}")
    for lag in sorted(offdiag_means.keys()):
        corr = offdiag_means[lag]
        pattern = ""
        if lag in (20, 21, 22):  # ~monthly (trading days)
            pattern = "← MONTHLY?"
        elif lag in (5,):
            pattern = "← WEEKLY?"
        elif lag in (1,):
            pattern = "← DAILY"
        print(f"  {lag:>4}  {corr:>10.4f}  {pattern:>10}")
    
    # Find dates that match many others (source dates)
    row_means = corr_matrix.mean(axis=1)
    top_source_idx = np.argsort(row_means)[-5:][::-1]
    
    print(f"\n  === TOP SOURCE DATES ===")
    for idx in top_source_idx:
        print(f"  {valid_dates[idx]}: mean corr = {row_means[idx]:.4f}")
    
    # Detect ~30-day periodicity
    if len(offdiag_means) >= 25:
        lags = np.array(sorted(offdiag_means.keys()))
        vals = np.array([offdiag_means[l] for l in lags])
        # Simple peak detection
        peaks = []
        for i in range(1, len(vals) - 1):
            if vals[i] > vals[i-1] and vals[i] > vals[i+1] and vals[i] > 0.05:
                peaks.append((int(lags[i]), float(vals[i])))
        if peaks:
            print(f"\n  Detected correlation peaks at lags: {peaks}")
    
    result = {
        "n_dates": n,
        "dates": valid_dates,
        "offdiag_means": {str(k): v for k, v in offdiag_means.items()},
        "top_source_dates": [
            {"date": valid_dates[idx], "mean_corr": round(float(row_means[idx]), 4)}
            for idx in top_source_idx
        ],
        "matrix_stats": {
            "mean": round(float(corr_matrix.mean()), 4),
            "std": round(float(corr_matrix.std()), 4),
            "max_offdiag": round(float(np.max(corr_matrix - np.eye(n))), 4),
        },
    }
    
    return result


# ---------------------------------------------------------------------------
# 5C: Temporal Archaeology — NMF Decomposition
# ---------------------------------------------------------------------------

def run_temporal_archaeology(
    ticker: str,
    target_date: str,
    max_source_dates: int = 30,
    n_components: int = 5,
    n_bins: int = 64,
) -> dict:
    """
    Phase 5C: Decompose one equity day's volume profile into a weighted
    combination of options-hedging profiles from surrounding days.
    
    Uses Non-Negative Matrix Factorization (NMF) to find the best
    combination of options profiles that reconstruct the equity profile.
    """
    from sklearn.decomposition import NMF
    
    print(f"\n{'='*60}")
    print(f"5C: Temporal Archaeology — {ticker} {target_date}")
    print(f"{'='*60}")
    
    # Load target equity profile
    try:
        eq_df = _load_equity_day(ticker, target_date)
    except FileNotFoundError:
        return {"error": f"No equity data for {target_date}"}
    
    target_profile = _time_profile(eq_df, n_bins)
    target_profile = np.clip(target_profile, 0, None)  # NMF needs non-negative
    
    # Load options profiles from surrounding dates
    all_dates = _overlap_dates(ticker, max_source_dates * 2)
    # Use dates around the target
    try:
        target_idx = all_dates.index(target_date)
    except ValueError:
        # Use closest dates
        target_idx = len(all_dates) // 2
    
    source_dates = all_dates[max(0, target_idx - max_source_dates):target_idx + max_source_dates]
    
    source_profiles = []
    source_labels = []
    
    for d in source_dates:
        try:
            opts_df = _load_options_day(ticker, d)
            profile = _time_profile(opts_df, n_bins)
            profile = np.clip(profile, 0, None)
            if profile.sum() > 0:
                source_profiles.append(profile)
                source_labels.append(d)
        except FileNotFoundError:
            continue
    
    if len(source_profiles) < n_components:
        return {"error": f"Only {len(source_profiles)} source dates, need >= {n_components}"}
    
    print(f"  Target: {target_date} ({len(eq_df)} equity trades)")
    print(f"  Source profiles: {len(source_profiles)} options days")
    
    # Build source matrix: (n_sources, n_bins)
    W_source = np.array(source_profiles)
    
    # NMF: decompose target ≈ W_source.T @ h, where h are the weights
    # We solve: target_profile ≈ sum(h_i * source_profile_i)
    # Approach: Use NMF on the combined matrix [source_profiles; target_profile]
    # then extract the encoding of the target row
    
    combined = np.vstack([W_source, target_profile.reshape(1, -1)])
    combined = combined + 1e-6  # NMF needs strictly positive
    
    n_comp = min(n_components, len(source_profiles))
    model = NMF(n_components=n_comp, init="nndsvd", max_iter=500, random_state=42)
    H = model.fit_transform(combined)
    W = model.components_
    
    # The target's encoding is the last row of H
    target_encoding = H[-1, :]
    
    # Reconstruct
    reconstruction = target_encoding @ W
    reconstruction_corr = _zncc(target_profile, reconstruction)
    residual = np.linalg.norm(target_profile - reconstruction) / np.linalg.norm(target_profile)
    
    print(f"\n  Reconstruction correlation: {reconstruction_corr:.4f}")
    print(f"  Residual (normalized): {residual:.4f}")
    print(f"  Residual as %: {residual*100:.1f}%")
    
    # Which source dates contribute most?
    source_encodings = H[:-1, :]  # All rows except last
    
    # For each source, compute its contribution to reconstructing the target
    contributions = []
    for i, label in enumerate(source_labels):
        # Dot product of source's encoding with target's encoding
        similarity = float(np.dot(source_encodings[i], target_encoding))
        profile_corr = _zncc(source_profiles[i], target_profile)
        contributions.append({
            "date": label,
            "nmf_weight": round(similarity, 4),
            "profile_corr": round(profile_corr, 4),
        })
    
    contributions.sort(key=lambda x: x["nmf_weight"], reverse=True)
    
    print(f"\n  === TOP CONTRIBUTING SOURCE DATES ===")
    print(f"  {'Date':>12}  {'NMF Weight':>12}  {'Profile Corr':>12}")
    for c in contributions[:10]:
        print(f"  {c['date']:>12}  {c['nmf_weight']:>12.4f}  {c['profile_corr']:>12.4f}")
    
    # Check if same-date options reconstruct best (expected)
    same_date = [c for c in contributions if c["date"] == target_date]
    if same_date:
        rank = contributions.index(same_date[0]) + 1
        print(f"\n  Same-date options rank: #{rank} of {len(contributions)}")
    
    result = {
        "target_date": target_date,
        "reconstruction_corr": round(reconstruction_corr, 4),
        "residual_pct": round(residual * 100, 1),
        "n_components": n_comp,
        "n_sources": len(source_profiles),
        "top_contributors": contributions[:10],
    }
    
    return result


def run_temporal_archaeology_residual(
    ticker: str,
    target_date: str,
    max_source_dates: int = 30,
    n_components: int = 5,
    n_bins: int = 64,
) -> dict:
    """
    Phase 5C-R: RESIDUAL Temporal Archaeology (Anomaly Test).
    
    Same as run_temporal_archaeology, but first subtracts the mean volume
    profile (the "standard U-shape") from both sources and target.
    This tests whether NMF captures UNIQUE deviations (genuine hedging
    echoes) rather than just the common intraday seasonality.
    
    Reports both raw reconstruction (r_raw) and residual reconstruction
    (r_residual). A high r_residual (>0.30) is strong evidence that
    past options chains dictate unique future volume bursts.
    """
    from sklearn.decomposition import NMF
    
    print(f"\n{'='*60}")
    print(f"5C-R: Temporal Archaeology RESIDUAL — {ticker} {target_date}")
    print(f"{'='*60}")
    
    # Load target equity profile
    try:
        eq_df = _load_equity_day(ticker, target_date)
    except FileNotFoundError:
        return {"error": f"No equity data for {target_date}"}
    
    target_profile = _time_profile(eq_df, n_bins)
    target_profile = np.clip(target_profile, 0, None)
    
    # Load options profiles from surrounding dates
    all_dates = _overlap_dates(ticker, max_source_dates * 2)
    try:
        target_idx = all_dates.index(target_date)
    except ValueError:
        target_idx = len(all_dates) // 2
    
    source_dates = all_dates[max(0, target_idx - max_source_dates):target_idx + max_source_dates]
    
    source_profiles = []
    source_labels = []
    
    for d in source_dates:
        try:
            opts_df = _load_options_day(ticker, d)
            profile = _time_profile(opts_df, n_bins)
            profile = np.clip(profile, 0, None)
            if profile.sum() > 0:
                source_profiles.append(profile)
                source_labels.append(d)
        except FileNotFoundError:
            continue
    
    if len(source_profiles) < n_components:
        return {"error": f"Only {len(source_profiles)} source dates, need >= {n_components}"}
    
    print(f"  Target: {target_date} ({len(eq_df)} equity trades)")
    print(f"  Source profiles: {len(source_profiles)} options days")
    
    W_source = np.array(source_profiles)
    
    # --- RAW reconstruction (original method) ---
    combined_raw = np.vstack([W_source, target_profile.reshape(1, -1)])
    combined_raw = combined_raw + 1e-6
    n_comp = min(n_components, len(source_profiles))
    model_raw = NMF(n_components=n_comp, init="nndsvd", max_iter=500, random_state=42)
    H_raw = model_raw.fit_transform(combined_raw)
    W_raw = model_raw.components_
    reconstruction_raw = H_raw[-1, :] @ W_raw
    r_raw = _zncc(target_profile, reconstruction_raw)
    
    # --- RESIDUAL reconstruction (anomaly test) ---
    # Compute mean profile across all sources (the "standard U-shape")
    mean_profile = W_source.mean(axis=0)
    
    # Subtract mean from sources and target
    source_residuals = W_source - mean_profile
    target_residual = target_profile - mean_profile
    
    # NMF requires non-negative: shift residuals by adding |min| + epsilon
    # This preserves the relative structure while satisfying NMF constraints
    all_residuals = np.vstack([source_residuals, target_residual.reshape(1, -1)])
    shift = abs(all_residuals.min()) + 1e-6
    all_residuals_shifted = all_residuals + shift
    
    model_resid = NMF(n_components=n_comp, init="nndsvd", max_iter=500, random_state=42)
    H_resid = model_resid.fit_transform(all_residuals_shifted)
    W_resid = model_resid.components_
    
    # Reconstruct the residual (still shifted)
    reconstruction_resid_shifted = H_resid[-1, :] @ W_resid
    # Un-shift to compare against original residual
    reconstruction_resid = reconstruction_resid_shifted - shift
    
    r_residual = _zncc(target_residual, reconstruction_resid)
    
    # Residual norm
    resid_norm_raw = np.linalg.norm(target_profile - reconstruction_raw) / np.linalg.norm(target_profile)
    resid_norm_resid = np.linalg.norm(target_residual - reconstruction_resid) / (np.linalg.norm(target_residual) + 1e-12)
    
    print(f"\n  === RECONSTRUCTION QUALITY ===")
    print(f"  Raw reconstruction ZNCC:      {r_raw:.4f}")
    print(f"  Residual reconstruction ZNCC: {r_residual:.4f}")
    print(f"  Raw residual norm:            {resid_norm_raw*100:.1f}%")
    print(f"  Residual residual norm:       {resid_norm_resid*100:.1f}%")
    print(f"  Mean profile variance:        {mean_profile.var():.2f}")
    print(f"  Target deviation variance:    {target_residual.var():.2f}")
    
    # Contribution analysis on residual reconstruction
    source_encodings = H_resid[:-1, :]
    target_encoding = H_resid[-1, :]
    
    contributions = []
    for i, label in enumerate(source_labels):
        similarity = float(np.dot(source_encodings[i], target_encoding))
        profile_corr = _zncc(source_residuals[i], target_residual)
        contributions.append({
            "date": label,
            "nmf_weight": round(similarity, 4),
            "residual_corr": round(profile_corr, 4),
        })
    
    contributions.sort(key=lambda x: x["nmf_weight"], reverse=True)
    
    print(f"\n  === TOP CONTRIBUTING SOURCE DATES (RESIDUAL) ===")
    print(f"  {'Date':>12}  {'NMF Weight':>12}  {'Resid Corr':>12}")
    for c in contributions[:10]:
        print(f"  {c['date']:>12}  {c['nmf_weight']:>12.4f}  {c['residual_corr']:>12.4f}")
    
    result = {
        "target_date": target_date,
        "r_raw": round(r_raw, 4),
        "r_residual": round(r_residual, 4),
        "residual_pct_raw": round(resid_norm_raw * 100, 1),
        "residual_pct_resid": round(resid_norm_resid * 100, 1),
        "n_components": n_comp,
        "n_sources": len(source_profiles),
        "mean_profile_var": round(float(mean_profile.var()), 2),
        "target_deviation_var": round(float(target_residual.var()), 2),
        "top_contributors_residual": contributions[:10],
    }
    
    return result


def run_temporal_archaeology_strict(
    ticker: str,
    target_date: str,
    exclude_window: int = 2,  # Exclude T+0 and T-1 (2 days)
    max_source_dates: int = 30,
    n_components: int = 5,
    n_bins: int = 64,
) -> dict:
    """
    Phase 5C-S: STRICT Temporal Archaeology (Data Leakage Fix).
    
    Same as residual archaeology, but EXCLUDES source dates within
    `exclude_window` days of the target date. This ensures genuine
    predictive power from past data only — no T+0 or T-1 contamination.
    
    If r_strict remains high (>0.7), it proves the equity tape is a
    deterministic function of options chain *history*, not just
    contemporaneous matching.
    """
    from sklearn.decomposition import NMF
    from datetime import datetime, timedelta
    
    print(f"\n{'='*60}")
    print(f"5C-S: STRICT Temporal Archaeology — {ticker} {target_date}")
    print(f"      (Excluding T+0 through T-{exclude_window-1})")
    print(f"{'='*60}")
    
    # Load target equity profile
    try:
        eq_df = _load_equity_day(ticker, target_date)
    except FileNotFoundError:
        return {"error": f"No equity data for {target_date}"}
    
    target_profile = _time_profile(eq_df, n_bins)
    target_profile = np.clip(target_profile, 0, None)
    
    # Load options profiles from surrounding dates
    all_dates = _overlap_dates(ticker, max_source_dates * 2)
    try:
        target_idx = all_dates.index(target_date)
    except ValueError:
        target_idx = len(all_dates) // 2
    
    source_dates = all_dates[max(0, target_idx - max_source_dates):target_idx + max_source_dates]
    
    # === STRICT FILTER: Exclude T+0 through T-(exclude_window-1) ===
    target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    excluded_dates = set()
    for offset in range(exclude_window):
        d = (target_dt - timedelta(days=offset)).strftime("%Y-%m-%d")
        excluded_dates.add(d)
    # Also check in case target_date + days are in source (shouldn't be, but safety)
    for offset in range(1, exclude_window):
        d = (target_dt + timedelta(days=offset)).strftime("%Y-%m-%d")
        excluded_dates.add(d)
    
    source_profiles = []
    source_labels = []
    excluded_count = 0
    
    for d in source_dates:
        if d in excluded_dates:
            excluded_count += 1
            continue
        try:
            opts_df = _load_options_day(ticker, d)
            profile = _time_profile(opts_df, n_bins)
            profile = np.clip(profile, 0, None)
            if profile.sum() > 0:
                source_profiles.append(profile)
                source_labels.append(d)
        except FileNotFoundError:
            continue
    
    if len(source_profiles) < n_components:
        return {"error": f"Only {len(source_profiles)} source dates, need >= {n_components}"}
    
    print(f"  Target: {target_date} ({len(eq_df)} equity trades)")
    print(f"  Source profiles: {len(source_profiles)} options days (excluded {excluded_count} near-term)")
    print(f"  Excluded dates: {sorted(excluded_dates)}")
    
    W_source = np.array(source_profiles)
    
    # --- RAW reconstruction (strict: no T+0/T-1) ---
    combined_raw = np.vstack([W_source, target_profile.reshape(1, -1)])
    combined_raw = combined_raw + 1e-6
    n_comp = min(n_components, len(source_profiles))
    model_raw = NMF(n_components=n_comp, init="nndsvd", max_iter=500, random_state=42)
    H_raw = model_raw.fit_transform(combined_raw)
    W_raw = model_raw.components_
    reconstruction_raw = H_raw[-1, :] @ W_raw
    r_raw_strict = _zncc(target_profile, reconstruction_raw)
    
    # --- RESIDUAL reconstruction (strict: deseason + exclude T+0/T-1) ---
    mean_profile = W_source.mean(axis=0)
    source_residuals = W_source - mean_profile
    target_residual = target_profile - mean_profile
    
    all_residuals = np.vstack([source_residuals, target_residual.reshape(1, -1)])
    shift = abs(all_residuals.min()) + 1e-6
    all_residuals_shifted = all_residuals + shift
    
    model_resid = NMF(n_components=n_comp, init="nndsvd", max_iter=500, random_state=42)
    H_resid = model_resid.fit_transform(all_residuals_shifted)
    W_resid = model_resid.components_
    
    reconstruction_resid_shifted = H_resid[-1, :] @ W_resid
    reconstruction_resid = reconstruction_resid_shifted - shift
    
    r_residual_strict = _zncc(target_residual, reconstruction_resid)
    
    # Residual norms
    resid_norm_raw = np.linalg.norm(target_profile - reconstruction_raw) / np.linalg.norm(target_profile)
    resid_norm_resid = np.linalg.norm(target_residual - reconstruction_resid) / (np.linalg.norm(target_residual) + 1e-12)
    
    print(f"\n  === STRICT RECONSTRUCTION QUALITY ===")
    print(f"  Strict raw ZNCC:      {r_raw_strict:.4f}")
    print(f"  Strict residual ZNCC: {r_residual_strict:.4f}")
    print(f"  Raw residual norm:    {resid_norm_raw*100:.1f}%")
    print(f"  Resid residual norm:  {resid_norm_resid*100:.1f}%")
    print(f"  Mean profile var:     {mean_profile.var():.2f}")
    print(f"  Target dev var:       {target_residual.var():.2f}")
    
    # Contribution analysis on residual reconstruction
    source_encodings = H_resid[:-1, :]
    target_encoding = H_resid[-1, :]
    
    contributions = []
    for i, label in enumerate(source_labels):
        similarity = float(np.dot(source_encodings[i], target_encoding))
        profile_corr = _zncc(source_residuals[i], target_residual)
        offset = (datetime.strptime(target_date, "%Y-%m-%d") - datetime.strptime(label, "%Y-%m-%d")).days
        contributions.append({
            "date": label,
            "offset_days": offset,
            "nmf_weight": round(similarity, 4),
            "residual_corr": round(profile_corr, 4),
        })
    
    contributions.sort(key=lambda x: x["nmf_weight"], reverse=True)
    
    print(f"\n  === TOP CONTRIBUTING SOURCE DATES (STRICT PAST) ===")
    print(f"  {'Date':>12}  {'Offset':>8}  {'NMF Weight':>12}  {'Resid Corr':>12}")
    for c in contributions[:10]:
        print(f"  {c['date']:>12}  T-{c['offset_days']:<5}  {c['nmf_weight']:>12.4f}  {c['residual_corr']:>12.4f}")
    
    result = {
        "target_date": target_date,
        "exclude_window": exclude_window,
        "r_raw_strict": round(r_raw_strict, 4),
        "r_residual_strict": round(r_residual_strict, 4),
        "residual_pct_raw": round(resid_norm_raw * 100, 1),
        "residual_pct_resid": round(resid_norm_resid * 100, 1),
        "n_components": n_comp,
        "n_sources": len(source_profiles),
        "n_excluded": excluded_count,
        "excluded_dates": sorted(excluded_dates),
        "mean_profile_var": round(float(mean_profile.var()), 2),
        "target_deviation_var": round(float(target_residual.var()), 2),
        "top_contributors_strict": contributions[:10],
    }
    
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Phase 5: Paradigm Shift")
    parser.add_argument("--mode", choices=["kernel", "heatmap", "archaeology", "archaeology-residual", "archaeology-strict", "all"],
                        default="all")
    parser.add_argument("--ticker", default="GME")
    parser.add_argument("--target-date", default=None)
    parser.add_argument("--max-dates", type=int, default=30)
    parser.add_argument("--n-components", type=int, default=5)
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    all_results = {"ticker": args.ticker}

    if args.mode in ("kernel", "all"):
        r = run_convolution_kernel(args.ticker, max_dates=args.max_dates)
        all_results["kernel"] = r
        with open(RESULTS_DIR / f"phase5a_kernel_{args.ticker}.json", "w") as f:
            json.dump(r, f, indent=2, default=str)

    if args.mode in ("heatmap", "all"):
        r = run_standing_wave_heatmap(args.ticker, max_dates=args.max_dates)
        all_results["heatmap"] = r
        with open(RESULTS_DIR / f"phase5b_heatmap_{args.ticker}.json", "w") as f:
            json.dump(r, f, indent=2, default=str)

    if args.mode in ("archaeology", "all"):
        target = args.target_date
        if not target:
            dates = _overlap_dates(args.ticker, args.max_dates)
            target = dates[-1] if dates else None
        if target:
            r = run_temporal_archaeology(
                args.ticker, target,
                max_source_dates=args.max_dates,
                n_components=args.n_components,
            )
            all_results["archaeology"] = r
            with open(RESULTS_DIR / f"phase5c_archaeology_{args.ticker}.json", "w") as f:
                json.dump(r, f, indent=2, default=str)

    if args.mode in ("archaeology-residual", "all"):
        target = args.target_date
        if not target:
            dates = _overlap_dates(args.ticker, args.max_dates)
            target = dates[-1] if dates else None
        if target:
            r = run_temporal_archaeology_residual(
                args.ticker, target,
                max_source_dates=args.max_dates,
                n_components=args.n_components,
            )
            all_results["archaeology_residual"] = r
            with open(RESULTS_DIR / f"phase5c_archaeology_residual_{args.ticker}.json", "w") as f:
                json.dump(r, f, indent=2, default=str)

    if args.mode in ("archaeology-strict",):
        target = args.target_date
        if not target:
            dates = _overlap_dates(args.ticker, args.max_dates)
            target = dates[-1] if dates else None
        if target:
            r = run_temporal_archaeology_strict(
                args.ticker, target,
                max_source_dates=args.max_dates,
                n_components=args.n_components,
            )
            all_results["archaeology_strict"] = r
            with open(RESULTS_DIR / f"phase5c_archaeology_strict_{args.ticker}.json", "w") as f:
                json.dump(r, f, indent=2, default=str)


if __name__ == "__main__":
    main()
