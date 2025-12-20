"""
Phase 77: Predictive Model for Options Burst Effects

This module builds:
1. Linear regression model to predict returns from burst fingerprints
2. Feature importance and coefficient analysis
3. Cluster analysis to understand which burst types have predictable effects
4. Model validation with R², out-of-sample testing
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from scipy import stats
from sklearn.linear_model import LinearRegression, Ridge, Lasso
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import r2_score, mean_absolute_error

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GREEK_DIR = BASE_DIR / "research/phase77_greek_echo/results"
OUTPUT_DIR = BASE_DIR / "research/phase77_greek_echo/results"

def load_data():
    """Load the explored burst data."""
    df = pd.read_csv(GREEK_DIR / "bursts_deep_explored.csv")
    df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed', utc=True)
    return df

def build_feature_matrix(df):
    """
    Build feature matrix X and target vector y.
    """
    # Define features
    feature_cols = [
        'gamma_flow',
        'delta_flow', 
        'charm_flow',
        'pc_ratio',
        'iv',
        'pct_0dte',
        'pct_itm',
        'pct_otm',
    ]
    
    # Add derived features
    df['is_morning'] = (df['hour'] < 12).astype(float)
    df['gamma_x_pc'] = df['gamma_flow'] * df['pc_ratio']
    df['charm_sign'] = np.sign(df['charm_flow'])
    
    feature_cols.extend(['is_morning', 'gamma_x_pc', 'charm_sign'])
    
    # Filter to available features
    available = [c for c in feature_cols if c in df.columns]
    
    # Drop rows with missing values
    valid = df[available + ['ret_5d', 'ret_20d', 'ret_60d']].dropna()
    
    print(f"Features: {available}")
    print(f"Valid samples: {len(valid)}")
    
    return valid, available

def train_regression_model(X, y, feature_names, horizon_name):
    """
    Train and evaluate a regression model.
    """
    print(f"\n{'='*60}")
    print(f"REGRESSION MODEL: Predicting {horizon_name}")
    print('='*60)
    
    # Standardize features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=0.25, random_state=42
    )
    
    # Try multiple models
    models = {
        'OLS': LinearRegression(),
        'Ridge': Ridge(alpha=1.0),
        'Lasso': Lasso(alpha=0.1),
        'RandomForest': RandomForestRegressor(n_estimators=100, max_depth=5, random_state=42)
    }
    
    results = {}
    
    for name, model in models.items():
        model.fit(X_train, y_train)
        
        # In-sample
        y_pred_train = model.predict(X_train)
        r2_train = r2_score(y_train, y_pred_train)
        
        # Out-of-sample
        y_pred_test = model.predict(X_test)
        r2_test = r2_score(y_test, y_pred_test)
        mae_test = mean_absolute_error(y_test, y_pred_test)
        
        # Cross-validation
        cv_scores = cross_val_score(model, X_scaled, y, cv=5, scoring='r2')
        
        results[name] = {
            'model': model,
            'r2_train': r2_train,
            'r2_test': r2_test,
            'mae_test': mae_test,
            'cv_mean': cv_scores.mean(),
            'cv_std': cv_scores.std()
        }
        
        print(f"\n{name}:")
        print(f"  R² (train): {r2_train:.3f}")
        print(f"  R² (test):  {r2_test:.3f}")
        print(f"  MAE (test): {mae_test:.2f}%")
        print(f"  CV R²: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")
    
    # Get best model by test R²
    best_name = max(results, key=lambda k: results[k]['r2_test'])
    best_model = results[best_name]['model']
    
    print(f"\nBest Model: {best_name}")
    
    # Feature importance
    print(f"\nFeature Coefficients ({best_name}):")
    if hasattr(best_model, 'coef_'):
        coefs = best_model.coef_
    elif hasattr(best_model, 'feature_importances_'):
        coefs = best_model.feature_importances_
    else:
        coefs = [0] * len(feature_names)
    
    importance_df = pd.DataFrame({
        'feature': feature_names,
        'coefficient': coefs
    }).sort_values('coefficient', key=abs, ascending=False)
    
    for _, row in importance_df.iterrows():
        direction = "+" if row['coefficient'] > 0 else "-"
        print(f"  {row['feature']}: {direction}{abs(row['coefficient']):.4f}")
    
    return results, importance_df, scaler

def cluster_analysis(df, feature_cols):
    """
    Cluster bursts to understand which types have predictable effects.
    """
    print(f"\n{'='*60}")
    print("CLUSTER ANALYSIS: Why Do Some Bursts Have Effects?")
    print('='*60)
    
    valid = df[feature_cols + ['ret_60d']].dropna()
    X = valid[feature_cols].values
    y = valid['ret_60d'].values
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # Cluster into 4 groups
    kmeans = KMeans(n_clusters=4, random_state=42, n_init=10)
    valid['cluster'] = kmeans.fit_predict(X_scaled)
    
    # Analyze each cluster
    cluster_stats = []
    
    for c in range(4):
        cluster_data = valid[valid['cluster'] == c]
        
        stats_dict = {
            'cluster': c,
            'n': len(cluster_data),
            'ret_60d_mean': cluster_data['ret_60d'].mean(),
            'ret_60d_std': cluster_data['ret_60d'].std(),
        }
        
        # Characterize cluster
        for feat in feature_cols:
            stats_dict[f'{feat}_mean'] = cluster_data[feat].mean()
        
        cluster_stats.append(stats_dict)
    
    cluster_df = pd.DataFrame(cluster_stats)
    
    print("\nCluster Characteristics:")
    print(cluster_df[['cluster', 'n', 'ret_60d_mean', 'ret_60d_std']].to_string(index=False))
    
    # Identify which clusters are "predictable" (low variance, high/low mean)
    print("\nCluster Interpretation:")
    for _, row in cluster_df.iterrows():
        c = int(row['cluster'])
        n = int(row['n'])
        mean_ret = row['ret_60d_mean']
        std_ret = row['ret_60d_std']
        
        # Characterize by top distinguishing features
        cluster_mask = valid['cluster'] == c
        cluster_data = valid[cluster_mask]
        
        # Find most distinctive features (furthest from overall mean)
        overall_means = valid[feature_cols].mean()
        cluster_means = cluster_data[feature_cols].mean()
        deviations = (cluster_means - overall_means) / valid[feature_cols].std()
        top_features = deviations.abs().sort_values(ascending=False).head(3).index.tolist()
        
        desc = []
        for f in top_features:
            if cluster_means[f] > overall_means[f]:
                desc.append(f"High {f}")
            else:
                desc.append(f"Low {f}")
        
        predictability = abs(mean_ret) / (std_ret + 1e-6)
        
        print(f"\n  Cluster {c} (n={n}):")
        print(f"    Characteristics: {', '.join(desc)}")
        print(f"    60d Return: {mean_ret:+.1f}% ± {std_ret:.1f}%")
        print(f"    Signal/Noise: {predictability:.2f}")
        
        if predictability > 0.5:
            if mean_ret > 0:
                print(f"    → BULLISH CLUSTER (tradeable)")
            else:
                print(f"    → BEARISH CLUSTER (tradeable)")
        else:
            print(f"    → NOISY CLUSTER (not tradeable)")
    
    return cluster_df, valid

def create_scoring_function(importance_df, scaler):
    """
    Create a simple scoring function for real-time use.
    """
    print(f"\n{'='*60}")
    print("SCORING FUNCTION")
    print('='*60)
    
    # Build linear formula
    formula_parts = []
    for _, row in importance_df.iterrows():
        if abs(row['coefficient']) > 0.01:
            sign = "+" if row['coefficient'] > 0 else "-"
            formula_parts.append(f"{sign} {abs(row['coefficient']):.3f} × {row['feature']}")
    
    print("\nPredicted 60d Return = ")
    print("  " + "\n  ".join(formula_parts))
    
    return importance_df

def main():
    print("Phase 77: Predictive Model Construction")
    print("=" * 60)
    
    # Load data
    df = load_data()
    print(f"Loaded {len(df)} bursts")
    
    # Build feature matrix
    valid_df, feature_cols = build_feature_matrix(df)
    
    if len(valid_df) < 50:
        print("Insufficient data for modeling.")
        return
    
    X = valid_df[feature_cols].values
    
    # Train models for each horizon
    all_results = {}
    
    for horizon in ['ret_5d', 'ret_20d', 'ret_60d']:
        y = valid_df[horizon].values
        results, importance, scaler = train_regression_model(X, y, feature_cols, horizon)
        all_results[horizon] = results
    
    # Cluster analysis
    available_for_cluster = [c for c in feature_cols if c in valid_df.columns]
    cluster_df, clustered_data = cluster_analysis(valid_df, available_for_cluster)
    
    # Create scoring function for 60d (best horizon based on prior analysis)
    y_60d = valid_df['ret_60d'].values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    final_model = LinearRegression()
    final_model.fit(X_scaled, y_60d)
    
    importance_df = pd.DataFrame({
        'feature': feature_cols,
        'coefficient': final_model.coef_
    }).sort_values('coefficient', key=abs, ascending=False)
    
    create_scoring_function(importance_df, scaler)
    
    # Plot results
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # Feature importance
    importance_df_sorted = importance_df.sort_values('coefficient')
    colors = ['green' if c > 0 else 'red' for c in importance_df_sorted['coefficient']]
    axes[0, 0].barh(importance_df_sorted['feature'], importance_df_sorted['coefficient'], color=colors)
    axes[0, 0].axvline(0, color='k', linewidth=0.5)
    axes[0, 0].set_xlabel('Coefficient (standardized)')
    axes[0, 0].set_title('Feature Importance: 60d Return Prediction')
    
    # Actual vs Predicted
    y_pred = final_model.predict(X_scaled)
    axes[0, 1].scatter(y_60d, y_pred, alpha=0.5)
    axes[0, 1].plot([-50, 100], [-50, 100], 'r--', label='Perfect prediction')
    axes[0, 1].set_xlabel('Actual 60d Return (%)')
    axes[0, 1].set_ylabel('Predicted 60d Return (%)')
    axes[0, 1].set_title(f'Actual vs Predicted (R²={r2_score(y_60d, y_pred):.3f})')
    axes[0, 1].legend()
    
    # Cluster returns
    cluster_means = cluster_df['ret_60d_mean'].values
    cluster_stds = cluster_df['ret_60d_std'].values
    axes[1, 0].bar(range(4), cluster_means, yerr=cluster_stds, capsize=5)
    axes[1, 0].axhline(0, color='k', linewidth=0.5)
    axes[1, 0].set_xlabel('Cluster')
    axes[1, 0].set_ylabel('60d Return (%)')
    axes[1, 0].set_title('Returns by Burst Cluster')
    
    # Prediction by decile
    valid_df['pred_60d'] = y_pred
    valid_df['pred_decile'] = pd.qcut(valid_df['pred_60d'], 5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'])
    decile_means = valid_df.groupby('pred_decile')['ret_60d'].mean()
    axes[1, 1].bar(range(5), decile_means.values)
    axes[1, 1].set_xticks(range(5))
    axes[1, 1].set_xticklabels(['Q1\n(Bearish)', 'Q2', 'Q3', 'Q4', 'Q5\n(Bullish)'])
    axes[1, 1].axhline(0, color='k', linewidth=0.5)
    axes[1, 1].set_ylabel('Actual 60d Return (%)')
    axes[1, 1].set_title('Actual Returns by Predicted Quintile')
    
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / "predictive_model_results.png", dpi=150)
    print(f"\nSaved: {OUTPUT_DIR / 'predictive_model_results.png'}")
    
    # Final summary
    print("\n" + "="*60)
    print("MODEL SUMMARY")
    print("="*60)
    
    r2 = r2_score(y_60d, y_pred)
    
    print(f"""
