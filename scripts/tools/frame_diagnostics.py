#!/usr/bin/env python3
"""Standalone diagnostics runner for the Power Tracks demo frames.

This script mirrors the critical parts of the notebook so we can
execute frame-alignment experiments, payload smoke tests, whitening
checks, and raw-line taps directly from the CLI.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
from scipy.signal import hilbert, welch

SCRIPT_DIR = Path(__file__).parent.resolve()

def safe_sort_timestamp(df: pd.DataFrame) -> pd.DataFrame:
    try:
        return df.sort_values("timestamp")
    except Exception:
        # Python 3.14 / Pandas workaround: skip sort if it crashes
        return df

CSV_FALLBACK_PATH = SCRIPT_DIR / "sample_data.csv"
RAW_TAP_PATH = Path(__file__).with_name("raw_line_tap.csv")
REPORT_PATH = Path(__file__).with_name("frame_diagnostics_report.json")
PRICE_PATH_DIR = SCRIPT_DIR / "price_paths"

DATA_SOURCE = os.getenv("PTE_DATA_SOURCE", "polygon").lower()
CSV_FILE_PATH = Path(os.getenv("PTE_CSV_PATH", str(CSV_FALLBACK_PATH))).expanduser()
POLYGON_SYMBOL = os.getenv("PTE_POLYGON_SYMBOL", "GME")
POLYGON_DATE = os.getenv("PTE_POLYGON_DATE", "2024-05-17")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")
POLYGON_WINDOW_MAX_PAGES = int(os.getenv("PTE_POLYGON_WINDOW_MAX_PAGES", "3"))
WINDOW_BUFFER_SECONDS = int(os.getenv("PTE_WINDOW_BUFFER_SECONDS", "30"))
MAX_WINDOW_SECONDS = int(os.getenv("PTE_MAX_WINDOW_SECONDS", "300"))
MANUAL_WINDOW_SPECS = [s.strip() for s in os.getenv("PTE_MANUAL_WINDOWS", "").split(",") if s.strip()]
MANUAL_TIME_ZONE = os.getenv("PTE_MANUAL_TIME_ZONE", "America/New_York")

RESAMPLE_RATE = 1_000
LOW_PERCENTILE = 15
HIGH_PERCENTILE = 85
DEBOUNCE_US = 200
FRAME_BITS = 56
HEADER_BYTES = 16
TRAILER_BYTES = 1
MASK_RANGE = range(0, 0x20)
ALIGNMENT_SAMPLE_FRAMES = int(os.getenv("PTE_ALIGNMENT_SAMPLE_FRAMES", "400"))

SCAN_TIMESPAN = os.getenv("PTE_SCAN_TIMESPAN", "minute")
SCAN_MULTIPLIER = int(os.getenv("PTE_SCAN_MULTIPLIER", "1"))
SCAN_PRICE_STD_THRESHOLD = float(os.getenv("PTE_SCAN_PRICE_STD_THRESHOLD", "0.05"))  # $0.05
SCAN_ROC_THRESHOLD = float(os.getenv("PTE_SCAN_ROC_THRESHOLD", "0.007"))  # 0.7%
SCAN_MAX_WINDOWS = int(os.getenv("PTE_SCAN_MAX_WINDOWS", "12"))
DETECTION_WINDOW_SECONDS = int(os.getenv("PTE_DETECTION_WINDOW_SECONDS", "60"))
DETECTION_STEP_SECONDS = int(os.getenv("PTE_DETECTION_STEP_SECONDS", "10"))
POWER_THRESHOLD = float(os.getenv("PTE_POWER_THRESHOLD", "10000"))
ROC_THRESHOLD = float(os.getenv("PTE_ROC_THRESHOLD", "0.007"))
ROC_LOOKBACK_SECONDS = int(os.getenv("PTE_ROC_LOOKBACK_SECONDS", "5"))
FREQ_BAND_LOW = float(os.getenv("PTE_FREQ_BAND_LOW", "0.5"))
FREQ_BAND_HIGH = float(os.getenv("PTE_FREQ_BAND_HIGH", "3.0"))
FREQ_BAND = (FREQ_BAND_LOW, FREQ_BAND_HIGH)
MASK_SEARCH_START = int(os.getenv("PTE_MASK_RANGE_START", "0"), 16) if "PTE_MASK_RANGE_START" in os.environ else 0
MASK_SEARCH_END = int(os.getenv("PTE_MASK_RANGE_END", "1F"), 16) if "PTE_MASK_RANGE_END" in os.environ else 0x1F
MIN_MASK_SCORE = float(os.getenv("PTE_MIN_MASK_SCORE", "0.15"))
MASK_SAMPLE_FRAMES = int(os.getenv("PTE_MASK_SAMPLE_FRAMES", "2000"))
MASK_VALIDATE_FRAMES = int(os.getenv("PTE_MASK_VALIDATE_FRAMES", "6000"))
VOLUME_MULTIPLIERS = tuple(
    int(item.strip())
    for item in os.getenv("PTE_VOLUME_MULTIPLIERS", "10,25,50,100").split(",")
    if item.strip()
)
BASE_TIME_UNIT_SECONDS = float(os.getenv("PTE_BASE_TIME_UNIT_SECONDS", "1"))
LAG_OFFSETS_DAYS = tuple(
    int(item.strip())
    for item in os.getenv("PTE_LAG_OFFSETS_DAYS", "1,4,7").split(",")
    if item.strip()
)
LAG_LABELS = [f"{day}d" for day in LAG_OFFSETS_DAYS] or ["1d", "4d", "7d"]
LAG_OFFSETS_SECONDS = tuple(day * 86400 for day in (LAG_OFFSETS_DAYS or (1, 4, 7)))
MAX_HORIZON_DAYS = int(os.getenv("PTE_MAX_HORIZON_DAYS", "90"))
MAX_HORIZON_SECONDS = MAX_HORIZON_DAYS * 86400
INCLUDE_OTC_TRADES = os.getenv("PTE_INCLUDE_OTC", "true").lower() in ("1", "true", "yes")
MACRO_LAG_MINUTES = tuple(
    int(item.strip())
    for item in os.getenv("PTE_MACRO_LAG_MINUTES", "1,4,7").split(",")
    if item.strip()
)
MACRO_LAG_LABELS = [f"{minute}m" for minute in MACRO_LAG_MINUTES] or ["1m", "4m", "7m"]
MACRO_LAG_OFFSETS_SECONDS = tuple(minute * 60 for minute in (MACRO_LAG_MINUTES or (1, 4, 7)))

_POLYGON_EXCHANGE_CACHE: Dict[int, str] | None = None


def get_polygon_exchange_map(api_key: str) -> Dict[int, str]:
    global _POLYGON_EXCHANGE_CACHE
    if _POLYGON_EXCHANGE_CACHE is not None:
        return _POLYGON_EXCHANGE_CACHE

    url = "https://api.polygon.io/v3/reference/exchanges"
    params = {
        "asset_class": "stocks",
        "limit": 1000,
        "apiKey": api_key,
    }
    mapping: Dict[int, str] = {}
    try:
        # Increased timeout for exchange metadata fetch
        response = requests.get(url, params=params, timeout=60)
        response.raise_for_status()
        payload = response.json()
        for row in payload.get("results") or []:
            try:
                exchange_id = int(row["id"])
            except Exception:
                continue
            code = str(row.get("code") or "").strip().upper()
            name = str(row.get("name") or "").strip()
            if code:
                label = code
            elif name:
                label = name
            else:
                label = f"EX-{exchange_id}"
            mapping[exchange_id] = label
    except Exception as exc:
        print(f"   • Warning: unable to load exchange metadata ({exc}), falling back to numeric codes")
    _POLYGON_EXCHANGE_CACHE = mapping
    return mapping


@dataclass
class BitstreamResult:
    bitstream: np.ndarray
    time_grid: np.ndarray
    envelope: np.ndarray
    low_threshold: float
    high_threshold: float
    debounce_seconds: float


@dataclass
class AlignmentResult:
    frames: np.ndarray
    polarity: str
    bit_order: str
    frame_bits: int
    offset_bits: int
    score: float
    header_variety: int
    header_entropy: float
    example_header: List[int]


@dataclass
class SyntheticResult:
    injected_frames: np.ndarray
    recovered_frames: np.ndarray
    crc_matches: bool
    frame_bytes: int


def load_waveform(csv_path: Path) -> pd.DataFrame:
    # Try resolving relative to CWD first, then SCRIPT_DIR
    if csv_path.exists():
        path = csv_path
    elif (SCRIPT_DIR / csv_path).exists():
        path = SCRIPT_DIR / csv_path
    else:
        # Fallback to ensure we have a path object for error reporting
        path = csv_path if csv_path.is_absolute() else (SCRIPT_DIR / csv_path)

    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path} (checked CWD and {SCRIPT_DIR})")
    
    # Peek at columns first to decide how to parse
    peek = pd.read_csv(path, nrows=1)
    if "timestamp" in peek.columns:
        df = pd.read_csv(path, parse_dates=["timestamp"])
    elif "timestamp_us" in peek.columns:
        df = pd.read_csv(path)
        df["timestamp"] = pd.to_datetime(df["timestamp_us"], unit="us", utc=True)
    else:
        raise ValueError(f"CSV must contain 'timestamp' or 'timestamp_us' column. Found: {list(peek.columns)}")

    if df.empty:
        raise ValueError(f"No rows found in {csv_path}")

    # Ensure valid timestamps before sorting
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        raise ValueError(f"No valid timestamp rows found in {csv_path}")

    df = safe_sort_timestamp(df)
    return df


def _parse_manual_timestamp(value: str) -> pd.Timestamp | None:
    try:
        ts = pd.Timestamp(value)
    except Exception:
        try:
            ts = pd.Timestamp(f"{POLYGON_DATE} {value}")
        except Exception:
            return None

    if ts.tzinfo is None:
        tz_name = MANUAL_TIME_ZONE or "UTC"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("UTC")
        ts = ts.tz_localize(tz)
    else:
        ts = ts.tz_convert("UTC")

    return ts.tz_convert("UTC")


def manual_windows_from_env() -> List[Dict[str, object]]:
    windows: List[Dict[str, object]] = []
    for spec in MANUAL_WINDOW_SPECS:
        if "/" not in spec:
            continue
        start_str, end_str = spec.split("/", 1)
        start_ts = _parse_manual_timestamp(start_str.strip())
        end_ts = _parse_manual_timestamp(end_str.strip())
        if start_ts is None or end_ts is None:
            continue
        if end_ts <= start_ts:
            continue
        windows.append(
            {
                "window_start": start_ts,
                "window_end": end_ts,
                "roc_value": None,
                "price_std": None,
                "num_bars": None,
                "source": "manual",
            }
        )
    return windows


def fetch_polygon_ticks(symbol: str, start_ts: pd.Timestamp, end_ts: pd.Timestamp,
                        api_key: str, max_pages: int) -> pd.DataFrame:
    if not api_key:
        raise ValueError("POLYGON_API_KEY is required to fetch live data")
    exchange_map = get_polygon_exchange_map(api_key)

    start_ts = pd.Timestamp(start_ts)
    end_ts = pd.Timestamp(end_ts)
    if start_ts.tzinfo is None:
        start_ts = start_ts.tz_localize("UTC")
    else:
        start_ts = start_ts.tz_convert("UTC")
    if end_ts.tzinfo is None:
        end_ts = end_ts.tz_localize("UTC")
    else:
        end_ts = end_ts.tz_convert("UTC")
    start_ns = int(start_ts.timestamp() * 1_000_000_000)
    end_ns = int(end_ts.timestamp() * 1_000_000_000)

    base_url = f"https://api.polygon.io/v3/trades/{symbol}"
    params = {
        "apiKey": api_key,
        "timestamp.gte": start_ns,
        "timestamp.lt": end_ns,
        "limit": 50_000,
        "order": "asc",
        "include_otc": "true" if INCLUDE_OTC_TRADES else "false",
    }

    trades: List[Dict[str, object]] = []
    url = base_url
    page = 0

    print(f"   • Fetching ticks {start_ts} → {end_ts} (max {max_pages} page(s))")
    import time
    max_retries = 3
    retry_delay = 2  # seconds
    tried_without_otc = False
    
    while url and page < max_pages:
        retry_count = 0
        response = None
        
        while retry_count < max_retries:
            try:
                # Increased timeout to 120 seconds for large data requests
                response = requests.get(url, params=params, timeout=120)
                response.raise_for_status()
                break  # Success, exit retry loop
            except requests.exceptions.HTTPError as e:
                # Handle 403 Forbidden - might be due to OTC trades permission
                error_response = e.response if hasattr(e, 'response') else response
                if error_response is not None and error_response.status_code == 403:
                    if INCLUDE_OTC_TRADES and not tried_without_otc:
                        print(f"      ⚠️  403 Forbidden - API key may not have OTC trades permission")
                        print(f"      🔄 Retrying without include_otc parameter...")
                        params.pop("include_otc", None)
                        tried_without_otc = True
                        retry_count = 0  # Reset retry count for the new attempt
                        continue
                    else:
                        error_msg = error_response.text if hasattr(error_response, 'text') else str(e)
                        raise RuntimeError(
                            f"403 Forbidden: API key may not have permission for this endpoint.\n"
                            f"Error details: {error_msg}\n"
                            f"URL: {error_response.url if hasattr(error_response, 'url') else url}"
                        )
                # For other HTTP errors, don't retry
                raise RuntimeError(f"API request failed on page {page + 1}: {e}")
            except (requests.exceptions.ReadTimeout, requests.exceptions.Timeout) as e:
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = retry_delay * (2 ** (retry_count - 1))  # Exponential backoff
                    print(f"      ⚠️  Timeout on page {page + 1}, retrying in {wait_time}s (attempt {retry_count + 1}/{max_retries})...")
                    time.sleep(wait_time)
                else:
                    raise RuntimeError(f"Failed to fetch page {page + 1} after {max_retries} attempts: {e}")
            except requests.exceptions.RequestException as e:
                # For other request errors, don't retry
                raise RuntimeError(f"API request failed on page {page + 1}: {e}")
        
        if response is None:
            raise RuntimeError(f"Failed to get response for page {page + 1}")
        
        payload = response.json()
        results = payload.get("results") or []
        if not results:
            break

        print(f"      page {page + 1}: {len(results)} ticks")

        for trade in results:
            ts_ns = trade.get("participant_timestamp") or trade.get("sip_timestamp")
            price = trade.get("price")
            if ts_ns is None or price is None:
                continue
            timestamp = pd.to_datetime(int(ts_ns) / 1_000_000, unit="ms", utc=True)
            exchange_id = trade.get("exchange")
            try:
                venue_code = int(exchange_id) if exchange_id is not None else None
            except Exception:
                venue_code = None
            venue_label = "OTC"
            if venue_code is not None:
                venue_label = exchange_map.get(venue_code, str(venue_code))
            trades.append(
                {
                    "timestamp": timestamp,
                    "price": float(price),
                    "venue": venue_label,
                    "venue_id": venue_code,
                    "symbol": symbol,
                    "size": int(trade.get("size") or 0),
                }
            )

        next_url = payload.get("next_url")
        if next_url:
            url = next_url if "apiKey" in next_url else f"{next_url}&apiKey={api_key}"
            params = {}
        else:
            url = None
        page += 1
        if page >= max_pages and payload.get("next_url"):
            break

    df = safe_sort_timestamp(pd.DataFrame(trades)).reset_index(drop=True)
    if not df.empty:
        df = df.drop_duplicates(subset=["timestamp", "price"])
    return df


def fetch_polygon_minute_bars(symbol: str, date: str, api_key: str,
                              multiplier: int = SCAN_MULTIPLIER,
                              timespan: str = SCAN_TIMESPAN) -> pd.DataFrame:
    if not api_key:
        raise ValueError("POLYGON_API_KEY is required to fetch live data")

    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/"
        f"{date}/{date}"
    )
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 50_000,
        "apiKey": api_key,
    }
    import time
    max_retries = 3
    retry_delay = 2
    
    for retry_count in range(max_retries):
        try:
            # Increased timeout for minute bars fetch
            response = requests.get(url, params=params, timeout=120)
            response.raise_for_status()
            payload = response.json()
            break  # Success
        except (requests.exceptions.ReadTimeout, requests.exceptions.Timeout) as e:
            if retry_count < max_retries - 1:
                wait_time = retry_delay * (2 ** retry_count)
                print(f"   ⚠️  Timeout fetching minute bars, retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise RuntimeError(f"Failed to fetch minute bars after {max_retries} attempts: {e}")
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"API request failed for minute bars: {e}")
    
    results = payload.get("results") or []
    if not results:
        raise RuntimeError("Polygon aggregates API returned no data")

    records = []
    for row in results:
        ts = pd.to_datetime(row["t"], unit="ms", utc=True)
        close = float(row.get("c") or row.get("o") or row.get("h") or row.get("l"))
        records.append(
            {
                "timestamp": ts,
                "close": close,
                "volume": row.get("v", 0),
                "high": row.get("h", close),
                "low": row.get("l", close),
                "open": row.get("o", close),
            }
        )
    df = safe_sort_timestamp(pd.DataFrame(records)).reset_index(drop=True)
    return df


def scan_windows_from_minutes(df: pd.DataFrame) -> List[Dict[str, object]]:
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = safe_sort_timestamp(df).reset_index(drop=True)
    if len(df) < 2 or SCAN_MAX_WINDOWS == 0:
        return []

    spacing = df["timestamp"].diff().dropna().dt.total_seconds()
    median_spacing = float(spacing.median()) if not spacing.empty else 60.0
    window_seconds = max(60.0, DETECTION_WINDOW_SECONDS, median_spacing * 2.0)
    step_seconds = max(10.0, DETECTION_STEP_SECONDS, median_spacing)

    window = pd.Timedelta(seconds=window_seconds)
    step = pd.Timedelta(seconds=step_seconds)
    start_time = df["timestamp"].min()
    end_time = df["timestamp"].max()

    windows: List[Dict[str, object]] = []
    current = start_time
    while current + window <= end_time:
        mask = (df["timestamp"] >= current) & (df["timestamp"] < current + window)
        window_df = df.loc[mask]
        if len(window_df) >= 2:
            roc = abs(window_df["close"].iloc[-1] - window_df["close"].iloc[0]) / max(
                window_df["close"].iloc[0], 1e-9
            )
            price_std = float(window_df["close"].std() or 0.0)
            if price_std >= SCAN_PRICE_STD_THRESHOLD or roc >= SCAN_ROC_THRESHOLD:
                windows.append(
                    {
                        "window_start": current,
                        "window_end": current + window,
                        "roc_value": roc,
                        "price_std": price_std,
                        "num_bars": len(window_df),
                        "source": "minute_scan",
                    }
                )
        current += step

    if SCAN_MAX_WINDOWS > 0 and len(windows) > SCAN_MAX_WINDOWS:
        scored = sorted(
            windows,
            key=lambda w: (
                max(w.get("price_std") or 0.0, w.get("roc_value") or 0.0),
                w.get("price_std") or 0.0,
                w.get("roc_value") or 0.0,
            ),
            reverse=True,
        )[:SCAN_MAX_WINDOWS]
        windows = sorted(scored, key=lambda w: w["window_start"])

    return windows


def prepare_polygon_windows() -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    agg_df = fetch_polygon_minute_bars(POLYGON_SYMBOL, POLYGON_DATE, POLYGON_API_KEY)
    scan_windows = scan_windows_from_minutes(agg_df)
    manual_windows = manual_windows_from_env()

    all_windows = list(scan_windows)
    all_windows.extend(manual_windows)

    if not all_windows:
        if not agg_df.empty:
            fallback_start = agg_df["timestamp"].iloc[0]
        else:
            fallback_start = pd.Timestamp(f"{POLYGON_DATE} 09:30", tz="America/New_York").tz_convert("UTC")
        all_windows = [
            {
                "window_start": fallback_start,
                "window_end": fallback_start + pd.Timedelta(seconds=max(60, DETECTION_WINDOW_SECONDS)),
                "roc_value": 0.0,
                "price_std": 0.0,
                "num_bars": 1,
                "source": "fallback",
            }
        ]

    tick_windows: List[Dict[str, object]] = []
    chunk = pd.Timedelta(seconds=max(60, MAX_WINDOW_SECONDS))
    buffer = pd.Timedelta(seconds=WINDOW_BUFFER_SECONDS)
    for spec in all_windows:
        start = spec["window_start"] - buffer
        end = spec["window_end"] + buffer
        chunk_start = start
        chunk_idx = 1
        while chunk_start < end:
            chunk_end = min(end, chunk_start + chunk)
            ticks = fetch_polygon_ticks(POLYGON_SYMBOL, chunk_start, chunk_end, POLYGON_API_KEY, POLYGON_WINDOW_MAX_PAGES)
            if not ticks.empty:
                meta_copy = dict(spec)
                meta_copy.update(
                    {
                        "chunk_start": chunk_start,
                        "chunk_end": chunk_end,
                        "chunk_index": chunk_idx,
                    }
                )
                tick_windows.append(
                    {
                        "ticks": ticks,
                        "meta": meta_copy,
                    }
                )
            chunk_start = chunk_end
            chunk_idx += 1

    meta = {
        "minute_scan_windows": scan_windows,
        "manual_windows": manual_windows,
        "minute_rows": int(len(agg_df)),
        "symbol": POLYGON_SYMBOL,
        "date": POLYGON_DATE,
    }
    return tick_windows, meta


def prepare_csv_window() -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    df = load_waveform(CSV_FILE_PATH)
    df = safe_sort_timestamp(df).reset_index(drop=True)
    base_window = {
        "window_start": df["timestamp"].min(),
        "window_end": df["timestamp"].max(),
        "roc_value": 0.0,
        "price_std": float(df["price"].std()),
        "num_bars": len(df),
        "source": "csv_full",
    }

    manual_specs = manual_windows_from_env()
    windows = manual_specs or [base_window]
    tick_windows: List[Dict[str, object]] = []
    for spec in windows:
        if spec.get("source") == "manual":
            start = spec["window_start"]
            end = spec["window_end"]
            mask = (df["timestamp"] >= start) & (df["timestamp"] <= end)
            ticks = df.loc[mask]
        else:
            ticks = df
        tick_windows.append({"ticks": ticks, "meta": spec})

    meta = {
        "minute_scan_windows": [base_window],
        "manual_windows": manual_specs,
        "minute_rows": len(df),
        "symbol": "csv",
        "date": "n/a",
    }
    return tick_windows, meta


def _to_timestamp(value) -> float:
    if hasattr(value, "timestamp"):
        return float(value.timestamp())
    return float(pd.Timestamp(value).timestamp())


def _ensure_timestamp(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def compute_spectral_power(prices: np.ndarray, times: Sequence, freq_band: Tuple[float, float]) -> float:
    if prices.size < 10:
        return 0.0

    time_axis = np.array([_to_timestamp(t) for t in times], dtype=float)
    t0, t1 = time_axis[0], time_axis[-1]
    duration = max(t1 - t0, 1e-6)
    resample_rate = RESAMPLE_RATE
    grid = np.linspace(t0, t1, max(16, int(duration * resample_rate)))
    uniform = np.interp(grid, time_axis, prices)
    diffs = np.diff(uniform)
    price_level = max(np.mean(np.abs(uniform)), 1e-6)
    returns = (diffs / price_level) * 1e6
    returns = returns - np.mean(returns)
    if returns.size < 16 or np.std(returns) < 1e-9:
        return 0.0
    freqs, psd = welch(returns, fs=resample_rate, nperseg=min(len(returns), 1024))
    low, high = freq_band
    mask = (freqs >= low) & (freqs <= high)
    if not np.any(mask):
        return 0.0
    return float(np.trapezoid(psd[mask], freqs[mask]))


def calculate_roc(prices: np.ndarray, times: Sequence, lookback_seconds: int) -> float:
    if prices.size < 2:
        return 0.0
    current_price = prices[-1]
    current_time = _to_timestamp(times[-1])
    target_time = current_time - lookback_seconds
    lookback_price = None
    for price, ts in zip(prices[::-1], times[::-1]):
        if _to_timestamp(ts) <= target_time:
            lookback_price = price
            break
    if lookback_price is None:
        lookback_price = prices[0]
    if lookback_price == 0:
        return 0.0
    return float((current_price - lookback_price) / lookback_price)


def xor_mask(frame: np.ndarray, mask_key: int) -> np.ndarray:
    return np.bitwise_xor(frame, mask_key).astype(np.uint8)


def decode_varints(data_bytes: bytes) -> List[int]:
    values: List[int] = []
    i = 0
    length = len(data_bytes)
    while i < length:
        value = 0
        shift = 0
        while i < length:
            byte = data_bytes[i]
            value |= (byte & 0x7F) << shift
            i += 1
            if (byte & 0x80) == 0:
                break
            shift += 7
            if shift >= 32:
                break
        values.append(value)
    return values


def zigzag_decode(value: int) -> int:
    return (value >> 1) ^ (-(value & 1))


def parse_header_bytes(header_bytes: np.ndarray) -> Dict[str, object] | None:
    if header_bytes.size < HEADER_BYTES:
        return None
    data = bytes(header_bytes[:HEADER_BYTES])
    opcode = data[0]
    version = data[1]
    start_time_us = int.from_bytes(data[2:6], "little", signed=False)
    duration_seconds = int.from_bytes(data[6:8], "little", signed=False)
    compression_ratio = data[8]
    anchor_raw = int.from_bytes(data[9:13], "little", signed=False)
    volume_hint = data[13] | (data[14] << 8) | (data[15] << 16)
    anchor_usd = anchor_raw / 10_000
    if compression_ratio not in (1, 2, 4, 8):
        return None
    if not (0 <= anchor_usd <= 10_000):
        return None
    return {
        "opcode": opcode,
        "version": version,
        "start_time_us": start_time_us,
        "duration_seconds": duration_seconds if duration_seconds > 0 else len(data),
        "compression_ratio": compression_ratio,
        "anchor_usd": anchor_usd,
        "volume_hint": volume_hint,
    }


def decode_payload_entries(varints: Sequence[int]) -> List[Dict[str, object]]:
    entries: List[Dict[str, object]] = []
    idx = 0
    while idx < len(varints):
        value = varints[idx]
        if value == 0x3F and idx + 1 < len(varints):
            delta = zigzag_decode(varints[idx + 1])
            entries.append({"opcode": "mirror", "value": delta, "raw": varints[idx + 1]})
            idx += 2
            continue
        if value == 0x91 and idx + 1 < len(varints):
            continuation = zigzag_decode(varints[idx + 1])
            entries.append({"opcode": "continuation", "value": continuation, "raw": varints[idx + 1]})
            idx += 2
            continue
        entries.append({"opcode": "delta", "value": zigzag_decode(value), "raw": value})
        idx += 1
    return entries


def _apply_mask_to_frames(frames: Sequence[np.ndarray], mask_key: int,
                          frame_limit: int | None = None) -> Dict[str, object]:
    if frame_limit is not None:
        frames = frames[:frame_limit]
    unmasked = [xor_mask(frame, mask_key) for frame in frames]
    crc_flags = []
    valid_frames = []
    for frame in unmasked:
        if len(frame) <= TRAILER_BYTES:
            crc_flags.append(False)
            continue
        body = frame[:-TRAILER_BYTES]
        trailer = frame[-TRAILER_BYTES:]
        expected = trailer[-1] & 0x7F
        ok = crc7(body, polynomial=0x09) == expected
        crc_flags.append(ok)
        if ok:
            valid_frames.append(frame)
    pass_count = sum(crc_flags)
    pass_rate = pass_count / len(unmasked) if unmasked else 0.0
    payload_segments = [frame[:-TRAILER_BYTES] for frame in unmasked if len(frame) > TRAILER_BYTES]
    concatenated = np.concatenate(payload_segments) if payload_segments else np.array([], dtype=np.uint8)
    header = parse_header_bytes(concatenated[:HEADER_BYTES]) if concatenated.size >= HEADER_BYTES else None
    payload_bytes = concatenated[HEADER_BYTES:] if concatenated.size >= HEADER_BYTES else np.array([], dtype=np.uint8)
    varints = decode_varints(payload_bytes.tobytes()) if payload_bytes.size else []
    payload_entries = decode_payload_entries(varints)
    varint_success = (
        sum(1 for entry in payload_entries if entry["opcode"] != "unknown") / len(payload_entries)
        if payload_entries else 0.0
    )
    return {
        "mask_key": mask_key,
        "pass_rate": pass_rate,
        "pass_count": pass_count,
        "frame_count": len(unmasked),
        "valid_frames": valid_frames,
        "header": header,
        "payload_bytes": payload_bytes,
        "varints": varints,
        "payload_entries": payload_entries,
        "varint_success": varint_success,
    }


def decode_burst(frames: Sequence[np.ndarray]) -> Dict[str, object] | None:
    if len(frames) == 0:
        return None
    subset = frames[:MASK_SAMPLE_FRAMES] if MASK_SAMPLE_FRAMES > 0 else frames
    best: Dict[str, object] | None = None
    best_score = -1.0
    for mask_key in range(MASK_SEARCH_START, MASK_SEARCH_END + 1):
        candidate = _apply_mask_to_frames(subset, mask_key)
        header_valid = candidate["header"] is not None
        score = (1.5 if header_valid else 0.0) + candidate["pass_rate"] + candidate["varint_success"]
        if score > best_score:
            best = candidate
            best_score = score
        if header_valid and candidate["pass_rate"] >= 0.95:
            break
    if not best or best_score < MIN_MASK_SCORE:
        return None
    return _apply_mask_to_frames(frames, best["mask_key"])


def build_price_path(header: Dict[str, object], payload_entries: Sequence[Dict[str, object]]) -> Tuple[np.ndarray, np.ndarray]:
    deltas = [entry["value"] for entry in payload_entries if entry["opcode"] == "delta"]
    if not deltas:
        return np.array([], dtype=float), np.array([], dtype=float)
    cumulative = np.cumsum(np.array(deltas, dtype=float) / 10_000.0)
    prices = header["anchor_usd"] + cumulative
    duration = header["duration_seconds"] if header["duration_seconds"] > 0 else len(deltas)
    step = duration / len(deltas)
    time_points = np.arange(len(deltas), dtype=float) * step
    return time_points, prices


def replicate_lag_paths(base_start: pd.Timestamp, time_points: np.ndarray,
                        prices: np.ndarray) -> List[Dict[str, object]]:
    if time_points.size == 0 or prices.size == 0:
        return []
    base_series = base_start + pd.to_timedelta(time_points, unit="s")
    lagged = []
    for label, offset in zip(LAG_LABELS, LAG_OFFSETS_SECONDS):
        lag_times = base_series + pd.to_timedelta(offset, unit="s")
        horizon_end = base_start + pd.to_timedelta(offset + MAX_HORIZON_SECONDS, unit="s")
        mask = lag_times <= horizon_end
        if not np.any(mask):
            continue
        lagged.append(
            {
                "label": label,
                "timestamps": lag_times[mask],
                "prices": prices[mask],
            }
        )
    return lagged

def replicate_macro_lag_paths(base_start: pd.Timestamp, time_points: np.ndarray,
                              prices: np.ndarray) -> List[Dict[str, object]]:
    if time_points.size == 0 or prices.size == 0:
        return []
    base_series = base_start + pd.to_timedelta(time_points, unit="s")
    macro_paths = []
    for label, offset in zip(MACRO_LAG_LABELS, MACRO_LAG_OFFSETS_SECONDS):
        lag_times = base_series + pd.to_timedelta(offset, unit="s")
        macro_paths.append(
            {
                "label": label,
                "timestamps": lag_times,
                "prices": prices,
            }
        )
    return macro_paths


def build_track_id(symbol: str, base_start: pd.Timestamp, mask_key: int) -> str:
    ts = _ensure_timestamp(base_start)
    return f"PT-{symbol}-{ts.strftime('%Y%m%d-%H%M%S')}-{mask_key:02X}"


def write_price_path_csv(label: str, lag_name: str, timestamps: Sequence[pd.Timestamp],
                         prices: Sequence[float]) -> Path:
    PRICE_PATH_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"price_path_{sanitize_label(label)}_{lag_name}.csv"
    path = PRICE_PATH_DIR / filename
    rows = []
    for ts, price in zip(timestamps, prices):
        rows.append({"timestamp": _ensure_timestamp(ts).isoformat(), "price": float(price)})
    pd.DataFrame(rows).to_csv(path, index=False)
    return path




def extract_bitstream(prices: np.ndarray, times: Sequence, resample_rate: int,
                      low_percentile: float, high_percentile: float,
                      debounce_us: float) -> BitstreamResult:
    if prices.size < 10:
        raise ValueError("Not enough samples to build a bitstream")

    t0, t1 = _to_timestamp(times[0]), _to_timestamp(times[-1])
    dt = 1.0 / resample_rate
    samples = max(2, int((t1 - t0) * resample_rate) + 1)
    time_grid = np.linspace(t0, t1, samples)
    price_grid = np.interp(time_grid, [_to_timestamp(t) for t in times], prices)
    price_grid = price_grid - np.median(price_grid)

    analytic = hilbert(price_grid)
    envelope = np.abs(analytic)
    env_min, env_max = envelope.min(), envelope.max()
    if env_max > env_min:
        envelope = (envelope - env_min) / (env_max - env_min)
    else:
        envelope = envelope - env_min

    low = np.percentile(envelope, low_percentile)
    high = np.percentile(envelope, high_percentile)
    if high > 0:
        low = max(low, high * 0.05)
        if low >= high:
            low = high * 0.5
    debounce_secs = debounce_us / 1e6

    bitstream = np.zeros_like(envelope, dtype=np.int8)
    state = 0
    for idx, sample in enumerate(envelope):
        if sample >= high:
            state = 1
        elif sample <= low:
            state = 0
        bitstream[idx] = state

    # Debounce tiny pulses
    if bitstream.size > 0:
        padded = np.pad(bitstream, (1, 1), mode="edge")
        diff = np.diff(padded)
        starts = np.where(diff == 1)[0]
        ends = np.where(diff == -1)[0]
        debounce_samples = max(1, int(debounce_secs / dt))
        for s, e in zip(starts, ends):
            if (e - s) < debounce_samples:
                bitstream[s:e] = 0

    return BitstreamResult(
        bitstream=bitstream,
        time_grid=time_grid,
        envelope=envelope,
        low_threshold=float(low),
        high_threshold=float(high),
        debounce_seconds=float(debounce_secs),
    )


def bits_to_frames(bitstream: np.ndarray, frame_bits: int, offset_bits: int,
                   bit_order: str = "big", max_frames: int | None = None) -> List[np.ndarray]:
    trimmed = bitstream[offset_bits:]
    total_frames = len(trimmed) // frame_bits
    if total_frames == 0:
        return []
    if max_frames is not None:
        total_frames = max(0, min(total_frames, max_frames))
    frames = []
    for start in range(0, total_frames * frame_bits, frame_bits):
        chunk = trimmed[start:start + frame_bits]
        bytes_out = []
        for i in range(0, frame_bits, 8):
            byte_bits = chunk[i:i + 8]
            if len(byte_bits) < 8:
                break
            if bit_order == "big":
                val = 0
                for bit in byte_bits:
                    val = (val << 1) | int(bit)
            else:
                val = 0
                for pos, bit in enumerate(byte_bits):
                    val |= (int(bit) & 1) << pos
            bytes_out.append(val)
        if bytes_out:
            frames.append(np.array(bytes_out, dtype=np.uint8))
    return frames


def score_headers(frames: Sequence[np.ndarray], sample: int = 50) -> Tuple[float, int, float, List[int]]:
    headers = [tuple(fr[:HEADER_BYTES]) for fr in frames[:sample] if len(fr) >= HEADER_BYTES]
    if not headers:
        return 0.0, 0, 0.0, []
    unique_headers = set(headers)
    trivial = sum(1 for h in headers if all(b in (0x00, 0xFF) for b in h))
    variety = max(0, len(unique_headers) - trivial)
    header_series = pd.Series(headers)
    probs = header_series.value_counts(normalize=True).to_numpy()
    entropy = float(-np.sum(probs * np.log2(probs))) if probs.size else 0.0
    return variety + entropy, variety, entropy, list(headers[0])


def verify_alignment(bitstream: np.ndarray, frame_bits: int,
                     sample_frames: int = ALIGNMENT_SAMPLE_FRAMES) -> AlignmentResult:
    if bitstream.size < frame_bits:
        raise RuntimeError("Bitstream shorter than a single frame")

    sample_frames = max(1, sample_frames)
    sample_bits = frame_bits * sample_frames
    streams = {
        "normal": bitstream,
        "inverted": 1 - bitstream,
    }

    best_result: AlignmentResult | None = None
    best_params: Tuple[str, str, int] | None = None

    for polarity, stream in streams.items():
        sample_stream = stream[:sample_bits]
        for bit_order in ("big", "little"):
            for offset in range(frame_bits):
                frames = bits_to_frames(sample_stream, frame_bits, offset, bit_order, max_frames=sample_frames)
                if not frames:
                    continue
                score, variety, entropy, example = score_headers(frames)
                if best_result is None or score > best_result.score:
                    best_result = AlignmentResult(
                        frames=np.array(frames),
                        polarity=polarity,
                        bit_order=bit_order,
                        frame_bits=frame_bits,
                        offset_bits=offset,
                        score=score,
                        header_variety=variety,
                        header_entropy=entropy,
                        example_header=example,
                    )
                    best_params = (polarity, bit_order, offset)

    if best_result is None or best_params is None:
        raise RuntimeError("Unable to find any frame alignment")

    polarity, bit_order, offset = best_params
    full_stream = streams[polarity]
    full_frames = bits_to_frames(full_stream, frame_bits, offset, bit_order)
    best_result.frames = np.array(full_frames)
    return best_result


def crc7(data: Sequence[int], polynomial: int = 0x09) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ (polynomial << 1)) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return (crc >> 1) & 0x7F


def build_synthetic_frames(num_frames: int = 4, payload_bytes: int = 8) -> np.ndarray:
    header = np.array([0x7F, 0xA5, 0x5A, 0x3C, 0xC3, 0x12], dtype=np.uint8)
    frames = []
    for idx in range(num_frames):
        payload = np.arange(payload_bytes, dtype=np.uint8) + idx
        crc_input = np.concatenate([header, payload])
        crc_val = crc7(crc_input)
        trailer = np.array([crc_val | 0x80], dtype=np.uint8)
        frame = np.concatenate([header, payload, trailer])
        frames.append(frame)
    return np.array(frames)


def frames_to_bitstream(frames: np.ndarray, bit_order: str = "big") -> np.ndarray:
    bits: List[int] = []
    for frame in frames:
        for byte in frame:
            if bit_order == "big":
                bits.extend([(byte >> shift) & 1 for shift in range(7, -1, -1)])
            else:
                bits.extend([(byte >> shift) & 1 for shift in range(8)])
    return np.array(bits, dtype=np.int8)


def test_synthetic_pipeline(bit_order: str = "big") -> SyntheticResult:
    injected = build_synthetic_frames()
    bitstream = frames_to_bitstream(injected, bit_order=bit_order)
    recovered_frames = bits_to_frames(bitstream, injected.shape[1] * 8, 0, bit_order)
    recovered = np.array(recovered_frames)
    crc_matches = True
    for frame in recovered:
        body = frame[:-1]
        crc_expected = frame[-1] & 0x7F
        crc_matches &= crc_expected == crc7(body)
    return SyntheticResult(
        injected_frames=injected,
        recovered_frames=recovered,
        crc_matches=bool(crc_matches),
        frame_bytes=injected.shape[1],
    )


def evaluate_masks(frames: np.ndarray, masks: Iterable[int]) -> List[Dict[str, float]]:
    results = []
    for mask in masks:
        unm = np.bitwise_xor(frames, mask).astype(np.uint8)
        payload = unm[:, HEADER_BYTES:-TRAILER_BYTES] if unm.shape[1] > HEADER_BYTES + TRAILER_BYTES else np.empty((len(unm), 0))
        unique_payload = len({tuple(row) for row in payload}) if payload.size else 0
        zero_ratio = float(np.mean(unm == 0)) if unm.size else 0.0
        results.append({
            "mask": mask,
            "unique_payloads": unique_payload,
            "zero_ratio": zero_ratio,
        })
    return results


def tap_raw_line(time_grid: np.ndarray, envelope: np.ndarray, bitstream: np.ndarray,
                 target_path: Path, limit: int = 2500) -> Path:
    rows = min(limit, len(time_grid))
    tap_df = pd.DataFrame({
        "timestamp": time_grid[:rows],
        "envelope": envelope[:rows],
        "bit_state": bitstream[:rows],
    })
    tap_df.to_csv(target_path, index=False)
    return target_path


def default_serializer(value):
    if isinstance(value, (int, float, str)):
        return value
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return str(value)


def sanitize_label(value: str) -> str:
    """Sanitize a label string for use in filenames/paths."""
    if value is None:
        return "unknown"
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(value))


def analyze_tick_window(window_df: pd.DataFrame, label: str) -> Dict[str, object]:
    summary = {
        "label": label,
        "tick_count": int(len(window_df)),
        "status": "ok",
    }

    if len(window_df) < 20:
        summary["status"] = "insufficient_ticks"
        return summary

    df_sorted = safe_sort_timestamp(window_df).reset_index(drop=True)
    prices = df_sorted["price"].to_numpy()
    times = df_sorted["timestamp"].to_numpy()

    spectral_power = compute_spectral_power(prices, times, FREQ_BAND)
    roc_value = calculate_roc(prices, times, ROC_LOOKBACK_SECONDS)
    summary["detection"] = {
        "spectral_power": spectral_power,
        "roc_value": roc_value,
        "power_threshold": POWER_THRESHOLD,
        "roc_threshold": ROC_THRESHOLD,
        "meets_dual_trigger": spectral_power >= POWER_THRESHOLD and roc_value >= ROC_THRESHOLD,
        "window_seconds": float((_to_timestamp(times[-1]) - _to_timestamp(times[0]))),
    }

    if "venue" in df_sorted.columns:
        venue_counts = df_sorted["venue"].astype(str).value_counts()
        summary["venues"] = {
            "unique": int(venue_counts.size),
            "top": {venue: int(count) for venue, count in venue_counts.head(10).items()},
        }

    try:
        bit_info = extract_bitstream(prices, times, RESAMPLE_RATE, LOW_PERCENTILE, HIGH_PERCENTILE, DEBOUNCE_US)
    except ValueError as exc:
        summary["status"] = "bitstream_error"
        summary["error"] = str(exc)
        return summary

    try:
        alignment = verify_alignment(bit_info.bitstream, FRAME_BITS)
    except RuntimeError as exc:
        summary["status"] = "alignment_error"
        summary["error"] = str(exc)
        summary["bitstream"] = {
            "length": int(len(bit_info.bitstream)),
            "ones_ratio": float(bit_info.bitstream.mean()),
        }
        return summary

    mask_metrics = evaluate_masks(alignment.frames, MASK_RANGE)
    best_mask = max(mask_metrics, key=lambda m: m["unique_payloads"]) if mask_metrics else None

    tap_name = RAW_TAP_PATH.with_name(f"raw_line_tap_{sanitize_label(label)}.csv")
    tap_path = tap_raw_line(bit_info.time_grid, bit_info.envelope, bit_info.bitstream, tap_name)

    symbol_series = df_sorted["symbol"] if "symbol" in df_sorted.columns else None
    symbol_value = (
        symbol_series.mode().iat[0]
        if symbol_series is not None and not symbol_series.empty
        else POLYGON_SYMBOL
    )

    summary.update(
        {
            "bitstream": {
                "length": int(len(bit_info.bitstream)),
                "ones_ratio": float(bit_info.bitstream.mean()),
                "low_threshold": bit_info.low_threshold,
                "high_threshold": bit_info.high_threshold,
                "debounce_seconds": bit_info.debounce_seconds,
            },
            "alignment": {
                "polarity": alignment.polarity,
                "bit_order": alignment.bit_order,
                "frame_bits": alignment.frame_bits,
                "offset_bits": alignment.offset_bits,
                "score": alignment.score,
                "header_variety": alignment.header_variety,
                "header_entropy": alignment.header_entropy,
                "example_header": alignment.example_header,
                "frames_sampled": min(200, int(len(alignment.frames))),
            },
            "whitening": mask_metrics,
            "best_mask": best_mask,
            "tap_file": str(tap_path.relative_to(Path.cwd())),
            "decoding": {
                "mask_found": False,
                "mask_candidate": None,
                "crc_pass_rate": 0.0,
                "varint_success": 0.0,
                "valid_frames": 0,
                "sample_varints": [],
            },
            "unfolding": {},
        }
    )

    # Use internal Python decoder instead of Node.js script
    decoded_burst = decode_burst(alignment.frames)

    if decoded_burst:
        header = decoded_burst.get("header")
        
        # Build price path sample if header is valid
        price_path_sample = []
        if header:
            t_points, p_values = build_price_path(header, decoded_burst["payload_entries"])
            # formatted for consistency with the rest of the pipeline
            price_path_sample = [
                {"step": float(t), "price": float(p)} 
                for t, p in zip(t_points, p_values)
            ]

        summary["decoding"].update(
            {
                "mask_found": True,
                "mask_candidate": decoded_burst["mask_key"],
                "crc_pass_rate": decoded_burst["pass_rate"],
                "varint_success": decoded_burst["varint_success"],
                "valid_frames": decoded_burst["pass_count"],
                "sample_varints": decoded_burst["varints"],
                "header": header,
                "price_path_sample": price_path_sample,
                "total_frames": decoded_burst["frame_count"],
            }
        )

        if header and price_path_sample:
            time_points = np.array([entry["step"] for entry in price_path_sample], dtype=float)
            price_series = np.array([entry["price"] for entry in price_path_sample], dtype=float)
            detection_day = _ensure_timestamp(df_sorted["timestamp"].iloc[0]).normalize()
            # Header maps startTimeUs (little endian from bytes) -> we need to support start_time_us key
            start_us = header.get("start_time_us", header.get("startTimeMs", 0) * 1000)
            base_start = detection_day + pd.to_timedelta(start_us, unit="us")
            
            lagged_paths = replicate_lag_paths(base_start, time_points, price_series)
            macro_lag_paths = replicate_macro_lag_paths(base_start, time_points, price_series)
            lag_counts = {entry["label"]: int(len(entry["prices"])) for entry in lagged_paths}
            macro_lag_counts = {entry["label"]: int(len(entry["prices"])) for entry in macro_lag_paths}
            price_path_files = []
            macro_price_path_files = []
            for entry in lagged_paths:
                try:
                    file_path = write_price_path_csv(label, entry["label"], entry["timestamps"], entry["prices"])
                    price_path_files.append(str(file_path.relative_to(Path.cwd())))
                except Exception:
                    continue
            for entry in macro_lag_paths:
                try:
                    macro_label = f"macro_{entry['label']}"
                    file_path = write_price_path_csv(label, macro_label, entry["timestamps"], entry["prices"])
                    macro_price_path_files.append(str(file_path.relative_to(Path.cwd())))
                except Exception:
                    continue
            
            track_id = build_track_id(symbol_value, base_start, decoded_burst["mask_key"])
            summary["unfolding"] = {
                "track_id": track_id,
                "anchor_usd": header.get("anchor_usd", 0.0),
                "duration_seconds": header.get("duration_seconds", 0),
                "compression_ratio": header.get("compression_ratio", 0),
                "delta_points": int(len(price_series)),
                "lagged_paths": len(lagged_paths),
                "lag_counts": lag_counts,
                "macro_lag_counts": macro_lag_counts,
                "price_path_files": price_path_files,
                "macro_price_path_files": macro_price_path_files,
                "macro_lag_paths": [
                    {
                        "label": entry["label"],
                        "timestamps": [ts.isoformat() for ts in entry["timestamps"]],
                        "prices": [float(price) for price in entry["prices"]],
                    }
                    for entry in macro_lag_paths
                ],
                "price_path_preview": [float(val) for val in price_series[:5]],
            }

    return summary


def main() -> None:
    print("⚙️  Loading waveform data...")
    if DATA_SOURCE == "polygon":
        tick_windows, detection_meta = prepare_polygon_windows()
        source_desc = f"polygon:{POLYGON_SYMBOL}:{POLYGON_DATE}"
    else:
        tick_windows, detection_meta = prepare_csv_window()
        source_desc = f"csv:{CSV_FILE_PATH}"

    if not tick_windows:
        raise RuntimeError("No tick windows available for analysis")

    print(f"   • Data source: {source_desc} ({len(tick_windows)} candidate window(s))")

    print("⚙️  Injecting synthetic payload to sanity-check CRC path...")
    synthetic = test_synthetic_pipeline()
    print(
        f"   • Synthetic frames: {synthetic.injected_frames.shape[0]}x{synthetic.frame_bytes} bytes, "
        f"CRC valid={synthetic.crc_matches}"
    )

    window_results = []
    for idx, window in enumerate(tick_windows, start=1):
        meta = window["meta"]
        start = meta.get("chunk_start", meta.get("window_start"))
        end = meta.get("chunk_end", meta.get("window_end"))
        chunk_idx = meta.get("chunk_index")
        chunk_label = f" segment {chunk_idx}" if chunk_idx is not None else ""
        print(f"⚙️  Analyzing window {idx}{chunk_label} ({start} – {end})...")
        label = f"{source_desc}_w{idx}"
        if chunk_idx is not None:
            label = f"{label}c{chunk_idx}"
        result = analyze_tick_window(window["ticks"], label)
        result["meta"] = window["meta"]
        window_results.append(result)

    report = {
        "data_source": source_desc,
        "window_count": len(window_results),
        "detection_meta": detection_meta,
        "window_results": window_results,
        "synthetic_check": {
            "frame_bytes": synthetic.frame_bytes,
            "frame_count": int(len(synthetic.injected_frames)),
            "crc_matches": synthetic.crc_matches,
        },
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2, default=default_serializer))
    print(f"✅ Wrote diagnostics report to {REPORT_PATH.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
