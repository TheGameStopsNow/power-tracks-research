#!/usr/bin/env python3
from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.loader import load_all_venues_summary, get_sample_dirs

def check():
    sample_dirs = get_sample_dirs()
    may13 = next((d for d in sample_dirs if "2024-05-13" in d.name), None)
    
    if may13:
        print(f"Checking venues for {may13.name}...")
        summary = load_all_venues_summary(may13)
        print(summary)
    else:
        print("May 13 sample not found")

if __name__ == "__main__":
    check()
