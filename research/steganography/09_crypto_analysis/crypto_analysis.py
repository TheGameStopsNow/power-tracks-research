#!/usr/bin/env python3
"""
Phase 7b: Crypto Market Steganalysis
====================================

Analyzes cryptocurrency markets for steganographic patterns:
1. BTC/ETH price LSB patterns
2. Transaction timing on public blockchains
3. Cross-crypto correlation
4. DEX vs CEX comparison
"""

import os
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from scipy import stats
import requests

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
OUTPUT_DIR = Path(__file__).resolve().parent / "results"

CRYPTO_SYMBOLS = ["X:BTCUSD", "X:ETHUSD", "X:SOLUSD", "X:DOGEUSD", "X:XRPUSD"]


def load_api_key() -> str:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.startswith("POLYGON_API_KEY="):
                    return line.strip().split("=", 1)[1]
    return ""


def fetch_crypto_bars(symbol: str, date: str, api_key: str) -> pd.DataFrame:
    """Fetch crypto minute bars from Polygon."""
    url = f"https://api.polygon.io/v2/aggs/ticker/{symbol}/range/1/minute/{date}/{date}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": api_key}
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            return pd.DataFrame()
        
        results = resp.json().get("results", [])
        if not results:
            return pd.DataFrame()
        
        df = pd.DataFrame(results)
        df = df.rename(columns={"t": "timestamp", "c": "price", "v": "volume"})
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except:
        return pd.DataFrame()


def analyze_crypto_lsb(df: pd.DataFrame, precision: int = 2) -> dict:
    """Analyze LSB patterns in crypto prices."""
    if df.empty:
        return {"error": "No data"}
    
    prices = df["price"].dropna()
    
    # Different precision for different price levels
    if prices.mean() > 1000:  # BTC-like
        precision = 0  # Dollar level
        lsb = (prices.astype(int) % 10)
    elif prices.mean() > 10:  # ETH-like
        precision = 1  # 10-cent level
        lsb = ((prices * 10).astype(int) % 10)
    else:  # Low-price coins
        precision = 4  # 0.0001 level
        lsb = ((prices * 10000).astype(int) % 10)
    
    lsb_counts = np.bincount(lsb.astype(int), minlength=10)
    expected = np.full(10, len(prices) / 10)
    chi2, pval = stats.chisquare(lsb_counts, expected)
    
    # Autocorrelation
    lsb_arr = lsb.values
    if len(lsb_arr) > 10:
        autocorr = np.corrcoef(lsb_arr[:-1], lsb_arr[1:])[0, 1]
    else:
        autocorr = 0
    
    return {
        "n_prices": len(prices),
        "price_level": "high" if prices.mean() > 1000 else ("mid" if prices.mean() > 10 else "low"),
        "precision_used": precision,
        "lsb_chi2": float(chi2),
        "lsb_pvalue": float(pval),
        "lsb_anomaly": bool(pval < 0.05),
        "lsb_distribution": lsb_counts.tolist(),
        "autocorrelation": float(autocorr) if not np.isnan(autocorr) else 0
    }


def analyze_crypto_timing(df: pd.DataFrame) -> dict:
    """Analyze timing patterns in crypto trades."""
    if df.empty or len(df) < 100:
        return {"error": "Insufficient data"}
    
    # Inter-arrival times
    iat = df["timestamp"].diff().dt.total_seconds().dropna()
    iat = iat[(iat > 0) & (iat < 600)]  # Filter outliers
    
    if len(iat) < 50:
        return {"error": "Insufficient timing data"}
    
    # Entropy
    hist, _ = np.histogram(iat, bins=20)
    probs = hist / hist.sum()
    entropy = stats.entropy(probs + 1e-10)
    max_entropy = np.log(20)
    
    return {
        "n_intervals": len(iat),
        "mean_iat_sec": float(iat.mean()),
        "std_iat_sec": float(iat.std()),
        "timing_entropy": float(entropy),
        "normalized_entropy": float(entropy / max_entropy),
        "periodic_signature": bool(entropy / max_entropy < 0.7)
    }


