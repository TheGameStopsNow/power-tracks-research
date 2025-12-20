
#!/usr/bin/env python3
"""
Reproduction Harness (Study J).
Standardized execution environment for all validation studies.
Ensures inputs/outputs are tracked and runs are reproducible.
"""

import argparse
import json
import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path

# Study Registry
STUDIES = {
    "A": {
        "name": "Selectivity Retest",
        "script": "scripts/run_selectivity_retest.py",
        "desc": "K-Spike Selectivity vs Controls"
    },
    "B": {
        "name": "Cluster Robustness",
        "script": "scripts/run_cluster_robustness.py",
        "desc": "Cluster 1/3 Stability"
    },
    "C": {
        "name": "Gate Efficacy",
        "script": "scripts/run_gating_reproduction.py",
        "desc": "Gated vs Component Performance"
    },
    "D": {
        "name": "Portability Panel",
        "script": "scripts/run_portability_panel.py",
        "desc": "Cross-Symbol Decay"
    },
    "E": {
        "name": "Temporal Generalization",
        "script": "scripts/run_temporal_generalization.py",
        "desc": "2021/2024/2025 Stability"
    },
    "F": {
        "name": "Basket Dynamics",
        "script": "scripts/run_basket_dynamics.py",
        "desc": "Lead-Lag Hierarchy"
    },
    "G": {
        "name": "Options Pinning",
        "script": "scripts/run_options_suite.py",
        "args": ["--mode", "pinning"],
        "desc": "Daily Gamma Pinning"
    },
    "H": {
        "name": "Options HIP",
        "script": "scripts/run_options_suite.py",
        "args": ["--mode", "hip"],
        "desc": "Intraday Flow Causality"
    },
    # Phase 2: Scientific Stress-Test
    "1.1": {
        "name": "Selectivity Re-confirmation",
        "script": "scripts/run_selectivity_suite.py",
        "desc": "Stricter nulls, extended panel (QQQ, DIA, PLTR)"
    },
    "1.2": {
        "name": "Cluster Stability",
        "script": "scripts/run_cluster_stability.py",
        "desc": "Bootstrap validation of Clusters 1 & 3"
    },
    "1.3": {
        "name": "Gating Efficacy & Holdout",
        "script": "scripts/run_gating_holdout.py",
        "desc": "Unseen data validation"
    },
    "2.1": {
        "name": "Full Portability Panel",
        "script": "scripts/run_portability_panel_extended.py",
        "desc": "Extended universe/regimes"
    },
    "2.2": {
        "name": "Timelessness Deep Dive",
        "script": "scripts/run_temporal_generalization_deep.py",
        "desc": "KS tests 2021 vs 2024"
    },
    "3.1": {
        "name": "Pinning Robustness",
        "script": "scripts/run_pinning_robustness.py",
        "desc": "Multi-date/symbol replication"
    },
    "3.2": {
        "name": "HIP Intraday Flow",
        "script": "scripts/run_hip_panel.py",
        "desc": "Causality across multiple days"
    },
    "4.1": {
        "name": "Execution & Slippage",
        "script": "scripts/run_execution_sim.py",
        "desc": "Realistic P&L sim"
    },
    "4.2": {
        "name": "Risk & Tail Behavior",
        "script": "scripts/run_risk_analysis.py",
        "desc": "Drawdown stress test"
    }
}

def run_study(study_id, dry_run=False):
    if study_id not in STUDIES:
        print(f"Error: Unknown Study ID '{study_id}'")
        return False
        
    study = STUDIES[study_id]
    print(f"=== Study {study_id}: {study['name']} ===")
    print(f"Description: {study['desc']}")
    
    # Construct Command
    cmd = ["python3", study["script"]]
    if "args" in study:
        cmd.extend(study["args"])
        
    print(f"Command: {' '.join(cmd)}")
    
    if dry_run:
        return True
        
    # Execution
    start_time = datetime.now()
    try:
        # Ensure script exists
        if not os.path.exists(study["script"]):
             print(f"Error: Script {study['script']} not found. Please implement it first.")
             return False

        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("Status: SUCCESS")
        print(result.stdout)
        
        # Manifest
        manifest = {
            "study_id": study_id,
            "name": study["name"],
            "timestamp": start_time.isoformat(),
            "duration_seconds": (datetime.now() - start_time).total_seconds(),
            "command": " ".join(cmd),
            "status": "SUCCESS"
        }
        
        manifest_path = f"reports/manifest_{study_id}_{start_time.strftime('%Y%m%d_%H%M%S')}.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"Manifest saved to {manifest_path}")
        return True
        
    except subprocess.CalledProcessError as e:
        print("Status: FAILED")
        print(e.stderr)
        return False

def main():
    parser = argparse.ArgumentParser(description="Validation Suite Harness")
    parser.add_argument("study_id", help="Study ID (A-H)")
    parser.add_argument("--dry-run", action="store_true", help="Print command only")
    args = parser.parse_args()
    
    run_study(args.study_id.upper(), args.dry_run)

if __name__ == "__main__":
    main()
