#!/usr/bin/env python3
"""
Squeeze Mechanics Forensic: 5 Analyses of GME Jan 2021
=======================================================
Five independent analyses targeting the options-driven mechanism
behind the GME squeeze, going beyond simple call/put volume:

1. Strike Ladder Cascade — Sequential breakthrough of gamma walls
2. Implied Delta Exposure — Aggregate dealer delta-hedging obligations
3. Volume → Price Lead-Lag — Intraday options-to-equity causality
4. Strike Magnetism / Pin — Price pulled toward or repelled from OI clusters  
5. Failed Wall Forensic — The specific moment gamma containment broke

Usage:
    python squeeze_mechanics_forensic.py [--analysis 1|2|3|4|5|all]
"""

import argparse
import json
import sys
import warnings
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)

# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))

from phase5_paradigm import _load_options_day, _load_equity_day

THETA_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw" / "thetadata" / "trades"
POLYGON_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw" / "polygon" / "trades"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

TICKER = "GME"
PEAK_DATE = "2021-01-28"  # Intraday peak (hit $483)
PEAK_CLOSE_DATE = "2021-01-27"  # Highest closing price ($347.51)


def get_dates(ticker, data_type="options"):
    """Get sorted list of available dates."""
    root = THETA_ROOT if data_type == "options" else POLYGON_ROOT
    prefix = "root=" if data_type == "options" else "symbol="
    ticker_dir = root / f"{prefix}{ticker}"
    if not ticker_dir.exists():
        return []
    dirs = sorted(d.name.replace("date=", "") for d in ticker_dir.iterdir() if d.is_dir())
    return dirs


def get_equity_close(ticker, date_str):
    """Get closing price for a day."""
    try:
        eq = _load_equity_day(ticker, date_str)
        if eq.empty:
            return None
        return float(eq["eq_price"].iloc[-1])
    except Exception:
        return None


def get_equity_ohlc(ticker, date_str):
    """Get OHLC for a trading day."""
    try:
        eq = _load_equity_day(ticker, date_str)
        if eq.empty:
            return None
        return {
            "open": float(eq["eq_price"].iloc[0]),
            "high": float(eq["eq_price"].max()),
            "low": float(eq["eq_price"].min()),
            "close": float(eq["eq_price"].iloc[-1]),
        }
    except Exception:
        return None


# ===========================================================================
# Analysis 1: STRIKE LADDER CASCADE
# ===========================================================================
# Hypothesis: The squeeze was a sequential breakthrough of gamma walls.
# Each time price crossed a high-OI strike, dealers' hedging at the next
# strike created a staircase of forced buying.

