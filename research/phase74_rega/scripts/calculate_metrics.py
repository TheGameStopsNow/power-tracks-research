import pandas as pd
import numpy as np
import os
import glob
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
OPTIONS_DIR = BASE_DIR / "data/raw/data/options_library/GME"
OHLCV_FILE = BASE_DIR / "research/phase42_history_options/full_history_stats.csv"
OUTPUT_FILE = BASE_DIR / "research/phase74_rega/daily_metrics.csv"
OUTPUT_DIR = BASE_DIR / "research/phase74_rega"

def load_ohlcv():
    print(f"Loading OHLCV from {OHLCV_FILE}...")
    df = pd.read_csv(OHLCV_FILE)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    # Calculate Dollar Volume
    df['dollar_vol'] = df['close'] * df['volume']
    # Calculate Daily Return
    df['ret'] = df['close'].pct_change()
    # Calculate Amihud Illiquidity Proxy (Impact Lambda)
    # Lambda ~ |Ret| / DollarVol
    # We take a rolling average to stabilize it, or just daily?
    # User said "estimated impact coefficient". Daily is noisy.
    # Let's use a 5-day rolling median of Amihud as the base "Lambda State"
    df['amihud'] = df['ret'].abs() / df['dollar_vol']
    df['lambda_proxy'] = df['amihud'].rolling(10, min_periods=1).median()
    
    # Simple Inverse Liquidity Proxy
    df['inv_liquidity'] = 1 / df['dollar_vol']
    
    return df.set_index('date')

def calculate_gex(date_str, spot_price):
    """
    Calculates Net Gamma Exposure (GEX) and Max Gamma Strike for a given date.
    Returns: (total_gex, max_gamma_strike, max_gamma_val)
    """
    # Find options file
    # Pattern: 2021-01-04/reconstructed_snapshot.parquet or similar
    # We need to handle potential varying filenames, but typically it's .../date/*.parquet
    
    day_dir = OPTIONS_DIR / date_str
    if not day_dir.exists():
        return None, None, None
        
    # Find parquet
    parquets = list(day_dir.glob("*.parquet"))
    if not parquets:
        return None, None, None
        
    path = parquets[0]
    
    try:
        df = pd.read_parquet(path)
    except Exception as e:
        print(f"Error reading {path}: {e}")
        return None, None, None

    # Necessary cols: type, strike, gamma, open_interest
    required = ['type', 'strike', 'gamma', 'open_interest']
    if not all(c in df.columns for c in required):
        return None, None, None

    # Filter for near-term? 
    # Research says "near-the-money, 0-1 DTE" is dominator? 
    # For daily GEX usually we take the whole chain or at least "near money".
    # Let's take ALL strikes within +/- 15% of spot to filter noise
    # But wait, we want "Dominance".
    # Let's stick to the 'vector_builder.py' logic: NTM +/- 15%
    
    ntm_mask = (df['strike'] >= spot_price * 0.85) & (df['strike'] <= spot_price * 1.15)
    ntm_df = df[ntm_mask].copy()
    
    if ntm_df.empty:
        return 0.0, None, 0.0

    # Calculate GEX per strike
    # GEX = Gamma * OI * 100 * Spot
    # For Dealer Exposure:
    # Dealer Short Calls (Price Up -> Delta Up -> Dealer Buys). Positive Gamma for Dealer?
    # No. 
    # Long Option = Long Gamma.
    # If Market is Long Calls, Dealer is Short Calls.
    # Dealer Short Call = Short Gamma. (Price Up -> Dealer Short Delta increases -> Dealer Sells). 
    # WAIT. 
    # Short Call Delta is negative (e.g. -0.5). Price Up -> Delta becomes -0.6. Dealer must Sell more to hedge.
    # Short Put Delta is positive (e.g. +0.5). Price Down -> Delta becomes +0.4. Dealer must Sell to hedge.
    # So Short Gamma (Net Short Options) = "Sell into weakness, Sell into strength" -> Destabilizing?
    # No. 
    # Long Gamma (Net Long Options) = "Buy Low, Sell High" -> Stabilizing.
    # Short Gamma = "Sell Low, Buy High" -> Destabilizing.
    
    # User conventions: "Gamma of the net position".
    # "If 1+lambda*Gamma is large... price gets stiffer". 
    # Stiffer = Stabilized = Long Gamma.
    # Unstable = Short Gamma.
    
    # So we assume POSITIVE GEX = STABILIZING (Dealer Long Options).
    # NEGATIVE GEX = DESTABILIZING (Dealer Short Options).
    
    # We typically assume Open Interest maps to "Customer Long".
    # Therefore Dealer is "Short".
    # So OpenInterest -> Negative Gamma contribution for Dealer?
    
    # Let's define GEX simply as the MAGNITUDE of potential hedging flow.
    # Or signed? User says "threshold is basically lambda*Gamma approx -1".
    # Meaning Negative Gamma (Destabilizing) causes instability.
    # Positive Gamma (Stabilizing) causes pinning.
    # Pinning = Price "stiffer".
    # So we want Positive GEX for Pinning prediction.
    
    # Standard assumption: Customers are Long Calls, Long Puts.
    # Dealer is Short Calls (-Gamma), Short Puts (-Gamma).
    # This implies Dealers are ALWAYS Short Gamma?
    # That doesn't fit the "Pinning" narrative (which requires Long Gamma).
    # Actually, MMs are often Long Inventory?
    
    # Let's look at the User's text: 
    # "Pinning / magnetization on high-gamma expiry days"
    # This implies High Gamma = Pinning.
    # So for this metric, we assume the calculated "GEX" is POSITIVE.
    # We will just sum Abs(Gamma) or just Gamma?
    # Gamma is always positive for options.
    # So we calculate "Total System Gamma Inventory". 
    # We will essentially treat it as "Available Magnetism".
    # Higher = More Pinning.
    
    ntm_df['gex'] = ntm_df['gamma'] * ntm_df['open_interest'] * 100 * spot_price
    
    # Aggregate by Strike to find "Pin Strike"
    strike_gex = ntm_df.groupby('strike')['gex'].sum()
    if strike_gex.empty:
        return 0.0, None, 0.0
        
    max_strike = strike_gex.idxmax()
    max_val = strike_gex.max()
    total_gex = ntm_df['gex'].sum()
    
    return total_gex, max_strike, max_val

