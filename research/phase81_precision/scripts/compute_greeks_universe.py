"""
Phase 81: Compute Greeks Universal (TSLA, AMD)

Computes delta, gamma, charm, and IMPLIED VOLATILITY (Vectorized Newton-Raphson).
Essential for checking the "67% IV Threshold" generality.
"""

import pandas as pd
import numpy as np
import scipy.stats as stats
from pathlib import Path
import glob
import time

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
OUTPUT_DIR = BASE_DIR / "research/phase81_precision/output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

R = 0.052 # Risk-free rate

def load_bars(ticker, date_str):
    bar_dir = BASE_DIR / f"research/phase81_precision/data/bars/{ticker}"
    bar_file = bar_dir / f"{ticker}_{date_str}_minute.csv" # 20240205 format from fetch script?
    # fetch_universe_bars saves as {ticker}_20240205_minute.csv (from date.replace('-',''))
    
    if not bar_file.exists():
        return None
    df = pd.read_csv(bar_file)
    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df = df.sort_values('timestamp')
    return df

def implied_volatility_vectorized(C, S, K, T, r):
    """
    Robust Bisection Method for IV.
    """
    low = np.zeros_like(C) + 0.001
    high = np.zeros_like(C) + 5.0 # Max 500% IV
    
    for i in range(15): # 15 iterations is enough for reasonable precision
        mid = (low + high) / 2
        
        d1 = (np.log(S / K) + (r + 0.5 * mid ** 2) * T) / (mid * np.sqrt(T))
        d2 = d1 - mid * np.sqrt(T)
        
        price = S * stats.norm.cdf(d1) - K * np.exp(-r * T) * stats.norm.cdf(d2)
        
        mask = price > C
        high[mask] = mid[mask]
        low[~mask] = mid[~mask]
        
    return (low + high) / 2

def compute_greeks_batch(df):
    S = df['underlying_price'].values
    K = df['fetched_strike'].values
    T = df['time_to_expiry'].values
    r = R
    
    # Estimate IV
    # Note: If right='P', we should use Put-Call Parity or Put pricing.
    # For MVP, let's assume market price reflects Call logic or convert P to C price via parity?
    # Simpler: Just run IV solver for Calls. For Puts, convert price?
    # Or just solve Put IV separately.
    
    # Vectorized solver is tricky with mixed types.
    # Group by Right.
    
    df['iv'] = 0.5
    df['delta'] = 0.0
    df['gamma'] = 0.0
    df['charm'] = 0.0
    
    # CALLS
    calls = df[df['fetched_right'] == 'C'].copy()
    if len(calls) > 0:
        Sc = calls['underlying_price'].values
        Kc = calls['fetched_strike'].values
        Tc = calls['time_to_expiry'].values
        Price = calls['price'].values
        
        iv_c = implied_volatility_vectorized(Price, Sc, Kc, Tc, r)
        
        d1 = (np.log(Sc / Kc) + (r + 0.5 * iv_c ** 2) * Tc) / (iv_c * np.sqrt(Tc))
        d2 = d1 - iv_c * np.sqrt(Tc)
        
        delta = stats.norm.cdf(d1)
        gamma = stats.norm.pdf(d1) / (Sc * iv_c * np.sqrt(Tc))
        charm = -stats.norm.pdf(d1) * (2*r*Tc - d2*iv_c*np.sqrt(Tc)) / (2*Tc*iv_c*np.sqrt(Tc))
        
        calls['iv'] = iv_c
        calls['delta'] = delta
        calls['gamma'] = gamma
        calls['charm'] = charm
        
        df.update(calls)
        
    # PUTS (Approximation: Use same IV logic or skip for now? Need accurate IV for threshold.)
    # Let's verify Put IV.
    # Put Price P = K*exp(-rT)*N(-d2) - S*N(-d1)
    # Using Call IV solver on P is wrong.
    # Quick fix: Convert Put Price to Call Price via Parity: C = P + S - K*exp(-rT)
    puts = df[df['fetched_right'] == 'P'].copy()
    if len(puts) > 0:
        Sp = puts['underlying_price'].values
        Kp = puts['fetched_strike'].values
        Tp = puts['time_to_expiry'].values
        PriceP = puts['price'].values
        
        # Synthetic Call Price
        PriceC = PriceP + Sp - Kp * np.exp(-r * Tp)
        # Ensure positive
        PriceC = np.maximum(PriceC, 0.01)
        
        iv_p = implied_volatility_vectorized(PriceC, Sp, Kp, Tp, r)
        
        d1 = (np.log(Sp / Kp) + (r + 0.5 * iv_p ** 2) * Tp) / (iv_p * np.sqrt(Tp))
        d2 = d1 - iv_p * np.sqrt(Tp)
        
        delta = stats.norm.cdf(d1) - 1
        gamma = stats.norm.pdf(d1) / (Sp * iv_p * np.sqrt(Tp))
        charm = -stats.norm.pdf(d1) * (2*r*Tp - d2*iv_p*np.sqrt(Tp)) / (2*Tp*iv_p*np.sqrt(Tp))
        
        puts['iv'] = iv_p
        puts['delta'] = delta
        puts['gamma'] = gamma
        puts['charm'] = charm
        
        df.update(puts)
        
    return df

def process_file(file_path, ticker):
    date_str = file_path.stem.split('_')[-1] # 20240205
    
    # Load Bars
    bars = load_bars(ticker, date_str)
    if bars is None: return None
    
    df = pd.read_csv(file_path)
    if len(df) == 0: return None
    
    # Parse Timestamps
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed')
    if df['timestamp'].dt.tz is None:
        df['timestamp'] = df['timestamp'].dt.tz_localize('America/New_York', ambiguous='infer').dt.tz_convert('UTC')
        
    df = df.sort_values('timestamp')
    
    # Merge
    merged = pd.merge_asof(
        df, bars[['timestamp', 'close']],
        on='timestamp', direction='backward', tolerance=pd.Timedelta('5min')
    )
    
    merged['underlying_price'] = merged['close']
    merged = merged.dropna(subset=['underlying_price'])
    
    if len(merged) == 0: return None
    
    # Expiry
    merged['expiry_dt'] = pd.to_datetime(merged['expiration'].astype(str), format='%Y%m%d').dt.tz_localize('UTC') + pd.Timedelta(hours=16)
    merged['time_to_expiry'] = (merged['expiry_dt'] - merged['timestamp']).dt.total_seconds() / (365 * 24 * 3600)
    merged = merged[merged['time_to_expiry'] > 0]
    
    # Compute Greeks
    processed = compute_greeks_batch(merged)
    
    out_file = OUTPUT_DIR / f"{ticker.lower()}_greeks_{date_str}.csv"
    processed.to_csv(out_file, index=False)
    print(f"Saved {ticker} {date_str}: {len(processed)} rows (Avg IV: {processed['iv'].mean():.2f})")

def main():
    print("Computing Universal Greeks...")
    for ticker in ["TSLA", "AMD"]:
        trade_dir = BASE_DIR / f"research/phase81_precision/data/opra_{ticker.lower()}"
        files = sorted(list(trade_dir.glob("*.csv")))
        print(f"Processing {ticker} ({len(files)} files)...")
        for f in files:
            process_file(f, ticker)

if __name__ == "__main__":
    main()
