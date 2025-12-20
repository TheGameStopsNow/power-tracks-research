#!/usr/bin/env python3
"""
Steganography Research: Control Sample Analysis
================================================

Fetches SPY data from Polygon API and runs the same LSB/timing analysis
to compare against GME findings. This validates whether observed patterns
are GME-specific or general market microstructure artifacts.
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import json

import pandas as pd
import numpy as np
from scipy import stats
from scipy.stats import entropy
import requests

# Configuration
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "samples"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "control_samples" / "results"

# Load API key from .env
def load_api_key() -> str:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.startswith("POLYGON_API_KEY="):
                    return line.strip().split("=", 1)[1]
    return os.getenv("POLYGON_API_KEY", "")


def fetch_minute_bars(symbol: str, date: str, api_key: str) -> pd.DataFrame:
    """Fetch minute bars from Polygon API."""
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{date}/{date}"
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 50000,
        "apiKey": api_key,
    }
    
    print(f"  Fetching {symbol} bars for {date}...")
    records = []
    while True:
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("results", []))
        next_url = data.get("next_url")
        if not next_url:
            break
        url = next_url
        params = {"apiKey": api_key}
    
    if not records:
        return pd.DataFrame()
    
    df = pd.DataFrame(records)
    df = df.rename(columns={
        "v": "volume",
        "o": "open",
        "c": "close",
        "h": "high",
        "l": "low",
        "t": "timestamp",
        "n": "transactions",
    })
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def extract_price_lsb(prices: pd.Series, decimal_places: int = 2) -> np.ndarray:
    """Extract LSB from price data."""
    multiplier = 10 ** decimal_places
    scaled = (prices * multiplier).astype(int)
    return scaled % 10


def chi_square_test(lsb_values: np.ndarray) -> dict:
    """Test if LSB distribution is uniform."""
    observed = np.bincount(lsb_values, minlength=10)
    expected = np.full(10, len(lsb_values) / 10)
    chi2, p_value = stats.chisquare(observed, expected)
    
    return {
        "chi2_statistic": float(chi2),
        "p_value": float(p_value),
        "significant": bool(p_value < 0.05)
    }


def calculate_entropy(lsb_values: np.ndarray) -> float:
    """Calculate normalized entropy."""
    _, counts = np.unique(lsb_values, return_counts=True)
    probs = counts / len(lsb_values)
    h = entropy(probs, base=2)
    max_entropy = np.log2(10)
    return float(h / max_entropy)


def benford_test(prices: pd.Series) -> dict:
    """Test against Benford's Law."""
    first_digits = []
    for p in prices:
        if p > 0:
            s = f"{p:.10f}".lstrip('0').replace('.', '')
            if s:
                first_digits.append(int(s[0]))
    
    if not first_digits:
        return {"error": "No valid prices"}
    
    first_digits = np.array(first_digits)
    observed = np.bincount(first_digits, minlength=10)[1:10]
    benford_expected = np.array([np.log10(1 + 1/d) for d in range(1, 10)])
    expected = benford_expected * len(first_digits)
    
    chi2, p_value = stats.chisquare(observed, expected)
    
    return {
        "chi2_statistic": float(chi2),
        "p_value": float(p_value),
        "significant_deviation": bool(p_value < 0.05)
    }


def analyze_symbol(symbol: str, dates: list, api_key: str) -> dict:
    """Run full analysis on a symbol."""
    results = []
    
    for date in dates:
        print(f"\nAnalyzing {symbol} on {date}...")
        try:
            df = fetch_minute_bars(symbol, date, api_key)
            
            if df.empty:
                print(f"  No data returned")
                results.append({"date": date, "error": "No data"})
                continue
            
            prices = df["close"].dropna()
            volumes = df["volume"].dropna()
            
            price_lsb = extract_price_lsb(prices)
            volume_lsb = (volumes.astype(int) % 10).values
            
            result = {
                "date": date,
                "total_bars": len(df),
                "price_lsb_chi2": chi_square_test(price_lsb),
                "volume_lsb_chi2": chi_square_test(volume_lsb),
                "price_entropy": calculate_entropy(price_lsb),
                "benford": benford_test(prices)
            }
            results.append(result)
            
            print(f"  Bars: {len(df)}")
            print(f"  Price LSB p-value: {result['price_lsb_chi2']['p_value']:.4f}")
            print(f"  Entropy: {result['price_entropy']:.3f}")
            
        except Exception as e:
            print(f"  Error: {e}")
            results.append({"date": date, "error": str(e)})
    
    return results


