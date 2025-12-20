# Troubleshooting

Common issues and quick fixes when running demos, labs, or suites.

- **Missing price_paths.csv**: Run `make data SYMBOL=GME DATE=2024-05-13` (requires `POLYGON_API_KEY`) then `make micro-sample`; the demo auto-picks micro/local/committed paths.
- **No API key**: Use the committed sample (already present) or set `POWER_TRACKS_PRICE_PATHS=data/samples/sample_2024-05-13/signals/price_paths.csv`.
- **NBVal/pytest not found**: `pip install -r requirements.txt` (includes pytest/nbval).
- **Suite entrypoint missing**: `make suite-<name>` falls back to legacy `pipelines/.../scripts`. If all are missing, it logs `[skip]` without failing.
- **Artifacts outdated**: Run suites, then `make publish-artifacts VERSION=vYYYYMMDD SRC=path/to/outputs`; `latest` will relink automatically.
- **Large data in repo**: Keep big files in `data/samples/local` or `POWER_TRACKS_DATA_DIR` (git-ignored); only commit tiny micro slices.
- **Repo size check fails**: `make check-size` shows offending files (>5 MB). Move large files into ignored paths or external storage.
