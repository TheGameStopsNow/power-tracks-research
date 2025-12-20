import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
import matplotlib.pyplot as plt
import os
import json
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
INPUT_FILE = BASE_DIR / "research/phase74_rega/daily_metrics.csv"
OUTPUT_DIR = BASE_DIR / "research/phase74_rega/results"

def fit_model(X, y):
    if len(np.unique(y)) < 2:
        return 0, 0 # No variance
    
    model = LogisticRegression(C=1e9, solver='lbfgs')
    model.fit(X, y)
    
    # Return Slope (Coefficient of R)
    slope = model.coef_[0][0]
    return slope

def run_time_shuffle(df, n_iter=1000):
    print(f"--- Running Time Shuffle ({n_iter} iterations) ---")
    
    X = df[['dominance_ratio']].values
    y = df['is_pinned'].values
    
    real_slope = fit_model(X, y)
    
    null_slopes = []
    for _ in range(n_iter):
        y_shuffled = np.random.permutation(y)
        slope = fit_model(X, y_shuffled)
        null_slopes.append(slope)
        
    null_slopes = np.array(null_slopes)
    
    # Calculate p-value (two-tailed)
    # Fraction of nulls more extreme than real
    more_extreme = np.sum(np.abs(null_slopes) >= np.abs(real_slope))
    p_val = more_extreme / n_iter
    
    print(f"Real Slope: {real_slope:.4f}")
    print(f"Null Slope Mean: {np.mean(null_slopes):.4f}")
    print(f"p-value: {p_val:.4f}")
    
    # Plot
    plt.figure(figsize=(10, 6))
    plt.hist(null_slopes, bins=30, alpha=0.7, color='gray', label='Null Distribution')
    plt.axvline(real_slope, color='red', linestyle='--', linewidth=2, label=f'Real Slope ({real_slope:.2f})')
    plt.title("Time Shuffle Placebo Test")
    plt.xlabel("Logistic Regression Slope")
    plt.legend()
    plt.savefig(OUTPUT_DIR / "placebo_time_shuffle.png")
    
    return real_slope, p_val

def run_strike_placebo(df):
    """
    Since we don't have the full chain here, we simulate 'Strike Placebo'
    by defining Fake Outcomes Y_fake derived from random price levels.
    Or, ideally, we would go back to calculate_metrics and compute 'is_pinned' for random strikes.
    
    As a proxy: We assume 'Random Strike Pinning' is uncorrelated with R.
    We can simulate this by generating random Y vectors with similar mean probability to real Y.
    Actually, that is equivalent to Time Shuffle.
    
    To do a TRUE Strike Placebo, we need to check if R predicts pinning to NON-MAX strikes.
    That requires reloading the options data.
    
    For now, we'll stick to Time Shuffle as the primary robustness check.
    We can add a 'Random Target' test:
    Outcome = (Close close to Close.shift(5)?) No.
    """
    return

def main():
    if not OUTPUT_DIR.exists():
        os.makedirs(OUTPUT_DIR)
        
    df = pd.read_csv(INPUT_FILE)
    df = df.dropna()
    
    # 1. Time Shuffle Test
    real_slope, p_val = run_time_shuffle(df)
    
    results = {
        "test_type": "time_shuffle",
        "n_iter": 1000,
        "real_slope": float(real_slope),
        "p_value": float(p_val),
        "significant": bool(p_val < 0.05)
    }
    
    with open(OUTPUT_DIR / "placebo_results.json", "w") as f:
        json.dump(results, f, indent=2)
        
if __name__ == "__main__":
    main()
