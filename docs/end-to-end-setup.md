# End-to-End Setup (Data → Engine → Studio)

This guide walks through bootstrapping the **Power Tracks Suite** on a single workstation, including:

1. Harvesting and staging historical market data (`power-tracks-data`)
2. Running the engine daemon against the staged data (`power-tracks-engine`)
3. Stitching macro tracks so `/v1/macro` and the Studio dashboards return multi-day chains
4. Wiring the FastAPI cache and Next.js Studio so everything runs end to end

It assumes the three repositories sit next to each other:

```
~/Documents/GitHub/
  power-tracks-data/
  power-tracks-engine/
  power-tracks-studio/
```

> 💡 All paths in this document are relative to the repo roots above. Adjust if you store the code elsewhere.

---

## 1. Prerequisites

- **Node.js 20.x** and **npm 9.x** (Engine + Studio)
- **Python 3.10+** and `pip` (Data repo + FastAPI API)
- **Docker + docker compose** (Studio stack)
- A **Polygon.io API key** with sufficient historical access
- 50GB+ of free disk space for staged ticks, decoded manifests, and macro outputs

Create (or update) the following `.env` files with shared secrets:

| File | Key settings |
| --- | --- |
| `power-tracks-engine/.env` | `POLYGON_API_KEY`, optional `ENGINE_API_KEY` |
| `power-tracks-studio/.env` | `POLYGON_API_KEY`, `DATA_STORAGE_PATH`, `ENGINE_REPO_PATH`, `ENGINE_HTTP_URL` |
| `power-tracks-studio/api/.env` *(if running FastAPI directly)* | `POLYGON_API_KEY`, `ENGINE_HTTP_URL`, `ENGINE_API_KEY` (if enabled) |

`DATA_STORAGE_PATH` should point at `../power-tracks-data/storage` so every container sees the same decoded artifacts.

---

## 2. Stage Historical Data (`power-tracks-data`)

1. **Install dependencies**
   ```bash
   cd power-tracks-data
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   pip install -e .
   ```

2. **Configure Polygon + storage**  
   Fill in `config/pt_data.yaml` (see `docs/data-pipeline-guide.md`) or export env vars:
   ```bash
   export POLYGON_API_KEY=pk_your_key
   export DATA_STORAGE_PATH="$(pwd)/storage"
   ```

3. **Harvest ticks + minute bars**  
   Example: load three May 2024 trade days for GME.
   ```bash
   pt-data harvest --symbols GME --start-date 2024-05-13 --end-date 2024-05-15
   pt-data minute-bars --symbols GME --start-date 2024-05-13 --end-date 2024-05-15
   ```

4. **Normalize into the shared storage tree**  
   The commands above populate `storage/ticks`, `storage/minute_bars`, and `storage/pipeline_outputs`.  
   The Docker stack later bind-mounts `storage` into every container via `DATA_STORAGE_PATH`.

> ✅ At this point `power-tracks-data/storage` should contain `pipeline_outputs/<SYMBOL>/<YYYY>/<MM>/<DD>/…` and `power_tracks/<SYMBOL>/decoded/<YYYY-MM-DD>/tracks.jsonl`. If the `decoded` folders are missing, run the generator in step 4a below.

---

## 3. Install & Configure the Engine (`power-tracks-engine`)

1. **Install Node deps + build**
   ```bash
   cd power-tracks-engine
   npm install
   npm run build --workspaces
   ```

2. **Point the engine at the staged data**  
   Update (or create) `engine.config.yaml` with:
   ```yaml
   data:
     mode: filesystem
     path: ../power-tracks-data/storage            # absolute path recommended
     allowlist: [GME]

   macro:
     minDays: 3
     maskDriftTolerance: 1
     defaultLookbackDays: 180
     decodedRoots:
       - "${ENGINE_DATA_PATH}/power_tracks/GME/decoded"
       - "${ENGINE_DATA_PATH}/pipeline_outputs/GME"
   ```

3. **Set environment variables**
   ```bash
   export ENGINE_DATA_PATH=/Users/you/Documents/GitHub/power-tracks-data/storage
   export POLYGON_API_KEY=pk_your_key
   ```

4. **Smoke-test the daemon locally**
   ```bash
   npm run --workspace @powertracks/daemon start
   # In another terminal:
   curl http://localhost:4020/health
   ```

You can stop the daemon (Ctrl+C) after verifying the health endpoint responds.

---

## 4. Ensure Decoded Days & Macro Inputs Exist

Macro stitching expects `decoded/<DATE>/tracks.jsonl` files plus `lag_manifest.json` artifacts. Populate them one of two ways:

### Option A – Generate JSONL indexes from pipeline outputs

If you only have legacy manifests in `pipeline_outputs`, run:

