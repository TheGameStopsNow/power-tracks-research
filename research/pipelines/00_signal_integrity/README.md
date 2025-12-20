# Module 00: Signal Integrity

**The Foundation.**

Before we analyze any patterns, we must prove the data is real. This module contains the tools to verify the integrity of the "Power Tracks" signal at the binary level.

## Structure (simplified)
-   **`run.py`**: One-click runner for the reproducibility suite (uses the existing scripts under `src/`).
-   **`src/`**: Verification scripts (decode frames, recompute checksums, validate signals).
-   **`tests/`**: Smoke tests for CRC/frame validation.
-   **`docs/`**: Specs and expected outputs:
    -   [Frame Format Spec](docs/FRAME_FORMAT_SPEC.md)
    -   [Expected Outputs](docs/EXPECTED_OUTPUTS.md)

## Quick Start (sample data)
From the repo root:
```bash
python pipelines/00_signal_integrity/run.py \
  --sample-dir data/samples/sample_2024-05-13
```
The runner auto-picks `MANIFEST.json` and `SHA256SUMS` if present. Add `--output report.json` to save a report.

## Tests
```bash
pytest pipelines/00_signal_integrity/tests
```
