import sys
import subprocess
from pathlib import Path

# Paths
PHASE_DIR = Path(__file__).resolve().parent
# Navigate up to find project root (assuming research/phaseXX/ structure)
PROJECT_ROOT = PHASE_DIR.parent.parent
FETCH_SCRIPT = PROJECT_ROOT / "scripts" / "fetch_manifest.py"
MANIFEST = PHASE_DIR / "manifest.json"

if __name__ == "__main__":
    if not FETCH_SCRIPT.exists():
        print(f"Error: Fetch script not found at {FETCH_SCRIPT}")
        sys.exit(1)
        
    if not MANIFEST.exists():
        print(f"Error: Manifest not found at {MANIFEST}")
        sys.exit(1)

    print(f"--- Downloading Data for {PHASE_DIR.name} ---")
    # Execute shared script with local manifest
    cmd = [sys.executable, str(FETCH_SCRIPT), "--manifest", str(MANIFEST)]
    subprocess.run(cmd, check=True)
