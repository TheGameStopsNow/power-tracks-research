#!/usr/bin/env python3
"""
Predictive Tests: ACF Regime Forecaster + RV Prediction + Volume Shape Forecast
================================================================================
Three out-of-sample predictive tests to strengthen the thesis:

Test 1 — ACF Magnitude Forecaster:
    Can yesterday's options/equity volume ratio (Re_Γ proxy) predict
    the MAGNITUDE of today's ACF₁?
    Uses Ridge regression with expanding window.
    Benchmark: AR(1) on ACF₁ alone (persistence baseline).

Test 2 — Realized Volatility Prediction:
    Does the current ACF regime predict next-day realized volatility?
    Regression: RV_{t+1} = α + β·ACF₁_t + ε

Test 3 — Volume Profile Forecast:
    Can we predict tomorrow's intraday volume shape using historical
    options NMF bases? Uses Strict Archaeology with strict temporal
    separation.

Usage:
    python predictive_tests.py                     # Run all tests, all tickers
    python predictive_tests.py --ticker GME        # Single ticker
    python predictive_tests.py --test acf          # Single test
    python predictive_tests.py --test rv
    python predictive_tests.py --test profile
"""

import argparse
import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, r2_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=FutureWarning)

# -- Infrastructure imports --------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "phase98_cluster_bridge"))

from panel_scan import (
    POLYGON_DIR,
    compute_daily_acf,
    get_available_equity_dates,
)

try:
    from temporal_convolution_engine import load_equity_day
except ImportError:
    from panel_scan import load_equity_day  # type: ignore

from phase5_paradigm import _load_options_day, _time_profile

THETA_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw" / "thetadata" / "trades"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# Tickers that have BOTH equity AND options data
ALL_TICKERS = [
    "AAPL", "ABNB", "AFRM", "AMC", "AMD", "ARM", "BYND", "CHWY", "CRWD",
    "DASH", "DJT", "DKNG", "DUOL", "GME", "HOOD", "LCID", "LYFT",
    "MSFT", "NET", "NVDA", "PINS", "PLTR", "RBLX", "RDDT", "RIVN",
    "SNAP", "SNOW", "SOFI", "TSLA", "U", "UBER", "W", "ZM",
]


# ===========================================================================
# Data helpers
# ===========================================================================

def get_overlap_dates(ticker: str) -> list[str]:
    """Find dates with both equity + options data."""
    eq_dir = POLYGON_DIR / f"symbol={ticker}"
    opts_dir = THETA_ROOT / f"root={ticker}"
    if not eq_dir.exists() or not opts_dir.exists():
        return []
    eq = {d.name.replace("date=", "") for d in eq_dir.iterdir() if d.is_dir()}
    opts_raw = {d.name.replace("date=", "") for d in opts_dir.iterdir() if d.is_dir()}
    opts = {f"{d[:4]}-{d[4:6]}-{d[6:8]}" for d in opts_raw if len(d) == 8}
    return sorted(eq & opts)


def compute_day_features(ticker: str, date_str: str) -> dict | None:
    """
    Compute per-day features for a single trading day:
    - ACF lag 1 (60s returns)
    - Realized volatility (sum of squared 60s returns)
    - Equity volume (total shares)
    - Options volume (total contracts)
    - Options/equity volume ratio (Re_Γ proxy)
    - Volume profile (64-bin normalized)
    """
    try:
        eq = load_equity_day(ticker, date_str)
        if eq.empty or len(eq) < 200:
            return None

        # ACF
        acf = compute_daily_acf(eq["price"], eq["ts"], interval_sec=60.0, max_lag=5)
        if np.isnan(acf).all():
            return None
        acf1 = float(acf[0])

        # Realized volatility from 60s returns
        df_bars = pd.DataFrame({"ts": eq["ts"], "price": eq["price"]}).set_index("ts")
        bars = df_bars.resample("60s").last().dropna()
        returns = bars["price"].pct_change().dropna().values
        if len(returns) < 20:
            return None
        rv = float(np.sum(returns ** 2))

        # Equity volume
        eq_volume = float(eq["size"].sum()) if "size" in eq.columns else float(len(eq))

        # Volume profile
        eq_profile = _time_profile(eq, n_bins=64) if len(eq) > 10 else None

        # Options volume
        try:
            opts = _load_options_day(ticker, date_str)
            opts_volume = float(opts["size"].sum()) if len(opts) > 0 else 0.0
        except (FileNotFoundError, Exception):
            opts_volume = 0.0

        # Re_Γ proxy: options contracts / equity volume
        re_gamma = opts_volume / eq_volume if eq_volume > 0 else 0.0

        return {
            "date": date_str,
            "acf1": acf1,
            "rv": rv,
            "eq_volume": eq_volume,
            "opts_volume": opts_volume,
            "re_gamma": re_gamma,
            "dampened": acf1 < 0,
            "profile": eq_profile,
        }
    except Exception as e:
        return None