def run_strike_ladder_cascade():
    """
    Track the sequential breakthrough of gamma walls during the GME squeeze.
    
    Method:
    - For each trading day in the buildup window, aggregate options volume by
      strike to identify the dominant gamma wall above price.
    - Track when price broke through each wall and measure the acceleration
      (was the move to the next wall faster than the previous?).
    - Identify the "cascade threshold" — the strike where breakthroughs became
      self-reinforcing.
    """
    print("\n" + "=" * 70)
    print("  ANALYSIS 1: STRIKE LADDER CASCADE")
    print("=" * 70)

    # Window: 60 trading days before peak to 10 after
    peak_dt = pd.Timestamp(PEAK_DATE)
    start_dt = peak_dt - timedelta(days=90)
    end_dt = peak_dt + timedelta(days=20)

    eq_dates = get_dates(TICKER, "equity")
    opts_dates = get_dates(TICKER, "options")

    # Convert to date string format
    eq_window = []
    for d in eq_dates:
        ds = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if "-" not in d else d
        dt = pd.Timestamp(ds)
        if start_dt <= dt <= end_dt:
            eq_window.append(ds)

    if not eq_window:
        print("  ⚠ No equity data found in window. Skipping strike ladder cascade.")
        return {"error": "no equity data in window", "window": f"{start_dt.date()} to {end_dt.date()}"}

    print(f"  Scanning {len(eq_window)} trading days ({eq_window[0]} → {eq_window[-1]})")

    # Build daily: price + top OI/volume strikes
    daily_data = []
    for i, date_str in enumerate(eq_window):
        ohlc = get_equity_ohlc(TICKER, date_str)
        if not ohlc:
            continue

        # Load options to find energy by strike
        date_key = date_str.replace("-", "")
        if date_key not in [d.replace("-", "") for d in opts_dates]:
            daily_data.append({
                "date": date_str, **ohlc,
                "walls": [], "call_vol_by_strike": {}, "put_vol_by_strike": {}
            })
            continue

        try:
            opts = _load_options_day(TICKER, date_str)
        except Exception:
            daily_data.append({
                "date": date_str, **ohlc,
                "walls": [], "call_vol_by_strike": {}, "put_vol_by_strike": {}
            })
            continue

        if opts.empty:
            daily_data.append({
                "date": date_str, **ohlc,
                "walls": [], "call_vol_by_strike": {}, "put_vol_by_strike": {}
            })
            continue

        # Aggregate volume by strike and right
        call_vol = defaultdict(int)
        put_vol = defaultdict(int)
        for _, row in opts.iterrows():
            strike = float(row["strike"])
            vol = int(row["size"])
            if row["right"] in ("C", "c"):
                call_vol[strike] += vol
            else:
                put_vol[strike] += vol

        # Find "gamma walls" = strikes with significant call volume above price
        price = ohlc["close"]
        walls_above = []
        for strike, vol in sorted(call_vol.items()):
            if strike > price and vol > 100:  # Minimum threshold
                walls_above.append({"strike": strike, "call_vol": vol,
                                     "put_vol": put_vol.get(strike, 0),
                                     "pct_above": round((strike - price) / price * 100, 1)})

        # Sort by volume (biggest walls first)
        walls_above.sort(key=lambda x: x["call_vol"], reverse=True)

        daily_data.append({
            "date": date_str,
            **ohlc,
            "walls": walls_above[:10],  # Top 10 walls
            "call_vol_by_strike": {str(k): v for k, v in sorted(call_vol.items())},
            "put_vol_by_strike": {str(k): v for k, v in sorted(put_vol.items())},
        })

        if (i + 1) % 10 == 0:
            print(f"    {i+1}/{len(eq_window)}", end="", flush=True)

    print()

    # === ANALYSIS: Track wall breakthroughs ===
    breakthroughs = []
    last_price = None
    tracked_walls = {}  # strike → date first appeared as wall

    for day in daily_data:
        price = day["close"]
        date = day["date"]

        # Register new walls
        for wall in day.get("walls", []):
            strike = wall["strike"]
            if strike not in tracked_walls:
                tracked_walls[strike] = {
                    "first_seen": date,
                    "first_seen_price": price,
                    "max_vol": wall["call_vol"],
                    "breached": False,
                    "breach_date": None,
                }
            else:
                tracked_walls[strike]["max_vol"] = max(
                    tracked_walls[strike]["max_vol"], wall["call_vol"]
                )

        # Check for breakthroughs
        if last_price is not None:
            for strike, info in tracked_walls.items():
                if not info["breached"] and last_price < strike <= price:
                    info["breached"] = True
                    info["breach_date"] = date
                    breakthroughs.append({
                        "date": date,
                        "strike_breached": strike,
                        "price_at_breach": price,
                        "first_seen": info["first_seen"],
                        "days_as_wall": (pd.Timestamp(date) - pd.Timestamp(info["first_seen"])).days,
                        "max_vol_at_wall": info["max_vol"],
                    })
                elif not info["breached"] and day["high"] >= strike > last_price:
                    # Intraday breach
                    info["breached"] = True
                    info["breach_date"] = date
                    breakthroughs.append({
                        "date": date,
                        "strike_breached": strike,
                        "price_at_breach": day["high"],
                        "first_seen": info["first_seen"],
                        "days_as_wall": (pd.Timestamp(date) - pd.Timestamp(info["first_seen"])).days,
                        "max_vol_at_wall": info["max_vol"],
                        "intraday": True,
                    })

        last_price = price

    # Measure cascade acceleration
    print("\n  STRIKE LADDER BREAKTHROUGHS:")
    print(f"  {'Date':<12} {'Strike':>8} {'Price':>8} {'Days Wall':>10} {'Call Vol':>10}")
    print("  " + "-" * 55)
    for bt in breakthroughs:
        print(f"  {bt['date']:<12} ${bt['strike_breached']:>7.0f} ${bt['price_at_breach']:>7.2f} "
              f"{bt['days_as_wall']:>8}d {bt['max_vol_at_wall']:>10,}")

    # Calculate time between breakthroughs
    if len(breakthroughs) > 1:
        intervals = []
        for i in range(1, len(breakthroughs)):
            days = (pd.Timestamp(breakthroughs[i]["date"]) -
                    pd.Timestamp(breakthroughs[i - 1]["date"])).days
            intervals.append({
                "from_strike": breakthroughs[i - 1]["strike_breached"],
                "to_strike": breakthroughs[i]["strike_breached"],
                "days": days,
            })

        print("\n  CASCADE ACCELERATION:")
        print(f"  {'From':>8} → {'To':>8}  {'Days':>5}  {'Trend':>8}")
        print("  " + "-" * 40)
        for iv in intervals:
            trend = "⚡ FASTER" if iv["days"] == 0 else ""
            print(f"  ${iv['from_strike']:>7.0f} → ${iv['to_strike']:>7.0f}  {iv['days']:>4}d  {trend}")

    return {
        "breakthroughs": breakthroughs,
        "daily_data_count": len(daily_data),
        "total_walls_tracked": len(tracked_walls),
    }


# ===========================================================================
# Analysis 2: IMPLIED DELTA EXPOSURE
# ===========================================================================
# Instead of counting contracts, estimate the aggregate delta dealers needed
# to hedge using a simplified Black-Scholes delta approximation.

def _bs_d1_vec(S, K, T, sigma, r=0.02):
    """Vectorized Black-Scholes d1."""
    S, K, T, sigma = np.asarray(S, float), np.asarray(K, float), np.asarray(T, float), np.asarray(sigma, float)
    safe_T = np.maximum(T, 1e-6)
    safe_sigma = np.maximum(sigma, 1e-6)
    return (np.log(S / K) + (r + 0.5 * safe_sigma**2) * safe_T) / (safe_sigma * np.sqrt(safe_T))


