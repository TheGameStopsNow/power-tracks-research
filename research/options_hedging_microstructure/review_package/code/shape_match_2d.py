#!/usr/bin/env python3
"""
Phase 98c: 2D Shape Matching
==============================
Compare BURST TRADE scatter shapes (Time × Price) against OPTIONS data
that has been sorted/shuffled in various ways.

The core question: which historical options book, resorted in a specific way,
produces a 2D point-cloud pattern that matches a given burst shape?

Key design:
 - Both datasets are rasterized into 2D histograms (NxN grid) for comparison
 - Options trades are sorted along one axis by various metrics
 - A power-law dummy filter rejects trivially matching distributions
 - ZNCC (Zero-Normalized Cross-Correlation) on the 2D grids scores similarity
"""

import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd
import streamlit as st
from scipy.ndimage import zoom
from scipy.stats import wasserstein_distance

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw" / "thetadata" / "trades"
BURST_DIR = Path(__file__).parent.parent.parent / "docs" / "analysis" / "diagnostics" / "edgx_bursts"

sys.path.insert(0, str(Path(__file__).parent.parent / "phase94_deep_sweep"))
sys.path.insert(0, str(Path(__file__).parent))

from shape_match import load_trades, get_available_dates


# ============================================================================
# Data Loading
# ============================================================================

@st.cache_data
def load_burst_points(date_str: str = "2024-05-17", burst_idx: int | None = None):
    """Load normalized burst point cloud for a given date."""
    path = BURST_DIR / "normalized_points.parquet"
    if not path.exists():
        st.error(f"Normalized points file not found: {path}")
        return pd.DataFrame()

    df = pd.read_parquet(path)
    mask = df["date"].astype(str).str.contains(date_str)
    subset = df[mask].copy()

    if burst_idx is not None:
        subset = subset[subset["burst_idx"] == burst_idx]

    return subset


@st.cache_data
def load_burst_features(date_str: str = "2024-05-17"):
    """Load burst feature summary for a date."""
    path = BURST_DIR / f"burst_point_features_{date_str.replace('-', '')}.csv"
    if path.exists():
        return pd.read_csv(path)
    # Fall back to full features parquet
    pq_path = BURST_DIR / "burst_point_features.parquet"
    if pq_path.exists():
        df = pd.read_parquet(pq_path)
        return df[df["date"] == date_str]
    return pd.DataFrame()


# ============================================================================
# 2D Rasterization
# ============================================================================

def rasterize_points(x: np.ndarray, y: np.ndarray,
                     grid_size_x: int = 64,
                     grid_size_y: int = 64,
                     weights: np.ndarray | None = None) -> np.ndarray:
    """
    Rasterize a 2D point cloud into a grid histogram.
    x, y should be in [0, 1] range (normalized).
    Returns a (grid_size_y, grid_size_x) array of counts/weights.
    """
    # Clip to [0, 1]
    x = np.clip(x, 0, 1 - 1e-9)
    y = np.clip(y, 0, 1 - 1e-9)

    xi = (x * grid_size_x).astype(int)
    yi = (y * grid_size_y).astype(int)

    grid = np.zeros((grid_size_y, grid_size_x), dtype=np.float64)
    if weights is not None:
        for i in range(len(x)):
            grid[yi[i], xi[i]] += weights[i]
    else:
        for i in range(len(x)):
            grid[yi[i], xi[i]] += 1.0

    return grid


def rasterize_points_fast(x: np.ndarray, y: np.ndarray,
                          grid_size_x: int = 64,
                          grid_size_y: int = 64,
                          weights: np.ndarray | None = None) -> np.ndarray:
    """Fast vectorized rasterization using np.add.at."""
    x = np.clip(x, 0, 1 - 1e-9)
    y = np.clip(y, 0, 1 - 1e-9)

    xi = (x * grid_size_x).astype(int)
    yi = (y * grid_size_y).astype(int)

    grid = np.zeros((grid_size_y, grid_size_x), dtype=np.float64)
    if weights is not None:
        np.add.at(grid, (yi, xi), weights)
    else:
        np.add.at(grid, (yi, xi), 1.0)

    return grid


