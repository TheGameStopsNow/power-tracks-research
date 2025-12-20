"""
Phase 79: Low Gamma Control Test

This script:
1. Loads burst data.
2. Classifies bursts into High Gamma (May 2024) vs Low Gamma (Jan-Apr 2024) regimes.
3. Runs the Prism Strategy (and others) on each subset independently.
4. Compares Alpha and Win Rate to validate the "Gamma Condition".
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from scipy import stats

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
# Input: Phase 77 Output
GREEK_DIR = BASE_DIR / "research/phase77_greek_echo/output"
# Output: Local Output
OUTPUT_DIR = BASE_DIR / "research/phase79_control/output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def load_data():
    file_path = GREEK_DIR / "burst_fingerprints_enhanced.csv" # Updated filename from phase78/77 work
    if not file_path.exists():
         # Fallback to check if the old name exists or warn
         old_path = GREEK_DIR / "bursts_deep_explored.csv"
         if old_path.exists():
             file_path = old_path
         else:
             raise FileNotFoundError(f"Could not find burst data at {file_path}")
             
    df = pd.read_csv(file_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed', utc=True)
    return df

def classify_regime(df):
    """
    Classify based on known volatility/gamma periods for GME in 2024.
    High Gamma: May 2024 (Run-up)
    Low Gamma: Jan, Feb, Mar, Apr 2024 (Quiet period)
    """
    # GME May 2024 run started around May 1-2, exploded May 13.
    # We have data for May 13-17.
    
    df['month'] = df['timestamp'].dt.month
    
    # Define regimes
    df['regime'] = df['month'].apply(lambda x: 'High Gamma (May)' if x == 5 else 'Low Gamma (Jan-Apr)')
    
    print("\nRegime Distribution:")
    print(df['regime'].value_counts())
    
    return df

def run_strategy_on_subset(df, subset_name):
    """
    Run Prism Strategy on a specific subset.
    Returns performance metrics.
    """
    if len(df) == 0:
        return {'Strategy': subset_name, 'Trades': 0, 'Alpha': 0, 'Win Rate': 0}
        
    valid = df.dropna(subset=['ret_60d']).copy()
    
    if len(valid) == 0:
        return {'Strategy': subset_name, 'Trades': 0, 'Alpha': 0, 'Win Rate': 0}
        
    # --- PRISM MODEL LOGIC (Same as Phase 78) ---
    # Normalize WITHIN the subset (important for regime-relative scoring)
    # OR use global parameters? 
    # To be rigorous, we should use the SAME absolute thresholds/parameters derived from the full model
    # to avoid overfitting the control noise.
    # But standardization features (z-scores) typically imply relative scoring.
    # Let's use GLOBAL normalization parameters from the full dataset if possible, 
    # but here we'll just re-standardize for simplicity, acknowledging it gives the 'best chance' to the control.
    
    valid['z_0dte'] = (valid['pct_0dte'] - valid['pct_0dte'].mean()) / (valid['pct_0dte'].std() + 1e-9)
    valid['z_iv'] = (valid['iv'] - valid['iv'].mean()) / (valid['iv'].std() + 1e-9)
    valid['z_morning'] = valid['hour'].apply(lambda x: 1 if x < 12 else 0)
    
    # Prism Score
    valid['prism_score'] = 3 * valid['z_0dte'] + 1 * valid['z_iv'] - 1.5 * valid['z_morning']
    
    # Signal: Top 20%
    threshold = valid['prism_score'].quantile(0.80)
    valid['signal_prism'] = valid['prism_score'] > threshold
    
    # Performance
    benchmark_ret = valid['ret_60d'].mean()
    benchmark_win = (valid['ret_60d'] > 0).mean()
    
    strategy_trades = valid[valid['signal_prism']]
    
    if len(strategy_trades) == 0:
         strat_ret = 0
         strat_win = 0
    else:
        strat_ret = strategy_trades['ret_60d'].mean()
        strat_win = (strategy_trades['ret_60d'] > 0).mean()
    
    alpha = strat_ret - benchmark_ret
    
    return {
        'Regime': subset_name,
        'N_Bursts': len(valid),
        'N_Trades': len(strategy_trades),
        'Benchmark Ret': benchmark_ret,
        'Strategy Ret': strat_ret,
        'Alpha': alpha,
        'Win Rate': strat_win * 100,
        'Benchmark Win': benchmark_win * 100
    }

def main():
    print("Phase 79: Low Gamma Control Test")
    print("=" * 60)
    
    df = load_data()
    df = classify_regime(df)
    
    results = []
    
    # 1. Total (Reference)
    res_total = run_strategy_on_subset(df, "ALL DATA")
    results.append(res_total)
    
    # 2. High Gamma (May)
    high_gamma = df[df['regime'] == 'High Gamma (May)']
    res_high = run_strategy_on_subset(high_gamma, "HIGH GAMMA (May)")
    results.append(res_high)
    
    # 3. Low Gamma (Jan-Apr)
    low_gamma = df[df['regime'] == 'Low Gamma (Jan-Apr)']
    res_low = run_strategy_on_subset(low_gamma, "LOW GAMMA (Jan-Apr)")
    results.append(res_low)
    
    # Display
    results_df = pd.DataFrame(results)
    
    cols = ['Regime', 'N_Bursts', 'N_Trades', 'Benchmark Ret', 'Strategy Ret', 'Alpha', 'Win Rate', 'Benchmark Win']
    print("\nControl Test Results:")
    print(results_df[cols].to_string(index=False, float_format="%.2f"))
    
    # Save
    results_df.to_csv(OUTPUT_DIR / "control_test_results.csv", index=False)
    
    # Plot Comparison
    plt.figure(figsize=(10, 6))
    
    x = np.arange(len(results_df))
    width = 0.35
    
    plt.bar(x - width/2, results_df['Benchmark Ret'], width, label='Benchmark (Buy All)', color='gray', alpha=0.7)
    plt.bar(x + width/2, results_df['Strategy Ret'], width, label='Prism Strategy', color='blue', alpha=0.7)
    
    plt.ylabel('Avg 60d Return (%)')
    plt.title('Prism Strategy Performance by Regime')
    plt.xticks(x, results_df['Regime'])
    plt.legend()
    plt.grid(axis='y', alpha=0.3)
    
    # Add Alpha Labels
    for i, row in results_df.iterrows():
        plt.text(i + width/2, row['Strategy Ret'] + 1, f"+{row['Alpha']:.1f}%", ha='center', color='black', fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "control_test_plot.png")
    print(f"\nSaved plot: {OUTPUT_DIR / 'control_test_plot.png'}")
    
    # Conclusion
    print("\n" + "="*60)
    print("HYPOTHESIS VERIFICATION")
    print("="*60)
    
    alpha_high = res_high['Alpha']
    alpha_low = res_low['Alpha']
    
    print(f"High Gamma Alpha: {alpha_high:.2f}%")
    print(f"Low Gamma Alpha:  {alpha_low:.2f}%")
    
    if alpha_high > 5 and alpha_low < 2: # heuristic thresholds
        print("\n✓ PASSED: Signal is robust in High Gamma but disappears in Low Gamma.")
        print("  This confirms Gamma Pressure is the causal mechanism.")
    elif alpha_low > 5:
        print("\n? AMBIGUOUS: Signal works in Low Gamma too.")
        print("  The signal might be a general market property, not just Gamma-driven.")
    else:
        print("\n✗ FAILED: Signal not strong enough in High Gamma or inconsistent.")

if __name__ == "__main__":
    main()
