#!/usr/bin/env python
"""
Assigns clusters to unclustered tracks based on shape similarity (TISA distance)
to the centroids of existing clusters.

1. Loads existing clusters from reports/track_clusters.json.
2. Computes the "average shape" (centroid) for each cluster (0, 1, 2, 3).
3. Finds tracks in data/power_tracks/GME that are NOT in track_clusters.json.
4. Computes TISA distance from each new track to each cluster centroid.
5. Assigns the track to the closest cluster.
6. Updates reports/track_clusters.json with the new assignments.
"""

import json
import os
import sys
import numpy as np
from pathlib import Path

# Import TISA
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../TISA")))
try:
    from tisa.distance import TISADistance
except ImportError:
    # Fallback if TISA is not found at ../../TISA
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../TISA")))
    try:
        from tisa.distance import TISADistance
    except ImportError:
        print("Error: Could not import TISADistance. Make sure TISA repo is at ../TISA")
        sys.exit(1)

def load_price_path(track_dir):
    path = os.path.join(track_dir, "price_path.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        series = json.load(f)
    if not isinstance(series, list) or not series:
        return None
    # Sort by timestamp and return prices only
    series_sorted = sorted(series, key=lambda x: x.get("ts", 0))
    return [float(pt["price"]) for pt in series_sorted if "price" in pt]

def resample_series(values, length):
    if not values:
        return None
    arr = np.asarray(values, dtype=float)
    if len(arr) == length:
        return arr
    if len(arr) < 2:
        return None
    # uniform resample in index-space
    idx = np.linspace(0, len(arr) - 1, num=length)
    return np.interp(idx, np.arange(len(arr)), arr)

def zscore(x):
    x = np.asarray(x, dtype=float)
    mu = x.mean()
    sigma = x.std() or 1.0
    return (x - mu) / sigma

def main():
    root = Path("data/power_tracks")
    clusters_path = Path("reports/track_clusters.json")
    
    if not clusters_path.exists():
        print(f"Error: {clusters_path} not found.")
        return

    with open(clusters_path, "r") as f:
        clusters_data = json.load(f)

    # Group tracks by cluster
    cluster_tracks = {}
    existing_ids = set()
    for item in clusters_data:
        cid = item.get("cluster")
        tid = item.get("trackId")
        sym = item.get("symbol")
        existing_ids.add(tid)
        
        if cid is not None and sym == "GME":
            if cid not in cluster_tracks:
                cluster_tracks[cid] = []
            cluster_tracks[cid].append(item)

    print(f"Found {len(existing_ids)} existing clustered tracks.")
    for cid, tracks in cluster_tracks.items():
        print(f"  Cluster {cid}: {len(tracks)} tracks")

    # Sample reference tracks for each cluster
    MAX_REF = 25
    references = []
    import random
    random.seed(42)
    
    print("\nSampling reference tracks...")
    LENGTH = 64 # Define LENGTH here as it's used for resampling
    for cid, tracks in cluster_tracks.items():
        sample = tracks if len(tracks) <= MAX_REF else random.sample(tracks, MAX_REF)
        for t in sample:
            track_dir = root / t["symbol"] / t["trackId"]
            prices = load_price_path(track_dir)
            if prices:
                resampled = resample_series(prices, LENGTH)
                if resampled is not None:
                    references.append({
                        "cluster": cid,
                        "shape_z": zscore(resampled),
                        "trackId": t["trackId"]
                    })
        print(f"  Cluster {cid}: {len(sample)} references selected.")

    # Find new tracks
    print("\nFinding new tracks...")
    gme_dir = root / "GME"
    new_tracks = []
    if gme_dir.exists():
        for track_dir in gme_dir.iterdir():
            if track_dir.is_dir():
                tid = track_dir.name
                if tid not in existing_ids:
                    # Check if it has price_path
                    if (track_dir / "price_path.json").exists():
                        # Load summary for date/time
                        summary_path = track_dir / "summary.json"
                        if summary_path.exists():
                            with open(summary_path, "r") as f:
                                summary = json.load(f)
                            
                            # Handle different summary formats
                            det_time = summary.get("detection_time") or summary.get("detectionTime")
                            date_str = summary.get("date")
                            
                            if det_time and date_str:
                                new_tracks.append({
                                    "symbol": "GME",
                                    "trackId": tid,
                                    "detectionTime": det_time,
                                    "date": date_str,
                                    "path": track_dir
                                })

    print(f"Found {len(new_tracks)} new unclustered tracks.")

    # Assign clusters
    tisa = TISADistance()
    assignments = []
    
    print("\nAssigning clusters (1-NN)...")
    for i, t in enumerate(new_tracks):
        if i % 10 == 0:
            print(f"  Processing {i}/{len(new_tracks)}...")
            
        prices = load_price_path(t["path"])
        if not prices:
            continue
        
        shape = resample_series(prices, LENGTH)
        if shape is None:
            continue
        
        shape_z = zscore(shape)
        
        best_cid = -1
        min_dist = float("inf")
        best_ref_id = None
        
        for ref in references:
            try:
                # Use pairwise with 1D arrays, hoping it works or returns a matrix
                d_mat = tisa.pairwise(shape_z, ref["shape_z"])
                if isinstance(d_mat, (float, int)):
                    d = d_mat
                else:
                    d = d_mat[0][0]
                if d < min_dist:
                    min_dist = d
                    best_cid = ref["cluster"]
                    best_ref_id = ref["trackId"]
            except Exception:
                continue
        
        assignments.append({
            "symbol": t["symbol"],
            "trackId": t["trackId"],
            "cluster": best_cid,
            "detectionTime": t["detectionTime"],
            "date": t["date"],
            "distanceToCentroid": float(min_dist)
        })
        # print(f"  Assigned {t['trackId']} to Cluster {best_cid} (dist={min_dist:.4f})")

    print(f"\nAssigned {len(assignments)} new tracks to clusters.")

    # Append to track_clusters.json
    # We'll create a new file to be safe: reports/track_clusters_extended.json
    # Or just overwrite if confident. Let's overwrite but keep a backup?
    # No, let's write to extended first.
    
    extended_data = clusters_data + assignments
    out_path = Path("reports/track_clusters_extended.json")
    with open(out_path, "w") as f:
        json.dump(extended_data, f, indent=2)
        
    print(f"Wrote extended clusters to {out_path}")

    # Also update the original file so other scripts pick it up
    # with open(clusters_path, "w") as f:
    #     json.dump(extended_data, f, indent=2)
    # print(f"Updated {clusters_path}")

if __name__ == "__main__":
    main()
