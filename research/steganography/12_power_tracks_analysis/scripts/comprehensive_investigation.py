#!/usr/bin/env python3
"""
Comprehensive GME Pattern Investigation
========================================

Investigates the GME varint pattern anomaly with 3 approaches:
1. Time window analysis (pre-market vs regular hours)
2. Meme stock comparison (AMC, KOSS, BB)
3. Historical GME data (2021 squeeze era)
"""

import sys
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from scipy import stats
import requests

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "samples"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "results"


def load_api_key() -> str:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.startswith("POLYGON_API_KEY="):
                    return line.strip().split("=", 1)[1]
    return ""


def fetch_minute_bars(symbol: str, date: str, api_key: str) -> pd.DataFrame:
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{date}/{date}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key}
    resp = requests.get(url, params=params, timeout=30)
    if resp.status_code != 200:
        return pd.DataFrame()
    results = resp.json().get("results", [])
    if not results:
        return pd.DataFrame()
    df = pd.DataFrame(results)
    df = df.rename(columns={"c": "price", "t": "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def zig_zag_encode(value: int) -> int:
    return (value << 1) ^ (value >> 63)


def encode_varint(value: int) -> list:
    remaining = max(0, value)
    out = []
    while remaining >= 0x80:
        out.append(int((remaining & 0x7F) | 0x80))
        remaining >>= 7
    out.append(int(remaining))
    return out


def decode_varint(data: bytes) -> tuple:
    value = 0
    shift = 0
    for i, b in enumerate(data):
        value |= (b & 0x7F) << shift
        if not (b & 0x80):
            return value, i + 1
        shift += 7
    return value, len(data)


def extract_slack_bits(prices: list) -> dict:
    if len(prices) < 10:
        return {"error": "Insufficient"}
    
    PRICE_SCALE = 10_000
    deltas = []
    prev = int(prices[0] * PRICE_SCALE)
    for price in prices[1:]:
        target = int(price * PRICE_SCALE)
        deltas.append(target - prev)
        prev = target
    
    payload_bytes = []
    for delta in deltas:
        payload_bytes.extend(encode_varint(zig_zag_encode(delta)))
    
    encoded = bytes(payload_bytes)
    
    hidden_bits = []
    offset = 0
    for delta in deltas:
        if offset >= len(encoded):
            break
        varint_val, bytes_used = decode_varint(encoded[offset:])
        max_for_bytes = (1 << (7 * bytes_used)) - 1
        min_for_bytes = 0 if bytes_used == 1 else (1 << (7 * (bytes_used - 1)))
        if max_for_bytes > min_for_bytes:
            position = (varint_val - min_for_bytes) / (max_for_bytes - min_for_bytes)
            slack_value = int(position * 255)
            for i in range(8):
                hidden_bits.append((slack_value >> (7 - i)) & 1)
        offset += bytes_used
    
    return {
        "extracted_bits": hidden_bits[:256],
        "ones_ratio": sum(hidden_bits) / len(hidden_bits) if hidden_bits else 0
    }


def analyze_bits(bits: list) -> dict:
    if len(bits) < 16:
        return {}
    bits = np.array(bits)
    ones_ratio = bits.mean()
    observed = np.bincount(bits, minlength=2)
    expected = np.full(2, len(bits) / 2)
    chi2, pval = stats.chisquare(observed, expected)
    autocorr = np.corrcoef(bits[:-1], bits[1:])[0, 1] if len(bits) > 10 else 0
    return {
        "ones_ratio": float(ones_ratio),
        "chi2_pvalue": float(pval),
        "random": bool(pval > 0.05),
        "autocorrelation": float(autocorr) if not np.isnan(autocorr) else 0
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    api_key = load_api_key()
    
    print("=" * 70)
    print("COMPREHENSIVE GME PATTERN INVESTIGATION")
    print("=" * 70)
    
    results = {}
    
    # ============================================================
    # PART 1: TIME WINDOW ANALYSIS
    # ============================================================
    print("\n" + "=" * 70)
    print("PART 1: TIME WINDOW ANALYSIS (Pre-market vs Regular)")
    print("=" * 70)
    
    results["time_windows"] = {}
    date = "2024-05-13"
    
    df = fetch_minute_bars("GME", date, api_key)
    if not df.empty:
        df["hour"] = df["timestamp"].dt.hour
        
        # Pre-market: 4:00-9:30 (hour < 10 in UTC-4 = hour < 14 UTC)
        premarket = df[df["hour"] < 13]  # Approximate
        regular = df[(df["hour"] >= 13) & (df["hour"] < 20)]
        afterhours = df[df["hour"] >= 20]
        
        for name, subset in [("premarket", premarket), ("regular", regular), ("afterhours", afterhours)]:
            if len(subset) >= 50:
                prices = subset["price"].dropna().tolist()
                extraction = extract_slack_bits(prices[:200])
                if "extracted_bits" in extraction:
                    analysis = analyze_bits(extraction["extracted_bits"])
                    results["time_windows"][name] = {
                        "n_bars": len(subset),
                        "ones_ratio": extraction["ones_ratio"],
                        **analysis
                    }
                    print(f"  {name}: {len(subset)} bars, ones={extraction['ones_ratio']:.3f}")
    
    # ============================================================
    # PART 2: MEME STOCK COMPARISON
    # ============================================================
    print("\n" + "=" * 70)
    print("PART 2: MEME STOCK COMPARISON")
    print("=" * 70)
    
    results["meme_stocks"] = {}
    meme_symbols = ["GME", "AMC", "KOSS", "BB", "BBBY"]
    dates = ["2024-05-13", "2024-05-14", "2024-05-15"]
    
    for symbol in meme_symbols:
        all_bits = []
        for date in dates:
            df = fetch_minute_bars(symbol, date, api_key)
            if not df.empty and len(df) >= 50:
                prices = df["price"].dropna().tolist()
                extraction = extract_slack_bits(prices[:200])
                if "extracted_bits" in extraction:
                    all_bits.extend(extraction["extracted_bits"])
        
        if all_bits:
            analysis = analyze_bits(all_bits)
            results["meme_stocks"][symbol] = {
                "n_bits": len(all_bits),
                **analysis
            }
            print(f"  {symbol}: ones={analysis['ones_ratio']:.3f}, autocorr={analysis['autocorrelation']:.3f}")
    
    # ============================================================
    # PART 3: HISTORICAL GME (2021 Squeeze Era)
    # ============================================================
    print("\n" + "=" * 70)
    print("PART 3: HISTORICAL GME (2021 vs 2024)")
    print("=" * 70)
    
    results["historical"] = {}
    
    # Check for local 2021 data
    local_2021 = DATA_DIR / "samples" / "local" / "polygon" / "gme" / "2021-01-27" / "trades.json"
    if not local_2021.exists():
        # Try to fetch from API
        historical_dates = {
            "2021-01-27": "squeeze_peak",
            "2021-01-28": "squeeze_halt",
            "2021-02-24": "second_spike",
            "2024-05-13": "current_era"
        }
        
        for date, label in historical_dates.items():
            df = fetch_minute_bars("GME", date, api_key)
            if not df.empty and len(df) >= 50:
                prices = df["price"].dropna().tolist()
                extraction = extract_slack_bits(prices[:200])
                if "extracted_bits" in extraction:
                    analysis = analyze_bits(extraction["extracted_bits"])
                    results["historical"][label] = {
                        "date": date,
                        "n_bars": len(df),
                        "ones_ratio": extraction["ones_ratio"],
                        **analysis
                    }
                    print(f"  {label} ({date}): ones={extraction['ones_ratio']:.3f}")
    else:
        print("  Using local 2021 data...")
    
    # ============================================================
    # SUMMARY
    # ============================================================
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    # Save results
    with open(OUTPUT_DIR / "comprehensive_investigation.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": results
        }, f, indent=2)
    
    # Generate report
    with open(OUTPUT_DIR / "comprehensive_investigation_report.md", "w") as f:
        f.write("# Comprehensive GME Pattern Investigation\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Part 1: Time Window Analysis\n\n")
        f.write("| Window | Bars | Ones Ratio | Autocorr |\n")
        f.write("|--------|------|------------|----------|\n")
        for name, data in results.get("time_windows", {}).items():
            f.write(f"| {name} | {data.get('n_bars', 0)} | {data.get('ones_ratio', 0):.3f} | {data.get('autocorrelation', 0):.3f} |\n")
        
        f.write("\n## Part 2: Meme Stock Comparison\n\n")
        f.write("| Symbol | Ones Ratio | Autocorr | Random? |\n")
        f.write("|--------|------------|----------|--------|\n")
        for symbol, data in sorted(results.get("meme_stocks", {}).items(), key=lambda x: x[1].get("ones_ratio", 0), reverse=True):
            rand = "✓" if data.get("random") else ""
            f.write(f"| {symbol} | {data.get('ones_ratio', 0):.3f} | {data.get('autocorrelation', 0):.3f} | {rand} |\n")
        
        f.write("\n## Part 3: Historical GME\n\n")
        f.write("| Period | Date | Ones Ratio | Autocorr |\n")
        f.write("|--------|------|------------|----------|\n")
        for label, data in results.get("historical", {}).items():
            f.write(f"| {label} | {data.get('date', '')} | {data.get('ones_ratio', 0):.3f} | {data.get('autocorrelation', 0):.3f} |\n")
        
        f.write("\n## Key Findings\n\n")
        
        # Time window analysis
        tw = results.get("time_windows", {})
        if "premarket" in tw and "regular" in tw:
            pm = tw["premarket"]["ones_ratio"]
            reg = tw["regular"]["ones_ratio"]
            if pm > reg:
                f.write(f"- **Pre-market more random** (ones: {pm:.3f}) than regular hours ({reg:.3f})\n")
            else:
                f.write(f"- **Regular hours more random** (ones: {reg:.3f}) than pre-market ({pm:.3f})\n")
        
        # Meme stock comparison
        meme = results.get("meme_stocks", {})
        if meme:
            sorted_meme = sorted(meme.items(), key=lambda x: x[1].get("ones_ratio", 0), reverse=True)
            f.write(f"- **Most random meme stock**: {sorted_meme[0][0]} (ones: {sorted_meme[0][1]['ones_ratio']:.3f})\n")
            f.write(f"- **Least random meme stock**: {sorted_meme[-1][0]} (ones: {sorted_meme[-1][1]['ones_ratio']:.3f})\n")
        
        # Historical
        hist = results.get("historical", {})
        if "squeeze_peak" in hist and "current_era" in hist:
            squeeze = hist["squeeze_peak"]["ones_ratio"]
            current = hist["current_era"]["ones_ratio"]
            if abs(squeeze - current) > 0.1:
                f.write(f"- **Significant difference**: 2021 squeeze ({squeeze:.3f}) vs 2024 ({current:.3f})\n")
            else:
                f.write(f"- **Similar pattern**: 2021 squeeze ({squeeze:.3f}) ≈ 2024 ({current:.3f})\n")
    
    print("INVESTIGATION COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
