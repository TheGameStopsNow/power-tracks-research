# Burst4 Case Study (2024‑05‑17 08:03:26 ET)

This folder aggregates every artifact we built while reverse‑engineering the 08:03 burst (“burst4 main”) and linking it to option flow and future price action. Use it as a quick handoff for new agents.

## Quick Start

- 1. **Normalized stroke views**
   - `normalized_burst4_main.png` – 2D normalized scatter with stroke-order coloring and stats.
   - `normalized_burst4_layers.png` / `normalized_burst4_layers_overlay.png` – per-slice breakdowns (10 time bins) showing how the face fills in.
   - `normalized_burst4_main_3d.html` – interactive Plotly view (depth slider, size slider, orthographic toggle, axis hotkeys X/Y/Z/O). Use this to rotate/export.

2. **Raw EDGX trades**
   - `trade_scatter_burst4_main_080320_080505.png` – price-vs-time scatter in dollars (no normalization) for ground truth comparison.

3. **Option lattice + lags**
   - `burst4_option_grid_3d.html` – 3D strike/expiration lattice with slider for each lag day; points sized by notional and colored by strike.
   - `burst4_option_lag_breakdown.csv/.png` – per-lag notional summary (lags 1, 4, 7) with call shares annotated.

4. **Future price impact**
   - `burst4_future_return_profile.csv` – horizon table covering 0d through 500d closes/returns. Shows the 120–250d ramp that mirrors the option ladder.

## Scripts & Source Tables

- Visualization / analysis scripts (see `./scripts/`):
  - `scripts/plot_normalized_burst4_main.py`
  - `scripts/plot_burst4_time_layers.py`
  - `scripts/plot_burst4_option_grid.py`
  - `scripts/summarize_burst4_lag_profile.py`
- Core datasets bundled here for convenience:
  - `burst_future_with_options.csv` – burst catalog + option features.
  - `burst_option_summary.csv` – per-lag option aggregations.
  - `normalized_points.csv` (converted from the original Parquet) – normalized point clouds for every burst (used by the plotting scripts). The original `.parquet` is included for reference.

## How to Extend

1. Align each slice (from `normalized_burst4_layers.png`) with future price bars using DTW or cross-correlation on normalized paths.
2. Weight slice z-depth by lag-specific call bias (from `burst4_option_lag_breakdown.csv`) and test whether those weights predict when the shape reappears (e.g., 120d vs 250d windows in `burst4_future_return_profile.csv`).
3. Replicate this folder structure for other bursts (e.g., 2021‑01‑25 faces) to build a catalog of reusable “glyphs.”

## Raw Data (bundled)

To restudy or recompute any of the visuals, the underlying tick/option files are copied into `./raw_data/`:

- **EDGX ticks (UTC timestamps, EDGX-only trades)**
  - `raw_data/ticks/gme_20240517_080000_080300.csv`
  - `raw_data/ticks/gme_20240517_080400_080600.csv`

- **Option trades feeding lag 1/4/7 (Polygon flat files parsed via OCC)**
  - `raw_data/options/2024-05-16.csv` (lag 1)
  - `raw_data/options/2024-05-13.csv` (lag 4)
  - `raw_data/options/2024-05-10.csv` (lag 7)

CSV exports were generated from the original Parquet datasets (which are still kept alongside them). Use whichever format is more convenient for your tooling when rerunning the scripts in `./scripts/` or building custom strike/expiry analyses.

Refer back to `docs/edgx_bursts_option_flow_report.md` (§5.1 case study) for the narrative discussion tying these artifacts together.
