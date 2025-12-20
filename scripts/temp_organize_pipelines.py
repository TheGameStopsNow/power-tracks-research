import os
import shutil
import json
from pathlib import Path

repo_root = Path(".").resolve()
pipelines_dir = repo_root / "research/pipelines"

pipelines = [
    "01_selectivity",
    "02_clusters_gating",
    "03_portability_temporal",
    "04_options_epd_hip",
    "05_effect_roles",
    "06_risk_execution",
    "07_live_forward"
]

download_data_template = """import sys
from pathlib import Path
from dotenv import load_dotenv

# Add repo root to path to import scripts
repo_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(repo_root))

import scripts.fetch_manifest as fetcher

if __name__ == "__main__":
    load_dotenv()
    print("Fetching data for {phase_name}...")
    fetcher.main()
"""

for p in pipelines:
    p_dir = pipelines_dir / p
    if not p_dir.exists():
        continue
    
    print(f"Organizing {p}...")
    
    # ensure directories
    (p_dir / "data").mkdir(exist_ok=True)
    (p_dir / "output").mkdir(exist_ok=True)
    (p_dir / "docs").mkdir(exist_ok=True)
    (p_dir / "scripts").mkdir(exist_ok=True)
    
    # move files
    for item in os.listdir(p_dir):
        item_path = p_dir / item
        if item_path.is_dir():
            continue
            
        if item.endswith(".json") and item != "manifest.json":
            shutil.move(item_path, p_dir / "output" / item)
        elif item.endswith(".md") and item != "README.md":
            shutil.move(item_path, p_dir / "docs" / item)
        elif item.endswith(".py") and item != "download_data.py" and item != "manifest.json":
            shutil.move(item_path, p_dir / "scripts" / item)
            
    # create manifest if missing
    manifest_path = p_dir / "manifest.json"
    if not manifest_path.exists():
        with open(manifest_path, "w") as f:
            json.dump({"sources": []}, f, indent=2)
            
    # create download_data.py
    dd_path = p_dir / "download_data.py"
    with open(dd_path, "w") as f:
        f.write(download_data_template.format(phase_name=p))

    # check readme
    readme_path = p_dir / "README.md"
    if not readme_path.exists():
        with open(readme_path, "w") as f:
            f.write(f"# {p}\n\n## Goal\nTo be documented.\n\n## Data\nRun `python download_data.py`.\n")
    
    # create .gitignore in data? Checks imply globally ignored.
    
print("Organization complete.")