# ============================================================================
# Reference-Frame Detrending (Phase 99c)
# ============================================================================
# Strip out the moving reference frame a market maker might use for
# price-relative printing, exposing hidden shape structure in residuals.

def detrend_vwap(prices: np.ndarray, sizes: np.ndarray,
                 window: int = 50) -> np.ndarray:
    """Detrend prices against rolling VWAP. Returns residuals."""
    cumvol = np.cumsum(sizes)
    cumpv = np.cumsum(prices * sizes)

    vwap = np.zeros_like(prices)
    for i in range(len(prices)):
        start = max(0, i - window + 1)
        vol_window = cumvol[i] - (cumvol[start - 1] if start > 0 else 0)
        pv_window = cumpv[i] - (cumpv[start - 1] if start > 0 else 0)
        vwap[i] = pv_window / vol_window if vol_window > 0 else prices[i]

    return prices - vwap


def detrend_ema(prices: np.ndarray, span: int = 20) -> np.ndarray:
    """Detrend prices against exponential moving average. Returns residuals."""
    alpha = 2.0 / (span + 1)
    ema = np.zeros_like(prices)
    ema[0] = prices[0]
    for i in range(1, len(prices)):
        ema[i] = alpha * prices[i] + (1 - alpha) * ema[i - 1]
    return prices - ema


def detrend_midpoint(prices: np.ndarray, window: int = 20) -> np.ndarray:
    """Detrend prices against rolling (high+low)/2 midpoint. Returns residuals."""
    mid = np.zeros_like(prices)
    for i in range(len(prices)):
        start = max(0, i - window + 1)
        seg = prices[start:i + 1]
        mid[i] = (seg.max() + seg.min()) / 2.0
    return prices - mid


def detrend_logreturns(prices: np.ndarray, window: int = 20) -> np.ndarray:
    """Detrend log-prices against rolling mean of log-prices. Returns residuals."""
    log_p = np.log(np.maximum(prices, 1e-8))
    rolling_mean = np.zeros_like(log_p)
    for i in range(len(log_p)):
        start = max(0, i - window + 1)
        rolling_mean[i] = log_p[start:i + 1].mean()
    return log_p - rolling_mean


DETREND_METHODS = {
    "none": None,
    "vwap_residual": detrend_vwap,
    "ema_residual": detrend_ema,
    "midpoint_residual": detrend_midpoint,
    "logreturn_residual": detrend_logreturns,
}


# ============================================================================
# Options → 2D Point Cloud Transforms
# ============================================================================

DTE_BUCKETS = {
    "0DTE":     (0, 0),
    "1-7d":     (1, 7),
    "8-30d":    (8, 30),
    "31-90d":   (31, 90),
    "91-180d":  (91, 180),
    "181-365d": (181, 365),
    "365d+":    (366, 9999),
    "all":      None,
}
DTE_BUCKET_NAMES = list(DTE_BUCKETS.keys())


def _compute_dte(df: pd.DataFrame) -> pd.Series:
    """Compute days-to-expiration from expiration/expiry and source_date columns."""
    # Find expiration column (some parquets use 'expiration', others 'expiry')
    exp_col = None
    if "expiration" in df.columns:
        exp_col = "expiration"
    elif "expiry" in df.columns:
        exp_col = "expiry"

    if exp_col is None:
        return pd.Series(dtype=float)

    try:
        exp = pd.to_datetime(df[exp_col], errors="coerce")
    except Exception:
        return pd.Series(dtype=float)

    # Determine trade date from source_date or timestamp
    if "source_date" in df.columns:
        try:
            trade = pd.to_datetime(df["source_date"], format="%Y%m%d",
                                   errors="coerce")
        except Exception:
            trade = exp  # fallback
    elif "timestamp" in df.columns:
        try:
            trade = pd.to_datetime(df["timestamp"], errors="coerce").dt.normalize()
        except Exception:
            trade = exp
    else:
        return pd.Series(dtype=float)

    dte = (exp - trade).dt.days
    return dte


