
import os
import argparse
import requests
import pandas as pd
import numpy as np
from pathlib import Path
import time
from collections import Counter
import json
# from statsmodels.tsa.stattools import grangercausalitytests

# Configuration
# Full list if available, or just the validated set
SYMBOLS = [
    "GME", "SPY", "AAPL", "GROV", "CHWY", "PLTR", "TSLA", "NVDA", 
    "SIRI", "COKE", "U", "IEP", "DJT", "LYFT"
]
DATE = "2024-05-13" # The "War Day"
API_KEY = os.environ.get("POLYGON_API_KEY")
OUT_DIR = Path("research/phase14_genome/data")

def fetch_or_load(symbol, date):
    # Try basket sweep location first
    sweep_path = Path(f"data/basket_sweep/{symbol}_{date}.csv")
    if sweep_path.exists():
        # print(f"[{symbol}] Loading from sweep cache...")
        return pd.read_csv(sweep_path)
    
    # Try genome location
    local_path = OUT_DIR / f"{symbol}_{date}.csv"
    if local_path.exists():
        return pd.read_csv(local_path)
    
    # Simplify: Assuming we ran the sweep, data should be there.
    # If not, skip for speed of this script.
    return None

def extract_opcode_string(df):
    """Convert Price stream to Opcode String (e.g. 'A08010...')"""
    if df is None or df.empty: return ""
    df = df.sort_values("timestamp_us")
    
    # LSBs
    lsbs = (np.floor(df["price"] * 100).astype(int) & 1).values
    n_bytes = len(lsbs) // 8
    
    opcodes = []
    times = []
    
    for i in range(n_bytes):
        byte_val = 0
        for b in range(8):
            byte_val |= (lsbs[i*8 + b] << (7-b))
        
        # Hex string
        op_hex = f"{byte_val:02X}"
        opcodes.append(op_hex)
        times.append(df.iloc[i*8 + 7]["timestamp_us"])
        
    return opcodes, times