def _bs_delta_vec(S, K, T, sigma, is_call, r=0.02):
    """
    Vectorized Black-Scholes delta. All args are numpy arrays.
    is_call: boolean array (True=call, False=put)
    """
    K = np.asarray(K, float)
    T = np.asarray(T, float)
    sigma = np.asarray(sigma, float)
    is_call = np.asarray(is_call, bool)
    n = len(K)
    S = np.broadcast_to(np.asarray(S, float), n).copy()

    delta = np.zeros(n)

    # Expired options: binary delta
    expired = T <= 0
    if expired.any():
        exp_call = expired & is_call
        exp_put = expired & ~is_call
        delta[exp_call] = np.where(S[exp_call] >= K[exp_call], 1.0, 0.0)
        delta[exp_put] = np.where(S[exp_put] <= K[exp_put], -1.0, 0.0)

    # Active options: N(d1) for calls, N(d1)-1 for puts
    active = ~expired
    if active.any():
        d1 = _bs_d1_vec(S[active], K[active], T[active], sigma[active], r)
        nd1 = stats.norm.cdf(d1)
        # Build sub-mask: which of the active options are calls?
        active_is_call = is_call[active]
        active_delta = np.where(active_is_call, nd1, nd1 - 1.0)
        delta[active] = active_delta

    return delta


def _batch_iv_from_price(opt_prices, S, K, T, is_call, r=0.02, n_iter=10):
    """
    Vectorized IV solver using Newton's method on arrays.
    Much faster than scalar per-trade computation.
    Falls back to 0.5 for bad/missing data.
    """
    n = len(opt_prices)
    opt_prices = np.asarray(opt_prices, float)
    S = np.broadcast_to(np.asarray(S, float), n).copy()
    K = np.asarray(K, float)
    T = np.asarray(T, float)
    is_call = np.asarray(is_call, bool)

    # Initial guess: Brenner-Subrahmanyam
    safe_T = np.maximum(T, 0.001)
    sigma = opt_prices / np.maximum(S, 0.01) * np.sqrt(2 * np.pi / safe_T)
    sigma = np.clip(sigma, 0.05, 5.0)

    # Mask invalid entries
    valid = (opt_prices > 0) & (K > 0) & (T > 0) & (S > 0)

    for _ in range(n_iter):
        d1 = _bs_d1_vec(S, K, safe_T, sigma, r)
        d2 = d1 - sigma * np.sqrt(safe_T)

        # BS price
        model_call = S * stats.norm.cdf(d1) - K * np.exp(-r * safe_T) * stats.norm.cdf(d2)
        model_put = K * np.exp(-r * safe_T) * stats.norm.cdf(-d2) - S * stats.norm.cdf(-d1)
        model_price = np.where(is_call, model_call, model_put)

        # Vega
        vega = S * np.sqrt(safe_T) * stats.norm.pdf(d1)
        vega = np.maximum(vega, 1e-10)

        # Newton step
        diff = model_price - opt_prices
        update = valid & (np.abs(diff) > 1e-4)
        sigma[update] -= diff[update] / vega[update]
        sigma = np.clip(sigma, 0.01, 10.0)

    sigma[~valid] = 0.5
    return np.clip(sigma, 0.05, 5.0)


def _approx_delta(strike, price, right, dte_days):
    """
    Simplified delta approximation without volatility (LEGACY).
    Kept for comparison with BS delta.
    """
    if dte_days <= 0:
        if right in ("C", "c"):
            return 1.0 if price >= strike else 0.0
        else:
            return -1.0 if price <= strike else 0.0
    moneyness = (price - strike) / strike if right in ("C", "c") else (strike - price) / strike
    time_factor = max(1.0, 30.0 / max(dte_days, 1))
    z = np.clip(moneyness * time_factor * 5.0, -20, 20)
    delta = 1.0 / (1.0 + np.exp(-z))
    if right in ("P", "p"):
        delta = delta - 1.0
    return delta


def _approx_delta_vec(strikes, price, rights, dte_days):
    """Vectorized sigmoid delta for comparison."""
    strikes = np.asarray(strikes, float)
    dte = np.asarray(dte_days, float)
    is_call = np.array([r in ("C", "c") for r in rights])

    moneyness = np.where(is_call,
                         (price - strikes) / strikes,
                         (strikes - price) / strikes)
    time_factor = np.maximum(1.0, 30.0 / np.maximum(dte, 1))
    z = np.clip(moneyness * time_factor * 5.0, -20, 20)
    delta = 1.0 / (1.0 + np.exp(-z))
    delta = np.where(is_call, delta, delta - 1.0)

    # Handle expired
    expired = dte <= 0
    delta[expired & is_call] = np.where(price >= strikes[expired & is_call], 1.0, 0.0)
    delta[expired & ~is_call] = np.where(price <= strikes[expired & ~is_call], -1.0, 0.0)

    return delta


