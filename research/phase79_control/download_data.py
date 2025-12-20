import sys
from pathlib import Path
from dotenv import load_dotenv

# Add repo root to path to import scripts
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(repo_root))

if __name__ == "__main__":
    load_dotenv()
    
    # Check for Phase 77 output
    phase77_file = repo_root / "research/phase77_greek_echo/output/burst_fingerprints_enhanced.csv"
    
    if phase77_file.exists():
        print(f"Verified dependency: {phase77_file} exists.")
    else:
        print(f"Warning: Dependency {phase77_file} not found. Please run Phase 77 analysis first.")
