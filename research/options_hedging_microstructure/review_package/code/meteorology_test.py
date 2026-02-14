#!/usr/bin/env python3
"""
Microstructure Meteorology: Predictive Flow Modeling
====================================================
Treats the options chain as a topographic pressure system — with Long Gamma
zones as high-pressure systems and Short Gamma gaps as low-pressure troughs —
and tests whether this "weather map" can predict the direction/magnitude of
next-day equity price movement.

Tests:
  1. Gamma Topography — build cross-sectional net gamma energy maps by strike
  2. Pressure Gradient — identify gamma walls (resistance) and troughs (acceleration)
  3. Flow Prediction — predict next-day price direction from pressure gradients
  4. Memory Horizon — determine minimum lookback needed (6/12/18/24/36 months)

Usage:
    python meteorology_test.py --ticker GME
    python meteorology_test.py --ticker TSLA --lookback 12
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

warnings.filterwarnings("ignore", category=FutureWarning)

# ---------------------------------------------------------------------------
# Infrastructure imports
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "phase98_cluster_bridge"))

from panel_scan import POLYGON_DIR
try:
    from temporal_convolution_engine import load_equity_day
except ImportError:
    from panel_scan import load_equity_day  # type: ignore

from phase5_paradigm import _load_options_day

THETA_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw" / "thetadata" / "trades"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ===========================================================================
# Helpers
# ===========================================================================

def get_equity_dates(ticker: str) -> list[str]:
    """Get equity dates as YYYY-MM-DD sorted."""
    for prefix in [f"symbol={ticker}", f"symbol={ticker.upper()}"]:
        sym_path = POLYGON_DIR / prefix
        if sym_path.exists():
            return sorted(d.name.split("=")[1] for d in sym_path.glob("date=*"))
    return []


def get_options_dates(ticker: str) -> list[str]:
    """Get options dates as YYYYMMDD sorted."""
    opts_dir = THETA_ROOT / f"root={ticker}"
    if not opts_dir.exists():
        return []
    return sorted(d.name.replace("date=", "") for d in opts_dir.iterdir() if d.is_dir())


def get_overlap_dates(ticker: str) -> list[str]:
    """Dates with both equity + options data, as YYYY-MM-DD."""
    eq = set(get_equity_dates(ticker))
    opts_raw = get_options_dates(ticker)
    opts = {f"{d[:4]}-{d[4:6]}-{d[6:8]}" for d in opts_raw if len(d) == 8}
    return sorted(eq & opts)


def get_daily_close(ticker: str, date_str: str) -> float | None:
    """Get the closing price for a trading day."""
    eq = load_equity_day(ticker, date_str)
    if eq.empty:
        return None
    return float(eq["price"].iloc[-1])


# ===========================================================================
# Step 1: Gamma Topography Map
# ===========================================================================

def build_gamma_topography(
    ticker: str, date_str: str, lookback_days: int = 30
) -> dict | None:
    """
    Build a cross-sectional "weather map" of gamma energy by strike.

    Since we don't have true OI or Greeks, we approximate gamma exposure using:
      energy(K) = Σ (volume × DTE_remaining) for each strike K

    This gives a topographic map where:
    - High energy zones → "high pressure" (dealer gamma walls, price resistance)
    - Low energy zones → "low pressure" (gamma troughs, price acceleration)

    We also split by right (put vs call) to infer directionality:
    - Put-heavy strikes → dealer likely long gamma (bought from hedgers)
    - Call-heavy strikes → ambiguous, but if short-DTE → likely retail-spec
    """
    target_dt = pd.Timestamp(date_str)
    start_dt = target_dt - timedelta(days=lookback_days + 15)

    # Get all options data in the lookback window
    opts_dates = get_options_dates(ticker)
    window_dates = []
    for d in opts_dates:
        dt = pd.Timestamp(f"{d[:4]}-{d[4:6]}-{d[6:8]}")
        if start_dt <= dt <= target_dt:
            window_dates.append(f"{d[:4]}-{d[4:6]}-{d[6:8]}")

    if len(window_dates) < 5:
        return None

    # Get current price
    current_price = get_daily_close(ticker, date_str)
    if current_price is None or current_price <= 0:
        return None

    # Accumulate energy by strike
    strike_energy = defaultdict(lambda: {"call_energy": 0.0, "put_energy": 0.0,
                                         "call_volume": 0, "put_volume": 0,
                                         "total_energy": 0.0})

    for trade_date in window_dates:
        try:
            opts = _load_options_day(ticker, trade_date)
        except (FileNotFoundError, Exception):
            continue

        if opts.empty or "expiration" not in opts.columns:
            continue

        # Vectorized: compute DTE remaining for all rows at once
        exp_dts = pd.to_datetime(opts["expiration"])
        dte_remaining = (exp_dts - target_dt).dt.days
        mask = dte_remaining > 0

        if not mask.any():
            continue

        valid = opts[mask].copy()
        valid_dte = dte_remaining[mask].values

        # Energy = volume × sqrt(DTE remaining)
        energy = valid["size"].values * np.sqrt(valid_dte)
        strikes_arr = valid["strike"].values.astype(float)
        rights_arr = valid["right"].values

        is_call = np.isin(rights_arr, ["C", "c"])
        is_put = np.isin(rights_arr, ["P", "p"])

        # Aggregate using a DataFrame for speed
        agg_df = pd.DataFrame({
            "strike": strikes_arr,
            "energy": energy,
            "volume": valid["size"].values,
            "is_call": is_call,
            "is_put": is_put,
        })
        agg_df["call_energy"] = agg_df["energy"] * agg_df["is_call"]
        agg_df["put_energy"] = agg_df["energy"] * agg_df["is_put"]
        agg_df["call_volume"] = agg_df["volume"] * agg_df["is_call"]
        agg_df["put_volume"] = agg_df["volume"] * agg_df["is_put"]

        grouped = agg_df.groupby("strike").agg(
            total_energy=("energy", "sum"),
            call_energy=("call_energy", "sum"),
            put_energy=("put_energy", "sum"),
            call_volume=("call_volume", "sum"),
            put_volume=("put_volume", "sum"),
        )

        for strike_val, row in grouped.iterrows():
            strike_energy[strike_val]["total_energy"] += row["total_energy"]
            strike_energy[strike_val]["call_energy"] += row["call_energy"]
            strike_energy[strike_val]["put_energy"] += row["put_energy"]
            strike_energy[strike_val]["call_volume"] += int(row["call_volume"])
            strike_energy[strike_val]["put_volume"] += int(row["put_volume"])

    if not strike_energy:
        return None

    # Build sorted topography
    strikes = sorted(strike_energy.keys())
    topo = {
        "date": date_str,
        "current_price": current_price,
        "n_strikes": len(strikes),
        "strikes": [],
    }

    for k in strikes:
        se = strike_energy[k]
        moneyness = (k - current_price) / current_price * 100  # % from spot
        topo["strikes"].append({
            "strike": k,
            "moneyness_pct": round(moneyness, 2),
            "total_energy": round(se["total_energy"], 1),
            "call_energy": round(se["call_energy"], 1),
            "put_energy": round(se["put_energy"], 1),
            "call_volume": se["call_volume"],
            "put_volume": se["put_volume"],
            "net_energy": round(se["put_energy"] - se["call_energy"], 1),  # positive = more puts (dealer long gamma)
        })

    return topo


# ===========================================================================
# Step 2: Pressure Gradient & Flow Prediction
# ===========================================================================

def compute_pressure_gradient(topo: dict) -> dict:
    """
    Analyze the gamma topography to find:
    - Gamma Walls: high-energy strikes near current price (resistance zones)
    - Gamma Troughs: low-energy gaps near current price (acceleration zones)
    - Predicted flow direction: toward the nearest trough, away from walls
    """
    price = topo["current_price"]
    strikes = topo["strikes"]

    if not strikes:
        return {"direction": 0, "confidence": 0, "walls": [], "troughs": []}

    # Filter to ±20% of current price (relevant zone)
    nearby = [s for s in strikes if abs(s["moneyness_pct"]) <= 20]
    if len(nearby) < 3:
        nearby = strikes  # use everything if too sparse

    # Split into above and below
    above = [s for s in nearby if s["strike"] > price]
    below = [s for s in nearby if s["strike"] <= price]

    # Calculate total energy above and below price
    energy_above = sum(s["total_energy"] for s in above) if above else 0
    energy_below = sum(s["total_energy"] for s in below) if below else 0
    total_energy = energy_above + energy_below

    if total_energy < 1:
        return {"direction": 0, "confidence": 0, "walls": [], "troughs": []}

    # Energy imbalance: more energy above → price pushed down (resistance above)
    energy_ratio = energy_above / (energy_below + 1e-10)

    # Identify walls (top energy concentrations within ±10%)
    near_10 = sorted(
        [s for s in nearby if abs(s["moneyness_pct"]) <= 10],
        key=lambda s: -s["total_energy"]
    )
    walls = near_10[:3] if near_10 else []

    # Identify troughs (lowest energy gaps within ±10%)
    troughs = sorted(
        [s for s in nearby if abs(s["moneyness_pct"]) <= 10],
        key=lambda s: s["total_energy"]
    )[:3] if near_10 else []

    # Net put energy bias (positive = more puts = more dealer long gamma below)
    net_put_above = sum(s["net_energy"] for s in above)
    net_put_below = sum(s["net_energy"] for s in below)

    # Flow prediction:
    # If more energy above → price is "blocked" from going up → predicted DOWN
    # If more energy below → price is "supported" from going down → predicted UP
    # Direction: +1 = up, -1 = down, magnitude = confidence
    if energy_ratio > 1.5:
        direction = -1  # heavy resistance above, path of least resistance is down
        confidence = min(1.0, (energy_ratio - 1.0) / 3.0)
    elif energy_ratio < 0.67:
        direction = +1  # heavy support below, path of least resistance is up
        confidence = min(1.0, (1.0 / energy_ratio - 1.0) / 3.0)
    else:
        direction = 0
        confidence = 0.0

    # Nearest wall distance
    nearest_wall_above = min(
        (s["strike"] for s in walls if s["strike"] > price),
        default=price * 1.1
    )
    nearest_wall_below = max(
        (s["strike"] for s in walls if s["strike"] <= price),
        default=price * 0.9
    )

    return {
        "direction": direction,
        "confidence": round(confidence, 3),
        "energy_ratio_above_below": round(energy_ratio, 3),
        "energy_above": round(energy_above, 1),
        "energy_below": round(energy_below, 1),
        "nearest_wall_above": round(nearest_wall_above, 2),
        "nearest_wall_below": round(nearest_wall_below, 2),
        "wall_strikes": [{"strike": w["strike"], "energy": w["total_energy"]} for w in walls],
        "trough_strikes": [{"strike": t["strike"], "energy": t["total_energy"]} for t in troughs],
        "net_put_above": round(net_put_above, 1),
        "net_put_below": round(net_put_below, 1),
    }


# ===========================================================================
# Step 3: Backtest Flow Prediction
# ===========================================================================

def backtest_meteorology(
    ticker: str, lookback_months: int = 12, min_confidence: float = 0.05
) -> dict:
    """
    Rolling backtest: each day, build the gamma topography from trailing
    options data, predict next-day direction, and score accuracy.
    """
    overlap = get_overlap_dates(ticker)
    if len(overlap) < 60:
        return {"status": "INSUFFICIENT_DATA", "n_days": len(overlap)}

    lookback_days = lookback_months * 22  # approximate trading days

    predictions = []
    actuals = []
    confidences = []
    dates_tested = []

    print(f"  [{ticker}] Backtesting with {lookback_months}-month lookback ({len(overlap)} candidate days)...")

    # Start after enough history
    start_idx = max(30, lookback_days)
    test_dates = overlap[start_idx:]

    for i, date_str in enumerate(test_dates):
        if i > 0 and i % 50 == 0:
            hit_rate = np.mean(np.array(predictions[:i]) == np.array(actuals[:i])) * 100 if actuals else 0
            print(f"    Day {i}/{len(test_dates)} — hit rate so far: {hit_rate:.1f}%")

        # Build topography
        topo = build_gamma_topography(ticker, date_str, lookback_days=lookback_days)
        if topo is None:
            continue

        # Get pressure gradient and prediction
        gradient = compute_pressure_gradient(topo)
        pred_dir = gradient["direction"]
        confidence = gradient["confidence"]

        if pred_dir == 0 or confidence < min_confidence:
            continue  # skip neutral predictions

        # Get actual next-day return
        date_idx = overlap.index(date_str)
        if date_idx + 1 >= len(overlap):
            continue
        next_date = overlap[date_idx + 1]

        price_today = topo["current_price"]
        price_tomorrow = get_daily_close(ticker, next_date)
        if price_tomorrow is None:
            continue

        actual_return = (price_tomorrow - price_today) / price_today
        actual_dir = 1 if actual_return > 0 else (-1 if actual_return < 0 else 0)

        predictions.append(pred_dir)
        actuals.append(actual_dir)
        confidences.append(confidence)
        dates_tested.append(date_str)

    if len(predictions) < 20:
        return {"status": "INSUFFICIENT_PREDICTIONS", "n_predictions": len(predictions)}

    preds = np.array(predictions)
    acts = np.array(actuals)
    confs = np.array(confidences)

    # Accuracy metrics
    correct = preds == acts
    hit_rate = float(np.mean(correct)) * 100

    # Confidence-weighted accuracy
    weighted_hits = np.sum(correct * confs) / np.sum(confs) * 100

    # High-confidence subset
    high_conf_mask = confs > np.median(confs)
    high_conf_hits = float(np.mean(correct[high_conf_mask])) * 100 if high_conf_mask.sum() > 5 else None

    # Directional bias
    n_up_pred = int((preds > 0).sum())
    n_down_pred = int((preds < 0).sum())
    n_up_actual = int((acts > 0).sum())

    # Net value: if we traded every prediction, what's the expected edge?
    # (correct predictions get +1, wrong get -1, scaled by confidence)
    net_edge = float(np.mean(np.where(correct, confs, -confs)))

    return {
        "status": "OK",
        "lookback_months": lookback_months,
        "n_predictions": len(predictions),
        "n_days_tested": len(test_dates),
        "prediction_rate": round(len(predictions) / len(test_dates) * 100, 1),
        "hit_rate": round(hit_rate, 1),
        "weighted_hit_rate": round(weighted_hits, 1),
        "high_confidence_hit_rate": round(high_conf_hits, 1) if high_conf_hits else None,
        "random_baseline": 50.0,
        "edge_over_random": round(hit_rate - 50.0, 1),
        "net_edge": round(net_edge, 4),
        "n_up_predictions": n_up_pred,
        "n_down_predictions": n_down_pred,
        "actual_up_pct": round(n_up_actual / len(acts) * 100, 1),
        "mean_confidence": round(float(np.mean(confs)), 3),
        "median_confidence": round(float(np.median(confs)), 3),
    }


# ===========================================================================
# Step 4: Memory Horizon Test
# ===========================================================================

def test_memory_horizon(ticker: str) -> dict:
    """
    Test predictive accuracy across different lookback windows to determine
    the minimum history needed for accurate "weather maps."
    """
    windows = [3, 6, 12, 18, 24]

    # Check available date range to determine which windows are feasible
    overlap = get_overlap_dates(ticker)
    if not overlap:
        return {"status": "NO_DATA"}

    first_date = pd.Timestamp(overlap[0])
    last_date = pd.Timestamp(overlap[-1])
    total_months = (last_date - first_date).days / 30

    # Only test windows that leave at least 60 days for backtesting
    feasible_windows = [w for w in windows if w * 30 + 60 < (last_date - first_date).days]
    if not feasible_windows:
        return {"status": "INSUFFICIENT_DATA", "total_months": round(total_months, 1)}

    print(f"\n{'─'*70}")
    print(f"  MEMORY HORIZON TEST — {ticker}")
    print(f"  Data span: {overlap[0]} → {overlap[-1]} ({total_months:.0f} months)")
    print(f"  Testing windows: {feasible_windows}")
    print(f"{'─'*70}")

    results = {}
    for window in feasible_windows:
        print(f"\n  Window: {window} months")
        bt = backtest_meteorology(ticker, lookback_months=window, min_confidence=0.05)
        results[f"{window}m"] = bt

        if bt["status"] == "OK":
            edge = bt["edge_over_random"]
            marker = "✓" if edge > 0 else "✗"
            print(f"    {marker} Hit rate: {bt['hit_rate']:.1f}%  "
                  f"(edge: {edge:+.1f}pp)  "
                  f"n={bt['n_predictions']}")
        else:
            print(f"    — {bt['status']}")

    # Find optimal window
    ok_results = {k: v for k, v in results.items() if v.get("status") == "OK"}
    if ok_results:
        best_window = max(ok_results, key=lambda k: ok_results[k]["hit_rate"])
        best_hit = ok_results[best_window]["hit_rate"]
        print(f"\n  Best window: {best_window} (hit rate: {best_hit:.1f}%)")

        # Check if accuracy plateaus
        sorted_windows = sorted(ok_results.items(), key=lambda x: int(x[0].replace("m", "")))
        if len(sorted_windows) >= 3:
            rates = [v["hit_rate"] for _, v in sorted_windows]
            # Check if the improvement from 2nd-to-last to last is < 1%
            improvement = rates[-1] - rates[-2]
            plateau_window = sorted_windows[-2][0] if improvement < 1.0 else sorted_windows[-1][0]
            print(f"  Plateau detected at: {plateau_window}")

    return {
        "status": "OK",
        "total_months": round(total_months, 1),
        "windows_tested": feasible_windows,
        "results": results,
    }


# ===========================================================================
# Orchestrator
# ===========================================================================

def run_meteorology_test(ticker: str, lookback: int = 12) -> dict:
    """Run the complete meteorology test for one ticker."""
    print(f"\n{'='*70}")
    print(f"MICROSTRUCTURE METEOROLOGY — {ticker}")
    print(f"{'='*70}")

    # Step 1: Build a sample topography to validate
    overlap = get_overlap_dates(ticker)
    if len(overlap) < 30:
        return {"ticker": ticker, "status": "INSUFFICIENT_DATA"}

    sample_date = overlap[-1]  # most recent date
    print(f"\n  Building sample topography for {sample_date}...")
    topo = build_gamma_topography(ticker, sample_date, lookback_days=lookback * 22)

    if topo is None:
        return {"ticker": ticker, "status": "TOPO_FAILED"}

    # Show topography summary
    strikes = topo["strikes"]
    price = topo["current_price"]
    near_strikes = [s for s in strikes if abs(s["moneyness_pct"]) <= 10]

    print(f"  Current price: ${price:.2f}")
    print(f"  Total strikes mapped: {topo['n_strikes']}")
    print(f"  Strikes within ±10%: {len(near_strikes)}")

    if near_strikes:
        top_energy = sorted(near_strikes, key=lambda s: -s["total_energy"])[:5]
        print(f"\n  Top-5 energy concentrations near price:")
        for s in top_energy:
            print(f"    ${s['strike']:8.2f}  ({s['moneyness_pct']:+.1f}%)  "
                  f"energy={s['total_energy']:,.0f}  "
                  f"C={s['call_energy']:,.0f}  P={s['put_energy']:,.0f}  "
                  f"net={'↑BUY' if s['net_energy']>0 else '↓SELL'}")

    # Step 2: Pressure gradient
    gradient = compute_pressure_gradient(topo)
    dir_label = {1: "UP ↑", -1: "DOWN ↓", 0: "NEUTRAL →"}[gradient["direction"]]
    print(f"\n  Pressure Analysis:")
    print(f"    Energy above:  {gradient['energy_above']:,.0f}")
    print(f"    Energy below:  {gradient['energy_below']:,.0f}")
    print(f"    Ratio (above/below): {gradient['energy_ratio_above_below']:.3f}")
    print(f"    Predicted flow:      {dir_label}  (confidence: {gradient['confidence']:.3f})")
    print(f"    Nearest wall above:  ${gradient['nearest_wall_above']:.2f}")
    print(f"    Nearest wall below:  ${gradient['nearest_wall_below']:.2f}")

    # Step 3: Backtest
    print(f"\n{'─'*70}")
    print(f"  DIRECTIONAL BACKTEST — {lookback}-month lookback")
    print(f"{'─'*70}")

    bt_result = backtest_meteorology(ticker, lookback_months=lookback)

    if bt_result["status"] == "OK":
        edge = bt_result["edge_over_random"]
        edge_label = f"+{edge:.1f}pp" if edge > 0 else f"{edge:.1f}pp"
        print(f"\n  ┌─────────────────────────────┬──────────────┐")
        print(f"  │ Metric                      │ Value        │")
        print(f"  ├─────────────────────────────┼──────────────┤")
        print(f"  │ Total predictions            │ {bt_result['n_predictions']:12d} │")
        print(f"  │ Prediction rate              │ {bt_result['prediction_rate']:10.1f}% │")
        print(f"  │ Hit rate                     │ {bt_result['hit_rate']:10.1f}% │")
        print(f"  │ Weighted hit rate             │ {bt_result['weighted_hit_rate']:10.1f}% │")
        if bt_result["high_confidence_hit_rate"]:
            print(f"  │ High-conf hit rate           │ {bt_result['high_confidence_hit_rate']:10.1f}% │")
        print(f"  │ Random baseline              │ {bt_result['random_baseline']:10.1f}% │")
        print(f"  │ Edge over random             │ {edge_label:>12s} │")
        print(f"  │ Net edge (conf-weighted)     │ {bt_result['net_edge']:+10.4f} │")
        print(f"  │ Up predictions               │ {bt_result['n_up_predictions']:12d} │")
        print(f"  │ Down predictions             │ {bt_result['n_down_predictions']:12d} │")
        print(f"  │ Actual up %                  │ {bt_result['actual_up_pct']:10.1f}% │")
        print(f"  └─────────────────────────────┴──────────────┘")

        if edge > 2:
            print(f"\n  ⚡ Significant predictive edge detected!")
        elif edge > 0:
            print(f"\n  ➕ Marginally positive edge — warrants further investigation.")
        else:
            print(f"\n  ✗ No directional edge — gamma topography alone doesn't predict direction.")
            print(f"    (This is consistent with the Long Gamma Default: hedging opposes")
            print(f"     ALL movement symmetrically, not directionally.)")

    # Step 4: Memory horizon test
    print(f"\n{'─'*70}")
    print(f"  MEMORY HORIZON TEST")
    print(f"{'─'*70}")

    horizon_result = test_memory_horizon(ticker)

    # Compile
    result = {
        "ticker": ticker,
        "status": "OK",
        "sample_topography": {
            "date": sample_date,
            "price": price,
            "n_strikes": topo["n_strikes"],
            "top_energy_strikes": [
                {"strike": s["strike"], "energy": s["total_energy"], "moneyness": s["moneyness_pct"]}
                for s in sorted(near_strikes, key=lambda s: -s["total_energy"])[:10]
            ] if near_strikes else [],
        },
        "gradient": gradient,
        "backtest": bt_result,
        "memory_horizon": horizon_result,
    }

    return result


# ===========================================================================
# CLI
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Microstructure Meteorology Test")
    parser.add_argument("--ticker", type=str, required=True, help="Ticker symbol")
    parser.add_argument("--lookback", type=int, default=12,
                        help="Primary lookback in months (default: 12)")
    args = parser.parse_args()

    result = run_meteorology_test(args.ticker.upper(), lookback=args.lookback)

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outpath = RESULTS_DIR / f"meteorology_{args.ticker.upper()}_{timestamp}.json"

    def clean(obj):
        if isinstance(obj, dict):
            return {k: clean(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [clean(v) for v in obj]
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (pd.Timestamp,)):
            return str(obj)
        return obj

    with open(outpath, "w") as f:
        json.dump(clean(result), f, indent=2)
    print(f"\n  Results saved to: {outpath.name}")


if __name__ == "__main__":
    main()
