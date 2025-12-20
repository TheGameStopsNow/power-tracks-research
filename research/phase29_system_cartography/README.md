# Research Phase 29: System Cartography

## Goal
Map the Global Market System using Grammar Decoding and Options Overlay to identify high-fidelity patterns (1-4-7, 7-4-1) and calculate "Gravity" scores from option magnets.

## Key Findings
- **Grammar Decoding**: Successfully identifies 3-step 7-4-1 and 1-4-7 sequences in tick data.
- **System Map**: Generates a comprehensive JSON map (`output/SYSTEM_CARTOGRAPHY_REPORT.json`) detailed sequence matches and gravity scores.
- **Data Integrity**: Audited 9341 tick files for fidelity.

## Artifacts
- `output/SYSTEM_CARTOGRAPHY_REPORT.json`: Complete system map with grammar sequences and hunt results.
- `output/`: Visualization artifacts (TBD).

## Usage
```bash
# Run the Master Cartographer
python scripts/run_cartography.py
```

## Data
Defined in `manifest.json`.
Run the downloader:
```bash
python download_data.py
```
