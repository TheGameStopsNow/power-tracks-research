
import pandas as pd
import numpy as np
import json
import argparse
from pathlib import Path
from scipy.spatial.distance import cdist

# Opcode Mapping (Must match Engine/Research)
OP_MAPPING = {
    0xA0: "FLOOR",
    0x98: "CEILING",
    0x80: "PIVOT",
    0x10: "STATION",
    0x01: "LIFT",
    0x02: "START"
}

def load_centroids(path):
    with open(path, 'r') as f:
        data = json.load(f)
    
    # We need a predictable order of features for the vector
    # Collect all unique keys from all centroids
    all_keys = set()
    for c in data:
        all_keys.update(c['centroid'].keys())
    
    feature_columns = sorted(list(all_keys))
    
    # Build matrix
    matrix = []
    names = []
    ids = []
    
    for c in data:
        vec = [c['centroid'].get(k, 0.0) for k in feature_columns]
        matrix.append(vec)
        names.append(c['name'])
        ids.append(c['id'])
        
    return np.array(matrix), names, ids, feature_columns

def process_file(csv_path, centroids, centroid_names, feature_cols):
    print(f"Processing {csv_path.name}...")
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Error reading {csv_path}: {e}")
        return None
        
    # 1. Extract LSBs (Chunked 8-bit)
    # Logic: int(price * 100) & 1
    # Optimization: Vectorized
    # Note: Ensure sorted by time
    df.sort_values('timestamp_us', inplace=True)
    
    lsbs = (np.floor(df['price'] * 100).astype(int) & 1).values
    
    # Truncate to multiple of 8
    n_bytes = len(lsbs) // 8
    if n_bytes == 0:
        return None
        
    lsbs = lsbs[:n_bytes*8]
    
    # Reshape to (N, 8) and pack bits
    # bit 0 is first tick... bit 7 is last tick? 
    # TS implementation: 
    # bitBuffer.push(lsb). 
    # for b in buffer: val = (val << 1) | b
    # So first tick is MSB.
    
    matrix = lsbs.reshape(n_bytes, 8)
    
    # Pack bits: MSB first
    opcodes = np.zeros(n_bytes, dtype=int)
    for i in range(8):
        opcodes |= (matrix[:, i] << (7 - i))
        
    # Map Opcodes to Names
    # We only care about the mapped ones
    # Create DataFrame of Events
    # Timestamp? We can take the timestamp of the 8th tick
    timestamps = df['timestamp_us'].values[:n_bytes*8:8] # Approximate? Or 7::8
    timestamps = df['timestamp_us'].values[7::8][:n_bytes] # Use timestamp of completion
    
    events = pd.DataFrame({
        'timestamp_us': timestamps,
        'opcode': opcodes
    })
    
    events['op_name'] = events['opcode'].map(OP_MAPPING)
    events['symbol'] = df['symbol'].iloc[0] if 'symbol' in df.columns else csv_path.stem.split('_')[0]
    
    # 2. Vectorize (1-Second Windows)
    events['sec_bucket'] = events['timestamp_us'] // 1000000
    events['action'] = events['symbol'] + "_" + events['op_name'] # Note: centroid keys likely include symbol "GME_" etc.
    # WAIT. The centroids were trained on GME/AMC/NOK data. The keys are "GME_LIFT", "AMC_PIVOT".
    # If I process "AAPL", the key will be "AAPL_LIFT".
    # This will NOT match the centroid features (which expect GME_LIFT).
    # 
    # CRITICAL: How does BasketStrategyAnalyzer handle this?
    # Engine logic: 
    # onEvent(symbol, opName) -> buffer.push({symbol, opName})
    # classifyState() -> 
    #   counts = { "GME_LIFT": 0, "AMC_PIVOT": 0 ... }
    #   dist = distance(counts, centroid)
    #
    # So the Centroids are SPECIFIC to the tickers in the basket (GME, AMC, NOK).
    # If I run SPY, it will produce "SPY_LIFT".
    # "SPY_LIFT" is not in the centroid feature list. It will be ignored (or zero distance contribution).
    # 
    # Implication: The CURRENT Centroids verify GME/AMC coordination.
    # They CANNOT classify "SPY Behavior" unless SPY mimics GME_LIFT (impossible, symbol mismatch).
    #
    # However, Phase 12 objective is: "Basket Classification: Run ... on new feed."
    # AND "Comparative Analysis: Report on Meme vs Mega Cap structural differences".
    #
    # Approach:
    # We want to see if SPY has "Pump Clusters" or "Suppression Clusters".
    # Using the GME centroids directly won't work due to symbol keys.
    #
    # ALTERNATIVE: abstract the features?
    # Or, for this sweep, we want to see if they share *structural* motifs.
    # But the clusters were defined by *inter-symbol* features (e.g. GME+AMC Sync).
    #
    # REVISED PLAN for Scanner:
    # 1. Calculate "Single Symbol" metrics.
    #    % of Opcodes that are STORM (A0/98) vs PEACE (80/10).
    #    This "Regime Density" is a universal metric.
    # 2. Check for "Chatter".
    #    Do they emit the Rosetta Opcodes at all?
    #    (Yes, if LSB is random, they will emit them 1/256 of the time by chance).
    #    We check if the *frequency* deviates from random (uniform 0.39%).
    #
    # This addresses "Comparative Analysis".
    # "Basket Classification" implies checking if they fit the "Meme Basket". i.e. Does SPY move with GME?
    # To test that, we'd need to run SPY *alongside* GME through the classifier.
    # But we want to see if SPY *itself* has a "War Regime".
    #
    # Let's pivot the script to output "Opcode Density stats".
    # Count of A0, 98, 80, 10, 01, 02 per Minute.
    # Compare vs Uniform Distribution.
    
    # Filter valid opcodes
    valid_events = events[events['op_name'].notna()]
    
    total_ops = len(events)
    if total_ops == 0: return None
    
    # Counts
    counts = valid_events['op_name'].value_counts()
    
    # Normalize by total *bytes* (not just valid ones, to see sparsity)
    stats = {
        'symbol': events['symbol'].iloc[0],
        'total_bytes': total_ops,
        'valid_ratio': len(valid_events) / total_ops
    }
    
    for name in OP_MAPPING.values():
        stats[name] = counts.get(name, 0)
        stats[f"{name}_pct"] = counts.get(name, 0) / total_ops
        
    return stats

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv-dir", default="data/basket_sweep")
    parser.add_argument("--centroids", default="services/daemon/src/data/basket_centroids.json") # Unused if doing generic stats
    args = parser.parse_args()
    
    csv_dir = Path(args.csv_dir)
    results = []
    
    print("Scanning for Opcode Density (War vs Peace)...")
    
    for f in csv_dir.glob("*.csv"):
        if "master" in f.name: continue
        res = process_file(f, None, None, None)
        if res:
            results.append(res)
            
    if not results:
        print("No results.")
        return
        
    df = pd.DataFrame(results)
    
    # Output
    print(df)
    df.to_csv(csv_dir / "basket_sweep_density.csv", index=False)
    print(f"Saved stats to {csv_dir}/basket_sweep_density.csv")

if __name__ == "__main__":
    main()
