#!/usr/bin/env python3
"""
IPO Origin Scanner — Reverse Engineering Options↔Equity Temporal Convolution
=============================================================================
Phase 99: Find recently IPO'd tickers where options history starts from
inception, enabling observation of how options mechanics bootstrap the
echo/ripple structure visible in mature equities like GME.

Uses ThetaData V3 REST API (local terminal on port 25503).

Key endpoints:
  - /v3/stock/list/dates/trade   → first/last equity trade dates
  - /v3/option/list/expirations  → all available option expirations
  - /v3/option/list/dates/trade  → first/last option trade dates
  - /v3/stock/history/eod        → daily bar data
  - /v3/option/history/trade     → tick-level option trades
  - /v3/stock/history/trade      → tick-level equity trades
"""

from __future__ import annotations

import sys
import time
import json
from io import StringIO
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============================================================================
# Configuration
# ============================================================================

BASE_URL = "http://127.0.0.1:25503/v3"
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw"
THETA_OPTS_DIR = DATA_DIR / "thetadata" / "trades"
THETA_EQUITY_DIR = DATA_DIR / "thetadata" / "stock_trades"
POLYGON_EQUITY_DIR = DATA_DIR / "polygon" / "trades"
RESULTS_DIR = Path(__file__).parent.parent.parent / "output" / "ipo_scanner"

# Polygon API for tick-level equity (ThetaData FREE tier only has EOD)
import os
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")

# Persistent session with retry logic
SESSION = requests.Session()
retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(pool_connections=50, pool_maxsize=50, max_retries=retries)
SESSION.mount("http://", adapter)
SESSION.mount("https://", adapter)


# ============================================================================
# Data classes
# ============================================================================

@dataclass
class TickerProfile:
    """Complete profile of a ticker's data availability for IPO-origin analysis."""
    symbol: str
    # Equity data range
    equity_first_date: str | None = None
    equity_last_date: str | None = None
    equity_total_days: int = 0
    # Options data range
    options_first_date: str | None = None
    options_last_date: str | None = None
    options_total_expirations: int = 0
    options_earliest_expiration: str | None = None
    # Derived metrics
    pre_options_days: int = 0  # equity days before options existed
    options_history_days: int = 0  # total days of options history
    gap_days: int = 0  # gap between equity start and options start
    # Quality scores
    coverage_score: float = 0.0  # 0-1, higher = better for our analysis
    notes: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


# ============================================================================
# ThetaData V3 API Helpers
# ============================================================================

def check_terminal() -> bool:
    """Verify Theta Terminal is running."""
    try:
        resp = SESSION.get(f"{BASE_URL}/stock/list/dates/trade?symbol=AAPL&format=csv", timeout=3)
        return resp.status_code == 200
    except requests.exceptions.ConnectionError:
        return False


def get_stock_trade_dates(symbol: str) -> list[str]:
    """Get all dates with equity trade data for a symbol."""
    url = f"{BASE_URL}/stock/list/dates/trade"
    params = {"symbol": symbol, "format": "csv"}
    try:
        resp = SESSION.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            return []
        df = pd.read_csv(StringIO(resp.text))
        if "date" in df.columns:
            return sorted(df["date"].astype(str).tolist())
        return []
    except Exception as e:
        print(f"  ⚠ Error fetching stock dates for {symbol}: {e}")
        return []


def get_option_expirations(symbol: str) -> list[str]:
    """Get all listed option expirations for a symbol."""
    url = f"{BASE_URL}/option/list/expirations"
    params = {"symbol": symbol, "format": "csv"}
    try:
        resp = SESSION.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            return []
        df = pd.read_csv(StringIO(resp.text))
        if "expiration" in df.columns:
            return sorted(df["expiration"].astype(str).tolist())
        return []
    except Exception as e:
        print(f"  ⚠ Error fetching option expirations for {symbol}: {e}")
        return []


