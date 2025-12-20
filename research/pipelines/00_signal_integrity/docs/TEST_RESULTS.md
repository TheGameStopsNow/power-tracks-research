# Test Results (current state)

**Last run**: 2025-11-25  
**Summary**: Reproducibility verification **passes** end-to-end on the bundled samples (2024-05-13 through 2024-05-17). Real Polygon tick trades are fetched, frames are encoded/validated (no caps), signals are generated (CSV/Parquet/SQLite), and checksums are verified. CRC unit tests pass against standard vectors. Frames are derived from ticks using the bundled encoder/decoder (not captured on-wire packets); all steps are reproducible with a Polygon API key. Predictiveness/selector and TISA alignment checks are included.

## Environment
- Python 3.11 virtualenv at `.venv`
- Dependencies installed via `pip install -r requirements.txt`

## CRC Unit Tests
- Command: `.venv/bin/pytest -q tests/test_crc.py`
- Result: ✅ 17 passed (standard CRC-7, CRC-16-CCITT-FALSE, CRC-16-X25 implementations)

## Reproducibility Verification
- Command (per day): `.venv/bin/python scripts/verify_reproducibility.py --sample-dir sample_2024-05-14 --manifest sample_2024-05-13/MANIFEST.json --sha256 sample_2024-05-14/SHA256SUMS` (repeat for 05-15, 05-16, 05-17)
- Result: ✅ PASS for 2024-05-13 .. 2024-05-17
- Findings (representative):
  - Raw tick data: ✅ PASS (tick-level with `price`, fetched via Polygon).
  - Frames: ✅ PASS (CRC 1.0 pass rate; per-day frames: 35 / 60 / 35 / 17 / 19 for 05-13..17).
  - Signals: ✅ PASS (price-path points per day: 9032 / 15480 / 9030 / 4386 / 4902; timestamps anchored to midnight UTC via start_time_ms).

## Pipeline Status
- `scripts/raw_to_signals.py` encodes ticks → frames (length-prefixed, no default cap) and decodes frames → price paths (CSV/Parquet/SQLite).
- `scripts/rebuild_day.py` fetches → encodes → decodes → regenerates SHA256SUMS for a given date (Polygon key required).
- `scripts/select_windows.py` + `scripts/window_pipeline.py` provide optional tiered scanning on OHLCV → tick windows → decode.
- `scripts/crosscheck_signals_vs_bars.py` compares decoded price paths to external OHLCV for sanity.
- `scripts/build_features.py`, `eval_predictiveness.py` compute features/labels vs minute bars and evaluate predictiveness.
- `scripts/score_tracks.py` scores/filters tracks and reports lift vs full set.
- `scripts/tisa_validate.py` runs TISA similarity checks of decoded signals against future bars over multiple horizons/scales.

## Predictiveness (05-13 .. 05-17, horizons 1/5/15/60 min)
- Aggregate hit rates vs baselines: 1m 0.53 (baseline_majority 0.55), 5m 0.65 (0.60), 15m 0.76 (0.54), 60m 0.68 (0.57); correlations rise at longer horizons. See `reports/predictiveness.json`.
- Selector (top 25% by |delta_close|) lift: +0.14 (1m), +0.10 (5m), +0.10 (15m), +0.15 (60m) on hit rate vs full set. See `reports/selector.json`.

## TISA Alignment (05-13 .. 05-17)
- `tisa_validate.py` compares decoded paths to future bars across horizons (1/4/7/30/90/180 days) and scales (0.5..4.0), using minute bars fetched from Polygon in `bars_range/`.
- Current TISA alignment is brittle on long sequences (best_distance may be `null`); to keep horizon sensitivity we also record z-score RMSE of the decoded path vs future bars. See per-day reports in `reports/tisa_YYYY-MM-DD.json`, the aggregated `reports/tisa_summary.json`, and plots in `reports/plots/tisa_distance.png` and `reports/plots/tisa_rmse.png`.
- Extended windowed analysis (`scripts/tisa_extended.py`): z-RMSE + DTW (with shuffled baselines) across windows 0-30, 60-70, 70-80, 80-90, 150-180 days and scales 0.5..4.0. Outputs live in `reports/tisa_extended_*.json`; plots in `reports/plots/tisa_extended_*.png`. Highlights:
  - 60-70/70-80d windows often show lowest z-RMSE/DTW vs shuffled at scales 0.5–0.75 (slower playback), suggesting the decoded shape carries into that mid-term window.
  - 80-90d and 150-180d are mixed: some days improve, others revert toward baseline.
- Null controls (`scripts/tisa_null_controls.py`): compare real decoded patterns against shuffled, random-walk, and bar-close patterns (10 shuffled draws; p-value = fraction of shuffled minima beating real). Reports in `reports/tisa_null_controls_*.json`. Mixed results: strong separation in 60-70/70-80d on some days (e.g., p≈0 on 05-14, 05-16, 05-17), but 80-90/150-180d often fail (p≈1).

## Required Actions to Maintain Reproducibility
1. If you refresh tick data or add dates, run `scripts/rebuild_day.py` for that date, then verify with `scripts/verify_reproducibility.py`.
2. Keep CRC tests green: `.venv/bin/pytest -q tests/test_crc.py`.
3. If sharing publicly, share decoded artifacts + SHA256SUMS; raw Polygon ticks must remain private.
4. For predictiveness/TISA updates, rerun `build_features.py`, `eval_predictiveness.py`, `score_tracks.py`, and `tisa_validate.py` after any data/decoder changes.

