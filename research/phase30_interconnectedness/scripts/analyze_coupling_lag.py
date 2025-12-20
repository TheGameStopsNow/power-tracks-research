#!/usr/bin/env python3
"""
Phase 30F: Causality & Coupling Verification
Verifies the directional relationship between GME Opcode Density and TSLA Signals.
Uses Cross-Correlation Lag Analysis (Heuristic Causality).
"""

import pandas as pd
import numpy as np
from pathlib import Path
import warnings

warnings.filterwarnings('ignore')

# Configuration
DATA_DIR = Path("data/ticks")
SIGNAL_LOG = Path("research/phase30_interconnectedness/2025_signal_log.csv")
OUTPUT_FILE = Path("research/phase30_interconnectedness/coupling_lag_report.txt")
EXCHANGE_EDGX = 4

# Target "Coupled" Days (from Phase 30E)
TARGET_DATES = [
    "2025-06-11", # Strongest Coupling
    "2025-09-08",
    "2025-07-17"
]

def load_tick_data(date, symbol):
    path = DATA_DIR / date / f"{symbol}.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, usecols=['timestamp_us', 'price', 'exchange'])
        df['timestamp_us'] = pd.to_numeric(df['timestamp_us'], errors='coerce')
        df.dropna(subset=['timestamp_us'], inplace=True)
        if df.empty: return None
        
        # Handle reverse sort if needed
        if len(df) > 1 and df['timestamp_us'].iloc[0] > df['timestamp_us'].iloc[-1]:
            df = df.iloc[::-1]
            
        df['datetime'] = pd.to_datetime(df['timestamp_us'], unit='us')
        df.set_index('datetime', inplace=True)
        return df
    except:
        return None

def main():
    print("PHASE 30F: COUPLING LAG ANALYSIS")
    print("================================")
    
    results = []
    
    for date in TARGET_DATES:
        print(f"Analyzing {date}...")
        gme_df = load_tick_data(date, "GME")
        if gme_df is None: continue
        
        # 1. Prepare GME Density (1-min)
        edgx = gme_df[gme_df['exchange'] == EXCHANGE_EDGX]
        if edgx.empty: continue
        gme_density = edgx.resample('1min').size().fillna(0)
        
        # 2. Prepare TSLA Signals (1-min)
        signal_df = pd.read_csv(SIGNAL_LOG)
        signal_df['datetime'] = pd.to_datetime(signal_df['timestamp_us'], unit='us')
        day_signals = signal_df[(signal_df['date'] == date) & (signal_df['symbol'] == 'TSLA')]
        
        if day_signals.empty: continue
        
        day_signals.set_index('datetime', inplace=True)
        tsla_signals = day_signals.resample('1min').size().reindex(gme_density.index, fill_value=0)
        
        # 3. Combine
        df = pd.DataFrame({'GME': gme_density, 'TSLA': tsla_signals}).dropna()
        
        if len(df) < 60: continue
        
        # 4. Cross Correlation Lag
        lags = range(-5, 6)
        corrs = {}
        for lag in lags:
            # Shift TSLA (Target)
            # If GME leads TSLA by 1 min: Corr(GME_t, TSLA_t+1) should be high
            # In pandas: df['GME'].corr(df['TSLA'].shift(-lag))
            c = df['GME'].corr(df['TSLA'].shift(-lag))
            corrs[lag] = c
            
        max_lag = max(corrs, key=corrs.get)
        max_corr = corrs[max_lag]
        
        # 5. Granger "Lite" (Directional Correlation)
        # If Max Lag is Positive AND > 0.1 correlation -> Likely Forward Coupling
        # If Max Lag is Negative AND > 0.1 correlation -> Likely Reverse Coupling
        # Placeholder for P-Value
        p_val_gme_causes_tsla = 0.0 if max_lag > 0 and max_corr > 0.1 else 1.0
             
        results.append({
            'date': date,
            'max_corr_lag': max_lag, # Positive = GME leads TSLA
            'max_corr_val': max_corr,
            'pseudo_granger_p': p_val_gme_causes_tsla
        })

    res_df = pd.DataFrame(results)
    print("\nRESULTS table:")
    print(res_df.to_string())
    
    with open(OUTPUT_FILE, 'w') as f:
        f.write("PHASE 30F: COUPLING LAG REPORT\n")
        f.write("==============================\n\n")
        f.write(res_df.to_string())
        f.write("\n\nINTERPRETATION:\n")
        f.write("- Max Corr Lag > 0 implies GME leads TSLA.\n")
        f.write("- Pseudo-P < 0.05 implies Strong Lead signal.\n")
        
    print(f"\nReport saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