def main():
    if not OUTPUT_DIR.exists():
        os.makedirs(OUTPUT_DIR)
        
    ohlcv = load_ohlcv()
    
    print("Processing Dates...")
    
    results = []
    
    # Iterate through days we have OHLCV for
    # (Since we need Spot for GEX Calc)
    
    # Limit to 2021-2025
    # Just iterate index
    for date, row in ohlcv.iterrows():
        date_str = date.strftime("%Y-%m-%d")
        
        # Look for options
        # We pass Spot = Close (approx)
        spot = row['close']
        
        total_gex, max_strike, max_gex_at_strike = calculate_gex(date_str, spot)
        
        if total_gex is not None:
            # We have options data
            results.append({
                'date': date,
                'close': spot,
                'volume': row['volume'],
                'dollar_vol': row['dollar_vol'],
                'lambda_amihud': row['lambda_proxy'], # Smoothed Impact
                'total_gex': total_gex,
                'max_gamma_strike': max_strike,
                'gex_at_max_strike': max_gex_at_strike,
                'ret': row['ret']
            })
            
    res_df = pd.DataFrame(results)
    
    if res_df.empty:
        print("No options data matched with OHLCV.")
        return

    # Compute Dominance Ratio
    # R = Lambda * Gamma
    # R is unitless-ish.
    # Unit Check:
    # Gamma (GEX calculated as Gamma*OI*100*Spot) has units of Dollars (of Delta) per Unit Move?
    # Actually: Gamma = dDelta/dSpot. Units 1/$.
    # GEX = Gamma * Spot * OI * 100 * Spot?
    # Wait, simple GEX = Gamma * OI * 100 * Spot.
    # Gamma (1/$) * Spot ($) = Unitless Delta sensitivity?
    # Delta is unitless (shares/contract?).
    # Let's say GEX = (1/$) * $ * Contracts = Contracts?
    # Then * Spot = Dollars.
    # So GEX is in Dollars. "Dollars needed to hedge per 1% move" is roughly accurate.
    
    # Lambda (Impact) = 1 / DollarVol. Units 1/$.
    # So R = GEX ($) * Lambda (1/$) = Unitless.
    # This works.
    
    # However, Lambda = |Ret| / DollarVol has units of (1) / $.
    # So R = GEX * (Ret / DollarVol) ~ Unitless.
    
    # We will use the smoothed lambda proxy.
    res_df['dominance_ratio'] = res_df['total_gex'] * res_df['lambda_amihud']
    
    # Outcome Variable: Pinned?
    # Close within 0.5% of max_gamma_strike
    res_df['dist_to_pin'] = (res_df['close'] - res_df['max_gamma_strike']).abs() / res_df['max_gamma_strike']
    res_df['is_pinned'] = (res_df['dist_to_pin'] < 0.005).astype(int)
    
    # Save
    res_df.to_csv(OUTPUT_FILE, index=False)
    print(f"Saved metrics for {len(res_df)} days to {OUTPUT_FILE}")
    print(res_df[['date', 'dominance_ratio', 'is_pinned']].head())
    print(res_df[['date', 'dominance_ratio', 'is_pinned']].tail())

if __name__ == "__main__":
    main()
