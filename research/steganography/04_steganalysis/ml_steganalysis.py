#!/usr/bin/env python3
"""
Steganography Research: ML-Based Steganalysis (Phase 4)
=======================================================

Trains anomaly detection models to detect potential steganographic
embedding in financial market data.

Approach:
1. Generate synthetic stego-data by embedding known patterns
2. Train models to distinguish clean vs stego data
3. Evaluate detection capability on held-out data
4. Apply to real GME data to score "stego likelihood"
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
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score, confusion_matrix

# Configuration
DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "samples"
OUTPUT_DIR = Path(__file__).resolve().parent / "results"


class StegoDataGenerator:
    """Generates synthetic steganographic data for training."""
    
    def __init__(self, embedding_rate: float = 0.1):
        """
        Args:
            embedding_rate: Fraction of values to modify (0-1)
        """
        self.embedding_rate = embedding_rate
    
    def embed_lsb_pattern(self, prices: np.ndarray, pattern: str = "alternating") -> np.ndarray:
        """
        Embed LSB patterns in price data.
        
        Patterns:
        - alternating: 0, 1, 0, 1, ...
        - zeros: all 0s
        - ones: all 1s
        - random: random bits
        """
        modified = prices.copy()
        n_embed = int(len(prices) * self.embedding_rate)
        embed_indices = np.random.choice(len(prices), n_embed, replace=False)
        
        for i, idx in enumerate(embed_indices):
            # Get current price in cents
            cents = int(modified[idx] * 100)
            
            if pattern == "alternating":
                target_bit = i % 2
            elif pattern == "zeros":
                target_bit = 0
            elif pattern == "ones":
                target_bit = 1
            else:  # random
                target_bit = np.random.randint(0, 2)
            
            # Modify LSB
            if cents % 2 != target_bit:
                cents += 1 if target_bit == 1 else -1
            
            modified[idx] = cents / 100.0
        
        return modified
    
    def embed_timing_pattern(self, timestamps: np.ndarray, period_ms: int = 100) -> np.ndarray:
        """
        Embed timing patterns in inter-arrival times.
        Modulates intervals to cluster around specific periods.
        """
        modified = timestamps.copy()
        n_embed = int(len(timestamps) * self.embedding_rate)
        embed_indices = np.random.choice(len(timestamps) - 1, n_embed, replace=False)
        
        for idx in embed_indices:
            # Add small offset to make interval closer to period_ms
            current_interval = modified[idx + 1] - modified[idx]
            target_interval = period_ms * 1_000_000  # Convert to ns
            
            # Nudge toward target
            adjustment = (target_interval - current_interval) * 0.3
            modified[idx + 1] += adjustment
        
        return modified
    
    def embed_volume_pattern(self, volumes: np.ndarray, round_to: int = 100) -> np.ndarray:
        """
        Embed volume patterns by rounding to specific lot sizes.
        """
        modified = volumes.copy()
        n_embed = int(len(volumes) * self.embedding_rate)
        embed_indices = np.random.choice(len(volumes), n_embed, replace=False)
        
        for idx in embed_indices:
            # Round to nearest lot size
            modified[idx] = round(volumes[idx] / round_to) * round_to
        
        return modified


def extract_features(df: pd.DataFrame) -> np.ndarray:
    """
    Extract features for steganalysis from trade data.
    """
    features = []
    
    prices = df["price"].values
    volumes = df["volume"].values
    
    # LSB features
    price_lsb = (prices * 100).astype(int) % 10
    volume_lsb = volumes.astype(int) % 10
    
    # LSB distribution (chi-square stat)
    price_lsb_counts = np.bincount(price_lsb, minlength=10)
    expected = np.full(10, len(prices) / 10)
    price_chi2, _ = stats.chisquare(price_lsb_counts, expected)
    features.append(price_chi2)
    
    # LSB entropy
    price_lsb_probs = price_lsb_counts / len(prices)
    price_lsb_entropy = stats.entropy(price_lsb_probs)
    features.append(price_lsb_entropy)
    
    # Volume LSB stats
    volume_lsb_counts = np.bincount(volume_lsb, minlength=10)
    volume_chi2, _ = stats.chisquare(volume_lsb_counts, expected)
    features.append(volume_chi2)
    
    # Autocorrelation of LSB
    if len(price_lsb) > 10:
        autocorr = np.corrcoef(price_lsb[:-1], price_lsb[1:])[0, 1]
        features.append(autocorr if not np.isnan(autocorr) else 0)
    else:
        features.append(0)
    
    # Price change features
    price_changes = np.diff(prices)
    features.append(np.std(price_changes))
    features.append(stats.skew(price_changes))
    features.append(stats.kurtosis(price_changes))
    
    # Volume features
    features.append(np.mean(volumes % 100 == 0))  # Round lot ratio
    features.append(np.std(volumes))
    
    # Runs test on price direction
    directions = np.sign(price_changes)
    runs = 1
    for i in range(1, len(directions)):
        if directions[i] != directions[i-1]:
            runs += 1
    features.append(runs / len(directions) if len(directions) > 0 else 0)
    
    return np.array(features)


def create_training_data(sample_dirs: list, generator: StegoDataGenerator) -> tuple:
    """
    Create labeled training data: clean + synthetic stego samples.
    """
    X_clean = []
    X_stego = []
    
    for sample_dir in sample_dirs:
        trades_files = list(sample_dir.glob("raw_ticks/*_trades.csv"))
        if not trades_files:
            continue
        
        df = pd.read_csv(trades_files[0])
        if "price" not in df.columns or "volume" not in df.columns:
            continue
        
        # Sample 10000 rows for efficiency
        if len(df) > 10000:
            df = df.sample(10000, random_state=42)
        
        # Clean features
        clean_features = extract_features(df)
        X_clean.append(clean_features)
        
        # Create stego version with LSB embedding
        df_stego = df.copy()
        df_stego["price"] = generator.embed_lsb_pattern(df["price"].values, "alternating")
        df_stego["volume"] = generator.embed_volume_pattern(df["volume"].values, 100)
        
        stego_features = extract_features(df_stego)
        X_stego.append(stego_features)
    
    X_clean = np.array(X_clean)
    X_stego = np.array(X_stego)
    
    # Combine and label
    X = np.vstack([X_clean, X_stego])
    y = np.array([0] * len(X_clean) + [1] * len(X_stego))
    
    return X, y


def train_detector(X: np.ndarray, y: np.ndarray) -> tuple:
    """
    Train steganalysis detector model.
    """
    # Split data
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)
    
    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # Train Random Forest classifier
    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X_train_scaled, y_train)
    
    # Evaluate
    y_pred = clf.predict(X_test_scaled)
    y_prob = clf.predict_proba(X_test_scaled)[:, 1]
    
    metrics = {
        "accuracy": float((y_pred == y_test).mean()),
        "roc_auc": float(roc_auc_score(y_test, y_prob)),
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
        "feature_importance": dict(zip(
            ["price_chi2", "price_entropy", "volume_chi2", "autocorr", 
             "price_std", "price_skew", "price_kurt", "round_lot", "vol_std", "runs"],
            clf.feature_importances_.tolist()
        ))
    }
    
    return clf, scaler, metrics


def score_real_data(sample_dirs: list, clf, scaler) -> list:
    """
    Score real market data for stego likelihood.
    """
    scores = []
    
    for sample_dir in sample_dirs:
        trades_files = list(sample_dir.glob("raw_ticks/*_trades.csv"))
        if not trades_files:
            continue
        
        df = pd.read_csv(trades_files[0])
        if "price" not in df.columns or "volume" not in df.columns:
            continue
        
        # Sample for efficiency
        if len(df) > 10000:
            df = df.sample(10000, random_state=42)
        
        features = extract_features(df)
        features_scaled = scaler.transform(features.reshape(1, -1))
        
        prob = clf.predict_proba(features_scaled)[0, 1]
        
        date = sample_dir.name.replace("sample_", "")
        scores.append({
            "date": date,
            "stego_probability": float(prob),
            "classification": "Suspicious" if prob > 0.5 else "Normal"
        })
    
    return scores


def main():
    """Run ML-based steganalysis pipeline."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    sample_dirs = sorted(DATA_DIR.glob("sample_*"))
    
    if len(sample_dirs) < 5:
        print("Insufficient data for ML training")
        return
    
    print("=" * 60)
    print("PHASE 4: ML-BASED STEGANALYSIS")
    print("=" * 60)
    
    # Create synthetic stego generator
    generator = StegoDataGenerator(embedding_rate=0.15)
    
    # Create training data
    print("\n1. Generating training data...")
    X, y = create_training_data(sample_dirs, generator)
    print(f"   Created {len(X)} samples ({sum(y==0)} clean, {sum(y==1)} stego)")
    
    # Train detector
    print("\n2. Training detector model...")
    clf, scaler, metrics = train_detector(X, y)
    print(f"   Accuracy: {metrics['accuracy']:.3f}")
    print(f"   ROC-AUC: {metrics['roc_auc']:.3f}")
    
    # Score real data
    print("\n3. Scoring real market data...")
    scores = score_real_data(sample_dirs, clf, scaler)
    
    suspicious_count = sum(1 for s in scores if s["classification"] == "Suspicious")
    print(f"   Analyzed {len(scores)} days")
    print(f"   Flagged as suspicious: {suspicious_count} ({100*suspicious_count/len(scores):.1f}%)")
    
    # Save results
    results = {
        "analysis_timestamp": datetime.now().isoformat(),
        "model_metrics": metrics,
        "daily_scores": scores,
        "summary": {
            "total_days": len(scores),
            "suspicious_days": suspicious_count,
            "suspicious_rate": suspicious_count / len(scores) if scores else 0
        }
    }
    
    output_file = OUTPUT_DIR / "ml_steganalysis_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    # Generate report
    report_file = OUTPUT_DIR / "ml_steganalysis_report.md"
    with open(report_file, "w") as f:
        f.write("# ML-Based Steganalysis Report (Phase 4)\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        
        f.write("## Model Performance\n\n")
        f.write("| Metric | Value |\n")
        f.write("|--------|-------|\n")
        f.write(f"| Accuracy | {metrics['accuracy']:.3f} |\n")
        f.write(f"| ROC-AUC | {metrics['roc_auc']:.3f} |\n\n")
        
        f.write("## Feature Importance\n\n")
        f.write("| Feature | Importance |\n")
        f.write("|---------|------------|\n")
        sorted_features = sorted(metrics['feature_importance'].items(), 
                                  key=lambda x: x[1], reverse=True)
        for feat, imp in sorted_features:
            f.write(f"| {feat} | {imp:.3f} |\n")
        f.write("\n")
        
        f.write("## Real Data Scores\n\n")
        f.write("| Date | Stego Probability | Classification |\n")
        f.write("|------|-------------------|----------------|\n")
        for s in sorted(scores, key=lambda x: x['stego_probability'], reverse=True):
            emoji = "⚠️" if s['classification'] == "Suspicious" else ""
            f.write(f"| {s['date']} | {s['stego_probability']:.3f} | {s['classification']} {emoji} |\n")
        
        f.write("\n## Interpretation\n\n")
        if suspicious_count > len(scores) * 0.3:
            f.write("> **⚠️ High suspicion rate.** However, this may indicate the model is detecting\n")
            f.write("> legitimate market microstructure patterns rather than actual steganography.\n")
        else:
            f.write("> Most days score as 'Normal'. The model can distinguish synthetic stego\n")
            f.write("> from real market data, suggesting real data is not heavily modified.\n")
    
    print("\n" + "=" * 60)
    print("ML STEGANALYSIS COMPLETE")
    print("=" * 60)
    print(f"Model accuracy: {metrics['accuracy']:.3f}")
    print(f"Suspicious days: {suspicious_count}/{len(scores)}")
    print(f"\nResults saved to: {output_file}")
    print(f"Report saved to: {report_file}")


if __name__ == "__main__":
    main()
