# Power Tracks Decoder Tool

This tool allows you to decrypt "Power Track" barcodes from raw market data CSVs.
It has been ported to be largely standalone Python code, removing the dependency on the internal Node.js engine.

## Setup

1.  Ensure you have Python 3.12+ installed.
2.  Install dependencies:
    ```bash
    pip install -r ../../requirements.txt
3.  (Optional) Download sample data (Requires Polygon API Key):
    ```bash
    python3 download_data.py
    ```
    This will fetch GME trade data to `../../data/samples/gme_20240517/tools_sample/sample_data.csv`.

## Usage

### 1. Basic Decryption (CSV)
To decode a specific CSV file (e.g., an EDGX burst export):

```bash
# Point to your CSV file
export PTE_DATA_SOURCE=csv
export PTE_CSV_PATH=/path/to/your/trades.csv

# Run the diagnostics
python3 frame_diagnostics.py
```


### CSV Format
The input CSV must contain at least:
- **`timestamp`** (ISO 8601 string) OR **`timestamp_us`** (integer microseconds)
- **`price`** (float)

### 2. Configuration
You can tweak detection thresholds using environment variables:

```bash
export PTE_POWER_THRESHOLD=5000  # Lower threshold for sensitivity
export PTE_FREQ_BAND_LOW=0.5
export PTE_FREQ_BAND_HIGH=3.0
python3 frame_diagnostics.py
```

## Output
The script will output:
- **`frame_diagnostics_report.json`**: Full JSON report of decoding attempts.
- **`price_paths/`**: Unfolded price paths (CSV) if a valid track is found.
- **Terminal Output**: progress logs and summary.

## How it Works
1.  **Alignment**: Scans the bitstream for valid 56-bit or 136-bit headers.
2.  **Bitmasking**: Brute-forces the 1-byte XOR mask against CRC-7 checksums.
3.  **Unfolding**: Parses VarInts and "mirrored" segments to reconstruct the future price path.
