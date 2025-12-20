import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Paths
PHASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PHASE_DIR.parent.parent
FETCH_SCRIPT = PROJECT_ROOT / "scripts" / "fetch_manifest.py"
MANIFEST = PHASE_DIR / "manifest.json"

if __name__ == "__main__":
    load_dotenv()
    if not FETCH_SCRIPT.exists():
        print(f"Error: Fetch script not found at {FETCH_SCRIPT}")
        sys.exit(1)
        
    if not MANIFEST.exists():
        print(f"Error: Manifest not found at {MANIFEST}")
        sys.exit(1)

    print(f"--- Downloading Data for Phase 14 (Genome) ---")
    cmd = [sys.executable, str(FETCH_SCRIPT), "--manifest", str(MANIFEST)]
    subprocess.run(cmd, check=True)
