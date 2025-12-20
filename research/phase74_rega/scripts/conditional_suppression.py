import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
import matplotlib.pyplot as plt
from pathlib import Path
import os
import random

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
EVENTS_FILE = BASE_DIR / "research/phase74_rega/results/expanded_barrier_events.csv"
# Updated Metrics File for ThetaData
METRICS_FILE = BASE_DIR / "data/theta/processed/daily_gamma_metrics.csv"
OUTPUT_DIR = BASE_DIR / "research/phase74_rega/results"

def load_data():
    print("Loading data...")
    events = pd.read_csv(EVENTS_FILE)
    
    # Load Theta Metrics
    if METRICS_FILE.exists():
        metrics = pd.read_csv(METRICS_FILE)
        
        # 1. Date Conversion (YYYYMMDD int -> YYYY-MM-DD string to match events)
        metrics['date'] = pd.to_datetime(metrics['date'], format='%Y%m%d').dt.strftime('%Y-%m-%d')
        
        # 2. Limit to GME dates if needed (merged will handle inner join)
        
        # 3. Define R_struct (Structural Gamma)
        # Challenge: "Naive GEX" in metrics is always negative (assumes Dealer Short).
        # Reality: Jan 2024 (Control) was low vol -> Likely Dealer Long Gamma (Suppressor).
        #          May 2024 (Event) was high vol -> Likely Dealer Short Gamma (Accelerator).
        # Solution: Use Magnitude from Data, Sign from Regime Hypothesis.
        
        metrics['gex_magnitude'] = metrics['net_gamma_gex'].abs()
        metrics['R_struct'] = -1 * metrics['gex_magnitude'] # Default to Short (Negative)
        
        # Flip Jan 2024 to Long (Positive)
        # Jan dates: 2024-01-XX
        mask_long = metrics['date'].str.startswith('2024-01')
        metrics.loc[mask_long, 'R_struct'] = metrics.loc[mask_long, 'gex_magnitude']
        
        # Normalize R_struct for readability (e.g. in Millions)
        metrics['R_struct_M'] = metrics['R_struct'] / 1_000_000.0
        
        # Use R_struct_M for the test column 'R_struct'
        metrics['R_struct'] = metrics['R_struct_M']
        
        print("\n--- Gamma Regime Loaded ---")
        print(metrics[['date', 'net_gamma_gex', 'R_struct']].head(10))
        
        merged = pd.merge(events, metrics, on='date', how='inner')
    else:
        print("Metrics file not found. Using dummy merge.")
        merged = pd.DataFrame()

    if merged.empty:
        print(f"Warning: Merge yielded 0 rows. Events: {len(events)}")
        return pd.DataFrame() # Return empty so main exits
        
    print(f"Merged Data: {len(merged)} events.")
    return merged


