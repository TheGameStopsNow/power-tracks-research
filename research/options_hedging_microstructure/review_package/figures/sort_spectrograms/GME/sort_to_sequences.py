#!/usr/bin/env python3
"""
Sort spectrogram images from date-based folders into type-based folders
with sequential numbering for After Effects image sequence import.

Structure: GME/<date>/<ImageType>.png  →  GME/sequences/<ImageType>/<NNNNN>.png

Dates are sorted chronologically so frame order = time order.
"""
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).parent  # …/GME/
OUT  = ROOT / "sequences"

# Gather all date folders (directories whose name is purely digits)
date_dirs = sorted(
    d for d in ROOT.iterdir()
    if d.is_dir() and d.name.isdigit()
)

print(f"Found {len(date_dirs)} date folders")

# First pass: discover every unique image filename across all date folders
all_types = set()
for dd in date_dirs:
    for f in dd.iterdir():
        if f.suffix.lower() == ".png":
            all_types.add(f.name)

all_types = sorted(all_types)
print(f"Found {len(all_types)} unique image types:")
for t in all_types:
    print(f"  {t}")

# Sanitise filenames for folder names (remove emoji, em-dash symbols)
def safe_folder_name(filename: str) -> str:
    stem = Path(filename).stem
    # Replace characters that could cause filesystem or AE issues
    stem = stem.replace("🟢", "Calls")
    stem = stem.replace("🔴", "Puts")
    stem = stem.replace(" ", "_")
    stem = stem.replace("—", "-")
    # collapse double underscores
    while "__" in stem:
        stem = stem.replace("__", "_")
    return stem

# Second pass: copy files into sequence folders
copied = 0
skipped = 0
for img_type in all_types:
    folder_name = safe_folder_name(img_type)
    out_dir = OUT / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)
    
    frame = 0
    for dd in date_dirs:
        src = dd / img_type
        if src.exists():
            # Zero-padded 5-digit frame number
            dst = out_dir / f"{frame:05d}.png"
            shutil.copy2(src, dst)
            frame += 1
            copied += 1
        else:
            skipped += 1

    print(f"  {folder_name}: {frame} frames")

print(f"\nDone! Copied {copied} files, skipped {skipped} missing slots.")
print(f"Output: {OUT}")
