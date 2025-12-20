# Evidence Pack at a Glance

What this is:
- Fully reproducible pipeline for GME 2024-05-13..17: Polygon ticks → Power Track frames → decoded price paths, with CRC checks and SHA256SUMS.
- Exploratory analyses (predictiveness, TISA/DTW, windowed overlays) plus plots and summaries.
- One-command rerun: `POLYGON_API_KEY=... bash scripts/run_evidence_pack.sh`.

What this is not:
- Not captured on-wire packets; frames are produced by the repo encoder from Polygon ticks.
- Not a claim of intentional embedding or guaranteed predictive edge; analyses are exploratory with shuffled baselines but no formal p-values.

Key entry points:
- How to rerun: `HOW_TO_REPRODUCE.md`.
- Evidence pack index: `reports/evidence_pack/README.md`.
- Plots: `reports/plots/` (predictiveness, TISA base/extended, overlays).
- Checksums: `sample_2024-05-13..17/SHA256SUMS`.

Suggested reviewer flow:
1) Run `scripts/run_evidence_pack.sh` with your Polygon key; capture the log:  
   `POLYGON_API_KEY=... bash scripts/run_evidence_pack.sh | tee reports/evidence_pack/rebuild_log.txt`
2) Inspect `reports/plots/` and `reports/tisa_extended_*.json` for windowed structure (strongest 60–80d).
3) Verify SHA256SUMS and `verify_reproducibility.py` PASS across all days.
4) If desired, record your confirmation in `reports/evidence_pack/INDEPENDENT_CHECK.md`.
