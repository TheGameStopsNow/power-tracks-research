import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, accuracy_score, roc_auc_score
from pathlib import Path
import json
import matplotlib.pyplot as plt
import os

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
INPUT_FILE = BASE_DIR / "research/phase74_rega/daily_metrics.csv"
OUTPUT_DIR = BASE_DIR / "research/phase74_rega/results"

def fit_logistic(df, train_mask, test_mask):
    print("--- Logistic Regression (sklearn) ---")
    
    # Needs 2D array for X
    X = df[['dominance_ratio']].values
    y = df['is_pinned'].values
    
    X_train, y_train = X[train_mask], y[train_mask]
    X_test, y_test = X[test_mask], y[test_mask]
    
    # Fit
    # C=1e9 to disable regularization (match statsmodels unpenalized)
    model = LogisticRegression(C=1e9, solver='lbfgs')
    model.fit(X_train, y_train)
    
    # Coefficients
    b0 = model.intercept_[0]
    b1 = model.coef_[0][0]
    print(f"Intercept: {b0:.4f}")
    print(f"Coeff (R): {b1:.4f}")
    
    # Predict
    y_pred_prob = model.predict_proba(X_test)[:, 1]
    
    # Metrics
    if len(np.unique(y_test)) > 1:
        auc = roc_auc_score(y_test, y_pred_prob)
    else:
        auc = 0.0
        print("Warning: Only one class in test set.")
    
    ll = log_loss(y_test, y_pred_prob)
    
    print(f"Test AUC: {auc:.3f}")
    print(f"Test LogLoss: {ll:.3f}")
    
    return model, auc, ll

def plot_fit(df, model, filename="logistic_fit.png"):
    plt.figure(figsize=(10, 6))
    
    # Scatter points
    plt.scatter(df['dominance_ratio'], df['is_pinned'], alpha=0.5, label='Observed')
    
    # Curve
    x_min, x_max = df['dominance_ratio'].min(), df['dominance_ratio'].max()
    x_range = np.linspace(x_min, x_max, 100).reshape(-1, 1)
    y_curve = model.predict_proba(x_range)[:, 1]
    
    plt.plot(x_range, y_curve, color='red', label='Logistic Fit')
    
    plt.xlabel("Dominance Ratio ($R_t$)")
    plt.ylabel("Pinning Probability ($P(Y=1)$)")
    plt.title("Dominance Ratio Threshold Model")
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    out_path = OUTPUT_DIR / filename
    plt.savefig(out_path)
    print(f"Saved plot to {out_path}")

def main():
    if not OUTPUT_DIR.exists():
        os.makedirs(OUTPUT_DIR)
        
    df = pd.read_csv(INPUT_FILE)
    df = df.dropna()
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    
    print(f"Total Samples: {len(df)}")
    if len(df) < 10:
        print("Not enough samples to fit.")
        return

    # Train/Test Split
    # Use 80% split
    cutoff_idx = int(len(df) * 0.8)
    cutoff_date = df.iloc[cutoff_idx]['date']
    print(f"Split Date: {cutoff_date}")
    
    train_mask = df['date'] < cutoff_date
    test_mask = df['date'] >= cutoff_date
    
    # Run Logistic
    model, auc, ll = fit_logistic(df, train_mask, test_mask)
    
    plot_fit(df, model)
    
    # Threshold Analysis
    # Where does P(Pinned) = 0.5?
    # 0 = b0 + b1 * R -> R = -b0/b1
    b0 = model.intercept_[0]
    b1 = model.coef_[0][0]
    
    if abs(b1) > 1e-5:
        threshold = -b0 / b1
        print(f"Critical Threshold R*: {threshold:.4f}")
    else:
        threshold = None
        print("Slope is zero, no threshold.")
    
    result = {
        "n_samples": len(df),
        "auc": auc,
        "log_loss": ll,
        "intercept": b0,
        "coefficient": b1,
        "critical_threshold": threshold
    }
    
    with open(OUTPUT_DIR / "metrics_report.json", "w") as f:
        json.dump(result, f, indent=2)

if __name__ == "__main__":
    main()
