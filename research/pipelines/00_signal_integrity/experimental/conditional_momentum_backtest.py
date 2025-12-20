#!/usr/bin/env python3
"""
Experimental: use decoded score as a regime gate for a simple momentum rule.

Idea:
  - Baseline rule: for each anchor date, compute past 5-trading-day return
    (from daily closes) and trade in that direction over a future window
    (e.g. 70-80 days). Measure hit rate and mean return.
  - Regime gate: only take those momentum trades where the decoded segment
    score (z-scored slope from trading_backtest_*.json) has |score| above
    a threshold (quantiles based on the TRAIN set).

This asks: does the decoded score help select better regimes in which a
plain momentum bet works better?

Inputs:
  - reports/trading_backtest_<window>_<trainEnd>.json
  - bars_range/<SYMBOL>_YYYY-MM-DD_minute.csv

Outputs:
  - reports/conditional_momentum_<window>_<trainEnd>.json
"""

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict

import numpy as np
import pandas as pd


def load_daily_close(symbol: str, date, bars_dir: Path) -> Optional[float]:
    """Load last minute close for a given trading date, or None if missing."""
    fname = bars_dir / f"{symbol}_{date.isoformat()}_minute.csv"
    if not fname.exists():
        return None
    df = pd.read_csv(fname)
    if "close" not in df.columns or df.empty:
        return None
    return float(df["close"].iloc[-1])


def past_ret_5d(symbol: str, date_str: str, bars_dir: Path, days: int = 5) -> Optional[float]:
    """Compute past N-trading-day return ending at 'date' using daily closes."""
    anchor = datetime.strptime(date_str, "%Y-%m-%d").date()
    closes = []
    cur = anchor
    steps = 0
    max_back = 40
    while len(closes) < days + 1 and steps < max_back:
        c = load_daily_close(symbol, cur, bars_dir)
        if c is not None:
            closes.append((cur, c))
        cur -= timedelta(days=1)
        steps += 1
    if len(closes) < days + 1:
        return None
    closes_sorted = sorted(closes, key=lambda x: x[0])
    oldest = closes_sorted[0][1]
    anchor_close = closes_sorted[-1][1]
    if oldest <= 0:
        return None
    return float(anchor_close / oldest - 1.0)


@dataclass
class Sample:
    date: str
    set_name: str
    future_return: float
    score: float
    past_ret_5d: float


def load_samples(symbol: str, window: str, train_end: str, root: Path) -> List[Sample]:
    """Load samples from trading_backtest JSON and augment with past_ret_5d."""
    reports_dir = root / "reports"
    tb_path = reports_dir / f"trading_backtest_{window.replace('-', '_')}_{train_end}.json"
    data = json.loads(tb_path.read_text())
    bars_dir = root / "bars_range"

    samples: List[Sample] = []
    for row in data["per_trade"]:
        if row["hit"] is None:
            continue
        date = row["date"]
        set_name = row["set"]
        fut_ret = float(row["realized_return"])
        score = float(row["score"])
        past = past_ret_5d(symbol, date, bars_dir)
        if past is None:
            continue
        samples.append(Sample(date=date, set_name=set_name, future_return=fut_ret, score=score, past_ret_5d=past))
    return samples


def summarize_trades(fut_rets: List[float], dirs: List[int]) -> Dict[str, Optional[float]]:
    hits = []
    realized = []
    for r, d in zip(fut_rets, dirs):
        if d == 0 or r == 0:
            continue
        hits.append((r > 0 and d > 0) or (r < 0 and d < 0))
        realized.append(r)
    if not hits:
        return {"n_trades": 0, "hit_rate": None, "mean_return": None, "mean_abs_return": None}
    hit_rate = sum(hits) / len(hits)
    mean_ret = float(np.mean(realized))
    mean_abs = float(np.mean(np.abs(realized)))
    return {
        "n_trades": len(hits),
        "hit_rate": hit_rate,
        "mean_return": mean_ret,
        "mean_abs_return": mean_abs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Conditional momentum backtest gated by decoded score.")
    parser.add_argument("--symbol", required=True, help="Symbol, e.g. GME")
    parser.add_argument("--window", required=True, help="Future window, e.g. 70-80")
    parser.add_argument("--train-end", required=True, help="Last train date used in trading_backtest (YYYY-MM-DD)")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    samples = load_samples(args.symbol, args.window, args.train_end, root)
    if not samples:
        raise SystemExit("No samples with both future_return and past_ret_5d found.")

    train = [s for s in samples if s.set_name == "train"]
    test = [s for s in samples if s.set_name == "test"]

    # Determine score thresholds from train |score| quantiles (including 0)
    train_scores = np.array([abs(s.score) for s in train])
    if train_scores.size > 0:
        qs = np.quantile(train_scores, [0.0, 0.25, 0.5, 0.75, 0.9])
        thresholds = sorted(float(x) for x in np.unique(qs))
    else:
        thresholds = [0.0]

    def evaluate(subset: List[Sample], threshold: float) -> Dict[str, Optional[float]]:
        fut_rets: List[float] = []
        dirs: List[int] = []
        for s in subset:
            if abs(s.score) < threshold:
                continue
            # Momentum direction from past 5d return
            if s.past_ret_5d > 0:
                d = 1
            elif s.past_ret_5d < 0:
                d = -1
            else:
                d = 0
            fut_rets.append(s.future_return)
            dirs.append(d)
        return summarize_trades(fut_rets, dirs)

    train_results = {str(th): evaluate(train, th) for th in thresholds}
    test_results = {str(th): evaluate(test, th) for th in thresholds}

    # Baseline (no gating) is threshold == smallest threshold
    summary = {
        "symbol": args.symbol,
        "window": args.window,
        "train_end": args.train_end,
        "thresholds": thresholds,
        "train_results": train_results,
        "test_results": test_results,
    }

    out = root / "reports" / f"conditional_momentum_{args.window.replace('-', '_')}_{args.train_end}.json"
    out.write_text(json.dumps(summary, indent=2))

    print("Thresholds:", thresholds)
    print("Train:", train_results)
    print("Test:", test_results)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

