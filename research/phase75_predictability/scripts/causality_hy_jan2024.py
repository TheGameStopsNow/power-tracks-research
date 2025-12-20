"""
Hayashi-Yoshida Lead-Lag Analysis - January 2024 Control Period

Low volatility comparison test.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import glob
import numba

BASE_DIR = Path(__file__).resolve().parent.parent.parent
OPRA_DIR = BASE_DIR / "data/opra_ticks"
TICKS_DIR = BASE_DIR / "data/ticks"
RESULTS_DIR = BASE_DIR / "research/phase75_predictability/results"

@numba.jit(nopython=True)
def compute_hy_cov_numba(t1, val1, t2, val2):
    n1 = len(t1)
    n2 = len(t2)
    cov_sum = 0.0
    j_start = 1
    for i in range(1, n1):
        start1 = t1[i-1]
        end1 = t1[i]
        d1 = val1[i] - val1[i-1]
        while j_start < n2 and t2[j_start] <= start1:
            j_start += 1
        k = j_start
        while k < n2:
            start2 = t2[k-1]
            if start2 >= end1:
                break
            d2 = val2[k] - val2[k-1]
            cov_sum += d1 * d2
            k += 1
    return cov_sum

def compute_delta(strike, price, right):
    moneyness = price / strike
    if right.lower() == 'call':
        delta = max(0.0, min(1.0, 0.5 + 0.5 * (moneyness - 1.0) * 5))
    else:
        delta = max(-1.0, min(0.0, -0.5 - 0.5 * (1.0 - moneyness) * 5))
    return delta

def load_opra_data_jan():
    """Load Jan 2024 OPRA trades."""
    print("Loading Jan 2024 OPRA options trades...")
    files = sorted(glob.glob(str(OPRA_DIR / "gme_option_trades_202401*.csv")))
    all_dfs = []
    for f in files:
        df = pd.read_csv(f)
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed', utc=True)
        all_dfs.append(df)
        print(f"  Loaded {Path(f).name}: {len(df)} trades")
    df_all = pd.concat(all_dfs, ignore_index=True)
    
    # Underlying ~ $16 for Jan 2024
    underlying_price = 16.0
    df_all['delta'] = df_all.apply(
        lambda row: compute_delta(row['strike'], underlying_price, row['right']), axis=1
    )
    df_all['delta_flow'] = df_all['size'] * df_all['delta'] * 100
    
    order = np.argsort(df_all['timestamp'].values)
    df_all = df_all.iloc[order].reset_index(drop=True)
    
    df_all['ts_sec'] = df_all['timestamp'].dt.floor('1s')
    flow_1s = df_all.groupby('ts_sec').agg({'delta_flow': 'sum'}).reset_index()
    flow_1s = flow_1s.rename(columns={'ts_sec': 'timestamp'})
    flow_1s['cum_flow'] = flow_1s['delta_flow'].cumsum()
    
    print(f"\nTotal Options Trades: {len(df_all)}")
    print(f"1-Second Aggregated Points: {len(flow_1s)}")
    return flow_1s

def load_price_data_jan():
    """Load Jan 2024 GME price ticks."""
    print("\nLoading Jan 2024 GME price ticks...")
    files = sorted(glob.glob(str(TICKS_DIR / "2024-01-*/GME.csv")))
    all_dfs = []
    for f in files:
        df = pd.read_csv(f)
        # Handle different timestamp formats
        if 'timestamp_us' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp_us'], unit='us', utc=True)
        elif 'sip_timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['sip_timestamp'], unit='ns', utc=True)
        else:
            df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed', utc=True)
        all_dfs.append(df[['timestamp', 'price']])
        print(f"  Loaded {f}: {len(df)} ticks")
    df_all = pd.concat(all_dfs, ignore_index=True)
    order = np.argsort(df_all['timestamp'].values)
    df_all = df_all.iloc[order].reset_index(drop=True)
    
    df_all['ts_sec'] = df_all['timestamp'].dt.floor('1s')
    price_1s = df_all.groupby('ts_sec').agg({'price': 'last'}).reset_index()
    price_1s = price_1s.rename(columns={'ts_sec': 'timestamp'})
    
    print(f"\nTotal Price Ticks: {len(df_all)}")
    print(f"1-Second Aggregated Points: {len(price_1s)}")
    return price_1s

def run_lead_lag_analysis(flow_df, price_df, label="Jan 2024"):
    print(f"\nRunning HY Lead-Lag Analysis ({label})...")
    t0 = min(flow_df['timestamp'].min(), price_df['timestamp'].min())
    flow_df['time_sec'] = (flow_df['timestamp'] - t0).dt.total_seconds()
    price_df['time_sec'] = (price_df['timestamp'] - t0).dt.total_seconds()
    
    t_flow = flow_df['time_sec'].values.astype(np.float64)
    v_flow = flow_df['cum_flow'].values.astype(np.float64)
    t_price = price_df['time_sec'].values.astype(np.float64)
    v_price = price_df['price'].values.astype(np.float64)
    
    var_flow = compute_hy_cov_numba(t_flow, v_flow, t_flow, v_flow)
    var_price = compute_hy_cov_numba(t_price, v_price, t_price, v_price)
    denom = np.sqrt(var_flow * var_price)
    
    lags_sec = np.linspace(-60, 60, 61)
    correlations = []
    
    print("Lag (sec) | HY Correlation")
    print("-" * 30)
    for lag in lags_sec:
        t_price_shifted = t_price - lag
        cov = compute_hy_cov_numba(t_flow, v_flow, t_price_shifted, v_price)
        corr = cov / denom if denom > 0 else 0
        correlations.append(corr)
        if lag % 10 == 0:
            print(f"{lag:+6.0f}s   | {corr:.4f}")
    
    peak_idx = np.argmax(correlations)
    peak_lag = lags_sec[peak_idx]
    peak_corr = correlations[peak_idx]
    
    print("-" * 30)
    print(f"PEAK: Lag = {peak_lag:+.0f}s, Correlation = {peak_corr:.4f}")
    if peak_lag > 0:
        print("\n*** OPTIONS FLOW LEADS PRICE ***")
    elif peak_lag < 0:
        print("\n*** PRICE LEADS OPTIONS FLOW ***")
    else:
        print("\n*** CONTEMPORANEOUS ***")
    
    plt.figure(figsize=(12, 6))
    plt.plot(lags_sec, correlations, marker='.', linewidth=1)
    plt.axvline(0, color='k', linestyle='--', alpha=0.5)
    plt.axvline(peak_lag, color='r', linestyle='--', label=f'Peak @ {peak_lag:+.0f}s')
    plt.title(f"Hayashi-Yoshida Lead-Lag: Options Flow vs GME Price\n({label} - Low Volatility Control)")
    plt.xlabel("Lag (Seconds) [Positive = Flow Leads Price]")
    plt.ylabel("HY Correlation")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.savefig(RESULTS_DIR / "hy_lead_lag_jan2024.png", dpi=150)
    print(f"\nSaved: {RESULTS_DIR / 'hy_lead_lag_jan2024.png'}")
    
    return peak_lag, peak_corr

def main():
    flow_df = load_opra_data_jan()
    price_df = load_price_data_jan()
    peak_lag, peak_corr = run_lead_lag_analysis(flow_df, price_df, "Jan 2024")
    
    print("\n" + "="*50)
    print("FINAL RESULT - LOW VOLATILITY CONTROL")
    print("="*50)
    print(f"Peak Lag: {peak_lag:+.0f} seconds")
    print(f"Peak Correlation: {peak_corr:.4f}")

if __name__ == "__main__":
    main()
