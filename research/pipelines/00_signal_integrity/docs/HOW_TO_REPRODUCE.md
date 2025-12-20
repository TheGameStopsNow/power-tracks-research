# How to Reproduce the Evidence Pack

Fast path (one command):
```bash
cd reproducibility-bundle
export POLYGON_API_KEY=YOUR_KEY
bash scripts/run_evidence_pack.sh
```
This will:
- Create a venv and install requirements.
- Rebuild ticks → frames → signals for 2024-05-13..17.
- Verify SHA256/frames/signals for each day.
- Regenerate predictiveness/TISA reports and plots (base + extended + overlays).

Artifacts to review after the run:
- Samples with refreshed `SHA256SUMS`: `sample_2024-05-13..17/`.
- Predictiveness: `reports/predictiveness.json`, `reports/plots/predictiveness_hit_rate.png`.
- TISA (base): `reports/tisa_*.json`, `reports/plots/tisa_distance.png`, `reports/plots/tisa_rmse.png`.
- TISA extended (windowed, z-RMSE/DTW with shuffles): `reports/tisa_extended_*.json`, `reports/plots/tisa_extended_*.png`.
- Overlays (decoded vs future shapes): `reports/plots/overlays/`.

Notes/limits:
- Frames are produced by the repo encoder from Polygon ticks (not captured on-wire).
- Raw Polygon ticks are fetched live; ensure your API key has access to historical trades.
- Predictiveness/TISA are exploratory; shuffled baselines are included but formal p-values are not computed in this run. Extend `tisa_extended.py` if you need more permutations.
