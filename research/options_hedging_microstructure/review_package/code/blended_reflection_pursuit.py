#!/usr/bin/env python3
"""
Blended Reflection Significance & Cross-Ticker Replication
===========================================================
Phase 3 of the cycle periodicity analysis.

1. Fetch daily OHLCV bars from Polygon for long histories (2010–2026)
2. Monte Carlo significance testing for cadence-stripped mirror signals
3. Cross-ticker replication: do other tickers show the same pattern?
4. Rolling stability: is the biweekly mirror signal stable or regime-specific?
5. OPEX-anchored analysis: does the signal align with options expiration?

Usage:
  cd /path/to/project
  source .venv/bin/activate
  python research/options_hedging_microstructure/blended_reflection_pursuit.py
"""
import os
import sys
import json
import time
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

warnings.filterwarnings("ignore", category=RuntimeWarning)

# ── Config ──────────────────────────────────────────────────────────────
API_KEY = os.environ.get("POLYGON_API_KEY")
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)
CACHE_DIR = RESULTS_DIR / "daily_bars_cache"
CACHE_DIR.mkdir(exist_ok=True)

# Tickers with long options histories for meaningful testing
TICKERS = [
    "GME", "AAPL", "MSFT", "TSLA", "NVDA", "AMD", "AMZN", "META",
    "NFLX", "GOOG", "SPY", "QQQ", "IWM", "XLF", "BAC", "JPM",
    "GS", "INTC", "CSCO", "DIS",
]

session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retries))


# ═══════════════════════════════════════════════════════════════════════
# 1. Fetch / Cache Daily Bars
# ═══════════════════════════════════════════════════════════════════════
def fetch_daily_bars(symbol: str, from_date: str = "2005-01-01",
                     to_date: str = "2026-02-12") -> pd.DataFrame:
    """Fetch daily OHLCV from Polygon, with disk caching."""
    cache_path = CACHE_DIR / f"{symbol}_daily.parquet"

    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        if len(df) > 100:
            return df

    if not API_KEY:
        print(f"    ⚠ No POLYGON_API_KEY — skipping {symbol}")
        return pd.DataFrame()

    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/day/{from_date}/{to_date}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": API_KEY}

    try:
        resp = session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            time.sleep(12)
            resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except Exception as e:
        print(f"    ⚠ Fetch failed for {symbol}: {e}")
        return pd.DataFrame()

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)
    df["date"] = pd.to_datetime(df["t"], unit="ms")
    df = df.rename(columns={"o": "open", "h": "high", "l": "low",
                             "c": "close", "v": "volume"})
    df = df[["date", "open", "high", "low", "close", "volume"]].set_index("date").sort_index()

    # Derived columns
    df["log_return"] = np.log(df["close"] / df["close"].shift(1))
    df["pct_return"] = df["close"].pct_change()

    df.to_parquet(cache_path)
    return df


