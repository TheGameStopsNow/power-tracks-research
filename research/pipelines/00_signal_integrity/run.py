#!/usr/bin/env python3
"""
Signal Integrity Suite Runner

Runs the reproducibility check on a sample dataset. Designed to be a simple
entry point for newcomers: point at a sample directory and it will invoke
the existing verification script.
"""
import argparse
import subprocess
from pathlib import Path
from typing import List


def build_command(sample_dir: Path, manifest: Path | None, sha256: Path | None, output: Path | None, skip_checksums: bool) -> List[str]:
    script = Path(__file__).parent / "src" / "verify_reproducibility.py"
    cmd: List[str] = ["python3", str(script), "--sample-dir", str(sample_dir)]
    if manifest:
        cmd += ["--manifest", str(manifest)]
    if sha256:
        cmd += ["--sha256", str(sha256)]
    if output:
        cmd += ["--output", str(output)]
    if skip_checksums:
        cmd += ["--no-checksums"]
    return cmd


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Signal Integrity reproducibility suite on a sample dataset.")
    parser.add_argument(
        "--sample-dir",
        type=Path,
        default=Path("data/samples/sample_2024-05-13"),
        help="Path to sample dataset directory (default: data/samples/sample_2024-05-13)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional manifest JSON path (defaults to <sample-dir>/MANIFEST.json if present)",
    )
    parser.add_argument(
        "--sha256",
        type=Path,
        default=None,
        help="Optional SHA256SUMS path (defaults to <sample-dir>/SHA256SUMS if present)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output JSON report path",
    )
    parser.add_argument(
        "--skip-checksums",
        action="store_true",
        help="Skip checksum verification (useful if you only need structure checks).",
    )
    args = parser.parse_args()

    sample_dir = args.sample_dir
    manifest = args.manifest or (sample_dir / "MANIFEST.json" if (sample_dir / "MANIFEST.json").exists() else None)
    sha256 = args.sha256 or (sample_dir / "SHA256SUMS" if (sample_dir / "SHA256SUMS").exists() else None)

    cmd = build_command(sample_dir, manifest, sha256, args.output, args.skip_checksums)
    print("==> Running signal integrity suite")
    print(" ".join(cmd))
    res = subprocess.run(cmd, cwd=Path(__file__).parent, text=True)
    if res.returncode != 0:
        raise SystemExit(res.returncode)


if __name__ == "__main__":
    main()
