#!/usr/bin/env python3
"""
Steganography Research: Advanced Analysis Suite
================================================

Deep-dive analysis including:
1. Hidden Markov Models for venue sequences
2. Mutual Information analysis (price LSB vs venue)
3. Decode attempt - extract potential bit sequences
4. Wavelet analysis on timing patterns
5. Event-driven window analysis
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from scipy import stats
from scipy.fft import fft, fftfreq
from scipy.signal import find_peaks
from collections import Counter
import string

# Configuration
DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "samples"
OUTPUT_DIR = Path(__file__).resolve().parent / "results"


# =============================================================================
# 1. MUTUAL INFORMATION ANALYSIS
# =============================================================================

def calculate_mutual_information(x: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    """Calculate mutual information between two discrete variables."""
    # Convert to discrete bins if continuous
    if len(np.unique(x)) > bins:
        x = pd.cut(x, bins=bins, labels=False)
    if len(np.unique(y)) > bins:
        y = pd.cut(y, bins=bins, labels=False)
    
    # Joint distribution
    joint = pd.crosstab(x, y, normalize=True)
    
    # Marginals
    px = joint.sum(axis=1)
    py = joint.sum(axis=0)
    
    # MI = sum p(x,y) * log(p(x,y) / (p(x)*p(y)))
    mi = 0
    for i in joint.index:
        for j in joint.columns:
            if joint.loc[i, j] > 0 and px[i] > 0 and py[j] > 0:
                mi += joint.loc[i, j] * np.log2(joint.loc[i, j] / (px[i] * py[j]))
    
    return mi


def analyze_mutual_information(df: pd.DataFrame) -> dict:
    """Analyze mutual information between various features."""
    results = {}
    
    prices = df["price"].values
    volumes = df["volume"].values
    venues = pd.factorize(df["venue"])[0]
    
    price_lsb = (prices * 100).astype(int) % 10
    volume_lsb = volumes.astype(int) % 10
    
    # MI between price LSB and venue
    results["mi_price_lsb_venue"] = calculate_mutual_information(price_lsb, venues)
    
    # MI between volume LSB and venue
    results["mi_volume_lsb_venue"] = calculate_mutual_information(volume_lsb, venues)
    
    # MI between consecutive price LSBs (autocorrelation proxy)
    results["mi_price_lsb_lag1"] = calculate_mutual_information(price_lsb[:-1], price_lsb[1:])
    
    # MI between price LSB and volume LSB (cross-channel)
    results["mi_price_lsb_volume_lsb"] = calculate_mutual_information(price_lsb, volume_lsb)
    
    # Entropy of price LSB (for reference)
    counts = np.bincount(price_lsb, minlength=10)
    probs = counts / len(price_lsb)
    results["entropy_price_lsb"] = float(stats.entropy(probs, base=2))
    
    # Theoretical max MI if perfectly correlated
    results["max_possible_mi"] = np.log2(min(10, len(np.unique(venues))))
    
    # Normalized MI (0-1 scale)
    results["normalized_mi_venue"] = results["mi_price_lsb_venue"] / results["max_possible_mi"]
    
    return results


# =============================================================================
# 2. DECODE ATTEMPT - EXTRACT BIT SEQUENCES
# =============================================================================

def extract_bit_sequence(values: np.ndarray, method: str = "lsb") -> str:
    """Extract binary string from values using various methods."""
    if method == "lsb":
        # Simple LSB extraction
        bits = (values.astype(int) % 2).astype(str)
        return "".join(bits)
    elif method == "direction":
        # Price direction (up=1, down=0)
        changes = np.diff(values)
        bits = (changes > 0).astype(int).astype(str)
        return "".join(bits)
    elif method == "venue":
        # Venue binary encoding (OTC=1, exchange=0)
        bits = (values == "OTC").astype(int).astype(str)
        return "".join(bits)
    return ""


def bits_to_ascii(bitstring: str) -> str:
    """Convert bit string to ASCII, filtering printable chars."""
    result = []
    for i in range(0, len(bitstring) - 7, 8):
        byte = bitstring[i:i+8]
        try:
            char = chr(int(byte, 2))
            if char in string.printable:
                result.append(char)
            else:
                result.append(".")
        except:
            result.append("?")
    return "".join(result)


def find_repeating_patterns(bitstring: str, min_len: int = 8, max_len: int = 32) -> list:
    """Find repeating patterns in bitstring that could be sync markers."""
    patterns = []
    for length in range(min_len, min(max_len, len(bitstring) // 4)):
        pattern_counts = Counter()
        for i in range(len(bitstring) - length):
            pattern = bitstring[i:i+length]
            pattern_counts[pattern] += 1
        
        # Find patterns that repeat more than expected by chance
        expected = len(bitstring) / (2 ** length)
        for pattern, count in pattern_counts.most_common(5):
            if count > expected * 5 and count > 10:  # 5x more than random
                patterns.append({
                    "pattern": pattern,
                    "length": length,
                    "count": count,
                    "expected": expected,
                    "ratio": count / expected
                })
    
    return sorted(patterns, key=lambda x: x["ratio"], reverse=True)[:10]


def decode_attempt(df: pd.DataFrame) -> dict:
    """Attempt to decode hidden messages from various channels."""
    results = {}
    
    # Sample for efficiency
    sample = df.head(10000)
    
    prices = sample["price"].values
    volumes = sample["volume"].values
    venues = sample["venue"].values
    
    # Extract bit sequences
    price_lsb_bits = extract_bit_sequence(prices * 100, "lsb")
    volume_lsb_bits = extract_bit_sequence(volumes, "lsb")
    direction_bits = extract_bit_sequence(prices, "direction")
    venue_bits = extract_bit_sequence(venues, "venue")
    
    results["extracted_bits"] = {
        "price_lsb": {
            "length": len(price_lsb_bits),
            "ones_ratio": price_lsb_bits.count("1") / len(price_lsb_bits) if price_lsb_bits else 0,
            "sample": price_lsb_bits[:100],
            "as_ascii_sample": bits_to_ascii(price_lsb_bits[:256])
        },
        "volume_lsb": {
            "length": len(volume_lsb_bits),
            "ones_ratio": volume_lsb_bits.count("1") / len(volume_lsb_bits) if volume_lsb_bits else 0,
            "sample": volume_lsb_bits[:100]
        },
        "price_direction": {
            "length": len(direction_bits),
            "ones_ratio": direction_bits.count("1") / len(direction_bits) if direction_bits else 0
        },
        "venue_otc": {
            "length": len(venue_bits),
            "ones_ratio": venue_bits.count("1") / len(venue_bits) if venue_bits else 0
        }
    }
    
    # Find repeating patterns (potential sync markers)
    results["repeating_patterns"] = {
        "price_lsb": find_repeating_patterns(price_lsb_bits),
        "volume_lsb": find_repeating_patterns(volume_lsb_bits)
    }
    
    return results


# =============================================================================
# 3. HIDDEN MARKOV MODEL FOR VENUE SEQUENCES
# =============================================================================

def fit_hmm_simple(sequences: np.ndarray, n_states: int = 3) -> dict:
    """Fit a simple HMM to venue sequences using EM-like approach."""
    # Simplified HMM: just estimate transition matrix
    unique_venues = np.unique(sequences)
    n_venues = len(unique_venues)
    
    venue_to_idx = {v: i for i, v in enumerate(unique_venues)}
    
    # Transition count matrix
    transitions = np.zeros((n_venues, n_venues))
    for i in range(len(sequences) - 1):
        from_idx = venue_to_idx[sequences[i]]
        to_idx = venue_to_idx[sequences[i + 1]]
        transitions[from_idx, to_idx] += 1
    
    # Normalize to probabilities
    row_sums = transitions.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1
    transition_probs = transitions / row_sums
    
    # Calculate entropy of transition distribution
    transition_entropy = []
    for row in transition_probs:
        if row.sum() > 0:
            h = stats.entropy(row + 1e-10)
            transition_entropy.append(h)
    
    # Detect anomalous transitions (low probability)
    anomalous = []
    for i in range(len(sequences) - 1):
        from_idx = venue_to_idx[sequences[i]]
        to_idx = venue_to_idx[sequences[i + 1]]
        prob = transition_probs[from_idx, to_idx]
        if prob < 0.01:  # Very unlikely transition
            anomalous.append({
                "position": i,
                "from": str(sequences[i]),
                "to": str(sequences[i + 1]),
                "probability": float(prob)
            })
    
    return {
        "n_venues": n_venues,
        "venues": [str(v) for v in unique_venues],
        "mean_transition_entropy": float(np.mean(transition_entropy)),
        "max_transition_entropy": float(np.max(transition_entropy)),
        "anomalous_transitions": anomalous[:20],  # Top 20
        "most_likely_transitions": [
            {
                "from": str(unique_venues[i]),
                "to": str(unique_venues[j]),
                "probability": float(transition_probs[i, j])
            }
            for i in range(n_venues)
            for j in range(n_venues)
            if transition_probs[i, j] > 0.3
        ]
    }


# =============================================================================
# 4. WAVELET ANALYSIS ON TIMING
# =============================================================================

def wavelet_timing_analysis(df: pd.DataFrame) -> dict:
    """Apply FFT spectral analysis to detect hidden timing patterns."""
    # Parse timestamps
    try:
        df["ts"] = pd.to_datetime(df["timestamp"], format="ISO8601")
    except:
        return {"error": "Cannot parse timestamps"}
    
    # Calculate inter-arrival times
    iat = df["ts"].diff().dt.total_seconds().dropna().values * 1000  # milliseconds
    
    # Remove outliers
    iat = iat[(iat > 0) & (iat < np.percentile(iat, 99))]
    
    if len(iat) < 1000:
        return {"error": "Insufficient data"}
    
    # Subsample for analysis
    signal = iat[:4096]  # Power of 2 for FFT efficiency
    
    try:
        # Apply FFT
        n = len(signal)
        yf = fft(signal - np.mean(signal))  # Remove DC component
        xf = fftfreq(n, d=np.mean(signal)/1000)[:n//2]  # Frequency in Hz
        
        # Power spectrum
        power = 2.0/n * np.abs(yf[:n//2])**2
        
        # Find peaks in spectrum
        peak_indices, properties = find_peaks(power, height=np.mean(power) * 3)
        
        peaks = []
        for idx in peak_indices[:10]:  # Top 10 peaks
            if xf[idx] > 0:
                peaks.append({
                    "frequency_hz": float(xf[idx]),
                    "period_ms": float(1000 / xf[idx]) if xf[idx] > 0 else 0,
                    "power": float(power[idx])
                })
        
        peaks.sort(key=lambda x: x["power"], reverse=True)
        
        return {
            "signal_length": len(signal),
            "spectral_peaks": peaks[:5],
            "mean_power": float(np.mean(power)),
            "dominant_period_ms": peaks[0]["period_ms"] if peaks else None,
            "n_significant_peaks": len(peak_indices),
            "interpretation": "Multi-scale structure detected" if len(peak_indices) > 3 else "Weak structure"
        }
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# 5. EVENT WINDOW ANALYSIS
# =============================================================================

def analyze_event_windows(df: pd.DataFrame) -> dict:
    """Analyze patterns in specific time windows."""
    try:
        df["ts"] = pd.to_datetime(df["timestamp"], format="ISO8601")
    except:
        return {"error": "Cannot parse timestamps"}
    
    df["hour"] = df["ts"].dt.hour
    df["minute"] = df["ts"].dt.minute
    
    # Define windows
    windows = {
        "premarket": df[(df["hour"] >= 4) & (df["hour"] < 9) | 
                         ((df["hour"] == 9) & (df["minute"] < 30))],
        "open_15min": df[(df["hour"] == 9) & (df["minute"] >= 30) | 
                          ((df["hour"] == 10) & (df["minute"] < 15))],
        "midday": df[(df["hour"] >= 11) & (df["hour"] < 14)],
        "close_30min": df[(df["hour"] == 15) & (df["minute"] >= 30) | (df["hour"] == 16)],
        "afterhours": df[df["hour"] >= 16]
    }
    
    results = {}
    for window_name, window_df in windows.items():
        if len(window_df) < 100:
            results[window_name] = {"count": len(window_df), "error": "Insufficient data"}
            continue
        
        prices = window_df["price"].values
        price_lsb = (prices * 100).astype(int) % 10
        
        # Chi-square test
        observed = np.bincount(price_lsb, minlength=10)
        expected = np.full(10, len(price_lsb) / 10)
        chi2, pval = stats.chisquare(observed, expected)
        
        results[window_name] = {
            "count": len(window_df),
            "chi2": float(chi2),
            "pvalue": float(pval),
            "significant": bool(pval < 0.05),
            "lsb_distribution": observed.tolist()
        }
    
    return results


# =============================================================================
# MAIN ANALYSIS
# =============================================================================

def analyze_single_day(sample_dir: Path) -> dict:
    """Run full advanced analysis on a single day."""
    trades_files = list(sample_dir.glob("raw_ticks/*_trades.csv"))
    
    if not trades_files:
        return {"error": "No trades found"}
    
    df = pd.read_csv(trades_files[0])
    
    required_cols = ["timestamp", "price", "volume", "venue"]
    if not all(col in df.columns for col in required_cols):
        return {"error": "Missing required columns"}
    
    date = sample_dir.name.replace("sample_", "")
    
    # Subsample for performance
    sample_df = df.head(50000) if len(df) > 50000 else df
    
    return {
        "date": date,
        "total_trades": len(df),
        "mutual_information": analyze_mutual_information(sample_df),
        "decode_attempt": decode_attempt(sample_df),
        "hmm_venue": fit_hmm_simple(sample_df["venue"].astype(str).values),
        "wavelet": wavelet_timing_analysis(sample_df),
        "event_windows": analyze_event_windows(sample_df)
    }


def main():
    """Run advanced analysis suite."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    sample_dirs = sorted(DATA_DIR.glob("sample_*"))
    
    print("=" * 60)
    print("ADVANCED STEGANALYSIS SUITE")
    print("=" * 60)
    
    results = []
    summary = {
        "high_mi_days": 0,
        "repeating_pattern_days": 0,
        "wavelet_structure_days": 0,
        "event_anomaly_days": 0
    }
    
    for sample_dir in sample_dirs:
        print(f"\nAnalyzing {sample_dir.name}...")
        try:
            result = analyze_single_day(sample_dir)
            results.append(result)
            
            if "error" not in result:
                # Update summary
                mi = result["mutual_information"]["normalized_mi_venue"]
                if mi > 0.1:  # Significant mutual information
                    summary["high_mi_days"] += 1
                
                if result["decode_attempt"]["repeating_patterns"]["price_lsb"]:
                    summary["repeating_pattern_days"] += 1
                
                if result["wavelet"].get("interpretation") == "Multi-scale structure detected":
                    summary["wavelet_structure_days"] += 1
                
                # Check event windows
                for window, data in result["event_windows"].items():
                    if isinstance(data, dict) and data.get("significant"):
                        summary["event_anomaly_days"] += 1
                        break
                
                print(f"  MI (price_lsb/venue): {mi:.4f}")
                print(f"  Repeating patterns: {len(result['decode_attempt']['repeating_patterns']['price_lsb'])}")
                
        except Exception as e:
            print(f"  Error: {e}")
            results.append({"date": sample_dir.name, "error": str(e)})
    
    # Save results
    total_valid = len([r for r in results if "error" not in r])
    summary["total_days"] = total_valid
    
    output_file = OUTPUT_DIR / "advanced_analysis_results.json"
    with open(output_file, "w") as f:
        json.dump({
            "analysis_timestamp": datetime.now().isoformat(),
            "summary": summary,
            "daily_results": results
        }, f, indent=2, default=str)
    
    # Generate report
    generate_report(results, summary)
    
    print("\n" + "=" * 60)
    print("ADVANCED ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"Days analyzed: {total_valid}")
    print(f"High MI days: {summary['high_mi_days']}")
    print(f"Repeating pattern days: {summary['repeating_pattern_days']}")
    print(f"Wavelet structure days: {summary['wavelet_structure_days']}")


def generate_report(results: list, summary: dict):
    """Generate comprehensive markdown report."""
    report_file = OUTPUT_DIR / "advanced_analysis_report.md"
    
    with open(report_file, "w") as f:
        f.write("# Advanced Steganalysis Report\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Summary\n\n")
        f.write("| Analysis | Finding |\n")
        f.write("|----------|--------|\n")
        if summary["total_days"] > 0:
            f.write(f"| High MI days | {summary['high_mi_days']}/{summary['total_days']} ({100*summary['high_mi_days']/summary['total_days']:.1f}%) |\n")
            f.write(f"| Repeating patterns | {summary['repeating_pattern_days']}/{summary['total_days']} ({100*summary['repeating_pattern_days']/summary['total_days']:.1f}%) |\n")
            f.write(f"| Wavelet structure | {summary['wavelet_structure_days']}/{summary['total_days']} ({100*summary['wavelet_structure_days']/summary['total_days']:.1f}%) |\n")
            f.write(f"| Event anomalies | {summary['event_anomaly_days']}/{summary['total_days']} ({100*summary['event_anomaly_days']/summary['total_days']:.1f}%) |\n\n")
        
        f.write("## Mutual Information Analysis\n\n")
        f.write("Measures statistical dependence between price LSB and venue choice.\n\n")
        valid = [r for r in results if "error" not in r]
        if valid:
            f.write("| Date | MI (LSB/Venue) | Normalized MI |\n")
            f.write("|------|----------------|---------------|\n")
            for r in sorted(valid, key=lambda x: x["mutual_information"]["normalized_mi_venue"], reverse=True)[:10]:
                mi = r["mutual_information"]
                f.write(f"| {r['date']} | {mi['mi_price_lsb_venue']:.4f} | {mi['normalized_mi_venue']:.4f} |\n")
        
        f.write("\n## Decode Attempts\n\n")
        f.write("### Extracted ASCII (from price LSB)\n\n")
        for r in valid[:3]:
            decode = r["decode_attempt"]["extracted_bits"]["price_lsb"]
            f.write(f"**{r['date']}**: `{decode['as_ascii_sample'][:50]}...`\n\n")
        
        f.write("### Repeating Patterns Found\n\n")
        for r in valid:
            patterns = r["decode_attempt"]["repeating_patterns"]["price_lsb"]
            if patterns:
                f.write(f"**{r['date']}**:\n")
                for p in patterns[:3]:
                    f.write(f"- Pattern `{p['pattern']}` ({p['length']} bits): {p['count']}x (expected {p['expected']:.1f})\n")
                f.write("\n")
        
        f.write("## HMM Venue Sequences\n\n")
        f.write("Most likely venue transitions:\n\n")
        for r in valid[:3]:
            hmm = r["hmm_venue"]
            f.write(f"**{r['date']}** (entropy: {hmm['mean_transition_entropy']:.2f}):\n")
            for t in hmm["most_likely_transitions"][:5]:
                f.write(f"- {t['from']} → {t['to']}: {t['probability']:.2f}\n")
            f.write("\n")
        
        f.write("## Event Window Analysis\n\n")
        f.write("Checking for time-of-day specific patterns:\n\n")
        for r in valid[:3]:
            f.write(f"**{r['date']}**:\n")
            for window, data in r["event_windows"].items():
                if isinstance(data, dict) and "pvalue" in data:
                    marker = "⚠️" if data["significant"] else ""
                    f.write(f"- {window}: p={data['pvalue']:.4f} {marker}\n")
            f.write("\n")
    
    print(f"Report saved to: {report_file}")


if __name__ == "__main__":
    main()
