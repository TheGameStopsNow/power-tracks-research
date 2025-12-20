# Power Tracks Data Lifecycle

This document captures how raw market data, orchestration outputs, and engine artifacts move through the shared storage tree. It complements `docs/data-architecture-analysis.md` by describing the “happy path” once the fixes from that analysis land.

## Shared Storage Layout

All repos (Data, Engine, Studio) mount the same `storage/` tree. Key directories:

| Path | Producer | Contents | Consumer(s) |
| --- | --- | --- | --- |
| `storage/minute_bars/{SYMBOL}/{YYYY}/{MM}/{DD}/{symbol}_minute_{date}.json` | Power Tracks Data pipeline | Minute-level OHLC bars emitted per symbol/day (JSON) | Engine daemon via `FilesystemLoader.loadMinuteBars()` |
| `storage/pipeline_outputs/{SYMBOL}/{YYYY}/{MM}/{DD}/{track_id}/` | Detector batch runs (CLI / pipeline) | `lag_manifest.json`, `decoded_fields.csv`, `summary.json`, and derived artifacts | Engine daemon + Studio for artifact reads |
| `storage/power_tracks/{SYMBOL}/{track_id}/` | `PowerTrackStorage` (engine) | Canonical artifact bundle (`window_ticks.csv`, `summary.json`, `price_path.json`, `decoded_burst.json`, etc.) | Engine daemon (`/v1/tracks/path`), Studio |
| `data/tracks/{SYMBOL}_{DATE}_tracks.json` | `PowerTrackStorage` | Deduped ledger of tracks per symbol/day (JSON array) | Engine daemon snapshot store + CLI backfills |
| `data/storage/pipeline_outputs/**` | Legacy runs / mirrors | Historical manifests for backfills | Engine daemon fallback |

## Minute Bars

- **Format**: JSON arrays (or JSONL) of `{ "ts": epochMillis, "open": ..., "high": ..., "low": ..., "close": ..., "volume": ... }`.
- **Primary Source**: Power Tracks Data repository writes them during pipeline backfills.
- **Engine Consumption**:
  - `services/daemon/src/loaders/filesystemLoader.ts` first looks for CSVs under `data/polygon_min/`.
  - When CSVs are missing, it falls back to the JSON directories above (`buildJsonMinuteBarCandidates` generates every known path variant).
  - JSON payloads are normalized via `loadMinuteBarsFromJson` → `convertJsonRecordsToMinuteBars`, including validation through `validateRealData`.
  - If neither file exists but the requested date is “today (NY)”, the daemon falls back to Polygon REST to fill the gap.
- **Optional CSV Consolidation**: When tooling still expects the legacy CSV format (`data/polygon_min/{SYMBOL}.csv`), run `python power-tracks-data/scripts/consolidate_minute_bars.py --storage-root storage/minute_bars --output-dir data/polygon_min --symbols GME` to rebuild the file directly from the JSON archives.
- **Operator Guidance**: As long as the pipeline writes JSON minute bars into `storage/minute_bars/**`, the engine does not require CSV consolidation. Use CSV only if an external system demands it.

## Track Manifests & Artifacts

1. **Detector Outputs**: When the CLI or daemon saves a track, `PowerTrackStorage` writes:
   - `data/tracks/{SYMBOL}_{DATE}_tracks.json` for the ledger.
   - `storage/power_tracks/{SYMBOL}/{track_id}/` containing:
     - `window_ticks.csv` (captured tick window)
     - `summary.json` (manifests + metrics)
     - `price_path.json` (timestamped detector price path)
     - `decoded_burst.json` (decoded payload)
2. **Shared Hub Sync**: The Data repo mirrors canonical bundles under `storage/power_tracks/**`, so Engine, Data, and Studio always read the same artifacts.
3. **Daemon Loader**: `FilesystemLoader.getTrackPricePath()` prefers the canonical `price_path.json`/`decoded_burst.json` pair and only falls back to CSVs when the bundle is missing. It also regenerates snapshots so `/v1/tracks/path` stays aligned with detector outputs.

## Decodability Guarantees

To satisfy the audit requirement that every persisted track carries decodability metrics:

- The detector populates `candidate.metrics.decodability` and `metadata.decodability` whenever decoding succeeds.
- `PowerTrackStorage.ensureDecodabilityGuarantee()` replays the artifact window if those fields are missing: it rebuilds OHLC bars from `price_path.json` or `window_ticks.csv`, recomputes D/D* using `computeDecodabilityFromPrices`, classifies the regime via `classifyRegime`, and injects the results back into both the ledger and `summary.json`.
- `storage.artifacts.test.ts` covers this path by stripping the fields before saving and asserting they reappear in the stored summary.

