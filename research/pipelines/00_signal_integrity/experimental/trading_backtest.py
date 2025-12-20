#!/usr/bin/env python3
"""
Experimental: simple trading-rule style backtest using decoded segments.

Idea (kept deliberately simple and honest about limitations):
  - Use segment_ohlc_s8_*.json on a TRAIN set of anchor dates to choose
    a single (segment_index, component) and window (e.g. 60-70 or 70-80 days)
    that most frequently gives the best (lowest) z-RMSE vs future OHLC.
  - Freeze that mapping.
  - For each anchor date (train and test), build the chosen decoded segment
    from sample_<date>/signals/price_paths.csv, and:
        * Predicted direction = sign of z-scored segment end - start.
        * Realized return = close_last / close_first - 1 over the chosen
          future window using minute bars from bars_range.
        * A "hit" if predicted direction and realized return have the same sign.

This is NOT a production trading system; it is a structured way to ask:
  - If we convert the discovered segment/window structure into a single,
    pre-specified directional rule, does it have any edge on held-out days?

Inputs:
  - sample_YYYY-MM-DD/signals/price_paths.csv
  - bars_range/<SYMBOL>_YYYY-MM-DD_minute.csv
  - reports/segment_ohlc_s8_YYYY-MM-DD.json  (from segment_ohlc_analysis.py)

Outputs:
  - reports/trading_backtest_<window>_<trainEnd>.json
"""

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd


# ---------- basic series helpers ----------
def load_signals(path: Path, date: str) -> pd.Series:
    """Load decoded price series for a given day and attach absolute timestamps."""
    df = pd.read_csv(path)
    if "price" not in df.columns or "timestamp_ms" not in df.columns:
        raise ValueError("signals CSV must include price and timestamp_ms")
    day_start = pd.Timestamp(f"{date}T00:00:00Z")
    df["timestamp"] = day_start + pd.to_timedelta(df["timestamp_ms"], unit="ms")
    return df.set_index("timestamp")["price"].sort_index()


def resample_signals(series: pd.Series, freq: str = "1min") -> pd.Series:
    return series.resample(freq).last().dropna()


