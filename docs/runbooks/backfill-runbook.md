# Power Tracks Backfill Runbook

_Last updated: 2025-11-10_

This playbook explains how to replay real Polygon data through the Power Tracks suite so Studio receives live-quality detections. It stitches together the Data, Engine, and Studio repos plus Backblaze B2 so you can hydrate history, verify outputs, and automate daily jobs.

---

## 1. Prerequisites & Layout

Clone the three repos side-by-side and ensure the shared storage tree is mounted read/write (see `power-tracks-engine/docs/data-architecture.md:5`):

```
~/Documents/GitHub/
├── power-tracks-data
├── power-tracks-engine
└── power-tracks-studio
```

Environment variables:

```bash
export POLYGON_API_KEY="pk_live_..."     # Polygon premium key
export ENGINE_API_KEY="..."              # Daemon x-api-key
export ENGINE_DATA_PATH="$HOME/Documents/GitHub/power-tracks-data/storage"
export B2_APPLICATION_KEY_ID="..."       # Optional (for sync)
export B2_APPLICATION_KEY="..."
export B2_BUCKET_NAME="power-tracks"
export DATABASE_URL="postgres://app:app@localhost:5432/app"
```

> Tip: copy these into `power-tracks-studio/.env` and `power-tracks-engine/.env` so `docker-dev.sh` picks them up (`power-tracks-studio/README.DEV.md:103`).

---

## 2. Harvest Polygon Data (power-tracks-data)

Use the unified CLI described in `power-tracks-data/docs/data-pipeline-guide.md:25`.

```bash
cd power-tracks-data
pt-data harvest \
  --symbols GME \
  --start-date 2024-05-13 \
  --end-date 2024-05-15 \
  --data-type all \
  --output-format json \
  --manifest-output output/harvest_2024-05.json
```

Validate before syncing:

```bash
pt-data validate --path data/harvested/GME/2024-05-13 --output output/validation_2024-05-13.json
```

Copy (or symlink) the harvested minute bars into the shared storage tree so the daemon’s JSON loader sees them (`power-tracks-engine/docs/data-architecture.md:17`):

```bash
rsync -av \
  data/harvested/GME/ \
  storage/minute_bars/GME/
```

---

## 3. Run Detector Backfills (power-tracks-engine)

The CLI wraps the batch runner in `scripts/run_power_track_batch.js` (`power-tracks-engine/cli/pte/src/index.ts:126`).

```bash
cd ../power-tracks-engine
pnpm install         # once per machine
pnpm pte backfill \
  --symbol GME \
  --start-date 2024-05-13 \
  --end-date 2024-05-15 \
  --ticks-dir ../power-tracks-data/data/harvested/GME \
  --out-dir reports/diagnostics \
  --passes hybrid_prod,hybrid_highband,legacy_fftwide
```

This produces a ledger CSV per day under `reports/diagnostics/<symbol>_<date>/`.

---

## 4. Decode & Persist Artifacts

Replay each ledger through the pipeline orchestrator (`scripts/run_power_track_pipeline.js:360`):

```bash
node scripts/run_power_track_pipeline.js \
  --ledger reports/diagnostics/gme_2024-05-13/gme_2024-05-13_ledger.csv \
  --output-dir reports/diagnostics/pipeline_outputs \
  --artifact-root ../power-tracks-data/storage/power_tracks
```

Artifacts created:

- `storage/power_tracks/<SYMBOL>/<track_id>/window_ticks.csv`
- `decoded_burst.json`, `price_path.json`, `summary.json`, `lag_manifest.json`
- Pipeline manifest under `reports/diagnostics/pipeline_outputs/<track_id>/pipeline_manifest.json`

Each run enforces decodability before writes (`power-tracks-engine/docs/plan-progress.md:9`).

---

## 5. Sync to Backblaze B2 (optional)

Run the data repo’s sync helper (`power-tracks-data/scripts/sync_artifacts_to_b2.py`) so Studio and remote agents can read:

```bash
cd ../power-tracks-data
python scripts/sync_artifacts_to_b2.py \
  --source storage/power_tracks \
  --bucket "$B2_BUCKET_NAME" \
  --base-path artifacts \
  --manifest-output output/b2_sync_manifest.json
```

For local MinIO, pass `--endpoint`, `--access-key`, and `--secret-key` (see `power-tracks-studio/docs/MIGRATION_STATUS.md:115`).

---

## 6. Hydrate Catalog (Postgres)

Studio’s catalog migration script moves legacy SQLite rows plus new artifacts into Postgres (`power-tracks-studio/docs/MIGRATION_STATUS.md:40`):

```bash
cd ../power-tracks-studio
node scripts/migrate_catalog_to_pg.js \
  --sqlite ../power-tracks-data/data/catalog/power_track_catalog.sqlite \
  --pg-url "$DATABASE_URL"
```

If you want to ingest fresh backfill outputs immediately, run the orchestrator queue (see `dashboard/lib/orchestration/queue.ts`), or call the daemon `/v1/tracks` endpoint to hydrate its SQLite snapshot store (`power-tracks-engine/docs/data-architecture.md:48`).

---

## 7. Verify Engine + Studio

1. **Daemon health**: `pnpm pte status` or `curl -H "x-api-key:$ENGINE_API_KEY" http://localhost:4020/status`
2. **Tracks list**: `curl -H "x-api-key:$ENGINE_API_KEY" 'http://localhost:4020/v1/tracks?symbol=GME&date=2024-05-13'`
3. **SSE stream**: `curl -N -H "x-api-key:$ENGINE_API_KEY" http://localhost:4020/v1/stream`
4. **Studio dashboard**: Load `/gme/2024-05-13` and `/macro`—the Next.js routes now pull from the generated SDK (`power-tracks-studio/dashboard/lib/api.ts:431`).

If SSE is quiet, check the daemon logs (`docker compose logs engine`) and confirm the shared `storage/minute_bars` paths match the detector config.

---

## 8. Automate (Daily/On-Demand)

Recommended cadence:

1. `pt-data harvest --start-date $(date -u +%Y-%m-%d)`
2. `pnpm pte backfill --date $(date -u +%Y-%m-%d)`
3. `node scripts/run_power_track_pipeline.js --ledger ...`
4. `python power-tracks-data/scripts/sync_artifacts_to_b2.py`
5. `node power-tracks-studio/scripts/migrate_catalog_to_pg.js --pg-url "$DATABASE_URL"`

Wire these steps into a cron, GitHub Actions workflow, or the Studio orchestrator (`dashboard/lib/orchestration/queue.ts:960`). The orchestrator already persists detections to both SQLite and Postgres (`recordDetectionsToPostgres`), so once the shared storage is populated, the UI cards flip from “smoke test” to live data (`power-tracks-studio/docs/state-cards/pipeline-status.md:42`).

Document each run (command + manifest path) in `power-tracks-engine/docs/runbook.md` or a Notion log so future operators know which days were replayed.