def options_to_2d(opts: pd.DataFrame,
                  sort_by: str = "time",
                  sort_direction: str = "asc",
                  subset: str = "all",
                  y_axis: str = "strike",
                  dte_bucket: str = "all") -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Convert options trades into a normalized 2D point cloud.

    X-axis: sorted index (0→1), sorted by `sort_by` metric
    Y-axis: normalized strike, price, or other metric

    Parameters
    ----------
    dte_bucket : str
        Filter by days-to-expiration tenor. One of DTE_BUCKETS keys:
        "0DTE", "1-7d", "8-30d", "31-90d", "91-180d", "181-365d", "365d+", or "all" (no filter).

    Returns (x_norm, y_norm, sizes) for rasterization.
    """
    df = opts.copy()

    # Filter by subset (call/put)
    if subset == "calls" and "right" in df.columns:
        df = df[df["right"] == "C"]
    elif subset == "puts" and "right" in df.columns:
        df = df[df["right"] == "P"]

    # Filter by DTE bucket
    if dte_bucket != "all" and dte_bucket in DTE_BUCKETS:
        bounds = DTE_BUCKETS[dte_bucket]
        if bounds is not None:
            dte = _compute_dte(df)
            if not dte.empty:
                lo, hi = bounds
                mask = (dte >= lo) & (dte <= hi)
                df = df[mask]

    if df.empty:
        return np.array([]), np.array([]), np.array([])

    # Determine sort column
    sort_col_map = {
        "time": "timestamp",
        "strike": "strike",
        "size": "size",
        "price": "price",
        "notional": "notional",
    }
    sort_col = sort_col_map.get(sort_by, "timestamp")

    if sort_col not in df.columns:
        return np.array([]), np.array([]), np.array([])

    ascending = sort_direction == "asc"
    df = df.sort_values(sort_col, ascending=ascending).reset_index(drop=True)

    # X = normalized sorted index
    n = len(df)
    x_norm = np.arange(n, dtype=np.float64) / max(n - 1, 1)

    # Y = normalized chosen axis
    y_col_map = {
        "strike": "strike",
        "price": "price",
        "size": "size",
        "notional": "notional",
    }
    y_col = y_col_map.get(y_axis, "strike")
    if y_col not in df.columns:
        return np.array([]), np.array([]), np.array([])

    y_vals = df[y_col].values.astype(np.float64)
    y_min, y_max = y_vals.min(), y_vals.max()
    if y_max > y_min:
        y_norm = (y_vals - y_min) / (y_max - y_min)
    else:
        y_norm = np.full_like(y_vals, 0.5)

    sizes = df["size"].values.astype(np.float64) if "size" in df.columns else np.ones(n)

    return x_norm, y_norm, sizes


# ============================================================================
# 2D Transform Library
# ============================================================================

def flip_x(grid: np.ndarray) -> np.ndarray:
    return grid[:, ::-1]

def flip_y(grid: np.ndarray) -> np.ndarray:
    return grid[::-1, :]

def transpose(grid: np.ndarray) -> np.ndarray:
    return grid.T

def rotate_90(grid: np.ndarray) -> np.ndarray:
    return np.rot90(grid, 1)

def rotate_180(grid: np.ndarray) -> np.ndarray:
    return np.rot90(grid, 2)

def rotate_270(grid: np.ndarray) -> np.ndarray:
    return np.rot90(grid, 3)

def log_scale(grid: np.ndarray) -> np.ndarray:
    return np.log1p(grid)

def sqrt_scale(grid: np.ndarray) -> np.ndarray:
    return np.sqrt(grid)

GRID_TRANSFORMS = {
    "identity": lambda g: g,
    "flip_x": flip_x,
    "flip_y": flip_y,
    "flip_xy": lambda g: flip_x(flip_y(g)),
    "transpose": transpose,
    "rot90": rotate_90,
    "rot180": rotate_180,
    "rot270": rotate_270,
    "log": log_scale,
    "sqrt": sqrt_scale,
    "log+flip_x": lambda g: flip_x(log_scale(g)),
    "log+flip_y": lambda g: flip_y(log_scale(g)),
    "sqrt+flip_x": lambda g: flip_x(sqrt_scale(g)),
    "sqrt+flip_y": lambda g: flip_y(sqrt_scale(g)),
}


# ============================================================================
# Similarity Metrics
# ============================================================================

def zncc_2d(a: np.ndarray, b: np.ndarray) -> float:
    """Zero-Normalized Cross-Correlation on flattened 2D grids."""
    a_flat = a.ravel().astype(np.float64)
    b_flat = b.ravel().astype(np.float64)

    a_mean = a_flat.mean()
    b_mean = b_flat.mean()
    a_std = a_flat.std()
    b_std = b_flat.std()

    if a_std < 1e-12 or b_std < 1e-12:
        return 0.0

    return float(np.mean((a_flat - a_mean) * (b_flat - b_mean)) / (a_std * b_std))


def structural_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Simple structural similarity (SSIM-like) for 2D grids."""
    mu_a = a.mean()
    mu_b = b.mean()
    sig_a = a.std()
    sig_b = b.std()
    sig_ab = np.mean((a - mu_a) * (b - mu_b))

    c1 = 0.01 ** 2
    c2 = 0.03 ** 2

    num = (2 * mu_a * mu_b + c1) * (2 * sig_ab + c2)
    den = (mu_a**2 + mu_b**2 + c1) * (sig_a**2 + sig_b**2 + c2)

    return float(num / den) if den > 0 else 0.0