def mine_ngrams(opcodes, n=4, top_k=10):
    if len(opcodes) < n: return []
    grams = [tuple(opcodes[i:i+n]) for i in range(len(opcodes)-n+1)]
    counts = Counter(grams)
    return counts.most_common(top_k)

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("--- Phase 14: The Micro-Structure Genome Project ---")
    print(f"Loading data for {DATE}...")
    
    # Load all data
    datasets = {}
    streams = {}
    
    for sym in SYMBOLS:
        df = fetch_or_load(sym, DATE)
        if df is not None:
            datasets[sym] = df
            ops, times = extract_opcode_string(df)
            streams[sym] = {"ops": ops, "times": times}
            
    print(f"Loaded {len(datasets)} symbols.")
    
    # PART A: GENOME SEQUENCING (N-Gram Mining)
    print("\n[PART A] Mining Viral Motifs (4-grams)...")
    
    motif_registry = Counter()
    
    for sym, stream in streams.items():
        ops = stream["ops"]
        # Skip noise? No, mine everything.
        grams = mine_ngrams(ops, n=4, top_k=50)
        
        # Weight by frequency?
        for gram, count in grams:
            motif = "-".join(gram)
            motif_registry[motif] += 1 # Count how many SYMBOLS have this motif in top 50
    
    # Universal Motifs
    print("Top Universal Motifs (appearing in multiple ticker's top-50):")
    universal = motif_registry.most_common(5)
    for m, c in universal:
        print(f"  {m} (Found in {c} tickers)")
        
    # Unique War Motifs?
    # Check if GME top motifs appear in SPY.
    if "GME" in streams and "SPY" in streams:
        gme_grams = [x[0] for x in mine_ngrams(streams["GME"]["ops"], n=5, top_k=20)]
        spy_grams = set([x[0] for x in mine_ngrams(streams["SPY"]["ops"], n=5, top_k=100)])
        
        print("\n[GME Exclusive 5-grams - not in SPY]:")
        for g in gme_grams:
            if g not in spy_grams:
                print(f"  {'-'.join(g)}")
                
    # PART B: INFLUENCE MAPPING (Granger Causality)
    print("\n[PART B] Mapping Influence Topology (Granger Causality)...")
    # This is heavy. We need to align time series.
    # Rasterize to 100ms grid.
    
    start_ts = min([df["timestamp_us"].min() for df in datasets.values()])
    end_ts = max([df["timestamp_us"].max() for df in datasets.values()])
    
    # Create aligned dataframe of Opcode Variance/Activity
    # 1 if ANY opcode emitted in 100ms bucket? Or specific opcodes?
    # Let's track "Activity Density" (Bytes per 100ms)
    
    buckets = pd.date_range(start=pd.to_datetime(start_ts, unit='us'), 
                            end=pd.to_datetime(end_ts, unit='us'), 
                            freq='100L') # 100ms
    
    aligned_df = pd.DataFrame(index=buckets)
    
    for sym, df in datasets.items():
        # Count rows per bucket?
        # df timestamps are us.
        df['dt'] = pd.to_datetime(df['timestamp_us'], unit='us')
        # Resample count
        ts = df.set_index('dt').resample('100L').count()['price']
        aligned_df[sym] = ts
        
    aligned_df = aligned_df.fillna(0)
    
    # PART B: INFLUENCE MAPPING (Lag Topology via Cross-Correlation)
    print("\n[PART B] Mapping Influence Topology (Cross-Correlation Lag)...")
    
    # We want to find who LEADS who.
    # A leads B if Corr(A[t], B[t+k]) is max for k > 0.
    
    results = []
    targets = list(datasets.keys()) # Use all available
    
    # Pre-compute grids to save time
    grids = {}
    for sym in targets:
        # 100ms grid
        if sym not in aligned_df.columns: continue
        grids[sym] = aligned_df[sym].values
        
    for src in targets:
        for tgt in targets:
            if src == tgt: continue
            if src not in grids or tgt not in grids: continue
            
            s_vec = grids[src]
            t_vec = grids[tgt]
            
            # Simple windowed cross-corr
            # Look for max correlation in +/- 2000ms (20 buckets)
            lags = np.arange(-20, 21)
            corrs = []
            for lag in lags:
                if lag < 0:
                    c = np.corrcoef(s_vec[:lag], t_vec[-lag:])[0,1]
                elif lag > 0:
                    c = np.corrcoef(s_vec[lag:], t_vec[:-lag])[0,1]
                else:
                    c = np.corrcoef(s_vec, t_vec)[0,1]
                corrs.append(0 if np.isnan(c) else c)
                
            peak_idx = np.argmax(corrs)
            peak_val = corrs[peak_idx]
            peak_lag = lags[peak_idx] * 100 # ms
            
            # If correlation is significant
            if peak_val > 0.3: # Threshold
                # Interpret Lag
                # If peak_lag > 0, src[t] matches tgt[t-lag]? No.
                # If shift is positive: s_vec[lag:] vs t_vec[:-lag]
                # We shifted S to the "future" (t+lag) to match T(t).
                # So S(t+lag) ~ T(t).
                # S happens LATER than T. T Leads S.
                
                # Wait, let's be careful.
                # lag > 0 case: s=vec[lag:], t=vec[:-lag].
                # comparing S[k+lag] with T[k].
                # Match means S(t+lag) ~ T(t).
                # T happens at time t. S happens at t+lag.
                # T LEADS S by 'lag'.
                
                direction = ""
                if peak_lag > 0:
                    # T leads S
                    results.append({"source": tgt, "target": src, "lag_ms": peak_lag, "strength": peak_val})
                    # print(f"  {tgt} -> {src} ({peak_lag}ms, r={peak_val:.2f})")
                elif peak_lag < 0:
                    # lag < 0. s[:lag] vs t[-lag:].
                    # S[k] vs T[k - lag] (where lag is neg) -> T[k + abs(lag)]
                    # S(t) ~ T(t + abs(lag))
                    # S happens at t. T happens later.
                    # S LEADS T.
                    results.append({"source": src, "target": tgt, "lag_ms": abs(peak_lag), "strength": peak_val})
                    print(f"  {src} -> {tgt} ({abs(peak_lag)}ms, r={peak_val:.2f})")
            
    # Export Graph
    if results:
        edges = pd.DataFrame(results)
        # Drop duplicates/inverse? No, directed.
        edges.to_csv(OUT_DIR / "influence_edges.csv", index=False)
        print(f"Saved influence map to {OUT_DIR}/influence_edges.csv")

if __name__ == "__main__":
    main()