## Data Access Patterns

- **Files vs. SQLite**: JSON files remain the source of truth; the SQLite snapshot store (under `sqlite/powertracks.sqlite`) is a cache populated by the daemon so `/v1/tracks` queries scale.
- **REST Fallbacks**: Minute bars and Polygon summaries fetch from REST only when local files are missing and the date is current. Historical replays rely solely on filesystem data.
- **Studio**: The Studio API either calls the daemon for `/v1/...` data or reads artifacts directly (e.g., when rendering decoded bursts). The storage layout above is referenced in `docs/state-cards` within the Studio repo.

## Operator Checklist

1. Ensure the shared `storage/` tree is mounted read/write for Engine, Data, and Studio containers.
2. Run backfills via `cli/pte` so detector outputs land under `storage/power_tracks/` and ledger files under `data/tracks/`.
3. When inspecting historical data, look under:
   - Minute bars: `storage/minute_bars/{SYMBOL}/{YYYY}/{MM}/{DD}/`.
   - Track artifacts: `storage/power_tracks/{SYMBOL}/{track_id}/`.
4. When adding new ingestion sources, update `buildJsonMinuteBarCandidates` or the artifact writer to keep the shared layout consistent.

For deeper troubleshooting and recommendations, see `docs/data-architecture-analysis.md`.

## Shared Root Discovery

The daemon automatically tries to co-locate itself with the shared storage tree so each repo stays aligned without bespoke config:

- If `ENGINE_DATA_PATH`, `POWER_TRACKS_STORAGE_PATH`, or `config.data.path` points at the `storage/` directory (the root that contains `minute_bars/`, `power_tracks/`, etc.), `loadEngineConfig()` fills in any missing `detector.storage` values:
  - `detector.storage.storageDir` defaults to `<repoRoot>/data/tracks` (the ledger directory under `power-tracks-data`).
  - `detector.storage.artifactRoot` defaults to `<storageRoot>/power_tracks`.
- When the CLI/daemon runs inside the mono-repo, the fallback also checks `../power-tracks-data/storage`, so cloning the data repo alongside the engine is enough to get a working shared path.
- You can still override these defaults in `engine.config.yaml`, but most deployments now only need to set `ENGINE_DATA_PATH=/path/to/power-tracks-data/storage`, and the rest of the layout is inferred automatically.

## Data Retention & Monitoring

Shared storage grows quickly (tick windows, artifacts, minute bars). To keep disks healthy:

### Archive Cadence

1. **Daily track ledger** (`data/tracks/{SYMBOL}_{DATE}_tracks.json`)
   - Keep the latest 90 days online.
   - Monthly job: move older files into `archives/tracks/{YYYY}/{MM}/` and compress (`.jsonl.gz`).
   - Use `jq -c '.[]'` to convert arrays to JSONL before compression if downstream tooling prefers streaming formats.

2. **Artifact bundles** (`storage/power_tracks/{SYMBOL}/{track_id}`)
   - Retain canonical artifacts for 180 days.
   - Archive by symbol/month: `tar -czf archives/artifacts/GME_2024-05.tar.gz storage/power_tracks/GME/gme_202405*`.
   - Keep `decoded_burst.json` and `price_path.json` in cold storage (S3/Glacier) after archiving; leave `summary.json`/`window_ticks.csv` online for quick inspection.

3. **Minute bars** (`storage/minute_bars/{SYMBOL}/{YYYY}/{MM}/{DD}`)
   - Summaries older than 365 days can be re-generated from compressed raw feeds, so store them as `.jsonl.gz`.
   - A cron-friendly helper:
     ```bash
     find storage/minute_bars -type f -name '*.json' -mtime +365 -print0 |
       xargs -0 -I{} sh -c 'gzip -9 "{}" && touch "{}.gz"'
     ```

### Monitoring Hooks

- **Prometheus**: `EngineMetrics` already exposes HTTP counters. Add `node_filesystem_*` collectors via node-exporter on the host and alert when `storage/` usage exceeds 80%.
- **Track count growth**: Extend the existing `/metrics` scraper with `track_snapshot_total{symbol="GME"}` by counting rows in `track_snapshots`; alert if the slope exceeds a configured threshold (e.g., >1k/day sustained).
- **Maintenance script**: add a weekly job that runs:
  ```bash
  du -sh data/tracks storage/power_tracks storage/minute_bars >> logs/storage-usage.log
  ```
  Review logs in Grafana/Loki to catch sudden spikes.

Document every archive run (date, command, resulting artifact) in `docs/runbook.md` so Studio/Data teams know when cold storage is updated.
