#!/usr/bin/env python3
"""
Experimental: multivariate predictiveness check for decoded segment signal.

Uses the trading_backtest_<window>_<trainEnd>.json output plus minute bars to ask:
  - How well does a simple past-5-day momentum feature predict the sign of
    future returns over the chosen window?
  - Does adding the decoded segment score (z-scored slope of the chosen segment)
    improve predictive performance (log-loss / accuracy) on a held-out test set?

We deliberately keep the model tiny:
  - Logistic regression with features:
      baseline: [1, past_ret_5d]
      full:     [1, past_ret_5d, score]

Outputs:
  - reports/multivariate_<window>_<trainEnd>.json with train/test metrics
    for both models.
"""

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize


def load_daily_close(symbol: str, date: datetime.date, bars_dir: Path) -> Optional[float]:
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
    # Walk backwards, collecting trading days with data.
    closes: List[Tuple[datetime.date, float]] = []
    cur = anchor
    max_back = 40  # safety to avoid infinite loops on sparse data
    steps = 0
    while len(closes) < days + 1 and steps < max_back:
        c = load_daily_close(symbol, cur, bars_dir)
        if c is not None:
            closes.append((cur, c))
        cur -= timedelta(days=1)
        steps += 1
    if len(closes) < days + 1:
        return None
    # Sort by date ascending, pick oldest and anchor.
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
    """Load per-trade data from trading_backtest JSON and augment with past_ret_5d."""
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


def build_design(samples: List[Sample]) -> Tuple[np.ndarray, np.ndarray]:
    """Return X (n x k) and y (n,) for logistic regression, y in {0,1}."""
    y = []
    X = []
    for s in samples:
        if s.future_return == 0:
            continue
        y.append(1 if s.future_return > 0 else 0)
        X.append((s.past_ret_5d, s.score))
    if not X:
        return np.zeros((0, 2)), np.zeros((0,))
    return np.asarray(X, dtype=np.float64), np.asarray(y, dtype=np.float64)


def fit_logistic(X: np.ndarray, y: np.ndarray, use_score: bool) -> np.ndarray:
    """
    Fit logistic regression via numerical optimization.
    If use_score is False, model is: p = sigmoid(b0 + b1 * past_ret_5d)
    If use_score is True,  model is: p = sigmoid(b0 + b1 * past_ret_5d + b2 * score)
    """
    if X.shape[0] == 0:
        return np.zeros(1)

    if use_score:
        # columns: [1, past_ret, score]
        X_design = np.column_stack([np.ones(len(X)), X[:, 0], X[:, 1]])
    else:
        # columns: [1, past_ret]
        X_design = np.column_stack([np.ones(len(X)), X[:, 0]])

    def nll(beta: np.ndarray) -> float:
        z = X_design @ beta
        # log-likelihood for Bernoulli logistic
        # avoid overflow with log1p(exp(z))
        ll = y * z - np.log1p(np.exp(z))
        return float(-np.sum(ll))

    beta0 = np.zeros(X_design.shape[1])
    res = minimize(nll, beta0, method="BFGS")
    return res.x


def predict_metrics(beta: np.ndarray, X: np.ndarray, y: np.ndarray, use_score: bool) -> Dict[str, float]:
    if X.shape[0] == 0:
        return {"n": 0, "accuracy": None, "log_loss": None}
    if use_score:
        X_design = np.column_stack([np.ones(len(X)), X[:, 0], X[:, 1]])
    else:
        X_design = np.column_stack([np.ones(len(X)), X[:, 0]])
    z = X_design @ beta
    p = 1.0 / (1.0 + np.exp(-z))
    # classification accuracy
    preds = (p >= 0.5).astype(int)
    acc = float(np.mean(preds == y))
    # log-loss
    eps = 1e-12
    ll = y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps)
    log_loss = float(-np.mean(ll))
    return {"n": int(len(y)), "accuracy": acc, "log_loss": log_loss}


def main() -> None:
    parser = argparse.ArgumentParser(description="Multivariate predictiveness check for decoded segment signal.")
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

    X_train, y_train = build_design(train)
    X_test, y_test = build_design(test)

    # Baseline: past_ret_5d only
    beta_base = fit_logistic(X_train, y_train, use_score=False)
    base_train = predict_metrics(beta_base, X_train, y_train, use_score=False)
    base_test = predict_metrics(beta_base, X_test, y_test, use_score=False)

    # Full: past_ret_5d + decoded score
    beta_full = fit_logistic(X_train, y_train, use_score=True)
    full_train = predict_metrics(beta_full, X_train, y_train, use_score=True)
    full_test = predict_metrics(beta_full, X_test, y_test, use_score=True)

    summary = {
        "symbol": args.symbol,
        "window": args.window,
        "train_end": args.train_end,
        "n_train": int(len(y_train)),
        "n_test": int(len(y_test)),
        "beta_baseline": beta_base.tolist(),
        "beta_full": beta_full.tolist(),
        "baseline": {"train": base_train, "test": base_test},
        "full": {"train": full_train, "test": full_test},
    }

    out = root / "reports" / f"multivariate_{args.window.replace('-', '_')}_{args.train_end}.json"
    out.write_text(json.dumps(summary, indent=2))

    print(f"Baseline train: {base_train}")
    print(f"Baseline test:  {base_test}")
    print(f"Full train:     {full_train}")
    print(f"Full test:      {full_test}")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

