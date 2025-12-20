# Power Tracks Research – Guided Walkthrough

Use this as the “tour guide” if you are new to the repo or to markets. Follow the track that matches your time and comfort level.

## Track A: 10–20 minutes (Newcomer)
1) **Run the one-click helper**:  
   `./scripts/one_click.sh` (prompts, installs, builds micro sample, runs demo)  
   If you skip Polygon, committed micro data already works.
2) **Run the Magic Demo** again anytime:  
   `make demo`  
   What you get: top return spikes + a PNG plot.
3) **Open the Guided Notebook** (optional, interactive):  
   `jupyter notebook getting-started/01_magic_demo.ipynb`  
   Look for the **STATUS** and runtime header at the top.

## Track B: 45–90 minutes (Practitioner)
1) **Labs** (concept drills):  
   - `labs/00_packet_analysis.ipynb` (how frames become price paths)  
   - `labs/01_spectral_primer.ipynb` (how bursts show up in spectra)  
   Tip: keep runtimes short by using the micro sample.
2) **Run a Suite on Sample Data**:  
   - `make suite-selectivity` (or `suite-clusters`, `suite-gating`, `suite-portability`, `suite-options`, `suite-risk`)  
   Suites auto-skip if no entrypoint is present; they won’t crash on missing paths.
3) **Inspect Artifacts**:  
   See `artifacts/latest/` (centroids, templates, gating, HIP, pinning).

## Track C: Maintainer
1) **Validate Everything**:  
   `make test` (pytest smokes)  
   `make test-nbval` (demo + labs notebooks)  
   `make check-size` (ensure only tiny files are tracked)
2) **Publish New Artifacts** (after suites):  
   `make publish-artifacts VERSION=vYYYYMMDD SRC=artifacts/tmp/<suite>`  
   This refreshes `artifacts/latest` automatically.
3) **Keep Notebooks Clean**: `.gitattributes` applies `nbstripout`; outputs should be stripped when committing.

## Where to look (map)
- **Start here**: `README.md` (choose your path)  
- **How things connect**: `docs/map.md`  
- **Fixes and gotchas**: `docs/troubleshooting.md`

## If something breaks
- Missing data: set `POWER_TRACKS_PRICE_PATHS` to a CSV or run `make data && make micro-sample`.
- Suites missing: they’ll log `[skip]`—add the entrypoint or use legacy scripts until migrated.
- Large file errors: move big files into `data/samples/local` (git-ignored) or external storage.
