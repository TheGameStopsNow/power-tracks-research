import numpy as np
from scipy.stats import norm

def calculate_gamma(S, K, T, sigma, r=0.0):
    """
    Calculate Black-Scholes Gamma for a Call or Put (Gamma is same for both).
    S: Spot Price
    K: Strike Price
    T: Time to Expiration (years)
    sigma: Implied Volatility (decimal)
    r: Risk-free rate (decimal)
    
    Returns: Gamma value
    """
    # Gamma = N'(d1) / (S * sigma * sqrt(T))
    # We assume T > 0, sigma > 0, S > 0 from caller or use np.errstate
    
    # Allow small T to avoid div by zero if not filtered
    # But caller did filter T > 0.001. So we are safe.
    
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    
    # Gamma = N'(d1) / (S * sigma * sqrt(T))
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    
    return gamma
