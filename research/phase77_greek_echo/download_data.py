import sys
from pathlib import Path
from dotenv import load_dotenv

# Add repo root to path to import scripts
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(repo_root))

if __name__ == "__main__":
    load_dotenv()
    print("Phase 77 relies on data from Phase 75 (OPRA Ticks).")
    print("Please ensure Phase 75 'download_data.py' has been run.")
    print("No additional raw data download required for Phase 77.")