def run_implied_delta_exposure():
    """
    Build a time series of estimated dealer delta-hedging obligations.
    
    Key insight: A deep OTM call contributes ~0 delta, while an ATM call
    contributes ~0.5 delta per contract × 100 shares. This captures actual
    mechanical pressure regardless of call/put labels.
    
    Method:
    - For each trading day, load all options trades
    - Estimate combined delta using moneyness-based approximation  
    - Track how aggregate dealer delta shifted as price moved
    - A dealer who SOLD calls is SHORT delta (must buy shares to hedge)
    - A dealer who SOLD puts is LONG delta (must sell shares to hedge)
    
    Convention: We assume dealers are net SHORT options (the selling side).
    Positive dealer delta = dealers need to sell shares (bearish pressure)
    Negative dealer delta = dealers need to buy shares (bullish pressure)
    """
    print("\n" + "=" * 70)
    print("  ANALYSIS 2: IMPLIED DELTA EXPOSURE")
    print("=" * 70)

    peak_dt = pd.Timestamp(PEAK_DATE)
    start_dt = peak_dt - timedelta(days=90)
    end_dt = peak_dt + timedelta(days=20)

    opts_dates = get_dates(TICKER, "options")
    window_dates = []
    for d in opts_dates:
        ds = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        dt = pd.Timestamp(ds)
        if start_dt <= dt <= end_dt:
            window_dates.append(ds)

    print(f"  Scanning {len(window_dates)} trading days...")

    daily_delta = []
    for i, date_str in enumerate(window_dates):
        price = get_equity_close(TICKER, date_str)
        if not price:
            continue

        try:
            opts = _load_options_day(TICKER, date_str)
        except Exception:
            continue

        if opts.empty or "expiration" not in opts.columns:
            continue

        trade_dt = pd.Timestamp(date_str)

        # Filter valid options
        opts = opts[opts["expiration"].notna()].copy()
        opts["dte"] = (pd.to_datetime(opts["expiration"]) - trade_dt).dt.days
        opts = opts[opts["dte"] >= 0]

        if opts.empty:
            continue

        # Extract arrays for vectorized computation
        strikes = opts["strike"].values.astype(float)
        rights = opts["right"].values
        volumes = opts["size"].values.astype(int)
        opt_prices = opts["price"].values.astype(float) if "price" in opts.columns else np.zeros(len(opts))
        dte_days = opts["dte"].values.astype(float)
        T = np.maximum(dte_days / 365.0, 0.001)
        is_call = np.array([r in ("C", "c") for r in rights])

        # --- Vectorized BS Delta ---
        ivs = _batch_iv_from_price(opt_prices, price, strikes, T, is_call)
        bs_deltas = _bs_delta_vec(price, strikes, T, ivs, is_call)
        bs_delta_shares = bs_deltas * volumes * 100

        # --- Vectorized Sigmoid Delta (legacy comparison) ---
        sig_deltas = _approx_delta_vec(strikes, price, rights, dte_days)
        sig_delta_shares = sig_deltas * volumes * 100

        # --- Gamma ---
        gamma_factors = np.exp(-0.5 * ((price - strikes) / (price * 0.05)) ** 2)
        gamma_shares = gamma_factors * volumes * 100

        # Aggregate by call/put
        total_call_delta_shares = float(np.sum(bs_delta_shares[is_call]))
        total_put_delta_shares = float(np.sum(bs_delta_shares[~is_call]))
        total_call_delta_sigmoid = float(np.sum(sig_delta_shares[is_call]))
        total_put_delta_sigmoid = float(np.sum(sig_delta_shares[~is_call]))
        total_gamma_shares = float(np.sum(gamma_shares))

        # Volume classification
        call_moneyness = (price - strikes[is_call]) / price
        put_moneyness = (strikes[~is_call] - price) / price
        call_vols = volumes[is_call]
        put_vols = volumes[~is_call]

        itm_call_vol = int(np.sum(call_vols[call_moneyness > 0.05]))
        otm_call_vol = int(np.sum(call_vols[call_moneyness < -0.05]))
        atm_call_vol = int(np.sum(call_vols[(call_moneyness >= -0.05) & (call_moneyness <= 0.05)]))
        itm_put_vol = int(np.sum(put_vols[put_moneyness > 0.05]))
        otm_put_vol = int(np.sum(put_vols[put_moneyness < -0.05]))
        atm_put_vol = int(np.sum(put_vols[(put_moneyness >= -0.05) & (put_moneyness <= 0.05)]))
        atm_volume = atm_call_vol + atm_put_vol

        # Dealer convention: dealers are short options → their delta is opposite
        dealer_delta = -(total_call_delta_shares + total_put_delta_shares)
        dealer_delta_sigmoid = -(total_call_delta_sigmoid + total_put_delta_sigmoid)

        daily_delta.append({
            "date": date_str,
            "price": price,
            "days_to_peak": (peak_dt - trade_dt).days,
            "dealer_delta_shares": round(dealer_delta),
            "dealer_delta_sigmoid": round(dealer_delta_sigmoid),
            "call_delta_shares": round(total_call_delta_shares),
            "put_delta_shares": round(total_put_delta_shares),
            "gamma_shares": round(total_gamma_shares),
            "atm_volume": atm_volume,
            "otm_call_vol": otm_call_vol,
            "itm_call_vol": itm_call_vol,
            "otm_put_vol": otm_put_vol,
            "itm_put_vol": itm_put_vol,
        })

        if (i + 1) % 10 == 0:
            print(f"    {i+1}/{len(window_dates)}", end="", flush=True)

    print()

    # === DISPLAY ===
    print("\n  DEALER DELTA EXPOSURE TIMELINE (BS Delta | Sigmoid Comparison):")
    print(f"  {'Date':<12} {'Price':>7} {'T-Peak':>6} {'BS Dealer Δ':>14} "
          f"{'Sigmoid Δ':>14} {'Gamma':>12} {'ATM Vol':>8}")
    print("  " + "-" * 80)
    for dd in daily_delta[-30:]:
        bs_str = f"{dd['dealer_delta_shares']:>+14,}"
        sig_str = f"{dd['dealer_delta_sigmoid']:>+14,}"
        gamma_str = f"{dd['gamma_shares']:>12,}"
        print(f"  {dd['date']:<12} ${dd['price']:>6.2f} T-{dd['days_to_peak']:>3} "
              f"{bs_str} {sig_str} {gamma_str} {dd['atm_volume']:>8,}")

    # Key finding: When did dealer delta flip sign?
    if daily_delta:
        delta_sign_changes = []
        for i in range(1, len(daily_delta)):
            prev_d = daily_delta[i - 1]["dealer_delta_shares"]
            curr_d = daily_delta[i]["dealer_delta_shares"]
            if prev_d * curr_d < 0:
                delta_sign_changes.append({
                    "date": daily_delta[i]["date"],
                    "from": prev_d,
                    "to": curr_d,
                    "price": daily_delta[i]["price"],
                })

        if delta_sign_changes:
            print(f"\n  DEALER DELTA SIGN CHANGES: {len(delta_sign_changes)}")
            for sc in delta_sign_changes:
                direction = "LONG→SHORT" if sc["from"] > 0 else "SHORT→LONG"
                print(f"    {sc['date']} @ ${sc['price']:.2f}: {direction} "
                      f"({sc['from']:+,} → {sc['to']:+,})")

    return {"daily_delta": daily_delta}


