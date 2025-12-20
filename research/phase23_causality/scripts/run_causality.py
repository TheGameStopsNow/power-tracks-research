
import pandas as pd
import numpy as np
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# Setup
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

PHASE_22_DATA = BASE_DIR.parent / "phase22_synchronicity/data/synchronicity_matrix.csv"

def compute_lagged_correlation(s1, s2, max_lag=5):
    """
    Returns (max_corr, best_lag)
    If best_lag > 0, s1 leads s2.
    If best_lag < 0, s2 leads s1.
    """
    best_corr = 0
    best_lag = 0
    
    # We test lags: s1(t) vs s2(t+lag)
    # If correlation is highest at lag=+1, then s1(t) predicts s2(t+1) => S1 LEADS.
    
    for lag in range(1, max_lag + 1):
        # Case A: S1 leads S2 (Shift S2 backwards to match S1's past?)
        # Corr(S1[0:-lag], S2[lag:])
        c = s1.corr(s2.shift(-lag))
        if abs(c) > abs(best_corr):
            best_corr = c
            best_lag = lag
            
        # Case B: S2 leads S1
        # Corr(S1[lag:], S2[0:-lag])
        c = s1.corr(s2.shift(lag))
        if abs(c) > abs(best_corr):
            best_corr = c
            best_lag = -lag # Negative lag means S2 predictive
            
    return best_corr, best_lag

def main():
    print("--- Phase 23: Lead-Lag Analysis (Manual Correlation) ---")
    
    if not PHASE_22_DATA.exists():
        print("Error: Phase 22 data not found.")
        return
        
    df = pd.read_csv(PHASE_22_DATA, index_col=0)
    df.index = pd.to_datetime(df.index)
    
    symbols = df.columns
    results = [] # {Source, Target, Lag, Correlation, Direction}
    
    MAX_LAG = 5 
    
    print(f"Testing {len(symbols)} symbols pairwise (Max Lag: {MAX_LAG})...")
    
    for i, source in enumerate(symbols):
        for j, target in enumerate(symbols):
            if i >= j: continue # Only do unique pairs once, logic handles direction
            
            s1 = df[source]
            s2 = df[target]
            
            corr, lag = compute_lagged_correlation(s1, s2, MAX_LAG)
            
            # Threshold for significance?
            if abs(corr) > 0.05: # Low threshold for binary/sparse data
                direction = "SYNC"
                if lag > 0: direction = f"{source}->{target}"
                elif lag < 0: direction = f"{target}->{source}"
                
                results.append({
                    "Pair": f"{source}-{target}",
                    "Max_Corr": corr,
                    "Best_Lag (Min)": abs(lag),
                    "Direction": direction
                })
                
    # Save Results
    if results:
        res_df = pd.DataFrame(results).sort_values("Max_Corr", ascending=False)
        res_df.to_csv(DATA_DIR / "lead_lag_results.csv", index=False)
        print(f"\nFound {len(res_df)} significant links.")
        print("Top 10 Links:")
        print(res_df.head(10))
    else:
        print("No significant lead-lag relationships found (or no input data).")
        return

if __name__ == "__main__":
    main()
