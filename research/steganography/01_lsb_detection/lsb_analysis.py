#!/usr/bin/env python3
"""
Steganography Research: LSB Detection Analysis
==============================================

Analyzes price data for potential Least Significant Bit (LSB) encoding patterns.
Tests whether LSB distributions deviate from expected randomness.

Methods:
1. Chi-square test for uniform LSB distribution
2. Shannon entropy analysis
3. Autocorrelation of LSB sequences  
4. Runs test for randomness
"""

import os
import sys
import glob
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np
from scipy import stats
from scipy.stats import chi2_contingency, entropy
import json

# Configuration
DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "samples"
OUTPUT_DIR = Path(__file__).resolve().parent / "results"


def extract_price_lsb(prices: pd.Series, decimal_places: int = 2) -> np.ndarray:
    """Extract LSB from price data at specified decimal precision."""
    # Convert to cents (2 decimal places) or sub-penny (3+ places)
    multiplier = 10 ** decimal_places
    scaled = (prices * multiplier).astype(int)
    return scaled % 10  # Last decimal digit


def extract_volume_lsb(volumes: pd.Series) -> np.ndarray:
    """Extract LSB from volume data."""
    return (volumes.astype(int) % 10).values


def chi_square_uniformity_test(lsb_values: np.ndarray) -> dict:
    """Test if LSB distribution is uniform (expected for random data)."""
    observed = np.bincount(lsb_values, minlength=10)
    expected = np.full(10, len(lsb_values) / 10)
    
    chi2, p_value = stats.chisquare(observed, expected)
    
    return {
        "chi2_statistic": float(chi2),
        "p_value": float(p_value),
        "observed_frequencies": observed.tolist(),
        "expected_frequency": float(expected[0]),
        "significant": bool(p_value < 0.05),
        "interpretation": "Non-uniform distribution detected" if p_value < 0.05 else "Uniform (random) distribution"
    }


def calculate_entropy(lsb_values: np.ndarray) -> dict:
    """Calculate Shannon entropy of LSB sequence."""
    # Frequency distribution
    _, counts = np.unique(lsb_values, return_counts=True)
    probs = counts / len(lsb_values)
    
    # Shannon entropy
    h = entropy(probs, base=2)
    max_entropy = np.log2(10)  # Maximum entropy for 10 possible values
    
    return {
        "shannon_entropy": float(h),
        "max_possible_entropy": float(max_entropy),
        "normalized_entropy": float(h / max_entropy),
        "interpretation": "High randomness" if h > 0.9 * max_entropy else "Potential structure detected"
    }