def make_segments(series: pd.Series, n_segments: int) -> List[Tuple[int, pd.Series]]:
    """Split a 1-minute price series into n_segments equal chunks (like segment_ohlc_analysis)."""
    n = len(series)
    seg_len = max(1, n // n_segments)
    segments: List[Tuple[int, pd.Series]] = []
    for i in range(n_segments):
        start = i * seg_len
        end = (i + 1) * seg_len if i < n_segments - 1 else n
        if start >= n:
            break
        seg = series.iloc[start:end]
        if len(seg) >= 5:
            segments.append((i, seg))
    return segments


def load_bars_span(symbol: str, start_date: str, end_date: str, bars_dir: Path) -> pd.DataFrame:
    """Load minute bars (at least close) between start_date and end_date inclusive."""
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    frames: List[pd.DataFrame] = []
    cur = start
    while cur <= end:
        fname = bars_dir / f"{symbol}_{cur.isoformat()}_minute.csv"
        if fname.exists():
            df = pd.read_csv(fname)
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            frames.append(df[["timestamp", "open", "high", "low", "close"]])
        cur += timedelta(days=1)
    if not frames:
        raise FileNotFoundError(f"No bars in {bars_dir} for {symbol} {start_date}..{end_date}")
    df_all = pd.concat(frames, ignore_index=True).sort_values("timestamp")
    return df_all.set_index("timestamp")


def zscore(arr: np.ndarray) -> np.ndarray:
    mu = arr.mean()
    sigma = arr.std()
    if sigma == 0:
        return arr - mu
    return (arr - mu) / sigma


# ---------- mapping selection from training ----------
@dataclass
class Mapping:
    window: str
    segment_index: int
    component: str
    counts: int


def choose_mapping(
    reports_dir: Path, window: str, train_dates: List[str], segments: int
) -> Mapping:
    """
    From segment_ohlc_s8_*.json on train_dates, choose the (segment, component)
    that most frequently attains the best (lowest) z-RMSE in the given window.
    """
    counts: Dict[Tuple[int, str], int] = {}

    for date in train_dates:
        path = reports_dir / f"segment_ohlc_s8_{date}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        wres = data.get("windows", {}).get(window)
        if not wres or "note" in wres:
            continue
        best_z: Optional[float] = None
        best_pair: Optional[Tuple[int, str]] = None
        for seg_key, comps in wres.items():
            if not seg_key.startswith("segment_"):
                continue
            seg_idx = int(seg_key.split("_", 1)[1])
            if seg_idx >= segments:
                continue
            for comp, vals in comps.items():
                z = float(vals["real_z_rmse"])
                if best_z is None or z < best_z:
                    best_z = z
                    best_pair = (seg_idx, comp)
        if best_pair is not None:
            counts[best_pair] = counts.get(best_pair, 0) + 1

    if not counts:
        raise SystemExit(f"No mapping could be chosen for window {window} on train set {train_dates}")

    # Choose pair with highest count; break ties by lexicographic order for determinism.
    (seg_idx, comp), n = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    return Mapping(window=window, segment_index=seg_idx, component=comp, counts=n)


# ---------- trading backtest ----------
@dataclass
class TradeResult:
    date: str
    set_name: str
    pred_sign: int
    realized_return: float
    score: float  # signed segment slope in z-space

    @property
    def hit(self) -> Optional[bool]:
        if self.pred_sign == 0:
            return None
        if self.realized_return == 0:
            return None
        return (self.pred_sign > 0 and self.realized_return > 0) or (
            self.pred_sign < 0 and self.realized_return < 0
        )


def compute_trade_for_day(
    root: Path,
    symbol: str,
    date: str,
    mapping: Mapping,
    segments: int,
    window: str,
    set_name: str,
) -> Optional[TradeResult]:
    """Build predicted direction from decoded segment and realized return from bars."""
    signals_path = root / f"sample_{date}" / "signals" / "price_paths.csv"
    if not signals_path.exists():
        return None
    price = resample_signals(load_signals(signals_path, date))
    if price.empty:
        return None

    segs = make_segments(price, segments)
    seg_series = None
    for idx, seg in segs:
        if idx == mapping.segment_index:
            seg_series = seg
            break
    if seg_series is None or len(seg_series) < 5:
        return None

    seg_arr = zscore(seg_series.to_numpy(dtype=np.float64))
    diff = float(seg_arr[-1] - seg_arr[0])
    pred_sign = 0
    if diff > 0:
        pred_sign = 1
    elif diff < 0:
        pred_sign = -1

    # Realized close return over the chosen window
    start_ts = price.index.min()
    w_start, w_end = map(int, window.split("-"))
    bars = load_bars_span(symbol, date, (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=w_end)).strftime("%Y-%m-%d"), root / "bars_range")
    win = bars[(bars.index >= start_ts + pd.Timedelta(days=w_start)) & (bars.index <= start_ts + pd.Timedelta(days=w_end))]
    if win.empty:
        return None
    closes = win["close"].to_numpy(dtype=np.float64)
    realized_ret = float(closes[-1] / closes[0] - 1.0)

    return TradeResult(
        date=date,
        set_name=set_name,
        pred_sign=pred_sign,
        realized_return=realized_ret,
        score=diff,
    )


def summarize_results(trades: List[TradeResult]) -> Dict[str, float]:
    hits = [t for t in trades if t.hit is not None]
    if not hits:
        return {
            "n_trades": 0,
            "hit_rate": None,
            "mean_return": None,
            "mean_abs_return": None,
        }
    hit_rate = sum(1 for t in hits if t.hit) / len(hits)
    rets = [t.realized_return for t in hits]
    return {
        "n_trades": len(hits),
        "hit_rate": hit_rate,
        "mean_return": float(np.mean(rets)),
        "mean_abs_return": float(np.mean(np.abs(rets))),
    }


