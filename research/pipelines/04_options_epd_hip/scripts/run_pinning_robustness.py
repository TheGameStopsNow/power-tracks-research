
#!/usr/bin/env python3
"""
Study 3.1: Gamma Magnet Pinning Robustness.
Compares pinning strength across the panel for May 13, 2024.

Method:
1. Load flow/price data for GME, AMC, BB, TLRY, CHWY, TSLA.
2. Identify "Gamma Magnets" (Strikes with high GEX).
   - We approximate GEX from volume/OI if GEX not available?
   - The flow files contain `strike_price` and `size`.
   - We'll assume high volume strikes are magnets.
3. Compute "Pinning Score":
   - 1 - (Mean Distance to Nearest Strike / Strike Interval)
   - Higher Score = Stronger Pinning.
"""

import pandas as pd
import numpy as np
import glob
import os
from pathlib import Path

def get_pinning_score(symbol, date="2024-05-13"):
    # 1. Load Flow to find Magnets
    base_dir = Path(__file__).resolve().parent.parent
    flow_path = base_dir / "data" / "flow" / f"{symbol}_{date}_flow.parquet"
    bars_path = base_dir / "data" / "minute_bars" / f"{symbol}_{date}_minute.csv"
    
    if not flow_path.exists() or not bars_path.exists():
        return None
        
    # Load Bars
    bars = pd.read_csv(bars_path)
    close_prices = bars["close"].values
    
    # Load Flow
    flow = pd.read_parquet(flow_path)
    # Identify top strikes by volume
    top_strikes = flow.groupby("strike_price")["size"].sum().sort_values(ascending=False).head(3).index.tolist()
    
    if not top_strikes:
        return None
        
    # 2. Compute Distance to Nearest Magnet
    distances = []
    for p in close_prices:
        d = min([abs(p - k) for k in top_strikes])
        distances.append(d)
        
    mean_dist = np.mean(distances)
    avg_price = np.mean(close_prices)
    
    # Normalize by price (percentage distance)
    # Lower distance = Better Pinning
    # Score = 1 / (Mean % Distance * 100)
    # e.g. 1% distance -> Score 1.0. 0.1% distance -> Score 10.0.
    
    pct_dist = mean_dist / avg_price
    score = 1.0 / (pct_dist * 100) if pct_dist > 0 else 100.0
    
    return {
        "symbol": symbol,
        "magnets": top_strikes,
        "mean_dist_pct": pct_dist,
        "pinning_score": score
    }

def main():
    symbols = ["GME", "AMC", "BB", "TLRY", "CHWY", "TSLA"]
    results = []
    
    for sym in symbols:
        res = get_pinning_score(sym)
        if res:
            results.append(res)
            
    df = pd.DataFrame(results)
    df = df.sort_values("pinning_score", ascending=False)
    
    print("\n=== Study 3.1 Results: Pinning Robustness ===")
    print(df)
    
    base_dir = Path(__file__).resolve().parent.parent
    out_dir = base_dir / "output"
    out_dir.mkdir(exist_ok=True)
    out_md = out_dir / "pinning_robustness.md"
    
    with open(out_md, "w") as f:
        f.write("# Study 3.1: Gamma Magnet Pinning Robustness\n\n")
        f.write("**Date**: 2024-05-13\n\n")
        f.write("## Pinning Scores\n")
        f.write("| Symbol | Magnets | Mean Dist % | Pinning Score |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        for _, row in df.iterrows():
            f.write(f"| {row['symbol']} | {row['magnets']} | {row['mean_dist_pct']:.2%} | {row['pinning_score']:.2f} |\n")
            
    print(f"Saved Report to {out_md}")

if __name__ == "__main__":
    main()
