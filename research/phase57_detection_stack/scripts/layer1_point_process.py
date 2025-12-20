#!/usr/bin/env python3
"""
Layer 1: Point Process Residuals
================================

Detects "Clock-Like" structure in trade arrival times by removing specific market burstiness.

Method:
1. Fit Univariate Hawkes Process (self-exciting): lambda(t) = mu + sum(alpha * exp(-beta * (t - ti)))
2. Compute Time-Rescaled Residuals: int_{t_{i-1}}^{t_i} lambda(u) du
3. If model explains burstiness, residuals should be i.i.d. Exponential(1).
4. Transform to Uniform[0,1] and test with Kolmogorov-Smirnov (KS).
5. Deviations indicate "unexplained structural timing" (e.g. periodic steganography).
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy import stats
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from research.phase57_detection_stack.layer0_data_harness import TickLoader, RegimeConditioner

class HawkesEstimator:
    def __init__(self, decay_beta: float = 100.0):
        # We can fix beta (decay rate) or fit it. 
        # Markets usually have beta around 100-1000 (ms scale).
        self.mu = 0.5
        self.alpha = 10.0
        self.beta = decay_beta 
        self.is_fitted = False

    def _recursive_intensity(self, timestamps, mu, alpha, beta):
        """
        Computes intensity at each event time t_k linearly.
        timestamps: array of times in SECONDS
        """
        n = len(timestamps)
        lambda_values = np.zeros(n)
        r_values = np.zeros(n)
        
        # R[k] = exp(-beta * (t_k - t_{k-1})) * (1 + R[k-1]) (roughly, depends on definition)
        # Correct def: sum_{ti < tk} exp(-beta(tk - ti))
        # R[k] = sum_{ti < tk} ...
        #      = sum_{ti < t_{k-1}} exp(-beta(tk - ti)) + exp(-beta(tk - t_{k-1})) ? No.
        
        # Recursive relation:
        # A(t) = sum_{ti < t} exp(-beta(t - ti))
        # At t_k: A(t_k) = sum_{i=0}^{k-1} exp(-beta(t_k - t_i))
        # A(t_k) = exp(-beta(t_k - t_{k-1})) * (1 + A(t_{k-1})) -- IF t_0 is included?
        # Let's simple recursion loop:
        
        last_r = 0.0
        # Assume t_{-1} = timestamps[0] approximately for the first point or start at 0
        # Actually standard simple recursion:
        
        dt = np.diff(timestamps, prepend=timestamps[0]) # prepend for first point
        
        # Optimized loop? Python loop is slow. 
        # For prototype, python loop is fine for N < 100k. Limit sample size.
        
        for i in range(1, n):
            term = np.exp(-beta * dt[i])
            last_r = term * (1 + last_r)
            lambda_values[i] = mu + alpha * last_r
            
        lambda_values[0] = mu # Base intensity for first point
        return lambda_values

    def fit(self, timestamps: np.ndarray):
        """
        Fit mu, alpha using MLE (fixing beta for stability/speed).
        timestamps: relative seconds from start (0.0 to T).
        """
        # Phase 57b: Jitter for unique timestamps
        # If we have duplicates, the log-likelihood explodes or residuals zero out.
        # Add tiny uniform jitter (nano-scale)
        dt = np.diff(timestamps)
        if np.any(dt == 0):
            # Add random jitter up to 100ns (1e-7 s)
            # Preserving monotonicity is key. 
            # We add cumulative jitter or just random?
            # Random uniform [0, 1e-6] doesn't guarantee sort order if original are same.
            # Better: add epsilon * index to sort order
            
            # Sort first (should be sorted)
            timestamps = np.sort(timestamps)
            # Find duplicates
            # Simple approach: add small noise to ALL timestamps, re-sort
            jitter = np.random.uniform(0, 1e-7, size=len(timestamps))
            timestamps = timestamps + jitter
            timestamps = np.sort(timestamps)
            
        t = timestamps - timestamps[0]
        n = len(t)
        T = t[-1]

        
        def neg_log_likelihood(params):
            mu, alpha = params
            if mu <= 0 or alpha < 0: return 1e9
            if alpha >= self.beta: return 1e9 # Stability condition alpha < beta (branching ratio < 1)
            
            # 1. Sum log(lambda(t_i))
            lam = self._recursive_intensity(t, mu, alpha, self.beta)
            # Avoid log(0)
            lam = np.maximum(lam, 1e-9)
            term1 = np.sum(np.log(lam))
            
            # 2. Integral_0^T lambda(u) du
            # = mu * T + alpha/beta * sum_{i=0}^{n-1} (1 - exp(-beta(T - t_i)))
            term2 = mu * T + (alpha / self.beta) * np.sum(1 - np.exp(-self.beta * (T - t)))
            
            return -(term1 - term2)

        # Initial guess
        initial_guess = [len(t)/T * 0.5, self.beta * 0.5]
        
        res = minimize(neg_log_likelihood, initial_guess, bounds=[(1e-4, None), (1e-4, self.beta-0.1)], method='L-BFGS-B')
        
        self.mu, self.alpha = res.x
        self.is_fitted = True
        return {'mu': self.mu, 'alpha': self.alpha, 'beta': self.beta, 'nll': res.fun}

    def get_residuals(self, timestamps: np.ndarray):
        """
        Compute Time-Rescaled Residuals.
        tau_k = int_{t_{k-1}}^{t_k} lambda(u) du
        """
        if not self.is_fitted:
            raise ValueError("Model not fitted")
            
        t = timestamps - timestamps[0]
        n = len(t)
        residuals = []
        
        # Recompute recursion to get state at each step
        last_r = 0.0
        dt = np.diff(t)
        
        # We need integral between t_{k-1} and t_k
        # int_{t_{k-1}}^{t_k} (mu + alpha * A(u)) du
        # A(u) decays from A(t_{k-1}) + 1 (pulse at t_{k-1})
        # Value immediately after t_{k-1} is (A(t_{k-1}) + 1)
        # So A(u) = (A(t_{k-1}) + 1) * exp(-beta(u - t_{k-1}))
        
        # Integral = mu*dt + alpha * (A(t_{k-1}) + 1) * (1 - exp(-beta*dt)) / beta
        
        # Re-run recursion tracking 'last_r' which represents A(t_{k-1}) BEFORE decay to current
        
        current_A = 0.0 # A(t_0) approx 0
        
        for k in range(1, n):
            delta = dt[k-1]
            
            # Intensity part from past events immediately after t_{k-1}
            # The "state" A just after t_{k-1} includes the jump from event k-1
            # So val = current_A + 1 (since event match alpha kernel) -> NO.
            # Definition: lambda(t) = mu + alpha * sum_{ti < t} ...
            # just after t_{k-1}, the sum includes t_{k-1}.
            
            val_after_prev_event = current_A + 1.0 
            
            # Integrate from u=0 to delta: (mu + alpha * val_after * exp(-beta * u))
            integral = self.mu * delta + (self.alpha * val_after_prev_event / self.beta) * (1 - np.exp(-self.beta * delta))
            
            residuals.append(integral)
            
            # Update state for next step
            # current_A (at t_k) = val_after_prev_event * exp(-beta * delta)
            current_A = val_after_prev_event * np.exp(-self.beta * delta)
            
        return np.array(residuals)

def ks_test_uniformity(residuals):
    """
    Transform exponential residuals to Uniform via U = 1 - exp(-res).
    Then KS test against Uniform[0,1].
    """
    u_vals = 1 - np.exp(-residuals)
    
    # Grid for KS
    # compare empirical CDF vs uniform CDF (which is x)
    res = stats.kstest(u_vals, 'uniform')
    
    return {
        'statistic': res.statistic,
        'pvalue': res.pvalue,
        'u_vals': u_vals
    }

if __name__ == "__main__":
    # Test on GME data chunk
    loader = TickLoader()
    # sample_dirs = sorted([d for d in DATA_DIR.glob("sample_*") if d.is_dir()])
    # test_date = sample_dirs[-1].name.replace("sample_", "")
    # Hardcode for speed if known, else dynamic
    test_date = "2024-05-14" # High volume day
    symbol = "GME"
    
    print(f"Loading {symbol} for {test_date}...")
    df = loader.load_ticks(test_date, symbol)
    
    if df is not None:
        # Filter for a high-intensity minute (Regime Conditioned)
        conditioner = RegimeConditioner()
        df = conditioner.label_regimes(df)
        
        # Pick a 'Normal Trading' or 'High Volume' slice
        sub = df[df['regime'].str.contains("Normal") | df['regime'].str.contains("High")].copy()
        
        if len(sub) < 1000:
            print("Not enough specific regime data, using all.")
            sub = df
            
        # Take a 1000-event chunk
        chunk = sub.iloc[1000:2000].copy()
        if len(chunk) < 500:
            print("Chunk too small.")
            sys.exit()
            
        timestamps = chunk['timestamp'].astype(np.int64) / 1e9 # Convert to seconds
        timestamps = timestamps.values
        
        print(f"\nFitting Hawkes on {len(timestamps)} events...")
        hwk = HawkesEstimator(decay_beta=100.0) # 10ms decay roughly
        res_fit = hwk.fit(timestamps)
        print(f"Fit: mu={res_fit['mu']:.4f}, alpha={res_fit['alpha']:.4f}, beta={res_fit['beta']:.4f}")
        
        print("Computing residuals...")
        resid = hwk.get_residuals(timestamps)
        
        print("Testing Uniformity (KS Test)...")
        ks_res = ks_test_uniformity(resid)
        print(f"KS Statistic: {ks_res['statistic']:.4f}")
        print(f"P-Value: {ks_res['pvalue']:.6f}")
        
        if ks_res['pvalue'] < 0.05:
            print(">> REJECT Null: Significant unexplained timing structure found.")
        else:
            print(">> FAIL TO REJECT: Timing consistent with Hawkes process.")