# ===========================================================================
# Analysis 3: INTRADAY VOLUME → PRICE LEAD-LAG
# ===========================================================================
# Test whether options volume bursts at specific strikes PRECEDED equity
# price moves in the same direction.

def run_intraday_leadlag():
    """
    Test causality: did options volume at specific strikes precede equity
    price moves within the same day?
    
    Method:
    - For each day in the buildup window, bin both options and equity into
      5-minute intervals
    - For each 5-min bin's options activity, measure the dominant strike
      direction (are people buying above or below current price?)
    - Correlate lagged options direction with subsequent equity price change
    - A positive correlation at lag +1 to +3 bins = options LEAD price
    """
    print("\n" + "=" * 70)
    print("  ANALYSIS 3: INTRADAY VOLUME → PRICE LEAD-LAG")
    print("=" * 70)

    peak_dt = pd.Timestamp(PEAK_DATE)
    start_dt = peak_dt - timedelta(days=30)

    opts_dates = get_dates(TICKER, "options")
    eq_dates = get_dates(TICKER, "equity")

    # Find overlap dates
    opts_set = set(d.replace("-", "") for d in opts_dates)
    eq_set = set(d.replace("-", "") for d in eq_dates)

    window_dates = []
    for d in sorted(opts_set & eq_set):
        ds = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        dt = pd.Timestamp(ds)
        if start_dt <= dt <= peak_dt:
            window_dates.append(ds)

    print(f"  Scanning {len(window_dates)} trading days (last 30 before peak)...")

    all_lead_lags = []
    daily_causality = []

    for date_str in window_dates:
        try:
            opts = _load_options_day(TICKER, date_str)
            eq = _load_equity_day(TICKER, date_str)
        except Exception:
            continue

        if opts.empty or eq.empty:
            continue

        # Bin into 5-minute intervals
        bin_size = "5min"
        eq["bin"] = eq["ts"].dt.floor(bin_size)
        opts["bin"] = opts["ts"].dt.floor(bin_size)

        # Equity: compute price return per bin
        eq_binned = eq.groupby("bin").agg(
            eq_price=("eq_price", "last"),
            eq_volume=("eq_size", "sum"),
        ).reset_index()
        eq_binned["eq_return"] = eq_binned["eq_price"].pct_change()

        # Get current price at each bin for moneyness
        price_at_bin = eq_binned.set_index("bin")["eq_price"].to_dict()

        # Options: compute "pressure direction" per bin
        # Positive = call-dominant buying above price (bullish)
        # Negative = put-dominant buying below price (bearish)
        opts_pressure = []
        for bin_time, grp in opts.groupby("bin"):
            current_price = price_at_bin.get(bin_time)
            if current_price is None:
                continue

            bull_pressure = 0
            bear_pressure = 0
            for _, row in grp.iterrows():
                strike = float(row["strike"])
                volume = int(row["size"])
                right = row["right"]

                if right in ("C", "c") and strike >= current_price:
                    # Buying OTM calls = bullish
                    bull_pressure += volume
                elif right in ("P", "p") and strike <= current_price:
                    # Buying OTM puts = bearish
                    bear_pressure += volume
                elif right in ("C", "c") and strike < current_price:
                    # Buying ITM calls = moderate bullish
                    bull_pressure += volume * 0.5
                elif right in ("P", "p") and strike > current_price:
                    # Buying ITM puts = moderate bearish
                    bear_pressure += volume * 0.5

            net = bull_pressure - bear_pressure
            opts_pressure.append({"bin": bin_time, "net_pressure": net,
                                   "total_vol": int(grp["size"].sum())})

        if not opts_pressure:
            continue

        opts_df = pd.DataFrame(opts_pressure).set_index("bin")
        eq_df = eq_binned.set_index("bin")

        # Merge and compute lead-lag correlation
        merged = opts_df.join(eq_df, how="inner")
        if len(merged) < 10:
            continue

        # Test: does options pressure at time T predict equity return at T+1, T+2, T+3?
        day_lags = {}
        for lag in range(0, 6):
            pressure = merged["net_pressure"].values
            returns = merged["eq_return"].shift(-lag).values

            # Remove NaN
            valid = ~np.isnan(returns)
            if valid.sum() < 5:
                continue

            corr, pval = stats.pearsonr(pressure[valid], returns[valid])
            day_lags[lag] = {"corr": round(corr, 4), "pval": round(pval, 4)}

        daily_causality.append({
            "date": date_str,
            "n_bins": len(merged),
            "lags": day_lags,
            "mean_pressure": float(merged["net_pressure"].mean()),
        })

    # Aggregate lag results across all days
    print(f"\n  LEAD-LAG RESULTS ({len(daily_causality)} days analyzed):")
    print(f"\n  {'Lag':>4} {'Mean Corr':>10} {'Median Corr':>12} {'% Positive':>11} {'% p<0.05':>9}")
    print("  " + "-" * 50)

    aggregate_lags = {}
    for lag in range(0, 6):
        corrs = [d["lags"][lag]["corr"] for d in daily_causality if lag in d["lags"]]
        pvals = [d["lags"][lag]["pval"] for d in daily_causality if lag in d["lags"]]
        if not corrs:
            continue
        aggregate_lags[lag] = {
            "mean_corr": round(np.mean(corrs), 4),
            "median_corr": round(np.median(corrs), 4),
            "pct_positive": round(np.mean([c > 0 for c in corrs]) * 100, 1),
            "pct_significant": round(np.mean([p < 0.05 for p in pvals]) * 100, 1),
            "n_days": len(corrs),
        }
        al = aggregate_lags[lag]
        lag_label = f"T+{lag}" if lag > 0 else "T+0"
        flag = " ← SAME-BIN" if lag == 0 else (" ← PREDICTIVE" if lag == 1 else "")
        print(f"  {lag_label:>4} {al['mean_corr']:>+10.4f} {al['median_corr']:>+12.4f} "
              f"{al['pct_positive']:>10.1f}% {al['pct_significant']:>8.1f}%{flag}")

    return {"daily_causality": daily_causality, "aggregate_lags": aggregate_lags}


