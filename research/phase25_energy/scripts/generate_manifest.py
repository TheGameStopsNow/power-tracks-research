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
DATE_RANGE = ["2024-05-13", "2024-05-14", "2024-05-15", "2024-05-16", "2024-05-17"]

START_TIME = "13:00:00Z"
END_TIME = "20:00:00Z"

manifest = {"sources": []}

for sym in ALL_TARGETS:
    for date in DATE_RANGE:
        entry = {
            "provider": "polygon",
            "api": "trades",
            "symbol": sym,
            "date": date,
            "start": f"{date}T{START_TIME}",
            "end": f"{date}T{END_TIME}",
            "venue": "all",
            "dest": "data/samples/local/{provider}/{symbol}/{date}",
            "notes": f"Phase 25 Energy data for {sym} on {date}"
        }
        manifest["sources"].append(entry)

out_path = Path("research/phase25_energy/manifest.json")
out_path.write_text(json.dumps(manifest, indent=2))
print(f"Generated {out_path} with {len(manifest['sources'])} entries.")
