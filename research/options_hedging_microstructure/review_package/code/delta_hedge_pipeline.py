#!/usr/bin/env python3
"""
Phase 98d: Delta Hedge Pipeline
=================================
Convert OPTIONS FLOW into PREDICTED EQUITY BURST SHAPES via Black-Scholes
delta hedging mechanics, then compare against ACTUAL OBSERVED BURSTS.

Hypothesis: Burst trade patterns in GME equity are mechanically caused by
market maker delta hedging of options positions.

Pipeline:
  Options Trade → BS Delta → Hedge Shares → Predicted Burst Shape
  Actual Equity Trades → Observed Burst Shape
  Compare: cross-correlation, lag sweep, 2D ZNCC
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import streamlit as st
from scipy.stats import norm as sp_norm
from scipy.signal import correlate

os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw" / "thetadata" / "trades"
EQUITY_DIR = Path(__file__).parent.parent.parent / "data" / "raw" / "polygon" / "trades"
BURST_DIR = (
    Path(__file__).parent.parent.parent
    / "docs"
    / "analysis"
    / "diagnostics"
    / "edgx_bursts"
)

# Import existing loaders
sys.path.insert(0, str(Path(__file__).parent.parent / "phase94_deep_sweep"))
sys.path.insert(0, str(Path(__file__).parent))

from shape_match import load_trades, get_available_dates


# ============================================================================
# Data Loading
# ============================================================================


@st.cache_data
def load_equity_trades(ticker: str, date_str: str) -> pd.DataFrame:
    """
    Load equity (stock) trades from Polygon parquet files.
    Returns DataFrame with timestamp, price, size columns.
    """
    # Polygon uses YYYY-MM-DD format
    date_hyphen = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    path = EQUITY_DIR / f"symbol={ticker}" / f"date={date_hyphen}"
    if not path.exists():
        return pd.DataFrame()

    frames = []
    for f in path.glob("*.parquet"):
        try:
            df = pd.read_parquet(f)
            frames.append(df)
        except (PermissionError, OSError):
            continue

    if not frames:
        return pd.DataFrame()

    trades = pd.concat(frames, ignore_index=True)
    trades["timestamp"] = pd.to_datetime(trades["timestamp"], utc=True)
    trades["ts"] = trades["timestamp"]
    trades = trades.sort_values("timestamp").reset_index(drop=True)
    return trades


@st.cache_data
def load_burst_points(date_str: str = "2024-05-17") -> pd.DataFrame:
    """Load normalized burst point cloud for a given date."""
    path = BURST_DIR / "burst_point_features.parquet"
    if not path.exists():
        return pd.DataFrame()
    bp = pd.read_parquet(path)
    # burst_point_features.parquet has aggregate features, not points
    # We need the raw burst points from the CSV or another source
    # Try loading from the scatter data
    csv_path = BURST_DIR / f"burst_point_features_{date_str.replace('-', '')}.csv"
    if csv_path.exists():
        return pd.read_csv(csv_path)

    # Fall back to the shape_match_2d loader
    from shape_match_2d import load_burst_points as _load_burst

    return _load_burst(date_str)


# ============================================================================
# Black-Scholes Delta Calculator
# ============================================================================


def bs_delta(
    S: float | np.ndarray,
    K: float | np.ndarray,
    T: float | np.ndarray,
    sigma: float | np.ndarray,
    right: str | np.ndarray,
    r: float = 0.05,
) -> np.ndarray:
    """
    Black-Scholes delta for European options.

    Parameters
    ----------
    S : stock price
    K : strike price
    T : time to expiration in years
    sigma : implied volatility
    right : 'C' for call, 'P' for put
    r : risk-free rate

    Returns
    -------
    delta : per-contract delta (between -1 and 1)
    """
    S = np.asarray(S, dtype=np.float64)
    K = np.asarray(K, dtype=np.float64)
    T = np.asarray(T, dtype=np.float64)
    sigma = np.asarray(sigma, dtype=np.float64)

    # Clamp T to avoid division by zero
    T = np.maximum(T, 1e-6)
    sigma = np.maximum(sigma, 0.01)

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))

    # Vectorize right handling
    if isinstance(right, str):
        if right.upper().startswith("C"):
            return sp_norm.cdf(d1)
        else:
            return sp_norm.cdf(d1) - 1.0
    else:
        right_arr = np.asarray(right)
        delta = np.where(
            np.char.upper(np.char.encode(right_arr, "ascii").astype(str)).astype(str)
            == "C",
            sp_norm.cdf(d1),
            sp_norm.cdf(d1) - 1.0,
        )
        return delta


def bs_delta_vectorized(
    S: np.ndarray,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    is_call: np.ndarray,
    r: float = 0.05,
) -> np.ndarray:
    """
    Fast vectorized Black-Scholes delta.

    Parameters
    ----------
    S, K, T, sigma : arrays of same length
    is_call : boolean array (True for calls, False for puts)
    r : risk-free rate

    Returns
    -------
    delta : array of deltas
    """
    T = np.maximum(T, 1e-6)
    sigma = np.maximum(sigma, 0.01)
    S = np.maximum(S, 0.01)
    K = np.maximum(K, 0.01)

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    call_delta = sp_norm.cdf(d1)

    delta = np.where(is_call, call_delta, call_delta - 1.0)
    return delta


def estimate_iv_from_price(
    option_price: float,
    S: float,
    K: float,
    T: float,
    right: str,
    r: float = 0.05,
    max_iter: int = 50,
) -> float:
    """
    Back-solve implied volatility from option price using Newton's method.
    Returns estimated IV or fallback value if Newton fails.
    """
    if T <= 0 or option_price <= 0 or S <= 0 or K <= 0:
        return 0.80  # fallback

    sigma = 0.50  # initial guess
    for _ in range(max_iter):
        d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)

        if right.upper().startswith("C"):
            price_est = S * sp_norm.cdf(d1) - K * np.exp(-r * T) * sp_norm.cdf(d2)
        else:
            price_est = K * np.exp(-r * T) * sp_norm.cdf(-d2) - S * sp_norm.cdf(-d1)

        diff = price_est - option_price
        # Vega
        vega = S * np.sqrt(T) * sp_norm.pdf(d1)
        if abs(vega) < 1e-12:
            break

        sigma -= diff / vega
        sigma = max(sigma, 0.01)
        sigma = min(sigma, 5.0)

        if abs(diff) < 1e-6:
            break

    return sigma


# ============================================================================
# Delta Exposure Timeline
# ============================================================================


def compute_delta_exposure(
    opts: pd.DataFrame,
    equity: pd.DataFrame,
    date_str: str,
    fixed_iv: float | None = None,
) -> pd.DataFrame:
    """
    Compute hedge-share demand timeline from options trades.

    For each options trade:
    1. Find stock price S at that timestamp (asof join from equity trades)
    2. Compute time-to-expiration T
    3. Estimate IV (from option price or use fixed)
    4. Compute BS delta
    5. Compute hedge_shares = size × 100 × delta

    Market maker convention:
    - MM sells to fill → hedges opposite
    - Sell call → short delta → BUY stock → positive hedge
    - Sell put  → long delta  → SELL stock → negative hedge

    Returns DataFrame with columns:
        timestamp, strike, right, size, price, delta, hedge_shares, cum_hedge
    """
    if opts.empty or equity.empty:
        return pd.DataFrame()

    # Parse timestamps
    opts = opts.copy()
    opts["ts"] = pd.to_datetime(opts["timestamp"], format="ISO8601", utc=True)
    opts = opts.sort_values("ts").reset_index(drop=True)

    equity = equity.copy()
    equity["ts"] = pd.to_datetime(equity["timestamp"], utc=True)
    equity = equity.sort_values("ts").reset_index(drop=True)

    # Asof merge: for each options trade, find nearest prior equity trade price
    merged = pd.merge_asof(
        opts[["ts", "strike", "right", "size", "price", "expiration"]],
        equity[["ts", "price"]].rename(columns={"price": "stock_price"}),
        on="ts",
        direction="backward",
    )

    # Fill any missing stock prices with forward fill then median
    merged["stock_price"] = merged["stock_price"].ffill()
    if merged["stock_price"].isna().any():
        merged["stock_price"] = merged["stock_price"].fillna(equity["price"].median())

    # Compute time to expiration
    # Handle multiple date formats (YYYY-MM-DD, YYYYMMDD)
    exp_col = "expiry" if "expiry" in merged.columns else "expiration"
    try:
        exp_dates = pd.to_datetime(merged[exp_col], format="ISO8601", utc=True)
    except (ValueError, TypeError):
        try:
            exp_dates = pd.to_datetime(merged[exp_col], format="%Y%m%d", utc=True)
        except (ValueError, TypeError):
            exp_dates = pd.to_datetime(merged[exp_col], format="mixed", utc=True)
    merged["T"] = (exp_dates - merged["ts"]).dt.total_seconds() / (365.25 * 86400)
    merged["T"] = merged["T"].clip(lower=1e-6)

    # Compute IV
    if fixed_iv is not None:
        merged["iv"] = fixed_iv
    else:
        # Batch IV estimation (slow but accurate)
        ivs = []
        for _, row in merged.iterrows():
            iv = estimate_iv_from_price(
                row["price"], row["stock_price"], row["strike"], row["T"], row["right"]
            )
            ivs.append(iv)
        merged["iv"] = ivs

    # Vectorized delta computation
    is_call = merged["right"].str.upper().str.startswith("C")
    merged["delta"] = bs_delta_vectorized(
        merged["stock_price"].values,
        merged["strike"].values,
        merged["T"].values,
        merged["iv"].values,
        is_call.values,
    )

    # Hedge shares (market maker perspective)
    # MM sells to customer → hedges by going opposite
    # Sell call (negative delta for MM) → buy stock (positive hedge)
    # Sell put  (positive delta for MM) → sell stock (negative hedge)
    # Net: hedge_shares = -1 × size × 100 × delta  (but we want directional pressure)
    # Actually: if MM sells a call with delta 0.5, they buy 50 shares per contract
    # So hedge = size × 100 × |delta| for calls, hedge = -size × 100 × |delta| for puts
    # Simpler: hedge_shares = size × 100 × delta (sign already correct for MM hedge)
    merged["hedge_shares"] = merged["size"] * 100 * merged["delta"]

    # Cumulative hedge demand
    merged["cum_hedge"] = merged["hedge_shares"].cumsum()

    # Absolute hedge (total shares traded regardless of direction)
    merged["abs_hedge"] = merged["hedge_shares"].abs()
    merged["cum_abs_hedge"] = merged["abs_hedge"].cumsum()

    return merged


# ============================================================================
# Expiration Classification & Gamma
# ============================================================================

EXP_BUCKETS = ["0DTE", "Weekly", "Monthly", "LEAPS"]
EXP_COLORS = {"0DTE": "#ff4444", "Weekly": "#ff9900", "Monthly": "#44aaff", "LEAPS": "#aa44ff", "ALL": "#aaaaaa"}


def classify_expiration(dte_days: pd.Series) -> pd.Series:
    """
    Classify options by days-to-expiration.
    0DTE: 0 days, Weekly: 1-7 days, Monthly: 8-45 days, LEAPS: >45 days
    """
    return pd.cut(
        dte_days,
        bins=[-1, 0, 7, 45, 9999],
        labels=["0DTE", "Weekly", "Monthly", "LEAPS"],
    ).astype(str)


def compute_gamma_vectorized(
    S: np.ndarray,
    K: np.ndarray,
    T: np.ndarray,
    sigma: np.ndarray,
    r: float = 0.05,
) -> np.ndarray:
    """
    Vectorized Black-Scholes gamma.
    Gamma = N'(d1) / (S * sigma * sqrt(T))
    """
    T = np.maximum(T, 1e-6)
    sigma = np.maximum(sigma, 0.01)
    S = np.maximum(S, 0.01)
    K = np.maximum(K, 0.01)

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return sp_norm.pdf(d1) / (S * sigma * np.sqrt(T))


def add_expiration_and_gamma(delta_df: pd.DataFrame) -> pd.DataFrame:
    """
    Enrich delta_df with expiration class, gamma, and gamma-weighted hedge shares.
    """
    df = delta_df.copy()

    # DTE in days
    df["dte_days"] = (df["T"] * 365.25).round().astype(int)
    df["exp_class"] = classify_expiration(df["dte_days"])

    # Gamma
    df["gamma"] = compute_gamma_vectorized(
        df["stock_price"].values,
        df["strike"].values,
        df["T"].values,
        df["iv"].values,
    )

    # Gamma-weighted hedge: hedge_shares * gamma
    # This captures the RE-HEDGING pressure: high gamma means small price
    # moves cause large delta changes, requiring more frequent hedging
    df["gamma_hedge"] = df["size"] * 100 * df["gamma"]
    df["abs_gamma_hedge"] = df["gamma_hedge"].abs()

    return df


def run_stratified_lag_analysis(
    delta_df: pd.DataFrame,
    equity_df: pd.DataFrame,
    n_bins: int = 256,
    max_lag: int = 80,
    weighting: str = "abs_hedge",
) -> dict:
    """
    Run cross-correlation for each expiration bucket independently.

    Parameters
    ----------
    weighting : str
        Which column to use for the hedge profile.
        'abs_hedge' = delta-based, 'abs_gamma_hedge' = gamma-weighted

    Returns
    -------
    dict with keys:
        'equity_profile': the equity volume profile
        'buckets': dict[bucket_name -> {
            'profile': hedge profile,
            'lags': lag array,
            'corrs': correlation array,
            'peak_lag': optimal lag,
            'peak_corr': peak correlation value,
            'zncc': zero-lag ZNCC,
            'count': number of trades,
            'total_exposure': total abs hedge volume,
            'mean_gamma': average gamma,
        }]
    """
    equity_profile = time_bin_profile(
        equity_df["ts"], equity_df["size"], n_bins, agg="sum"
    )

    results = {"equity_profile": equity_profile, "buckets": {}}

    for bucket in EXP_BUCKETS:
        sub = delta_df[delta_df["exp_class"] == bucket]
        if len(sub) < 10:
            continue

        profile = time_bin_profile(
            sub["ts"], sub[weighting], n_bins, agg="sum"
        )

        lags, corrs = cross_correlate_profiles(profile, equity_profile, max_lag)
        peak_idx = np.argmax(corrs)

        results["buckets"][bucket] = {
            "profile": profile,
            "lags": lags,
            "corrs": corrs,
            "peak_lag": int(lags[peak_idx]),
            "peak_corr": float(corrs[peak_idx]),
            "zncc": zncc_1d(profile, equity_profile),
            "count": len(sub),
            "total_exposure": float(sub[weighting].sum()),
            "mean_gamma": float(sub["gamma"].mean()) if "gamma" in sub.columns else 0,
        }

    # Also run "combined" (all buckets)
    all_profile = time_bin_profile(
        delta_df["ts"], delta_df[weighting], n_bins, agg="sum"
    )
    lags, corrs = cross_correlate_profiles(all_profile, equity_profile, max_lag)
    peak_idx = np.argmax(corrs)
    results["buckets"]["ALL"] = {
        "profile": all_profile,
        "lags": lags,
        "corrs": corrs,
        "peak_lag": int(lags[peak_idx]),
        "peak_corr": float(corrs[peak_idx]),
        "zncc": zncc_1d(all_profile, equity_profile),
        "count": len(delta_df),
        "total_exposure": float(delta_df[weighting].sum()),
        "mean_gamma": float(delta_df["gamma"].mean()) if "gamma" in delta_df.columns else 0,
    }

    return results


# ============================================================================
# Stratified Visualization
# ============================================================================


def render_stratified_dashboard(
    strat_results: dict,
    n_bins: int = 256,
    weighting: str = "abs_hedge",
) -> plt.Figure:
    """
    Multi-panel visualization of expiration-stratified lag analysis.

    Top row: Per-bucket hedge profiles overlaid with equity profile
    Bottom row: Per-bucket cross-correlation curves
    """
    buckets = strat_results["buckets"]
    n_buckets = len(buckets)
    if n_buckets == 0:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No data", ha="center", va="center", color="white")
        return fig

    fig, axes = plt.subplots(2, n_buckets, figsize=(6 * n_buckets, 10))
    fig.patch.set_facecolor("#111")

    if n_buckets == 1:
        axes = axes.reshape(2, 1)

    eq_profile = strat_results["equity_profile"]
    eq_norm = eq_profile / (eq_profile.max() or 1)
    x = np.linspace(0, 1, n_bins)

    weight_label = "Δ-hedge" if weighting == "abs_hedge" else "γ-hedge"

    for i, (bucket, data) in enumerate(buckets.items()):
        ax_top = axes[0, i]
        ax_bot = axes[1, i]

        for ax in [ax_top, ax_bot]:
            ax.set_facecolor("black")
            ax.tick_params(colors="white", labelsize=8)
            for s in ax.spines.values():
                s.set_color("#333")

        color = EXP_COLORS.get(bucket, "#ffffff")
        h_profile = data["profile"]
        h_norm = h_profile / (h_profile.max() or 1)

        # Top: profiles overlay
        ax_top.bar(x, eq_norm, width=1.0 / n_bins, color="orange", alpha=0.3, edgecolor="none", label="Equity")
        ax_top.bar(x, h_norm, width=1.0 / n_bins, color=color, alpha=0.6, edgecolor="none", label=f"{bucket} {weight_label}")
        ax_top.set_title(
            f"{bucket}: {data['count']:,} trades\nZNCC={data['zncc']:.3f}",
            color="white", fontsize=11, fontweight="bold",
        )
        ax_top.legend(facecolor="#222", edgecolor="#555", labelcolor="white", fontsize=7, loc="upper right")
        if i == 0:
            ax_top.set_ylabel("Normalized Volume", color="white", fontsize=9)

        # Bottom: cross-correlation
        ax_bot.plot(data["lags"], data["corrs"], color=color, linewidth=1.5)
        ax_bot.fill_between(data["lags"], data["corrs"], alpha=0.2, color=color)
        ax_bot.axhline(0, color="gray", linewidth=0.5, linestyle="--")
        ax_bot.axvline(data["peak_lag"], color="yellow", linewidth=1, linestyle="--", alpha=0.8)
        ax_bot.scatter([data["peak_lag"]], [data["peak_corr"]], color="yellow", s=60, zorder=5)
        ax_bot.set_title(
            f"Peak r={data['peak_corr']:.3f} @ lag={data['peak_lag']}",
            color="white", fontsize=10, fontweight="bold",
        )
        ax_bot.set_xlabel("Lag (bins)", color="white", fontsize=9)
        if i == 0:
            ax_bot.set_ylabel("Correlation", color="white", fontsize=9)

    fig.suptitle(
        f"Expiration-Stratified Lag Analysis ({weight_label})",
        color="white", fontsize=15, fontweight="bold",
    )
    fig.tight_layout()
    return fig


def render_gamma_heatmap(
    delta_df: pd.DataFrame,
    n_bins: int = 128,
) -> plt.Figure:
    """
    2D heatmap: Time × Strike colored by gamma exposure.
    Shows WHERE the gamma is concentrated throughout the day.
    """
    fig, axes = plt.subplots(1, 2, figsize=(20, 7))
    fig.patch.set_facecolor("#111")

    for ax in axes:
        ax.set_facecolor("black")
        ax.tick_params(colors="white", labelsize=9)
        for s in ax.spines.values():
            s.set_color("#333")

    # Normalize time
    t_min, t_max = delta_df["ts"].min(), delta_df["ts"].max()
    t_norm = (delta_df["ts"] - t_min).dt.total_seconds() / (t_max - t_min).total_seconds()

    # Strike range
    s_min, s_max = delta_df["strike"].min(), delta_df["strike"].max()
    s_norm = (delta_df["strike"] - s_min) / (s_max - s_min + 1e-9)

    # Gamma exposure heatmap
    ti = np.clip((t_norm * n_bins).astype(int), 0, n_bins - 1)
    si = np.clip((s_norm * n_bins).astype(int), 0, n_bins - 1)

    gamma_grid = np.zeros((n_bins, n_bins))
    np.add.at(gamma_grid, (si.values, ti.values), (delta_df["gamma"] * delta_df["size"] * 100).values)

    # Delta exposure heatmap
    delta_grid = np.zeros((n_bins, n_bins))
    np.add.at(delta_grid, (si.values, ti.values), delta_df["abs_hedge"].values)

    from matplotlib.colors import LogNorm

    for ax, grid, title, cmap in [
        (axes[0], gamma_grid, "Gamma Exposure (Strike × Time)", "hot"),
        (axes[1], delta_grid, "Delta Hedge Volume (Strike × Time)", "YlOrRd"),
    ]:
        grid_plot = grid.copy()
        grid_plot[grid_plot <= 0] = np.nan
        vmin_val = np.nanmin(grid_plot[np.isfinite(grid_plot) & (grid_plot > 0)]) if np.any(np.isfinite(grid_plot) & (grid_plot > 0)) else 1
        vmax_val = np.nanmax(grid_plot[np.isfinite(grid_plot)]) if np.any(np.isfinite(grid_plot)) else 1
        im = ax.imshow(
            grid_plot,
            aspect="auto",
            origin="lower",
            cmap=cmap,
            norm=LogNorm(vmin=max(vmin_val, 1), vmax=max(vmax_val, 2)),
        )
        ax.set_title(title, color="white", fontsize=12, fontweight="bold")
        ax.set_xlabel("Time →", color="white")
        ax.set_ylabel("Strike →", color="white")

        # Add strike labels
        n_labels = 6
        strikes = np.linspace(s_min, s_max, n_labels)
        ax.set_yticks(np.linspace(0, n_bins - 1, n_labels))
        ax.set_yticklabels([f"${s:.0f}" for s in strikes])

        plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    fig.suptitle(
        "Gamma & Delta Exposure Heatmap",
        color="white", fontsize=14, fontweight="bold",
    )
    fig.tight_layout()
    return fig


# ============================================================================
# Cross-Day & Position Reconstruction Engines
# ============================================================================


def get_trading_day_offset(date_str: str, offset: int, available_dates: list[str]) -> str | None:
    """
    Get the trading day that is `offset` trading days from `date_str`.
    Negative offset = past, positive = future.
    """
    if date_str not in available_dates:
        return None
    idx = available_dates.index(date_str)
    target_idx = idx + offset
    if 0 <= target_idx < len(available_dates):
        return available_dates[target_idx]
    return None


def compute_day_profile(
    ticker: str,
    date_str: str,
    source: str = "options",
    n_bins: int = 64,
    fixed_iv: float = 0.80,
    weighting: str = "abs_hedge",
) -> np.ndarray | None:
    """
    Compute a single-day hedge or equity profile.

    source: 'options' -> delta hedge profile, 'equity' -> volume profile
    """
    if source == "equity":
        eq = load_equity_trades(ticker, date_str)
        if eq.empty or len(eq) < 10:
            return None
        return time_bin_profile(eq["ts"], eq["size"], n_bins, agg="sum")
    else:
        opts = load_trades(ticker, [date_str])
        eq = load_equity_trades(ticker, date_str)
        if opts.empty or eq.empty or len(opts) < 10:
            return None
        delta_df = compute_delta_exposure(opts, eq, date_str, fixed_iv=fixed_iv)
        if delta_df.empty:
            return None
        enriched = add_expiration_and_gamma(delta_df)
        return time_bin_profile(enriched["ts"], enriched[weighting], n_bins, agg="sum")


def compute_cross_day_matrix(
    ticker: str,
    equity_dates: list[str],
    options_dates: list[str],
    day_offsets: list[int] | None = None,
    n_bins: int = 64,
    fixed_iv: float = 0.80,
    weighting: str = "abs_hedge",
    max_lag_bins: int = 30,
    progress_callback=None,
) -> dict:
    """
    Cross-day correlation matrix.

    For each equity day, correlate its burst profile against the options
    hedge profile from N days prior (or after).

    Returns dict with 'matrix' (DataFrame), 'zncc_by_offset', 'peak_by_offset',
    'n_valid', and 'detail' (per-pair results).
    """
    if day_offsets is None:
        day_offsets = [-60, -30, -14, -7, -5, -3, -2, -1, 0, 1, 3, 7, 14]

    sorted_opt_dates = sorted(options_dates)
    results = {
        "zncc_by_offset": {},
        "peak_by_offset": {},
        "n_valid": {},
        "detail": [],
    }

    total_steps = len(equity_dates) * len(day_offsets)
    step = 0

    offset_corrs = {off: [] for off in day_offsets}
    offset_zncc = {off: [] for off in day_offsets}
    offset_peak = {off: [] for off in day_offsets}

    for eq_date in equity_dates:
        eq_profile = compute_day_profile(ticker, eq_date, "equity", n_bins)
        if eq_profile is None:
            step += len(day_offsets)
            continue

        for offset in day_offsets:
            step += 1
            if progress_callback:
                progress_callback(step / total_steps)

            opt_date = get_trading_day_offset(eq_date, offset, sorted_opt_dates)
            if opt_date is None:
                continue

            opt_profile = compute_day_profile(
                ticker, opt_date, "options", n_bins, fixed_iv, weighting
            )
            if opt_profile is None:
                continue

            lags, corrs = cross_correlate_profiles(opt_profile, eq_profile, max_lag_bins)
            zncc = zncc_1d(opt_profile, eq_profile)
            peak_idx = np.argmax(corrs)

            record = {
                "eq_date": eq_date,
                "opt_date": opt_date,
                "offset": offset,
                "zncc": zncc,
                "peak_corr": float(corrs[peak_idx]),
                "peak_lag": int(lags[peak_idx]),
            }
            results["detail"].append(record)

            offset_corrs[offset].append(corrs)
            offset_zncc[offset].append(zncc)
            offset_peak[offset].append((float(corrs[peak_idx]), int(lags[peak_idx])))

    # Aggregate
    for offset in day_offsets:
        if offset_zncc[offset]:
            results["zncc_by_offset"][offset] = float(np.mean(offset_zncc[offset]))
            peaks = offset_peak[offset]
            results["peak_by_offset"][offset] = (
                float(np.mean([p[0] for p in peaks])),
                float(np.mean([p[1] for p in peaks])),
            )
            results["n_valid"][offset] = len(offset_zncc[offset])
        else:
            results["zncc_by_offset"][offset] = None
            results["peak_by_offset"][offset] = (None, None)
            results["n_valid"][offset] = 0

    # Build correlation matrix (offset x lag)
    lag_range = np.arange(-max_lag_bins, max_lag_bins + 1)
    matrix_data = {}
    for offset in day_offsets:
        if offset_corrs[offset]:
            stacked = np.array(offset_corrs[offset])
            mean_corr = stacked.mean(axis=0)
            if len(mean_corr) == len(lag_range):
                matrix_data[offset] = mean_corr
            else:
                padded = np.zeros(len(lag_range))
                padded[:min(len(mean_corr), len(lag_range))] = mean_corr[:len(lag_range)]
                matrix_data[offset] = padded
        else:
            matrix_data[offset] = np.zeros(len(lag_range))

    results["matrix"] = pd.DataFrame(matrix_data, index=lag_range).T
    results["matrix"].index.name = "day_offset"
    return results


def reconstruct_open_positions(
    ticker: str,
    target_date: str,
    lookback_days: int = 90,
    available_dates: list[str] | None = None,
    fixed_iv: float = 0.80,
    progress_callback=None,
) -> pd.DataFrame:
    """
    Reconstruct all options positions OPEN on target_date.

    Collects trades from [target_date - lookback_days] through [target_date - 1]
    whose expiration >= target_date. Recomputes delta/gamma at target_date's price.
    """
    target_dt = datetime.strptime(target_date, "%Y%m%d")
    target_ts = pd.Timestamp(target_date, tz="UTC")
    lookback_start = (target_dt - timedelta(days=lookback_days)).strftime("%Y%m%d")

    if available_dates is None:
        available_dates = sorted(get_available_dates("GME"))

    history_dates = [d for d in available_dates if lookback_start <= d < target_date]
    if not history_dates:
        return pd.DataFrame()

    equity_target = load_equity_trades(ticker, target_date)
    if equity_target.empty:
        return pd.DataFrame()
    current_price = equity_target["price"].median()

    all_positions = []
    for i, hist_date in enumerate(history_dates):
        if progress_callback:
            progress_callback((i + 1) / len(history_dates))

        opts = load_trades(ticker, [hist_date])
        if opts.empty:
            continue

        # Handle both 'expiration' and 'expiry' column names
        exp_col = "expiry" if "expiry" in opts.columns else "expiration"
        try:
            opts["exp_date"] = pd.to_datetime(opts[exp_col], format="ISO8601", utc=True)
        except (ValueError, TypeError):
            try:
                opts["exp_date"] = pd.to_datetime(opts[exp_col], format="%Y%m%d", utc=True)
            except (ValueError, TypeError):
                opts["exp_date"] = pd.to_datetime(opts[exp_col], format="mixed", utc=True)

        alive = opts[opts["exp_date"] >= target_ts].copy()
        if alive.empty:
            continue

        alive["trade_date"] = hist_date
        alive["days_held"] = (target_dt - datetime.strptime(hist_date, "%Y%m%d")).days

        alive["T_current"] = (
            (alive["exp_date"] - target_ts).dt.total_seconds() / (365.25 * 86400)
        ).clip(lower=1e-6)

        is_call = alive["right"].str.upper().str.startswith("C")
        alive["current_delta"] = bs_delta_vectorized(
            np.full(len(alive), current_price),
            alive["strike"].values,
            alive["T_current"].values,
            np.full(len(alive), fixed_iv),
            is_call.values,
        )
        alive["current_gamma"] = compute_gamma_vectorized(
            np.full(len(alive), current_price),
            alive["strike"].values,
            alive["T_current"].values,
            np.full(len(alive), fixed_iv),
        )

        alive["current_hedge_shares"] = alive["size"] * 100 * alive["current_delta"]
        alive["current_gamma_hedge"] = alive["size"] * 100 * alive["current_gamma"]

        alive["dte_days"] = (alive["T_current"] * 365.25).round().astype(int)
        alive["exp_class"] = classify_expiration(alive["dte_days"])

        # Keep a normalized 'expiration' column for output
        alive["expiration_norm"] = alive["exp_date"]

        all_positions.append(alive[[
            "trade_date", "strike", "right", "size", "expiration_norm",
            "exp_date", "exp_class", "days_held",
            "current_delta", "current_gamma",
            "current_hedge_shares", "current_gamma_hedge", "dte_days",
        ]].rename(columns={"expiration_norm": "expiration"}))

    if not all_positions:
        return pd.DataFrame()
    return pd.concat(all_positions, ignore_index=True)


# ============================================================================
# Engine 1: Size Fingerprint Matching
# ============================================================================


def detect_hedge_fingerprints(
    delta_df: pd.DataFrame,
    equity_df: pd.DataFrame,
    time_window_sec: float = 300.0,
    size_tolerance: float = 0.10,
    burst_gap_ms: float = 100.0,
) -> pd.DataFrame:
    """
    Match equity bursts to options hedge predictions via size decomposition.
    Uses vectorized merge_asof for speed.

    Returns DataFrame with matched burst↔option pairs.
    """
    eq = equity_df.sort_values("ts").copy()
    eq["dt_ms"] = eq["ts"].diff().dt.total_seconds() * 1000
    eq["burst_id"] = (eq["dt_ms"] > burst_gap_ms).cumsum()

    bursts = eq.groupby("burst_id").agg(
        burst_ts=("ts", "mean"),
        burst_total=("size", "sum"),
        burst_n_trades=("size", "count"),
    ).reset_index()
    bursts = bursts[bursts["burst_total"] >= 50].copy()

    # Pre-filter options with meaningful hedge sizes
    opts = delta_df[delta_df["hedge_shares"].abs() >= 50].copy()
    opts["abs_hedge"] = opts["hedge_shares"].abs()

    if opts.empty or bursts.empty:
        return pd.DataFrame()

    # Vectorized: merge_asof to find nearest option for each burst
    bursts_sorted = bursts.sort_values("burst_ts").reset_index(drop=True)
    opts_sorted = opts.sort_values("ts").reset_index(drop=True)

    merged = pd.merge_asof(
        bursts_sorted.rename(columns={"burst_ts": "ts_key"}),
        opts_sorted[["ts", "abs_hedge", "strike", "right", "delta"]].rename(
            columns={"ts": "ts_key", "abs_hedge": "opt_hedge",
                     "strike": "opt_strike", "right": "opt_right",
                     "delta": "opt_delta"}
        ),
        on="ts_key",
        direction="nearest",
        tolerance=pd.Timedelta(seconds=time_window_sec),
    )

    # Also do forward and backward merges to get more candidates
    merged_fwd = pd.merge_asof(
        bursts_sorted.rename(columns={"burst_ts": "ts_key"}),
        opts_sorted[["ts", "abs_hedge", "strike", "right", "delta"]].rename(
            columns={"ts": "ts_key", "abs_hedge": "opt_hedge",
                     "strike": "opt_strike", "right": "opt_right",
                     "delta": "opt_delta"}
        ),
        on="ts_key",
        direction="forward",
        tolerance=pd.Timedelta(seconds=time_window_sec),
    )

    merged_bwd = pd.merge_asof(
        bursts_sorted.rename(columns={"burst_ts": "ts_key"}),
        opts_sorted[["ts", "abs_hedge", "strike", "right", "delta"]].rename(
            columns={"ts": "ts_key", "abs_hedge": "opt_hedge",
                     "strike": "opt_strike", "right": "opt_right",
                     "delta": "opt_delta"}
        ),
        on="ts_key",
        direction="backward",
        tolerance=pd.Timedelta(seconds=time_window_sec),
    )

    # Combine all merge results
    all_merged = pd.concat([merged, merged_fwd, merged_bwd], ignore_index=True)
    all_merged = all_merged.dropna(subset=["opt_hedge"])

    if all_merged.empty:
        return pd.DataFrame()

    # Compute match error
    all_merged["match_error"] = (
        (all_merged["burst_total"] - all_merged["opt_hedge"]).abs()
        / all_merged["burst_total"].clip(lower=1)
    )
    all_merged["match_quality"] = 1.0 - all_merged["match_error"]

    # Filter by tolerance
    matched = all_merged[all_merged["match_error"] <= size_tolerance].copy()

    if matched.empty:
        return pd.DataFrame()

    # Deduplicate: keep best match per burst
    matched = matched.sort_values("match_error").drop_duplicates(
        subset=["burst_id"], keep="first"
    )

    # Build output
    result = pd.DataFrame({
        "burst_id": matched["burst_id"].values,
        "burst_ts": matched["ts_key"].values,
        "burst_total": matched["burst_total"].values,
        "burst_n_trades": matched["burst_n_trades"].values,
        "matched_strike": matched["opt_strike"].values,
        "matched_right": matched["opt_right"].values,
        "matched_delta": matched["opt_delta"].values,
        "matched_hedge": matched["opt_hedge"].values,
        "match_error": matched["match_error"].values,
        "match_quality": matched["match_quality"].values,
        "time_offset_sec": np.zeros(len(matched)),  # approximate from merge
    })

    return result


def render_fingerprint_scatter(
    fingerprints: pd.DataFrame,
    equity_df: pd.DataFrame,
) -> plt.Figure:
    """Scatter plot of matched burst<->option pairs."""
    fig, axes = plt.subplots(2, 2, figsize=(20, 10))
    fig.patch.set_facecolor("#111")

    for row in axes:
        for ax in row:
            ax.set_facecolor("black")
            ax.tick_params(colors="white", labelsize=9)
            for s in ax.spines.values():
                s.set_color("#333")

    if fingerprints.empty:
        axes[0, 0].text(0.5, 0.5, "No matches found", color="white",
                        ha="center", va="center", fontsize=14)
        return fig

    # Panel 1: Time offset distribution
    ax = axes[0, 0]
    ax.hist(fingerprints["time_offset_sec"], bins=50, color="cyan", alpha=0.7, edgecolor="none")
    ax.axvline(0, color="yellow", linewidth=1, linestyle="--")
    ax.set_xlabel("Time Offset (sec): option - burst", color="white")
    ax.set_ylabel("Count", color="white")
    ax.set_title(f"Timing: {len(fingerprints):,} matches", color="white", fontsize=11, fontweight="bold")

    # Panel 2: Match quality distribution
    ax = axes[0, 1]
    ax.hist(fingerprints["match_quality"], bins=50, color="#44ff44", alpha=0.7, edgecolor="none")
    ax.set_xlabel("Match Quality (1.0 = exact)", color="white")
    ax.set_ylabel("Count", color="white")
    mean_q = fingerprints["match_quality"].mean()
    ax.set_title(f"Quality Distribution (mean={mean_q:.3f})", color="white", fontsize=11, fontweight="bold")

    # Panel 3: Burst total vs matched hedge
    ax = axes[1, 0]
    ax.scatter(fingerprints["burst_total"], fingerprints["matched_hedge"],
               c=fingerprints["match_quality"], cmap="viridis", alpha=0.5, s=10)
    max_val = max(fingerprints["burst_total"].max(), fingerprints["matched_hedge"].max())
    ax.plot([0, max_val], [0, max_val], color="red", linewidth=1, linestyle="--", alpha=0.5)
    ax.set_xlabel("Burst Total (shares)", color="white")
    ax.set_ylabel("Matched Hedge (shares)", color="white")
    ax.set_title("Burst vs Hedge Size", color="white", fontsize=11, fontweight="bold")
    ax.set_xlim(0, min(max_val, 5000))
    ax.set_ylim(0, min(max_val, 5000))

    # Panel 4: Strike distribution of matches
    ax = axes[1, 1]
    ax.hist(fingerprints["matched_strike"], bins=50, color="#ff6600", alpha=0.7, edgecolor="none")
    ax.set_xlabel("Matched Strike", color="white")
    ax.set_ylabel("Count", color="white")
    ax.set_title("Strike Distribution of Matches", color="white", fontsize=11, fontweight="bold")

    fig.suptitle("Size Fingerprint Matching: Equity Bursts → Options Hedges",
                 color="white", fontsize=14, fontweight="bold")
    fig.tight_layout()
    return fig


# ============================================================================
# Engine 2: Rolling Gamma Displacement
# ============================================================================


def compute_gamma_roll_matrix(
    ticker: str,
    date_range: list[str],
    fixed_iv: float = 0.80,
    progress_callback=None,
) -> pd.DataFrame:
    """
    Track gamma exposure by expiration bucket across consecutive days.

    Returns DataFrame with columns:
        trade_date, exp_bucket, gamma_exposure, delta_exposure,
        trade_count, notional
    """
    rows = []
    for i, date_str in enumerate(date_range):
        if progress_callback:
            progress_callback((i + 1) / len(date_range))

        opts = load_trades(ticker, [date_str])
        eq = load_equity_trades(ticker, date_str)
        if opts.empty or eq.empty:
            continue

        delta_df = compute_delta_exposure(opts, eq, date_str, fixed_iv=fixed_iv)
        if delta_df.empty:
            continue

        enriched = add_expiration_and_gamma(delta_df)

        # Parse actual expiration dates for bucketing
        exp_col = "expiry" if "expiry" in enriched.columns else "expiration"
        try:
            enriched["exp_date"] = pd.to_datetime(enriched[exp_col], format="ISO8601", utc=True)
        except (ValueError, TypeError):
            enriched["exp_date"] = pd.to_datetime(enriched[exp_col], format="mixed", utc=True)

        # Group by expiration week
        trade_dt = pd.Timestamp(date_str, tz="UTC")
        enriched["days_to_exp"] = (enriched["exp_date"] - trade_dt).dt.days

        for exp_class in ["0DTE", "Weekly", "Monthly", "LEAPS"]:
            sub = enriched[enriched["exp_class"] == exp_class]
            if sub.empty:
                continue
            rows.append({
                "trade_date": date_str,
                "exp_bucket": exp_class,
                "gamma_exposure": float(sub["abs_gamma_hedge"].sum()),
                "delta_exposure": float(sub["abs_hedge"].sum()),
                "trade_count": len(sub),
                "mean_dte": float(sub["dte_days"].mean()),
                "notional": float(sub["notional"].sum()) if "notional" in sub.columns else 0,
            })

        # Also track by specific expiration date (top 5)
        top_exps = enriched["exp_date"].value_counts().head(5).index
        for exp_date in top_exps:
            sub = enriched[enriched["exp_date"] == exp_date]
            rows.append({
                "trade_date": date_str,
                "exp_bucket": exp_date.strftime("%m/%d"),
                "gamma_exposure": float(sub["abs_gamma_hedge"].sum()),
                "delta_exposure": float(sub["abs_hedge"].sum()),
                "trade_count": len(sub),
                "mean_dte": float(sub["dte_days"].mean()),
                "notional": float(sub["notional"].sum()) if "notional" in sub.columns else 0,
            })

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def render_gamma_roll_waterfall(
    roll_df: pd.DataFrame,
    metric: str = "gamma_exposure",
) -> plt.Figure:
    """Stacked area chart showing gamma by expiration across days."""
    if roll_df.empty:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.text(0.5, 0.5, "No data", ha="center", va="center", color="white")
        return fig

    # Use only the class-level buckets for the stacked view
    class_buckets = ["0DTE", "Weekly", "Monthly", "LEAPS"]
    class_data = roll_df[roll_df["exp_bucket"].isin(class_buckets)]

    # Also get specific-expiration data for detail view
    date_buckets = roll_df[~roll_df["exp_bucket"].isin(class_buckets)]

    fig, axes = plt.subplots(1, 2, figsize=(22, 7))
    fig.patch.set_facecolor("#111")

    for ax in axes:
        ax.set_facecolor("black")
        ax.tick_params(colors="white", labelsize=9)
        for s in ax.spines.values():
            s.set_color("#333")

    # Left: Stacked by expiration class
    ax = axes[0]
    pivot = class_data.pivot_table(
        index="trade_date", columns="exp_bucket", values=metric, fill_value=0
    )
    if not pivot.empty:
        colors = [EXP_COLORS.get(c, "#888") for c in pivot.columns]
        pivot.plot.bar(ax=ax, stacked=True, color=colors, alpha=0.8, width=0.8, edgecolor="none")
        ax.legend(facecolor="#222", edgecolor="#555", labelcolor="white", fontsize=8)
    ax.set_xlabel("Trading Date", color="white")
    ax.set_ylabel(metric.replace("_", " ").title(), color="white")
    ax.set_title(f"Rolling {metric.replace('_', ' ').title()} by Expiration Class",
                 color="white", fontsize=12, fontweight="bold")
    ax.tick_params(axis="x", rotation=45)

    # Right: By specific expiration date (shows the roll)
    ax = axes[1]
    if not date_buckets.empty:
        pivot2 = date_buckets.pivot_table(
            index="trade_date", columns="exp_bucket", values=metric, fill_value=0
        )
        if not pivot2.empty:
            pivot2.plot.bar(ax=ax, stacked=True, alpha=0.8, width=0.8, edgecolor="none",
                           colormap="Set2")
            ax.legend(facecolor="#222", edgecolor="#555", labelcolor="white",
                      fontsize=7, title="Expiration", title_fontsize=8)
    ax.set_xlabel("Trading Date", color="white")
    ax.set_ylabel(metric.replace("_", " ").title(), color="white")
    ax.set_title("By Specific Expiration Date (The Roll)",
                 color="white", fontsize=12, fontweight="bold")
    ax.tick_params(axis="x", rotation=45)

    fig.suptitle("Rolling Gamma Displacement — Energy Migration Through Time",
                 color="white", fontsize=14, fontweight="bold")
    fig.tight_layout()
    return fig


# ============================================================================
# Engine 3: Cadence Decomposition
# ============================================================================


def decompose_burst_cadence(
    equity_df: pd.DataFrame,
    n_parts: int = 3,
    burst_gap_ms: float = 100.0,
    min_burst_trades: int = 6,
) -> pd.DataFrame:
    """
    Decompose equity bursts into n_parts sub-sequences and check for
    equal-size splitting (the obfuscation hypothesis).

    For each burst with >= min_burst_trades:
      1. Sort trades by timestamp
      2. Split into n_parts equal sub-groups
      3. Compute total_size, mean_price, timing centroid per sub-group
      4. Measure equality of sub-group sizes (Gini coefficient)

    Returns DataFrame with per-burst analysis:
        burst_id, n_trades, total_size,
        part_sizes (list), part_prices (list),
        size_gini (0=perfectly equal, 1=all in one part),
        total_mod_100 (burst total modulo 100),
        is_hedge_multiple (total is within 5% of 100*N)
    """
    eq = equity_df.sort_values("ts").copy()
    eq["dt_ms"] = eq["ts"].diff().dt.total_seconds() * 1000
    eq["burst_id"] = (eq["dt_ms"] > burst_gap_ms).cumsum()

    results = []
    for bid, group in eq.groupby("burst_id"):
        if len(group) < min_burst_trades:
            continue

        trades = group.sort_values("ts")
        total_size = trades["size"].sum()
        n = len(trades)

        # Split into n_parts
        chunk_size = n // n_parts
        remainder = n % n_parts
        parts = []
        idx = 0
        for p in range(n_parts):
            end = idx + chunk_size + (1 if p < remainder else 0)
            part = trades.iloc[idx:end]
            parts.append({
                "size": part["size"].sum(),
                "mean_price": part["price"].mean(),
                "centroid_ts": part["ts"].mean(),
                "n_trades": len(part),
            })
            idx = end

        part_sizes = [p["size"] for p in parts]
        part_prices = [p["mean_price"] for p in parts]

        # Gini coefficient of part sizes (0 = perfectly equal)
        sizes_arr = np.array(part_sizes, dtype=float)
        if sizes_arr.sum() > 0:
            sizes_norm = sizes_arr / sizes_arr.sum()
            gini = 1.0 - np.sum(sizes_norm ** 2) * n_parts
            # Normalize to [0, 1]
            gini = max(0, min(1, gini * n_parts / (n_parts - 1)))
        else:
            gini = 0.0

        # Check if total is a hedge multiple
        nearest_100 = round(total_size / 100) * 100
        is_hedge = abs(total_size - nearest_100) <= max(total_size * 0.05, 5)

        results.append({
            "burst_id": bid,
            "n_trades": n,
            "total_size": total_size,
            "part_sizes": part_sizes,
            "part_prices": part_prices,
            "size_gini": gini,
            "size_cv": np.std(part_sizes) / max(np.mean(part_sizes), 1),
            "price_range": max(part_prices) - min(part_prices),
            "total_mod_100": total_size % 100,
            "is_hedge_multiple": is_hedge,
        })

    return pd.DataFrame(results)


def render_cadence_decomposition(
    cadence_df: pd.DataFrame,
    n_parts: int = 3,
) -> plt.Figure:
    """Visualize burst cadence decomposition results."""
    fig, axes = plt.subplots(2, 2, figsize=(20, 10))
    fig.patch.set_facecolor("#111")

    for row in axes:
        for ax in row:
            ax.set_facecolor("black")
            ax.tick_params(colors="white", labelsize=9)
            for s in ax.spines.values():
                s.set_color("#333")

    if cadence_df.empty:
        axes[0, 0].text(0.5, 0.5, "No data", color="white", ha="center", va="center")
        return fig

    # Panel 1: Size Gini distribution (0 = perfectly equal split)
    ax = axes[0, 0]
    ax.hist(cadence_df["size_gini"], bins=50, color="cyan", alpha=0.7, edgecolor="none")
    ax.axvline(cadence_df["size_gini"].median(), color="yellow", linewidth=2, linestyle="--",
               label=f"Median={cadence_df['size_gini'].median():.3f}")
    ax.set_xlabel(f"Size Gini ({n_parts}-part split)", color="white")
    ax.set_ylabel("Count", color="white")
    ax.set_title(f"Split Equality: {len(cadence_df):,} bursts analyzed",
                 color="white", fontsize=11, fontweight="bold")
    ax.legend(facecolor="#222", edgecolor="#555", labelcolor="white", fontsize=9)

    # Panel 2: Hedge multiple enrichment
    ax = axes[0, 1]
    hedge = cadence_df["is_hedge_multiple"].sum()
    non_hedge = len(cadence_df) - hedge
    pct = 100 * hedge / len(cadence_df) if len(cadence_df) > 0 else 0
    ax.bar(["Hedge\nMultiple", "Non-Hedge"], [hedge, non_hedge],
           color=["#44ff44", "#ff4444"], alpha=0.7)
    ax.set_ylabel("Burst Count", color="white")
    ax.set_title(f"Burst Totals = Hedge Multiples: {pct:.1f}%",
                 color="white", fontsize=11, fontweight="bold")

    # Panel 3: Size CV vs burst size scatter
    ax = axes[1, 0]
    colors = ["#44ff44" if h else "#ff4444" for h in cadence_df["is_hedge_multiple"]]
    ax.scatter(cadence_df["total_size"], cadence_df["size_cv"],
               c=colors, alpha=0.3, s=5)
    ax.set_xlabel("Burst Total Size", color="white")
    ax.set_ylabel("Size CV (lower = more equal split)", color="white")
    ax.set_title("Split Equality vs Burst Size\n(green = hedge multiple)",
                 color="white", fontsize=11, fontweight="bold")
    ax.set_xlim(0, cadence_df["total_size"].quantile(0.95))

    # Panel 4: Mod-100 histogram (should show spike at 0 if hedge-related)
    ax = axes[1, 1]
    ax.hist(cadence_df["total_mod_100"], bins=100, color="#ff6600",
            alpha=0.7, edgecolor="none")
    ax.axvline(0, color="yellow", linewidth=2, linestyle="--")
    ax.set_xlabel("Burst Total mod 100", color="white")
    ax.set_ylabel("Count", color="white")
    expected = len(cadence_df) / 100
    at_zero = (cadence_df["total_mod_100"] == 0).sum()
    enrichment = at_zero / expected if expected > 0 else 0
    ax.set_title(f"Mod-100 Distribution (spike at 0 = {enrichment:.1f}× enrichment)",
                 color="white", fontsize=11, fontweight="bold")

    fig.suptitle(f"Cadence Decomposition: {n_parts}-Part Burst Slicing Analysis",
                 color="white", fontsize=14, fontweight="bold")
    fig.tight_layout()
    return fig


# ============================================================================
# Cross-Day Visualization
# ============================================================================


def render_cross_day_heatmap(matrix_results: dict) -> plt.Figure:
    """2D heatmap: day_offset (y) x intraday_lag (x) -> mean correlation."""
    matrix = matrix_results["matrix"]

    fig, axes = plt.subplots(1, 2, figsize=(20, 6), gridspec_kw={"width_ratios": [3, 1]})
    fig.patch.set_facecolor("#111")

    for ax in axes:
        ax.set_facecolor("black")
        ax.tick_params(colors="white", labelsize=9)
        for s in ax.spines.values():
            s.set_color("#333")

    # Left: heatmap
    ax = axes[0]
    vmax = max(abs(matrix.values.min()), abs(matrix.values.max()), 0.01)
    im = ax.imshow(
        matrix.values, aspect="auto", cmap="RdBu_r",
        vmin=-vmax, vmax=vmax, origin="lower",
    )
    ax.set_xlabel("Intraday Lag (bins)", color="white", fontsize=11)
    ax.set_ylabel("Day Offset (trading days)", color="white", fontsize=11)
    ax.set_title(
        "Cross-Day × Intraday Lag Correlation Matrix",
        color="white", fontsize=13, fontweight="bold",
    )

    cols = matrix.columns.tolist()
    n_col_ticks = min(11, len(cols))
    col_positions = np.linspace(0, len(cols) - 1, n_col_ticks, dtype=int)
    ax.set_xticks(col_positions)
    ax.set_xticklabels([str(cols[i]) for i in col_positions])

    row_labels = matrix.index.tolist()
    ax.set_yticks(range(len(row_labels)))
    ax.set_yticklabels([str(r) for r in row_labels])

    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label="Mean Correlation")

    # Right: ZNCC by offset
    ax2 = axes[1]
    offsets = sorted(matrix_results["zncc_by_offset"].keys())
    zncc_vals = [matrix_results["zncc_by_offset"].get(o, 0) or 0 for o in offsets]
    n_valid = [matrix_results["n_valid"].get(o, 0) for o in offsets]

    colors = ["#44ff44" if v > 0 else "#ff4444" for v in zncc_vals]
    ax2.barh(range(len(offsets)), zncc_vals, color=colors, alpha=0.7, edgecolor="none")
    ax2.set_yticks(range(len(offsets)))
    ax2.set_yticklabels([f"{o:+d} ({n_valid[i]}d)" for i, o in enumerate(offsets)])
    ax2.axvline(0, color="gray", linewidth=0.5, linestyle="--")
    ax2.set_title("Mean ZNCC by Day Offset", color="white", fontsize=11, fontweight="bold")
    ax2.set_xlabel("ZNCC", color="white")

    fig.tight_layout()
    return fig


def render_position_reconstruction(
    positions: pd.DataFrame,
    target_date: str,
) -> plt.Figure:
    """Visualize reconstructed open positions by age and class."""
    fig, axes = plt.subplots(2, 2, figsize=(20, 10))
    fig.patch.set_facecolor("#111")

    for row in axes:
        for ax in row:
            ax.set_facecolor("black")
            ax.tick_params(colors="white", labelsize=9)
            for s in ax.spines.values():
                s.set_color("#333")

    target_label = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:8]}"

    # Panel 1: Hedge demand by days_held
    ax = axes[0, 0]
    held_groups = positions.groupby("days_held").agg(
        total_hedge=("current_hedge_shares", lambda x: x.abs().sum()),
        total_gamma=("current_gamma_hedge", "sum"),
        n_trades=("size", "count"),
    ).reset_index()
    ax.bar(held_groups["days_held"], held_groups["total_hedge"], color="dodgerblue", alpha=0.7)
    ax.set_xlabel("Days Held (trade age)", color="white")
    ax.set_ylabel("Abs Hedge Shares", color="white")
    ax.set_title(f"Hedge Demand by Position Age\n(Target: {target_label})", color="white", fontsize=11, fontweight="bold")

    # Panel 2: Gamma by days_held
    ax = axes[0, 1]
    ax.bar(held_groups["days_held"], held_groups["total_gamma"], color="#ff6600", alpha=0.7)
    ax.set_xlabel("Days Held (trade age)", color="white")
    ax.set_ylabel("Gamma Hedge", color="white")
    ax.set_title("Gamma Demand by Position Age", color="white", fontsize=11, fontweight="bold")

    # Panel 3: By expiration class
    ax = axes[1, 0]
    class_groups = positions.groupby("exp_class").agg(
        total_hedge=("current_hedge_shares", lambda x: x.abs().sum()),
        total_gamma=("current_gamma_hedge", "sum"),
        n_trades=("size", "count"),
        mean_days_held=("days_held", "mean"),
    ).reset_index()
    bar_colors = [EXP_COLORS.get(c, "#888") for c in class_groups["exp_class"]]
    ax.bar(class_groups["exp_class"], class_groups["total_hedge"], color=bar_colors, alpha=0.7)
    ax.set_xlabel("Expiration Class", color="white")
    ax.set_ylabel("Abs Hedge Shares", color="white")
    ax.set_title("Hedge by Expiration Class (historical)", color="white", fontsize=11, fontweight="bold")

    # Panel 4: Summary
    ax = axes[1, 1]
    ax.axis("off")
    total_hedge = positions["current_hedge_shares"].abs().sum()
    total_gamma = positions["current_gamma_hedge"].sum()
    summary_lines = [
        f"Position Reconstruction: {target_label}",
        f"{'─' * 40}",
        f"Lookback trades: {len(positions):,}",
        f"Unique trade dates: {positions['trade_date'].nunique()}",
        f"Max position age: {positions['days_held'].max()} days",
        f"Total |hedge shares|: {total_hedge:,.0f}",
        f"Total γ hedge: {total_gamma:,.0f}",
        f"{'─' * 40}",
    ]
    for _, row in class_groups.iterrows():
        summary_lines.append(
            f"{row['exp_class']}: {row['n_trades']:,} trades, "
            f"|hedge|={row['total_hedge']:,.0f}, "
            f"avg age={row['mean_days_held']:.0f}d"
        )
    ax.text(
        0.05, 0.95, "\n".join(summary_lines),
        transform=ax.transAxes, color="white", fontsize=10,
        verticalalignment="top", fontfamily="monospace",
    )

    fig.tight_layout()
    return fig


# ============================================================================
# Comparison Engine
# ============================================================================


def time_bin_profile(
    timestamps: pd.Series,
    values: pd.Series,
    n_bins: int = 256,
    agg: str = "sum",
) -> np.ndarray:
    """
    Bin a time series into n_bins equal-width time bins.
    Returns array of aggregated values per bin.
    """
    ts = pd.to_datetime(timestamps)
    t_min, t_max = ts.min(), ts.max()
    if t_min == t_max:
        return np.zeros(n_bins)

    t_norm = (ts - t_min).dt.total_seconds() / (t_max - t_min).total_seconds()
    bins = np.clip((t_norm * n_bins).astype(int), 0, n_bins - 1)

    profile = np.zeros(n_bins)
    if agg == "sum":
        np.add.at(profile, bins.values, values.values)
    elif agg == "count":
        np.add.at(profile, bins.values, 1)
    elif agg == "mean":
        counts = np.zeros(n_bins)
        np.add.at(profile, bins.values, values.values)
        np.add.at(counts, bins.values, 1)
        mask = counts > 0
        profile[mask] /= counts[mask]

    return profile


def cross_correlate_profiles(
    predicted: np.ndarray,
    actual: np.ndarray,
    max_lag_bins: int = 50,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Cross-correlate predicted hedge profile with actual equity burst profile.

    Returns (lags, correlations) where lags are in bin units.
    """
    # Normalize
    p = predicted - predicted.mean()
    a = actual - actual.mean()

    p_std = p.std()
    a_std = a.std()
    if p_std < 1e-12 or a_std < 1e-12:
        return np.arange(-max_lag_bins, max_lag_bins + 1), np.zeros(
            2 * max_lag_bins + 1
        )

    # Full cross-correlation
    full_corr = correlate(a, p, mode="full")
    n = len(predicted)
    full_corr /= n * p_std * a_std

    # Extract lag range
    center = len(full_corr) // 2
    start = max(0, center - max_lag_bins)
    end = min(len(full_corr), center + max_lag_bins + 1)

    lags = np.arange(start - center, end - center)
    corrs = full_corr[start:end]

    return lags, corrs


