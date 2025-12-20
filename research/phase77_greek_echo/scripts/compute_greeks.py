"""
Phase 77: Greek Computation for OPRA Trades

This module computes:
1. Implied Volatility (IV) via Black-Scholes inversion
2. Delta (Δ), Gamma (Γ), Charm for each options trade
3. Aggregated Greek flows per second
"""

import pandas as pd
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq
from pathlib import Path
import glob

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
OPRA_DIR = BASE_DIR / "research/phase75_predictability/data/opra_ticks"
TICKS_DIR = BASE_DIR / "data/ticks"
OUTPUT_DIR = BASE_DIR / "research/phase77_greek_echo/output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Risk-free rate (approximate)
RISK_FREE_RATE = 0.05

def black_scholes_price(S, K, T, r, sigma, option_type='call'):
    """Calculate Black-Scholes option price."""
    if T <= 0 or sigma <= 0:
        return 0.0
    
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    if option_type == 'call':
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    
    return price

def implied_volatility(price, S, K, T, r, option_type='call'):
    """Compute implied volatility via Black-Scholes inversion."""
    if price <= 0 or T <= 0:
        return np.nan
    
    # Bounds for IV search
    low_vol = 0.01
    high_vol = 5.0
    
    def objective(sigma):
        return black_scholes_price(S, K, T, r, sigma, option_type) - price
    
    try:
        # Check if solution exists in bounds
        low_price = black_scholes_price(S, K, T, r, low_vol, option_type)
        high_price = black_scholes_price(S, K, T, r, high_vol, option_type)
        
        if price < low_price or price > high_price:
            return np.nan
            
        iv = brentq(objective, low_vol, high_vol, xtol=1e-6)
        return iv
    except:
        return np.nan

def compute_greeks(S, K, T, r, sigma, option_type='call'):
    """Compute Delta, Gamma, and Charm for an option."""
    if T <= 0 or sigma <= 0:
        return {'delta': 0, 'gamma': 0, 'charm': 0}
    
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    # Delta
    if option_type == 'call':
        delta = norm.cdf(d1)
    else:
        delta = norm.cdf(d1) - 1
    
    # Gamma (same for put and call)
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    
    # Charm (dDelta/dt) - decay of delta over time
    charm = -norm.pdf(d1) * (2 * r * T - d2 * sigma * np.sqrt(T)) / (2 * T * sigma * np.sqrt(T))
    
    return {
        'delta': delta,
        'gamma': gamma,
        'charm': charm
    }

def load_underlying_prices(date_str):
    """Load underlying equity prices for a date."""
    # Convert date format
    date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    
    # Try tick data first
    tick_file = TICKS_DIR / date_formatted / "GME.csv"
    
    # Try minute bars as fallback
    bar_file = BASE_DIR / "research/phase76_echo_quant/data/bars" / f"GME_{date_formatted}_minute.csv"
    
    df = None
    
    if tick_file.exists():
        df = pd.read_csv(tick_file, nrows=100000)  # Limit for speed
        # Handle timestamp
        if 'timestamp_us' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp_us'], unit='us', utc=True)
        elif 'sip_timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['sip_timestamp'], unit='ns', utc=True)
        else:
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
            
        # Check if we have regular hours data
        if df['timestamp'].min().hour > 16:  # Only after-hours
            df = None  # Fallback to bars
    
    if df is None and bar_file.exists():
        df = pd.read_csv(bar_file)
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        df['price'] = df['close']
        print(f"  Using minute bars for {date_formatted}")
    
    if df is None:
        print(f"  Warning: No price data for {date_formatted}")
        return None
    
    # Resample to 1-second for matching
    df['ts_sec'] = df['timestamp'].dt.floor('1s')
    price_1s = df.groupby('ts_sec').agg({'price': 'last'}).reset_index()
    price_1s = price_1s.rename(columns={'ts_sec': 'timestamp'})
    
    return price_1s

