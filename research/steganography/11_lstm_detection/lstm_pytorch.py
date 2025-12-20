#!/usr/bin/env python3
"""
Phase 8: PyTorch LSTM Autoencoder for Sequence Anomaly Detection
=================================================================

Uses LSTM autoencoder to learn normal trade sequence patterns
and detect anomalies that could indicate steganographic encoding.
"""

import os
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

# Set device
device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
print(f"Using device: {device}")

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "samples"
OUTPUT_DIR = Path(__file__).resolve().parent / "results"


class LSTMEncoder(nn.Module):
    """LSTM encoder."""
    def __init__(self, input_dim, hidden_dim, latent_dim, num_layers=2):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_dim, latent_dim)
        
    def forward(self, x):
        _, (h, _) = self.lstm(x)
        return self.fc(h[-1])


class LSTMDecoder(nn.Module):
    """LSTM decoder."""
    def __init__(self, latent_dim, hidden_dim, output_dim, seq_len, num_layers=2):
        super().__init__()
        self.seq_len = seq_len
        self.fc = nn.Linear(latent_dim, hidden_dim)
        self.lstm = nn.LSTM(hidden_dim, hidden_dim, num_layers, batch_first=True)
        self.out = nn.Linear(hidden_dim, output_dim)
        
    def forward(self, z):
        h = self.fc(z).unsqueeze(1).repeat(1, self.seq_len, 1)
        out, _ = self.lstm(h)
        return self.out(out)


class LSTMAutoencoder(nn.Module):
    """LSTM Autoencoder for sequence anomaly detection."""
    def __init__(self, input_dim, hidden_dim=64, latent_dim=16, seq_len=50, num_layers=2):
        super().__init__()
        self.encoder = LSTMEncoder(input_dim, hidden_dim, latent_dim, num_layers)
        self.decoder = LSTMDecoder(latent_dim, hidden_dim, input_dim, seq_len, num_layers)
        
    def forward(self, x):
        z = self.encoder(x)
        return self.decoder(z)


def prepare_sequences(df: pd.DataFrame, seq_len: int = 50) -> tuple:
    """Prepare sequence data from dataframe."""
    features = []
    
    # Feature 1: Price LSB (normalized)
    if "price" in df.columns:
        price_lsb = ((df["price"] * 100).astype(int) % 10) / 9.0
        features.append(price_lsb.values)
    
    # Feature 2: Volume LSB (normalized)
    if "volume" in df.columns:
        volume_lsb = (df["volume"].astype(int) % 10) / 9.0
        features.append(volume_lsb.values)
    
    # Feature 3: Price direction
    if "price" in df.columns:
        price_dir = (np.sign(df["price"].diff().fillna(0)).values + 1) / 2.0
        features.append(price_dir)
    
    # Feature 4: Volume change direction
    if "volume" in df.columns:
        vol_dir = (np.sign(df["volume"].diff().fillna(0)).values + 1) / 2.0
        features.append(vol_dir)
    
    if not features:
        return None, 0
    
    data = np.column_stack(features).astype(np.float32)
    
    # Create sequences
    sequences = []
    for i in range(len(data) - seq_len):
        sequences.append(data[i:i + seq_len])
    
    return np.array(sequences), len(features)


def train_autoencoder(sequences: np.ndarray, n_features: int, epochs: int = 30, 
                       batch_size: int = 64, seq_len: int = 50) -> tuple:
    """Train the LSTM autoencoder."""
    
    # Split data
    train_data, val_data = train_test_split(sequences, test_size=0.2, random_state=42)
    
    # Create data loaders
    train_tensor = torch.FloatTensor(train_data).to(device)
    val_tensor = torch.FloatTensor(val_data).to(device)
    
    train_loader = DataLoader(TensorDataset(train_tensor, train_tensor), 
                               batch_size=batch_size, shuffle=True)
    
    # Create model
    model = LSTMAutoencoder(
        input_dim=n_features,
        hidden_dim=64,
        latent_dim=16,
        seq_len=seq_len
    ).to(device)
    
    criterion = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    
    # Training loop
    best_loss = float('inf')
    patience = 5
    no_improve = 0
    
    for epoch in range(epochs):
        model.train()
        train_loss = 0
        for batch_x, batch_y in train_loader:
            optimizer.zero_grad()
            output = model(batch_x)
            loss = criterion(output, batch_y)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()
        
        # Validation
        model.eval()
        with torch.no_grad():
            val_output = model(val_tensor)
            val_loss = criterion(val_output, val_tensor).item()
        
        if val_loss < best_loss:
            best_loss = val_loss
            no_improve = 0
        else:
            no_improve += 1
            if no_improve >= patience:
                break
    
    return model, best_loss


