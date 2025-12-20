import subprocess
from pathlib import Path


def test_run_suite_skips_cleanly():
    repo_root = Path(__file__).resolve().parents[1]
    runner = repo_root / "pipelines" / "run_suite.py"
    suites = ["selectivity", "clusters", "gating", "portability", "temporal", "options", "risk"]
    for suite in suites:
        cmd = ["python3", str(runner), suite]
        res = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
        # Either it finds an entrypoint (return 0) or cleanly skips (also 0)
        assert res.returncode == 0, f"{suite} failed: {res.stderr}"
        assert "[skip]" in res.stdout or "==>" in res.stdout
