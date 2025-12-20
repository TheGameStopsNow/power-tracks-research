import pandas as pd
import numpy as np
from pathlib import Path
from scipy.stats import norm
import glob
import os

# Constants
RISK_FREE_RATE = 0.053 # 5.3%
RAW_DIR = Path("data/theta/raw")
OUT_DIR = Path("data/theta/processed")

def calculate_gamma(S, K, T, sigma, r=RISK_FREE_RATE, q=0):
    """
    Calculates Gamma for an option using Black-Scholes.
    S: Underlying Price
    K: Strike Price
    T: Time to Expiration (years)
    sigma: Implied Volatility
    r: Risk-free rate
    q: Dividend yield
    """
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0

    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return gamma

def process_day(date_str):
    oi_file = RAW_DIR / f"oi_{date_str}.csv"
    iv_file = RAW_DIR / f"iv_{date_str}.csv"
    
    if not oi_file.exists() or not iv_file.exists():
        print(f"[{date_str}] Missing files.")
        return None

    try:
        df_oi = pd.read_csv(oi_file, on_bad_lines='skip')
        df_iv = pd.read_csv(iv_file, on_bad_lines='skip')
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        print(f"[{date_str}] Empty file.")
        return None
        
    if df_oi.empty or df_iv.empty:
        print(f"[{date_str}] Empty DataFrame.")
        return None

    
    
    # Merge
    # Key: expiration, strike, right
    
    # Sanitize and Cast Types (Handle garbage rows from concurrent writes)
    df_oi['strike'] = pd.to_numeric(df_oi['strike'], errors='coerce')
    df_iv['strike'] = pd.to_numeric(df_iv['strike'], errors='coerce')
    
    df_oi = df_oi.dropna(subset=['strike'])
    df_iv = df_iv.dropna(subset=['strike'])
    
    # Clean Rights (uppercase)
    df_oi['right'] = df_oi['right'].astype(str).str.upper()
    df_iv['right'] = df_iv['right'].astype(str).str.upper()

    
    merged = pd.merge(df_oi, df_iv, on=['expiration', 'strike', 'right'], suffixes=('_oi', '_iv'))
    
    # Calculate T (Time to Expiry)
    # Expiry is YYYY-MM-DD
    # Current Date is date_str (YYYYMMDD)
    current_date = pd.to_datetime(date_str, format='%Y%m%d')
    merged['expiration_dt'] = pd.to_datetime(merged['expiration'])
    
    # Days to expiry
    merged['days_to_exp'] = (merged['expiration_dt'] - current_date).dt.days
    # Filter expired? If days < 0?
    merged = merged[merged['days_to_exp'] >= 0]
    
    # Avoid T=0 division error (use 0.5 days minimum or 1/365)
    merged['T'] = merged['days_to_exp'] / 365.0
    merged.loc[merged['T'] == 0, 'T'] = 1/365.0 # Expiring today
    
    # Calculate Gamma
    # Vectorized Apply? Or Iterative? Iterative is slow. 
    # Vectorized func?
    # norm.pdf works on arrays.
    
    S = merged['underlying_price'].astype(float)
    K = merged['strike']
    T = merged['T']
    sigma = merged['implied_vol'].astype(float)
    
    # invalid sigma
    sigma = sigma.replace(0, np.nan)
    
    d1 = (np.log(S / K) + (RISK_FREE_RATE + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    
    merged['gamma'] = gamma.fillna(0)
    
    # Calculate GEX (Dollar Gamma Exposure)
    # GEX = Gamma * OI * 100 * S
    # Sign? 
    # Dealer Short Call (-), Short Put (Wait. Dealer Long Put? No generally Short Put too).
    # Buying Put -> Dealer Sells Put (Short Put). 
    # Short Put has POSITIVE Delta? No. 
    # Long Put Delta < 0. Short Put Delta > 0.
    # Short Put Gamma? 
    # Long Put Gamma > 0. Short Put Gamma < 0.
    # So Dealer Position Gamma is NEGATIVE for both Calls and Puts if they are Short.
    # Assuming Dealer takes opposite of OI.
    
    merged['oi'] = merged['open_interest'].fillna(0)
    
    # Net Gamma Contribution
    # We will just sum Magnitude for "Total Gamma"
    merged['gamma_notional'] = merged['gamma'] * merged['oi'] * 100 * S
    
    # Directional?
    # If Dealer Short Call: Gamma < 0.
    # If Dealer Short Put: Gamma < 0.
    # So Net Gamma is always Negative?
    # No. This assumes ALL OI is purchased by customers.
    # This is the "Naive GEX" assumption.
    # We will use this.
    # So Net Gamma = -1 * Sum(Gamma Notional)
    
    total_gex = -1 * merged['gamma_notional'].sum()
    
    # Split by Call/Put
    calls = merged[merged['right'] == 'CALL']
    puts = merged[merged['right'] == 'PUT']
    
    call_gex = -1 * calls['gamma_notional'].sum()
    put_gex = -1 * puts['gamma_notional'].sum() 
    # Note: Put Gamma is negative for Short Put.
    
    # Metrics
    return {
        'date': date_str,
        'net_gamma_gex': total_gex,
        'call_gex': call_gex,
        'put_gex': put_gex,
        'total_oi': merged['oi'].sum(),
        'avg_iv': sigma.mean()
    }

def main():
    if not OUT_DIR.exists():
        os.makedirs(OUT_DIR)
        
    # List IV files to determine dates available
    files = glob.glob(str(RAW_DIR / "iv_*.csv"))
    dates = [Path(f).stem.split('_')[1] for f in files]
    dates.sort()
    
    results = []
    for d in dates:
        print(f"Processing {d}...")
        res = process_day(d)
        if res:
            results.append(res)
            
    if results:
        df_res = pd.DataFrame(results)
        outfile = OUT_DIR / "daily_gamma_metrics.csv"
        df_res.to_csv(outfile, index=False)
        print(f"Saved {outfile}")
        print(df_res)
    else:
        print("No results.")

if __name__ == "__main__":
    main()
