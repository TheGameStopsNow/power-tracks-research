#!/usr/bin/env python3
"""
Phase 7a: Options Order Flow Steganalysis
=========================================

Analyzes options order flow for potential encoding channels:
1. Strike price selection patterns
2. Expiry date patterns  
3. Put/call ratio sequences
4. Volume patterns across strikes
"""

import os
from pathlib import Path
from datetime import datetime, timedelta
import json
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from scipy import stats
import requests

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
OUTPUT_DIR = Path(__file__).resolve().parent / "results"


def load_api_key() -> str:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.startswith("POLYGON_API_KEY="):
                    return line.strip().split("=", 1)[1]
    return ""


def fetch_options_contracts(symbol: str, date: str, api_key: str) -> pd.DataFrame:
    """Fetch options trades for a symbol on a given date."""
    url = f"https://api.polygon.io/v3/trades/O:{symbol}*"
    params = {
        "timestamp.gte": f"{date}T09:30:00Z",
        "timestamp.lte": f"{date}T16:00:00Z",
        "limit": 50000,
        "apiKey": api_key
    }
    
    try:
        resp = requests.get(url, params=params, timeout=60)
        if resp.status_code != 200:
            return pd.DataFrame()
        
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return pd.DataFrame()
        
        return pd.DataFrame(results)
    except:
        return pd.DataFrame()


def fetch_options_chain(symbol: str, date: str, api_key: str) -> pd.DataFrame:
    """Fetch options chain snapshot."""
    url = f"https://api.polygon.io/v3/snapshot/options/{symbol}"
    params = {"apiKey": api_key}
    
    try:
        resp = requests.get(url, params=params, timeout=60)
        if resp.status_code != 200:
            print(f"  Options chain API error: {resp.status_code}")
            return pd.DataFrame()
        
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return pd.DataFrame()
        
        # Flatten the options data
        records = []
        for opt in results:
            details = opt.get("details", {})
            day = opt.get("day", {})
            records.append({
                "contract_type": details.get("contract_type"),
                "strike_price": details.get("strike_price"),
                "expiration_date": details.get("expiration_date"),
                "volume": day.get("volume", 0),
                "open_interest": day.get("open_interest", 0),
                "vwap": day.get("vwap", 0),
                "close": day.get("close", 0)
            })
        
        return pd.DataFrame(records)
    except Exception as e:
        print(f"  Error: {e}")
        return pd.DataFrame()


def analyze_strike_patterns(df: pd.DataFrame) -> dict:
    """Analyze patterns in strike price selection."""
    if df.empty or "strike_price" not in df.columns:
        return {"error": "No strike data"}
    
    strikes = df["strike_price"].dropna()
    
    if len(strikes) < 10:
        return {"error": "Insufficient strikes"}
    
    # LSB analysis on strike prices
    strike_cents = (strikes * 100).astype(int) % 100
    strike_lsb = strike_cents % 10
    
    lsb_counts = np.bincount(strike_lsb.astype(int), minlength=10)
    expected = np.full(10, len(strikes) / 10)
    chi2, pval = stats.chisquare(lsb_counts, expected)
    
    # Round strike preference
    round_strikes = (strikes % 5 == 0).sum() / len(strikes)
    
    return {
        "n_strikes": len(strikes),
        "lsb_chi2": float(chi2),
        "lsb_pvalue": float(pval),
        "lsb_significant": bool(pval < 0.05),
        "lsb_distribution": lsb_counts.tolist(),
        "round_strike_pct": float(round_strikes * 100),
        "unique_strikes": int(strikes.nunique()),
        "mean_strike": float(strikes.mean()),
        "strike_range": float(strikes.max() - strikes.min())
    }


def analyze_expiry_patterns(df: pd.DataFrame) -> dict:
    """Analyze patterns in expiration date selection."""
    if df.empty or "expiration_date" not in df.columns:
        return {"error": "No expiry data"}
    
    expiries = pd.to_datetime(df["expiration_date"].dropna())
    
    if len(expiries) < 10:
        return {"error": "Insufficient expiries"}
    
    # Day of week distribution
    dow = expiries.dt.dayofweek
    dow_counts = dow.value_counts().sort_index()
    
    # Days to expiry distribution
    today = datetime.now()
    dte = (expiries - today).dt.days
    
    return {
        "n_contracts": len(expiries),
        "unique_expiries": int(expiries.nunique()),
        "day_of_week_dist": dow_counts.to_dict(),
        "mean_dte": float(dte.mean()) if len(dte) > 0 else 0,
        "dte_std": float(dte.std()) if len(dte) > 0 else 0,
        "weekly_pct": float((dte <= 7).sum() / len(dte) * 100) if len(dte) > 0 else 0
    }