def zncc_1d(a: np.ndarray, b: np.ndarray) -> float:
    """Zero-Normalized Cross-Correlation for 1D profiles."""
    a = a.astype(np.float64)
    b = b.astype(np.float64)
    a_std = a.std()
    b_std = b.std()
    if a_std < 1e-12 or b_std < 1e-12:
        return 0.0
    return float(np.mean((a - a.mean()) * (b - b.mean())) / (a_std * b_std))


# ============================================================================
# Visualization
# ============================================================================


def render_delta_dashboard(
    delta_df: pd.DataFrame,
    equity_df: pd.DataFrame,
    burst_start: str | None = None,
    burst_end: str | None = None,
    n_bins: int = 256,
) -> plt.Figure:
    """
    Render 4-panel delta hedging dashboard.

    Panel 1: Options flow (colored by C/P, sized by notional)
    Panel 2: Predicted hedge demand (cumulative delta) over time
    Panel 3: Actual equity trade volume over time
    Panel 4: Cross-correlation (lag vs correlation)
    """
    fig, axes = plt.subplots(2, 2, figsize=(22, 14))
    fig.patch.set_facecolor("#111")

    for row in axes:
        for ax in row:
            ax.set_facecolor("black")
            ax.tick_params(colors="white", labelsize=9)
            for s in ax.spines.values():
                s.set_color("#333")

    ts = delta_df["ts"]

    # ── Panel 1: Options flow timeline ──
    ax1 = axes[0, 0]
    calls = delta_df[delta_df["right"].str.upper().str.startswith("C")]
    puts = delta_df[~delta_df["right"].str.upper().str.startswith("C")]

    if not calls.empty:
        ax1.scatter(
            calls["ts"],
            calls["strike"],
            s=np.clip(calls["size"] * 2, 1, 100),
            alpha=0.4,
            c="limegreen",
            edgecolors="none",
            label=f"Calls ({len(calls):,})",
        )
    if not puts.empty:
        ax1.scatter(
            puts["ts"],
            puts["strike"],
            s=np.clip(puts["size"] * 2, 1, 100),
            alpha=0.4,
            c="red",
            edgecolors="none",
            label=f"Puts ({len(puts):,})",
        )
    ax1.set_title("Options Flow: Strike × Time", color="white", fontsize=12, fontweight="bold")
    ax1.set_ylabel("Strike ($)", color="white")
    ax1.legend(facecolor="#222", edgecolor="#555", labelcolor="white", fontsize=9)
    ax1.tick_params(axis="x", rotation=30)

    # ── Panel 2: Predicted hedge demand ──
    ax2 = axes[0, 1]
    ax2.fill_between(
        ts,
        delta_df["cum_hedge"],
        alpha=0.3,
        color="dodgerblue",
    )
    ax2.plot(ts, delta_df["cum_hedge"], color="dodgerblue", linewidth=0.8, alpha=0.8)
    ax2.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    ax2.set_title(
        "Predicted Hedge Demand (Cumulative Δ Shares)",
        color="white",
        fontsize=12,
        fontweight="bold",
    )
    ax2.set_ylabel("Shares", color="white")
    ax2.tick_params(axis="x", rotation=30)

    # ── Panel 3: Actual equity trade volume ──
    ax3 = axes[1, 0]

    # Filter equity to market hours if possible
    eq = equity_df.copy()
    if burst_start and burst_end:
        bs = pd.Timestamp(burst_start, tz="UTC")
        be = pd.Timestamp(burst_end, tz="UTC")
        eq = eq[(eq["ts"] >= bs) & (eq["ts"] <= be)]

    if not eq.empty:
        # Time-bin the equity volume
        eq_profile = time_bin_profile(eq["ts"], eq["size"], n_bins, agg="sum")
        x_bins = np.linspace(0, 1, n_bins)
        ax3.bar(x_bins, eq_profile, width=1.0 / n_bins, color="orange", alpha=0.7, edgecolor="none")
        ax3.set_title(
            f"Actual Equity Volume ({len(eq):,} trades)",
            color="white",
            fontsize=12,
            fontweight="bold",
        )
    else:
        # Show full day
        eq_profile = time_bin_profile(equity_df["ts"], equity_df["size"], n_bins, agg="sum")
        x_bins = np.linspace(0, 1, n_bins)
        ax3.bar(x_bins, eq_profile, width=1.0 / n_bins, color="orange", alpha=0.7, edgecolor="none")
        ax3.set_title(
            f"Actual Equity Volume — Full Day ({len(equity_df):,} trades)",
            color="white",
            fontsize=12,
            fontweight="bold",
        )
    ax3.set_ylabel("Shares", color="white")
    ax3.set_xlabel("Normalized Time", color="white")

    # ── Panel 4: Cross-correlation ──
    ax4 = axes[1, 1]

    # Build profiles for comparison
    hedge_profile = time_bin_profile(
        delta_df["ts"], delta_df["abs_hedge"], n_bins, agg="sum"
    )
    if not eq.empty:
        actual_profile = time_bin_profile(eq["ts"], eq["size"], n_bins, agg="sum")
    else:
        actual_profile = time_bin_profile(
            equity_df["ts"], equity_df["size"], n_bins, agg="sum"
        )

    max_lag = min(n_bins // 4, 60)
    lags, corrs = cross_correlate_profiles(hedge_profile, actual_profile, max_lag)

    ax4.plot(lags, corrs, color="cyan", linewidth=1.5)
    ax4.fill_between(lags, corrs, alpha=0.2, color="cyan")
    peak_idx = np.argmax(corrs)
    peak_lag = lags[peak_idx]
    peak_corr = corrs[peak_idx]
    ax4.axvline(peak_lag, color="yellow", linewidth=1, linestyle="--", alpha=0.8)
    ax4.scatter([peak_lag], [peak_corr], color="yellow", s=80, zorder=5)
    ax4.set_title(
        f"Cross-Correlation: Peak r={peak_corr:.3f} at lag={peak_lag} bins",
        color="white",
        fontsize=12,
        fontweight="bold",
    )
    ax4.set_xlabel("Lag (time bins)", color="white")
    ax4.set_ylabel("Correlation", color="white")
    ax4.axhline(0, color="gray", linewidth=0.5, linestyle="--")

    # Overall ZNCC
    zncc = zncc_1d(hedge_profile, actual_profile)
    fig.suptitle(
        f"Delta Hedge Pipeline — ZNCC(hedge, equity) = {zncc:.4f}",
        color="white",
        fontsize=16,
        fontweight="bold",
    )

    fig.tight_layout()
    return fig


def render_shape_comparison(
    delta_df: pd.DataFrame,
    equity_df: pd.DataFrame,
    n_bins: int = 256,
) -> plt.Figure:
    """
    Side-by-side comparison of predicted hedge profile vs actual equity volume.
    """
    fig, axes = plt.subplots(1, 3, figsize=(22, 6))
    fig.patch.set_facecolor("#111")

    for ax in axes:
        ax.set_facecolor("black")
        ax.tick_params(colors="white", labelsize=10)
        for s in ax.spines.values():
            s.set_color("#333")

    hedge_profile = time_bin_profile(
        delta_df["ts"], delta_df["abs_hedge"], n_bins, agg="sum"
    )
    equity_profile = time_bin_profile(
        equity_df["ts"], equity_df["size"], n_bins, agg="sum"
    )

    x = np.linspace(0, 1, n_bins)

    # Normalize both for comparison
    h_norm = hedge_profile / (hedge_profile.max() or 1)
    e_norm = equity_profile / (equity_profile.max() or 1)

    # Panel 1: Predicted hedge
    axes[0].bar(x, h_norm, width=1.0 / n_bins, color="dodgerblue", alpha=0.8, edgecolor="none")
    axes[0].set_title("Predicted Hedge Volume\n(from options Δ)", color="white", fontsize=12, fontweight="bold")
    axes[0].set_xlabel("Normalized Time", color="white")

    # Panel 2: Actual equity
    axes[1].bar(x, e_norm, width=1.0 / n_bins, color="orange", alpha=0.8, edgecolor="none")
    axes[1].set_title("Actual Equity Volume", color="white", fontsize=12, fontweight="bold")
    axes[1].set_xlabel("Normalized Time", color="white")

    # Panel 3: Overlay
    axes[2].bar(x, h_norm, width=1.0 / n_bins, color="dodgerblue", alpha=0.5, edgecolor="none", label="Predicted")
    axes[2].bar(x, e_norm, width=1.0 / n_bins, color="orange", alpha=0.5, edgecolor="none", label="Actual")
    zncc = zncc_1d(hedge_profile, equity_profile)
    axes[2].set_title(
        f"Overlay — ZNCC = {zncc:.4f}",
        color="white",
        fontsize=12,
        fontweight="bold",
    )
    axes[2].set_xlabel("Normalized Time", color="white")
    axes[2].legend(facecolor="#222", edgecolor="#555", labelcolor="white")

    fig.suptitle("Predicted vs Actual Volume Profile", color="white", fontsize=14, fontweight="bold")
    fig.tight_layout()
    return fig


# ============================================================================
# Streamlit App
# ============================================================================


def get_equity_dates(ticker: str) -> list[str]:
    """Get available equity trade dates for ticker."""
    path = EQUITY_DIR / f"symbol={ticker}"
    if not path.exists():
        return []
    dates = sorted(
        d.name.replace("date=", "").replace("-", "")
        for d in path.iterdir()
        if d.is_dir()
    )
    return dates


def get_overlapping_dates(ticker: str) -> list[str]:
    """Find dates with both options and equity data."""
    opt_dates = set(get_available_dates(ticker))
    eq_dates = set(get_equity_dates(ticker))
    return sorted(opt_dates & eq_dates)


def main():
    st.set_page_config(page_title="Delta Hedge Pipeline", layout="wide")
    st.title("⚡ Delta Hedge Pipeline: Options → Predicted Burst")
    st.markdown(
        "Convert options flow into predicted equity hedging activity via "
        "Black-Scholes delta, then compare against actual trades."
    )

    # ── Sidebar ──
    ticker = st.sidebar.text_input("Ticker", value="GME")
    overlap_dates = get_overlapping_dates(ticker)

    if not overlap_dates:
        st.error(f"No overlapping dates found for {ticker}")
        return

    # Default to 20240517 if available
    default_idx = 0
    if "20240517" in overlap_dates:
        default_idx = overlap_dates.index("20240517")

    date_str = st.sidebar.selectbox(
        "Date", overlap_dates, index=default_idx
    )

    iv_mode = st.sidebar.radio(
        "IV Estimation",
        ["Fixed (fast)", "Newton's method (slow)"],
        index=0,
    )
    fixed_iv = None
    if iv_mode.startswith("Fixed"):
        fixed_iv = st.sidebar.slider("Fixed IV", 0.1, 3.0, 0.80, 0.05)

    n_bins = st.sidebar.slider("Time bins", 64, 512, 256, 32)

    subset = st.sidebar.selectbox(
        "Options subset", ["all", "calls", "puts"], index=0
    )

    run_btn = st.sidebar.button("🚀 Run Pipeline", type="primary")

    if not run_btn:
        st.info("Select parameters and click **Run Pipeline** to start.")
        st.markdown("""
        ### How it works

        1. **Load** options trades + equity trades for the same day
        2. **Merge** stock price at each options trade timestamp (asof join)
        3. **Compute** Black-Scholes delta for each options trade
        4. **Convert** to hedge shares: `size × 100 × Δ`
        5. **Compare** predicted hedge volume profile to actual equity volume
        6. **Cross-correlate** to find optimal time lag
        """)
        return

    # ── Load data ──
    with st.spinner("Loading options trades..."):
        opts = load_trades(ticker, [date_str])
    with st.spinner("Loading equity trades..."):
        date_hyphen = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        equity = load_equity_trades(ticker, date_str)

    st.sidebar.markdown(f"**Options**: {len(opts):,} trades")
    st.sidebar.markdown(f"**Equity**: {len(equity):,} trades")

    if opts.empty:
        st.error("No options data found")
        return
    if equity.empty:
        st.error("No equity data found")
        return

    # Filter subset
    if subset == "calls":
        opts = opts[opts["right"].str.upper().str.startswith("C")]
    elif subset == "puts":
        opts = opts[opts["right"].str.upper().str.startswith("P")]

    # ── Compute delta exposure ──
    with st.spinner(f"Computing delta exposure ({len(opts):,} trades)..."):
        delta_df = compute_delta_exposure(opts, equity, date_str, fixed_iv=fixed_iv)

    if delta_df.empty:
        st.error("Delta computation failed")
        return

    # ── Summary stats ──
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Options Trades", f"{len(delta_df):,}")
    col2.metric("Equity Trades", f"{len(equity):,}")
    col3.metric(
        "Peak Cum. Hedge",
        f"{delta_df['cum_hedge'].abs().max():,.0f} shares",
    )

    hedge_profile = time_bin_profile(delta_df["ts"], delta_df["abs_hedge"], n_bins, agg="sum")
    equity_profile = time_bin_profile(equity["ts"], equity["size"], n_bins, agg="sum")
    zncc = zncc_1d(hedge_profile, equity_profile)
    col4.metric("ZNCC", f"{zncc:.4f}")

    # ── 4-panel dashboard ──
    st.subheader("📊 Delta Hedging Dashboard")
    fig1 = render_delta_dashboard(delta_df, equity, n_bins=n_bins)
    st.pyplot(fig1)
    plt.close(fig1)

    # ── Shape comparison ──
    st.subheader("📐 Shape Comparison: Predicted vs Actual")
    fig2 = render_shape_comparison(delta_df, equity, n_bins=n_bins)
    st.pyplot(fig2)
    plt.close(fig2)

    # ── Delta distribution ──
    st.subheader("🔬 Delta Distribution")
    fig3, ax3 = plt.subplots(1, 2, figsize=(16, 5))
    fig3.patch.set_facecolor("#111")
    for ax in ax3:
        ax.set_facecolor("black")
        ax.tick_params(colors="white")
        for s in ax.spines.values():
            s.set_color("#333")

    ax3[0].hist(
        delta_df["delta"].dropna(),
        bins=50,
        color="dodgerblue",
        alpha=0.7,
        edgecolor="none",
    )
    ax3[0].set_title("Delta Distribution", color="white", fontsize=12, fontweight="bold")
    ax3[0].set_xlabel("Delta", color="white")

    ax3[1].hist(
        delta_df["hedge_shares"].dropna(),
        bins=50,
        color="orange",
        alpha=0.7,
        edgecolor="none",
    )
    ax3[1].set_title(
        "Hedge Shares per Trade", color="white", fontsize=12, fontweight="bold"
    )
    ax3[1].set_xlabel("Shares", color="white")

    fig3.tight_layout()
    st.pyplot(fig3)
    plt.close(fig3)

    # ── Expiration-Stratified Analysis ──
    st.subheader("🧬 Expiration-Stratified Lag Analysis")
    st.markdown(
        "Each option type (0DTE, Weekly, Monthly, LEAPS) may influence equity "
        "at different lags. This decomposes the hedge signal by expiration bucket."
    )

    # Enrich with expiration class and gamma
    with st.spinner("Computing gamma and classifying expirations..."):
        enriched_df = add_expiration_and_gamma(delta_df)

    # Show expiration breakdown
    exp_summary = []
    for bucket in EXP_BUCKETS + ["ALL"]:
        sub = enriched_df if bucket == "ALL" else enriched_df[enriched_df["exp_class"] == bucket]
        if len(sub) == 0:
            continue
        exp_summary.append({
            "Bucket": bucket,
            "Trades": f"{len(sub):,}",
            "Contracts": f"{sub['size'].sum():,}",
            "Mean Gamma": f"{sub['gamma'].mean():.4f}",
            "Total γ Exposure": f"{sub['abs_gamma_hedge'].sum():,.0f}",
            "Total Δ Hedge": f"{sub['abs_hedge'].sum():,.0f}",
            "Mean DTE": f"{sub['dte_days'].mean():.1f}",
        })
    st.dataframe(pd.DataFrame(exp_summary), use_container_width=True)

    # Weighting selector
    weight_mode = st.radio(
        "Hedge weighting",
        ["Delta (|Δ × size × 100|)", "Gamma (γ × size × 100)"],
        index=0,
        horizontal=True,
    )
    weighting = "abs_hedge" if weight_mode.startswith("Delta") else "abs_gamma_hedge"

    # Run stratified analysis
    with st.spinner("Running stratified lag analysis..."):
        strat_results = run_stratified_lag_analysis(
            enriched_df, equity, n_bins=n_bins, max_lag=80, weighting=weighting
        )

    # Summary table
    lag_summary = []
    for bucket, data in strat_results["buckets"].items():
        lag_summary.append({
            "Bucket": bucket,
            "ZNCC (lag=0)": f"{data['zncc']:.4f}",
            "Peak r": f"{data['peak_corr']:.4f}",
            "Peak Lag (bins)": data["peak_lag"],
            "Trades": f"{data['count']:,}",
            "Exposure": f"{data['total_exposure']:,.0f}",
        })
    st.dataframe(pd.DataFrame(lag_summary), use_container_width=True)

    # Render stratified dashboard
    fig_strat = render_stratified_dashboard(strat_results, n_bins=n_bins, weighting=weighting)
    st.pyplot(fig_strat)
    plt.close(fig_strat)

    # ── Gamma Heatmap ──
    st.subheader("🔥 Gamma & Delta Exposure Heatmap")
    st.markdown(
        "Where is gamma concentrated? High gamma zones predict where small "
        "price moves cause cascading re-hedging."
    )
    fig_gamma = render_gamma_heatmap(enriched_df, n_bins=128)
    st.pyplot(fig_gamma)
    plt.close(fig_gamma)

    # ── Raw data preview ──
    with st.expander("📋 Delta Exposure Data (first 100 rows)"):
        display_cols = [
            "ts", "strike", "right", "size", "price",
            "stock_price", "T", "iv", "delta", "hedge_shares", "cum_hedge",
            "exp_class", "gamma", "gamma_hedge",
        ]
        avail_cols = [c for c in display_cols if c in enriched_df.columns]
        st.dataframe(enriched_df[avail_cols].head(100))


if __name__ == "__main__":
    main()
