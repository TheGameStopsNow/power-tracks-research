import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
import matplotlib.pyplot as plt
import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
INPUT_FILE = BASE_DIR / "research/phase74_rega/daily_metrics_rigorous.csv"
OUTPUT_DIR = BASE_DIR / "research/phase74_rega/results"

def fit_model(X, y):
    model = LinearRegression()
    model.fit(X, y)
    return model.coef_[0], model.intercept_, model

def main():
    if not OUTPUT_DIR.exists():
        os.makedirs(OUTPUT_DIR)
        
    df = pd.read_csv(INPUT_FILE)
    df = df.dropna()
    
    # Model: |Ret| ~ a + b * (1 / (1 + R_struct))
    # We expect b > 0 (Higher R -> Lower Vol -> Term shrinks -> No, wait)
    # R is Dominance.
    # User derivation: |dS| ~ 1 / (1 + R)
    # If R is Large -> 1/(1+R) is Small -> |dS| is Small.
    # So |dS| is proportional to 1/(1+R).
    # Plot X = 1/(1+R), Y = |Ret|.
    # We expect Positive Slope. (As X grows (R shrinks), Y grows).
    # As X shrinks (R grows), Y shrinks.
    
    # Calculate Predictor
    # Ensure R is positive (Net Long Gamma assumption from Fixed IV calc is always positive)
    df['inv_factor'] = 1 / (1 + df['R_struct'])
    df['abs_ret'] = df['ret'].abs()
    
    X = df[['inv_factor']].values
    y = df['abs_ret'].values
    
    # 1. Fit Real Data
    slope, intercept, model = fit_model(X, y)
    y_pred = model.predict(X)
    r2 = r2_score(y, y_pred)
    
    print(f"--- Rigorous Volatility Model (Fixed IV) ---")
    print(f"Model: |Ret| = {intercept:.4f} + {slope:.4f} * [1/(1 + R_struct)]")
    print(f"Slope: {slope:.4f} (Expected > 0)")
    print(f"R-squared: {r2:.4f}")
    
    # 2. Permutation Test (Circular Shift)
    # Preserves autocorrelation of X and y, breaks relationship
    print("\n--- Running Circular Shift Permutation Test (1000 iter) ---")
    n_iter = 1000
    null_slopes = []
    
    # We shift Y against X
    y_series = df['abs_ret'].values
    n = len(y_series)
    
    for i in range(n_iter):
        # Random shift (exclude 0)
        shift = np.random.randint(1, n)
        y_shuffled = np.roll(y_series, shift)
        
        # Fit
        s, _, _ = fit_model(X, y_shuffled)
        null_slopes.append(s)
        
    null_slopes = np.array(null_slopes)
    
    # p-value (One-sided: is real slope greater than nulls?)
    # or Two-sided
    # We expect Positive slope.
    p_val_pos = np.sum(null_slopes >= slope) / n_iter
    
    print(f"Null Slope Mean: {np.mean(null_slopes):.4f}")
    print(f"Real Slope: {slope:.4f}")
    print(f"p-value (slope > null): {p_val_pos:.4f}")
    
    # Plot Fit
    plt.figure(figsize=(10, 6))
    plt.scatter(df['inv_factor'], df['abs_ret'], alpha=0.6, label='Observed Data')
    
    # Line
    x_range = np.linspace(df['inv_factor'].min(), df['inv_factor'].max(), 100).reshape(-1, 1)
    y_line = model.predict(x_range)
    plt.plot(x_range, y_line, color='red', label=f'Fit (Slope={slope:.2f})')
    
    plt.title(f"Rigorous Volatility Suppression Test (Fixed IV)\np={p_val_pos:.3f} | R2={r2:.3f}")
    plt.xlabel("Suppression Factor: 1 / (1 + R_struct)")
    plt.ylabel("Daily Volatility: |Return|")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.savefig(OUTPUT_DIR / "rigorous_vol_fit.png")
    plt.close()
    
    # Plot Null Dist
    plt.figure(figsize=(10, 6))
    plt.hist(null_slopes, bins=30, color='gray', alpha=0.7, label='Null Hyp (Circular Shifts)')
    plt.axvline(slope, color='red', linestyle='--', linewidth=2, label=f'Real Slope ({slope:.2f})')
    plt.title("Statistical Significance Check")
    plt.xlabel("Regression Slope")
    plt.legend()
    plt.savefig(OUTPUT_DIR / "rigorous_permutation.png")
    plt.close()

if __name__ == "__main__":
    main()
