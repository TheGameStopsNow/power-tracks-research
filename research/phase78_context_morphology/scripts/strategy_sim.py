"""
Phase 78: Prism Strategy Simulation

Strategies:
1. **Prism Long**: Buy if Model Predicts > 20% return.
2. **0DTE Contrarian**: Buy if Burst has > 50% 0DTE.
3. **Smart Combo**: Buy if High 0DTE AND High IV.

Benchmark: Buy & Hold GME during the same valid periods.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GREEK_DIR = BASE_DIR / "research/phase77_greek_echo/results"
OUTPUT_DIR = BASE_DIR / "research/phase78_context_morphology/results"

def run_simulation():
    print("Phase 78: Prism Strategy Simulation")
    print("="*60)
    
    # Load bursts with forward returns
    df = pd.read_csv(GREEK_DIR / "bursts_deep_explored.csv")
    
    # Filter to those with 60d outcomes
    valid = df.dropna(subset=['ret_60d']).copy()
    print(f"Valid trade opportunities: {len(valid)}")
    
    if len(valid) == 0:
        print("No valid data.")
        return
        
    # --- STRATEGY 1: 0DTE Dominance (Simpler Model) ---
    # Buy if 0DTE > 50% (Recall: High 0DTE -> Bullish 60d)
    valid['signal_0dte'] = valid['pct_0dte'] > 0.5
    
    # --- STRATEGY 2: High IV Reversion ---
    # Buy if IV > Median
    median_iv = valid['iv'].median()
    valid['signal_iv'] = valid['iv'] > median_iv
    
    # --- STRATEGY 3: Prism Model Score ---
    # Approximation of the regression model coefficients
    # Score = 7*0dte + 1.7*iv - 10*delta_flow(std) ...
    # Simplified: Score = 0DTE_score + IV_score - Morning_penalty
    
    # Normalize simply for scoring
    valid['z_0dte'] = (valid['pct_0dte'] - valid['pct_0dte'].mean()) / valid['pct_0dte'].std()
    valid['z_iv'] = (valid['iv'] - valid['iv'].mean()) / valid['iv'].std()
    valid['z_morning'] = valid['hour'].apply(lambda x: 1 if x < 12 else 0)
    
    # Model coefficients weights (rough)
    # 0DTE (+7), IV (+1.7), Morning (-2.5) => Let's use 3:1:-1 weights
    valid['prism_score'] = 3 * valid['z_0dte'] + 1 * valid['z_iv'] - 1.5 * valid['z_morning']
    
    # Buy top 20% scores
    threshold = valid['prism_score'].quantile(0.80)
    valid['signal_prism'] = valid['prism_score'] > threshold
    
    # --- PERFORMANCE ---
    strategies = {
        'Benchmark (Buy Every Burst)': [True] * len(valid),
        '0DTE Contrarian': valid['signal_0dte'],
        'High IV Reversion': valid['signal_iv'],
        'Prism Model (Top 20%)': valid['signal_prism']
    }
    
    summary = []
    
    for name, signal in strategies.items():
        sub = valid[signal]
        n_trades = len(sub)
        
        if n_trades == 0:
            avg_ret = 0
            win_rate = 0
        else:
            avg_ret = sub['ret_60d'].mean()
            win_rate = (sub['ret_60d'] > 0).mean() * 100
        
        summary.append({
            'Strategy': name,
            'Trades': n_trades,
            'Avg Return': avg_ret,
            'Win Rate': win_rate
        })
        
    summary_df = pd.DataFrame(summary)
    print("\nSimulation Results (60-Day Hold):")
    print(summary_df.to_string(index=False, float_format="%.2f"))
    
    # Save
    summary_df.to_csv(OUTPUT_DIR / "strategy_results.csv", index=False)
    
    # Plot equity curves (cumulative sum of percentage returns - simplified)
    plt.figure(figsize=(10, 6))
    
    for name, signal in strategies.items():
        # Sort by time
        sorted_sig = valid[signal].sort_values('timestamp')
        if len(sorted_sig) > 0:
            equity = sorted_sig['ret_60d'].cumsum()
            plt.plot(range(len(equity)), equity, label=f"{name} (Avg: {sorted_sig['ret_60d'].mean():.1f}%)")
            
    plt.title("Cumulative Returns by Strategy (Non-Compounded)")
    plt.xlabel("Trade Number")
    plt.ylabel("Cumulative % Return")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.savefig(OUTPUT_DIR / "strategy_performance.png")
    print(f"\nSaved plot: {OUTPUT_DIR / 'strategy_performance.png'}")

if __name__ == "__main__":
    run_simulation()
