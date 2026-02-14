#!/usr/bin/env python3
"""
Phase 3A+3D: Intraday ACF Profile + Multi-Timescale ACF
========================================================
Two empirical measurements in one engine:

3A — Intraday ACF Profile:
  Stratify ACF by time-of-day (13 half-hour windows).
  Test the 0DTE Absorbent Layer hypothesis: does dampening spike near close?

3D — Squeeze Eigenvalue (Multi-Timescale ACF):
  Compute ACF lag-1 at multiple bar widths (30s, 60s, 120s, 300s, 600s).
  If the +0.11 squeeze signature holds across scales → it's a fundamental constant.

Usage:
  # CLI mode — full panel scan
  python phase3_acf_engines.py --mode intraday --tickers GME DJT SNAP TSLA AAPL
  python phase3_acf_engines.py --mode multiscale --tickers GME AMC
  python phase3_acf_engines.py --mode both --tickers GME

  # Streamlit mode
  streamlit run phase3_acf_engines.py
"""
import sys
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# Check if running under Streamlit
try:
    import streamlit as st
    STREAMLIT_MODE = True
except ImportError:
    STREAMLIT_MODE = False

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# Data infrastructure
ENGINE_DIR = Path(__file__).parent.parent / "phase98_cluster_bridge"
sys.path.insert(0, str(ENGINE_DIR))
from temporal_convolution_engine import load_equity_day

POLYGON_DIR = (
    Path(__file__).parent.parent.parent / "data" / "raw" / "polygon" / "trades"
)
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ============================================================================
# Data helpers
# ============================================================================

def get_available_equity_dates(symbol: str) -> list[str]:
    """List locally cached equity trading days."""
    for prefix in [f"symbol={symbol}", f"symbol={symbol.upper()}"]:
        path = POLYGON_DIR / prefix
        if path.exists():
            return sorted(d.name.split("=")[1] for d in path.glob("date=*"))
    return []


# ============================================================================
# 3A: Intraday ACF Profile
# ============================================================================

# 13 half-hour windows across the trading day
INTRADAY_WINDOWS = [
    ("09:30", "10:00"), ("10:00", "10:30"), ("10:30", "11:00"),
    ("11:00", "11:30"), ("11:30", "12:00"), ("12:00", "12:30"),
    ("12:30", "13:00"), ("13:00", "13:30"), ("13:30", "14:00"),
    ("14:00", "14:30"), ("14:30", "15:00"), ("15:00", "15:30"),
    ("15:30", "16:00"),
]
WINDOW_LABELS = [f"{s}–{e}" for s, e in INTRADAY_WINDOWS]

