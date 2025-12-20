#!/usr/bin/env python3
"""
Cross-check decoded price paths against external OHLCV bars.

Inputs:
- signals CSV (from raw_to_signals decode) with columns: price, timestamp_us (relative to midnight)
- external bars CSV with columns: timestamp, open, high, low, close, volume

We reconstruct absolute timestamps by adding timestamp_us to the provided date (UTC),
resample signals to 1-minute OHLC, and compute MAE/RMSE vs external bars.
"""

import argparse
from pathlib import Path
import pandas as pd
import numpy as np


def load_signals(path: Path, date: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "price" not in df.columns or "timestamp_us" not in df.columns:
        raise ValueError(f"{path} must include price and timestamp_us columns")
    day_start = pd.Timestamp(f"{date}T00:00:00Z")
    df["timestamp"] = day_start + pd.to_timedelta(df["timestamp_us"], unit="us")
    return df[["timestamp", "price"]]


def load_bars(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"timestamp", "open", "high", "low", "close"}
    if not required.issubset(df.columns):
        raise ValueError(f"{path} must include {required}")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def resample_signals(signals: pd.DataFrame) -> pd.DataFrame:
    res = signals.set_index("timestamp")["price"].resample("1min").ohlc()
    res = res.dropna()
    res = res.rename(columns={"open": "sig_open", "high": "sig_high", "low": "sig_low", "close": "sig_close"})
    return res


def compare(sig_ohlc: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    merged = bars.set_index("timestamp").join(sig_ohlc, how="inner")
    for col in ["open", "high", "low", "close"]:
        merged[f"{col}_mae"] = (merged[col] - merged[f"sig_{col}"]).abs()
        merged[f"{col}_rmse"] = (merged[col] - merged[f"sig_{col}"]) ** 2
        merged[f"{col}_diff"] = merged[col] - merged[f"sig_{col}"]
    return merged


def summarize(merged: pd.DataFrame):
    summary = {}
    for col in ["open", "high", "low", "close"]:
        mae = merged[f"{col}_mae"].mean()
        rmse = np.sqrt(merged[f"{col}_rmse"].mean())
        summary[f"{col}_mae"] = float(mae)
        summary[f"{col}_rmse"] = float(rmse)
        summary[f"{col}_corr"] = float(merged[f"{col}_diff"].corr(merged[col]) or 0)
    # lead/lag: shift signals by +/-1 minute and recompute close corr
    merged_shift_fwd = merged.copy()
    merged_shift_fwd["sig_close_fwd"] = merged_shift_fwd["sig_close"].shift(-1)
    merged_shift_back = merged.copy()
    merged_shift_back["sig_close_back"] = merged_shift_back["sig_close"].shift(1)
    summary["close_corr"] = float(merged["close"].corr(merged["sig_close"]) or 0)
    summary["close_corr_lead1m"] = float(merged["close"].corr(merged_shift_fwd["sig_close_fwd"]) or 0)
    summary["close_corr_lag1m"] = float(merged["close"].corr(merged_shift_back["sig_close_back"]) or 0)
    summary["rows_compared"] = int(len(merged))
    return summary


def main():
    parser = argparse.ArgumentParser(description="Cross-check decoded signals vs external OHLCV bars.")
    parser.add_argument("--signals", required=True, type=Path, help="Decoded signals CSV")
    parser.add_argument("--bars", required=True, type=Path, help="External OHLCV bars CSV")
    parser.add_argument("--date", required=True, help="Date YYYY-MM-DD for signals (to anchor timestamp_us)")
    args = parser.parse_args()

    signals = load_signals(args.signals, args.date)
    bars = load_bars(args.bars)
    sig_ohlc = resample_signals(signals)
    merged = compare(sig_ohlc, bars)
    summary = summarize(merged)

    print("Comparison summary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"Joined rows: {summary['rows_compared']}, signals bars: {len(sig_ohlc)}, external bars: {len(bars)}")


if __name__ == "__main__":
    main()