def main():
    api_key = load_api_key()
    if not api_key:
        print("POLYGON_API_KEY not found in .env")
        return
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Use same dates as GME analysis where possible (2024 dates)
    dates = [
        "2024-05-06", "2024-05-07", "2024-05-08", "2024-05-09", "2024-05-10",
        "2024-05-13", "2024-05-14", "2024-05-15", "2024-05-16", "2024-05-17"
    ]
    
    print("=" * 60)
    print("CONTROL SAMPLE ANALYSIS: SPY vs GME")
    print("=" * 60)
    
    # Analyze SPY (control)
    print("\n>>> Analyzing SPY (control)...")
    spy_results = analyze_symbol("SPY", dates, api_key)
    
    # Summarize findings
    spy_price_anomalies = sum(1 for r in spy_results if "error" not in r and r["price_lsb_chi2"]["significant"])
    spy_benford_deviations = sum(1 for r in spy_results if "error" not in r and r.get("benford", {}).get("significant_deviation", False))
    spy_valid = sum(1 for r in spy_results if "error" not in r)
    
    # Load GME results for comparison
    gme_results_file = BASE_DIR / "research" / "steganography" / "01_lsb_detection" / "results" / "lsb_analysis_results.json"
    gme_summary = {"price_lsb_anomalies": 26, "benford_deviations": 26, "total_days": 26}
    
    if gme_results_file.exists():
        with open(gme_results_file) as f:
            gme_data = json.load(f)
            gme_summary = gme_data.get("summary", gme_summary)
    
    # Generate comparison report
    report = {
        "analysis_timestamp": datetime.now().isoformat(),
        "spy_results": spy_results,
        "comparison": {
            "spy": {
                "days_analyzed": spy_valid,
                "price_lsb_anomalies": spy_price_anomalies,
                "benford_deviations": spy_benford_deviations,
                "anomaly_rate": spy_price_anomalies / spy_valid if spy_valid > 0 else 0
            },
            "gme": {
                "days_analyzed": gme_summary.get("total_days", 26),
                "price_lsb_anomalies": gme_summary.get("price_lsb_anomalies", 26),
                "benford_deviations": gme_summary.get("benford_deviations", 26),
                "anomaly_rate": gme_summary.get("price_lsb_anomalies", 26) / gme_summary.get("total_days", 26)
            }
        }
    }
    
    output_file = OUTPUT_DIR / "control_analysis_results.json"
    with open(output_file, "w") as f:
        json.dump(report, f, indent=2)
    
    # Generate markdown report
    report_file = OUTPUT_DIR / "control_analysis_report.md"
    with open(report_file, "w") as f:
        f.write("# Control Sample Analysis: SPY vs GME\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Comparison\n\n")
        f.write("| Metric | SPY (Control) | GME (Test) |\n")
        f.write("|--------|---------------|------------|\n")
        f.write(f"| Days analyzed | {spy_valid} | {gme_summary.get('total_days', 26)} |\n")
        f.write(f"| Price LSB anomalies | {spy_price_anomalies} ({100*spy_price_anomalies/spy_valid:.1f}%) | {gme_summary.get('price_lsb_anomalies', 26)} (100%) |\n")
        f.write(f"| Benford deviations | {spy_benford_deviations} ({100*spy_benford_deviations/spy_valid:.1f}%) | {gme_summary.get('benford_deviations', 26)} (100%) |\n\n")
        
        if spy_price_anomalies == spy_valid:
            f.write("## Interpretation\n\n")
            f.write("> **⚠️ Both SPY and GME show LSB anomalies.** This suggests the patterns are general market artifacts, not GME-specific.\n\n")
        else:
            f.write("## Interpretation\n\n")
            f.write("> **GME shows significantly more anomalies than SPY.** This could indicate GME-specific microstructure effects.\n\n")
    
    print("\n" + "=" * 60)
    print("COMPARISON SUMMARY")
    print("=" * 60)
    print(f"SPY: {spy_price_anomalies}/{spy_valid} days with LSB anomalies ({100*spy_price_anomalies/spy_valid:.1f}%)")
    print(f"GME: {gme_summary.get('price_lsb_anomalies', 26)}/{gme_summary.get('total_days', 26)} days with LSB anomalies (100%)")
    print(f"\nResults saved to: {output_file}")
    print(f"Report saved to: {report_file}")


if __name__ == "__main__":
    main()
