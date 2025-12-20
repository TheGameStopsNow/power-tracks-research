import sys
from pathlib import Path
from dotenv import load_dotenv

# Add repo root to path to import scripts
repo_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(repo_root))

import scripts.fetch_manifest as fetcher

if __name__ == "__main__":
    load_dotenv()
    pipeline_name = Path(__file__).parent.name
    print(f"Fetching data for {pipeline_name}...")
    
    # Point to local manifest
    manifest_path = Path(__file__).parent / "manifest.json"
    # Override sys.argv
    sys.argv = [sys.argv[0], "--manifest", str(manifest_path)]
    
    fetcher.main()
