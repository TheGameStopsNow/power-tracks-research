"""
Phase 83: Fit Prism Equation (Mathematical Formalization)

Fits the continuous "Prism Equation" to the empirical burst data using Non-Linear Least Squares.

Model:
    E[R] = beta_0 + beta_1 * L(Gamma) * C(IV) * A(Charm)

    L(Gamma) = log(1 + |Gamma|)
    C(IV) = 1 / (1 + exp(-k * (IV - IV_critical)))  <- Sigmoid Activation
    A(Charm) = 1 + gamma * sgn(Charm)               <- Linear Multiplier

Goal: Solve for 'k' (Phase Transition Stiffness) and 'gamma' (Charm Sensitivity).
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.optimize import curve_fit

BASE_DIR = Path(__file__).resolve().parents[3]
INPUT_FILE = BASE_DIR / "research/phase77_greek_echo/results/burst_fingerprints_enhanced.csv"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def sigmoid(x, k, x0):
    """
    Sigmoid activation function.
    k: Stiffness (Slope at transition).
    x0: Critical Threshold (Inflection point).
    """
    # Clip exponent to avoid overflow
    arg = -k * (x - x0)
    arg = np.clip(arg, -50, 50)
    return 1 / (1 + np.exp(arg))

def prism_model(X, beta_0, beta_1, k, gamma):
    """
    The Coupled Prism Equation.
    X: [abs_gamma, iv, charm_sign]
    """
    gamma_val, iv, charm_sign = X
    
    # 1. Lens Function L (Log scaling of Gamma to handle outliers)
    lens = np.log1p(gamma_val)
    
    # 2. Coupling Function C (Phase Transition at IV)
    # Fixing x0 at 0.664 (empirically derived) or letting it float?
    # Let's let it float to verify the 66.4% finding mathematically.
    # Wait, curve_fit arguments must be explicit.
    # Let's assume x0 is a parameter to optimize too. 
    # But for this simple signature, let's start by fixing x0=0.664 and optimize k.
    
    coupling = sigmoid(iv, k, 0.664)
    
    # 3. Accelerant Function A (Charm Interaction)
    # If Charm > 0, A > 1 (Boost). If Charm < 0, A < 1 (Dampen).
    # Simple form: 1 + gamma * sign(charm)
    accelerant = 1 + gamma * charm_sign
    
    # Interaction
    return beta_0 + beta_1 * lens * coupling * accelerant

def prism_model_with_floating_threshold(X, beta_0, beta_1, k, x0, gamma):
    """
    Full model allowing the Critical Threshold (x0) to be discovered by the fit.
    """
    gamma_val, iv, charm_sign = X
    lens = np.log1p(gamma_val)
    coupling = sigmoid(iv, k, x0)
    accelerant = 1 + gamma * charm_sign
    return beta_0 + beta_1 * lens * coupling * accelerant

def main():
    print("Phase 83: Fitting the Prism Equation...")
    
    # Load Data
    df = pd.read_csv(INPUT_FILE)
    valid = df.dropna(subset=['ret_60d']).copy()
    
    # Filter very extreme outliers for stability
    valid = valid[valid['ret_60d'].abs() < 200]
    
    X_data = [
        valid['gamma_flow'].abs().values,
        valid['iv'].values,
        np.sign(valid['charm_flow'].values)
    ]
    y_data = valid['ret_60d'].values
    
    print(f"Data Points: {len(y_data)}")
    
    # --- FIT 1: Fixed Threshold (0.664) ---
    print("\nAttempting Fit 1 (Fixed Threshold 66.4%)...")
    # P0: beta0=0, beta1=1, k=10, gamma=0.1
    try:
        popt, pcov = curve_fit(prism_model, X_data, y_data, p0=[0, 1, 10, 0.1], maxfev=5000)
        perr = np.sqrt(np.diag(pcov))
        
        print("Model Parameters:")
        print(f"  Beta_0 (Base Drift):  {popt[0]:.4f}")
        print(f"  Beta_1 (Sensitivity): {popt[1]:.4f}")
        print(f"  k (Stiffness):        {popt[2]:.4f}")
        print(f"  Gamma (Charm Factor): {popt[3]:.4f}")
        
        # Calculate R2
        y_pred = prism_model(X_data, *popt)
        ss_res = np.sum((y_data - y_pred)**2)
        ss_tot = np.sum((y_data - np.mean(y_data))**2)
        r2 = 1 - (ss_res / ss_tot)
        print(f"  R^2 Score: {r2:.4f}")
        
    except Exception as e:
        print(f"Fit 1 Failed: {e}")

    # --- FIT 2: Floating Threshold (Discovery) ---
    print("\nAttempting Fit 2 (Floating Threshold)...")
    try:
        # P0: beta0, beta1, k=20, x0=0.66, gamma=0.1
        # Bounds for x0: [0.5, 0.9] (reasonable IV range)
        popt2, pcov2 = curve_fit(
            prism_model_with_floating_threshold, 
            X_data, y_data, 
            p0=[0, 1, 20, 0.66, 0.1],
            bounds=([-np.inf, -np.inf, 0, 0.4, -np.inf], [np.inf, np.inf, 200, 1.0, np.inf]),
            maxfev=10000
        )
        
        print("Model Parameters (Floating):")
        print(f"  Critical Threshold (x0): {popt2[3]:.4f} (Physics = 66.40%)")
        print(f"  k (Stiffness):           {popt2[2]:.4f}")
        
        # Save Predictions for Comparison
        valid['pred_continuous'] = prism_model_with_floating_threshold(X_data, *popt2)
        
        # Compare vs Boolean Logic
        # Boolean Logic: If IV > 0.664 and Charm > 0: Trade.
        # Simple proxy: trade if algo says trade.
        # Let's compare fit error.
        
        y_pred2 = valid['pred_continuous']
        ss_res2 = np.sum((y_data - y_pred2)**2)
        r2_2 = 1 - (ss_res2 / ss_tot)
        print(f"  R^2 Score: {r2_2:.4f}")
        
        # Save Params
        with open(OUTPUT_DIR / "prism_equation_params.txt", "w") as f:
            f.write(f"Critical Threshold (x0): {popt2[3]:.6f}\n")
            f.write(f"Stiffness (k): {popt2[2]:.6f}\n")
            f.write(f"Charm Factor (gamma): {popt2[4]:.6f}\n")
            f.write(f"R2: {r2_2:.6f}\n")
            
        # Plot Fit
        plt.figure(figsize=(10, 6))
        plt.scatter(y_data, y_pred2, alpha=0.5, label='Data')
        plt.plot([y_data.min(), y_data.max()], [y_data.min(), y_data.max()], 'r--', label='Perfect Fit')
        plt.title("Actual vs Predicted Returns (Prism Equation)")
        plt.xlabel("Actual Return (%)")
        plt.ylabel("Math Model Predicted (%)")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig(OUTPUT_DIR / "model_fit_scatter.png")
        print(f"Saved plot: {OUTPUT_DIR / 'model_fit_scatter.png'}")
        
    except Exception as e:
        print(f"Fit 2 Failed: {e}")

if __name__ == "__main__":
    main()
