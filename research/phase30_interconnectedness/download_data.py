import sys
from pathlib import Path
from dotenv import load_dotenv

# Add repo root to path to import scripts
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(repo_root))

import scripts.fetch_manifest as fetcher

if __name__ == "__main__":
    load_dotenv() # Load .env variables
    
    phase_dir = Path(__file__).parent
    manifest_path = phase_dir / "manifest.json"
    
    if not manifest_path.exists():
        print(f"Error: Manifest not found at {manifest_path}")
        sys.exit(1)

    print(f"--- Downloading Data for {phase_dir.name} ---")
    sys.argv = ["fetch_manifest.py", "--manifest", str(manifest_path)]
    fetcher.main()
