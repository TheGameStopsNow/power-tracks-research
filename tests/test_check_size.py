import subprocess
from pathlib import Path


def test_check_size_passes_on_repo():
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "tools" / "check_size.py"
    res = subprocess.run(["python3", str(script), "--limit-mb", "5", "--root", "."], cwd=repo_root)
    assert res.returncode == 0
