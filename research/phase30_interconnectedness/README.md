# Research Phase 30: Interconnectedness & Zombie Mode

## Goal
Investigates mathematical correlation between GME and other basket assets during low-volume 'Zombie' periods.

## Key Findings
- [Pending Analysis]

## Artifacts
- `output/latency_map.json`: Network latency structure between assets.
- `output/correlation_matrix.csv`: Cross-asset correlation coefficients.

## Usage
```bash
# Run the network scan
python scripts/scan_network.py

# Run master scanner for GME
python scripts/gme_master_scanner.py
```

## Data
Data is defined in `manifest.json`.
Run the downloader to fetch required datasets:
```bash
python download_data.py
```
