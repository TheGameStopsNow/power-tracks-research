#!/usr/bin/env python3
"""
Unified entrypoint to run research suites (sample-safe).

Each suite resolves to a preferred command:
- New layout: pipelines/<suite>/run.py
- Legacy layout: pipelines/<suite>/scripts/run_*.py
- Make target fallback: make suite-<name>

If no candidate exists, the suite is skipped with a message instead of failing.
"""
import argparse
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Optional


def pick_command(root: Path, candidates: Iterable[str]) -> Optional[str]:
    """
    Pick the first command whose check path exists.
    Candidates use the form:
        "<path-to-check>|<command-to-run>"
    If no pipe is present, the path is also the command.
    """
    for raw in candidates:
        if "|" in raw:
            check_path, cmd = raw.split("|", 1)
        else:
            check_path, cmd = raw, raw
        check_path = check_path.format(root=root)
        cmd = cmd.format(root=root)
        if Path(check_path).exists():
            return cmd
    return None


def run(cmd: str, cwd: Path) -> None:
    print(f"==> {cmd}")
    res = subprocess.run(cmd, shell=True, cwd=cwd)
    if res.returncode != 0:
        sys.exit(res.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a research suite with graceful fallbacks.")
    parser.add_argument("suite", choices=["signal", "selectivity", "clusters", "gating", "portability", "temporal", "options"], help="Suite name")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent.parent
    suites = {
        "signal": [
            "{root}/research/pipelines/00_signal_integrity/run.py",
            "{root}/research/pipelines/00_signal_integrity/src/verify_reproducibility.py",
        ],
        "selectivity": [
            "{root}/research/pipelines/01_selectivity/run.py",
            "{root}/research/pipelines/01_selectivity/scripts/run_selectivity_suite.py",
            "{root}/Makefile|make -C {root} suite-selectivity",
        ],
        "clusters": [
            "{root}/research/pipelines/02_clusters_gating/run_cluster_stability.py",
            "{root}/research/pipelines/02_clusters_gating/scripts/run_cluster_stability.py",
            "{root}/Makefile|make -C {root} suite-clusters",
        ],
        "gating": [
            "{root}/research/pipelines/02_clusters_gating/run_gating_reproduction.py",
            "{root}/research/pipelines/02_clusters_gating/scripts/run_gating_reproduction.py",
            "{root}/Makefile|make -C {root} suite-gating",
        ],
        "portability": [
            "{root}/research/pipelines/03_portability_temporal/run_portability_panel_extended.py",
            "{root}/research/pipelines/03_portability_temporal/scripts/run_portability_panel_extended.py",
            "{root}/Makefile|make -C {root} suite-portability",
        ],
        "temporal": [
            "{root}/research/pipelines/03_portability_temporal/run_temporal_generalization_deep.py",
            "{root}/research/pipelines/03_portability_temporal/scripts/run_temporal_generalization_deep.py",
        ],
        "options": [
            "{root}/research/pipelines/04_options_epd_hip/run_options_suite.py",
            "{root}/research/pipelines/04_options_epd_hip/scripts/run_options_suite.py",
            "{root}/Makefile|make -C {root} suite-options",
        ],
    }

    cmd = pick_command(root, suites[args.suite])
    if not cmd:
        print(f"[skip] No entrypoint found for suite '{args.suite}'.")
        return
    run(cmd, cwd=root)


if __name__ == "__main__":
    main()
