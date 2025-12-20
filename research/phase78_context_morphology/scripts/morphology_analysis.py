"""
Phase 78: Echo Morphology Analysis

This module performs:
1. Extraction of 60-day forward price paths for each burst.
2. Path Normalization (percent change from burst time).
3. Clustering (K-Means) to identify "Shape Archetypes".
4. Visualization of archetypes.
5. Classification: Which Greek fingerprint predicts which Shape?
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import confusion_matrix
import glob

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GREEK_DIR = BASE_DIR / "research/phase77_greek_echo/results"
OI_DIR = BASE_DIR / "research/phase78_context_morphology/data/open_interest"
RESULTS_DIR = BASE_DIR / "research/phase78_context_morphology/output"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

def load_data():
    bursts = pd.read_csv(GREEK_DIR / "bursts_deep_explored.csv")
    bursts['timestamp'] = pd.to_datetime(bursts['timestamp'], format='mixed', utc=True)
    
    # Load bars
    bar_files = sorted(glob.glob(str(BARS_DIR / "GME_*_minute.csv")))
    all_bars = []
    for f in bar_files:
        temp = pd.read_csv(f)
        temp['timestamp'] = pd.to_datetime(temp['timestamp'], utc=True)
        all_bars.append(temp[['timestamp', 'close']])
    
    bars_df = pd.concat(all_bars, ignore_index=True)
    order = np.argsort(bars_df['timestamp'].values)
    bars_df = bars_df.iloc[order].reset_index(drop=True)
    
    return bursts, bars_df

def extract_paths(bursts, bars_df, horizon_days=60):
    """
    Extract normalized price paths for each burst.
    Resample to daily resolution for cleaner clustering.
    """
    paths = []
    metadata = []
    
    # Approx bars per day
    bars_per_day = 390
    max_len = horizon_days * bars_per_day
    
    # Ensure bar_times is np.datetime64
    bar_times = bars_df['timestamp'].values.astype('datetime64[ns]')
    
    for idx, burst in bursts.iterrows():
        start_time = burst['timestamp'].to_datetime64()
        start_idx = np.searchsorted(bar_times, start_time)
        
        if start_idx >= len(bars_df):
            continue
            
        # We want roughly 60 daily points
        # Get the slice
        end_idx = min(start_idx + max_len, len(bars_df))
        slice_df = bars_df.iloc[start_idx:end_idx].copy()
        
        if len(slice_df) < (horizon_days * 10): # Require some data
            continue
            
        # Resample to daily close (approx)
        # Simple method: take every 390th bar
        # Better: resample by time
        slice_df.set_index('timestamp', inplace=True)
        daily = slice_df['close'].resample('1D').last().dropna()
        
        # Limit to horizon days
        if len(daily) > horizon_days:
            daily = daily.iloc[:horizon_days]
        if len(daily) < horizon_days:
            # Pad or skip? Skip for now
            continue
            
        # Normalize: Percent change from T0
        # T0 price is burst price
        base_price = burst['underlying_price']
        normalized = (daily.values - base_price) / base_price * 100
        
        paths.append(normalized)
        metadata.append(burst)
        
    return np.array(paths), pd.DataFrame(metadata)

def cluster_shapes(paths, n_clusters=4):
    """Cluster paths into archetypes."""
    print(f"\nClustering {len(paths)} paths into {n_clusters} archetypes...")
    
    # Use simple Euclidean K-Means on the path vectors
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=20)
    labels = kmeans.fit_predict(paths)
    
    centers = kmeans.cluster_centers_
    
    return labels, centers

def analyze_fingerprint_correlation(bursts, labels):
    """Correlate Greek fingerprints with Shape Cluster."""
    bursts['cluster'] = labels
    
    # Compute derived features if missing
    if 'is_morning' not in bursts.columns:
        if 'hour' in bursts.columns:
             bursts['is_morning'] = (bursts['hour'] < 12).astype(int)
        else:
             bursts['hour'] = bursts['timestamp'].dt.hour
             bursts['is_morning'] = (bursts['hour'] < 12).astype(int)
    
    features = ['gamma_flow', 'delta_flow', 'charm_flow', 'pc_ratio', 'iv', 'pct_0dte', 'is_morning']
    
    print("\nFeature means by Shape Archetype:")
    means = bursts.groupby('cluster')[features].mean()
    print(means.to_string())
    
    # Find distinctive features
    for c in sorted(bursts['cluster'].unique()):
        print(f"\nArchetype {c} distinctive features:")
        cluster_mean = means.loc[c]
        global_mean = bursts[features].mean()
        std = bursts[features].std()
        
        z_scores = (cluster_mean - global_mean) / std
        distinctive = z_scores.abs().sort_values(ascending=False).head(3)
        
        for feat, score in distinctive.items():
            direction = "High" if z_scores[feat] > 0 else "Low"
            print(f"  {direction} {feat} (z={score:.2f})")

def plot_archetypes(paths, labels, centers):
    """Visualize the derived archetypes."""
    n_clusters = len(centers)
    fig, axes = plt.subplots(1, n_clusters, figsize=(n_clusters*4, 4), sharey=True)
    
    if n_clusters == 1: axes = [axes]
    
    for i in range(n_clusters):
        # Plot all paths in this cluster (faint)
        cluster_paths = paths[labels == i]
        for p in cluster_paths:
            axes[i].plot(p, color='gray', alpha=0.1)
            
        # Plot centroid (bold)
        axes[i].plot(centers[i], color='red', linewidth=3)
        axes[i].axhline(0, color='k', linestyle='--')
        axes[i].set_title(f"Archetype {i} (n={len(cluster_paths)})")
        axes[i].set_xlabel("Days Since Burst")
        
    axes[0].set_ylabel("Return (%)")
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "morphology_archetypes.png", dpi=150)
    print(f"\nSaved archetype plot: {OUTPUT_DIR / 'morphology_archetypes.png'}")

def main():
    print("Phase 78: Echo Morphology Analysis")
    print("="*60)
    
    # Load
    bursts, bars = load_data()
    print(f"Loaded {len(bursts)} bursts")
    
    # Extract
    paths, meta_bursts = extract_paths(bursts, bars)
    print(f"Extracted {len(paths)} valid 60-day paths")
    
    if len(paths) < 10:
        print("Not enough paths for clustering.")
        return
        
    # Cluster
    labels, centers = cluster_shapes(paths, n_clusters=3)
    
    # Characterize
    print("\n" + "="*60)
    print("ARCHETYPE CHARACTERIZATION")
    print("="*60)
    
    # Determine what each cluster represents (Bull/Bear/Chop)
    for i, center in enumerate(centers):
        final_ret = center[-1]
        max_ret = np.max(center)
        min_ret = np.min(center)
        
        desc = "Choppy"
        if final_ret > 10: desc = "Bullish Trend"
        elif final_ret < -10: desc = "Bearish Trend"
        elif max_ret > 20 and final_ret < 5: desc = "Pump & Dump"
        elif min_ret < -20 and final_ret > -5: desc = "V-Shape Reversal"
        
        print(f"Archetype {i}: {desc} (Final: {final_ret:.1f}%)")
        
    plot_archetypes(paths, labels, centers)
    
    # Link to Greeks
    analyze_fingerprint_correlation(meta_bursts, labels)
    
    # Save tagged data
    meta_bursts['shape_archetype'] = labels
    meta_bursts.to_csv(OUTPUT_DIR / "bursts_with_morphology.csv", index=False)

if __name__ == "__main__":
    main()
