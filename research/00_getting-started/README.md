# Getting Started

## Goal
Demonstrate the Power Tracks pipeline: loading data, detecting anomalies (bursts), and visualizing results.

## Key Findings
*   Price paths contain detectable "micro-bursts" that deviate from random walks (z-spike > 3.0).
*   Simple statistical filters (z-score on returns) are often enough to find interesting events.

## Artifacts
*   `output/demo_output.png`: Visualization of top 3 anomalies on the price path.
*   `01_magic_demo.ipynb`: Interactive walkthrough.

## Usage

1.  **Download Data**:
    ```bash
    python download_data.py
    ```

2.  **Run Demo**:
    ```bash
    python 00_magic_demo.py
    ```

## Data
Contains a small sample slice of GME trades (May 17, 2024).
Run `python download_data.py` to fetch fresh data if needed, or rely on the included sample in `data/` (gitignored).
