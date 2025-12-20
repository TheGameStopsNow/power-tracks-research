import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import glob
import os

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
TICKS_DIR = BASE_DIR / "data/ticks"
# We need the Options Flow data. In Phase 74, we fetched Open Interest and IV.
# For Flow, we need minute-level or tick-level "Net Delta Flow".
# Since we don't have a direct "Net Delta Flow" file yet, we will construct a proxy
# using the 1-minute aggregations we can derive or use the 'barrier' events as high-res flow points.
import numba

@numba.jit(nopython=True)
def compute_hy_cov_numba(t1, val1, t2, val2):
    """
    Compute Hayashi-Yoshida Covariance using Numba for speed.
    t1, t2: sorted timestamps (float or int)
    val1, val2: values (prices or cumulative flow)
    
    The estimator sums product of increments (d1 * d2) if intervals overlap.
    """
    n1 = len(t1)
    n2 = len(t2)
    
    cov_sum = 0.0
    
    # Pointers
    j_start = 1
    
    # Iterate through series 1 intervals (i-1 to i)
    for i in range(1, n1):
        # Interval 1: (start1, end1]
        start1 = t1[i-1]
        end1 = t1[i]
        d1 = val1[i] - val1[i-1]
        
        # Determine relevant range in series 2
        # We need intervals (s_{j-1}, s_j] that overlap with (start1, end1]
        # Overlap condition: s_{j-1} < end1 AND s_j > start1
        
        # Advance j_start to the first potential overlap
        # We need s_j > start1. Minimal j is where s_j > start1.
        while j_start < n2 and t2[j_start] <= start1:
            j_start += 1
            
        # Iterate from j_start
        k = j_start
        while k < n2:
            # Interval 2: (start2, end2]
            start2 = t2[k-1]
            end2 = t2[k]
            
            # Stop if interval 2 starts after interval 1 ends
            if start2 >= end1:
                break
                
            # If we are here, we have overlap
            d2 = val2[k] - val2[k-1]
            cov_sum += d1 * d2
            
            k += 1
            
    return cov_sum

def load_data():
    """
    Load Price Ticks and Flow Events.
    """
    print("Loading data...")
    # 1. Flow Events (Proxy for Options Flow)
    # Using the 'expanded_barrier_events.csv' which has timestamps and Net Vol
    events_path = BASE_DIR / "research/phase74_rega/results/expanded_barrier_events.csv"
    if not events_path.exists():
        print("Events file not found.")
        return None, None
        
    df_flow = pd.read_csv(events_path)
    df_flow['timestamp'] = pd.to_datetime(df_flow['timestamp'], format='mixed', utc=True)
    # Convert to numeric seconds for HY
    t0 = df_flow['timestamp'].min()
    df_flow['time_sec'] = (df_flow['timestamp'] - t0).dt.total_seconds()
    # Cumulative Flow for HY (since we use increments)
    df_flow['cum_flow'] = df_flow['net_vol_3s'].cumsum()
    
    # 2. Price Ticks (GME)
    # We need high-res ticks matching the flow dates.
    # Let's pick the "Event" period (May 2024) for the Case Study
    ticks_files = sorted(glob.glob(str(TICKS_DIR / "2024-05-1[3-7]/GME.csv")))
    
    all_ticks = []
    for f in ticks_files:
        temp = pd.read_csv(f)
        # Handle timestamp cols - always convert to UTC
        if 'timestamp_us' in temp.columns:
            temp['timestamp'] = pd.to_datetime(temp['timestamp_us'], unit='us', utc=True)
        else:
            temp['timestamp'] = pd.to_datetime(temp['timestamp'], format='mixed', utc=True)
            
        all_ticks.append(temp[['timestamp', 'price']])
        
    if not all_ticks:
        print("No tick data found for May 2024.")
        return None, None
        
    df_price = pd.concat(all_ticks, ignore_index=True)
    # Use numpy argsort to bypass pandas sorting bug
    order = np.argsort(df_price['timestamp'].values)
    df_price = df_price.iloc[order].reset_index(drop=True)
    df_price['time_sec'] = (df_price['timestamp'] - t0).dt.total_seconds()
    
    return df_flow, df_price

def main():
    df_flow, df_price = load_data()
    if df_flow is None:
        return

    print(f"Loaded {len(df_flow)} flow events and {len(df_price)} price ticks.")
    
    # HY Lead-Lag Analysis
    # We want to verify: Does Flow(t) lead Price(t+lag)?
    # We compute Corr(Flow_t, Price_{t+lag})
    # Since HY is covariance, we can just shift the timestamps of one series.
    
    lags_sec = np.linspace(-10, 10, 21) # -10s to +10s
    correlations = []
    
    # Pre-compute arrays for Numba
    t_flow = df_flow['time_sec'].values
    v_flow = df_flow['cum_flow'].values
    t_price = df_price['time_sec'].values
    v_price = df_price['price'].values
    
    # Variances for normalization (Realized Variance)
    # RV = HY(X, X)
    var_flow = compute_hy_cov_numba(t_flow, v_flow, t_flow, v_flow)
    var_price = compute_hy_cov_numba(t_price, v_price, t_price, v_price)
    denom = np.sqrt(var_flow * var_price)
    
    print("\nRunning Lead-Lag Analysis (HY Estimator)...")
    for lag in lags_sec:
        # Shift Flow Time by Lag: Flow(t) vs Price(t) -> if Lag > 0, we shift Flow forward? 
        # Usually: Lead-Lag Corr(X, Y_lag) means Y is shifted.
        # If Flow Leads Price, then Corr(Flow_t, Price_{t+L}) should be high for L > 0.
        # Effectively, we compare Flow at t with Price at t+L.
        # In HY, to compute Cov(X_t, Y_{t+L}), we assume Y's timestamps are s_j - L.
        
        # Test: Does Flow(t) predict Price(t+lag)?
        # Means we match Flow(t) with Price(t+lag).
        # Equivalently, shift Price BACK by lag to align with Flow? 
        # Or shift Flow FORWARD?
        # Let's shift Price timestamps: t_price_shifted = t_price - lag
        # Then we are matching Flow(t) with Price(t_shifted). 
        # If lag=+1s, t_price becomes t-1. We pair Flow(t) with Price(t+1). CORRECT.
        
        t_price_shifted = t_price - lag
        
        # Sort is required for HY?
        # Shifting doesn't change order.
        
        cov = compute_hy_cov_numba(t_flow, v_flow, t_price_shifted, v_price)
        corr = cov / denom
        correlations.append(corr)
        print(f"Lag {lag:+.1f}s: Rho = {corr:.4f}")
        
    # Plot
    plt.figure(figsize=(10, 6))
    plt.plot(lags_sec, correlations, marker='o')
    plt.axvline(0, color='k', linestyle='--')
    plt.title("Hayashi-Yoshida Lead-Lag: Options Flow vs GME Price")
    plt.xlabel("Lag (Seconds) [Positive = Flow Leads Price]")
    plt.ylabel("HY Correlation")
    plt.grid(True)
    plt.savefig(BASE_DIR / "research/phase75_predictability/output/hy_lead_lag.png")
    print("Saved plot to research/phase75_predictability/output/hy_lead_lag.png")


if __name__ == "__main__":
    main()