def get_option_trade_dates(symbol: str) -> list[str]:
    """Get all dates with option trade data for a symbol."""
    url = f"{BASE_URL}/option/list/dates/trade"
    params = {"symbol": symbol, "format": "csv"}
    try:
        resp = SESSION.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            return []
        df = pd.read_csv(StringIO(resp.text))
        if "date" in df.columns:
            return sorted(df["date"].astype(str).tolist())
        return []
    except Exception as e:
        print(f"  ⚠ Error fetching option trade dates for {symbol}: {e}")
        return []


def get_eod_bars(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch EOD bars for a symbol over a date range."""
    url = f"{BASE_URL}/stock/history/eod"
    params = {
        "symbol": symbol,
        "start_date": start_date.replace("-", ""),
        "end_date": end_date.replace("-", ""),
        "format": "csv",
    }
    try:
        resp = SESSION.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            return pd.DataFrame()
        df = pd.read_csv(StringIO(resp.text))
        return df
    except Exception as e:
        print(f"  ⚠ Error fetching EOD bars for {symbol}: {e}")
        return pd.DataFrame()


def fetch_stock_trades_day(symbol: str, date_str: str) -> pd.DataFrame:
    """Fetch tick-level equity trades for one day from ThetaData."""
    url = f"{BASE_URL}/stock/history/trade"
    date_clean = date_str.replace("-", "")
    params = {
        "symbol": symbol,
        "date": date_clean,
        "format": "csv",
    }
    try:
        resp = SESSION.get(url, params=params, timeout=60)
        if resp.status_code != 200:
            return pd.DataFrame()
        df = pd.read_csv(StringIO(resp.text))
        return df
    except Exception as e:
        print(f"  ⚠ Error fetching stock trades for {symbol} on {date_str}: {e}")
        return pd.DataFrame()


def fetch_option_trades_bulk(symbol: str, date_str: str, expiration: str) -> pd.DataFrame:
    """Fetch ALL strikes for a given expiration (bulk) on a given date."""
    url = f"{BASE_URL}/option/history/trade"
    date_clean = date_str.replace("-", "")
    exp_clean = expiration.replace("-", "")
    params = {
        "symbol": symbol,
        "expiration": exp_clean,
        "strike": 0,  # Bulk: all strikes
        "date": date_clean,
        "format": "csv",
    }
    try:
        resp = SESSION.get(url, params=params, timeout=60)
        if resp.status_code != 200:
            return pd.DataFrame()
        df = pd.read_csv(StringIO(resp.text))
        if not df.empty and "expiration" not in df.columns:
            df["expiration"] = exp_clean
        return df
    except Exception as e:
        print(f"  ⚠ Error fetching option trades for {symbol} exp={expiration}: {e}")
        return pd.DataFrame()


def fetch_polygon_equity_day(symbol: str, date_str: str) -> pd.DataFrame:
    """
    Fetch tick-level equity trades for one day from Polygon REST API.
    This is the workhorse for granular equity data (ThetaData FREE tier
    only provides EOD bars for stocks).
    """
    if not POLYGON_API_KEY:
        return pd.DataFrame()

    date_clean = date_str.replace("-", "").replace('"', '')
    # Convert YYYYMMDD to YYYY-MM-DD for Polygon
    if len(date_clean) == 8 and "-" not in date_clean:
        date_hyphen = f"{date_clean[:4]}-{date_clean[4:6]}-{date_clean[6:8]}"
    else:
        date_hyphen = date_str

    out_path = POLYGON_EQUITY_DIR / f"symbol={symbol}" / f"date={date_hyphen}" / "part-0.parquet"
    if out_path.exists():
        return pd.read_parquet(out_path)

    all_results = []
    url = f"https://api.polygon.io/v3/trades/{symbol}"
    params = {"timestamp": date_hyphen, "limit": 50000, "apiKey": POLYGON_API_KEY}

    while url:
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            all_results.extend(results)
            url = data.get("next_url")
            if url and "apiKey" not in url:
                url += f"&apiKey={POLYGON_API_KEY}"
            params = {}
        except Exception as e:
            print(f"  ⚠ Polygon error for {symbol} on {date_str}: {e}")
            break

    if not all_results:
        return pd.DataFrame()

    df = pd.DataFrame(all_results)
    df["timestamp"] = pd.to_datetime(df["sip_timestamp"], unit="ns")
    cols = [c for c in ["timestamp", "price", "size", "exchange", "conditions"] if c in df.columns]
    df = df[cols]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    return df


def fetch_polygon_equity_batch(
    symbol: str,
    dates: list[str],
    verbose: bool = True,
    delay: float = 0.15,
) -> int:
    """Fetch tick-level equity trades for multiple days from Polygon."""
    if not POLYGON_API_KEY:
        if verbose:
            print("  ⚠ POLYGON_API_KEY not set, skipping equity tick fetch")
        return 0

    fetched = 0
    for i, date in enumerate(dates):
        df = fetch_polygon_equity_day(symbol, date)
        if not df.empty:
            fetched += 1
            if verbose and (i + 1) % 10 == 0:
                print(f"     [{i+1}/{len(dates)}] {date} — {len(df):,} trades")
        time.sleep(delay)
    return fetched


# ============================================================================
# Profile Builder
# ============================================================================

def build_ticker_profile(symbol: str, verbose: bool = True) -> TickerProfile:
    """
    Build a complete data availability profile for a ticker.
    This is the core scanner function.
    """
    profile = TickerProfile(symbol=symbol)

    if verbose:
        print(f"\n{'='*60}")
        print(f"  Scanning: {symbol}")
        print(f"{'='*60}")

    # 1. Stock trade date range
    if verbose:
        print(f"  📊 Checking equity trade dates...")
    stock_dates = get_stock_trade_dates(symbol)
    if stock_dates:
        profile.equity_first_date = stock_dates[0]
        profile.equity_last_date = stock_dates[-1]
        profile.equity_total_days = len(stock_dates)
        if verbose:
            print(f"     First: {stock_dates[0]}, Last: {stock_dates[-1]}, Total: {len(stock_dates)} days")
    else:
        profile.notes.append("No equity trade data found")
        if verbose:
            print(f"     ❌ No equity trade data")
        return profile

    # 2. Option expirations
    if verbose:
        print(f"  📋 Checking option expirations...")
    expirations = get_option_expirations(symbol)
    if expirations:
        profile.options_total_expirations = len(expirations)
        profile.options_earliest_expiration = expirations[0]
        if verbose:
            print(f"     Total expirations: {len(expirations)}")
            print(f"     Earliest: {expirations[0]}, Latest: {expirations[-1]}")
    else:
        profile.notes.append("No option expirations found")
        if verbose:
            print(f"     ❌ No option data")
        return profile

    # 3. Option trade date range
    # Try direct endpoint first, fall back to inferring from expirations
    if verbose:
        print(f"  📈 Checking option trade dates...")
    opt_dates = get_option_trade_dates(symbol)
    if opt_dates:
        profile.options_first_date = opt_dates[0]
        profile.options_last_date = opt_dates[-1]
        if verbose:
            print(f"     First: {opt_dates[0]}, Last: {opt_dates[-1]}, Total: {len(opt_dates)} days")
    else:
        # Fallback: infer options start from earliest expiration
        # The earliest expiration is listed ~1-4 weeks after options start trading
        if expirations:
            profile.options_first_date = profile.equity_first_date  # Options trade from equity start
            profile.options_last_date = profile.equity_last_date
            profile.notes.append("Options dates inferred from expirations (STANDARD sub)")
            if verbose:
                print(f"     ℹ️  Inferred from expirations (earliest exp: {expirations[0]})")
        else:
            profile.notes.append("No option trade dates found")
            if verbose:
                print(f"     ❌ No option trade date data")

    # 4. Compute derived metrics
    def _parse_date(d):
        try:
            return datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            return datetime.strptime(d, "%Y%m%d")

    equity_start = _parse_date(profile.equity_first_date)

    if profile.options_first_date:
        # Use earliest expiration as proxy for when options actually started
        # (the expiration must be >= options listing date)
        earliest_exp = _parse_date(expirations[0]) if expirations else None
        if earliest_exp:
            # Options likely started trading ~2 weeks before earliest expiration
            inferred_opts_start = earliest_exp - timedelta(days=14)
            # But not before equity started
            opts_start = max(equity_start, inferred_opts_start)
        else:
            opts_start = _parse_date(profile.options_first_date)

        profile.options_first_date = opts_start.strftime("%Y-%m-%d")
        profile.gap_days = (opts_start - equity_start).days
        profile.pre_options_days = max(0, profile.gap_days)

        opts_end = _parse_date(profile.options_last_date or profile.equity_last_date)
        profile.options_history_days = (opts_end - opts_start).days
    else:
        profile.gap_days = -1

    # 5. Compute coverage score
    # Ideal: equity start ~2021-2023, options within 3 months, 500+ expirations
    score = 0.0

    # Recency bonus: IPO in 2021-2024 preferred
    years_since_ipo = (datetime.now() - equity_start).days / 365.25
    if 1.5 <= years_since_ipo <= 5:
        score += 0.3  # Sweet spot
    elif 0.5 <= years_since_ipo <= 8:
        score += 0.15
    else:
        score += 0.05

    # Gap penalty: smaller gap between equity and options = better
    if 0 <= profile.gap_days <= 30:
        score += 0.25  # Options almost immediately
    elif profile.gap_days <= 90:
        score += 0.20
    elif profile.gap_days <= 180:
        score += 0.10
    else:
        score += 0.0

    # Options depth: more expirations = more liquid
    if profile.options_total_expirations >= 500:
        score += 0.25
    elif profile.options_total_expirations >= 200:
        score += 0.20
    elif profile.options_total_expirations >= 50:
        score += 0.10
    else:
        score += 0.05

    # History length: >2 years of options = good analysis potential
    if profile.options_history_days >= 730:
        score += 0.20
    elif profile.options_history_days >= 365:
        score += 0.15
    elif profile.options_history_days >= 180:
        score += 0.10
    else:
        score += 0.05

    profile.coverage_score = round(score, 2)

    if verbose:
        print(f"\n  🏆 Coverage Score: {profile.coverage_score:.2f}")
        print(f"     Gap (equity→options): {profile.gap_days} days")
        print(f"     Pre-options baseline: {profile.pre_options_days} days")
        print(f"     Options history: {profile.options_history_days} days")
        print(f"     Expirations: {profile.options_total_expirations}")

    return profile


# ============================================================================
# Batch Scanner
# ============================================================================

# Default candidate list — mid-cap IPOs from 2021-2024 with known options
DEFAULT_CANDIDATES = [
    # 2023-2024 IPOs (cleanest origin)
    "ARM",    # Arm Holdings — IPO Sep 2023
    "RDDT",   # Reddit — IPO Mar 2024
    "CART",   # Instacart/Maplebear — IPO Sep 2023
    "BIRK",   # Birkenstock — IPO Oct 2023
    # 2021-2022 IPOs (more history)
    "RIVN",   # Rivian — IPO Nov 2021
    "RKLB",   # Rocket Lab — SPAC Aug 2021
    "IONQ",   # IonQ — SPAC Oct 2021
    "BIRD",   # Allbirds — IPO Nov 2021
    "DUOL",   # Duolingo — IPO Jul 2021
    "HOOD",   # Robinhood — IPO Jul 2021
    "COIN",   # Coinbase — DPO Apr 2021
    "AFRM",   # Affirm — IPO Jan 2021
    "PLTR",   # Palantir — DPO Sep 2020
    "SNOW",   # Snowflake — IPO Sep 2020
]


def scan_candidates(
    symbols: list[str] | None = None,
    verbose: bool = True,
    delay: float = 0.5,
) -> list[TickerProfile]:
    """
    Scan multiple tickers and rank by suitability for IPO-origin analysis.
    """
    if symbols is None:
        symbols = DEFAULT_CANDIDATES

    profiles = []
    for i, sym in enumerate(symbols):
        if verbose:
            print(f"\n[{i+1}/{len(symbols)}]", end="")
        try:
            profile = build_ticker_profile(sym, verbose=verbose)
            profiles.append(profile)
        except Exception as e:
            print(f"  ❌ Error scanning {sym}: {e}")
            profiles.append(TickerProfile(symbol=sym, notes=[f"Error: {e}"]))
        time.sleep(delay)  # courtesy delay

    # Sort by coverage score
    profiles.sort(key=lambda p: p.coverage_score, reverse=True)
    return profiles


def print_ranking(profiles: list[TickerProfile]) -> None:
    """Print a ranked summary table."""
    print(f"\n{'='*90}")
    print(f"  IPO-Origin Suitability Ranking")
    print(f"{'='*90}")
    print(f"{'Rank':<5} {'Symbol':<8} {'Score':<7} {'Equity Start':<14} {'Opts Start':<14} "
          f"{'Gap':<6} {'Exp#':<7} {'OptDays':<8}")
    print(f"{'-'*90}")

    for i, p in enumerate(profiles):
        print(
            f"{i+1:<5} {p.symbol:<8} {p.coverage_score:<7.2f} "
            f"{p.equity_first_date or 'N/A':<14} "
            f"{p.options_first_date or 'N/A':<14} "
            f"{str(p.gap_days)+'d':<6} "
            f"{p.options_total_expirations:<7} "
            f"{p.options_history_days:<8}"
        )
    print(f"{'='*90}")


def save_results(profiles: list[TickerProfile], suffix: str = "") -> Path:
    """Save scan results to JSON and CSV."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"ipo_scan_{ts}{suffix}"

    # JSON (full detail)
    json_path = RESULTS_DIR / f"{base}.json"
    with open(json_path, "w") as f:
        json.dump([p.to_dict() for p in profiles], f, indent=2)

    # CSV (summary)
    csv_path = RESULTS_DIR / f"{base}.csv"
    df = pd.DataFrame([p.to_dict() for p in profiles])
    # Drop list columns for CSV
    for col in df.columns:
        if df[col].apply(lambda x: isinstance(x, list)).any():
            df[col] = df[col].apply(lambda x: "; ".join(x) if isinstance(x, list) else x)
    df.to_csv(csv_path, index=False)

    print(f"\n  💾 Results saved:")
    print(f"     JSON: {json_path}")
    print(f"     CSV:  {csv_path}")
    return json_path


# ============================================================================
# Data Fetcher — Download Full History for Selected Ticker
# ============================================================================

def fetch_genesis_data(
    symbol: str,
    max_equity_days: int = 500,
    max_option_days: int = 500,
    exp_window_days: int = 90,
    progress_callback=None,
    verbose: bool = True,
) -> dict:
    """
    Fetch the full genesis dataset for a selected ticker:
    1. EOD bars from IPO (FREE tier) — for cross-day echo analysis
    2. Tick-level option trades from options listing (STANDARD tier)

    Note: Stock tick trades require paid stock subscription (403 on FREE).
    We use EOD bars for equity and rely on Polygon for tick-level equity
    when needed.

    Parameters
    ----------
    symbol : str
        Ticker symbol
    max_equity_days : int
        Maximum number of equity trading days to fetch
    max_option_days : int
        Maximum number of option trading days to fetch
    exp_window_days : int
        Window size in days ahead to look for expirations
    progress_callback : callable
        Optional callback(progress_fraction) for UI integration
    """
    if verbose:
        print(f"\n{'='*60}")
        print(f"  Fetching Genesis Data for {symbol}")
        print(f"{'='*60}")

    result = {"symbol": symbol, "equity_eod_days": 0, "option_days": 0, "errors": []}

    # --- Equity EOD bars ---
    stock_dates = get_stock_trade_dates(symbol)
    if not stock_dates:
        result["errors"].append("No equity dates available")
        return result

    target_dates = stock_dates[:max_equity_days]
    if verbose:
        print(f"\n  📊 Fetching EOD bars for {len(target_dates)} equity trading days...")

    # Fetch in monthly chunks for efficiency
    eod_out_dir = THETA_EQUITY_DIR / f"symbol={symbol}"
    eod_out_dir.mkdir(parents=True, exist_ok=True)
    eod_cache = eod_out_dir / "eod_bars.parquet"

    if eod_cache.exists():
        existing_eod = pd.read_parquet(eod_cache)
        if verbose:
            print(f"     Found cached EOD bars: {len(existing_eod)} rows")
    else:
        existing_eod = pd.DataFrame()

    # Fetch full range in one request (EOD is lightweight)
    first_date = target_dates[0]
    last_date = target_dates[-1]
    eod_df = get_eod_bars(symbol, first_date, last_date)

    if not eod_df.empty:
        # Merge with existing
        if not existing_eod.empty:
            eod_df = pd.concat([existing_eod, eod_df]).drop_duplicates(
                subset=["created"] if "created" in eod_df.columns else eod_df.columns[:1]
            )
        eod_df.to_parquet(eod_cache, index=False)
        result["equity_eod_days"] = len(eod_df)
        if verbose:
            print(f"     ✅ Saved {len(eod_df)} EOD bars to {eod_cache}")
    else:
        result["errors"].append("EOD bars returned empty")

    # --- Equity tick trades (via Polygon) ---
    if POLYGON_API_KEY:
        if verbose:
            print(f"\n  📈 Fetching tick-level equity trades via Polygon...")
        poly_count = fetch_polygon_equity_batch(symbol, target_dates, verbose=verbose)
        result["equity_tick_days"] = poly_count
        if verbose:
            print(f"     ✅ {poly_count} Polygon equity tick days fetched/cached")
    else:
        result["equity_tick_days"] = 0
        if verbose:
            print(f"\n  ℹ️  POLYGON_API_KEY not set — skipping tick-level equity")

    # --- Option trades (tick-level, STANDARD sub) ---
    expirations = get_option_expirations(symbol)
    if not expirations:
        result["errors"].append("No option expirations available")
        if verbose:
            print(f"  ❌ No option expirations for {symbol}")
        return result

    # Use equity trading dates to drive option fetching
    # (option/list/dates/trade is empty on STANDARD sub)
    target_opt_dates = target_dates[:max_option_days]
    if verbose:
        print(f"\n  📋 Fetching option trades for {len(target_opt_dates)} trading days...")

    opts_out_dir = THETA_OPTS_DIR / f"root={symbol}"
    opts_out_dir.mkdir(parents=True, exist_ok=True)

    for i, date in enumerate(target_opt_dates):
        date_clean = date.replace("-", "").replace('"', '')
        date_out = opts_out_dir / f"date={date_clean}"
        if date_out.exists() and any(date_out.glob("*.parquet")):
            result["option_days"] += 1
            continue  # skip already-fetched

        # Find expirations active on this date
        try:
            trade_dt = datetime.strptime(date_clean, "%Y%m%d")
        except ValueError:
            try:
                trade_dt = datetime.strptime(date.strip('"'), "%Y-%m-%d")
            except ValueError:
                continue

        active_exps = []
        for exp in expirations:
            exp_clean = exp.replace('"', '')
            try:
                exp_dt = datetime.strptime(exp_clean, "%Y-%m-%d")
            except ValueError:
                try:
                    exp_dt = datetime.strptime(exp_clean, "%Y%m%d")
                except ValueError:
                    continue
            if trade_dt <= exp_dt <= trade_dt + timedelta(days=exp_window_days):
                active_exps.append(exp_clean)

        if not active_exps:
            continue

        # Fetch bulk for each active expiration
        day_frames = []
        for exp in active_exps[:15]:  # cap at 15 expirations per day
            df = fetch_option_trades_bulk(symbol, date_clean, exp)
            if not df.empty:
                day_frames.append(df)
            time.sleep(0.05)

        if day_frames:
            combined = pd.concat(day_frames, ignore_index=True)
            date_out.mkdir(parents=True, exist_ok=True)
            combined.to_parquet(date_out / "part-0.parquet", index=False)
            result["option_days"] += 1
            if verbose and (i + 1) % 5 == 0:
                print(f"     [{i+1}/{len(target_opt_dates)}] fetched {date_clean} "
                      f"({len(combined)} trades across {len(active_exps)} exps)")

        if progress_callback:
            total_work = len(target_dates) + len(target_opt_dates)
            progress_callback((len(target_dates) + i + 1) / total_work)
        time.sleep(0.1)

    if verbose:
        print(f"\n  ✅ Genesis data fetch complete!")
        print(f"     Equity EOD days: {result['equity_eod_days']}")
        print(f"     Option tick days: {result['option_days']}")
        if result["errors"]:
            print(f"     Errors: {result['errors']}")

    return result


# ============================================================================
# Streamlit App
# ============================================================================

def run_streamlit_app():
    """Streamlit UI for the IPO Origin Scanner."""
    import streamlit as st

    st.set_page_config(page_title="IPO Origin Scanner", layout="wide")
    st.title("🔬 IPO Origin Scanner")
    st.markdown("""
    **Reverse Engineer the Options↔Equity Temporal Convolution**

    Find recently IPO'd tickers where we can observe the complete lifecycle 
    of how options mechanics bootstrap price echoes from zero.
    """)

    # Check terminal connection
    if not check_terminal():
        st.error("⚠️ Cannot connect to Theta Terminal on port 25503. Please start it first.")
        st.stop()

    st.success("✅ Connected to Theta Terminal")

    # --- Tab layout ---
    tab_scan, tab_fetch, tab_profile = st.tabs(["🔍 Scan Tickers", "📥 Fetch Data", "📊 Profile Detail"])

    with tab_scan:
        st.subheader("Scan Candidates")
        custom_symbols = st.text_area(
            "Symbols (comma-separated, or leave blank for defaults)",
            value=", ".join(DEFAULT_CANDIDATES),
        )
        symbols = [s.strip().upper() for s in custom_symbols.split(",") if s.strip()]

        if st.button("🚀 Run Scan", type="primary"):
            profiles = []
            progress = st.progress(0)
            status = st.empty()

            for i, sym in enumerate(symbols):
                status.text(f"Scanning {sym}... ({i+1}/{len(symbols)})")
                try:
                    profile = build_ticker_profile(sym, verbose=False)
                    profiles.append(profile)
                except Exception as e:
                    profiles.append(TickerProfile(symbol=sym, notes=[f"Error: {e}"]))
                progress.progress((i + 1) / len(symbols))
                time.sleep(0.3)

            profiles.sort(key=lambda p: p.coverage_score, reverse=True)
            st.session_state["scan_profiles"] = profiles
            status.text("Scan complete!")

        if "scan_profiles" in st.session_state:
            profiles = st.session_state["scan_profiles"]

            # Summary table
            df = pd.DataFrame([{
                "Rank": i + 1,
                "Symbol": p.symbol,
                "Score": p.coverage_score,
                "Equity Start": p.equity_first_date or "N/A",
                "Options Start": p.options_first_date or "N/A",
                "Gap (days)": p.gap_days,
                "Expirations": p.options_total_expirations,
                "Options History (days)": p.options_history_days,
            } for i, p in enumerate(profiles)])

            st.dataframe(
                df.style.background_gradient(subset=["Score"], cmap="YlGn"),
                use_container_width=True,
                hide_index=True,
            )

            # Save button
            if st.button("💾 Save Results"):
                path = save_results(profiles)
                st.success(f"Saved to {path}")

    with tab_fetch:
        st.subheader("Fetch Genesis Data")
        st.markdown("Download complete tick-level data for a selected ticker from IPO origin.")

        col1, col2, col3 = st.columns(3)
        with col1:
            fetch_symbol = st.text_input("Symbol", value="ARM").upper()
        with col2:
            max_eq = st.number_input("Max equity days", value=500, min_value=10, max_value=2000)
        with col3:
            max_opt = st.number_input("Max option days", value=500, min_value=10, max_value=2000)

        exp_window = st.slider("Expiration window (days ahead)", 30, 180, 90)

        if st.button("📥 Download Genesis Data", type="primary"):
            progress = st.progress(0)
            status = st.empty()

            def prog_cb(frac):
                progress.progress(frac)

            status.text(f"Fetching data for {fetch_symbol}...")
            result = fetch_genesis_data(
                fetch_symbol,
                max_equity_days=max_eq,
                max_option_days=max_opt,
                exp_window_days=exp_window,
                progress_callback=prog_cb,
                verbose=False,
            )
            st.session_state["fetch_result"] = result
            status.text("Fetch complete!")

            col_a, col_b = st.columns(2)
            col_a.metric("Equity Days", result["equity_days"])
            col_b.metric("Option Days", result["option_days"])
            if result["errors"]:
                st.warning(f"Errors: {result['errors']}")

    with tab_profile:
        st.subheader("Detailed Ticker Profile")
        detail_sym = st.text_input("Symbol to profile", value="ARM", key="profile_sym").upper()

        if st.button("🔎 Build Profile"):
            with st.spinner(f"Profiling {detail_sym}..."):
                profile = build_ticker_profile(detail_sym, verbose=False)

            st.json(profile.to_dict())

            # Timeline visualization
            if profile.equity_first_date and profile.options_first_date:
                st.subheader("Data Timeline")

                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt
                import matplotlib.dates as mdates

                fig, ax = plt.subplots(figsize=(12, 3))
                fig.patch.set_facecolor("#111")
                ax.set_facecolor("black")
                ax.tick_params(colors="white")
                for s in ax.spines.values():
                    s.set_color("#333")

                # Parse dates
                try:
                    eq_start = datetime.strptime(profile.equity_first_date, "%Y-%m-%d")
                    eq_end = datetime.strptime(profile.equity_last_date, "%Y-%m-%d")
                    opt_start = datetime.strptime(profile.options_first_date, "%Y-%m-%d")
                    opt_end = datetime.strptime(profile.options_last_date, "%Y-%m-%d")
                except ValueError:
                    eq_start = datetime.strptime(profile.equity_first_date, "%Y%m%d")
                    eq_end = datetime.strptime(profile.equity_last_date, "%Y%m%d")
                    opt_start = datetime.strptime(profile.options_first_date, "%Y%m%d")
                    opt_end = datetime.strptime(profile.options_last_date, "%Y%m%d")

                # Equity bar
                ax.barh(1, (eq_end - eq_start).days, left=eq_start,
                       color="#4ecdc4", alpha=0.8, height=0.6, label="Equity")
                # Options bar
                ax.barh(0, (opt_end - opt_start).days, left=opt_start,
                       color="#ff6b6b", alpha=0.8, height=0.6, label="Options")

                # Gap marker
                if profile.gap_days > 0:
                    ax.axvspan(eq_start, opt_start, alpha=0.15, color="yellow",
                              label=f"Pre-options gap ({profile.gap_days}d)")

                ax.set_yticks([0, 1])
                ax.set_yticklabels(["Options", "Equity"], color="white", fontsize=11)
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
                ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
                plt.xticks(rotation=45, color="white")
                ax.legend(facecolor="#222", edgecolor="#555", labelcolor="white", fontsize=8)
                ax.set_title(f"{detail_sym} — Data Coverage Timeline",
                           color="white", fontsize=13, fontweight="bold")
                fig.tight_layout()
                st.pyplot(fig)


# ============================================================================
# CLI Entry Point
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="IPO Origin Scanner")
    parser.add_argument("--mode", choices=["scan", "fetch", "profile", "app"], default="scan")
    parser.add_argument("--symbols", type=str, help="Comma-separated symbols")
    parser.add_argument("--symbol", type=str, default="ARM", help="Single symbol for fetch/profile")
    parser.add_argument("--max-days", type=int, default=500)
    args = parser.parse_args()

    if args.mode == "app":
        run_streamlit_app()
        return

    if not check_terminal():
        print("❌ Cannot connect to Theta Terminal. Ensure it's running on port 25503.")
        sys.exit(1)

    print("✅ Connected to Theta Terminal")

    if args.mode == "scan":
        symbols = args.symbols.split(",") if args.symbols else None
        profiles = scan_candidates(symbols)
        print_ranking(profiles)
        save_results(profiles)

    elif args.mode == "profile":
        profile = build_ticker_profile(args.symbol)
        print(json.dumps(profile.to_dict(), indent=2))

    elif args.mode == "fetch":
        result = fetch_genesis_data(args.symbol, max_equity_days=args.max_days, max_option_days=args.max_days)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