# Pre-compute window boundaries as seconds-from-midnight for fast filtering
def _hhmm_to_seconds(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return h * 3600 + m * 60

WINDOW_BOUNDS = [(_hhmm_to_seconds(s), _hhmm_to_seconds(e)) for s, e in INTRADAY_WINDOWS]
# EST/EDT offset from UTC (we'll detect per-date)
EST_OFFSET = -5 * 3600
EDT_OFFSET = -4 * 3600


def compute_window_acf(returns: np.ndarray) -> float:
    """Compute ACF lag-1 from pre-computed returns."""
    if len(returns) < 5:
        return np.nan
    n = len(returns)
    mean = returns.mean()
    var = np.var(returns)
    if var < 1e-12:
        return np.nan
    acf1 = np.mean((returns[:-1] - mean) * (returns[1:] - mean)) / var
    return float(acf1)


def compute_intraday_profile(
    symbol: str,
    dates: list[str],
    interval_sec: float = 60.0,
) -> dict:
    """
    Compute ACF lag-1 for each 30-min window across all days.
    Uses fast epoch-based filtering (no strftime).
    """
    window_acfs = {label: [] for label in WINDOW_LABELS}

    for date_str in dates:
        eq = load_equity_day(symbol, date_str)
        if eq.empty or len(eq) < 100:
            continue

        ts = eq["ts"]
        # Convert to epoch seconds for fast math
        if hasattr(ts.iloc[0], 'timestamp'):
            epoch_s = ts.values.astype('int64') // 10**9
        else:
            epoch_s = ts.astype('int64') // 10**9

        # Detect EST vs EDT from the date (Apr-Nov = EDT)
        month = int(date_str[4:6]) if len(date_str) == 8 else int(date_str.split("-")[1])
        offset = EDT_OFFSET if 3 <= month <= 11 else EST_OFFSET

        # Seconds-of-day in Eastern time
        sod = (epoch_s + offset) % 86400

        for (win_start, win_end), label in zip(WINDOW_BOUNDS, WINDOW_LABELS):
            mask = (sod >= win_start) & (sod < win_end)
            window_data = eq[mask]
            if len(window_data) < 20:
                continue

            # Resample to bars within this window
            df = pd.DataFrame(
                {"ts": window_data["ts"], "price": window_data["price"]}
            ).set_index("ts")
            bars = df.resample(f"{int(interval_sec)}s").last().dropna()
            returns = bars["price"].pct_change().dropna().values

            acf1 = compute_window_acf(returns)
            if not np.isnan(acf1):
                window_acfs[label].append(acf1)

    # Compute stats per window
    results = {}
    for label in WINDOW_LABELS:
        vals = window_acfs[label]
        if vals:
            arr = np.array(vals)
            results[label] = {
                "mean_acf1": round(float(np.mean(arr)), 4),
                "median_acf1": round(float(np.median(arr)), 4),
                "std_acf1": round(float(np.std(arr)), 4),
                "n_days": len(vals),
                "pct_dampened": round(float(np.sum(arr < 0) / len(arr) * 100), 1),
            }
        else:
            results[label] = {
                "mean_acf1": np.nan,
                "median_acf1": np.nan,
                "std_acf1": np.nan,
                "n_days": 0,
                "pct_dampened": 0,
            }

    return results


# ============================================================================
# 3D: Multi-Timescale ACF (Squeeze Eigenvalue)
# ============================================================================

TIMESCALES = [30, 60, 120, 300, 600]  # seconds


def compute_multiscale_acf(
    symbol: str,
    dates: list[str],
    max_lag: int = 10,
) -> dict:
    """
    Compute ACF at multiple bar widths across all days.
    Returns dict keyed by timescale with per-day ACF arrays.
    """
    results = {ts: {"lag1_values": [], "full_acf_mean": None} for ts in TIMESCALES}

    for date_str in dates:
        eq = load_equity_day(symbol, date_str)
        if eq.empty or len(eq) < 100:
            continue

        for interval_sec in TIMESCALES:
            df = pd.DataFrame({"ts": eq["ts"], "price": eq["price"]}).set_index("ts")
            bars = df.resample(f"{int(interval_sec)}s").last().dropna()
            returns = bars["price"].pct_change().dropna().values

            if len(returns) < max_lag + 5:
                continue

            n = len(returns)
            mean = returns.mean()
            var = np.var(returns)
            if var < 1e-12:
                continue

            acf = np.zeros(max_lag)
            for lag in range(1, max_lag + 1):
                acf[lag - 1] = (
                    np.mean((returns[: n - lag] - mean) * (returns[lag:] - mean)) / var
                )
            results[interval_sec]["lag1_values"].append(acf[0])

    # Compute summary stats per timescale
    summary = {}
    for ts in TIMESCALES:
        vals = results[ts]["lag1_values"]
        if vals:
            arr = np.array(vals)
            summary[ts] = {
                "mean_lag1": round(float(np.mean(arr)), 4),
                "median_lag1": round(float(np.median(arr)), 4),
                "std_lag1": round(float(np.std(arr)), 4),
                "n_days": len(vals),
                "pct_dampened": round(float(np.sum(arr < 0) / len(arr) * 100), 1),
            }
        else:
            summary[ts] = {
                "mean_lag1": np.nan,
                "median_lag1": np.nan,
                "std_lag1": np.nan,
                "n_days": 0,
                "pct_dampened": 0,
            }

    return summary


# ============================================================================
# CLI Mode
# ============================================================================

def run_cli():
    parser = argparse.ArgumentParser(description="Phase 3A+3D ACF Engines")
    parser.add_argument("--mode", choices=["intraday", "multiscale", "both"], default="both")
    parser.add_argument("--tickers", nargs="*", default=["GME"])
    parser.add_argument("--max-days", type=int, default=200)
    parser.add_argument("--interval", type=float, default=60.0)
    args = parser.parse_args()

    tickers = [t.upper() for t in args.tickers]

    for symbol in tickers:
        dates = get_available_equity_dates(symbol)[:args.max_days]
        if not dates:
            print(f"  {symbol}: NO DATA")
            continue

        if args.mode in ("intraday", "both"):
            print(f"\n{'='*70}")
            print(f"  3A: INTRADAY ACF PROFILE — {symbol} ({len(dates)} days)")
            print(f"{'='*70}")

            profile = compute_intraday_profile(symbol, dates, args.interval)
            print(f"  {'Window':<14s}  {'Mean ACF₁':>10s}  {'Damp%':>6s}  {'N days':>6s}")
            print(f"  {'─'*14}  {'─'*10}  {'─'*6}  {'─'*6}")
            for label in WINDOW_LABELS:
                p = profile[label]
                print(f"  {label:<14s}  {p['mean_acf1']:+10.4f}  {p['pct_dampened']:6.1f}  {p['n_days']:6d}")

            # Save
            out_path = RESULTS_DIR / f"intraday_acf_{symbol}.json"
            with open(out_path, "w") as f:
                json.dump(profile, f, indent=2, default=str)
            print(f"\n  Saved to {out_path}")

        if args.mode in ("multiscale", "both"):
            print(f"\n{'='*70}")
            print(f"  3D: MULTI-TIMESCALE ACF — {symbol} ({len(dates)} days)")
            print(f"{'='*70}")

            ms_results = compute_multiscale_acf(symbol, dates)
            print(f"  {'Scale':>6s}  {'Mean ACF₁':>10s}  {'Damp%':>6s}  {'N days':>6s}")
            print(f"  {'─'*6}  {'─'*10}  {'─'*6}  {'─'*6}")
            for ts in TIMESCALES:
                r = ms_results[ts]
                print(f"  {ts:5d}s  {r['mean_lag1']:+10.4f}  {r['pct_dampened']:6.1f}  {r['n_days']:6d}")

            # Save
            out_path = RESULTS_DIR / f"multiscale_acf_{symbol}.json"
            with open(out_path, "w") as f:
                json.dump({str(k): v for k, v in ms_results.items()}, f, indent=2, default=str)
            print(f"\n  Saved to {out_path}")


# ============================================================================
# Streamlit Mode
# ============================================================================

def run_streamlit():
    st.set_page_config(page_title="Phase 3: ACF Engines", page_icon="🔬", layout="wide")

    st.title("🔬 Phase 3: ACF Engines")
    st.caption("Intraday ACF Profile (3A) + Multi-Timescale ACF (3D)")

    available = sorted(d.name.split("=")[1] for d in POLYGON_DIR.glob("symbol=*") if d.is_dir())

    with st.sidebar:
        st.header("⚙️ Controls")
        symbols = st.multiselect("Tickers", available, default=["GME", "DJT", "TSLA", "AAPL"])
        max_days = st.slider("Max days per ticker", 20, 500, 200)
        interval = st.select_slider("Bar interval (seconds)", options=[30, 60, 120], value=60)

    if not symbols:
        st.warning("Select at least one ticker")
        return

    # --- TAB 1: Intraday ACF Profile ---
    tab1, tab2 = st.tabs(["📊 3A: Intraday Profile", "🔬 3D: Multi-Timescale"])

    with tab1:
        st.subheader("Intraday ACF Profile — Does dampening vary by session?")
        st.caption(
            "If 0DTEs cause dampening, negative ACF should **spike near close** (3:30–4:00 PM) "
            "as 0DTE gamma explodes approaching expiry."
        )

        all_profiles = {}
        for sym in symbols:
            dates = get_available_equity_dates(sym)[:max_days]
            if dates:
                with st.spinner(f"Computing intraday profile for {sym}…"):
                    all_profiles[sym] = compute_intraday_profile(sym, dates, interval)

        if all_profiles and HAS_PLOTLY:
            fig = go.Figure()
            colors = ["#64b5f6", "#ef5350", "#fdd835", "#66bb6a", "#ab47bc",
                       "#ff7043", "#26c6da", "#8d6e63"]
            for i, (sym, profile) in enumerate(all_profiles.items()):
                means = [profile[w]["mean_acf1"] for w in WINDOW_LABELS]
                fig.add_trace(go.Scatter(
                    x=WINDOW_LABELS,
                    y=means,
                    mode="lines+markers",
                    name=sym,
                    line=dict(color=colors[i % len(colors)], width=2),
                    marker=dict(size=6),
                ))

            fig.add_hline(y=0, line_dash="dot", line_color="gray")
            fig.add_vrect(x0="15:00–15:30", x1="15:30–16:00",
                          fillcolor="#c62828", opacity=0.08, line_width=0,
                          annotation_text="0DTE Zone", annotation_position="top left")

            fig.update_layout(
                height=500,
                template="plotly_dark",
                paper_bgcolor="#0e1117",
                plot_bgcolor="#0e1117",
                font=dict(family="JetBrains Mono, monospace", size=11),
                yaxis_title="Mean ACF Lag-1",
                xaxis_title="Time of Day",
                xaxis_tickangle=45,
                margin=dict(t=40, b=80),
            )
            st.plotly_chart(fig, use_container_width=True)

            # Table
            for sym, profile in all_profiles.items():
                with st.expander(f"📋 {sym} — Detail"):
                    df = pd.DataFrame(profile).T
                    df.index.name = "Window"
                    st.dataframe(df, use_container_width=True)

    # --- TAB 2: Multi-Timescale ACF ---
    with tab2:
        st.subheader("Multi-Timescale ACF — Is the squeeze signature scale-invariant?")
        st.caption(
            "If the +0.11 squeeze signature holds across bar widths (30s → 10min) → "
            "it's a fundamental constant. If scale-dependent → it's a measurement artifact."
        )

        all_ms = {}
        for sym in symbols:
            dates = get_available_equity_dates(sym)[:max_days]
            if dates:
                with st.spinner(f"Computing multi-timescale ACF for {sym}…"):
                    all_ms[sym] = compute_multiscale_acf(sym, dates)

        if all_ms and HAS_PLOTLY:
            fig = go.Figure()
            scale_labels = [f"{ts}s" for ts in TIMESCALES]

            colors = ["#64b5f6", "#ef5350", "#fdd835", "#66bb6a", "#ab47bc",
                       "#ff7043", "#26c6da", "#8d6e63"]
            for i, (sym, ms_result) in enumerate(all_ms.items()):
                means = [ms_result[ts]["mean_lag1"] for ts in TIMESCALES]
                fig.add_trace(go.Scatter(
                    x=scale_labels,
                    y=means,
                    mode="lines+markers",
                    name=sym,
                    line=dict(color=colors[i % len(colors)], width=2),
                    marker=dict(size=8),
                ))

            fig.add_hline(y=0, line_dash="dot", line_color="gray")
            fig.update_layout(
                height=500,
                template="plotly_dark",
                paper_bgcolor="#0e1117",
                plot_bgcolor="#0e1117",
                font=dict(family="JetBrains Mono, monospace", size=11),
                yaxis_title="Mean ACF Lag-1",
                xaxis_title="Bar Width",
                margin=dict(t=40, b=60),
            )
            st.plotly_chart(fig, use_container_width=True)

            # Summary table
            rows = []
            for sym, ms_result in all_ms.items():
                for ts in TIMESCALES:
                    r = ms_result[ts]
                    rows.append({
                        "Ticker": sym,
                        "Scale": f"{ts}s",
                        "Mean ACF₁": r["mean_lag1"],
                        "Dampened%": r["pct_dampened"],
                        "N Days": r["n_days"],
                    })
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)


# ============================================================================
# Entry
# ============================================================================

if __name__ == "__main__":
    if STREAMLIT_MODE and len(sys.argv) <= 1:
        # Streamlit auto-detection (no CLI args)
        run_streamlit()
    elif STREAMLIT_MODE and "--mode" not in sys.argv:
        run_streamlit()
    else:
        run_cli()