def emd_2d(a: np.ndarray, b: np.ndarray) -> float:
    """Earth Mover's Distance on flattened histograms (lower = more similar)."""
    a_flat = a.ravel().astype(np.float64)
    b_flat = b.ravel().astype(np.float64)
    a_sum = a_flat.sum()
    b_sum = b_flat.sum()
    if a_sum > 0:
        a_flat = a_flat / a_sum
    if b_sum > 0:
        b_flat = b_flat / b_sum
    return float(wasserstein_distance(a_flat, b_flat))


# ============================================================================
# Power-Law Dummy Generator
# ============================================================================

def generate_power_law_dummy(grid_size_x: int = 64, grid_size_y: int = 64, alpha: float = 1.5) -> np.ndarray:
    """
    Generate a synthetic 2D histogram that follows a power law.
    Used to detect and filter trivially matching distributions.
    """
    x = np.arange(1, grid_size_x + 1, dtype=np.float64)
    y = np.arange(1, grid_size_y + 1, dtype=np.float64)
    xx, yy = np.meshgrid(x, y)
    # Power law decaying from corner
    grid = 1.0 / ((xx ** alpha) + (yy ** alpha))
    return grid / grid.max()


# ============================================================================
# Scan Engine
# ============================================================================

def run_2d_scan(burst_grid: np.ndarray,
                opts: pd.DataFrame,
                grid_size_x: int = 64,
                grid_size_y: int = 64,
                progress_bar=None) -> list[dict]:
    """
    Exhaustively search sort/shuffle/transform combos for options data
    that matches the burst grid.
    """
    results = []

    sort_axes = ["time", "strike", "size", "price", "notional"]
    sort_dirs = ["asc", "desc"]
    subsets = ["all", "calls", "puts"]
    y_axes = ["strike", "price"]

    # Also build weight modes
    weight_modes = ["count", "size", "notional"]

    total = len(sort_axes) * len(sort_dirs) * len(subsets) * len(y_axes) * len(weight_modes) * len(GRID_TRANSFORMS)
    step = 0

    # Power-law dummy
    dummy_grid = generate_power_law_dummy(grid_size_x, grid_size_y)
    dummy_score = zncc_2d(burst_grid, dummy_grid)

    for sort_by in sort_axes:
        for sort_dir in sort_dirs:
            for subset in subsets:
                for y_axis in y_axes:
                    x_n, y_n, sizes = options_to_2d(
                        opts, sort_by=sort_by, sort_direction=sort_dir,
                        subset=subset, y_axis=y_axis
                    )
                    if len(x_n) < 20:
                        step += len(weight_modes) * len(GRID_TRANSFORMS)
                        continue

                    for w_mode in weight_modes:
                        w = None
                        if w_mode == "size":
                            w = sizes
                        elif w_mode == "notional":
                            w = opts.loc[opts.index[:len(sizes)], "notional"].values if "notional" in opts.columns else sizes

                        opts_grid = rasterize_points_fast(x_n, y_n, grid_size_x, grid_size_y, w)

                        for t_name, t_fn in GRID_TRANSFORMS.items():
                            step += 1
                            if progress_bar:
                                progress_bar.progress(step / total)

                            transformed = t_fn(opts_grid)

                            # Resize if transform changed grid dimensions (e.g. transpose on non-square grids)
                            if transformed.shape != burst_grid.shape:
                                zoom_factors = (burst_grid.shape[0] / transformed.shape[0],
                                                burst_grid.shape[1] / transformed.shape[1])
                                transformed = zoom(transformed, zoom_factors, order=1)

                            score = zncc_2d(burst_grid, transformed)
                            ssim = structural_similarity(burst_grid, transformed)

                            results.append({
                                "sort_by": sort_by,
                                "direction": sort_dir,
                                "subset": subset,
                                "y_axis": y_axis,
                                "weight": w_mode,
                                "transform": t_name,
                                "zncc": score,
                                "ssim": ssim,
                                "dummy_zncc": dummy_score,
                                "excess_over_dummy": score - dummy_score,
                            })

    return results


