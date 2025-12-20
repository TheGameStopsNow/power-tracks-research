import sys
from pathlib import Path
from dotenv import load_dotenv
import subprocess

# Add repo root to path to import scripts
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(repo_root))

import scripts.fetch_manifest as fetcher

if __name__ == "__main__":
    load_dotenv()
    
    # 1. Run standard manifest fetch (if any)
    # fetcher.main() 
    
    # 2. Run custom OPRA fetcher
    print("Fetching OPRA data via custom script...")
    script_path = Path(__file__).parent / "scripts" / "fetch_opra_polygon.py"
    subprocess.run([sys.executable, str(script_path)], check=True)
