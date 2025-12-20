import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Add repo root to path
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(repo_root))

if __name__ == "__main__":
    load_dotenv()
    
    # 1. Fetch Bars
    print("Step 1: Fetching NVDA Bars...")
    script_path_1 = Path(__file__).parent / "scripts" / "fetch_nvda_bars.py"
    subprocess.run([sys.executable, str(script_path_1)], check=False)
    
    # 2. Fetch OPRA
    print("\nStep 2: Fetching NVDA OPRA Trades (Theta)...")
    script_path_2 = Path(__file__).parent / "scripts" / "fetch_opra_nvda.py"
    subprocess.run([sys.executable, str(script_path_2)], check=False)
