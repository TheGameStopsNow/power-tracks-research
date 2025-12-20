#!/usr/bin/env python3
"""
Phase 8: LSTM Deep Learning for Sequence Pattern Detection
==========================================================

Uses LSTM neural networks to detect anomalous patterns in:
1. Price LSB sequences
2. Volume sequences  
3. Venue transition sequences
4. Timing sequences

The model learns normal market patterns and flags deviations
that could indicate steganographic encoding.
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split

# Try to import TensorFlow/Keras
try:
    import tensorflow as tf
    from tensorflow.keras.models import Sequential, Model
    from tensorflow.keras.layers import LSTM, Dense, Dropout, Input, RepeatVector, TimeDistributed
    from tensorflow.keras.callbacks import EarlyStopping
    HAS_TF = True
except ImportError:
    HAS_TF = False
    print("TensorFlow not available, using PyTorch")

# Try PyTorch as fallback
if not HAS_TF:
    try:
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset
        HAS_TORCH = True
    except ImportError:
        HAS_TORCH = False

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "samples"
OUTPUT_DIR = Path(__file__).resolve().parent / "results"


class LSTMAutoencoder:
    """LSTM Autoencoder for anomaly detection."""
    
    def __init__(self, sequence_length=50, n_features=4, encoding_dim=16):
        self.sequence_length = sequence_length
        self.n_features = n_features
        self.encoding_dim = encoding_dim
        self.model = None
        self.scaler = MinMaxScaler()
        
    def build_model(self):
        """Build LSTM autoencoder model."""
        if not HAS_TF:
            return self._build_pytorch_model()
        
        # Encoder
        inputs = Input(shape=(self.sequence_length, self.n_features))
        encoded = LSTM(64, activation='relu', return_sequences=True)(inputs)
        encoded = LSTM(32, activation='relu', return_sequences=False)(encoded)
        encoded = Dense(self.encoding_dim, activation='relu')(encoded)
        
        # Decoder
        decoded = RepeatVector(self.sequence_length)(encoded)
        decoded = LSTM(32, activation='relu', return_sequences=True)(decoded)
        decoded = LSTM(64, activation='relu', return_sequences=True)(decoded)
        decoded = TimeDistributed(Dense(self.n_features))(decoded)
        
        self.model = Model(inputs, decoded)
        self.model.compile(optimizer='adam', loss='mse')
        
        return self.model
    
    def _build_pytorch_model(self):
        """Build PyTorch LSTM model as fallback."""
        # Simple implementation for when TF not available
        pass
    
    def prepare_sequences(self, df: pd.DataFrame) -> np.ndarray:
        """Prepare sequence data from dataframe."""
        features = []
        
        # Feature 1: Price LSB
        if "price" in df.columns:
            price_lsb = (df["price"] * 100).astype(int) % 10
            features.append(price_lsb.values)
        
        # Feature 2: Volume LSB
        if "volume" in df.columns:
            volume_lsb = df["volume"].astype(int) % 10
            features.append(volume_lsb.values)
        
        # Feature 3: Venue encoding
        if "venue" in df.columns:
            venue_encoded = pd.factorize(df["venue"])[0]
            features.append(venue_encoded)
        
        # Feature 4: Price direction
        if "price" in df.columns:
            price_dir = np.sign(df["price"].diff().fillna(0)).values
            features.append(price_dir)
        
        if not features:
            return np.array([])
        
        # Stack features
        data = np.column_stack(features)
        
        # Scale to [0, 1]
        data = self.scaler.fit_transform(data)
        
        # Create sequences
        sequences = []
        for i in range(len(data) - self.sequence_length):
            sequences.append(data[i:i + self.sequence_length])
        
        return np.array(sequences)
    
    def train(self, sequences: np.ndarray, epochs=50, batch_size=32):
        """Train the autoencoder on normal data."""
        if self.model is None:
            self.build_model()
        
        if not HAS_TF:
            print("  TensorFlow not available, skipping training")
            return None
        
        X_train, X_val = train_test_split(sequences, test_size=0.2, random_state=42)
        
        early_stop = EarlyStopping(
            monitor='val_loss',
            patience=5,
            restore_best_weights=True
        )
        
        history = self.model.fit(
            X_train, X_train,
            epochs=epochs,
            batch_size=batch_size,
            validation_data=(X_val, X_val),
            callbacks=[early_stop],
            verbose=0
        )
        
        return history
    
    def detect_anomalies(self, sequences: np.ndarray, threshold_percentile=95):
        """Detect anomalous sequences based on reconstruction error."""
        if self.model is None or not HAS_TF:
            return np.array([]), np.array([])
        
        # Get reconstructions
        reconstructions = self.model.predict(sequences, verbose=0)
        
        # Calculate reconstruction error per sequence
        mse = np.mean(np.power(sequences - reconstructions, 2), axis=(1, 2))
        
        # Determine threshold
        threshold = np.percentile(mse, threshold_percentile)
        
        # Flag anomalies
        anomalies = mse > threshold
        
        return anomalies, mse


class SequencePatternAnalyzer:
    """Analyzes sequences for hidden patterns."""
    
    def __init__(self, sequence_length=100):
        self.sequence_length = sequence_length
        self.autoencoder = LSTMAutoencoder(sequence_length=sequence_length)
        
    def analyze_file(self, filepath: Path) -> dict:
        """Analyze a single file for sequence anomalies."""
        df = pd.read_csv(filepath)
        
        required_cols = ["price", "volume"]
        if not all(col in df.columns for col in required_cols):
            return {"error": "Missing required columns"}
        
        # Prepare sequences
        sequences = self.autoencoder.prepare_sequences(df)
        
        if len(sequences) < 100:
            return {"error": "Insufficient sequences"}
        
        # Train on first portion (assumed normal)
        train_size = int(len(sequences) * 0.7)
        train_sequences = sequences[:train_size]
        
        # Train model
        self.autoencoder.train(train_sequences, epochs=30)
        
        # Detect anomalies in all sequences
        if HAS_TF:
            anomalies, errors = self.autoencoder.detect_anomalies(sequences)
            
            return {
                "n_sequences": len(sequences),
                "n_anomalies": int(anomalies.sum()),
                "anomaly_rate": float(anomalies.mean()),
                "mean_error": float(errors.mean()),
                "max_error": float(errors.max()),
                "error_std": float(errors.std())
            }
        else:
            return {
                "n_sequences": len(sequences),
                "error": "TensorFlow required for LSTM training"
            }


def analyze_with_simple_lstm(df: pd.DataFrame) -> dict:
    """Simple LSTM-based pattern analysis without full autoencoder."""
    # Extract features
    prices = df["price"].values if "price" in df.columns else np.array([])
    volumes = df["volume"].values if "volume" in df.columns else np.array([])
    
    if len(prices) < 100:
        return {"error": "Insufficient data"}
    
    # Calculate sequence statistics
    price_lsb = (prices * 100).astype(int) % 10
    volume_lsb = volumes.astype(int) % 10
    
    # N-gram analysis for pattern detection
    n = 8  # Look for 8-element patterns
    price_patterns = {}
    volume_patterns = {}
    
    for i in range(len(price_lsb) - n):
        pattern = tuple(price_lsb[i:i+n])
        price_patterns[pattern] = price_patterns.get(pattern, 0) + 1
        
        vol_pattern = tuple(volume_lsb[i:i+n])
        volume_patterns[vol_pattern] = volume_patterns.get(vol_pattern, 0) + 1
    
    # Find repeated patterns
    price_repeated = sum(1 for c in price_patterns.values() if c > 5)
    volume_repeated = sum(1 for c in volume_patterns.values() if c > 5)
    
    # Entropy of n-grams
    price_probs = np.array(list(price_patterns.values())) / sum(price_patterns.values())
    price_entropy = -np.sum(price_probs * np.log2(price_probs + 1e-10))
    max_entropy = np.log2(len(price_patterns))
    
    return {
        "n_observations": len(prices),
        "price_ngram_patterns": len(price_patterns),
        "price_repeated_patterns": price_repeated,
        "volume_ngram_patterns": len(volume_patterns),
        "volume_repeated_patterns": volume_repeated,
        "price_ngram_entropy": float(price_entropy),
        "normalized_entropy": float(price_entropy / max_entropy) if max_entropy > 0 else 0,
        "pattern_detected": price_repeated > 100 or volume_repeated > 100
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("LSTM SEQUENCE PATTERN DETECTION")
    print("=" * 60)
    
    if HAS_TF:
        print(f"TensorFlow version: {tf.__version__}")
    else:
        print("Using simple n-gram analysis (TensorFlow not available)")
    
    sample_dirs = sorted(DATA_DIR.glob("sample_*"))
    
    results = []
    
    for sample_dir in sample_dirs:
        trades_files = list(sample_dir.glob("raw_ticks/*_trades.csv"))
        if not trades_files:
            continue
        
        date = sample_dir.name.replace("sample_", "")
        print(f"\n>>> {date}")
        
        df = pd.read_csv(trades_files[0])
        print(f"  {len(df):,} trades")
        
        # Use subset for analysis
        df_sample = df.head(50000) if len(df) > 50000 else df
        
        if HAS_TF:
            # Full LSTM analysis
            analyzer = SequencePatternAnalyzer(sequence_length=50)
            result = analyzer.analyze_file(trades_files[0])
        else:
            # Simple pattern analysis
            result = analyze_with_simple_lstm(df_sample)
        
        result["date"] = date
        results.append(result)
        
        if "anomaly_rate" in result:
            print(f"  Anomaly rate: {result['anomaly_rate']:.2%}")
        elif "pattern_detected" in result:
            print(f"  Pattern detected: {result['pattern_detected']}")
            print(f"  Repeated patterns: {result['price_repeated_patterns']}")
    
    # Summary
    summary = {
        "method": "LSTM Autoencoder" if HAS_TF else "N-gram Analysis",
        "days_analyzed": len(results),
        "has_tensorflow": HAS_TF
    }
    
    if HAS_TF:
        anomaly_rates = [r.get("anomaly_rate", 0) for r in results if "anomaly_rate" in r]
        if anomaly_rates:
            summary["mean_anomaly_rate"] = float(np.mean(anomaly_rates))
            summary["max_anomaly_rate"] = float(max(anomaly_rates))
    else:
        pattern_counts = [r.get("price_repeated_patterns", 0) for r in results]
        summary["mean_repeated_patterns"] = float(np.mean(pattern_counts))
        summary["max_repeated_patterns"] = int(max(pattern_counts))
        summary["days_with_patterns"] = sum(1 for r in results if r.get("pattern_detected"))
    
    # Save results
    with open(OUTPUT_DIR / "lstm_results.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
            "daily_results": results
        }, f, indent=2, default=str)
    
    # Generate report
    with open(OUTPUT_DIR / "lstm_report.md", "w") as f:
        f.write("# LSTM Sequence Pattern Detection\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        f.write(f"**Method**: {summary['method']}\n\n")
        
        f.write("## Summary\n\n")
        f.write(f"- Days analyzed: {summary['days_analyzed']}\n")
        
        if HAS_TF:
            f.write(f"- Mean anomaly rate: {summary.get('mean_anomaly_rate', 0):.2%}\n")
            f.write(f"- Max anomaly rate: {summary.get('max_anomaly_rate', 0):.2%}\n")
        else:
            f.write(f"- Mean repeated patterns: {summary.get('mean_repeated_patterns', 0):.0f}\n")
            f.write(f"- Days with significant patterns: {summary.get('days_with_patterns', 0)}\n")
        
        f.write("\n## Daily Results\n\n")
        f.write("| Date | Patterns | Repeated | Entropy | Detected |\n")
        f.write("|------|----------|----------|---------|----------|\n")
        for r in results:
            if "error" not in r:
                detected = "✓" if r.get("pattern_detected") else ""
                f.write(f"| {r.get('date', 'N/A')} | {r.get('price_ngram_patterns', 'N/A')} | {r.get('price_repeated_patterns', 'N/A')} | {r.get('normalized_entropy', 0):.3f} | {detected} |\n")
        
        f.write("\n## Interpretation\n\n")
        if summary.get("days_with_patterns", 0) > len(results) / 2:
            f.write("> ⚠️ **Significant sequence patterns detected in majority of days**\n")
        else:
            f.write("> ✅ Sequence patterns are within normal range\n")
    
    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"Results saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
