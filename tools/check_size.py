#!/usr/bin/env python3
"""
Fail if large files are present in tracked paths.

Allowed large paths (ignored):
- data/samples/local/*
- data/raw/*
- data/tmp/*
- artifacts/*

Default limit: 5 MB per file.
"""
import argparse
import os
from pathlib import Path


ALLOW_DIRS = {
    "data/samples/local",
    "data/raw",
    "data/tmp",
    "artifacts",
}


def is_allowed(path: Path) -> bool:
    for allow in ALLOW_DIRS:
        if allow in path.as_posix().split("/"):
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Check for large files in tracked paths.")
    parser.add_argument("--limit-mb", type=int, default=5, help="Per-file size limit in MB (default: 5).")
    parser.add_argument("--root", default=".", help="Repo root to scan.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    limit_bytes = args.limit_mb * 1024 * 1024
    offenders = []

    for dirpath, dirnames, filenames in os.walk(root):
        # skip hidden/system dirs
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in {".git", "__pycache__"}]
        for name in filenames:
            path = Path(dirpath) / name
            rel = path.relative_to(root)
            if is_allowed(rel):
                continue
            size = path.stat().st_size
            if size > limit_bytes:
                offenders.append((rel, size))

    if offenders:
        print("Found files exceeding limit:")
        for rel, size in offenders:
            print(f"- {rel} ({size/1024/1024:.2f} MB)")
        raise SystemExit(1)
    print("Size check passed.")


if __name__ == "__main__":
    main()