# ============================================================================
# Visualization
# ============================================================================

def render_grid_comparison(burst_grid: np.ndarray, opts_grid: np.ndarray,
                           burst_label: str = "Burst Trades",
                           opts_label: str = "Options (transformed)"):
    """Render two 2D grids side by side using Streamlit."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # Burst
    im1 = ax1.imshow(burst_grid, origin='lower', cmap='inferno',
                     norm=mcolors.LogNorm(vmin=max(burst_grid[burst_grid > 0].min(), 0.1),
                                         vmax=burst_grid.max())
                     if burst_grid.max() > 0 and (burst_grid > 0).any() else None)
    ax1.set_title(burst_label, fontsize=12, fontweight='bold')
    ax1.set_xlabel("Time (normalized)")
    ax1.set_ylabel("Price (normalized)")
    fig.colorbar(im1, ax=ax1, shrink=0.7)

    # Options
    vmin = max(opts_grid[opts_grid > 0].min(), 0.1) if (opts_grid > 0).any() else 0.1
    im2 = ax2.imshow(opts_grid, origin='lower', cmap='inferno',
                     norm=mcolors.LogNorm(vmin=vmin, vmax=opts_grid.max())
                     if opts_grid.max() > 0 and (opts_grid > 0).any() else None)
    ax2.set_title(opts_label, fontsize=12, fontweight='bold')
    ax2.set_xlabel("Sorted Index (normalized)")
    ax2.set_ylabel(opts_label.split("(")[-1].rstrip(")") if "(" in opts_label else "Y")
    fig.colorbar(im2, ax=ax2, shrink=0.7)

    fig.tight_layout()
    return fig


# ============================================================================
# Streamlit App
# ============================================================================

def main():
    st.set_page_config(page_title="2D Shape Match", layout="wide")
    st.title("🔬 2D Shape Matching: Burst Trades ↔ Options")
    st.markdown("""
    Compare the **2D scatter shape** of burst trades against **options data**
    that's been sorted/shuffled in various ways. Filter out power-law matches.
    """)

    # ── Sidebar ──
    st.sidebar.header("⚙️ Configuration")

    ticker = st.sidebar.text_input("Ticker", value="GME")
    burst_date = st.sidebar.text_input("Burst Date", value="2024-05-17")

    grid_size_x = st.sidebar.slider("Grid Resolution X", 16, 420, 64, step=1)
    grid_size_y = st.sidebar.slider("Grid Resolution Y", 16, 420, 64, step=1)

    # Load burst data
    burst_points = load_burst_points(burst_date)
    if burst_points.empty:
        st.error(f"No burst points for {burst_date}")
        return

    # Select burst
    burst_ids = burst_points["burst_id"].unique().tolist()
    features = load_burst_features(burst_date)
    if not features.empty:
        burst_labels = []
        for bid in burst_ids:
            feat_row = features[features["burst_id"] == bid]
            if not feat_row.empty:
                n = feat_row["point_count"].values[0]
                cl = feat_row["cluster"].values[0]
                burst_labels.append(f"{bid} (n={n}, cluster={cl})")
            else:
                burst_labels.append(bid)
    else:
        burst_labels = burst_ids

    selected_idx = st.sidebar.selectbox(
        "Burst ID",
        range(len(burst_ids)),
        format_func=lambda i: burst_labels[i]
    )
    selected_burst_id = burst_ids[selected_idx]

    # Load selected burst
    burst_subset = burst_points[burst_points["burst_id"] == selected_burst_id]
    n_points = len(burst_subset)
    st.sidebar.metric("Burst Points", f"{n_points:,}")

    # Rasterize burst
    burst_x = burst_subset["norm_x"].values.astype(np.float64)
    burst_y = burst_subset["norm_y"].values.astype(np.float64)
    burst_grid = rasterize_points_fast(burst_x, burst_y, grid_size_x, grid_size_y)

    # ── Left column: Burst visualization ──
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🎯 Burst Scatter (Target)")
        fig_burst, ax = plt.subplots(figsize=(7, 5))
        ax.scatter(burst_x, burst_y, s=1, alpha=0.3, c='dodgerblue')
        ax.set_xlabel("Normalized Time")
        ax.set_ylabel("Normalized Price")
        ax.set_title(f"Burst: {selected_burst_id}\n{n_points:,} points")
        st.pyplot(fig_burst)
        plt.close()

    with col2:
        st.subheader("📊 Burst Rasterized (2D Histogram)")
        fig_grid, ax = plt.subplots(figsize=(7, 5))
        if burst_grid.max() > 0 and (burst_grid > 0).any():
            ax.imshow(burst_grid, origin='lower', cmap='inferno',
                     norm=mcolors.LogNorm(vmin=max(burst_grid[burst_grid > 0].min(), 0.1),
                                         vmax=burst_grid.max()))
        else:
            ax.imshow(burst_grid, origin='lower', cmap='inferno')
        ax.set_title(f"Rasterized {grid_size_x}×{grid_size_y}")
        ax.set_xlabel("Time bin")
        ax.set_ylabel("Price bin")
        st.pyplot(fig_grid)
        plt.close()

    st.divider()

    # ── Options Source Selection ──
    st.header("🔍 Options Source")

    mode = st.radio("Mode", ["Single Date", "Multi-Date Scan"], horizontal=True)

    if mode == "Single Date":
        avail_dates = get_available_dates(ticker)
        if not avail_dates:
            st.error(f"No options data for {ticker}")
            return

        opts_date = st.selectbox("Options Date", avail_dates,
                                 index=min(len(avail_dates)-1, 50))

        opts = load_trades(ticker, [opts_date])
        if opts.empty:
            st.error(f"No trades for {opts_date}")
            return

        st.metric("Options Trades", f"{len(opts):,}")

        # Manual exploration controls
        st.subheader("Manual Exploration")
        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a:
            sort_by = st.selectbox("Sort By", ["time", "strike", "size", "price", "notional"])
        with col_b:
            sort_dir = st.selectbox("Direction", ["asc", "desc"])
        with col_c:
            subset = st.selectbox("Subset", ["all", "calls", "puts"])
        with col_d:
            y_axis = st.selectbox("Y Axis", ["strike", "price", "size", "notional"])

        weight_mode = st.selectbox("Weight", ["count", "size", "notional"])
        grid_transform = st.selectbox("Grid Transform", list(GRID_TRANSFORMS.keys()))

        # Generate the options 2D view
        x_n, y_n, sizes = options_to_2d(
            opts, sort_by=sort_by, sort_direction=sort_dir,
            subset=subset, y_axis=y_axis
        )

        if len(x_n) > 0:
            w = None
            if weight_mode == "size":
                w = sizes
            elif weight_mode == "notional":
                nots = opts["notional"].values if "notional" in opts.columns else sizes
                w = nots[:len(x_n)]

            opts_grid = rasterize_points_fast(x_n, y_n, grid_size_x, grid_size_y, w)
            opts_grid = GRID_TRANSFORMS[grid_transform](opts_grid)

            # Resize if transform changed grid dimensions (e.g. transpose on non-square grids)
            if opts_grid.shape != burst_grid.shape:
                zoom_factors = (burst_grid.shape[0] / opts_grid.shape[0],
                                burst_grid.shape[1] / opts_grid.shape[1])
                opts_grid = zoom(opts_grid, zoom_factors, order=1)

            score = zncc_2d(burst_grid, opts_grid)
            ssim = structural_similarity(burst_grid, opts_grid)
            dummy = zncc_2d(burst_grid, generate_power_law_dummy(grid_size_x, grid_size_y))

            c1, c2, c3 = st.columns(3)
            c1.metric("ZNCC", f"{score:.4f}")
            c2.metric("SSIM", f"{ssim:.4f}")
            c3.metric("Excess over Dummy", f"{score - dummy:+.4f}",
                      delta_color="normal" if score > dummy else "inverse")

            label = f"Options {opts_date} | Sort: {sort_by} {sort_dir} | {subset} | Y: {y_axis} | W: {weight_mode} | T: {grid_transform}"
            fig = render_grid_comparison(burst_grid, opts_grid,
                                         burst_label=f"Burst {selected_burst_id}",
                                         opts_label=label)
            st.pyplot(fig)
            plt.close()

            # Show raw scatter too
            with st.expander("Raw Options Scatter"):
                fig_sc, ax_sc = plt.subplots(figsize=(10, 4))
                ax_sc.scatter(x_n, y_n, s=1, alpha=0.2, c='coral')
                ax_sc.set_xlabel(f"Sorted Index ({sort_by} {sort_dir})")
                ax_sc.set_ylabel(y_axis)
                ax_sc.set_title(f"{opts_date} | {subset} | {len(x_n):,} trades")
                st.pyplot(fig_sc)
                plt.close()

        # ── Full Scan ──
        st.divider()
        if st.button("🚀 Run Full Scan (This Date)", type="primary"):
            with st.spinner(f"Scanning all sort/transform combos for {opts_date}..."):
                prog = st.progress(0)
                results = run_2d_scan(burst_grid, opts, grid_size_x, grid_size_y, progress_bar=prog)
                prog.empty()

            df_results = pd.DataFrame(results)
            df_results = df_results.sort_values("zncc", ascending=False)

            st.subheader(f"📈 Top Matches for {opts_date}")
            st.dataframe(
                df_results.head(30),
                use_container_width=True
            )

            # Show top N matches with spectrograms
            if not df_results.empty:
                n_show = st.slider("Show top N spectrograms", 1, 10, 5, key="single_top_n")
                top_n = df_results.head(n_show)

                for rank_i, (_, row) in enumerate(top_n.iterrows()):
                    st.markdown(
                        f"**#{rank_i+1}:** Sort=`{row['sort_by']}` `{row['direction']}` | "
                        f"Subset=`{row['subset']}` | Y=`{row['y_axis']}` | "
                        f"W=`{row['weight']}` | T=`{row['transform']}` | "
                        f"ZNCC=**{row['zncc']:.4f}** | Excess={row['excess_over_dummy']:+.4f}"
                    )

                    x_r, y_r, s_r = options_to_2d(
                        opts, sort_by=row['sort_by'], sort_direction=row['direction'],
                        subset=row['subset'], y_axis=row['y_axis']
                    )
                    if len(x_r) == 0:
                        continue
                    w_r = None
                    if row['weight'] == 'size':
                        w_r = s_r
                    elif row['weight'] == 'notional':
                        w_r = opts["notional"].values[:len(x_r)] if "notional" in opts.columns else s_r
                    r_grid = rasterize_points_fast(x_r, y_r, grid_size_x, grid_size_y, w_r)
                    r_grid = GRID_TRANSFORMS[row['transform']](r_grid)
                    if r_grid.shape != burst_grid.shape:
                        zf = (burst_grid.shape[0] / r_grid.shape[0],
                              burst_grid.shape[1] / r_grid.shape[1])
                        r_grid = zoom(r_grid, zf, order=1)

                    fig_r = render_grid_comparison(
                        burst_grid, r_grid,
                        burst_label="Burst (Target)",
                        opts_label=f"#{rank_i+1}: {row['sort_by']} {row['direction']} ({row['transform']})"
                    )
                    st.pyplot(fig_r)
                    plt.close()

    else:  # Multi-Date Scan
        avail_dates = get_available_dates(ticker)
        n_dates = st.slider("Number of dates to scan", 5, len(avail_dates), min(50, len(avail_dates)))
        step = max(1, len(avail_dates) // n_dates)
        scan_dates = avail_dates[::step]

        st.info(f"Will scan {len(scan_dates)} dates: {scan_dates[0]} → {scan_dates[-1]}")

        if st.button("🚀 Run Multi-Date Scan", type="primary"):
            all_results = []
            overall_prog = st.progress(0)

            for di, d in enumerate(scan_dates):
                overall_prog.progress((di) / len(scan_dates))
                st.text(f"Scanning {d}...")

                opts = load_trades(ticker, [d])
                if opts.empty or len(opts) < 50:
                    continue

                results = run_2d_scan(burst_grid, opts, grid_size_x, grid_size_y)
                for r in results:
                    r["source_date"] = d
                all_results.extend(results)

            overall_prog.empty()

            if all_results:
                df_all = pd.DataFrame(all_results)
                df_all = df_all.sort_values("zncc", ascending=False)

                st.subheader("📈 Top Matches Across All Dates")
                st.dataframe(
                    df_all.head(50),
                    use_container_width=True
                )

                # Summary: best match per date
                best_per_date = df_all.groupby("source_date")["zncc"].max().sort_values(ascending=False)
                st.subheader("Best ZNCC per Date")
                top_20 = best_per_date.head(20)
                fig_bar, ax_bar = plt.subplots(figsize=(12, 4))
                ax_bar.bar(range(len(top_20)), top_20.values, color='coral')
                ax_bar.set_xticks(range(len(top_20)))
                ax_bar.set_xticklabels(top_20.index, rotation=45, ha='right', fontsize=8)
                ax_bar.set_ylabel("Best ZNCC")
                ax_bar.set_title("Top 20 Dates by Best ZNCC Score")
                fig_bar.tight_layout()
                st.pyplot(fig_bar)
                plt.close()

                # ── Top-N Spectrograms ──
                st.subheader("🔬 Top Match Spectrograms")
                n_show_multi = st.slider("Show top N spectrograms", 1, 10, 5, key="multi_top_n")
                top_n_multi = df_all.head(n_show_multi)

                _cached_opts = {}  # avoid reloading the same date
                for rank_i, (_, row) in enumerate(top_n_multi.iterrows()):
                    src_date = row["source_date"]
                    st.markdown(
                        f"**#{rank_i+1}** ({src_date}): Sort=`{row['sort_by']}` `{row['direction']}` | "
                        f"Subset=`{row['subset']}` | Y=`{row['y_axis']}` | "
                        f"W=`{row['weight']}` | T=`{row['transform']}` | "
                        f"ZNCC=**{row['zncc']:.4f}** | Excess={row['excess_over_dummy']:+.4f}"
                    )

                    if src_date not in _cached_opts:
                        _cached_opts[src_date] = load_trades(ticker, [src_date])
                    opts_rd = _cached_opts[src_date]
                    if opts_rd.empty:
                        st.caption("(data unavailable)")
                        continue

                    x_r, y_r, s_r = options_to_2d(
                        opts_rd, sort_by=row['sort_by'], sort_direction=row['direction'],
                        subset=row['subset'], y_axis=row['y_axis']
                    )
                    if len(x_r) == 0:
                        continue
                    w_r = None
                    if row['weight'] == 'size':
                        w_r = s_r
                    elif row['weight'] == 'notional':
                        w_r = opts_rd["notional"].values[:len(x_r)] if "notional" in opts_rd.columns else s_r
                    r_grid = rasterize_points_fast(x_r, y_r, grid_size_x, grid_size_y, w_r)
                    r_grid = GRID_TRANSFORMS[row['transform']](r_grid)
                    if r_grid.shape != burst_grid.shape:
                        zf = (burst_grid.shape[0] / r_grid.shape[0],
                              burst_grid.shape[1] / r_grid.shape[1])
                        r_grid = zoom(r_grid, zf, order=1)

                    fig_r = render_grid_comparison(
                        burst_grid, r_grid,
                        burst_label="Burst (Target)",
                        opts_label=f"#{rank_i+1}: {src_date} | {row['sort_by']} {row['direction']} ({row['transform']})"
                    )
                    st.pyplot(fig_r)
                    plt.close()
            else:
                st.warning("No results found.")


if __name__ == "__main__":
    main()
