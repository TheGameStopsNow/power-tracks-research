
import pandas as pd
import numpy as np
from pathlib import Path
import random

# Configuration
SIGNAL_LOG = Path("research/phase30_interconnectedness/signal_log.csv")
IMPACT_STATS = Path("research/phase30_interconnectedness/impact_stats.md") # Read existing impact for observed
OUTPUT_REPORT = Path("research/phase30_interconnectedness/significance_report.md")

N_PERMUTATIONS = 10000

def load_signals():
    if not SIGNAL_LOG.exists():
        return None
    return pd.read_csv(SIGNAL_LOG)

def calculate_cv(df):
    """Calculates Coefficient of Variation of signal counts across tickers."""
    counts = df['symbol'].value_counts()
    if len(counts) < 2:
        return 0
    return counts.std() / counts.mean()

def permutation_test_clustering(df):
    """
    Test if signals are clustered in specific tickers (High CV) 
    vs randomly distributed (Low CV).
    """
    print(f"Running Permutation Test (N={N_PERMUTATIONS}) for Clustering...")
    
    observed_cv = calculate_cv(df)
    
    # We want to shuffle the "Symbol" column relative to the "Events"
    # Effectively, we preserve the total number of events and total number of active tickers?
    # Actually, specific tickers might just be more active.
    # A rigorous test might be: shuffle the 'symbol' assignments across all available symbols?
    # Or simpler: Is the concentration in Top X tickers significant?
    
    # We will shuffle the 'symbol' column of the dataframe.
    # This assumes the distribution of *events* is fixed, but who they belong to is random.
    
    simulated_stats = []
    symbols = df['symbol'].values.copy() # Array of symbols involved
    
    for _ in range(N_PERMUTATIONS):
        np.random.shuffle(symbols)
        # Create temp series to count
        # In a shuffled world, finding 400 'GME's is unlikely if GME is just one label among 30.
        # Wait, if we shuffle the column, the counts are exactly the same.
        # shuffling the column inplace doesn't change relative counts.
        
        # CORRECT LOGIC:
        # We need to assign each event to a random ticker from the UNIVERSE of tickers.
        # Assuming equal probability of being 'infected' under H0.
        # Universe = valid tickers in the study.
        pass

    # Actually, simpler H0: "Signals are uniformly distributed across all tickers."
    # Universe of tickers:
    unique_tickers = df['symbol'].unique() # Or better, the TARGETS list.
    # Let's assume the unique tickers in the log is the universe for now, 
    # or provided known universe. 
    # If we only verified signals in GME/BB/etc, we only see them.
    # We need the full list of tickers we SCANNED.
    
    # Let's assume uniform probability 1/N_tickers for each event.
    n_events = len(df)
    n_tickers = len(unique_tickers)
    
    simulated_cvs = []
    for _ in range(N_PERMUTATIONS):
        # Randomly assign n_events to n_tickers
        sim_counts = np.random.multinomial(n_events, [1/n_tickers]*n_tickers)
        cv = np.std(sim_counts) / np.mean(sim_counts)
        simulated_cvs.append(cv)
        
    simulated_cvs = np.array(simulated_cvs)
    p_value = (simulated_cvs >= observed_cv).mean()
    
    return observed_cv, p_value, np.percentile(simulated_cvs, 99)

