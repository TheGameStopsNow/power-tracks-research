#!/usr/bin/env python3
"""
Append research data windows to docs/raw_data_manifest.json.

Walks select research phase data folders, infers symbol/date from filenames like
SYMBOL_YYYY-MM-DD.csv, and appends Polygon trades windows (13:30Z–20:00Z) so raw
files can be re-downloaded into the same paths with one fetch step.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent
MANIFEST_PATH = BASE_DIR / "docs" / "raw_data_manifest.json"

PHASE_FOLDERS = [
    ("phase13_temporal", BASE_DIR / "research" / "phase13_temporal" / "data"),
    ("phase14_genome", BASE_DIR / "research" / "phase14_genome" / "data"),
    ("phase15_atlas", BASE_DIR / "research" / "phase15_atlas" / "data"),
    ("phase18_ripple", BASE_DIR / "research" / "phase18_ripple" / "data"),
    ("phase22_synchronicity", BASE_DIR / "research" / "phase22_synchronicity" / "data"),
    ("phase23_causality", BASE_DIR / "research" / "phase23_causality" / "data"),
    ("phase24_full_scan", BASE_DIR / "research" / "phase24_full_scan" / "data"),
    ("phase25_energy", BASE_DIR / "research" / "phase25_energy" / "data"),
    ("phase27_options", BASE_DIR / "research" / "phase27_options" / "data"),
    ("phase29_system_cartography", BASE_DIR / "research" / "phase29_system_cartography" / "real_ticks"),
    ("phase30_interconnectedness", BASE_DIR / "research" / "phase30_interconnectedness" / "data"),
]


def parse_symbol_date(path: Path) -> Optional[Tuple[str, str]]:
    match = re.match(r"(?P<symbol>[A-Z]+)_(?P<date>\d{4}-\d{2}-\d{2})", path.stem)
    if not match:
        return None
    return match.group("symbol"), match.group("date")


def default_window(date_str: str) -> Tuple[str, str]:
    date = datetime.fromisoformat(date_str).date()
    start_dt = datetime.combine(date, time(hour=13, minute=30, tzinfo=timezone.utc))
    end_dt = datetime.combine(date, time(hour=20, minute=0, tzinfo=timezone.utc))
    return start_dt.isoformat().replace("+00:00", "Z"), end_dt.isoformat().replace("+00:00", "Z")


def iter_phase_entries() -> Iterable[dict]:
    for phase_name, folder in PHASE_FOLDERS:
        if not folder.exists():
            continue
        for path in sorted(folder.glob("*.csv")):
            parsed = parse_symbol_date(path)
            if not parsed:
                continue
            symbol, date = parsed
            start, end = default_window(date)
            yield {
                "provider": "polygon",
                "api": "trades",
                "symbol": symbol,
                "date": date,
                "start": start,
                "end": end,
                "venue": "all",
                "dest": str(path.relative_to(BASE_DIR)),
                "notes": f"Research/{phase_name} raw trades ({symbol} {date}) – restore into data/ before running the phase scripts",
            }


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"sources": []}
    return json.loads(MANIFEST_PATH.read_text())


def dedupe(existing: List[dict], additions: Iterable[dict]) -> List[dict]:
    seen = {entry.get("dest") for entry in existing if "dest" in entry}
    merged = list(existing)
    for entry in additions:
        dest = entry.get("dest")
        if dest in seen:
            continue
        merged.append(entry)
        seen.add(dest)
    return merged


def main() -> None:
    manifest = load_manifest()
    sources: List[dict] = list(manifest.get("sources", []))
    additions = list(iter_phase_entries())
    manifest["sources"] = dedupe(sources, additions)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    print(f"Added {len(additions)} research entries (deduped) to {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
