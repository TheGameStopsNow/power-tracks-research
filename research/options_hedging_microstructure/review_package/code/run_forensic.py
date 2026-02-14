#!/usr/bin/env python3
"""
run_forensic.py — Streaming wrapper for notebook forensic cells.
Runs shadow_hunter, manipulation_forensic, squeeze_mechanics_forensic,
and counterfactual_analysis with real-time output (no buffering).

Usage:
    python run_forensic.py --script shadow_hunter --ticker GME --event jun2024
    python run_forensic.py --script manipulation_forensic --ticker GME --event jan2021
    python run_forensic.py --script squeeze_mechanics_forensic
    python run_forensic.py --script counterfactual_analysis
"""

import argparse
import sys
import os
from pathlib import Path
import subprocess

CODE_DIR = Path(__file__).resolve().parent

SCRIPTS = {
    "shadow_hunter": "shadow_hunter.py",
    "manipulation_forensic": "manipulation_forensic.py",
    "squeeze_mechanics": "squeeze_mechanics_forensic.py",
    "counterfactual": "counterfactual_analysis.py",
}


def run_streaming(script_name: str, extra_args: list[str] | None = None):
    """Run a script with real-time streaming output."""
    script_path = CODE_DIR / script_name
    if not script_path.exists():
        print(f"ERROR: {script_name} not found at {script_path}")
        return 1

    cmd = [sys.executable, "-u", str(script_path)]  # -u = unbuffered
    if extra_args:
        cmd.extend(extra_args)

    print(f"▶ Running: {script_path.name} {' '.join(extra_args or [])}")
    print(f"  (streaming output below)\n{'─' * 60}\n")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # merge stderr into stdout
        text=True,
        cwd=str(CODE_DIR),
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )

    for line in proc.stdout:
        print(line, end="", flush=True)

    proc.wait()

    print(f"\n{'─' * 60}")
    if proc.returncode == 0:
        print(f"✅ {script_path.name} completed successfully.")
    else:
        print(f"❌ {script_path.name} exited with code {proc.returncode}")

    return proc.returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Streaming forensic runner")
    parser.add_argument("--script", required=True, choices=list(SCRIPTS.keys()))
    parser.add_argument("--ticker", default="GME")
    parser.add_argument("--event", choices=["jan2021", "jun2024", "both"], default=None)
    args = parser.parse_args()

    script_file = SCRIPTS[args.script]
    extra = ["--ticker", args.ticker]
    if args.event:
        extra.extend(["--event", args.event])

    rc = run_streaming(script_file, extra)
    sys.exit(rc)
