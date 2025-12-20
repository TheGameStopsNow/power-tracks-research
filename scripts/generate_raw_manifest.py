#!/usr/bin/env python3
import json
from datetime import datetime
from pathlib import Path
import re

BASE_DIR = Path(__file__).resolve().parent.parent
MANIFEST_PATH = BASE_DIR / "docs" / "raw_data_manifest.json"
TARGET_DIRS = [
    BASE_DIR / "pipelines" / "00_signal_integrity" / "bars",
    BASE_DIR / "pipelines" / "00_signal_integrity" / "bars_range",
    BASE_DIR / "pipelines" / "00_signal_integrity" / "test_ticks",
    BASE_DIR / "pipelines" / "00_signal_integrity" / "test-data",
    BASE_DIR / "pipelines" / "00_signal_integrity" / "features",
]

def parse_filename(path: Path):
    match = re.match(r"(?P<symbol>[A-Z]+)_(?P<date>\d{4}-\d{2}-\d{2})", path.name)
    if not match:
        return None
    symbol = match.group("symbol")
    date = match.group("date")
    return symbol, date

def infer_window(date_str: str):
    d = datetime.fromisoformat(date_str)
    start = d.replace(hour=13, minute=0, second=0)
    end = d.replace(hour=20, minute=0, second=0)
    return start.isoformat() + "Z", end.isoformat() + "Z"

def main():
    entries = []
    for target_dir in TARGET_DIRS:
        if not target_dir.exists():
            continue
        for path in sorted(target_dir.iterdir()):
            if path.is_file():
                parsed = parse_filename(path)
                if not parsed:
                    continue
                symbol, date = parsed
                start, end = infer_window(date)
                entries.append({
                    "provider": "polygon",
                    "api": "trades",
                    "symbol": symbol,
                    "date": date,
                    "start": start,
                    "end": end,
                    "venue": "all",
                    "dest": str(path.relative_to(BASE_DIR)),
                    "notes": f"Recreate {path.relative_to(BASE_DIR)}"
                })
    existing = json.loads(MANIFEST_PATH.read_text())
    existing_sources = [entry for entry in existing.get("sources", []) if "dest" in entry]
    # keep existing base entries, append newly generated ones if missing
    generated_keys = {entry["dest"] for entry in existing_sources}
    for entry in entries:
        if entry["dest"] not in generated_keys:
            existing_sources.append(entry)
    existing["sources"] = [entry for entry in existing.get("sources", []) if "dest" not in entry] + existing_sources
    MANIFEST_PATH.write_text(json.dumps(existing, indent=2))

if __name__ == "__main__":
    main()
