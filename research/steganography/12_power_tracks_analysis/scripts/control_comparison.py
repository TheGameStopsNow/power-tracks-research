#!/usr/bin/env python3
"""
Power Tracks Control Comparison
================================

Compares varint slack patterns between GME and control symbols (SPY)
to determine if the non-random patterns are GME-specific or a general
artifact of the encoding.
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
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "results"


def load_api_key() -> str:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.startswith("POLYGON_API_KEY="):
                    return line.strip().split("=", 1)[1]
    return ""


def fetch_trades(symbol: str, date: str, api_key: str, limit: int = 1000) -> pd.DataFrame:
    """Fetch trades from Polygon API."""
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{date}/{date}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key}
    
    resp = requests.get(url, params=params, timeout=30)
    if resp.status_code != 200:
        return pd.DataFrame()
    
    results = resp.json().get("results", [])
    if not results:
        return pd.DataFrame()
    
    df = pd.DataFrame(results)
    df = df.rename(columns={"c": "price"})
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
    """Extract slack bits from price sequence."""
    if len(prices) < 10:
        return {"error": "Insufficient prices"}
    
    PRICE_SCALE = 10_000
    
    # Calculate deltas
    deltas = []
    prev = int(prices[0] * PRICE_SCALE)
    for price in prices[1:]:
        target = int(price * PRICE_SCALE)
        deltas.append(target - prev)
        prev = target
    
    # Encode as varints
    payload_bytes = []
    for delta in deltas:
        payload_bytes.extend(encode_varint(zig_zag_encode(delta)))
    
    encoded = bytes(payload_bytes)
    
    # Calculate optimal vs actual
    optimal_bits = 0
    for delta in deltas:
        enc = zig_zag_encode(delta)
        if enc == 0:
            optimal_bits += 1
        else:
            optimal_bits += max(1, int(np.ceil(np.log2(enc + 1))))
    
    actual_bits = len(encoded) * 7
    slack_bits = actual_bits - optimal_bits
    
    # Extract hidden bits
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
        "n_prices": len(prices),
        "slack_bits": slack_bits,
        "extracted_bits": hidden_bits[:256],
        "ones_ratio": sum(hidden_bits) / len(hidden_bits) if hidden_bits else 0
    }


def analyze_bits(bits: list) -> dict:
    """Statistical analysis of bits."""
    if len(bits) < 16:
        return {}
    
    bits = np.array(bits)
    ones_ratio = bits.mean()
    
    observed = np.bincount(bits, minlength=2)
    expected = np.full(2, len(bits) / 2)
    chi2, pval = stats.chisquare(observed, expected)
    
    runs = 1
    for i in range(1, len(bits)):
        if bits[i] != bits[i-1]:
            runs += 1
    
    n0, n1 = (bits == 0).sum(), (bits == 1).sum()
    expected_runs = 1 + 2 * n0 * n1 / len(bits)
    runs_ratio = runs / expected_runs if expected_runs > 0 else 1
    
    autocorr = np.corrcoef(bits[:-1], bits[1:])[0, 1] if len(bits) > 10 else 0
    
    return {
        "ones_ratio": float(ones_ratio),
        "chi2": float(chi2),
        "chi2_pvalue": float(pval),
        "random": bool(pval > 0.05),
        "runs_ratio": float(runs_ratio),
        "autocorrelation": float(autocorr) if not np.isnan(autocorr) else 0
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    api_key = load_api_key()
    
    print("=" * 70)
    print("POWER TRACKS CONTROL COMPARISON")
    print("GME vs SPY varint slack patterns")
    print("=" * 70)
    
    # Test dates
    dates = ["2024-05-13", "2024-05-14", "2024-05-15", "2024-05-16", "2024-05-17"]
    symbols = ["GME", "SPY", "AAPL", "TSLA", "MSFT"]
    
    results = {}
    
    for symbol in symbols:
        print(f"\n>>> {symbol}")
        results[symbol] = {"days": [], "all_bits": []}
        
        for date in dates:
            df = fetch_trades(symbol, date, api_key)
            
            if df.empty or len(df) < 100:
                continue
            
            prices = df["price"].dropna().head(200).tolist()
            
            extraction = extract_slack_bits(prices)
            if "error" in extraction:
                continue
            
            analysis = analyze_bits(extraction["extracted_bits"])
            
            results[symbol]["days"].append({
                "date": date,
                "slack_bits": extraction["slack_bits"],
                "ones_ratio": extraction["ones_ratio"],
                **analysis
            })
            results[symbol]["all_bits"].extend(extraction["extracted_bits"])
            
            print(f"  {date}: ones={extraction['ones_ratio']:.3f}, random={analysis.get('random', 'N/A')}")
        
        # Aggregate analysis
        if results[symbol]["all_bits"]:
            agg = analyze_bits(results[symbol]["all_bits"])
            results[symbol]["aggregate"] = agg
            print(f"  AGGREGATE: ones={agg['ones_ratio']:.3f}, autocorr={agg['autocorrelation']:.3f}")
    
    # Compare GME to controls
    print("\n" + "=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)
    
    comparison = {}
    for symbol, data in results.items():
        if "aggregate" in data:
            comparison[symbol] = {
                "ones_ratio": data["aggregate"]["ones_ratio"],
                "autocorrelation": data["aggregate"]["autocorrelation"],
                "random": data["aggregate"]["random"],
                "n_bits": len(data["all_bits"])
            }
            print(f"{symbol}: ones={comparison[symbol]['ones_ratio']:.3f}, autocorr={comparison[symbol]['autocorrelation']:.3f}, random={comparison[symbol]['random']}")
    
    # Save results
    with open(OUTPUT_DIR / "control_comparison.json", "w") as f:
        # Filter out all_bits for JSON (too large)
        save_data = {}
        for sym, data in results.items():
            save_data[sym] = {
                "days": data["days"],
                "aggregate": data.get("aggregate", {})
            }
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "comparison": comparison,
            "results": save_data
        }, f, indent=2)
    
    # Generate report
    with open(OUTPUT_DIR / "control_comparison_report.md", "w") as f:
        f.write("# Power Tracks Control Comparison\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Comparison: GME vs Controls\n\n")
        f.write("| Symbol | Ones Ratio | Autocorr | Random? | Bits |\n")
        f.write("|--------|------------|----------|---------|------|\n")
        for sym, data in sorted(comparison.items()):
            rand = "✓" if data["random"] else ""
            f.write(f"| {sym} | {data['ones_ratio']:.3f} | {data['autocorrelation']:.3f} | {rand} | {data['n_bits']} |\n")
        
        f.write("\n## Interpretation\n\n")
        
        # Check if GME is unique
        gme_ones = comparison.get("GME", {}).get("ones_ratio", 0.5)
        spy_ones = comparison.get("SPY", {}).get("ones_ratio", 0.5)
        
        if abs(gme_ones - spy_ones) < 0.1:
            f.write("> ✅ **GME and SPY show similar patterns** - anomaly is likely a natural encoding artifact\n")
        else:
            f.write(f"> ⚠️ **GME differs from SPY** (ones: {gme_ones:.3f} vs {spy_ones:.3f}) - pattern may be GME-specific\n")
    
    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