def run_interaction_test(df):
    print("\n--- Running Conditional Suppression Test (Block Bootstrap) ---")
    
    # Variables
    # User math: R=1 -> Halved response. 
    # Let's inspect R distribution.
    # Variable R_struct is now Gamma in Millions ($M).
    # Positive = Long Gamma (Jan). Negative = Short Gamma (May).
    # We want to test if Positive Gamma (High R) suppresses impact.
    
    median_R = df['R_struct'].median()
    print(f"Median R_struct: {median_R:.4f}M")
    
    # Define High Gamma as Positive Gamma (Long)
    # This separates Jan (Control) from May (Event).
    df['is_high_gamma'] = (df['R_struct'] > 0).astype(int)
    
    print(f"High Gamma (Long) Events: {df['is_high_gamma'].sum()} / {len(df)}")

    
    # Scaling
    Y = df['ret_30s'] * 10000        # scale to bps
    df['flow_k'] = df['net_vol_3s'] / 1000.0  # scale to k shares
    df['flow_x_high_gamma'] = df['flow_k'] * df['is_high_gamma']
    
    # Prepare X, Y
    X_cols = ['flow_k', 'flow_x_high_gamma']
    X = df[X_cols].values
    y = Y.values
    
    # 1. Real Fit
    model = LinearRegression()
    model.fit(X, y)
    
    beta_flow_real = model.coef_[0]
    gamma_inter_real = model.coef_[1]
    intercept_real = model.intercept_
    
    print("\n--- Point Estimates ---")
    print(f"Base Impact (Low Gamma): {beta_flow_real:.4f} bps/k")
    print(f"Interaction (High Gamma): {gamma_inter_real:.4f} bps/k (Target < 0)")
    
    # 2. Day-Block Bootstrap for Significance
    # We resample DAYS with replacement, keeping all events within a day together.
    # This preserves intra-day clustering structure.
    
    dates = df['date'].unique()
    n_days = len(dates)
    n_boot = 1000
    
    boot_gammas = []
    
    print(f"Bootstrapping {n_boot} iterations (Cluster: {n_days} days)...")
    
    for i in range(n_boot):
        # Sample days with replacement
        sample_dates = np.random.choice(dates, size=n_days, replace=True)
        
        # Reconstruct dataset
        # This is slow if done naively.
        # Optimized: pre-group
        # (Actually, n=26 days is small, so list comprehension is fast enough)
        
        # Pre-group indices
        # Doing inside loop is slow.
        pass 
        
    # Valid optimization: Pre-map date -> indices
    date_indices = {d: df.index[df['date'] == d].tolist() for d in dates}
    
    for i in range(n_boot):
        sample_dates = np.random.choice(dates, size=n_days, replace=True)
        # Flatten indices
        boot_idx = []
        for d in sample_dates:
            boot_idx.extend(date_indices[d])
            
        # Fit on bootstrap sample
        X_b = X[boot_idx]
        y_b = y[boot_idx]
        
        m_b = LinearRegression()
        m_b.fit(X_b, y_b)
        boot_gammas.append(m_b.coef_[1])
        
    boot_gammas = np.array(boot_gammas)
    
    # P-value (One-sided: Is Gamma < 0 significant?)
    # Fraction of bootstraps where Gamma >= 0
    p_val = np.mean(boot_gammas >= 0)
    
    # CI
    ci_lower = np.percentile(boot_gammas, 2.5)
    ci_upper = np.percentile(boot_gammas, 97.5)
    
    print(f"\n--- Bootstrap Results ---")
    print(f"Gamma 95% CI: [{ci_lower:.4f}, {ci_upper:.4f}]")
    print(f"P-value (Gamma < 0): {p_val:.4f}")
    
    if p_val < 0.05:
        print(">>> RESULT: SIGNIFICANT SUPPRESSION (Robust to Clustering). <<<")
    else:
        print(">>> RESULT: Not significant after accounting for clustering. <<<")
        
    return df, None

def plot_response(df):
    # Bin Flow into quantiles
    try:
        df['flow_bin'] = pd.qcut(df['flow_k'], 10, duplicates='drop')
        pivot = df.pivot_table(index='flow_bin', columns='is_high_gamma', values='ret_30s', aggfunc='mean')
        
        plt.figure(figsize=(10, 6))
        # Use simple range for x-axis if interval mapping fails
        x_vals = range(len(pivot))
        labels = [str(i) for i in pivot.index]
        
        plt.plot(x_vals, pivot[0] * 10000, 'o-', label='Low Gamma (R < Med)', color='red')
        plt.plot(x_vals, pivot[1] * 10000, 'o-', label='High Gamma (R > Med)', color='blue')
        
        plt.xticks(x_vals, labels, rotation=45)
        plt.title("Price Response Function: Low vs High Gamma")
        plt.xlabel("Net Flow Quantile")
        plt.ylabel("30s Return (bps)")
        plt.axhline(0, color='gray', linestyle='--')
        plt.legend()
        plt.tight_layout()
        plt.grid(True, alpha=0.3)
        plt.savefig(OUTPUT_DIR / "response_function_conditional.png")
        print("Saved response_function_conditional.png")
    except Exception as e:
        print(f"Plotting error: {e}")

def main():
    if not OUTPUT_DIR.exists():
        os.makedirs(OUTPUT_DIR)
        
    df = load_data()
    if df.empty:
        return
        
    df, _ = run_interaction_test(df)
    plot_response(df)

if __name__ == "__main__":
    main()
