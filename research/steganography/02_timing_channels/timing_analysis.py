#!/usr/bin/env python3
"""
Steganography Research: Timing Channel Analysis
===============================================

Analyzes order flow timing patterns for potential covert timing channels.
Tests whether inter-arrival times exhibit non-random patterns.

Methods:
1. Inter-arrival time distribution analysis
2. Entropy-based timing steganalysis
3. Periodicity detection via FFT
4. Clustering around specific intervals
"""

import os
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np
from scipy import stats
from scipy.fft import fft, fftfreq
from scipy.signal import find_peaks
import json

# Configuration
DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "samples"
OUTPUT_DIR = Path(__file__).resolve().parent / "results"


def calculate_inter_arrival_times(timestamps: pd.Series) -> np.ndarray:
    """Calculate inter-arrival times in microseconds."""
    ts = pd.to_datetime(timestamps, format='ISO8601')
    deltas = ts.diff().dropna()
    # Convert to microseconds
    return deltas.dt.total_seconds().values * 1_000_000


def entropy_analysis(iat: np.ndarray, n_bins: int = 50) -> dict:
    """Calculate entropy of inter-arrival time distribution."""
    # Bin the inter-arrival times
    hist, bin_edges = np.histogram(iat, bins=n_bins, density=True)
    hist = hist[hist > 0]  # Remove zeros
    
    # Shannon entropy
    h = -np.sum(hist * np.log2(hist + 1e-10) * (bin_edges[1] - bin_edges[0]))
    
    # Compare to exponential distribution (expected for random arrivals)
    rate = 1 / np.mean(iat)
    exp_samples = np.random.exponential(1/rate, len(iat))
    exp_hist, _ = np.histogram(exp_samples, bins=n_bins, density=True)
    exp_hist = exp_hist[exp_hist > 0]
    h_exp = -np.sum(exp_hist * np.log2(exp_hist + 1e-10) * (bin_edges[1] - bin_edges[0]))
    
    return {
        "entropy": float(h),
        "expected_entropy": float(h_exp),
        "entropy_ratio": float(h / h_exp) if h_exp > 0 else None,
        "interpretation": "Lower than expected entropy suggests structure" if h < 0.9 * h_exp else "Normal entropy"
    }


def periodicity_detection(iat: np.ndarray, sample_rate: float = 1000) -> dict:
    """Detect periodic patterns in timing using FFT."""
    # Use a subset for FFT (power of 2 for efficiency)
    n = min(2**16, len(iat))
    signal = iat[:n]
    
    # Normalize
    signal = (signal - np.mean(signal)) / (np.std(signal) + 1e-10)
    
    # FFT
    yf = np.abs(fft(signal))
    xf = fftfreq(n, 1/sample_rate)
    
    # Only positive frequencies
    pos_mask = xf > 0
    yf = yf[pos_mask]
    xf = xf[pos_mask]
    
    # Find peaks
    peaks, properties = find_peaks(yf, height=np.mean(yf) + 2*np.std(yf))
    
    dominant_freqs = []
    for i, peak in enumerate(peaks[:5]):  # Top 5 peaks
        dominant_freqs.append({
            "frequency_hz": float(xf[peak]),
            "period_us": float(1_000_000 / xf[peak]) if xf[peak] > 0 else None,
            "magnitude": float(yf[peak])
        })
    
    return {
        "num_significant_peaks": len(peaks),
        "dominant_frequencies": dominant_freqs,
        "interpretation": "Periodic structure detected" if len(peaks) > 3 else "No strong periodicity"
    }


