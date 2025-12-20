#!/usr/bin/env python3
import json
import glob
import os
import numpy as np

def summarize_tisa(pattern):
    files = glob.glob(pattern)
    print(f"Found {len(files)} files for {pattern}")
    all_p = []
    for f in files:
        with open(f, "r") as fp:
            data = json.load(fp)
        # TISA search json doesn't have p-values directly, usually they are in nulls file
        # But wait, tisa_multiscale_search.py outputs best match.
        # tisa_multiscale_nulls.py outputs p-values.
        # Let's look for nulls files.
        pass

def summarize_nulls(pattern):
    files = glob.glob(pattern)
    print(f"Found {len(files)} files for {pattern}")
    all_p = []
    for f in files:
        with open(f, "r") as fp:
            data = json.load(fp)
        for row in data:
            p = row.get("pValue")
            if p is not None:
                all_p.append(p)
    
    if not all_p:
        return "N/A"
    
    # Fraction < 0.01
    frac = sum(1 for p in all_p if p < 0.01) / len(all_p)
    return f"{frac:.1%} (n={len(all_p)})"

def summarize_signatures(pattern):
    files = glob.glob(pattern)
    print(f"Found {len(files)} files for {pattern}")
    all_p = []
    for f in files:
        with open(f, "r") as fp:
            data = json.load(fp)
        for row in data:
            p = row.get("pValue")
            if p is not None:
                all_p.append(p)
    
    if not all_p:
        return "N/A"
    
    # Fraction < 0.01 (Strong Match)
    frac_strong = sum(1 for p in all_p if p < 0.01) / len(all_p)
    # Fraction > 0.10 (No Match)
    frac_weak = sum(1 for p in all_p if p > 0.10) / len(all_p)
    
    return f"Strong: {frac_strong:.1%}, Weak: {frac_weak:.1%} (n={len(all_p)})"

print("--- Raw Shape Match (TISA) ---")
print("GME vs SPY (Cross-Symbol):")
print(summarize_nulls("reports/tisa_multiscale_nulls_GME_vs_SPY_*.json"))

print("\n--- Refined Event Signatures ---")
print("GME vs GME (Baseline):")
print(summarize_signatures("reports/tisa_spike_signatures_GME_vs_GME_*.json"))
print("GME vs SPY (Control):")
print(summarize_signatures("reports/tisa_spike_signatures_GME_vs_SPY_*.json"))