def analyze_put_call_patterns(df: pd.DataFrame) -> dict:
    """Analyze put/call ratio patterns."""
    if df.empty or "contract_type" not in df.columns:
        return {"error": "No contract type data"}
    
    calls = df[df["contract_type"] == "call"]
    puts = df[df["contract_type"] == "put"]
    
    if len(calls) < 5 or len(puts) < 5:
        return {"error": "Insufficient put/call data"}
    
    call_vol = calls["volume"].sum() if "volume" in calls.columns else len(calls)
    put_vol = puts["volume"].sum() if "volume" in puts.columns else len(puts)
    
    pc_ratio = put_vol / call_vol if call_vol > 0 else 0
    
    return {
        "n_calls": len(calls),
        "n_puts": len(puts),
        "call_volume": int(call_vol),
        "put_volume": int(put_vol),
        "put_call_ratio": float(pc_ratio),
        "interpretation": "bearish" if pc_ratio > 1.2 else ("bullish" if pc_ratio < 0.8 else "neutral")
    }


def analyze_volume_patterns(df: pd.DataFrame) -> dict:
    """Analyze volume patterns across strikes."""
    if df.empty or "volume" not in df.columns:
        return {"error": "No volume data"}
    
    volumes = df["volume"].dropna()
    volumes = volumes[volumes > 0]
    
    if len(volumes) < 10:
        return {"error": "Insufficient volume data"}
    
    # Volume LSB
    vol_lsb = volumes.astype(int) % 10
    lsb_counts = np.bincount(vol_lsb.astype(int), minlength=10)
    expected = np.full(10, len(volumes) / 10)
    chi2, pval = stats.chisquare(lsb_counts, expected)
    
    # Round lot analysis
    round_lots = (volumes % 100 == 0).sum() / len(volumes)
    
    return {
        "n_contracts": len(volumes),
        "vol_lsb_chi2": float(chi2),
        "vol_lsb_pvalue": float(pval),
        "vol_lsb_significant": bool(pval < 0.05),
        "round_lot_pct": float(round_lots * 100),
        "mean_volume": float(volumes.mean()),
        "max_volume": int(volumes.max())
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    api_key = load_api_key()
    
    symbols = ["GME", "AMC", "TSLA", "NVDA", "SPY", "AAPL"]
    
    print("=" * 60)
    print("OPTIONS ORDER FLOW STEGANALYSIS")
    print("=" * 60)
    
    results = []
    
    for symbol in symbols:
        print(f"\n>>> {symbol}")
        
        df = fetch_options_chain(symbol, datetime.now().strftime("%Y-%m-%d"), api_key)
        
        if df.empty:
            print("  No options data available")
            results.append({"symbol": symbol, "error": "No data"})
            continue
        
        print(f"  Found {len(df)} options contracts")
        
        result = {
            "symbol": symbol,
            "n_contracts": len(df),
            "strike_analysis": analyze_strike_patterns(df),
            "expiry_analysis": analyze_expiry_patterns(df),
            "put_call_analysis": analyze_put_call_patterns(df),
            "volume_analysis": analyze_volume_patterns(df)
        }
        
        results.append(result)
        
        if "strike_analysis" in result and "lsb_significant" in result["strike_analysis"]:
            print(f"  Strike LSB anomaly: {result['strike_analysis']['lsb_significant']}")
    
    # Save results
    with open(OUTPUT_DIR / "options_analysis.json", "w") as f:
        json.dump({"timestamp": datetime.now().isoformat(), "results": results}, f, indent=2)
    
    # Generate report
    with open(OUTPUT_DIR / "options_report.md", "w") as f:
        f.write("# Options Order Flow Steganalysis\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Summary\n\n")
        f.write("| Symbol | Contracts | Strike LSB Anomaly | P/C Ratio |\n")
        f.write("|--------|-----------|-------------------|----------|\n")
        for r in results:
            if "error" not in r:
                strike = r.get("strike_analysis", {})
                pc = r.get("put_call_analysis", {})
                anomaly = "✓" if strike.get("lsb_significant") else ""
                ratio = pc.get("put_call_ratio", 0)
                f.write(f"| {r['symbol']} | {r['n_contracts']} | {anomaly} | {ratio:.2f} |\n")
    
    print("\n" + "=" * 60)
    print("OPTIONS ANALYSIS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