def interval_clustering_analysis(iat: np.ndarray) -> dict:
    """Check for clustering around specific interval values (potential timing channel)."""
    # Define bins at common timing boundaries (10us, 50us, 100us, 1ms, etc.)
    boundaries = [10, 50, 100, 500, 1000, 5000, 10000, 50000, 100000]
    
    clusters = []
    for b in boundaries:
        # Count values within 5% of boundary
        tolerance = b * 0.05
        count = np.sum((iat >= b - tolerance) & (iat <= b + tolerance))
        expected = len(iat) * (2 * tolerance) / (np.max(iat) - np.min(iat) + 1)
        ratio = count / expected if expected > 0 else 0
        
        if count > 100:  # Minimum threshold
            clusters.append({
                "boundary_us": int(b),
                "count": int(count),
                "expected":  round(expected, 1),
                "ratio": round(ratio, 2),
                "significant": bool(ratio > 2.0)
            })
    
    significant_clusters = [c for c in clusters if c.get("significant")]
    
    return {
        "clusters": clusters,
        "significant_clusters": len(significant_clusters),
        "interpretation": "Timing clustering detected" if significant_clusters else "No suspicious clustering"
    }


def distribution_analysis(iat: np.ndarray) -> dict:
    """Analyze the statistical distribution of inter-arrival times."""
    # Basic statistics
    stats_dict = {
        "mean_us": float(np.mean(iat)),
        "median_us": float(np.median(iat)),
        "std_us": float(np.std(iat)),
        "min_us": float(np.min(iat)),
        "max_us": float(np.max(iat)),
        "skewness": float(stats.skew(iat)),
        "kurtosis": float(stats.kurtosis(iat))
    }
    
    # Test against exponential distribution (Poisson arrivals)
    rate = 1 / np.mean(iat)
    ks_stat, ks_pvalue = stats.kstest(iat, 'expon', args=(0, 1/rate))
    
    stats_dict["ks_test_exponential"] = {
        "statistic": float(ks_stat),
        "p_value": float(ks_pvalue),
        "follows_exponential": bool(ks_pvalue > 0.05)
    }
    
    # Coefficient of variation (CV=1 for exponential)
    cv = np.std(iat) / np.mean(iat)
    stats_dict["coefficient_of_variation"] = float(cv)
    stats_dict["cv_interpretation"] = "CV~1 expected for random; <1 suggests regularity" if cv < 0.8 else "Normal variation"
    
    return stats_dict


def analyze_single_day(sample_dir: Path) -> dict:
    """Run full timing analysis on a single trading day."""
    trades_files = list(sample_dir.glob("raw_ticks/*_trades.csv"))
    
    if not trades_files:
        return {"error": f"No trades found in {sample_dir}"}
    
    trades_file = trades_files[0]
    df = pd.read_csv(trades_file)
    
    if "timestamp" not in df.columns:
        return {"error": f"Missing timestamp column in {trades_file}"}
    
    # Calculate inter-arrival times
    iat = calculate_inter_arrival_times(df["timestamp"])
    
    # Filter extreme outliers (data quality)
    iat = iat[(iat > 0) & (iat < np.percentile(iat, 99.9))]
    
    if len(iat) < 1000:
        return {"error": "Insufficient data points for analysis"}
    
    date = sample_dir.name.replace("sample_", "")
    
    return {
        "date": date,
        "total_trades": len(df),
        "analyzed_intervals": len(iat),
        "distribution": distribution_analysis(iat),
        "entropy": entropy_analysis(iat),
        "periodicity": periodicity_detection(iat),
        "clustering": interval_clustering_analysis(iat)
    }