def main():
    df = load_signals()
    if df is None or df.empty:
        print("No signals to test.")
        return

    # 1. Clustering Significance
    obs_cv, p_cluster, crit_cv = permutation_test_clustering(df)
    
    print(f"\n--- Clustering Test ---")
    print(f"Observed CV: {obs_cv:.4f}")
    print(f"Critical CV (99%): {crit_cv:.4f}")
    
    if p_cluster == 0:
        p_display = f"< {1/N_PERMUTATIONS:.4f}"
    else:
        p_display = f"{p_cluster:.6f}"
        
    print(f"p-value: {p_display}")
    
    verdict = "SIGNIFICANT" if p_cluster < 0.01 else "NOT SIGNIFICANT"
    print(f"Result: {verdict}")
    
    # 2. Causality Significance (Bootstrap)
    print(f"\n--- Causality Bootstrap Test ---")
    RAW_RETURNS = Path("research/phase30_interconnectedness/impact_raw_returns.csv")
    
    causality_result = None
    
    if RAW_RETURNS.exists():
        returns_df = pd.read_csv(RAW_RETURNS)
        # Filter for Cross-Impact GME->KOSS 10s as the key test case
        
        subset = returns_df[
            (returns_df['type'] == 'CROSS') & 
            (returns_df['trigger'] == 'GME') & 
            (returns_df['target'] == 'KOSS') & 
            (returns_df['window_sec'] == 10)
        ]
        
        if not subset.empty:
            signal_rets = subset[subset['is_signal'] == True]['return'].values
            baseline_rets = subset[subset['is_signal'] == False]['return'].values
            
            # Filter out NaN values
            signal_rets = signal_rets[~np.isnan(signal_rets)]
            baseline_rets = baseline_rets[~np.isnan(baseline_rets)]
            
            if len(signal_rets) > 0 and len(baseline_rets) > 0:
                obs_alpha = np.mean(signal_rets) - np.mean(baseline_rets)
                n_events = len(signal_rets)
                
                # Bootstrap
                random_means = np.random.choice(baseline_rets, size=(N_PERMUTATIONS, n_events), replace=True).mean(axis=1)
                
                p_val_low = (random_means <= np.mean(signal_rets)).mean()
                p_val_high = (random_means >= np.mean(signal_rets)).mean()
                p_val = min(p_val_low, p_val_high) * 2
                
                print(f"Test: GME -> KOSS (10s)")
                print(f"Valid Signal Events: {len(signal_rets)}")
                print(f"Valid Baseline Events: {len(baseline_rets)}")
                print(f"Observed Return: {np.mean(signal_rets):.6f}")
                print(f"Baseline Mean: {np.mean(baseline_rets):.6f}")
                print(f"Observed Alpha: {obs_alpha:.6f}")
                print(f"Bootstrap p-value: {p_val:.6f}")
                
                sig_label = "SIGNIFICANT" if p_val < 0.01 else "NOT SIGNIFICANT"
                print(f"Result: {sig_label}")
                
                causality_result = {
                    'alpha': obs_alpha,
                    'p_val': p_val,
                    'label': sig_label,
                    'n_signal': len(signal_rets),
                    'n_baseline': len(baseline_rets)
                }
            else:
                print("Insufficient valid (non-NaN) data for GME->KOSS test.")
                causality_result = None
        else:
            print("No GME->KOSS cross-impact data found.")
            causality_result = None
    else:
        print("Raw returns file not found. Run measure_impact.py first.")
        causality_result = None

    # Write report
    with open(OUTPUT_REPORT, "w") as f:
        f.write("# Statistical Significance Report\n\n")
        f.write("## 1. Signal Clustering (Permutation Test)\n")
        f.write(f"- **H0:** Signals are uniformly distributed across tickers.\n")
        f.write(f"- **Observed CV:** {obs_cv:.4f}\n")
        f.write(f"- **Simulated CV (99th):** {crit_cv:.4f}\n")
        f.write(f"- **p-value:** {p_display}\n")
        f.write(f"- **Verdict:** {verdict} clustering.\n\n")

        f.write("## 2. Causality Significance (Bootstrap)\n")
        if causality_result:
            f.write(f"- **Test:** GME -> KOSS (10s Return)\n")
            f.write(f"- **Sample Size:** {causality_result['n_signal']} signal events, {causality_result['n_baseline']} baseline\n")
            f.write(f"- **Observed Alpha:** {causality_result['alpha']:.6f}\n")
            f.write(f"- **p-value:** {causality_result['p_val']:.6f}\n")
            f.write(f"- **Verdict:** {causality_result['label']}\n")
        else:
            f.write("- **Status:** Insufficient data for GME->KOSS cross-impact test.\n")
            f.write("- **Note:** This test requires valid return data for both signal and baseline events.\n")


if __name__ == "__main__":
    main()
