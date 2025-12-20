# Phase 78: Context Morphology

## Goal
Retrieve Open Interest (OI) profiles for GME bursts identified in Phase 77 to analyze "Context Morphology" — the shape of market positioning surrounding high-activity events.

## Key Findings
- **Analysis pending**: Run `morphology_analysis.py` after fetching OI.

## Artifacts
- `data/open_interest/gme_oi_*.csv`: EOD Open Interest snapshots for burst dates.
- `output/morphology_report.csv`: Metrics describing OI distribution shape.

## Usage
1. Download Data:
   ```bash
   python download_data.py
   ```
   *Note: Relies on Phase 77 burst fingerprints (`research/phase77_greek_echo/output/burst_fingerprints_enhanced.csv`). Requires ThetaData (local instance).*

2. Run Analysis:
   ```bash
   python scripts/morphology_analysis.py
   ```

## Data
- **Source**: ThetaData (Open Interest).
- **Trigger**: Bursts from Phase 77.