# ═══════════════════════════════════════════════════════════════════════
# 2. Core Analysis Functions
# ═══════════════════════════════════════════════════════════════════════
def blended_mirror_corr(returns: np.ndarray, offset: int,
                        cadence: int, window: int = 60) -> list[float]:
    """Compute cadence-stripped mirror correlations at given offset."""
    n = len(returns)
    if offset + window >= n:
        return []

    corrs = []
    for i in range(0, n - offset - window, max(1, window // 4)):
        a = returns[i:i+window:cadence]
        b = returns[i+offset:i+offset+window:cadence]
        ml = min(len(a), len(b))
        if ml < 5:
            continue
        a, b = a[:ml], b[:ml]
        a_s, b_s = np.std(a), np.std(b)
        if a_s < 1e-12 or b_s < 1e-12:
            continue
        an = (a - a.mean()) / a_s
        bn = (b - b.mean()) / b_s
        corrs.append(float(np.mean(an * bn[::-1])))
    return corrs


def monte_carlo_blended(returns: np.ndarray, offset: int, cadence: int,
                        window: int = 60, n_shuffles: int = 1000) -> dict:
    """Monte Carlo significance test for cadence-stripped mirror signal."""
    # Real signal
    real_corrs = blended_mirror_corr(returns, offset, cadence, window)
    if not real_corrs:
        return {"error": "no valid windows"}
    real_mean = float(np.mean(real_corrs))

    # Shuffle distribution
    shuffle_means = []
    for _ in range(n_shuffles):
        shuffled = returns.copy()
        np.random.shuffle(shuffled)
        shuf_corrs = blended_mirror_corr(shuffled, offset, cadence, window)
        if shuf_corrs:
            shuffle_means.append(float(np.mean(shuf_corrs)))

    if not shuffle_means:
        return {"error": "shuffle failed"}

    null_mean = float(np.mean(shuffle_means))
    null_std = float(np.std(shuffle_means))
    z_score = (real_mean - null_mean) / null_std if null_std > 0 else 0

    # Empirical p-value (two-tailed)
    null_arr = np.array(shuffle_means)
    p_value = float(np.mean(np.abs(null_arr - null_mean) >= abs(real_mean - null_mean)))

    return {
        "real_mean": round(real_mean, 5),
        "real_std": round(float(np.std(real_corrs)), 5),
        "null_mean": round(null_mean, 5),
        "null_std": round(null_std, 5),
        "z_score": round(z_score, 3),
        "p_value": round(p_value, 4),
        "significant_05": abs(z_score) > 1.96,
        "significant_01": abs(z_score) > 2.576,
        "n_real_windows": len(real_corrs),
        "n_shuffles": len(shuffle_means),
    }


# ═══════════════════════════════════════════════════════════════════════
# 3. Full Analysis Pipeline
# ═══════════════════════════════════════════════════════════════════════
def main():
    print(f"\n{'#'*80}")
    print(f"  BLENDED REFLECTION — SIGNIFICANCE & REPLICATION")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*80}\n")

    all_results = {"timestamp": datetime.now().isoformat()}

    # ── Phase 1: Fetch Data ─────────────────────────────────────────
    print("▸ Fetching daily bars from Polygon (2005-2026)...\n")
    ticker_data = {}
    for symbol in TICKERS:
        print(f"  {symbol:6s} ... ", end="", flush=True)
        df = fetch_daily_bars(symbol)
        if df.empty or len(df) < 500:
            print(f"⚠ insufficient ({len(df)} days)")
            continue
        ticker_data[symbol] = df
        print(f"✓ {len(df)} days ({df.index[0].date()} → {df.index[-1].date()})")
        time.sleep(0.15)  # rate limit courtesy

    print(f"\n  → {len(ticker_data)} tickers with ≥500 days of data\n")

    # ── Phase 2: GME Deep Significance Test ─────────────────────────
    print("="*80)
    print("  PHASE 2: GME Blended Reflection — 1000-Shuffle Significance")
    print("="*80)

    if "GME" in ticker_data:
        gme_returns = ticker_data["GME"]["log_return"].dropna().values
        gme_n = len(gme_returns)
        print(f"\n  GME: {gme_n} trading days")

        # Test the top findings from Phase 2
        test_configs = [
            # (offset, cadence, description)
            (370, 10, "370d / biweekly (global peak from Phase 2)"),
            (370, 5, "370d / weekly"),
            (370, 7, "370d / weekly (7-day)"),
            (252, 10, "252d / biweekly"),
            (252, 5, "252d / weekly"),
            (504, 4, "504d / every-4th"),
            (504, 5, "504d / weekly"),
            (741, 5, "741d / weekly (original hypothesis)"),
            (741, 10, "741d / biweekly"),
            (370, 1, "370d / raw (no cadence strip)"),
            (504, 1, "504d / raw"),
        ]

        gme_results = {}
        print(f"\n  {'Config':<42s}  {'Real':>7}  {'Null':>7}  {'z':>6}  {'p':>6}  {'Sig?'}")
        print(f"  {'─'*42}  {'─'*7}  {'─'*7}  {'─'*6}  {'─'*6}  {'─'*5}")

        for offset, cadence, desc in test_configs:
            if offset >= gme_n - 60:
                continue
            result = monte_carlo_blended(gme_returns, offset, cadence,
                                         window=60, n_shuffles=1000)
            gme_results[f"{offset}_{cadence}"] = {**result, "desc": desc}

            if "error" not in result:
                sig = "✓✓" if result["significant_01"] else ("✓" if result["significant_05"] else "✗")
                print(f"  {desc:<42s}  {result['real_mean']:+7.4f}  {result['null_mean']:+7.4f}  "
                      f"{result['z_score']:+6.2f}  {result['p_value']:6.4f}  {sig}")
            else:
                print(f"  {desc:<42s}  {result['error']}")

        all_results["gme_significance"] = gme_results

    # ── Phase 3: Cross-Ticker Replication ───────────────────────────
    print(f"\n{'='*80}")
    print(f"  PHASE 3: Cross-Ticker Replication")
    print(f"{'='*80}")

    # Use the top 3 most interesting configs from GME to test across tickers
    replication_configs = [
        (370, 10, "370d/e10"),
        (252, 5, "252d/e5"),
        (504, 5, "504d/e5"),
    ]

    panel_results = {}
    print(f"\n  {'Ticker':<8}", end="")
    for _, _, desc in replication_configs:
        print(f"  {desc:>12}", end="")
    print(f"  {'N days':>8}")
    print(f"  {'─'*8}", end="")
    for _ in replication_configs:
        print(f"  {'─'*12}", end="")
    print(f"  {'─'*8}")

    for symbol, df in sorted(ticker_data.items()):
        returns = df["log_return"].dropna().values
        n = len(returns)

        row = {"symbol": symbol, "n_days": n}
        print(f"  {symbol:<8}", end="", flush=True)

        for offset, cadence, desc in replication_configs:
            if offset >= n - 60:
                print(f"  {'—':>12}", end="")
                row[desc] = None
                continue

            # Quick significance test (200 shuffles for panel speed)
            result = monte_carlo_blended(returns, offset, cadence,
                                         window=60, n_shuffles=200)
            if "error" not in result:
                sig_marker = "*" if result["significant_05"] else " "
                val_str = f"{result['real_mean']:+.4f}{sig_marker}"
                val_str += f"z{result['z_score']:+.1f}"
                print(f"  {val_str:>12}", end="")
                row[desc] = result
            else:
                print(f"  {'err':>12}", end="")
                row[desc] = None

        print(f"  {n:>8}")
        panel_results[symbol] = row

    all_results["panel_replication"] = panel_results

    # ── Phase 4: Rolling Stability (GME) ────────────────────────────
    print(f"\n{'='*80}")
    print(f"  PHASE 4: Rolling Stability — GME 370d/e10 Mirror")
    print(f"{'='*80}")

    if "GME" in ticker_data:
        gme_returns = ticker_data["GME"]["log_return"].dropna().values
        gme_dates = ticker_data["GME"].index[1:]  # skip first NaN
        gme_n = len(gme_returns)

        rolling_window = 504  # 2 years of data per window
        step = 63  # quarterly steps
        offset = 370
        cadence = 10
        mirror_window = 60

        rolling_results = []
        print(f"\n  Window={rolling_window}d, step={step}d, offset={offset}d, cadence=e{cadence}")
        print(f"\n  {'Window':>30}  {'Mirror':>8}  {'N win':>6}  {'Sig?'}")
        print(f"  {'─'*30}  {'─'*8}  {'─'*6}  {'─'*5}")

        for start in range(0, gme_n - rolling_window, step):
            end = start + rolling_window
            chunk = gme_returns[start:end]

            if offset + mirror_window >= len(chunk):
                continue

            corrs = blended_mirror_corr(chunk, offset, cadence, mirror_window)
            if not corrs:
                continue

            mean_corr = float(np.mean(corrs))

            # Quick significance against 100 shuffles
            shuf_means = []
            for _ in range(100):
                s = chunk.copy()
                np.random.shuffle(s)
                sc = blended_mirror_corr(s, offset, cadence, mirror_window)
                if sc:
                    shuf_means.append(float(np.mean(sc)))

            z = 0
            if shuf_means:
                null_std = np.std(shuf_means)
                z = (mean_corr - np.mean(shuf_means)) / null_std if null_std > 0 else 0

            sig = "✓" if abs(z) > 1.96 else "✗"

            start_date = gme_dates[start].strftime("%Y-%m-%d") if start < len(gme_dates) else "?"
            end_date = gme_dates[min(end, len(gme_dates)-1)].strftime("%Y-%m-%d")

            rolling_results.append({
                "start": start_date,
                "end": end_date,
                "mirror_mean": round(mean_corr, 4),
                "z_score": round(float(z), 2),
                "n_windows": len(corrs),
                "significant": abs(z) > 1.96,
            })

            print(f"  {start_date} → {end_date}  {mean_corr:+8.4f}  {len(corrs):6d}  {sig} (z={z:+.2f})")

        all_results["rolling_stability"] = rolling_results

        # Summary
        if rolling_results:
            sig_count = sum(1 for r in rolling_results if r["significant"])
            total = len(rolling_results)
            print(f"\n  → {sig_count}/{total} windows significant at p<0.05")
            mirror_vals = [r["mirror_mean"] for r in rolling_results]
            print(f"  → Mean mirror across all windows: {np.mean(mirror_vals):+.4f}")
            print(f"  → Std of mirror across windows: {np.std(mirror_vals):.4f}")

    # ── Phase 5: OPEX-Anchored Analysis ─────────────────────────────
    print(f"\n{'='*80}")
    print(f"  PHASE 5: OPEX-Anchored Analysis — Mirror Signal vs OPEX Calendar")
    print(f"{'='*80}")

    if "GME" in ticker_data:
        gme_df = ticker_data["GME"]
        gme_returns = gme_df["log_return"].dropna().values
        gme_dates = gme_df.index[1:]

        # Standard monthly OPEX: 3rd Friday of each month
        opex_dates = []
        for year in range(gme_dates[0].year, gme_dates[-1].year + 1):
            for month in range(1, 13):
                # Find 3rd Friday
                first_day = pd.Timestamp(year=year, month=month, day=1)
                # Day of week: Monday=0, Friday=4
                first_fri = first_day + pd.Timedelta(days=(4 - first_day.dayofweek) % 7)
                third_fri = first_fri + pd.Timedelta(weeks=2)
                opex_dates.append(third_fri)

        opex_dates = sorted([d for d in opex_dates if gme_dates[0] <= d <= gme_dates[-1]])

        # Test: is the mirror signal stronger in OPEX weeks vs non-OPEX weeks?
        all_corr_opex = []
        all_corr_non_opex = []

        offset = 370
        cadence = 10
        window = 60

        for i in range(0, len(gme_returns) - offset - window, window // 4):
            center_date = gme_dates[i + window // 2] if i + window // 2 < len(gme_dates) else None
            if center_date is None:
                continue

            a = gme_returns[i:i+window:cadence]
            b = gme_returns[i+offset:i+offset+window:cadence]
            ml = min(len(a), len(b))
            if ml < 5:
                continue
            a, b = a[:ml], b[:ml]
            a_s, b_s = np.std(a), np.std(b)
            if a_s < 1e-12 or b_s < 1e-12:
                continue
            an = (a - a.mean()) / a_s
            bn = (b - b.mean()) / b_s
            corr = float(np.mean(an * bn[::-1]))

            # Check if within 5 trading days of an OPEX
            near_opex = any(abs((center_date - opex).days) <= 7 for opex in opex_dates)

            if near_opex:
                all_corr_opex.append(corr)
            else:
                all_corr_non_opex.append(corr)

        if all_corr_opex and all_corr_non_opex:
            opex_mean = float(np.mean(all_corr_opex))
            non_opex_mean = float(np.mean(all_corr_non_opex))

            print(f"\n  OPEX-week windows:     mean={opex_mean:+.4f}, n={len(all_corr_opex)}")
            print(f"  Non-OPEX-week windows: mean={non_opex_mean:+.4f}, n={len(all_corr_non_opex)}")
            print(f"  Difference: {opex_mean - non_opex_mean:+.4f}")

            # Welch's t-test
            from scipy import stats as sp_stats
            try:
                t_stat, t_p = sp_stats.ttest_ind(all_corr_opex, all_corr_non_opex, equal_var=False)
                print(f"  Welch's t-test: t={t_stat:.3f}, p={t_p:.4f}")
                sig = "✓ SIGNIFICANT" if t_p < 0.05 else "✗ not significant"
                print(f"  → OPEX enhancement: {sig}")
                all_results["opex_analysis"] = {
                    "opex_mean": round(opex_mean, 5),
                    "non_opex_mean": round(non_opex_mean, 5),
                    "difference": round(opex_mean - non_opex_mean, 5),
                    "t_stat": round(float(t_stat), 3),
                    "p_value": round(float(t_p), 4),
                    "significant": float(t_p) < 0.05,
                }
            except ImportError:
                print("  (scipy not available for t-test)")

    # ── Phase 6: FFT on Absolute Returns (Volume Proxy) ────────────
    print(f"\n{'='*80}")
    print(f"  PHASE 6: Cross-Ticker FFT — Confirming 509d Cycle Panel-Wide")
    print(f"{'='*80}")

    fft_panel = {}
    for symbol, df in sorted(ticker_data.items()):
        returns = df["log_return"].dropna().values
        n = len(returns)
        if n < 1000:
            continue

        close = df["close"].dropna().values
        close = close - np.mean(close)
        w = np.hanning(len(close))
        fft = np.fft.rfft(close * w)
        power = np.abs(fft) ** 2
        freqs = np.fft.rfftfreq(len(close), d=1.0)
        periods = np.where(freqs > 0, 1.0 / freqs, np.inf)

        mask = (periods > 20) & (periods < len(close) / 2) & np.isfinite(periods)
        vp = power[mask]
        vper = periods[mask]
        total = vp.sum()

        if total < 1e-12:
            continue

        # Check 250d and 500d bands
        bands = {}
        for bname, lo, hi in [("~250", 230, 275), ("~500", 475, 535)]:
            bm = (vper >= lo) & (vper <= hi)
            if bm.any():
                bp = vp[bm]
                bper = vper[bm]
                pi = np.argmax(bp)
                bands[bname] = {"period": round(float(bper[pi]), 1),
                                "pct": round(float(bp[pi] / total * 100), 2)}
            else:
                bands[bname] = {"period": None, "pct": 0}

        # Top peak
        top_idx = np.argmax(vp)
        top_period = round(float(vper[top_idx]), 1)
        top_pct = round(float(vp[top_idx] / total * 100), 2)

        fft_panel[symbol] = {"n": n, "top_period": top_period, "top_pct": top_pct, "bands": bands}

        p250 = bands["~250"]["pct"]
        p500 = bands["~500"]["pct"]
        print(f"  {symbol:6s}: n={n:5d}, top={top_period:6.0f}d ({top_pct:5.1f}%), "
              f"~250d={p250:5.2f}%, ~500d={p500:5.2f}%")

    all_results["fft_panel"] = fft_panel

    # Check how many have 500d as dominant
    if fft_panel:
        has_500 = sum(1 for v in fft_panel.values()
                      if v["bands"]["~500"]["pct"] > 1.0)
        total = len(fft_panel)
        print(f"\n  → {has_500}/{total} tickers with >1% spectral power at ~500d")

    # ── Save ────────────────────────────────────────────────────────
    out_path = RESULTS_DIR / "blended_reflection_results.json"
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n\n  📁 Full results saved to {out_path.name}")

    # ── Final Summary ───────────────────────────────────────────────
    print(f"\n{'#'*80}")
    print(f"  FINAL SUMMARY")
    print(f"{'#'*80}")

    if "gme_significance" in all_results:
        sig_configs = [k for k, v in all_results["gme_significance"].items()
                       if isinstance(v, dict) and v.get("significant_05")]
        print(f"\n  GME: {len(sig_configs)} / {len(all_results['gme_significance'])} configs significant at p<0.05")
        for k in sig_configs:
            v = all_results["gme_significance"][k]
            print(f"    {v.get('desc', k)}: z={v['z_score']:+.2f}, p={v['p_value']:.4f}")

    if "rolling_stability" in all_results:
        rs = all_results["rolling_stability"]
        sig_count = sum(1 for r in rs if r["significant"])
        print(f"\n  Rolling stability: {sig_count}/{len(rs)} windows significant")

    if "opex_analysis" in all_results:
        oa = all_results["opex_analysis"]
        print(f"\n  OPEX enhancement: diff={oa['difference']:+.5f}, p={oa['p_value']:.4f}")

    print(f"\n{'#'*80}\n")


if __name__ == "__main__":
    main()
