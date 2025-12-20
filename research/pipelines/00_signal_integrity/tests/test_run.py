import subprocess
from pathlib import Path


def test_signal_integrity_runner():
    repo_root = Path(__file__).resolve().parents[3]
    runner = repo_root / "pipelines" / "00_signal_integrity" / "run.py"
    sample = repo_root / "data" / "samples" / "sample_2024-05-13"

    cmd = ["python3", str(runner), "--sample-dir", str(sample), "--skip-checksums"]
    res = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr or res.stdout