Model Performance:
  R² (explained variance): {r2:.3f}
  This means the model explains {r2*100:.1f}% of the variance in 60d returns.

Key Predictors (by importance):
""")
    for i, (_, row) in enumerate(importance_df.head(5).iterrows()):
        effect = "BULLISH" if row['coefficient'] > 0 else "BEARISH"
        print(f"  {i+1}. {row['feature']}: {effect} effect (coef={row['coefficient']:.3f})")
    
    # Quintile spread
    q1_ret = decile_means.iloc[0]
    q5_ret = decile_means.iloc[-1]
    spread = q5_ret - q1_ret
    
    print(f"""
Quintile Analysis:
  Bottom Quintile (bearish predictions): {q1_ret:+.1f}% actual return
  Top Quintile (bullish predictions): {q5_ret:+.1f}% actual return
  Spread: {spread:.1f}%

Is this model tradeable?
""")
    
    if spread > 20:
        print("  ✓ YES - Significant quintile spread suggests exploitable alpha")
    elif spread > 10:
        print("  ~ MAYBE - Modest spread, would need low transaction costs")
    else:
        print("  ✗ NO - Spread too small for practical trading")
    
    # Save model coefficients
    importance_df.to_csv(OUTPUT_DIR / "model_coefficients.csv", index=False)
    
    # Save cluster data
    clustered_data.to_csv(OUTPUT_DIR / "clustered_bursts.csv", index=False)

if __name__ == "__main__":
    main()
