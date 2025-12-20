# Research Sandbox Guide

This folder mirrors the pipelines style: each phase is self-contained with its own data, scripts, reports, and outputs. No raw Polygon data is committed; everything here is metadata, code, or derived findings.

## Structure
- `phase*/` — self-contained phases. Keep raw slices under `data/`, derived artifacts under `outputs/` or `charts/`, and narrative in the phase report/README.
- `edgx_deep_decode/` — EDGX-specific studies (LSB/Glasshouse), structured the same way.
- `PHASE_INDEX.md` — quick map of phases, symbols, dates, and where outputs live.

## Raw Data Windows
- All raw windows must be declared in `docs/raw_data_manifest.json`. Use `scripts/add_research_to_manifest.py` to append the research windows from phase13/15/18 based on the files under `research/*/data`.
- Fetch raw data with the paid Polygon key (no synthetic data). For tick-level slices, prefer `pt-data harvest` with the date/time windows listed in the manifest or `PHASE_INDEX.md`.
- If you add new data to any phase, rerun `python scripts/add_research_to_manifest.py` so the manifest stays authoritative.

## Reproduction Flow
1) Append research windows: `python scripts/add_research_to_manifest.py`
2) Pull raw slices (ticks) with `pt-data harvest --symbols ... --start-date ... --end-date ... --output data/<path>` using the manifest windows.
3) Run the phase scripts from within each phase folder; outputs stay inside that folder.

## Anonymity & Integrity
- Research attribution is `TheGameStopsNow` (do not use the author’s real name or system username).
- Zero synthetic data: only real Polygon data, validated via `validateRealData()` in downstream steps.
- Provenance: keep links relative to this repo; avoid absolute paths or user-specific home directories.