```bash
cd power-tracks-engine
npx ts-node scripts/generateMacroTracksJsonl.ts \
  --base-path ../power-tracks-data \
  --symbol GME \
  --start 2024-05-13 --end 2024-05-15
```

This scans `pipeline_outputs` for each day, extracts metadata from `lag_manifest.json`, and writes `power_tracks/GME/decoded/<DATE>/tracks.jsonl`.

### Option B – Re-run the detector locally

If you harvested raw ticks (CSV) instead, rerun the detector and decoder so decoded artifacts land under `storage`:

```bash
cd power-tracks-engine
pte backfill \
  --symbol GME \
  --start-date 2024-05-13 \
  --end-date 2024-05-15 \
  --ticks-dir ../power-tracks-data/storage/ticks \
  --out-dir ../power-tracks-data/storage/pipeline_outputs
```

---

## 5. Stitch Macro Tracks

With decoded days in place:

1. **Run the daemon (filesystem mode)**
   ```bash
   export ENGINE_DATA_PATH=../power-tracks-data/storage
   npm run --workspace @powertracks/daemon start
   ```

2. **Trigger macro stitching via CLI**
   ```bash
   pte macro \
     --symbol GME \
     --lookback 180 \
     --decoded-root ../power-tracks-data/storage/power_tracks/GME/decoded \
     --json > /tmp/gme-macros.json
   ```

3. **Or hit the API to persist chains + SQLite snapshots**
   ```bash
   curl "http://localhost:4020/v1/macro?symbol=GME&start=2024-05-13&end=2024-05-15"
   ```

4. **Automate multi-day backfills**
   ```bash
   node scripts/power_track_full_backfill.js \
     --symbol GME \
     --start 2024-05-01 \
     --end 2024-05-31
   ```

Macro payloads land in `power-tracks-data/storage/power_tracks/GME/macro_tracks.json` and the SQLite snapshot (`services/daemon/data/powertracks.sqlite`), which the Studio reads.

Leave the daemon running for the next step.

---

## 6. Launch the Studio Stack (`power-tracks-studio`)

1. **Set `.env` (example)**
   ```bash
   POLYGON_API_KEY=pk_your_key
   DATA_STORAGE_PATH=/Users/you/Documents/GitHub/power-tracks-data/storage
   ENGINE_REPO_PATH=/Users/you/Documents/GitHub/power-tracks-engine
   ENGINE_HTTP_URL=http://engine:8001   # containers talk to the engine service name
   ```

2. **Start Docker services**
   ```bash
   cd power-tracks-studio
   docker compose up -d db redis minio
   docker compose up -d engine api studio
   ```

   The compose file bind-mounts `DATA_STORAGE_PATH` into every container at `/app/data`, so the daemon inside Docker sees the same decoded artifacts you prepared earlier.

3. **Verify endpoints**
   ```bash
   curl http://localhost:4020/health           # daemon (host instance)
   curl http://localhost:8001/health           # daemon inside Docker network
   curl http://localhost:8700/v1/tracks?include=macro
   open http://localhost:8080                  # Studio dashboard
   ```

   Inside the Studio, use the Macro Tracks view or toggle “include macro” on the tracks table to see stitched chains.

---

## 7. Troubleshooting

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| `/v1/macro` returns `503 Macro stitcher unavailable` | `ENGINE_DATA_PATH` not set or `data.mode` left on `polygon` | Set filesystem mode and restart daemon |
| Macro response says `status: empty` | `decodedRoots` resolved to empty folders | Ensure `power_tracks/<SYMBOL>/decoded/<DATE>/tracks.jsonl` exists (run generator or detector) |
| Studio shows “Macro data unavailable” | API hitting Docker hostnames (`engine:8001`) while running locally | Set `NEXT_PUBLIC_ENGINE_URL=http://localhost:8001` (or use Docker) |
| Macro CLI exits with “No decoded roots specified” | `macro.decodedRoots` missing | Update `engine.config.yaml` or pass `--decoded-root` |
| `ECONNREFUSED` from API | Engine daemon not running or API cannot reach it | Start daemon first, confirm `ENGINE_HTTP_URL` |

For deeper details on macro stitching internals, see `docs/macro-flow.md`. For observability and operational runbooks, see `docs/runbook.md`.

---

## 8. Next Steps

- Automate recurring macro refreshes with `cron` calling `scripts/power_track_full_backfill.js`
- Explore Prometheus metrics via `http://localhost:4020/metrics`
- Use `pte macro --json` outputs as fixtures in Studio tests to validate rendering

With the steps above, you should be able to go from raw Polygon data → decoded artifacts → stitched macro tracks inside the Studio in under an hour on a modern workstation.
