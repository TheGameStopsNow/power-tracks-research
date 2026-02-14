#!/usr/bin/env python3
"""
Gamma Spectrogram — Rolling ACF Heatmap Engine
================================================
Visualizes the dynamic battle between Long Gamma dampening and Short Gamma
amplification over time for any ticker with local Polygon/ThetaData tick data.

Output: Time × Lag ACF heatmap where:
  - Blue  = negative ACF (Long Gamma dampening / mean-reversion)
  - Red   = positive ACF (Short Gamma amplification / momentum)
  - White = neutral (random walk)

Usage:
cd . && .venv/bin/python -m streamlit run research/options_hedging_microstructure/gamma_spectrogram.py
"""
import sys
import time as _time
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Data infrastructure (reuse temporal_convolution_engine loaders)
# ---------------------------------------------------------------------------
ENGINE_DIR = Path(__file__).parent.parent / "phase98_cluster_bridge"
sys.path.insert(0, str(ENGINE_DIR))

from temporal_convolution_engine import load_equity_day, load_options_day, get_available_equity_dates

POLYGON_DIR = (
    Path(__file__).parent.parent.parent / "data" / "raw" / "polygon" / "trades"
)

TRADING_DAY_MINUTES = 390  # 6.5 hours


def lag_to_label(lag: int, interval_sec: float) -> str:
    """Convert a lag index + bar interval into a human-readable time string."""
    total_min = lag * interval_sec / 60.0
    total_days = total_min / TRADING_DAY_MINUTES

    if total_min < 1:
        return f"{lag * interval_sec:.0f}s"
    elif total_min < 60:
        return f"{total_min:.0f}m"
    elif total_min < TRADING_DAY_MINUTES:
        h = int(total_min // 60)
        m = int(total_min % 60)
        return f"{h}h{m:02d}m" if m else f"{h}h"
    else:
        h = int(total_min // 60)
        m = int(total_min % 60)
        return f"{h}h{m:02d}m / {total_days:.1f}d"


# ---------------------------------------------------------------------------
# Core: compute ACF for a single day
# ---------------------------------------------------------------------------
def compute_daily_acf(
    prices: pd.Series,
    timestamps: pd.Series,
    interval_sec: float = 60.0,
    max_lag: int = 20,
) -> np.ndarray:
    """
    Compute autocorrelation of returns at `interval_sec` bar size.
    Returns array of ACF values from lag 1..max_lag (lag-0 is always 1.0).
    """
    df = pd.DataFrame({"ts": timestamps, "price": prices}).set_index("ts")
    bars = df.resample(f"{int(interval_sec)}s").last().dropna()
    returns = bars["price"].pct_change().dropna().values

    if len(returns) < max_lag + 10:
        return np.full(max_lag, np.nan)

    n = len(returns)
    mean = returns.mean()
    var = np.var(returns)
    if var < 1e-12:
        return np.full(max_lag, np.nan)

    acf = np.zeros(max_lag)
    for lag in range(1, max_lag + 1):
        acf[lag - 1] = (
            np.mean((returns[: n - lag] - mean) * (returns[lag:] - mean)) / var
        )
    return acf


def _resample_returns(prices: pd.Series, timestamps: pd.Series,
                     interval_sec: float) -> np.ndarray:
    """Resample tick data into bar returns."""
    df = pd.DataFrame({"ts": timestamps, "price": prices}).set_index("ts")
    bars = df.resample(f"{int(interval_sec)}s").last().dropna()
    return bars["price"].pct_change().dropna().values


def _acf_from_returns(returns: np.ndarray, max_lag: int) -> np.ndarray:
    """Compute ACF lag 1..max_lag from a pre-computed returns array."""
    if len(returns) < max_lag + 10:
        return np.full(max_lag, np.nan)
    n = len(returns)
    mean = returns.mean()
    var = np.var(returns)
    if var < 1e-12:
        return np.full(max_lag, np.nan)
    acf = np.zeros(max_lag)
    for lag in range(1, max_lag + 1):
        acf[lag - 1] = (
            np.mean((returns[: n - lag] - mean) * (returns[lag:] - mean)) / var
        )
    return acf


# ---------------------------------------------------------------------------
# Rolling: compute ACF for every day in a window
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Computing rolling ACF…")
def compute_rolling_acf(
    symbol: str,
    dates: list[str],
    interval_sec: float = 60.0,
    max_lag: int = 20,
) -> tuple[list[str], np.ndarray]:
    """
    For each date, compute the lag-1..max_lag ACF.
    Returns (valid_dates, acf_matrix) where acf_matrix is shape [n_days, max_lag].
    """
    valid_dates: list[str] = []
    acf_rows: list[np.ndarray] = []

    for date_str in dates:
        eq = load_equity_day(symbol, date_str)
        if eq.empty or len(eq) < 100:
            continue
        acf = compute_daily_acf(eq["price"], eq["ts"], interval_sec, max_lag)
        if np.isnan(acf).all():
            continue
        valid_dates.append(date_str)
        acf_rows.append(acf)

    if not acf_rows:
        return [], np.array([])

    return valid_dates, np.stack(acf_rows)


# ---------------------------------------------------------------------------
# Multi-day concatenation mode
# ---------------------------------------------------------------------------


def _acf_from_returns_gapped(returns: np.ndarray, max_lag: int) -> np.ndarray:
    """Compute ACF with NaN-aware pairs — skip any pair where either value is NaN."""
    valid = ~np.isnan(returns)
    clean = np.where(valid, returns, 0.0)  # zero-fill for mean calc
    n_valid = valid.sum()
    if n_valid < max_lag + 10:
        return np.full(max_lag, np.nan)
    mean = np.nanmean(returns)
    var = np.nanvar(returns)
    if var < 1e-12:
        return np.full(max_lag, np.nan)

    acf = np.zeros(max_lag)
    centered = np.where(valid, returns - mean, np.nan)
    for lag in range(1, max_lag + 1):
        x = centered[: len(returns) - lag]
        y = centered[lag:]
        pair_valid = ~np.isnan(x) & ~np.isnan(y)
        if pair_valid.sum() < 20:
            acf[lag - 1] = np.nan
        else:
            acf[lag - 1] = np.mean(x[pair_valid] * y[pair_valid]) / var
    return acf
@st.cache_data(show_spinner="Computing multi-day ACF…")
def compute_rolling_multiday_acf(
    symbol: str,
    dates: list[str],
    interval_sec: float = 60.0,
    max_lag: int = 20,
    window_days: int = 5,
    stride: int = 1,
) -> tuple[list[str], np.ndarray]:
    """
    Slide a window of `window_days` consecutive days, concatenate their
    returns into one long series, and compute ACF on that.
    Labeled by the last date in each window.
    stride: advance by this many days between windows (1 = full overlap).
    """
    # Pre-load all returns
    day_returns: dict[str, np.ndarray] = {}
    for date_str in dates:
        eq = load_equity_day(symbol, date_str)
        if eq.empty or len(eq) < 50:
            continue
        rets = _resample_returns(eq["price"], eq["ts"], interval_sec)
        if len(rets) > 10:
            day_returns[date_str] = rets

    # Ordered list of dates that actually have data
    available = [d for d in dates if d in day_returns]

    valid_dates: list[str] = []
    acf_rows: list[np.ndarray] = []

    for i in range(window_days - 1, len(available), stride):
        window_dates = available[i - window_days + 1 : i + 1]
        if len(window_dates) < window_days:
            continue
        # Concatenate returns across the window
        concat = np.concatenate([day_returns[d] for d in window_dates])
        acf = _acf_from_returns(concat, max_lag)
        if np.isnan(acf).all():
            continue
        valid_dates.append(available[i])  # label = last date in window
        acf_rows.append(acf)

    if not acf_rows:
        return [], np.array([])

    return valid_dates, np.stack(acf_rows)


# ---------------------------------------------------------------------------
# Multi-day concatenation with NaN gap barriers
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Computing gapped multi-day ACF…")
def compute_rolling_multiday_acf_gapped(
    symbol: str,
    dates: list[str],
    interval_sec: float = 60.0,
    max_lag: int = 20,
    window_days: int = 5,
    stride: int = 1,
) -> tuple[list[str], np.ndarray]:
    """
    Like compute_rolling_multiday_acf, but inserts a NaN barrier between
    each day's returns to prevent cross-day contamination.
    ACF pairs that span a day boundary are excluded from the computation.
    """
    day_returns: dict[str, np.ndarray] = {}
    for date_str in dates:
        eq = load_equity_day(symbol, date_str)
        if eq.empty or len(eq) < 50:
            continue
        rets = _resample_returns(eq["price"], eq["ts"], interval_sec)
        if len(rets) > 10:
            day_returns[date_str] = rets

    available = [d for d in dates if d in day_returns]
    valid_dates: list[str] = []
    acf_rows: list[np.ndarray] = []

    for i in range(window_days - 1, len(available), stride):
        window_dates = available[i - window_days + 1 : i + 1]
        if len(window_dates) < window_days:
            continue
        # Concatenate with NaN barriers between days
        segments = []
        for d in window_dates:
            segments.append(day_returns[d])
            segments.append(np.array([np.nan]))  # barrier
        # Remove trailing barrier
        concat = np.concatenate(segments[:-1])
        acf = _acf_from_returns_gapped(concat, max_lag)
        if np.isnan(acf).all():
            continue
        valid_dates.append(available[i])
        acf_rows.append(acf)

    if not acf_rows:
        return [], np.array([])
    return valid_dates, np.stack(acf_rows)


# ---------------------------------------------------------------------------
# Bar-stride mode: slide a fixed-width window across concatenated bars
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Computing bar-stride ACF…")
def compute_bar_stride_acf(
    symbol: str,
    dates: list[str],
    interval_sec: float = 60.0,
    max_lag: int = 20,
    window_bars: int = 200,
    bar_stride: int = 1,
    gap_barrier: bool = False,
) -> tuple[list[str], np.ndarray]:
    """
    Concatenate ALL days into one long return series, then slide a
    fixed-width window (in bars) with a configurable bar stride.

    This decouples the stride from the trading-day structure entirely.
    Each window position is labelled by the date containing its center bar.

    Parameters
    ----------
    window_bars : width of the sliding window in bars
    bar_stride : advance by this many bars between consecutive ACF columns
    gap_barrier : if True, insert NaN at day boundaries to block cross-day pairs
    """
    # Pre-load all returns per day
    day_returns: dict[str, np.ndarray] = {}
    day_order: list[str] = []
    for date_str in dates:
        eq = load_equity_day(symbol, date_str)
        if eq.empty or len(eq) < 50:
            continue
        rets = _resample_returns(eq["price"], eq["ts"], interval_sec)
        if len(rets) > 10:
            day_returns[date_str] = rets
            day_order.append(date_str)

    if not day_order:
        return [], np.array([])

    # Build the full concatenated series and a parallel date-index array
    all_rets: list[np.ndarray] = []
    bar_to_date: list[str] = []  # which date each bar belongs to

    for d in day_order:
        rets = day_returns[d]
        if gap_barrier and all_rets:
            # Insert NaN barrier between days
            all_rets.append(np.array([np.nan]))
            bar_to_date.append(d)
        all_rets.append(rets)
        bar_to_date.extend([d] * len(rets))

    full_series = np.concatenate(all_rets)
    n_total = len(full_series)

    if n_total < window_bars:
        return [], np.array([])

    valid_dates: list[str] = []
    acf_rows: list[np.ndarray] = []

    acf_fn = _acf_from_returns_gapped if gap_barrier else _acf_from_returns

    for start in range(0, n_total - window_bars + 1, bar_stride):
        window = full_series[start : start + window_bars]
        acf = acf_fn(window, max_lag)
        if np.isnan(acf).all():
            continue

        # Label by the date at the center of this window
        center = start + window_bars // 2
        center = min(center, len(bar_to_date) - 1)
        label = bar_to_date[center]

        valid_dates.append(label)
        acf_rows.append(acf)

    if not acf_rows:
        return [], np.array([])
    return valid_dates, np.stack(acf_rows)



# ---------------------------------------------------------------------------
# Deseasonalize: subtract mean lag profile
# ---------------------------------------------------------------------------
def deseasonalize_acf(acf_matrix: np.ndarray) -> np.ndarray:
    """
    Subtract the cross-date mean at each lag to remove shared horizontal
    banding. Returns the residual ACF matrix.
    """
    mean_profile = np.nanmean(acf_matrix, axis=0)  # shape [max_lag]
    return acf_matrix - mean_profile[np.newaxis, :]


# ---------------------------------------------------------------------------
# Deinterlace: remove day-boundary harmonic from ACF lag axis
# ---------------------------------------------------------------------------

def deinterlace_acf(
    acf_matrix: np.ndarray,
    bars_per_day: float,
    n_harmonics: int = 4,
    notch_width: float = 1.5,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Remove the periodic modulation caused by overnight gaps by notch-filtering
    the day-boundary frequency and its harmonics from the lag axis.

    The ACF at each date has a periodic component at frequency 1/bars_per_day
    (and harmonics 2/bpd, 3/bpd, ...) caused by the overnight gap return leaking
    through the multi-day concatenation. This function:

    1. FFTs each date column along the lag axis
    2. Identifies frequency bins near k/bars_per_day for k=1..n_harmonics
    3. Zeros those bins (notch filter)
    4. Inverse FFTs to get the cleaned ACF

    Also removes the DC component (mean) along the lag axis, which captures
    the overall level shift from concatenating heterogeneous days.

    Parameters
    ----------
    acf_matrix : shape [n_dates, max_lag]
    bars_per_day : float — e.g. 26.0 for 900s bars, 6.5 for 3600s bars
    n_harmonics : how many overtones of 1/bpd to notch (default 4)
    notch_width : how many frequency bins wide each notch should be (default 1.5)

    Returns
    -------
    (cleaned, periodic_field) — both shape [n_dates, max_lag]
        cleaned: the ACF with day-boundary harmonics removed
        periodic_field: the removed component (what creates the "imagery")
    """
    n_dates, max_lag = acf_matrix.shape
    cleaned = np.zeros_like(acf_matrix)
    periodic = np.zeros_like(acf_matrix)

    # Frequency resolution: bin spacing = 1/max_lag
    freqs = np.fft.rfftfreq(max_lag)  # [0, 1/N, 2/N, ..., 0.5]

    # Build notch mask (1 = keep, 0 = suppress)
    mask = np.ones(len(freqs))
    for k in range(1, n_harmonics + 1):
        target_freq = k / bars_per_day
        if target_freq > 0.5:
            break  # above Nyquist
        for j, f in enumerate(freqs):
            if abs(f - target_freq) < notch_width / max_lag:
                mask[j] = 0.0

    for i in range(n_dates):
        row = acf_matrix[i]
        if np.isnan(row).all():
            cleaned[i] = row
            periodic[i] = np.zeros(max_lag)
            continue

        # Fill NaN with 0 for FFT
        filled = np.where(np.isnan(row), 0.0, row)
        spectrum = np.fft.rfft(filled)

        # Cleaned = only the non-harmonic frequencies
        clean_spectrum = spectrum * mask
        harm_spectrum = spectrum * (1 - mask)

        cleaned[i] = np.fft.irfft(clean_spectrum, n=max_lag)
        periodic[i] = np.fft.irfft(harm_spectrum, n=max_lag)

        # Restore NaN positions
        nan_mask = np.isnan(row)
        cleaned[i][nan_mask] = np.nan
        periodic[i][nan_mask] = np.nan

    return cleaned, periodic


def compute_interlace_diagnostics(
    acf_matrix: np.ndarray,
    bars_per_day: float,
    n_harmonics: int = 4,
) -> dict:
    """
    Quantify how much of the spectrogram's visual structure comes from
    the day-boundary harmonic vs genuine intraday ACF structure.

    Returns a dict with:
      - harmonic_power_pct: % of total spectral power at day harmonics
      - per_harmonic: power at each harmonic k=1..n
      - bars_per_day: the input value
      - dominant_period_lags: the lag period of the strongest harmonic
    """
    _, max_lag = acf_matrix.shape
    freqs = np.fft.rfftfreq(max_lag)

    total_power = 0.0
    harmonic_power = 0.0
    per_harmonic = {}

    for i in range(acf_matrix.shape[0]):
        row = acf_matrix[i]
        if np.isnan(row).all():
            continue
        filled = np.where(np.isnan(row), 0.0, row)
        power = np.abs(np.fft.rfft(filled)) ** 2
        total_power += power.sum()

        for k in range(1, n_harmonics + 1):
            target_freq = k / bars_per_day
            if target_freq > 0.5:
                break
            for j, f in enumerate(freqs):
                if abs(f - target_freq) < 1.5 / max_lag:
                    hp = float(power[j])
                    harmonic_power += hp
                    per_harmonic[k] = per_harmonic.get(k, 0.0) + hp

    pct = (harmonic_power / total_power * 100) if total_power > 0 else 0.0

    # Find dominant harmonic
    dominant_k = max(per_harmonic, key=per_harmonic.get) if per_harmonic else 1
    dominant_period = bars_per_day / dominant_k

    return {
        "harmonic_power_pct": round(pct, 1),
        "per_harmonic": {k: round(v / total_power * 100, 1) for k, v in per_harmonic.items()},
        "bars_per_day": bars_per_day,
        "dominant_period_lags": round(dominant_period, 1),
        "n_harmonics_checked": len(per_harmonic),
    }


# ---------------------------------------------------------------------------
# Overnight gap return ACF
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Computing overnight gap ACF…")
def compute_overnight_gap_acf(
    symbol: str,
    dates: list[str],
    max_lag: int = 20,
) -> tuple[list[str], np.ndarray]:
    """
    Compute the ACF of close-to-open overnight gap returns.
    Each 'bar' is the return from prev day's last trade to this day's first trade.
    Returns a single ACF row (the gap series is one long time series).
    """
    gap_returns = []
    gap_dates = []
    prev_close = None

    for date_str in dates:
        eq = load_equity_day(symbol, date_str)
        if eq.empty or len(eq) < 50:
            prev_close = None
            continue
        day_open = eq["price"].iloc[0]
        day_close = eq["price"].iloc[-1]
        if prev_close is not None and prev_close > 0:
            gap_ret = (day_open - prev_close) / prev_close
            gap_returns.append(gap_ret)
            gap_dates.append(date_str)
        prev_close = day_close

    if len(gap_returns) < max_lag + 10:
        return [], np.array([])

    gap_arr = np.array(gap_returns)
    acf = _acf_from_returns(gap_arr, max_lag)

    return gap_dates, acf


# ---------------------------------------------------------------------------
# Daily close prices for price panel
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False, ttl=3600)
def get_daily_closes(symbol: str, dates: list[str], _v: int = 5) -> dict[str, float]:
    """Return {date_str: split-adjusted close_price} for each date.

    Primary source: Polygon REST API ``/v2/aggs`` which returns
    split-adjusted daily bars by default.
    Fallback: raw last-trade prices from local tick data (NOT adjusted).
    """
    import os, requests as _req

    api_key = os.environ.get("POLYGON_API_KEY")
    if api_key and dates:
        try:
            # Convert YYYYMMDD → YYYY-MM-DD for Polygon
            def _fmt(d: str) -> str:
                d = d.replace("-", "")
                return f"{d[:4]}-{d[4:6]}-{d[6:8]}"

            from_date = _fmt(min(dates))
            to_date = _fmt(max(dates))
            url = (
                f"https://api.polygon.io/v2/aggs/ticker/{symbol}"
                f"/range/1/day/{from_date}/{to_date}"
            )
            params = {
                "adjusted": "true",
                "sort": "asc",
                "limit": 50000,
                "apiKey": api_key,
            }
            resp = _req.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    # Build date→close map from Polygon results
                    closes: dict[str, float] = {}
                    date_set = set(dates)
                    for bar in results:
                        # bar["t"] is ms-epoch → convert to YYYYMMDD
                        ts = pd.Timestamp(bar["t"], unit="ms", tz="US/Eastern")
                        dstr = ts.strftime("%Y-%m-%d")
                        # Match against our date list (which may be YYYYMMDD)
                        if dstr in date_set:
                            closes[dstr] = bar["c"]
                        dstr_compact = dstr.replace("-", "")
                        if dstr_compact in date_set:
                            closes[dstr_compact] = bar["c"]
                    if closes:
                        return closes
        except Exception:
            pass  # fall through to raw tick fallback

    # Fallback: raw tick-data closes (NOT split-adjusted)
    closes = {}
    for d in dates:
        eq = load_equity_day(symbol, d)
        if not eq.empty and len(eq) > 0:
            closes[d] = float(eq["price"].iloc[-1])
    return closes


# ---------------------------------------------------------------------------
# Heatmap rendering
# ---------------------------------------------------------------------------
def render_spectrogram(
    dates: list[str],
    acf_matrix: np.ndarray,
    symbol: str,
    interval_sec: float,
    vmin: float = -0.25,
    vmax: float = 0.25,
    prices: dict[str, float] | None = None,
):
    """
    Render the Gamma Spectrogram as a Plotly heatmap.
    X=date, Y=lag, Z=ACF value.
    Blue=dampening (Long Gamma), Red=amplification (Short Gamma).
    Optional third panel shows daily closing prices.
    """
    max_lag = acf_matrix.shape[1]
    lag_labels = [lag_to_label(i + 1, interval_sec) for i in range(max_lag)]

    # Custom diverging colorscale: blue (dampening) ← white → red (amplification)
    colorscale = [
        [0.0, "#1a237e"],     # deep blue
        [0.15, "#1565c0"],    # blue
        [0.35, "#64b5f6"],    # light blue
        [0.5, "#ffffff"],     # white (neutral)
        [0.65, "#ef9a9a"],    # light red
        [0.85, "#c62828"],    # red
        [1.0, "#b71c1c"],     # deep red
    ]

    has_prices = prices and any(d in prices for d in dates)
    n_rows = 3 if has_prices else 2
    row_heights = [0.60, 0.20, 0.20] if has_prices else [0.75, 0.25]
    subtitles = [
        f"Gamma Spectrogram — {symbol} ({int(interval_sec)}s bars)",
        f"Lag-1 ACF Timeline — Dampening vs Amplification",
    ]
    if has_prices:
        subtitles.append(f"Price Action — {symbol}")

    fig = make_subplots(
        rows=n_rows,
        cols=1,
        row_heights=row_heights,
        shared_xaxes=True,
        vertical_spacing=0.05,
        subplot_titles=subtitles,
    )

    # Main heatmap
    fig.add_trace(
        go.Heatmap(
            z=acf_matrix.T,
            x=dates,
            y=lag_labels,
            colorscale=colorscale,
            zmin=vmin,
            zmax=vmax,
            colorbar=dict(
                title=dict(text="ACF", side="right"),
                len=0.5 if has_prices else 0.7,
                y=0.75 if has_prices else 0.65,
            ),
            customdata=np.array([[i + 1] * len(dates) for i in range(max_lag)]),
            hovertemplate=(
                "Date: %{x}<br>"
                "Lag %{customdata} bars (%{y})<br>"
                "ACF: %{z:.4f}<br>"
                "<extra></extra>"
            ),
        ),
        row=1,
        col=1,
    )

    # Panel 2: Lag-1 ACF bar chart with MACD-style MAs
    lag1 = acf_matrix[:, 0]

    # Moving averages
    fast_win, slow_win = 8, 30
    lag1_series = pd.Series(lag1)
    fast_ma = lag1_series.rolling(fast_win, min_periods=1).mean().values
    slow_ma = lag1_series.rolling(slow_win, min_periods=1).mean().values

    # Bar coloring: lighter when trend is flipping
    colors = []
    for i, v in enumerate(lag1):
        # Is fast MA crossing or diverging from slow MA?
        trend_confirming = (fast_ma[i] < slow_ma[i])  # both deepening
        if i > 0:
            prev_sign = 1 if lag1[i - 1] > 0 else -1
            curr_sign = 1 if v > 0 else -1
            flipping = (prev_sign != curr_sign) or (fast_ma[i] > slow_ma[i] and v < 0)
        else:
            flipping = False

        if v > 0:
            # Amplification (red) — lighter when fading back to dampening
            colors.append("rgba(198,40,40,0.35)" if flipping or fast_ma[i] < slow_ma[i]
                          else "rgba(198,40,40,1.0)")
        else:
            # Dampening (blue) — lighter when rising toward zero / flipping
            colors.append("rgba(21,101,192,0.35)" if flipping or fast_ma[i] > slow_ma[i]
                          else "rgba(21,101,192,1.0)")

    fig.add_trace(
        go.Bar(
            x=dates,
            y=lag1,
            marker_color=colors,
            name="Lag-1 ACF",
            hovertemplate="Date: %{x}<br>ACF₁: %{y:.4f}<extra></extra>",
        ),
        row=2,
        col=1,
    )

    # Fast MA line
    fig.add_trace(
        go.Scatter(
            x=dates, y=fast_ma,
            mode="lines",
            line=dict(color="#ffd54f", width=1.5),
            name=f"Fast MA({fast_win})",
            hovertemplate="Fast MA: %{y:.4f}<extra></extra>",
        ),
        row=2, col=1,
    )

    # Slow MA line
    fig.add_trace(
        go.Scatter(
            x=dates, y=slow_ma,
            mode="lines",
            line=dict(color="#ff8a65", width=1.5, dash="dash"),
            name=f"Slow MA({slow_win})",
            hovertemplate="Slow MA: %{y:.4f}<extra></extra>",
        ),
        row=2, col=1,
    )


    fig.add_hline(y=0, line_dash="dot", line_color="gray", row=2, col=1)
    fig.add_hline(
        y=-0.2, line_dash="dash", line_color="rgba(102,187,106,0.5)",
        annotation_text="Buy zone (−0.2)",
        annotation_position="bottom right",
        annotation_font_color="rgba(102,187,106,0.7)",
        annotation_font_size=10,
        row=2, col=1,
    )

    # Panel 3: Price action
    if has_prices:
        price_vals = [prices.get(d, np.nan) for d in dates]
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=price_vals,
                mode="lines",
                line=dict(color="#e0e0e0", width=1.5),
                fill="tozeroy",
                fillcolor="rgba(255,255,255,0.04)",
                name="Close",
                hovertemplate="Date: %{x}<br>Close: $%{y:.2f}<extra></extra>",
            ),
            row=3,
            col=1,
        )
        fig.update_yaxes(
            showgrid=True, gridcolor="#222", tickprefix="$",
            type="log",
            row=3, col=1,
        )

    # Layout
    fig.update_layout(
        height=900 if has_prices else 800,
        template="plotly_dark",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font=dict(family="JetBrains Mono, monospace", size=12),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1.0,
            font=dict(size=10), bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(t=60, b=40, l=60, r=40),
    )

    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False, row=1, col=1)
    fig.update_yaxes(showgrid=True, gridcolor="#333", row=2, col=1)

    return fig


# ---------------------------------------------------------------------------
# Summary statistics panel
# ---------------------------------------------------------------------------
def compute_regime_stats(
    dates: list[str], acf_matrix: np.ndarray
) -> dict:
    """Compute summary statistics for the spectrogram."""
    lag1 = acf_matrix[:, 0]
    n_dampened = np.sum(lag1 < 0)
    n_amplified = np.sum(lag1 > 0)
    n_total = len(lag1)

    return {
        "n_days": n_total,
        "n_dampened": int(n_dampened),
        "n_amplified": int(n_amplified),
        "pct_dampened": n_dampened / n_total * 100 if n_total > 0 else 0,
        "pct_amplified": n_amplified / n_total * 100 if n_total > 0 else 0,
        "mean_lag1": float(np.nanmean(lag1)),
        "median_lag1": float(np.nanmedian(lag1)),
        "min_lag1": float(np.nanmin(lag1)),
        "max_lag1": float(np.nanmax(lag1)),
        "std_lag1": float(np.nanstd(lag1)),
        "regime": "LONG GAMMA DEFAULT" if n_dampened > n_amplified else "SHORT GAMMA DOMINANT",
    }


# ---------------------------------------------------------------------------
# Per-expiration ACF — options volume ACF for individual expiry dates
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _scan_available_expirations(
    symbol: str,
    dates: list[str],
) -> list[str]:
    """
    Scan every date in the range to discover all unique expiration dates
    that had actual trading activity. Returns sorted list of normalized
    expiry strings (YYYY-MM-DD).
    """
    expirations: set[str] = set()
    for date_str in dates:
        opts = load_options_day(symbol, date_str)
        if opts.empty:
            continue
        # Handle both column name variants
        exp_col = "expiration" if "expiration" in opts.columns else (
            "expiry" if "expiry" in opts.columns else None
        )
        if exp_col is None:
            continue
        # Normalize expiry formats to YYYY-MM-DD
        for raw in opts[exp_col].unique():
            raw_str = str(raw).replace("-", "")
            if len(raw_str) == 8 and raw_str.isdigit():
                expirations.add(f"{raw_str[:4]}-{raw_str[4:6]}-{raw_str[6:8]}")
    return sorted(expirations)


@st.cache_data(show_spinner="Computing per-expiration volume ACF…")
def compute_expiration_volume_acf(
    symbol: str,
    dates: list[str],
    interval_sec: float,
    max_lag: int,
    window_days: int,
    stride: int,
    expiry_date: str,
) -> tuple[list[str], np.ndarray]:
    """
    For each rolling window, load options trades matching a specific
    expiration date, resample into volume bars, compute ACF.
    """
    # Normalize target expiry to both formats for matching
    exp_nodash = expiry_date.replace("-", "")
    exp_dash = f"{exp_nodash[:4]}-{exp_nodash[4:6]}-{exp_nodash[6:8]}"

    # Pre-load per-day volume bars
    day_vol_bars: dict[str, np.ndarray] = {}
    for date_str in dates:
        opts = load_options_day(symbol, date_str)
        if opts.empty or "timestamp" not in opts.columns:
            continue
        # Handle both column name variants
        exp_col = "expiration" if "expiration" in opts.columns else (
            "expiry" if "expiry" in opts.columns else None
        )
        if exp_col is None:
            continue

        # Match either format
        mask = opts[exp_col].isin([exp_nodash, exp_dash])
        filtered = opts[mask]
        if filtered.empty:
            continue

        # Resample into volume bars
        ts = filtered.set_index("timestamp")
        vol_bars = ts.resample(f"{int(interval_sec)}s")["size"].sum().fillna(0)
        vol = vol_bars.values.astype(float)

        if len(vol) >= 2:
            day_vol_bars[date_str] = vol

    available = [d for d in dates if d in day_vol_bars]
    if not available:
        return [], np.array([])

    # Ensure window_days doesn't exceed available data
    win = max(1, min(window_days, len(available)))

    valid_dates: list[str] = []
    acf_rows: list[np.ndarray] = []

    for i in range(win - 1, len(available), max(1, stride)):
        window_dates = available[i - win + 1 : i + 1]
        if len(window_dates) < win:
            continue
        concat = np.concatenate([day_vol_bars[d] for d in window_dates])
        if len(concat) < max_lag + 5:
            continue
        acf = _acf_from_returns(concat, max_lag)
        if np.isnan(acf).all():
            continue
        valid_dates.append(available[i])
        acf_rows.append(acf)

    if not acf_rows:
        return [], np.array([])

    return valid_dates, np.stack(acf_rows)


# ---------------------------------------------------------------------------
# Streamlit App
# ---------------------------------------------------------------------------
def main():
    st.set_page_config(
        page_title="Gamma Spectrogram",
        page_icon="🌊",
        layout="wide",
    )

    st.markdown(
        """
        <style>
        .stApp { background-color: #0e1117; }
        .metric-card {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border: 1px solid #333;
            border-radius: 8px;
            padding: 16px;
            text-align: center;
        }
        .metric-card h3 { margin: 0; font-size: 14px; color: #888; }
        .metric-card .value { font-size: 28px; font-weight: bold; }
        .dampened { color: #64b5f6; }
        .amplified { color: #ef5350; }
        .neutral { color: #fff; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("🌊 Gamma Spectrogram")
    st.caption(
        "Rolling ACF heatmap — visualizing the dynamic battle between "
        "**Long Gamma dampening** (blue) and **Short Gamma amplification** (red)"
    )

    # Sidebar controls
    with st.sidebar:
        st.header("⚙️ Controls")

        # Discover available tickers
        available = sorted(
            d.name.split("=")[1]
            for d in POLYGON_DIR.glob("symbol=*")
            if d.is_dir()
        )
        symbol = st.selectbox("Ticker", available, index=available.index("GME") if "GME" in available else 0)

        # Get available dates
        all_dates = get_available_equity_dates(symbol)
        if not all_dates:
            st.error(f"No equity data found for {symbol}")
            return

        st.info(f"📊 {len(all_dates)} trading days available")

        # Date range with quick-shift buttons
        max_idx = len(all_dates) - 1

        # Initialize session state — these keys ARE the widget keys
        if "spec_start_idx" not in st.session_state:
            st.session_state.spec_start_idx = 0
        if "spec_end_idx" not in st.session_state:
            st.session_state.spec_end_idx = min(1500, max_idx)

        def _shift_both(delta: int):
            """on_click callback: shift both indices by delta."""
            s = max(0, min(st.session_state.spec_start_idx + delta, max_idx))
            e = max(0, min(st.session_state.spec_end_idx + delta, max_idx))
            st.session_state.spec_start_idx = s
            st.session_state.spec_end_idx = e

        # Quick-shift: both together
        st.caption("📅 Shift both")
        bcol1, bcol2, bcol3, bcol4 = st.columns(4)
        with bcol1:
            st.button("◀◀ −5d", key="both_back5", use_container_width=True,
                      on_click=_shift_both, args=(-5,))
        with bcol2:
            st.button("◀ −1d", key="both_back1", use_container_width=True,
                      on_click=_shift_both, args=(-1,))
        with bcol3:
            st.button("▶ +1d", key="both_fwd1", use_container_width=True,
                      on_click=_shift_both, args=(1,))
        with bcol4:
            st.button("▶▶ +5d", key="both_fwd5", use_container_width=True,
                      on_click=_shift_both, args=(5,))

        col1, col2 = st.columns(2)
        with col1:
            start_idx = st.number_input(
                "Start (day index)", min_value=0, max_value=max_idx,
                key="spec_start_idx",
            )
        with col2:
            end_idx = st.number_input(
                "End (day index)", min_value=0, max_value=max_idx,
                key="spec_end_idx",
            )

        selected_dates = all_dates[int(start_idx):int(end_idx) + 1]
        if len(selected_dates) > 0:
            st.caption(f"Range: {selected_dates[0]} → {selected_dates[-1]} ({len(selected_dates)} days)")
        else:
            st.warning("Start index must be less than end index.")
            return

        st.divider()

        interval = st.select_slider(
            "Bar interval (seconds)",
            options=[1, 3, 4, 5, 10, 15, 30, 60, 69, 120, 300, 420,600, 700, 840, 900, 1200, 1680, 1800, 3600],
            value=900,
        )

        # Bars per trading day at this interval
        bars_per_day = int(TRADING_DAY_MINUTES * 60 / interval)

        # Multi-day mode
        multiday = st.toggle("Multi-day window", value=True,
                             help="Concatenate N consecutive days to enable cross-day lags")

        use_bar_stride = False
        if multiday:
            use_bar_stride = st.toggle(
                "Bar-stride mode",
                value=False,
                help="Slide window in bar-space instead of day-space. "
                     "Decouples the stride rhythm from the trading day structure.",
            )

        if multiday and use_bar_stride:
            window_days = 1  # not used directly
            window_stride = 1  # not used directly
            _default_win = bars_per_day * 5
            window_bars_val = st.slider(
                "Window width (bars)", min_value=50,
                max_value=bars_per_day * 30, value=min(_default_win, bars_per_day * 30),
                help=f"{bars_per_day} bars = 1 trading day",
            )
            bar_stride_val = st.slider(
                "Bar stride", min_value=1, max_value=max(1, window_bars_val // 2),
                value=min(bars_per_day, window_bars_val // 2),
                help=f"Advance by N bars between windows. "
                     f"bars_per_day={bars_per_day}. "
                     f"Try prime numbers to avoid phase-locking to day structure.",
            )
            max_possible = window_bars_val - 10
            max_lag = st.slider("Max lag (bars)", min_value=5,
                                max_value=min(max_possible, 5000), value=min(900, max_possible))
            n_columns = max(0, (bars_per_day * len(selected_dates) - window_bars_val) // bar_stride_val)
            st.caption(f"≈ {n_columns:,} ACF columns at stride {bar_stride_val}")
        elif multiday:
            window_days = st.slider("Window size (days)", min_value=2, max_value=70, value=5)
            window_stride = st.slider(
                "Window stride (days)", min_value=1, max_value=window_days, value=1,
                help=f"Advance by N days between windows. "
                     f"stride=1 → {window_days-1}/{window_days} day overlap. "
                     f"stride={window_days} → 0 overlap (independent columns).",
            )
            max_possible = bars_per_day * window_days - 10
            max_lag = st.slider("Max lag (bars)", min_value=5,
                                max_value=min(max_possible, 5000), value=min(900, max_possible))
        else:
            window_days = 1
            window_stride = 1
            max_possible = bars_per_day - 10
            max_lag = st.slider("Max lag (bars)", min_value=5,
                                max_value=max_possible, value=min(900, max_possible))
            st.caption(f"⚠️ Single-day mode: max = {max_possible} bars ({bars_per_day} bars/day)")

        _lag_min = max_lag * interval / 60.0
        _lag_days = _lag_min / TRADING_DAY_MINUTES
        st.caption(f"= {lag_to_label(max_lag, interval)}  ({_lag_days:.1f} trading days)")

        st.divider()

        col_v1, col_v2 = st.columns(2)
        with col_v1:
            vmin = st.number_input("Color min", value=-0.25, step=0.05, format="%.2f")
        with col_v2:
            vmax = st.number_input("Color max", value=0.25, step=0.05, format="%.2f")

        st.divider()
        st.subheader("🧹 Cleanup Modes")
        gap_barrier = st.toggle(
            "NaN gap barrier",
            value=False,
            help="Insert NaN at day boundaries to prevent overnight gap "
                 "from contaminating cross-day ACF lags",
        )
        do_deinterlace = st.toggle(
            "Deinterlace",
            value=False,
            help="Fourier notch filter: removes day-boundary harmonics from the "
                 "lag axis. This is what creates the structured 'imagery' — "
                 "periodic modulation at 1/bars_per_day and overtones.",
        )
        if do_deinterlace:
            n_harmonics = st.slider(
                "Harmonics to notch", min_value=1, max_value=30, value=4,
                help="Number of overtones of the day-boundary frequency to remove",
            )
            notch_w = st.slider(
                "Notch width (bins)", min_value=0.5, max_value=20.0, value=1.5, step=0.5,
                help="Width of each frequency notch. Wider = more aggressive.",
            )
        else:
            n_harmonics = 4
            notch_w = 1.5
        do_deseason = st.toggle(
            "Deseasonalize",
            value=False,
            help="Subtract mean ACF profile across dates to remove "
                 "shared horizontal banding (isolates date-specific deviations)",
        )
        show_gap_acf = st.toggle(
            "Overnight gap channel",
            value=False,
            help="Show close→open gap return ACF as a separate trace",
        )
        show_expiry_acf = st.toggle(
            "📊 Expiration ACF",
            value=False,
            help="Show per-expiration ACF spectrograms computed from options "
                 "volume for individual expiry dates.",
        )
        if show_expiry_acf:
            with st.spinner("Scanning expirations…"):
                avail_expiries = _scan_available_expirations(
                    symbol, selected_dates,
                )
            if avail_expiries:
                selected_expiries = st.multiselect(
                    "Expirations",
                    options=avail_expiries,
                    default=avail_expiries[:3],
                    help="Select specific option expiration dates to show as separate ACF spectrograms.",
                )
            else:
                st.warning("No options expirations found in date range.")
                selected_expiries = []

        st.divider()
        st.subheader("📸 Export")
        auto_export = st.toggle(
            "Auto-export images",
            value=False,
            help="Automatically save all charts as high-res PNGs on each run",
        )
        if auto_export:
            export_dir = st.text_input(
                "Export directory",
                value=str(Path(__file__).parent / "exports"),
                help="Absolute path to save exported images",
            )
            export_scale = st.slider(
                "Export scale", min_value=1, max_value=4, value=2,
                help="Image scale multiplier (2x = 2400×1800 for a 1200×900 chart)",
            )
        else:
            export_dir = ""
            export_scale = 2

    # Compute
    if multiday and use_bar_stride:
        valid_dates, acf_matrix = compute_bar_stride_acf(
            symbol, selected_dates, interval, max_lag,
            window_bars=window_bars_val,
            bar_stride=bar_stride_val,
            gap_barrier=gap_barrier,
        )
    elif multiday:
        if gap_barrier:
            valid_dates, acf_matrix = compute_rolling_multiday_acf_gapped(
                symbol, selected_dates, interval, max_lag, window_days,
                stride=window_stride,
            )
        else:
            valid_dates, acf_matrix = compute_rolling_multiday_acf(
                symbol, selected_dates, interval, max_lag, window_days,
                stride=window_stride,
            )
    else:
        valid_dates, acf_matrix = compute_rolling_acf(
            symbol, selected_dates, interval, max_lag
        )

    if len(valid_dates) == 0:
        if multiday:
            st.warning(
                f"No valid windows found. Need ≥{window_days} consecutive days with data "
                f"and ≥{max_lag + 10} total bars per window."
            )
        else:
            st.warning(
                f"No valid trading days found. Max lag ({max_lag}) may exceed "
                f"available bars per day (~{bars_per_day})."
            )
        return

    # Compute stats
    raw_acf_matrix = acf_matrix.copy()
    interlace_field = None

    if do_deinterlace and multiday:
        bpd = TRADING_DAY_MINUTES * 60 / interval
        acf_matrix, interlace_field = deinterlace_acf(
            acf_matrix, bpd, n_harmonics=n_harmonics, notch_width=notch_w
        )
    if do_deseason:
        acf_matrix = deseasonalize_acf(acf_matrix)
    stats = compute_regime_stats(valid_dates, acf_matrix)

    # Metric cards
    col_a, col_b, col_c, col_d, col_e = st.columns(5)
    unit = f"Windows ({window_days}d)" if multiday else "Trading Days"
    with col_a:
        st.metric(unit, stats["n_days"])
    with col_b:
        regime_color = "🔵" if stats["regime"] == "LONG GAMMA DEFAULT" else "🔴"
        st.metric("Regime", f"{regime_color} {stats['regime']}")
    with col_c:
        st.metric("Dampened Days", f"{stats['n_dampened']} ({stats['pct_dampened']:.0f}%)")
    with col_d:
        st.metric("Amplified Days", f"{stats['n_amplified']} ({stats['pct_amplified']:.0f}%)")
    with col_e:
        st.metric("Mean Lag-1 ACF", f"{stats['mean_lag1']:.4f}")

    # Render
    mode_label = []
    if gap_barrier:
        mode_label.append("gapped")
    if do_deinterlace:
        mode_label.append("deinterlaced")
    if do_deseason:
        mode_label.append("deseasonalized")
    mode_suffix = f" [{', '.join(mode_label)}]" if mode_label else ""

    # Load daily closes for price panel
    daily_closes = get_daily_closes(symbol, valid_dates)

    fig = render_spectrogram(
        valid_dates, acf_matrix, f"{symbol}{mode_suffix}", interval, vmin, vmax,
        prices=daily_closes,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Auto-export: main spectrogram
    if auto_export and export_dir:
        _export_path = Path(export_dir)
        _export_path.mkdir(parents=True, exist_ok=True)
        _ts = int(_time.time())
        _fname = f"{symbol}_{int(interval)}s_spectrogram_{_ts}.png"
        _fpath = _export_path / _fname
        try:
            fig.write_image(str(_fpath), scale=export_scale,
                           width=1600, height=900)
            st.toast(f"📸 Exported: {_fname}", icon="✅")
        except Exception as e:
            st.warning(f"Export failed: {e}. Install kaleido: `pip install -U kaleido`")

    # Interlace diagnostics expander
    if do_deinterlace and interlace_field is not None and multiday:
        with st.expander("📡 Interlace Diagnostics — What Creates the Imagery", expanded=True):
            bpd = TRADING_DAY_MINUTES * 60 / interval
            diag = compute_interlace_diagnostics(raw_acf_matrix, bpd, n_harmonics=n_harmonics)

            dcol1, dcol2, dcol3, dcol4 = st.columns(4)
            with dcol1:
                st.metric("Harmonic Power", f"{diag['harmonic_power_pct']}%",
                          help="% of total spectral power at day-boundary harmonics")
            with dcol2:
                st.metric("Bars/Day", f"{bpd:.1f}")
            with dcol3:
                st.metric("Dominant Period", f"{diag['dominant_period_lags']:.1f} lags")
            with dcol4:
                st.metric("Harmonics Checked", diag["n_harmonics_checked"])

            # Per-harmonic breakdown
            if diag["per_harmonic"]:
                harm_df = pd.DataFrame([
                    {"Harmonic k": k, "Frequency": f"{k/bpd:.4f}", "Period (lags)": f"{bpd/k:.1f}",
                     "Power %": f"{v:.1f}%"}
                    for k, v in sorted(diag["per_harmonic"].items())
                ])
                st.dataframe(harm_df, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("Extracted Interlace Field (the 'imagery')")
            st.caption(
                "This is what the deinterlace filter removed — the periodic component "
                "at the day-boundary frequency and its harmonics. This is the carrier "
                "signal that creates the visual structure."
            )

            # Render the extracted field as its own heatmap
            max_lag_f = interlace_field.shape[1]
            lag_labels_f = [lag_to_label(i + 1, interval) for i in range(max_lag_f)]
            field_colorscale = [
                [0.0, "#1a237e"], [0.25, "#42a5f5"],
                [0.5, "#ffffff"],
                [0.75, "#ef5350"], [1.0, "#b71c1c"],
            ]
            fig_field = go.Figure(go.Heatmap(
                z=interlace_field.T,
                x=valid_dates,
                y=lag_labels_f,
                colorscale=field_colorscale,
                zmin=vmin * 0.5,
                zmax=vmax * 0.5,
                colorbar=dict(title=dict(text="Periodic ACF", side="right")),
            ))
            fig_field.update_layout(
                height=400,
                template="plotly_dark",
                paper_bgcolor="#0e1117",
                plot_bgcolor="#0e1117",
                font=dict(family="JetBrains Mono, monospace", size=11),
                title="Day-Boundary Harmonic Field (removed component)",
                margin=dict(t=50, b=40, l=60, r=40),
            )
            fig_field.update_xaxes(showgrid=False)
            fig_field.update_yaxes(showgrid=False)
            st.plotly_chart(fig_field, use_container_width=True)

            # Auto-export: interlace field
            if auto_export and export_dir:
                _fname2 = f"{symbol}_{int(interval)}s_interlace_field_{int(_time.time())}.png"
                _fpath2 = Path(export_dir) / _fname2
                try:
                    fig_field.write_image(str(_fpath2), scale=export_scale,
                                         width=1600, height=400)
                    st.toast(f"📸 Exported: {_fname2}", icon="✅")
                except Exception:
                    pass


    if show_gap_acf:
        with st.expander("🌙 Overnight Gap Return ACF", expanded=True):
            st.caption(
                "ACF of close→open gap returns. Each 'bar' is one overnight gap. "
                "Positive = gaps auto-correlate (momentum); Negative = gaps mean-revert."
            )
            gap_dates, gap_acf = compute_overnight_gap_acf(
                symbol, selected_dates, max_lag=min(max_lag, 50)
            )
            if len(gap_dates) > 0:
                gap_lag_labels = [f"Gap Lag {i+1}" for i in range(len(gap_acf))]
                fig_gap = go.Figure()
                gap_colors = ["#c62828" if v > 0 else "#1565c0" for v in gap_acf]
                fig_gap.add_trace(go.Bar(
                    x=gap_lag_labels,
                    y=gap_acf,
                    marker_color=gap_colors,
                    hovertemplate="%{x}<br>ACF: %{y:.4f}<extra></extra>",
                ))
                fig_gap.add_hline(y=0, line_dash="dot", line_color="gray")
                # Add ±2/sqrt(N) significance bands
                n_gaps = len(gap_dates)
                sig_bound = 2.0 / np.sqrt(n_gaps)
                fig_gap.add_hline(
                    y=sig_bound, line_dash="dash", line_color="#555",
                    annotation_text=f"95% CI (±{sig_bound:.3f})",
                    annotation_position="top right",
                )
                fig_gap.add_hline(
                    y=-sig_bound, line_dash="dash", line_color="#555",
                )
                fig_gap.update_layout(
                    height=350,
                    template="plotly_dark",
                    paper_bgcolor="#0e1117",
                    plot_bgcolor="#0e1117",
                    font=dict(family="JetBrains Mono, monospace", size=11),
                    yaxis_title="ACF",
                    xaxis_title="Lag (trading days)",
                    title=f"Overnight Gap ACF — {symbol} ({n_gaps} gaps)",
                    margin=dict(t=50, b=40, l=60, r=40),
                    showlegend=False,
                )
                st.plotly_chart(fig_gap, use_container_width=True)

                # Auto-export: overnight gap ACF
                if auto_export and export_dir:
                    _fname3 = f"{symbol}_{int(interval)}s_overnight_gap_acf_{int(_time.time())}.png"
                    _fpath3 = Path(export_dir) / _fname3
                    try:
                        fig_gap.write_image(str(_fpath3), scale=export_scale,
                                           width=1200, height=350)
                        st.toast(f"📸 Exported: {_fname3}", icon="✅")
                    except Exception:
                        pass

                # Summary info
                sig_lags = np.where(np.abs(gap_acf) > sig_bound)[0]
                if len(sig_lags) > 0:
                    sig_str = ", ".join([f"Lag {l+1} ({gap_acf[l]:.3f})" for l in sig_lags[:10]])
                    st.info(f"📌 Significant lags: {sig_str}")
                else:
                    st.success("No significant gap autocorrelations detected (consistent with EMH).")
            else:
                st.warning("Not enough overnight gaps to compute ACF.")

    # Detailed stats
    with st.expander("📊 Detailed Statistics"):
        stat_cols = st.columns(4)
        with stat_cols[0]:
            st.metric("Median Lag-1", f"{stats['median_lag1']:.4f}")
        with stat_cols[1]:
            st.metric("Std Dev", f"{stats['std_lag1']:.4f}")
        with stat_cols[2]:
            st.metric("Min Lag-1", f"{stats['min_lag1']:.4f}")
        with stat_cols[3]:
            st.metric("Max Lag-1", f"{stats['max_lag1']:.4f}")

        # Rolling mean overlay
        st.subheader("Rolling 20-day Mean ACF (Lag-1)")
        lag1 = acf_matrix[:, 0]
        rolling_mean = pd.Series(lag1).rolling(20, min_periods=5).mean().values

        fig_rolling = go.Figure()
        fig_rolling.add_trace(go.Scatter(
            x=valid_dates,
            y=rolling_mean,
            mode="lines",
            line=dict(color="#64b5f6", width=2),
            name="Rolling 20d Mean",
        ))
        fig_rolling.add_hline(y=0, line_dash="dot", line_color="gray")
        fig_rolling.add_hrect(y0=-0.25, y1=0, fillcolor="#1565c0", opacity=0.1, line_width=0)
        fig_rolling.add_hrect(y0=0, y1=0.25, fillcolor="#c62828", opacity=0.1, line_width=0)
        fig_rolling.update_layout(
            height=300,
            template="plotly_dark",
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
            font=dict(family="JetBrains Mono, monospace", size=11),
            yaxis_title="ACF₁",
            margin=dict(t=20, b=40, l=60, r=40),
        )
        st.plotly_chart(fig_rolling, use_container_width=True)

    # Phase transition detection
    with st.expander("🔄 Phase Transition Detection"):
        st.caption(
            "Identifies dates where the regime flips from Long Gamma (dampening) "
            "to Short Gamma (amplification) or vice versa."
        )
        lag1 = acf_matrix[:, 0]
        transitions = []
        for i in range(1, len(lag1)):
            if lag1[i - 1] < 0 and lag1[i] > 0:
                transitions.append({
                    "Date": valid_dates[i],
                    "Direction": "🔴 → Short Gamma",
                    "ACF Before": f"{lag1[i-1]:.4f}",
                    "ACF After": f"{lag1[i]:.4f}",
                    "Δ ACF": f"{lag1[i] - lag1[i-1]:.4f}",
                })
            elif lag1[i - 1] > 0 and lag1[i] < 0:
                transitions.append({
                    "Date": valid_dates[i],
                    "Direction": "🔵 → Long Gamma",
                    "ACF Before": f"{lag1[i-1]:.4f}",
                    "ACF After": f"{lag1[i]:.4f}",
                    "Δ ACF": f"{lag1[i] - lag1[i-1]:.4f}",
                })

        if transitions:
            st.dataframe(
                pd.DataFrame(transitions),
                use_container_width=True,
                hide_index=True,
            )
            st.caption(f"Total transitions: {len(transitions)} across {len(valid_dates)} days")
        else:
            st.info("No regime transitions detected in this window.")

    # Per-expiration ACF spectrograms
    if show_expiry_acf and selected_expiries:
        with st.expander(f"📊 Expiration ACF Spectrograms — {len(selected_expiries)} expirations", expanded=True):
            # Expiration ACF always uses multi-day windows
            exp_window = max(window_days, 5)  # min 5 days
            exp_stride = max(1, window_stride)
            # Cap max_lag so concatenated bars (bars_per_day * window) are sufficient
            bars_in_window = bars_per_day * exp_window
            exp_max_lag = min(max_lag, bars_in_window - 10)
            if exp_max_lag < 5:
                st.warning(f"Window too small for ACF. Need at least 15 bars per window.")
            else:
                y_labels = [lag_to_label(lag + 1, interval) for lag in range(exp_max_lag)]
                st.caption(
                    f"Using {exp_window}-day window, stride {exp_stride}, "
                    f"max_lag capped to {exp_max_lag}"
                )

                exp_results: dict[str, tuple[list[str], np.ndarray]] = {}
                progress = st.progress(0, text="Computing per-expiration ACF…")
                for idx, exp_date in enumerate(selected_expiries):
                    progress.progress(
                        (idx + 1) / len(selected_expiries),
                        text=f"Computing ACF for expiry {exp_date}…"
                    )
                    exp_dates, exp_acf = compute_expiration_volume_acf(
                        symbol, selected_dates, interval, exp_max_lag,
                        exp_window, exp_stride, exp_date,
                    )
                    if len(exp_dates) > 0:
                        if do_deinterlace:
                            bpd = TRADING_DAY_MINUTES * 60 / interval
                            exp_acf, _ = deinterlace_acf(
                                exp_acf, bpd, n_harmonics=n_harmonics,
                                notch_width=notch_w
                            )
                        if do_deseason:
                            exp_acf = deseasonalize_acf(exp_acf)
                        exp_results[exp_date] = (exp_dates, exp_acf)
                progress.empty()

                if not exp_results:
                    st.warning("No options data found for selected expirations in this date range.")
                else:
                    n_plots = len(exp_results)
                    fig_exp = make_subplots(
                        rows=n_plots, cols=1,
                        shared_xaxes=True,
                        vertical_spacing=0.03,
                        subplot_titles=[f"Expiry: {e}" for e in exp_results.keys()],
                    )

                    for plot_idx, (exp_name, (exp_dates, exp_acf)) in enumerate(
                        exp_results.items(), 1
                    ):
                        fig_exp.add_trace(
                            go.Heatmap(
                                z=exp_acf.T,
                                x=exp_dates,
                                y=y_labels,
                                colorscale="RdBu_r",
                                zmin=vmin, zmax=vmax,
                                showscale=(plot_idx == 1),
                                colorbar=dict(title="ACF") if plot_idx == 1 else None,
                                hovertemplate=(
                                    "Date: %{x}<br>"
                                    "Lag: %{y}<br>"
                                    "ACF: %{z:.4f}<br>"
                                    "<extra></extra>"
                                ),
                            ),
                            row=plot_idx, col=1,
                        )

                    mode_str = ""
                    if do_deinterlace:
                        mode_str += " [deinterlaced]"
                    if do_deseason:
                        mode_str += " [deseasonalized]"

                    fig_exp.update_layout(
                        title=f"Options Volume ACF per Expiration — {symbol}{mode_str}",
                        height=250 * n_plots,
                        template="plotly_dark",
                        paper_bgcolor="#0e1117",
                        plot_bgcolor="#0e1117",
                        font=dict(family="JetBrains Mono, monospace", size=11),
                        margin=dict(t=60, b=40, l=80, r=40),
                    )
                    for i in range(1, n_plots + 1):
                        fig_exp.update_yaxes(showgrid=False, row=i, col=1)
                        fig_exp.update_xaxes(showgrid=False, row=i, col=1)

                    st.plotly_chart(fig_exp, use_container_width=True)

                    for exp_name, (exp_dates, exp_acf) in exp_results.items():
                        lag1_mean = float(np.nanmean(exp_acf[:, 0]))
                        st.caption(
                            f"**{exp_name}**: {len(exp_dates)} windows, "
                            f"mean ACF₁ = {lag1_mean:.4f}"
                        )


if __name__ == "__main__":
    main()