# ===========================================================================
# Analysis 4: STRIKE MAGNETISM / PIN ANALYSIS
# ===========================================================================
# Test whether price was pulled TOWARD high-OI strikes (pin risk) during
# the buildup, and whether that magnetism broke down at the squeeze.

def run_strike_magnetism():
    """
    Track strike magnetism: was price pulled toward high-volume strikes?
    
    Method:
    - For each day, identify the "dominant strike" (highest total options volume)
    - Measure price distance from dominant strike at close
    - Track whether price converged toward dominant strikes (magnetism) or
      diverged (repulsion) during the buildup vs squeeze phase
    """
    print("\n" + "=" * 70)
    print("  ANALYSIS 4: STRIKE MAGNETISM / PIN ANALYSIS")
    print("=" * 70)

    peak_dt = pd.Timestamp(PEAK_DATE)
    start_dt = peak_dt - timedelta(days=180)
    end_dt = peak_dt + timedelta(days=30)

    opts_dates = get_dates(TICKER, "options")
    window_dates = []
    for d in opts_dates:
        ds = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        dt = pd.Timestamp(ds)
        if start_dt <= dt <= end_dt:
            window_dates.append(ds)

    print(f"  Scanning {len(window_dates)} trading days...")

    daily_magnetism = []
    for i, date_str in enumerate(window_dates):
        price = get_equity_close(TICKER, date_str)
        if not price:
            continue

        try:
            opts = _load_options_day(TICKER, date_str)
        except Exception:
            continue

        if opts.empty:
            continue

        # Find dominant strikes by total volume
        strike_vol = defaultdict(int)
        strike_call_vol = defaultdict(int)
        strike_put_vol = defaultdict(int)
        for _, row in opts.iterrows():
            strike = float(row["strike"])
            vol = int(row["size"])
            strike_vol[strike] += vol
            if row["right"] in ("C", "c"):
                strike_call_vol[strike] += vol
            else:
                strike_put_vol[strike] += vol

        if not strike_vol:
            continue

        # Top 3 strikes by volume
        sorted_strikes = sorted(strike_vol.items(), key=lambda x: x[1], reverse=True)
        top_strike = sorted_strikes[0][0]
        top_vol = sorted_strikes[0][1]

        # Nearest round strike above and below price
        all_strikes_near = [s for s in strike_vol.keys()
                            if abs(s - price) / price < 0.2]  # Within 20%
        nearest_above = min([s for s in all_strikes_near if s >= price], default=None)
        nearest_below = max([s for s in all_strikes_near if s < price], default=None)

        # Pin score: how close to the dominant strike? (0 = exactly at strike)
        pin_distance = abs(price - top_strike) / price * 100

        # Friday flag for expiration pin
        day_of_week = pd.Timestamp(date_str).dayofweek  # 0=Mon, 4=Fri

        daily_magnetism.append({
            "date": date_str,
            "price": round(price, 2),
            "days_to_peak": (peak_dt - pd.Timestamp(date_str)).days,
            "top_strike": top_strike,
            "top_vol": top_vol,
            "pin_distance_pct": round(pin_distance, 2),
            "nearest_above": nearest_above,
            "nearest_below": nearest_below,
            "is_friday": day_of_week == 4,
            "n_active_strikes": len(all_strikes_near),
            "call_dom_ratio": round(
                sum(strike_call_vol.values()) / max(sum(strike_put_vol.values()), 1), 2
            ),
        })

        if (i + 1) % 20 == 0:
            print(f"    {i+1}/{len(window_dates)}", end="", flush=True)

    print()

    # === ANALYSIS: Magnetism vs phase ===
    # Split into phases: buildup (T-180 to T-30), trigger (T-30 to T-7), squeeze (T-7 to T+0)
    phases = {
        "buildup": [d for d in daily_magnetism if d["days_to_peak"] > 30],
        "trigger": [d for d in daily_magnetism if 7 < d["days_to_peak"] <= 30],
        "squeeze": [d for d in daily_magnetism if 0 <= d["days_to_peak"] <= 7],
        "post": [d for d in daily_magnetism if d["days_to_peak"] < 0],
    }

    print("\n  MAGNETISM BY PHASE:")
    print(f"  {'Phase':<12} {'N Days':>6} {'Mean Pin %':>10} {'Median Pin %':>12} {'Friday Pin':>10}")
    print("  " + "-" * 55)

    phase_stats = {}
    for phase_name, phase_data in phases.items():
        if not phase_data:
            continue
        pins = [d["pin_distance_pct"] for d in phase_data]
        friday_pins = [d["pin_distance_pct"] for d in phase_data if d["is_friday"]]
        phase_stats[phase_name] = {
            "n": len(pins),
            "mean_pin": round(np.mean(pins), 2),
            "median_pin": round(np.median(pins), 2),
            "friday_mean": round(np.mean(friday_pins), 2) if friday_pins else None,
        }
        ps = phase_stats[phase_name]
        fri = f"{ps['friday_mean']:.2f}%" if ps["friday_mean"] is not None else "   —"
        print(f"  {phase_name:<12} {ps['n']:>6} {ps['mean_pin']:>9.2f}% {ps['median_pin']:>11.2f}% {fri:>10}")

    # Look for the "magnetism break" — when did pin distance explode?
    print("\n  MAGNETISM BREAK — Price vs Top Strike (last 30 days):")
    print(f"  {'Date':<12} {'Price':>8} {'Top Strike':>10} {'Distance':>9} {'Vol':>10} {'Break?'}")
    print("  " + "-" * 60)
    for d in daily_magnetism[-30:]:
        distance = d["pin_distance_pct"]
        broken = " ⚡ BROKEN" if distance > 20 else ""
        print(f"  {d['date']:<12} ${d['price']:>7.2f} ${d['top_strike']:>8.0f} "
              f"{distance:>8.2f}% {d['top_vol']:>10,}{broken}")

    return {
        "daily_magnetism": daily_magnetism,
        "phase_stats": phase_stats,
    }