def detect_anomalies(model: LSTMAutoencoder, sequences: np.ndarray, 
                      threshold_percentile: float = 95) -> tuple:
    """Detect anomalous sequences."""
    model.eval()
    
    with torch.no_grad():
        tensor = torch.FloatTensor(sequences).to(device)
        reconstructions = model(tensor).cpu().numpy()
    
    # Calculate reconstruction error
    mse = np.mean(np.power(sequences - reconstructions, 2), axis=(1, 2))
    
    # Threshold
    threshold = np.percentile(mse, threshold_percentile)
    anomalies = mse > threshold
    
    return anomalies, mse, threshold


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("PyTorch LSTM AUTOENCODER ANALYSIS")
    print("=" * 60)
    
    sample_dirs = sorted(DATA_DIR.glob("sample_*"))
    seq_len = 50
    
    results = []
    
    for sample_dir in sample_dirs:
        trades_files = list(sample_dir.glob("raw_ticks/*_trades.csv"))
        if not trades_files:
            continue
        
        date = sample_dir.name.replace("sample_", "")
        print(f"\n>>> {date}")
        
        df = pd.read_csv(trades_files[0])
        
        # Use subset for speed
        df_sample = df.head(30000) if len(df) > 30000 else df
        print(f"  Using {len(df_sample):,} trades")
        
        # Prepare sequences
        sequences, n_features = prepare_sequences(df_sample, seq_len)
        
        if sequences is None or len(sequences) < 200:
            print("  Insufficient data")
            continue
        
        print(f"  {len(sequences)} sequences, {n_features} features")
        
        # Train autoencoder
        print("  Training LSTM autoencoder...")
        model, val_loss = train_autoencoder(sequences, n_features, epochs=30, seq_len=seq_len)
        print(f"  Validation loss: {val_loss:.6f}")
        
        # Detect anomalies
        anomalies, errors, threshold = detect_anomalies(model, sequences)
        
        result = {
            "date": date,
            "n_sequences": len(sequences),
            "n_anomalies": int(anomalies.sum()),
            "anomaly_rate": float(anomalies.mean()),
            "mean_error": float(errors.mean()),
            "max_error": float(errors.max()),
            "threshold": float(threshold),
            "val_loss": float(val_loss)
        }
        results.append(result)
        
        print(f"  Anomaly rate: {result['anomaly_rate']:.2%}")
        print(f"  Max error: {result['max_error']:.6f}")
    
    # Summary
    anomaly_rates = [r["anomaly_rate"] for r in results]
    
    summary = {
        "method": "PyTorch LSTM Autoencoder",
        "device": str(device),
        "days_analyzed": len(results),
        "mean_anomaly_rate": float(np.mean(anomaly_rates)),
        "max_anomaly_rate": float(max(anomaly_rates)),
        "min_anomaly_rate": float(min(anomaly_rates))
    }
    
    # Save results
    with open(OUTPUT_DIR / "lstm_pytorch_results.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
            "daily_results": results
        }, f, indent=2)
    
    # Generate report
    with open(OUTPUT_DIR / "lstm_pytorch_report.md", "w") as f:
        f.write("# PyTorch LSTM Autoencoder Analysis\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        f.write(f"**Device**: {device}\n\n")
        
        f.write("## Summary\n\n")
        f.write(f"- Days analyzed: {summary['days_analyzed']}\n")
        f.write(f"- Mean anomaly rate: {summary['mean_anomaly_rate']:.2%}\n")
        f.write(f"- Max anomaly rate: {summary['max_anomaly_rate']:.2%}\n")
        
        f.write("\n## Daily Results\n\n")
        f.write("| Date | Sequences | Anomalies | Rate | Max Error |\n")
        f.write("|------|-----------|-----------|------|----------|\n")
        for r in sorted(results, key=lambda x: x["anomaly_rate"], reverse=True):
            f.write(f"| {r['date']} | {r['n_sequences']} | {r['n_anomalies']} | {r['anomaly_rate']:.2%} | {r['max_error']:.4f} |\n")
        
        f.write("\n## Interpretation\n\n")
        if summary['mean_anomaly_rate'] > 0.10:
            f.write("> ⚠️ **Higher than expected anomaly detection rate**\n")
            f.write("> This could indicate non-random structure in trade sequences.\n")
        else:
            f.write("> ✅ Anomaly rates are within expected range (~5%)\n")
    
    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print(f"Mean anomaly rate: {summary['mean_anomaly_rate']:.2%}")
    print("=" * 60)


if __name__ == "__main__":
    main()