def main():
    """Run timing channel analysis across all available trading days."""
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
        "periodicity_detected": 0,
        "clustering_detected": 0,
        "low_entropy_days": 0,
        "non_exponential_days": 0
    }
    
    for sample_dir in sample_dirs:
        print(f"\nAnalyzing {sample_dir.name}...")
        try:
            result = analyze_single_day(sample_dir)
            results.append(result)
            
            if "error" not in result:
                if result["periodicity"]["num_significant_peaks"] > 3:
                    summary_stats["periodicity_detected"] += 1
                if result["clustering"]["significant_clusters"] > 0:
                    summary_stats["clustering_detected"] += 1
                if result["entropy"]["entropy_ratio"] and result["entropy"]["entropy_ratio"] < 0.9:
                    summary_stats["low_entropy_days"] += 1
                if not result["distribution"]["ks_test_exponential"]["follows_exponential"]:
                    summary_stats["non_exponential_days"] += 1
                
                print(f"  Trades: {result['total_trades']:,}")
                print(f"  Mean IAT: {result['distribution']['mean_us']:.0f} µs")
                print(f"  CV: {result['distribution']['coefficient_of_variation']:.2f}")
                print(f"  Periodic peaks: {result['periodicity']['num_significant_peaks']}")
        except Exception as e:
            print(f"  Error: {e}")
            results.append({"date": sample_dir.name, "error": str(e)})
    
    # Save detailed results
    output_file = OUTPUT_DIR / "timing_analysis_results.json"
    with open(output_file, "w") as f:
        json.dump({
            "analysis_timestamp": datetime.now().isoformat(),
            "summary": summary_stats,
            "daily_results": results
        }, f, indent=2)
    
    print("\n" + "=" * 60)
    print("TIMING CHANNEL ANALYSIS SUMMARY")
    print("=" * 60)
    print(f"Total trading days analyzed: {summary_stats['total_days']}")
    print(f"Days with periodicity detected: {summary_stats['periodicity_detected']}")
    print(f"Days with interval clustering: {summary_stats['clustering_detected']}")
    print(f"Days with low entropy: {summary_stats['low_entropy_days']}")
    print(f"Days not following exponential: {summary_stats['non_exponential_days']}")
    print(f"\nDetailed results saved to: {output_file}")
    
    # Generate report
    generate_report(results, summary_stats)


def generate_report(results: list, summary: dict):
    """Generate markdown report."""
    report_file = OUTPUT_DIR / "timing_analysis_report.md"
    
    with open(report_file, "w") as f:
        f.write("# Timing Channel Steganalysis Report\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Summary\n\n")
        f.write("| Metric | Count | Percentage |\n")
        f.write("|--------|-------|------------|\n")
        f.write(f"| Total days analyzed | {summary['total_days']} | 100% |\n")
        f.write(f"| Periodicity detected | {summary['periodicity_detected']} | {100*summary['periodicity_detected']/summary['total_days']:.1f}% |\n")
        f.write(f"| Interval clustering | {summary['clustering_detected']} | {100*summary['clustering_detected']/summary['total_days']:.1f}% |\n")
        f.write(f"| Low entropy | {summary['low_entropy_days']} | {100*summary['low_entropy_days']/summary['total_days']:.1f}% |\n")
        f.write(f"| Non-exponential | {summary['non_exponential_days']} | {100*summary['non_exponential_days']/summary['total_days']:.1f}% |\n\n")
        
        f.write("## Interpretation\n\n")
        f.write("- **Periodicity**: Regular timing patterns could indicate algorithmic encoding\n")
        f.write("- **Clustering**: Orders clustering at specific intervals may hide data\n")
        f.write("- **Low entropy**: Less randomness than expected suggests structure\n")
        f.write("- **Non-exponential**: Natural order flow follows Poisson (exponential IAT)\n\n")
        
        f.write("## Anomalies Detected\n\n")
        anomalies = [r for r in results if "error" not in r and 
                     (r["periodicity"]["num_significant_peaks"] > 5 or
                      r["clustering"]["significant_clusters"] > 2)]
        
        if anomalies:
            for r in anomalies:
                f.write(f"### {r['date']} ⚠️\n\n")
                f.write(f"- Periodic peaks: {r['periodicity']['num_significant_peaks']}\n")
                f.write(f"- Clustered intervals: {r['clustering']['significant_clusters']}\n")
                if r['periodicity']['dominant_frequencies']:
                    f.write(f"- Dominant period: {r['periodicity']['dominant_frequencies'][0]['period_us']:.0f} µs\n")
                f.write("\n")
        else:
            f.write("No significant anomalies detected across the analyzed period.\n\n")
    
    print(f"Report saved to: {report_file}")


if __name__ == "__main__":
    main()