def autocorrelation_analysis(lsb_values: np.ndarray, max_lag: int = 50) -> dict:
    """Check for autocorrelation in LSB sequence (hidden patterns)."""
    n = len(lsb_values)
    mean = np.mean(lsb_values)
    var = np.var(lsb_values)
    
    if var == 0:
        return {"error": "Zero variance in LSB values"}
    
    autocorr = []
    for lag in range(1, min(max_lag + 1, n // 2)):
        corr = np.corrcoef(lsb_values[:-lag], lsb_values[lag:])[0, 1]
        if not np.isnan(corr):
            autocorr.append({"lag": lag, "correlation": float(corr)})
    
    # Significance threshold (approximate)
    sig_threshold = 2 / np.sqrt(n)
    significant_lags = [a for a in autocorr if abs(a["correlation"]) > sig_threshold]
    
    return {
        "autocorrelations": autocorr[:10],  # First 10 lags
        "significant_lags": len(significant_lags),
        "significance_threshold": float(sig_threshold),
        "interpretation": "Significant autocorrelation detected" if significant_lags else "No significant autocorrelation"
    }


def runs_test(lsb_values: np.ndarray) -> dict:
    """Wald-Wolfowitz runs test for randomness."""
    median = np.median(lsb_values)
    binary = (lsb_values > median).astype(int)
    
    # Count runs
    runs = 1
    for i in range(1, len(binary)):
        if binary[i] != binary[i-1]:
            runs += 1
    
    n1 = np.sum(binary)
    n2 = len(binary) - n1
    
    if n1 == 0 or n2 == 0:
        return {"error": "Cannot perform runs test - all values on one side of median"}
    
    # Expected runs and variance
    expected_runs = (2 * n1 * n2) / (n1 + n2) + 1
    var_runs = (2 * n1 * n2 * (2 * n1 * n2 - n1 - n2)) / ((n1 + n2)**2 * (n1 + n2 - 1))
    
    if var_runs <= 0:
        return {"error": "Invalid variance in runs test"}
    
    z_score = (runs - expected_runs) / np.sqrt(var_runs)
    p_value = 2 * (1 - stats.norm.cdf(abs(z_score)))
    
    return {
        "observed_runs": int(runs),
        "expected_runs": float(expected_runs),
        "z_score": float(z_score),
        "p_value": float(p_value),
        "significant": bool(p_value < 0.05),
        "interpretation": "Non-random pattern detected" if p_value < 0.05 else "Random sequence"
    }


def benford_law_analysis(prices: pd.Series) -> dict:
    """Test if first digits follow Benford's Law (natural financial data should)."""
    # Extract first non-zero digit
    first_digits = []
    for p in prices:
        if p > 0:
            s = f"{p:.10f}".lstrip('0').replace('.', '')
            if s:
                first_digits.append(int(s[0]))
    
    if not first_digits:
        return {"error": "No valid prices for Benford analysis"}
    
    first_digits = np.array(first_digits)
    observed = np.bincount(first_digits, minlength=10)[1:10]  # Digits 1-9
    
    # Benford's Law expected distribution
    benford_expected = np.array([np.log10(1 + 1/d) for d in range(1, 10)])
    expected = benford_expected * len(first_digits)
    
    chi2, p_value = stats.chisquare(observed, expected)
    
    return {
        "chi2_statistic": float(chi2),
        "p_value": float(p_value),
        "observed_distribution": observed.tolist(),
        "benford_expected": (benford_expected * 100).round(2).tolist(),
        "significant_deviation": bool(p_value < 0.05),
        "interpretation": "Deviates from Benford's Law" if p_value < 0.05 else "Follows Benford's Law (natural data)"
    }


def analyze_single_day(sample_dir: Path) -> dict:
    """Run full LSB analysis on a single trading day."""
    trades_files = list(sample_dir.glob("raw_ticks/*_trades.csv"))
    
    if not trades_files:
        return {"error": f"No trades found in {sample_dir}"}
    
    trades_file = trades_files[0]
    df = pd.read_csv(trades_file)
    
    if "price" not in df.columns or "volume" not in df.columns:
        return {"error": f"Missing price/volume columns in {trades_file}"}
    
    prices = df["price"].dropna()
    volumes = df["volume"].dropna()
    
    # Price LSB analysis (cents - 2 decimal places)
    price_lsb_cents = extract_price_lsb(prices, decimal_places=2)
    
    # Price LSB analysis (sub-penny - 4 decimal places)
    price_lsb_subpenny = extract_price_lsb(prices, decimal_places=4)
    
    # Volume LSB analysis
    volume_lsb = extract_volume_lsb(volumes)
    
    date = sample_dir.name.replace("sample_", "")
    
    return {
        "date": date,
        "total_trades": len(df),
        "price_range": {"min": float(prices.min()), "max": float(prices.max())},
        "volume_range": {"min": int(volumes.min()), "max": int(volumes.max())},
        "price_lsb_cents": {
            "chi_square": chi_square_uniformity_test(price_lsb_cents),
            "entropy": calculate_entropy(price_lsb_cents),
            "autocorrelation": autocorrelation_analysis(price_lsb_cents),
            "runs_test": runs_test(price_lsb_cents)
        },
        "price_lsb_subpenny": {
            "chi_square": chi_square_uniformity_test(price_lsb_subpenny),
            "entropy": calculate_entropy(price_lsb_subpenny),
        },
        "volume_lsb": {
            "chi_square": chi_square_uniformity_test(volume_lsb),
            "entropy": calculate_entropy(volume_lsb),
            "runs_test": runs_test(volume_lsb)
        },
        "benford_analysis": benford_law_analysis(prices)
    }


def main():
    """Run LSB analysis across all available trading days."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    sample_dirs = sorted(DATA_DIR.glob("sample_*"))
    
    if not sample_dirs:
        print(f"No sample directories found in {DATA_DIR}")
        return
    
    print(f"Found {len(sample_dirs)} trading days to analyze")
    print("=" * 60)
    
    results = []
    summary_stats = {
        "total_days": len(sample_dirs),
        "price_lsb_anomalies": 0,
        "volume_lsb_anomalies": 0,
        "benford_deviations": 0,
        "autocorrelation_detected": 0
    }
    
    for sample_dir in sample_dirs:
        print(f"\nAnalyzing {sample_dir.name}...")
        try:
            result = analyze_single_day(sample_dir)
            results.append(result)
            
            # Update summary
            if "error" not in result:
                if result["price_lsb_cents"]["chi_square"]["significant"]:
                    summary_stats["price_lsb_anomalies"] += 1
                if result["volume_lsb"]["chi_square"]["significant"]:
                    summary_stats["volume_lsb_anomalies"] += 1
                if result["benford_analysis"].get("significant_deviation"):
                    summary_stats["benford_deviations"] += 1
                if result["price_lsb_cents"]["autocorrelation"].get("significant_lags", 0) > 0:
                    summary_stats["autocorrelation_detected"] += 1
                    
                print(f"  Trades: {result['total_trades']:,}")
                print(f"  Price LSB chi2 p-value: {result['price_lsb_cents']['chi_square']['p_value']:.4f}")
                print(f"  Volume LSB chi2 p-value: {result['volume_lsb']['chi_square']['p_value']:.4f}")
        except Exception as e:
            print(f"  Error: {e}")
            results.append({"date": sample_dir.name, "error": str(e)})
    
    # Save detailed results
    output_file = OUTPUT_DIR / "lsb_analysis_results.json"
    with open(output_file, "w") as f:
        json.dump({
            "analysis_timestamp": datetime.now().isoformat(),
            "summary": summary_stats,
            "daily_results": results
        }, f, indent=2)
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total trading days analyzed: {summary_stats['total_days']}")
    print(f"Days with price LSB anomalies: {summary_stats['price_lsb_anomalies']}")
    print(f"Days with volume LSB anomalies: {summary_stats['volume_lsb_anomalies']}")
    print(f"Days deviating from Benford's Law: {summary_stats['benford_deviations']}")
    print(f"Days with autocorrelation detected: {summary_stats['autocorrelation_detected']}")
    print(f"\nDetailed results saved to: {output_file}")
    
    # Generate markdown report
    generate_report(results, summary_stats)


def generate_report(results: list, summary: dict):
    """Generate a markdown report of findings."""
    report_file = OUTPUT_DIR / "lsb_analysis_report.md"
    
    with open(report_file, "w") as f:
        f.write("# LSB Steganalysis Report\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Summary\n\n")
        f.write(f"| Metric | Count | Percentage |\n")
        f.write(f"|--------|-------|------------|\n")
        f.write(f"| Total days analyzed | {summary['total_days']} | 100% |\n")
        f.write(f"| Price LSB anomalies | {summary['price_lsb_anomalies']} | {100*summary['price_lsb_anomalies']/summary['total_days']:.1f}% |\n")
        f.write(f"| Volume LSB anomalies | {summary['volume_lsb_anomalies']} | {100*summary['volume_lsb_anomalies']/summary['total_days']:.1f}% |\n")
        f.write(f"| Benford deviations | {summary['benford_deviations']} | {100*summary['benford_deviations']/summary['total_days']:.1f}% |\n")
        f.write(f"| Autocorrelation detected | {summary['autocorrelation_detected']} | {100*summary['autocorrelation_detected']/summary['total_days']:.1f}% |\n\n")
        
        f.write("## Interpretation\n\n")
        f.write("- **Chi-square test**: Detects if LSB distribution deviates from uniform (p < 0.05 = anomaly)\n")
        f.write("- **Benford's Law**: Natural financial data typically follows this distribution\n")
        f.write("- **Autocorrelation**: Sequential LSB dependency could indicate encoding\n\n")
        
        f.write("## Daily Details\n\n")
        for r in results:
            if "error" in r:
                continue
            f.write(f"### {r['date']}\n\n")
            f.write(f"- Trades: {r['total_trades']:,}\n")
            f.write(f"- Price range: ${r['price_range']['min']:.2f} - ${r['price_range']['max']:.2f}\n")
            f.write(f"- Price LSB (cents) p-value: {r['price_lsb_cents']['chi_square']['p_value']:.4f}")
            if r['price_lsb_cents']['chi_square']['significant']:
                f.write(" ⚠️ **ANOMALY**")
            f.write("\n")
            f.write(f"- Price entropy: {r['price_lsb_cents']['entropy']['normalized_entropy']:.3f}\n")
            f.write("\n")
    
    print(f"Report saved to: {report_file}")


if __name__ == "__main__":
    main()
