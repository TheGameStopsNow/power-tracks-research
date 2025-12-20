import json
from pathlib import Path

CORE = ["GME", "AMC", "KOSS", "BB", "SPY"]
SLEEPERS = [
    "LEN.B", "AMAL", "ALUR", "CNTB", "DJTWW",
    "MPU", "CMPX", "FLGC", "JAKK", "AXGN", 
    "MEGL", "BNS", "HOWL", "KELYA", "NCDL", 
    "GIC", "IAGG", "ORN", "ALNT", "QCLN"
]
ALL_TARGETS = list(set(CORE + SLEEPERS))
DATE = "2024-05-14"
START = "2024-05-14T13:00:00Z"
END = "2024-05-14T20:00:00Z"

manifest = {"sources": []}

for sym in ALL_TARGETS:
    entry = {
        "provider": "polygon",
        "api": "trades",
        "symbol": sym,
        "date": DATE,
        "start": START,
        "end": END,
        "venue": "all",
        "dest": "data/samples/local/{provider}/{symbol}/{date}",
        "notes": f"Phase 24 Dragnet data for {sym} on {DATE}"
    }
    manifest["sources"].append(entry)

out_path = Path("research/phase24_full_scan/manifest.json")
out_path.write_text(json.dumps(manifest, indent=2))
print(f"Generated {out_path} with {len(manifest['sources'])} entries.")