def threshold_summary(trades: List[TradeResult], thresholds: List[float]) -> List[Dict[str, float]]:
    """Summarize performance for different |score| thresholds."""
    out: List[Dict[str, float]] = []
    for th in thresholds:
        subset = [t for t in trades if t.hit is not None and abs(t.score) >= th]
        if not subset:
            out.append(
                {
                    "threshold": th,
                    "n_trades": 0,
                    "hit_rate": None,
                    "mean_return": None,
                    "mean_abs_return": None,
                }
            )
            continue
        hit_rate = sum(1 for t in subset if t.hit) / len(subset)
        rets = [t.realized_return for t in subset]
        out.append(
            {
                "threshold": th,
                "n_trades": len(subset),
                "hit_rate": hit_rate,
                "mean_return": float(np.mean(rets)),
                "mean_abs_return": float(np.mean(np.abs(rets))),
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Experimental trading-style backtest from decoded segments.")
    parser.add_argument("--symbol", required=True, help="Symbol, e.g. GME")
    parser.add_argument("--window", required=True, help="Future window in days, e.g. 60-70 or 70-80")
    parser.add_argument("--train-end", required=True, help="Last anchor date in training set (YYYY-MM-DD)")
    parser.add_argument("--segments", type=int, default=8, help="Number of segments used in segment_ohlc_analysis")
    parser.add_argument("--output", type=Path, default=None, help="Optional output JSON path")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    reports_dir = root / "reports"

    # Available dates are those with segment_ohlc_s8_*.json and a sample directory.
    dates = sorted(
        d.name.split("_")[-1].split(".")[0]
        for d in reports_dir.glob("segment_ohlc_s8_*.json")
    )
    if not dates:
        raise SystemExit("No segment_ohlc_s8_*.json found in reports/. Run segment_ohlc_analysis first.")

    train_dates = [d for d in dates if d <= args.train_end]
    test_dates = [d for d in dates if d > args.train_end]
    if not train_dates:
        raise SystemExit(f"No training dates <= {args.train_end} among {dates}")

    mapping = choose_mapping(reports_dir, args.window, train_dates, args.segments)

    trades: List[TradeResult] = []
    for date in train_dates:
        tr = compute_trade_for_day(root, args.symbol, date, mapping, args.segments, args.window, set_name="train")
        if tr is not None:
            trades.append(tr)
    for date in test_dates:
        tr = compute_trade_for_day(root, args.symbol, date, mapping, args.segments, args.window, set_name="test")
        if tr is not None:
            trades.append(tr)

    train_trades = [t for t in trades if t.set_name == "train"]
    test_trades = [t for t in trades if t.set_name == "test"]

    # Thresholds based on train |score| quantiles (including 0).
    scores = np.array([abs(t.score) for t in train_trades if t.hit is not None])
    if scores.size > 0:
        qs = np.quantile(scores, [0.0, 0.25, 0.5, 0.75, 0.9])
        thresholds = sorted(float(x) for x in np.unique(qs))
    else:
        thresholds = [0.0]

    summary = {
        "symbol": args.symbol,
        "window": args.window,
        "train_end": args.train_end,
        "mapping": {
            "segment_index": mapping.segment_index,
            "component": mapping.component,
            "counts": mapping.counts,
        },
        "train_summary": summarize_results(train_trades),
        "test_summary": summarize_results(test_trades),
        "thresholds": thresholds,
        "train_thresholds": threshold_summary(train_trades, thresholds),
        "test_thresholds": threshold_summary(test_trades, thresholds),
        "per_trade": [
            {
                "date": t.date,
                "set": t.set_name,
                "pred_sign": t.pred_sign,
                "realized_return": t.realized_return,
                "hit": t.hit,
                "score": t.score,
            }
            for t in trades
        ],
    }

    out_path = args.output
    if out_path is None:
        out_path = reports_dir / f"trading_backtest_{args.window.replace('-', '_')}_{args.train_end}.json"
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"Mapping chosen: window={mapping.window}, segment={mapping.segment_index}, component={mapping.component}, counts={mapping.counts}")
    print("Train summary:", summary["train_summary"])
    print("Test summary:", summary["test_summary"])
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
