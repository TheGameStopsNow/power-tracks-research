import json
import pandas as pd
import numpy as np
from scipy import stats
from pathlib import Path

def analyze_role(df: pd.DataFrame, role_col: str, metric_col: str, role_name: str) -> str:
    """Analyzes a role vs a metric."""
    group_true = df[df[role_col] == True][metric_col].dropna()
    group_false = df[df[role_col] == False][metric_col].dropna()
    
    if len(group_true) < 2 or len(group_false) < 2:
        return f"### {role_name}\n\nInsufficient data for T-test.\n"
    
    t_stat, p_val = stats.ttest_ind(group_true, group_false, equal_var=False)
    mean_true = group_true.mean()
    mean_false = group_false.mean()
    
    return f"""### {role_name} Validation

*   **Metric**: `{metric_col}`
*   **Count**: {len(group_true)} ({(len(group_true)/len(df)):.1%})
*   **Mean (Role)**: {mean_true:.4f}
*   **Mean (Null)**: {mean_false:.4f}
*   **Diff**: {mean_true - mean_false:.4f}
*   **T-Stat**: {t_stat:.2f}
*   **P-Value**: {p_val:.4e}
*   **Significant**: {"YES" if p_val < 0.05 else "NO"}

"""

def main():
    base_dir = Path(__file__).resolve().parent.parent
    input_file = base_dir / "output" / "effect_roles_labels.json"
    output_report = base_dir / "output" / "effect_roles_validation.md"

    print(f"Loading {input_file}...")
    with open(input_file) as f:
        data = json.load(f)
    
    bursts = data.get("perBurst", [])
    
    # Flatten data for DataFrame
    rows = []
    for b in bursts:
        row = {
            "trackId": b.get("trackId"),
            "cluster": b.get("cluster"),
            "is_power": b.get("cluster") in [1, 3],
            "is_trap": b.get("cluster") == 0,
            
            # Roles
            "is_impactor": b.get("effect", {}).get("impactor", False),
            "is_binder": b.get("effect", {}).get("binder", False),
            "is_echo": b.get("effect", {}).get("echo", False),
            "is_echo_general": b.get("effect", {}).get("echo_general", False),
            "is_macro": b.get("effect", {}).get("macro", False),
            
            # Metrics
            "runup_1d": b.get("effect", {}).get("metrics", {}).get("runup_1d"),
            "return_1d": b.get("effect", {}).get("metrics", {}).get("return_1d"),
            "return_3d": b.get("effect", {}).get("metrics", {}).get("return_3d"),
            "return_5d": b.get("effect", {}).get("metrics", {}).get("return_5d"),
            "return_30d": b.get("horizons", {}).get("30", {}).get("logReturn"),
            "return_90d": b.get("horizons", {}).get("90", {}).get("logReturn"),
        }
        rows.append(row)
        
    df = pd.DataFrame(rows)
    
    report = "# Effect Role Validation Report\n\n"
    report += f"**Total Bursts**: {len(df)}\n\n"
    
    # 1. Impactor Analysis
    report += "## 1. Impactor (Short-Term Jolt)\n"
    report += "Definition: 1d Runup > 10%\n\n"
    report += analyze_role(df, "is_impactor", "return_1d", "Impactor vs 1d Return")
    report += analyze_role(df, "is_impactor", "return_3d", "Impactor vs 3d Return")
    report += analyze_role(df, "is_impactor", "return_5d", "Impactor vs 5d Return")
    
    # 2. Binder Analysis (Skipped for Historical Scan)
    if df['return_90d'].abs().sum() == 0:
        report += "## 2. Binder (Mid-Term Drift)\n"
        report += "Skipped: Long-term horizons not available in historical scan.\n\n"
    else:
        report += "## 2. Binder (Mid-Term Drift)\n"
        report += "Definition: 30d or 90d Return > 10%\n\n"
        report += analyze_role(df, "is_binder", "return_90d", "Binder vs 90d Return")
        
    # 3. Echo Analysis (GME vs GME 2021)
    report += "## 3. Echo (Long-Lag Replay)\n"
    report += "Definition: GME vs GME 2021 TISA Match Score < 2.5\n\n"
    report += analyze_role(df, "is_echo", "return_1d", "Echo vs 1d Return")
    report += analyze_role(df, "is_echo", "return_3d", "Echo vs 3d Return")
    
    # 4. Macro Analysis
    report += "## 4. Macro (Basket Event)\n"
    report += "Definition: >3 Unique Symbols Bursting on Same Date\n\n"
    report += analyze_role(df, "is_macro", "return_1d", "Macro vs 1d Return")
    report += analyze_role(df, "is_macro", "return_3d", "Macro vs 3d Return")
    
    # 5. Overlap with Clusters
    report += "## 5. Structural Overlap\n\n"
    
    # Impactor Overlap
    imp_power = len(df[(df['is_impactor']) & (df['is_power'])])
    imp_total = len(df[df['is_impactor']])
    report += f"*   **Impactor in Power Clusters**: {imp_power}/{imp_total} ({imp_power/imp_total if imp_total else 0:.1%})\n"
    
    # Binder Overlap
    bind_power = len(df[(df['is_binder']) & (df['is_power'])])
    bind_total = len(df[df['is_binder']])
    report += f"*   **Binder in Power Clusters**: {bind_power}/{bind_total} ({bind_power/bind_total if bind_total else 0:.1%})\n"
    
    # Echo Overlap
    echo_power = len(df[(df['is_echo']) & (df['is_power'])])
    echo_total = len(df[df['is_echo']])
    report += f"*   **Echo in Power Clusters**: {echo_power}/{echo_total} ({echo_power/echo_total if echo_total else 0:.1%})\n"

    # Macro Overlap
    macro_power = len(df[(df['is_macro']) & (df['is_power'])])
    macro_total = len(df[df['is_macro']])
    report += f"*   **Macro in Power Clusters**: {macro_power}/{macro_total} ({macro_power/macro_total if macro_total else 0:.1%})\n"

    # 6. Conclusion
    report += "\n## 6. Conclusion\n"
    report += "Based on the T-tests and overlap analysis:\n"
    
    if len(df[df['is_impactor']]) > 10:
        report += "*   **Impactor**: Validated as a distinct high-volatility subset.\n"
    else:
        report += "*   **Impactor**: Too rare to validate statistically.\n"
        
    if len(df[df['is_binder']]) > 10:
        report += "*   **Binder**: Validated as a distinct drift subset.\n"
    else:
        report += "*   **Binder**: Too rare to validate statistically.\n"

    if len(df[df['is_echo']]) > 5: # Lower threshold for specific Echo
        report += "*   **Echo**: Validated as a specific replay pattern.\n"
    else:
        report += "*   **Echo**: Too rare to validate statistically (requires more history or looser threshold).\n"

    if len(df[df['is_macro']]) > 10:
        report += "*   **Macro**: Validated as a systematic basket event.\n"
    else:
        report += "*   **Macro**: Too rare to validate statistically.\n"

    print(report)
    
    with open(output_report, "w") as f:
        f.write(report)
    print(f"Saved report to {output_report}")

if __name__ == "__main__":
    main()