def process_opra_file(filepath):
    """Process a single OPRA file and compute Greeks."""
    print(f"Processing: {filepath.name}")
    
    df = pd.read_csv(filepath)
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed', utc=True)
    
    # Extract date for underlying price lookup
    date_str = filepath.stem.split('_')[-1]
    
    # Load underlying prices
    price_df = load_underlying_prices(date_str)
    if price_df is None:
        return None
    
    # Match options trades to underlying price
    df['ts_sec'] = df['timestamp'].dt.floor('1s')
    df = df.merge(price_df, left_on='ts_sec', right_on='timestamp', suffixes=('', '_und'))
    df = df.rename(columns={'price_und': 'underlying_price', 'price': 'option_price'})
    
    # Compute time to expiry (in years)
    # Parse expiration from the data
    if 'expiration' in df.columns:
        df['expiration_dt'] = pd.to_datetime(df['expiration'], format='%Y-%m-%d', utc=True)
    else:
        # Assume expiration from filename
        df['expiration_dt'] = pd.to_datetime(date_str, format='%Y%m%d', utc=True)
    
    df['T'] = (df['expiration_dt'] - df['timestamp']).dt.total_seconds() / (365.25 * 24 * 3600)
    df['T'] = df['T'].clip(lower=1/365.25)  # Minimum 1 day
    
    # Determine option type
    if 'right' in df.columns:
        df['option_type'] = df['right'].str.lower()
    elif 'fetched_right' in df.columns:
        df['option_type'] = df['fetched_right'].str.lower()
    else:
        df['option_type'] = 'call'  # Default
    
    # Compute IV and Greeks
    results = []
    
    for idx, row in df.iterrows():
        S = row['underlying_price']
        K = row['strike']
        T = row['T']
        opt_type = row['option_type']
        opt_price = row['option_price']
        
        # Skip if price is invalid
        if pd.isna(opt_price) or opt_price <= 0:
            continue
        
        # Compute IV
        iv = implied_volatility(opt_price, S, K, T, RISK_FREE_RATE, opt_type)
        
        if pd.isna(iv):
            # Use a default IV if inversion fails
            iv = 0.5  # 50% IV as fallback
        
        # Compute Greeks
        greeks = compute_greeks(S, K, T, RISK_FREE_RATE, iv, opt_type)
        
        results.append({
            'timestamp': row['timestamp'],
            'strike': K,
            'expiration': row['expiration_dt'],
            'option_type': opt_type,
            'underlying_price': S,
            'option_price': opt_price,
            'size': row['size'],
            'iv': iv,
            'delta': greeks['delta'],
            'gamma': greeks['gamma'],
            'charm': greeks['charm'],
            # Compute dollar Greeks
            'delta_flow': row['size'] * greeks['delta'] * 100,  # *100 for contract multiplier
            'gamma_flow': row['size'] * greeks['gamma'] * 100,
            'charm_flow': row['size'] * greeks['charm'] * 100
        })
    
    result_df = pd.DataFrame(results)
    print(f"  Computed Greeks for {len(result_df)} trades")
    
    return result_df

def main():
    print("Phase 77: Greek Computation for OPRA Trades")
    print("=" * 50)
    
    # Process all OPRA files
    opra_files = sorted(glob.glob(str(OPRA_DIR / "gme_option_trades_*.csv")))
    
    all_results = []
    
    for filepath in opra_files:
        result = process_opra_file(Path(filepath))
        if result is not None and len(result) > 0:
            all_results.append(result)
    
    if not all_results:
        print("No results generated.")
        return
    
    df_all = pd.concat(all_results, ignore_index=True)
    
    # Aggregate to 1-second Greek flows
    df_all['ts_sec'] = df_all['timestamp'].dt.floor('1s')
    
    agg_flows = df_all.groupby('ts_sec').agg({
        'delta_flow': 'sum',
        'gamma_flow': 'sum',
        'charm_flow': 'sum',
        'size': 'sum',
        'underlying_price': 'last',
        'iv': 'mean'
    }).reset_index()
    
    agg_flows = agg_flows.rename(columns={'ts_sec': 'timestamp'})
    
    # Add put/call ratio
    put_call = df_all.groupby(['ts_sec', 'option_type'])['size'].sum().unstack(fill_value=0)
    if 'put' in put_call.columns and 'call' in put_call.columns:
        put_call['pc_ratio'] = put_call['put'] / (put_call['call'] + 1)
    else:
        put_call['pc_ratio'] = 0
    
    agg_flows = agg_flows.merge(put_call[['pc_ratio']], left_on='timestamp', right_index=True, how='left')
    
    # Save
    df_all.to_csv(OUTPUT_DIR / "opra_with_greeks.csv", index=False)
    agg_flows.to_csv(OUTPUT_DIR / "greek_flows_1s.csv", index=False)
    
    print(f"\n--- Summary ---")
    print(f"Total trades with Greeks: {len(df_all)}")
    print(f"1-second aggregated flows: {len(agg_flows)}")
    print(f"Saved: {OUTPUT_DIR / 'opra_with_greeks.csv'}")
    print(f"Saved: {OUTPUT_DIR / 'greek_flows_1s.csv'}")
    
    # Quick stats
    print(f"\nGreek Flow Statistics:")
    print(f"  Delta Flow: μ={agg_flows['delta_flow'].mean():.1f}, σ={agg_flows['delta_flow'].std():.1f}")
    print(f"  Gamma Flow: μ={agg_flows['gamma_flow'].mean():.4f}, σ={agg_flows['gamma_flow'].std():.4f}")
    print(f"  P/C Ratio: μ={agg_flows['pc_ratio'].mean():.2f}")

if __name__ == "__main__":
    main()