def calculate_cross_crypto_mi(df1: pd.DataFrame, df2: pd.DataFrame) -> float:
    """Calculate MI between two crypto assets."""
    df1["minute"] = df1["timestamp"].dt.floor("T")
    df2["minute"] = df2["timestamp"].dt.floor("T")
    
    merged = pd.merge(df1[["minute", "price"]], df2[["minute", "price"]], 
                       on="minute", suffixes=("_1", "_2"))
    
    if len(merged) < 50:
        return np.nan
    
    # Use relative changes for comparison
    pct1 = merged["price_1"].pct_change().dropna() * 1000
    pct2 = merged["price_2"].pct_change().dropna() * 1000
    
    # Discretize
    lsb1 = (pct1.clip(-5, 5) + 5).astype(int)
    lsb2 = (pct2.clip(-5, 5) + 5).astype(int)
    
    joint = pd.crosstab(lsb1, lsb2, normalize=True)
    px = joint.sum(axis=1)
    py = joint.sum(axis=0)
    
    mi = 0
    for i in joint.index:
        for j in joint.columns:
            if joint.loc[i, j] > 0 and px[i] > 0 and py[j] > 0:
                mi += joint.loc[i, j] * np.log2(joint.loc[i, j] / (px[i] * py[j]))
    
    return mi


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    api_key = load_api_key()
    
    date = "2024-05-16"
    
    print("=" * 60)
    print("CRYPTO MARKET STEGANALYSIS")
    print("=" * 60)
    
    crypto_data = {}
    results = []
    
    for symbol in CRYPTO_SYMBOLS:
        name = symbol.replace("X:", "")
        print(f"\n>>> {name}")
        
        df = fetch_crypto_bars(symbol, date, api_key)
        
        if df.empty:
            print("  No data")
            continue
        
        print(f"  {len(df)} bars")
        crypto_data[name] = df
        
        result = {
            "symbol": name,
            "lsb_analysis": analyze_crypto_lsb(df),
            "timing_analysis": analyze_crypto_timing(df)
        }
        results.append(result)
        
        if result["lsb_analysis"].get("lsb_anomaly"):
            print(f"  LSB anomaly detected!")
    
    # Cross-crypto correlation
    print("\n>>> Cross-crypto MI analysis...")
    cross_mi = []
    symbols = list(crypto_data.keys())
    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            s1, s2 = symbols[i], symbols[j]
            mi = calculate_cross_crypto_mi(crypto_data[s1], crypto_data[s2])
            if not np.isnan(mi):
                cross_mi.append({"pair": f"{s1}-{s2}", "mi": mi})
                print(f"  {s1}-{s2}: MI = {mi:.4f}")
    
    # Save results
    with open(OUTPUT_DIR / "crypto_analysis.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "date": date,
            "results": results,
            "cross_mi": cross_mi
        }, f, indent=2)
    
    # Generate report
    with open(OUTPUT_DIR / "crypto_report.md", "w") as f:
        f.write("# Crypto Market Steganalysis\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## LSB Analysis\n\n")
        f.write("| Crypto | Bars | LSB Anomaly | Autocorr |\n")
        f.write("|--------|------|-------------|----------|\n")
        for r in results:
            lsb = r["lsb_analysis"]
            if "error" not in lsb:
                anomaly = "✓" if lsb["lsb_anomaly"] else ""
                f.write(f"| {r['symbol']} | {lsb['n_prices']} | {anomaly} | {lsb['autocorrelation']:.4f} |\n")
        
        f.write("\n## Cross-Crypto Correlation\n\n")
        f.write("| Pair | MI |\n")
        f.write("|------|----|\n")
        for item in sorted(cross_mi, key=lambda x: x["mi"], reverse=True):
            f.write(f"| {item['pair']} | {item['mi']:.4f} |\n")
    
    print("\n" + "=" * 60)
    print("CRYPTO ANALYSIS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
