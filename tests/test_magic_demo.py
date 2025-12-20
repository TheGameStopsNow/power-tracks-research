import subprocess
from pathlib import Path


def test_magic_demo_runs(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "getting-started" / "00_magic_demo.py"
    output = tmp_path / "demo.png"
    sample = repo_root / "data" / "samples" / "micro" / "price_paths.csv"

    cmd = [
        "python3",
        str(script),
        "--input",
        str(sample),
        "--rows",
        "200",
        "--output",
        str(output),
    ]
    res = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
    assert res.returncode == 0, res.stderr or res.stdout
    assert output.exists()
