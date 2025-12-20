import sys
from pathlib import Path
from dotenv import load_dotenv
import subprocess

# Add repo root to path to import scripts
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(repo_root))

if __name__ == "__main__":
    load_dotenv()
    
    # Run custom historical bars fetcher
    print("Fetching Historical Bars via custom script...")
    script_path = Path(__file__).parent / "scripts" / "fetch_historical_bars.py"
    subprocess.run([sys.executable, str(script_path)], check=True)