# ===========================================================================
# Analysis 5: FAILED WALL FORENSIC
# ===========================================================================
# Identify the exact day and strike where gamma containment broke — when
# price punched through a wall that had previously held.

def run_failed_wall_forensic():
    """
    Identify the specific gamma wall failure that triggered the squeeze.
    
    Method:
    - Build rolling gamma topography over 90 days before peak
    - For each day, identify the dominant call energy wall above price
    - Track "wall test" events (price approaching within N% of a wall)
    - Distinguish "held" (price reversed) vs "failed" (price broke through)
    - Analyze what was different about the flow on the day the wall failed
    """
    print("\n" + "=" * 70)
    print("  ANALYSIS 5: FAILED WALL FORENSIC")
    print("=" * 70)

    peak_dt = pd.Timestamp(PEAK_DATE)
    start_dt = peak_dt - timedelta(days=90)
    end_dt = peak_dt + timedelta(days=5)

    opts_dates = get_dates(TICKER, "options")
    eq_dates = get_dates(TICKER, "equity")

    # Get overlap dates
    opts_set = set(d.replace("-", "") for d in opts_dates)
    eq_set = set(d.replace("-", "") for d in eq_dates)

    window_dates = []
    for d in sorted(opts_set & eq_set):
        ds = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        dt = pd.Timestamp(ds)
        if start_dt <= dt <= end_dt:
            window_dates.append(ds)

    print(f"  Scanning {len(window_dates)} trading days...")

    # Build daily walls and test events
    daily_walls = []

    for i, date_str in enumerate(window_dates):
        ohlc = get_equity_ohlc(TICKER, date_str)
        if not ohlc:
            continue

        try:
            opts = _load_options_day(TICKER, date_str)
        except Exception:
            continue

        if opts.empty:
            continue

        price = ohlc["close"]

        # Build gamma energy map (aggregate volume × sqrt(DTE))
        strike_energy = defaultdict(lambda: {"call": 0, "put": 0, "total": 0})
        for _, row in opts.iterrows():
            strike = float(row["strike"])
            vol = int(row["size"])
            right = row["right"]

            if "expiration" in opts.columns and pd.notna(row.get("expiration")):
                exp_dt = pd.Timestamp(row["expiration"])
                dte = max((exp_dt - pd.Timestamp(date_str)).days, 1)
            else:
                dte = 30  # default

            energy = vol * np.sqrt(dte)

            if right in ("C", "c"):
                strike_energy[strike]["call"] += energy
                strike_energy[strike]["total"] += energy
            else:
                strike_energy[strike]["put"] += energy
                strike_energy[strike]["total"] += energy

        # Identify walls above and below price
        walls_above = []
        walls_below = []
        for strike, energies in strike_energy.items():
            if energies["total"] < 100:  # Minimum energy threshold
                continue
            if strike > price:
                walls_above.append({
                    "strike": strike,
                    "total_energy": energies["total"],
                    "call_energy": energies["call"],
                    "put_energy": energies["put"],
                    "pct_above": round((strike - price) / price * 100, 1),
                })
            elif strike < price:
                walls_below.append({
                    "strike": strike,
                    "total_energy": energies["total"],
                    "call_energy": energies["call"],
                    "put_energy": energies["put"],
                    "pct_below": round((price - strike) / price * 100, 1),
                })

        # Sort by energy
        walls_above.sort(key=lambda x: x["total_energy"], reverse=True)
        walls_below.sort(key=lambda x: x["total_energy"], reverse=True)

        # Dominant wall = highest energy above price
        dom_wall = walls_above[0] if walls_above else None

        # Check if price tested the dominant wall today
        wall_test = None
        if dom_wall:
            wall_strike = dom_wall["strike"]
            approach_pct = (wall_strike - ohlc["high"]) / wall_strike * 100
            if approach_pct < 3:  # Within 3% of the wall
                wall_test = {
                    "strike": wall_strike,
                    "approach_pct": round(approach_pct, 2),
                    "breached": ohlc["high"] >= wall_strike,
                    "closed_above": ohlc["close"] >= wall_strike,
                }

        daily_walls.append({
            "date": date_str,
            **ohlc,
            "dominant_wall": dom_wall,
            "n_walls_above": len(walls_above),
            "n_walls_below": len(walls_below),
            "wall_test": wall_test,
            "top_3_walls": [w["strike"] for w in walls_above[:3]],
            "total_call_energy": sum(w["call_energy"] for w in walls_above + walls_below),
            "total_put_energy": sum(w["put_energy"] for w in walls_above + walls_below),
        })

        if (i + 1) % 10 == 0:
            print(f"    {i+1}/{len(window_dates)}", end="", flush=True)

    print()

    # === ANALYSIS: Wall tests and failures ===
    wall_tests = [d for d in daily_walls if d["wall_test"] is not None]
    failures = [d for d in wall_tests if d["wall_test"]["breached"]]
    holds = [d for d in wall_tests if not d["wall_test"]["breached"]]

    print(f"\n  WALL TEST SUMMARY:")
    print(f"    Total wall tests: {len(wall_tests)}")
    print(f"    Walls held:       {len(holds)} ({len(holds)/max(len(wall_tests),1)*100:.0f}%)")
    print(f"    Walls breached:   {len(failures)} ({len(failures)/max(len(wall_tests),1)*100:.0f}%)")

    print(f"\n  WALL TEST EVENTS:")
    print(f"  {'Date':<12} {'Close':>7} {'Wall':>7} {'Approach':>9} {'Result':>10} {'Energy':>10}")
    print("  " + "-" * 60)
    for wt in wall_tests:
        test = wt["wall_test"]
        result = "🔴 BREACH" if test["breached"] else "🟢 HELD"
        wall_energy = wt["dominant_wall"]["total_energy"] if wt["dominant_wall"] else 0
        print(f"  {wt['date']:<12} ${wt['close']:>6.2f} ${test['strike']:>6.0f} "
              f"{test['approach_pct']:>+8.2f}% {result:>10} {wall_energy:>10,.0f}")

    # Identify THE critical failure — the first breach that wasn't recovered
    print("\n  CRITICAL FAILURE ANALYSIS:")
    for fail in failures:
        test = fail["wall_test"]
        # Look at the next day: did price stay above the wall?
        fail_idx = daily_walls.index(fail)
        if fail_idx + 1 < len(daily_walls):
            next_day = daily_walls[fail_idx + 1]
            stayed = next_day["close"] >= test["strike"]
            recovery = "NO RECOVERY — CASCADE INITIATED" if stayed else "Recovered below wall"
        else:
            recovery = "Last day in window"

        # Compare energy on breach day vs hold days
        fail_energy = fail["total_call_energy"]
        hold_energies = [h["total_call_energy"] for h in holds] if holds else [0]
        energy_vs_avg = fail_energy / max(np.mean(hold_energies), 1)

        print(f"\n    Date: {fail['date']}")
        print(f"    Wall: ${test['strike']:.0f}")
        print(f"    Price: ${fail['low']:.2f} – ${fail['high']:.2f} (closed ${fail['close']:.2f})")
        print(f"    Call energy: {fail_energy:,.0f} (vs hold avg: {np.mean(hold_energies):,.0f} = {energy_vs_avg:.1f}×)")
        print(f"    Next day: {recovery}")

    return {
        "daily_walls": [{
            "date": d["date"], "close": d["close"], "high": d["high"], "low": d["low"],
            "dominant_wall": d["dominant_wall"],
            "wall_test": d["wall_test"],
            "total_call_energy": d["total_call_energy"],
        } for d in daily_walls],
        "n_tests": len(wall_tests),
        "n_holds": len(holds),
        "n_failures": len(failures),
    }


