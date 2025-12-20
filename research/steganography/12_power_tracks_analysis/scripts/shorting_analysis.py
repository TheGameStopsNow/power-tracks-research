#!/usr/bin/env python3
"""
Cluster 0 Shorting Strategy Analysis
=====================================

If Cluster 0 has -31.9% mean return, can we profit by SHORTING it?

Key questions:
1. How consistent is the decline? (variance matters for shorts)
2. What's the max runup BEFORE the decline? (key risk for shorts)
3. What's the timing? (when does the decline happen?)
4. What would the P&L look like with realistic position sizing?
"""

import sys
from pathlib import Path
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from scipy import stats

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "reports"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "results"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("CLUSTER 0 SHORTING STRATEGY ANALYSIS")
    print("Can we profit by shorting the 'Trap' cluster?")
    print("=" * 70)
    
    # Load clustered data
    clustered_file = DATA_DIR / "forward_returns_midterm_GME_clustered.json"
    if not clustered_file.exists():
        print(f"Data file not found: {clustered_file}")
        return
    
    with open(clustered_file) as f:
        data = json.load(f)
    
    bursts = data.get("perBurst", [])
    print(f"\nTotal bursts: {len(bursts)}")
    
    # Separate by cluster
    cluster_0 = [b for b in bursts if b.get("cluster") == 0]
    cluster_1 = [b for b in bursts if b.get("cluster") == 1]
    cluster_3 = [b for b in bursts if b.get("cluster") == 3]
    
    print(f"Cluster 0 (Trap): {len(cluster_0)}")
    print(f"Cluster 1 (Power A): {len(cluster_1)}")
    print(f"Cluster 3 (Power B): {len(cluster_3)}")
    
    # ============================================================
    # SHORTING ANALYSIS FOR CLUSTER 0
    # ============================================================
    print("\n" + "=" * 70)
    print("CLUSTER 0 SHORTING ANALYSIS")
    print("=" * 70)
    
    c0_returns = [b["horizons"]["30"]["logReturn"] for b in cluster_0 if "horizons" in b and "30" in b["horizons"]]
    c0_runups = [b["horizons"]["30"]["maxRunup"] for b in cluster_0 if "horizons" in b and "30" in b["horizons"]]
    c0_drawdowns = [b["horizons"]["30"]["maxDrawdown"] for b in cluster_0 if "horizons" in b and "30" in b["horizons"]]
    
    if not c0_returns:
        print("No return data found")
        return
    
    # Key metrics
    mean_return = np.mean(c0_returns)
    std_return = np.std(c0_returns)
    median_return = np.median(c0_returns)
    
    mean_runup = np.mean(c0_runups)
    max_runup = max(c0_runups)
    
    mean_drawdown = np.mean(c0_drawdowns)
    max_drawdown = min(c0_drawdowns)
    
    print(f"\n30-Day Horizon Statistics (Cluster 0):")
    print(f"  Mean Return: {mean_return:.1%}")
    print(f"  Median Return: {median_return:.1%}")
    print(f"  Std Dev: {std_return:.1%}")
    print(f"  ")
    print(f"  MAX RUNUP (shorts fear this): {max_runup:.1%}")
    print(f"  Mean Runup: {mean_runup:.1%}")
    print(f"  ")
    print(f"  Max Drawdown: {max_drawdown:.1%}")
    print(f"  Mean Drawdown: {mean_drawdown:.1%}")
    
    # ============================================================
    # SHORTING VIABILITY
    # ============================================================
    print("\n" + "=" * 70)
    print("SHORTING VIABILITY")
    print("=" * 70)
    
    # Key risk for shorts: max runup before decline
    # If you short at signal and it runs up 46% first, you're margin called
    
    # Win rate if you short and hold 30 days
    short_wins = sum(1 for r in c0_returns if r < 0)  # Negative return = short wins
    short_win_rate = short_wins / len(c0_returns)
    
    # Expected value calculation for shorts
    # Short return = -log_return (if stock goes down 30%, short gains 30%)
    short_returns = [-r for r in c0_returns]
    short_mean = np.mean(short_returns)
    short_sharpe = short_mean / np.std(short_returns) if np.std(short_returns) > 0 else 0
    
    print(f"\nIf you SHORT every Cluster 0:")
    print(f"  Win Rate: {short_win_rate:.1%}")
    print(f"  Mean Short Return: {short_mean:.1%}")
    print(f"  Sharpe Ratio: {short_sharpe:.2f}")
    print(f"  ")
    print(f"  ⚠️ MAX ADVERSE EXCURSION: {max_runup:.1%}")
    print(f"  This is the WORST case: stock runs UP {max_runup:.0%} before falling")
    
    # Risk-adjusted sizing
    kelly_fraction = (short_win_rate - (1 - short_win_rate) / (short_mean / 0.3)) if short_mean > 0 else 0
    
    print(f"\nRisk Considerations:")
    print(f"  Kelly Fraction: {kelly_fraction:.1%}")
    print(f"  To survive max runup, need: {1/max_runup:.1%}x leverage max")
    
    # ============================================================
    # PROFITABLE SHORTING SCENARIOS
    # ============================================================
    print("\n" + "=" * 70)
    print("PROFITABLE SHORTING SCENARIOS")
    print("=" * 70)
    
    # Scenario 1: Wait for runup, THEN short
    # Look at bursts where runup happened BEFORE drawdown
    runup_first = []
    for b in cluster_0:
        if "horizons" not in b or "30" not in b["horizons"]:
            continue
        runup = b["horizons"]["30"]["maxRunup"]
        drawdown = b["horizons"]["30"]["maxDrawdown"]
        final = b["horizons"]["30"]["logReturn"]
        
        # If runup > 10% and final return is negative, runup happened first
        if runup > 0.1 and final < 0:
            runup_first.append({"runup": runup, "final": final})
    
    print(f"\nScenario 1: Wait for 10%+ runup, then short")
    print(f"  Opportunities: {len(runup_first)}/{len(cluster_0)}")
    if runup_first:
        mean_profit = np.mean([-r["final"] for r in runup_first])
        print(f"  Mean profit (short after runup): {mean_profit:.1%}")
    
    # Scenario 2: Compare with NOT shorting Power clusters
    c1_returns = [b["horizons"]["30"]["logReturn"] for b in cluster_1 if "horizons" in b and "30" in b["horizons"]]
    c3_returns = [b["horizons"]["30"]["logReturn"] for b in cluster_3 if "horizons" in b and "30" in b["horizons"]]
    
    print(f"\nScenario 2: Long Cluster 1/3, Short Cluster 0")
    if c1_returns and c3_returns:
        power_mean = np.mean(c1_returns + c3_returns)
        trap_mean = mean_return
        spread = -trap_mean - power_mean  # Short trap, long power
        print(f"  Power Clusters Mean: {power_mean:.1%}")
        print(f"  Trap Cluster Mean: {trap_mean:.1%}")
        print(f"  Long/Short Spread: {spread:.1%}")
    
    # ============================================================
    # CONCLUSION
    # ============================================================
    print("\n" + "=" * 70)
    print("CONCLUSION")
    print("=" * 70)
    
    if short_win_rate > 0.6 and max_runup < 0.5:
        print("✅ SHORTING CLUSTER 0 IS VIABLE")
        print(f"   Win rate: {short_win_rate:.1%}")
        print(f"   Manageable runup risk: {max_runup:.1%}")
    elif short_win_rate > 0.6:
        print("⚠️ SHORTING IS VIABLE BUT RISKY")
        print(f"   Win rate is good: {short_win_rate:.1%}")
        print(f"   BUT max runup is dangerous: {max_runup:.1%}")
        print(f"   Strategy: Wait for runup before entry")
    else:
        print("❌ SHORTING NOT RECOMMENDED")
        print(f"   Win rate too low: {short_win_rate:.1%}")
    
    # Save results
    results = {
        "cluster_0_count": len(cluster_0),
        "mean_return": mean_return,
        "std_return": std_return,
        "short_win_rate": short_win_rate,
        "mean_short_return": short_mean,
        "max_runup_risk": max_runup,
        "mean_runup_risk": mean_runup,
        "sharpe_ratio": short_sharpe,
        "recommendation": "VIABLE_BUT_RISKY" if short_win_rate > 0.6 else "NOT_RECOMMENDED"
    }
    
    with open(OUTPUT_DIR / "shorting_analysis.json", "w") as f:
        json.dump(results, f, indent=2)
    
    with open(OUTPUT_DIR / "shorting_analysis_report.md", "w") as f:
        f.write("# Cluster 0 Shorting Strategy Analysis\n\n")
        f.write(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")
        f.write("## Can We Profit by Shorting the Trap?\n\n")
        f.write(f"| Metric | Value |\n")
        f.write(f"|--------|-------|\n")
        f.write(f"| Cluster 0 Count | {len(cluster_0)} |\n")
        f.write(f"| Mean Return (long) | {mean_return:.1%} |\n")
        f.write(f"| Short Win Rate | {short_win_rate:.1%} |\n")
        f.write(f"| Mean Short Return | {short_mean:.1%} |\n")
        f.write(f"| ⚠️ Max Runup Risk | {max_runup:.1%} |\n")
        f.write(f"| Sharpe Ratio | {short_sharpe:.2f} |\n\n")
        
        f.write("## Key Risk\n\n")
        f.write(f"> **Max Runup: {max_runup:.0%}** - Stock may rally {max_runup:.0%} before crashing\n\n")
        f.write("This means you need to either:\n")
        f.write("1. Wait for the spike before shorting\n")
        f.write("2. Size positions to survive a temporary {:.0f}% loss\n\n".format(max_runup * 100))
        
        f.write("## Recommendation\n\n")
        if short_win_rate > 0.6:
            f.write(f"> ⚠️ **VIABLE BUT RISKY**\n\n")
            f.write("Shorting Cluster 0 has positive expected value, but requires:\n")
            f.write("- Patience to wait for the initial spike\n")
            f.write("- Conservative position sizing\n")
            f.write("- Stop losses above recent highs\n")
        else:
            f.write("> ❌ **NOT RECOMMENDED**\n")
    
    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
