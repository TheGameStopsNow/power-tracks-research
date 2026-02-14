#!/usr/bin/env python3
"""
Phase 6: Robustness Tests (Reviewer Feedback Remediation)
=========================================================
6A — Cross-Ticker NMF Placebo: Reconstruct ticker X equity from ticker Y options.
      If r drops significantly vs same-ticker (r≈1.0), rules out shared market shape.
6B — Out-of-Sample NMF Reconstruction: Fit NMF basis on days 1…K, reconstruct K+1…T.
      No refitting. If OOS r still significant, confirms genuine predictive power.
6C — Lead-Lag Placebo Shift: Offset options timestamps by +1s/+10s.
      If 50–100ms spike disappears, confirms real temporal structure.
6D — Impulse Response Kernel: Ridge regression h(τ) from options flow → equity returns.
      TimeSeriesSplit OOS R², permutation null for p-value.

Usage:
    python phase6_robustness.py --mode placebo-nmf
    python phase6_robustness.py --mode oos-nmf
    python phase6_robustness.py --mode placebo-leadlag
    python phase6_robustness.py --mode kernel
    python phase6_robustness.py --mode all
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Reuse infrastructure from existing phases
sys.path.insert(0, str(Path(__file__).parent))
from phase5_paradigm import (
    _load_equity_day,
    _load_options_day,
    _overlap_dates,
    _time_profile,
    _zncc,
)
from phase4_causal import (
    load_equity_trades,
    load_options_trades,
    compute_lead_lag,
)

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ===========================================================================
# 6A: Cross-Ticker NMF Placebo
# ===========================================================================

def run_cross_ticker_placebo(
    source_ticker: str,
    target_ticker: str,
    target_date: str,
    max_source_dates: int = 30,
    n_components: int = 5,
    n_bins: int = 64,
) -> dict:
    """
    Reconstruct target_ticker equity profile using source_ticker options.
    
    If r drops significantly vs same-ticker reconstruction (r≈1.0),
    this rules out the hypothesis that NMF is merely fitting shared
    market-wide intraday shape (the U-shape).
    """
    from sklearn.decomposition import NMF

    print(f"\n{'='*60}")
    print(f"6A: Cross-Ticker NMF Placebo")
    print(f"    Source options: {source_ticker}")
    print(f"    Target equity:  {target_ticker} ({target_date})")
    print(f"{'='*60}")

    # Load target equity profile
    try:
        eq_df = _load_equity_day(target_ticker, target_date)
    except FileNotFoundError:
        return {"error": f"No equity data for {target_ticker} on {target_date}"}

    target_profile = _time_profile(eq_df, n_bins)
    target_profile = np.clip(target_profile, 0, None)

    # Load source options profiles (from WRONG ticker)
    source_dates = _overlap_dates(source_ticker, max_source_dates * 2)
    if not source_dates:
        return {"error": f"No overlap dates for source {source_ticker}"}

    # Use middle chunk of available dates
    mid = len(source_dates) // 2
    use_dates = source_dates[max(0, mid - max_source_dates):mid + max_source_dates]

    source_profiles = []
    source_labels = []
    for d in use_dates:
        try:
            opts_df = _load_options_day(source_ticker, d)
            profile = _time_profile(opts_df, n_bins)
            profile = np.clip(profile, 0, None)
            if profile.sum() > 0:
                source_profiles.append(profile)
                source_labels.append(d)
        except FileNotFoundError:
            continue

    if len(source_profiles) < n_components:
        return {"error": f"Only {len(source_profiles)} source dates for {source_ticker}"}

    print(f"  Target profile: {len(eq_df)} equity trades")
    print(f"  Source profiles: {len(source_profiles)} {source_ticker} options days")

    W_source = np.array(source_profiles)

    # --- RAW NMF ---
    combined = np.vstack([W_source, target_profile.reshape(1, -1)]) + 1e-6
    n_comp = min(n_components, len(source_profiles))
    model = NMF(n_components=n_comp, init="nndsvd", max_iter=500, random_state=42)
    H = model.fit_transform(combined)
    W = model.components_
    reconstruction = H[-1, :] @ W
    r_raw = _zncc(target_profile, reconstruction)

    # --- RESIDUAL NMF ---
    mean_profile = W_source.mean(axis=0)
    source_residuals = W_source - mean_profile
    target_mean_source = mean_profile  # Note: using SOURCE ticker's mean
    target_residual = target_profile - target_mean_source

    all_residuals = np.vstack([source_residuals, target_residual.reshape(1, -1)])
    shift = abs(all_residuals.min()) + 1e-6
    all_residuals_shifted = all_residuals + shift

    model_resid = NMF(n_components=n_comp, init="nndsvd", max_iter=500, random_state=42)
    H_resid = model_resid.fit_transform(all_residuals_shifted)
    W_resid = model_resid.components_
    reconstruction_resid = H_resid[-1, :] @ W_resid - shift
    r_residual = _zncc(target_residual, reconstruction_resid)

    print(f"\n  === CROSS-TICKER PLACEBO RESULTS ===")
    print(f"  Raw ZNCC:      {r_raw:.4f}")
    print(f"  Residual ZNCC: {r_residual:.4f}")

    result = {
        "source_ticker": source_ticker,
        "target_ticker": target_ticker,
        "target_date": target_date,
        "r_raw_cross": round(r_raw, 4),
        "r_residual_cross": round(r_residual, 4),
        "n_sources": len(source_profiles),
        "n_components": n_comp,
    }
    return result


# ===========================================================================
# 6B: Out-of-Sample NMF Reconstruction
# ===========================================================================

def run_oos_nmf(
    ticker: str,
    n_bins: int = 64,
    n_components: int = 5,
    train_frac: float = 0.6,
) -> dict:
    """
    Fit NMF basis on the first train_frac of available dates.
    Reconstruct the remaining dates WITHOUT refitting.
    
    Reports in-sample and out-of-sample r values.
    """
    from sklearn.decomposition import NMF

    print(f"\n{'='*60}")
    print(f"6B: Out-of-Sample NMF Reconstruction — {ticker}")
    print(f"    Train fraction: {train_frac:.0%}")
    print(f"{'='*60}")

    all_dates = _overlap_dates(ticker, 200)
    if len(all_dates) < 10:
        return {"error": f"Only {len(all_dates)} overlap dates for {ticker}"}

    # Load all equity and options profiles
    equity_profiles = []
    options_profiles = []
    valid_dates = []

    for d in all_dates:
        try:
            eq_df = _load_equity_day(ticker, d)
            opts_df = _load_options_day(ticker, d)
            eq_prof = _time_profile(eq_df, n_bins)
            opts_prof = _time_profile(opts_df, n_bins)
            eq_prof = np.clip(eq_prof, 0, None)
            opts_prof = np.clip(opts_prof, 0, None)
            if eq_prof.sum() > 0 and opts_prof.sum() > 0:
                equity_profiles.append(eq_prof)
                options_profiles.append(opts_prof)
                valid_dates.append(d)
        except FileNotFoundError:
            continue

    N = len(valid_dates)
    if N < 10:
        return {"error": f"Only {N} valid dates for {ticker}"}

    split_idx = int(N * train_frac)
    print(f"  Total days: {N}, Train: {split_idx}, Test: {N - split_idx}")

    # === TRAIN: Fit NMF basis on options profiles days 1…K ===
    train_options = np.array(options_profiles[:split_idx]) + 1e-6
    n_comp = min(n_components, split_idx)
    model = NMF(n_components=n_comp, init="nndsvd", max_iter=500, random_state=42)
    model.fit(train_options)
    W_basis = model.components_  # (n_comp, n_bins)

    # === Reconstruct ALL equity profiles using frozen basis ===
    in_sample_r = []
    out_sample_r = []

    for i, eq_prof in enumerate(equity_profiles):
        # Project equity onto frozen basis: h = argmin ||eq - h·W||
        # Using non-negative least squares for consistency
        from scipy.optimize import nnls
        h, _ = nnls(W_basis.T, eq_prof)
        recon = h @ W_basis
        r = _zncc(eq_prof, recon)

        if i < split_idx:
            in_sample_r.append(r)
        else:
            out_sample_r.append(r)

    is_mean = float(np.mean(in_sample_r))
    oos_mean = float(np.mean(out_sample_r))
    oos_median = float(np.median(out_sample_r))
    oos_min = float(np.min(out_sample_r))

    print(f"\n  === OOS NMF RESULTS ===")
    print(f"  In-sample  mean r: {is_mean:.4f} (n={len(in_sample_r)})")
    print(f"  Out-sample mean r: {oos_mean:.4f} (n={len(out_sample_r)})")
    print(f"  Out-sample med  r: {oos_median:.4f}")
    print(f"  Out-sample min  r: {oos_min:.4f}")

    result = {
        "ticker": ticker,
        "n_train": split_idx,
        "n_test": N - split_idx,
        "n_components": n_comp,
        "is_mean_r": round(is_mean, 4),
        "oos_mean_r": round(oos_mean, 4),
        "oos_median_r": round(oos_median, 4),
        "oos_min_r": round(oos_min, 4),
        "oos_all_r": [round(r, 4) for r in out_sample_r],
        "is_all_r": [round(r, 4) for r in in_sample_r],
    }
    return result


# ===========================================================================
# 6C: Lead-Lag Placebo Shift
# ===========================================================================

def run_lead_lag_placebo(
    ticker: str,
    date_str: str,
    shifts_ms: list[int] = None,
    min_size: int = 20,
) -> dict:
    """
    Run lead-lag analysis with artificial shifts applied to options timestamps.
    
    If the 50–100ms response spike is real, it should:
    - Be present at shift=0 (original)
    - Disappear at shift=+1000ms and +10000ms
    
    This rules out timestamp alignment artifacts.
    """
    if shifts_ms is None:
        shifts_ms = [0, 1000, 5000, 10000]

    print(f"\n{'='*60}")
    print(f"6C: Lead-Lag Placebo Shift — {ticker} {date_str}")
    print(f"    Shifts: {shifts_ms} ms")
    print(f"{'='*60}")

    # Load data
    eq_df = load_equity_trades(ticker, date_str)
    opts_df = load_options_trades(ticker, date_str)

    if eq_df is None or opts_df is None:
        return {"error": f"Missing data for {ticker} on {date_str}"}
    if len(eq_df) == 0 or len(opts_df) == 0:
        return {"error": f"Empty data for {ticker} on {date_str}"}

    results_by_shift = {}

    for shift in shifts_ms:
        print(f"\n  --- Shift: +{shift}ms ---")
        # Create shifted copy of options trades
        opts_shifted = opts_df.copy()
        if shift > 0:
            shift_ns = shift * 1_000_000  # ms to ns
            opts_shifted["ts"] = opts_shifted["ts"] + pd.Timedelta(nanoseconds=shift_ns)

        ll_result = compute_lead_lag(eq_df, opts_shifted, min_size=min_size)
        results_by_shift[str(shift)] = ll_result

    # Compare response ratios at 50ms and 100ms across shifts
    print(f"\n  === PLACEBO SHIFT COMPARISON ===")
    print(f"  {'Shift':>10}  {'50ms ratio':>12}  {'100ms ratio':>12}  {'500ms ratio':>12}")
    for shift in shifts_ms:
        r = results_by_shift[str(shift)]
        r50 = r.get("50", {}).get("response_ratio", "N/A")
        r100 = r.get("100", {}).get("response_ratio", "N/A")
        r500 = r.get("500", {}).get("response_ratio", "N/A")
        print(f"  +{shift:>8}ms  {r50:>12}  {r100:>12}  {r500:>12}")

    result = {
        "ticker": ticker,
        "date": date_str,
        "shifts_ms": shifts_ms,
        "results_by_shift": results_by_shift,
    }
    return result


# ===========================================================================
# 6D: Impulse Response Kernel (Ridge Regression)
# ===========================================================================

def lag_matrix(x: np.ndarray, L: int) -> np.ndarray:
    """
    Build lag matrix from feature array x.
    x: (T, F) features → returns (T-L, F*(L+1))
    """
    T, F = x.shape
    X = []
    for tau in range(L + 1):
        X.append(x[L - tau:T - tau])
    return np.concatenate(X, axis=1)


def run_impulse_kernel(
    ticker: str,
    L: int = 60,
    alpha: float = 1.0,
    n_permutations: int = 200,
    n_bins: int = 64,
) -> dict:
    """
    Estimate impulse response kernel h(τ) via Ridge regression:
        y_t = Σ h(τ) · x_{t-τ} + ε_t
    
    Where:
        x_t = options volume in 60-second bars (binned)
        y_t = equity return in matching bars
    
    Uses TimeSeriesSplit for OOS R², permutation null for p-value.
    """
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import TimeSeriesSplit

    print(f"\n{'='*60}")
    print(f"6D: Impulse Response Kernel — {ticker}")
    print(f"    Max lag: {L} bars, Alpha: {alpha}")
    print(f"{'='*60}")

    # Collect all overlapping dates
    all_dates = _overlap_dates(ticker, 100)
    if len(all_dates) < 5:
        return {"error": f"Only {len(all_dates)} overlap dates"}

    # Build concatenated time series of (options_volume, equity_returns) per bar
    all_x = []  # options volume per bar
    all_y = []  # equity returns per bar

    for d in all_dates:
        try:
            eq_df = _load_equity_day(ticker, d)
            opts_df = _load_options_day(ticker, d)
        except FileNotFoundError:
            continue

        # Bin both into n_bins intervals per day
        eq_profile = _time_profile(eq_df, n_bins)

        # Compute equity returns: use price-based returns if available
        if "eq_price" in eq_df.columns:
            eq_ts = eq_df["ts"].values.astype("int64")
            eq_prices = eq_df["eq_price"].values
            # Bin into n_bins intervals
            t_min, t_max = eq_ts.min(), eq_ts.max()
            if t_max == t_min:
                continue
            bin_edges = np.linspace(t_min, t_max, n_bins + 1)
            bar_returns = np.zeros(n_bins)
            for b in range(n_bins):
                mask = (eq_ts >= bin_edges[b]) & (eq_ts < bin_edges[b + 1])
                if mask.sum() >= 2:
                    p_first = eq_prices[mask][0]
                    p_last = eq_prices[mask][-1]
                    if p_first > 0:
                        bar_returns[b] = np.log(p_last / p_first)
        else:
            # Use volume changes as proxy
            bar_returns = np.diff(np.concatenate([[0], eq_profile]))

        opts_profile = _time_profile(opts_df, n_bins)

        all_x.append(opts_profile)
        all_y.append(bar_returns)

    if len(all_x) < 5:
        return {"error": "Insufficient data"}

    # Concatenate across days
    X = np.concatenate(all_x).reshape(-1, 1)  # (T, 1)
    Y = np.concatenate(all_y)                  # (T,)

    T = len(Y)
    print(f"  Total bars: {T} ({len(all_x)} days × {n_bins} bins)")

    if T <= L + 10:
        return {"error": f"Not enough bars ({T}) for lag {L}"}

    # Build lag matrix
    X_lag = lag_matrix(X, L)
    Y_trim = Y[L:]

    # === OOS cross-validation ===
    tscv = TimeSeriesSplit(n_splits=5)
    oos_scores = []
    for train_idx, test_idx in tscv.split(X_lag):
        model = Ridge(alpha=alpha, fit_intercept=True)
        model.fit(X_lag[train_idx], Y_trim[train_idx])
        y_hat = model.predict(X_lag[test_idx])
        y_test = Y_trim[test_idx]
        ss_res = np.sum((y_test - y_hat) ** 2)
        ss_tot = np.sum((y_test - np.mean(y_test)) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
        oos_scores.append(r2)

    oos_r2 = float(np.nanmean(oos_scores))

    # === Full model for kernel shape ===
    full_model = Ridge(alpha=alpha, fit_intercept=True)
    full_model.fit(X_lag, Y_trim)
    kernel = full_model.coef_.ravel()  # (L+1,) — the impulse response

    # === Permutation null ===
    print(f"  Running {n_permutations} permutation shuffles...")
    perm_scores = []
    rng = np.random.RandomState(42)
    for p in range(n_permutations):
        # Shuffle X labels (break temporal structure)
        perm_idx = rng.permutation(len(X_lag))
        X_perm = X_lag[perm_idx]

        perm_oos = []
        for train_idx, test_idx in tscv.split(X_perm):
            m = Ridge(alpha=alpha, fit_intercept=True)
            m.fit(X_perm[train_idx], Y_trim[train_idx])
            y_hat = m.predict(X_perm[test_idx])
            y_test = Y_trim[test_idx]
            ss_res = np.sum((y_test - y_hat) ** 2)
            ss_tot = np.sum((y_test - np.mean(y_test)) ** 2)
            r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
            perm_oos.append(r2)
        perm_scores.append(float(np.nanmean(perm_oos)))

    perm_p = float(np.mean([s >= oos_r2 for s in perm_scores]))

    print(f"\n  === IMPULSE RESPONSE KERNEL RESULTS ===")
    print(f"  OOS R²:           {oos_r2:.6f}")
    print(f"  Permutation p:    {perm_p:.4f}")
    print(f"  Perm mean OOS R²: {np.mean(perm_scores):.6f}")
    print(f"  Kernel peak lag:  {np.argmax(np.abs(kernel))}")
    print(f"  Kernel peak val:  {kernel[np.argmax(np.abs(kernel))]:.6f}")

    result = {
        "ticker": ticker,
        "L": L,
        "alpha": alpha,
        "oos_r2": round(oos_r2, 6),
        "oos_scores": [round(s, 6) for s in oos_scores],
        "perm_p_value": round(perm_p, 4),
        "perm_mean_r2": round(float(np.mean(perm_scores)), 6),
        "n_permutations": n_permutations,
        "n_bars": T,
        "n_days": len(all_x),
        "kernel_peak_lag": int(np.argmax(np.abs(kernel))),
        "kernel_peak_value": round(float(kernel[np.argmax(np.abs(kernel))]), 6),
        "kernel": [round(float(k), 6) for k in kernel],
    }
    return result


# ===========================================================================
# CLI
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Phase 6: Robustness Tests")
    parser.add_argument(
        "--mode",
        choices=["placebo-nmf", "oos-nmf", "placebo-leadlag", "kernel", "all"],
        default="all",
    )
    args = parser.parse_args()

    # === 6A: Cross-Ticker NMF Placebo ===
    if args.mode in ("placebo-nmf", "all"):
        placebo_pairs = [
            ("AAPL", "GME"),   # Reconstruct GME equity from AAPL options
            ("AAPL", "TSLA"),  # Reconstruct TSLA equity from AAPL options
            ("GME", "AAPL"),   # Reconstruct AAPL equity from GME options
        ]
        # Also run same-ticker controls for comparison
        same_ticker_controls = [
            ("GME", "GME"),
            ("TSLA", "TSLA"),
            ("AAPL", "AAPL"),
        ]

        all_results = []

        # Find a usable target date for each target ticker
        for source, target in placebo_pairs + same_ticker_controls:
            dates = _overlap_dates(target, 50)
            if not dates:
                print(f"  No dates for {target}, skipping")
                continue
            # Use middle date
            target_date = dates[len(dates) // 2]
            r = run_cross_ticker_placebo(source, target, target_date)
            all_results.append(r)

        out_path = RESULTS_DIR / "phase6a_cross_ticker_placebo.json"
        with open(out_path, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"\nSaved: {out_path}")

    # === 6B: OOS NMF ===
    if args.mode in ("oos-nmf", "all"):
        oos_tickers = ["AAPL", "GME", "TSLA", "PLTR", "CHWY", "DJT", "SOFI"]
        all_results = []
        for t in oos_tickers:
            r = run_oos_nmf(t)
            all_results.append(r)

        out_path = RESULTS_DIR / "phase6b_oos_nmf.json"
        with open(out_path, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"\nSaved: {out_path}")

    # === 6C: Lead-Lag Placebo ===
    if args.mode in ("placebo-leadlag", "all"):
        # Use tickers with both equity and options data
        test_cases = [
            ("TSLA", None),   # date will be auto-detected
            ("GME", None),
            ("AAPL", None),
        ]
        all_results = []
        for ticker, date in test_cases:
            if date is None:
                dates = _overlap_dates(ticker, 50)
                if dates:
                    date = dates[len(dates) // 2]
                else:
                    print(f"  No overlap dates for {ticker}")
                    continue
            r = run_lead_lag_placebo(ticker, date)
            all_results.append(r)

        out_path = RESULTS_DIR / "phase6c_leadlag_placebo.json"
        with open(out_path, "w") as f:
            json.dump(all_results, f, indent=2, default=str)
        print(f"\nSaved: {out_path}")

    # === 6D: Impulse Response Kernel ===
    if args.mode in ("kernel", "all"):
        kernel_tickers = ["TSLA", "GME", "AAPL", "MSFT", "DJT"]
        all_results = []
        for t in kernel_tickers:
            r = run_impulse_kernel(t, L=60, alpha=1.0, n_permutations=200)
            all_results.append(r)

        out_path = RESULTS_DIR / "phase6d_impulse_kernel.json"
        with open(out_path, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
