# Steganography Research

## Goal
Investigate potential covert channels in equity market data (GME) using statistical steganography detection techniques (LSB analysis, timing channels, order book microstructure).

## Key Findings
(See `docs/FINDINGS.md` for full report)
*   **LSB Anomalies**: 100% of analyzed GME days show non-uniform price/volume LSB distributions (p < 0.0001).
*   **Timing Channels**: Detected strong periodicity (16.4s) and interval clustering (HFT fingerprints).
*   **Microstructure**: Runs ratio > 1.4 suggests algorithmic direction control significantly above random.

## Artifacts
*   `docs/FINDINGS.md`: Comprehensive initial findings report.
*   `data/`: Local data cache (gitignored).
*   `output/`: Analysis results.

## Usage

1.  **Download Data**:
    ```bash
    python download_data.py
    ```

2.  **Run Analysis**:
    (See specific subdirectories for detailed scripts, e.g., `12_power_tracks_analysis`)

## Data
Focused on GME tick data (May 2024 and historical samples).
Run `python download_data.py` to fetch.