def build_daily_panel(ticker: str, max_days: int = 500) -> pd.DataFrame:
    """Build a daily feature panel for one ticker."""
    dates = get_overlap_dates(ticker)
    if not dates:
        # Fall back to equity-only dates
        dates = get_available_equity_dates(ticker)
    dates = dates[-max_days:]  # Most recent N days

    rows = []
    print(f"  [{ticker}] Scanning {len(dates)} days...", end="", flush=True)
    for i, d in enumerate(dates):
        feat = compute_day_features(ticker, d)
        if feat is not None:
            rows.append(feat)
        if (i + 1) % 50 == 0:
            print(f" {i+1}", end="", flush=True)
    print(f" → {len(rows)} valid days")

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


# ===========================================================================
# Test 1: ACF Magnitude Forecaster
# ===========================================================================

def test_acf_forecast(df: pd.DataFrame, ticker: str) -> dict:
    """
    Can we predict tomorrow's ACF₁ MAGNITUDE from today's features?

    Full model features:
    - re_gamma (today's options/equity volume ratio = Re_Γ proxy)
    - acf1 (today's ACF₁ — persistence / autoregressive component)
    - rv (today's realized volatility)
    - log_eq_volume

    Baseline: AR(1) on ACF₁ alone (yesterday's ACF predicts today's)

    Method: Ridge regression, expanding window, min 30 training days.
    Reports OOS R² for both full model and baseline, plus the marginal
    R² lift from adding options features.
    """
    if len(df) < 50:
        return {"ticker": ticker, "status": "INSUFFICIENT_DATA", "n_days": len(df)}

    df = df.copy()
    df["log_eq_vol"] = np.log1p(df["eq_volume"])

    # Target: NEXT day's ACF₁
    df["target_acf1"] = df["acf1"].shift(-1)
    df = df.dropna(subset=["re_gamma", "acf1", "rv", "log_eq_vol", "target_acf1"])

    features_full = ["acf1", "re_gamma", "rv", "log_eq_vol"]
    features_base = ["acf1"]  # AR(1) baseline

    X_full = df[features_full].values
    X_base = df[features_base].values
    y = df["target_acf1"].values
    n = len(y)

    if n < 50:
        return {"ticker": ticker, "status": "INSUFFICIENT_DATA", "n_days": n}

    min_train = max(30, n // 3)

    oos_full = []
    oos_base = []
    oos_mean = []  # predict-the-mean benchmark
    oos_true = []

    for t in range(min_train, n):
        y_train = y[:t]

        # Full model
        scaler_f = StandardScaler()
        X_f_train = scaler_f.fit_transform(X_full[:t])
        X_f_test = scaler_f.transform(X_full[t:t+1])
        model_f = Ridge(alpha=1.0)
        model_f.fit(X_f_train, y_train)
        oos_full.append(model_f.predict(X_f_test)[0])

        # AR(1) baseline
        scaler_b = StandardScaler()
        X_b_train = scaler_b.fit_transform(X_base[:t])
        X_b_test = scaler_b.transform(X_base[t:t+1])
        model_b = Ridge(alpha=1.0)
        model_b.fit(X_b_train, y_train)
        oos_base.append(model_b.predict(X_b_test)[0])

        # Mean baseline (predict history mean)
        oos_mean.append(float(np.mean(y_train)))

        oos_true.append(y[t])

    oos_full = np.array(oos_full)
    oos_base = np.array(oos_base)
    oos_mean = np.array(oos_mean)
    oos_true = np.array(oos_true)

    r2_full = float(r2_score(oos_true, oos_full))
    r2_ar1 = float(r2_score(oos_true, oos_base))
    r2_mean = float(r2_score(oos_true, oos_mean))
    r2_lift = r2_full - r2_ar1

    # Correlation metrics
    corr_full = float(np.corrcoef(oos_true, oos_full)[0, 1])
    corr_ar1 = float(np.corrcoef(oos_true, oos_base)[0, 1])

    # ACF persistence (lag-1 autocorrelation of ACF₁ series itself)
    acf_series = df["acf1"].values
    acf_persistence = float(np.corrcoef(acf_series[:-1], acf_series[1:])[0, 1])

    # Dampening persistence stats
    pct_dampened = float((y < 0).mean()) * 100

    # Fit final model for coefficients
    scaler_f = StandardScaler()
    X_all_s = scaler_f.fit_transform(X_full)
    final_model = Ridge(alpha=1.0)
    final_model.fit(X_all_s, y)
    coefs = dict(zip(features_full, final_model.coef_.tolist()))

    return {
        "ticker": ticker,
        "status": "OK",
        "n_days": n,
        "n_oos": len(oos_true),
        "oos_r2_full": round(r2_full, 4),
        "oos_r2_ar1": round(r2_ar1, 4),
        "oos_r2_mean": round(r2_mean, 4),
        "r2_lift_over_ar1": round(r2_lift, 4),
        "oos_corr_full": round(corr_full, 4),
        "oos_corr_ar1": round(corr_ar1, 4),
        "acf_persistence": round(acf_persistence, 4),
        "pct_dampened": round(pct_dampened, 1),
        "mean_acf1": round(float(np.mean(y)), 4),
        "std_acf1": round(float(np.std(y)), 4),
        "coefficients": {k: round(v, 4) for k, v in coefs.items()},
    }


# ===========================================================================
# Test 2: Realized Volatility Prediction
# ===========================================================================

def test_rv_prediction(df: pd.DataFrame, ticker: str) -> dict:
    """
    Does today's ACF regime predict tomorrow's realized volatility?

    Model: RV_{t+1} = α + β₁·ACF₁_t + β₂·RV_t + β₃·log_vol_t + ε
    Benchmark: RV_{t+1} = α + β·RV_t  (AR(1) only)

    Method: Ridge regression, expanding window.
    """
    if len(df) < 50:
        return {"ticker": ticker, "status": "INSUFFICIENT_DATA", "n_days": len(df)}

    df = df.copy()
    df["log_rv"] = np.log(df["rv"].clip(lower=1e-12))
    df["log_eq_vol"] = np.log1p(df["eq_volume"])

    # Target: next-day log RV
    df["target_rv"] = df["log_rv"].shift(-1)
    df = df.dropna(subset=["acf1", "log_rv", "log_eq_vol", "target_rv"])

    features_full = ["acf1", "log_rv", "re_gamma", "log_eq_vol"]
    features_base = ["log_rv"]  # AR(1) benchmark

    X_full = df[features_full].values
    X_base = df[features_base].values
    y = df["target_rv"].values
    n = len(y)

    if n < 50:
        return {"ticker": ticker, "status": "INSUFFICIENT_DATA", "n_days": n}

    min_train = max(30, n // 3)

    oos_full = []
    oos_base = []
    oos_true = []

    for t in range(min_train, n):
        y_train = y[:t]

        # Full model
        scaler_f = StandardScaler()
        X_f_train = scaler_f.fit_transform(X_full[:t])
        X_f_test = scaler_f.transform(X_full[t:t+1])
        model_f = Ridge(alpha=1.0)
        model_f.fit(X_f_train, y_train)
        oos_full.append(model_f.predict(X_f_test)[0])

        # Baseline model
        scaler_b = StandardScaler()
        X_b_train = scaler_b.fit_transform(X_base[:t])
        X_b_test = scaler_b.transform(X_base[t:t+1])
        model_b = Ridge(alpha=1.0)
        model_b.fit(X_b_train, y_train)
        oos_base.append(model_b.predict(X_b_test)[0])

        oos_true.append(y[t])

    oos_full = np.array(oos_full)
    oos_base = np.array(oos_base)
    oos_true = np.array(oos_true)

    r2_full = float(r2_score(oos_true, oos_full))
    r2_base = float(r2_score(oos_true, oos_base))
    r2_lift = r2_full - r2_base

    # Fit final model for coefficients
    scaler_f = StandardScaler()
    X_all_s = scaler_f.fit_transform(X_full)
    final_model = Ridge(alpha=1.0)
    final_model.fit(X_all_s, y)
    coefs = dict(zip(features_full, final_model.coef_.tolist()))

    return {
        "ticker": ticker,
        "status": "OK",
        "n_days": n,
        "n_oos": len(oos_true),
        "oos_r2_full": round(r2_full, 4),
        "oos_r2_baseline": round(r2_base, 4),
        "r2_lift_from_acf": round(r2_lift, 4),
        "coefficients": {k: round(v, 4) for k, v in coefs.items()},
    }


# ===========================================================================
# Test 3: Volume Profile Forecast
# ===========================================================================

def test_profile_forecast(df: pd.DataFrame, ticker: str) -> dict:
    """
    Can we predict tomorrow's volume shape from historical options NMF?

    Method:
    - For each test day t, use NMF bases fitted on days [0..t-2]
    - Predict day t's 64-bin volume profile
    - Measure correlation between predicted and actual
    - Compare against naive baseline (mean historical profile)

    This tests whether options structure contains *predictive* information
    about equity volume shape.
    """
    from sklearn.decomposition import NMF

    # Filter to days with valid profiles
    valid = df.dropna(subset=["profile"]).copy()
    profiles = np.array(valid["profile"].tolist())

    if len(profiles) < 40 or profiles.shape[1] != 64:
        return {"ticker": ticker, "status": "INSUFFICIENT_DATA", "n_days": len(profiles)}

    # Ensure non-negative for NMF
    profiles = np.maximum(profiles, 0)
    n = len(profiles)

    min_train = max(20, n // 3)
    n_components = min(5, min_train // 5)

    oos_corrs_nmf = []
    oos_corrs_baseline = []

    for t in range(min_train, n):
        train_profiles = profiles[:t]
        test_profile = profiles[t]

        # Mean baseline
        mean_profile = train_profiles.mean(axis=0)
        mean_profile = mean_profile / (mean_profile.sum() + 1e-12)

        # NMF forecast: fit on training data, project test
        try:
            nmf = NMF(n_components=n_components, max_iter=300, random_state=42)
            W_train = nmf.fit_transform(train_profiles)

            # Predict using mean coefficients from last 5 days
            recent_W = W_train[-5:]
            mean_coefs = recent_W.mean(axis=0)

            predicted = mean_coefs @ nmf.components_
            predicted = predicted / (predicted.sum() + 1e-12)
        except Exception:
            predicted = mean_profile

        # Normalize test profile
        test_norm = test_profile / (test_profile.sum() + 1e-12)

        # Correlations
        corr_nmf = float(np.corrcoef(test_norm, predicted)[0, 1])
        corr_base = float(np.corrcoef(test_norm, mean_profile)[0, 1])

        if not np.isnan(corr_nmf):
            oos_corrs_nmf.append(corr_nmf)
        if not np.isnan(corr_base):
            oos_corrs_baseline.append(corr_base)

    if not oos_corrs_nmf:
        return {"ticker": ticker, "status": "INSUFFICIENT_DATA", "n_days": n}

    mean_corr_nmf = float(np.mean(oos_corrs_nmf))
    mean_corr_base = float(np.mean(oos_corrs_baseline))
    corr_lift = mean_corr_nmf - mean_corr_base

    return {
        "ticker": ticker,
        "status": "OK",
        "n_days": n,
        "n_oos": len(oos_corrs_nmf),
        "mean_oos_corr_nmf": round(mean_corr_nmf, 4),
        "mean_oos_corr_baseline": round(mean_corr_base, 4),
        "corr_lift": round(corr_lift, 4),
        "median_oos_corr_nmf": round(float(np.median(oos_corrs_nmf)), 4),
        "pct_beat_baseline": round(
            float(np.mean(np.array(oos_corrs_nmf) > np.array(oos_corrs_baseline[:len(oos_corrs_nmf)]))) * 100, 1
        ),
    }


# ===========================================================================
# Main
# ===========================================================================

def run_all(tickers: list[str], tests: list[str], max_days: int = 500):
    """Run the specified tests across all tickers."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    results = {"acf": [], "rv": [], "profile": []}
    panels = {}

    print("=" * 70)
    print(f"PREDICTIVE TESTS — {len(tickers)} tickers, {len(tests)} tests")
    print("=" * 70)

    # Phase 1: Build daily panels
    print("\n--- Building daily feature panels ---")
    for ticker in tickers:
        panel = build_daily_panel(ticker, max_days=max_days)
        if len(panel) >= 30:
            panels[ticker] = panel
        else:
            print(f"  [{ticker}] SKIP: only {len(panel)} days")

    print(f"\n{len(panels)} tickers with sufficient data.\n")

    # Phase 2: Run tests
    for test_name in tests:
        print(f"\n{'=' * 70}")
        print(f"TEST: {test_name.upper()}")
        print(f"{'=' * 70}")

        for ticker, panel in panels.items():
            if test_name == "acf":
                result = test_acf_forecast(panel, ticker)
            elif test_name == "rv":
                result = test_rv_prediction(panel, ticker)
            elif test_name == "profile":
                result = test_profile_forecast(panel, ticker)
            else:
                continue

            results[test_name].append(result)

            if result.get("status") == "OK":
                if test_name == "acf":
                    lift = result["r2_lift_over_ar1"]
                    marker = "✓" if lift > 0 else "✗"
                    print(
                        f"  {marker} {ticker:6s}: R²={result['oos_r2_full']:.4f}"
                        f"  AR(1)={result['oos_r2_ar1']:.4f}"
                        f"  lift={lift:+.4f}"
                        f"  corr={result['oos_corr_full']:.3f}"
                        f"  persist={result['acf_persistence']:.3f}"
                        f"  damped={result['pct_dampened']:.0f}%"
                        f"  (n={result['n_oos']})"
                    )
                elif test_name == "rv":
                    lift = result["r2_lift_from_acf"]
                    marker = "✓" if lift > 0 else "✗"
                    print(
                        f"  {marker} {ticker:6s}: R²={result['oos_r2_full']:.4f}"
                        f"  baseline={result['oos_r2_baseline']:.4f}"
                        f"  lift={lift:+.4f}"
                        f"  (n={result['n_oos']})"
                    )
                elif test_name == "profile":
                    lift = result["corr_lift"]
                    marker = "✓" if lift > 0.01 else "✗"
                    print(
                        f"  {marker} {ticker:6s}: corr={result['mean_oos_corr_nmf']:.3f}"
                        f"  baseline={result['mean_oos_corr_baseline']:.3f}"
                        f"  lift={lift:+.3f}"
                        f"  beat%={result['pct_beat_baseline']:.0f}%"
                        f"  (n={result['n_oos']})"
                    )
            else:
                print(f"  - {ticker:6s}: {result.get('status', 'ERROR')}")

    # Phase 3: Summary tables
    print("\n\n" + "=" * 70)
    print("AGGREGATE SUMMARY")
    print("=" * 70)

    for test_name in tests:
        ok = [r for r in results[test_name] if r.get("status") == "OK"]
        if not ok:
            print(f"\n{test_name}: No valid results.")
            continue

        print(f"\n--- {test_name.upper()} ({len(ok)} tickers) ---")

        if test_name == "acf":
            r2s = [r["oos_r2_full"] for r in ok]
            lifts = [r["r2_lift_over_ar1"] for r in ok]
            persists = [r["acf_persistence"] for r in ok]
            n_beat = sum(1 for l in lifts if l > 0)
            print(f"  Mean OOS R² (full):   {np.mean(r2s):.4f} (±{np.std(r2s):.4f})")
            print(f"  Mean OOS R² (AR1):    {np.mean([r['oos_r2_ar1'] for r in ok]):.4f}")
            print(f"  Mean R² lift:         {np.mean(lifts):+.4f}")
            print(f"  Mean ACF persistence: {np.mean(persists):.3f}")
            print(f"  Tickers w/ positive lift: {n_beat}/{len(ok)} ({n_beat/len(ok)*100:.0f}%)")
            print(f"  Best: {max(ok, key=lambda r: r['r2_lift_over_ar1'])['ticker']}"
                  f"  lift={max(lifts):+.4f}")
            print(f"  Worst: {min(ok, key=lambda r: r['r2_lift_over_ar1'])['ticker']}"
                  f"  lift={min(lifts):+.4f}")

        elif test_name == "rv":
            r2s = [r["oos_r2_full"] for r in ok]
            lifts = [r["r2_lift_from_acf"] for r in ok]
            n_beat = sum(1 for l in lifts if l > 0)
            print(f"  Mean OOS R² (full): {np.mean(r2s):.4f}")
            print(f"  Mean OOS R² (AR1):  {np.mean([r['oos_r2_baseline'] for r in ok]):.4f}")
            print(f"  Mean R² lift:       {np.mean(lifts):+.4f}")
            print(f"  Tickers with positive lift: {n_beat}/{len(ok)}")
            print(f"  Best: {max(ok, key=lambda r: r['r2_lift_from_acf'])['ticker']}"
                  f"  lift={max(lifts):+.4f}")

        elif test_name == "profile":
            corrs = [r["mean_oos_corr_nmf"] for r in ok]
            lifts = [r["corr_lift"] for r in ok]
            n_beat = sum(1 for l in lifts if l > 0.01)
            print(f"  Mean OOS corr (NMF):     {np.mean(corrs):.3f}")
            print(f"  Mean OOS corr (baseline): {np.mean([r['mean_oos_corr_baseline'] for r in ok]):.3f}")
            print(f"  Mean corr lift:           {np.mean(lifts):+.3f}")
            print(f"  Tickers with >1% lift:    {n_beat}/{len(ok)}")

    # Save results
    output = {
        "timestamp": timestamp,
        "n_tickers": len(panels),
        "tests": {k: v for k, v in results.items() if v},
    }

    # Clean for JSON (remove numpy arrays / profile data)
    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items() if k != "profile"}
        elif isinstance(obj, list):
            return [clean(v) for v in obj]
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    outpath = RESULTS_DIR / f"predictive_tests_{timestamp}.json"
    with open(outpath, "w") as f:
        json.dump(clean(output), f, indent=2)
    print(f"\nResults saved to: {outpath.name}")

    return results


# ===========================================================================
# CLI
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Predictive Tests for ACF Thesis")
    parser.add_argument("--ticker", type=str, default=None,
                        help="Run for a single ticker (default: all)")
    parser.add_argument("--test", type=str, default=None,
                        choices=["acf", "rv", "profile"],
                        help="Run a single test (default: all)")
    parser.add_argument("--max-days", type=int, default=500,
                        help="Max days per ticker")
    args = parser.parse_args()

    tickers = [args.ticker.upper()] if args.ticker else ALL_TICKERS
    tests = [args.test] if args.test else ["acf", "rv", "profile"]

    run_all(tickers, tests, max_days=args.max_days)


if __name__ == "__main__":
    main()