# ===========================================================================
# Orchestrator
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="GME Squeeze Mechanics Forensic")
    parser.add_argument("--analysis", type=str, default="all",
                        help="Which analysis to run: 1-5 or 'all'")
    args = parser.parse_args()

    results = {}
    analyses = {
        "1": ("strike_ladder_cascade", run_strike_ladder_cascade),
        "2": ("implied_delta_exposure", run_implied_delta_exposure),
        "3": ("intraday_leadlag", run_intraday_leadlag),
        "4": ("strike_magnetism", run_strike_magnetism),
        "5": ("failed_wall_forensic", run_failed_wall_forensic),
    }

    if args.analysis == "all":
        to_run = list(analyses.values())
    else:
        nums = [n.strip() for n in args.analysis.split(",")]
        to_run = [analyses[n] for n in nums if n in analyses]

    for name, func in to_run:
        try:
            results[name] = func()
        except Exception as e:
            print(f"\n  ⚠ Analysis {name} failed: {e}")
            # Print traceback with scrubbed paths (no absolute user paths)
            import traceback, re
            tb_text = traceback.format_exc()
            tb_text = re.sub(r'"/.+?/review_package/', '"review_package/', tb_text)
            print(tb_text)
            results[name] = {"error": str(e)}

    # Save results
    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean(v) for v in obj]
        elif isinstance(obj, (np.bool_,)):
            return bool(obj)
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (pd.Timestamp,)):
            return str(obj)
        return obj

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"squeeze_mechanics_GME_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(clean(results), f, indent=2, default=str)
    print(f"\n  Results saved to: {out_path.name}")


if __name__ == "__main__":
    main()
