import pandas as pd
import numpy as np
from pathlib import Path
import os
from bs_greeks import calculate_gamma

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
OPTIONS_DIR = BASE_DIR / "data/raw/data/options_library/GME"
OHLCV_FILE = BASE_DIR / "research/phase42_history_options/full_history_stats.csv"
OUTPUT_FILE = BASE_DIR / "research/phase74_rega/daily_metrics_rigorous.csv"

# Rigorous Parameters
FIXED_IV = 1.00  # 100% Volatility (High but standardizes the bell curve width)
RISK_FREE = 0.05

def load_ohlcv():
    print(f"Loading OHLCV from {OHLCV_FILE}...")
    df = pd.read_csv(OHLCV_FILE)
    df['date'] = pd.to_datetime(df['date'])
    return df

def process_date(date_str, spot_price, dollar_vol):
    """
    Process a single date's options snapshot.
    Returns: Fixed-IV Gamma Exposure (GEX_fixed)
    """
    day_dir = OPTIONS_DIR / date_str
    parquet_path = day_dir / "reconstructed_snapshot.parquet"
    
    if not parquet_path.exists():
        return None
        
    try:
        # Load snapshot
        # Neededcols: strike, expiry, open_interest, type
        # We assume columns found: 'strike', 'expiry', 'open_interest', 'type'
        df = pd.read_parquet(parquet_path, columns=['strike', 'expiry', 'open_interest', 'type'])
        
        # Parse Expiry
        df['expiry'] = pd.to_datetime(df['expiry'])
        current_date_dt = pd.to_datetime(date_str)
        
        # Calculate T (Years)
        df['T'] = (df['expiry'] - current_date_dt).dt.days / 365.0
        
        # Filter expired or invalid
        df = df[df['T'] > 0.001].copy()
        
        # Vectorized Gamma Calculation?
        # Trying to be fast. Our bs_greeks is scalar.
        # Let's map or vectorise.
        
        # S, sigma, r are scalars. K and T are vectors.
        # calculate_gamma uses numpy, so it should broadcast if inputs are arrays.
        
        S = spot_price
        K = df['strike'].values
        T = df['T'].values
        sigma = FIXED_IV
        r = RISK_FREE
        
        # Recalculate Gamma using FIXED IV
        # This breaks the endogeneity loop.
        # Gamma here purely reflects "Closeness to Strike" and "Time to Expiry" and "Open Interest"
        # It does NOT wiggle because today's IV changed.
        
        # Import inside to use numpy vectorization from bs_greeks logic if possible
        # My bs_greeks used np.log, so it IS vectorized. Good.
        from bs_greeks import calculate_gamma
        gammas = calculate_gamma(S, K, T, sigma, r)
        
        df['gamma_fixed'] = gammas
        
        # GEX = Gamma * OI * 100
        # Units: (1/$) * Contracts * 100 = Shares / $
        # This is Pure Gamma Exposure in terms of shares needed per dollar move.
        df['gex_fixed'] = df['gamma_fixed'] * df['open_interest'] * 100
        
        total_gamma_shares = df['gex_fixed'].sum()
        return total_gamma_shares
        
    except Exception as e:
        print(f"Error processing {date_str}: {e}")
        return None

def main():
    ohlcv = load_ohlcv()
    
    results = []
    
    available_dates = sorted([d.name for d in OPTIONS_DIR.iterdir() if d.is_dir()])
    print(f"Found {len(available_dates)} option snapshots.")
    
    for date_str in available_dates:
        try:
            date_dt = pd.to_datetime(date_str)
            market_data = ohlcv[ohlcv['date'] == date_dt]
            
            if market_data.empty:
                continue
                
            spot = market_data.iloc[0]['close']
            vol = market_data.iloc[0]['volume']
            dvol = spot * vol
            
            # Return calc
            idx = market_data.index[0]
            if idx > 0:
                prev_close = ohlcv.loc[idx-1, 'close']
                ret = (spot - prev_close) / prev_close
            else:
                ret = 0.0
            
            # Process Gamma
            # Returns Shares per Dollar
            gamma_shares = process_date(date_str, spot, dvol)
            
            if gamma_shares is None:
                gamma_shares = 0
                
            results.append({
                "date": date_str,
                "close": spot,
                "ret": ret,
                "dollar_vol": dvol,
                "gamma_shares_per_dollar": gamma_shares
            })
            
        except Exception as e:
            print(f"Skipping {date_str}: {e}")

    # Create DF
    res_df = pd.DataFrame(results)
    res_df['lambda_amihud'] = (res_df['ret'].abs() / res_df['dollar_vol']).rolling(20).mean()
    
    # R_struct
    # R = (Amihud * P^2) * Gamma_shares
    res_df['R_struct'] = res_df['lambda_amihud'] * (res_df['close']**2) * res_df['gamma_shares_per_dollar']
    
    res_df.to_csv(OUTPUT_FILE, index=False)
    print(f"Rigorous metrics saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
